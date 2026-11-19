"""Bounded AutoDock Vina runs on prepared 3D PDBQT structures."""
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Response
from fastapi.responses import FileResponse
from pydantic import ValidationError
from . import ml, search
from .config import BACKEND, ROOT
from .db import get_db
from .security import current_user

router = APIRouter(prefix='/api/docking')
EXAMPLE = BACKEND / 'data/docking_examples'
BINARIES = {
    ('Darwin','arm64'): 'vina_1.2.7_mac_aarch64',
    ('Darwin','x86_64'): 'vina_1.2.7_mac_x86_64',
    ('Linux','aarch64'): 'vina_1.2.7_linux_aarch64',
    ('Linux','x86_64'): 'vina_1.2.7_linux_x86_64',
    ('Windows','AMD64'): 'vina_1.2.7_win.exe',
}

def binary_path():
    name = BINARIES.get((platform.system(), platform.machine()))
    path = BACKEND / 'tools/vina' / name if name else None
    if not path or not path.is_file():
        raise HTTPException(503, 'A Vina executable for this operating system is not included.')
    return path

def prepared_file(upload, kind):
    if not upload or not upload.filename.lower().endswith(('.pdbqt','.sdf') if kind=='ligand' else ('.pdbqt',)):
        raise HTTPException(422, f'Upload a prepared {kind} .pdbqt file'+(' or a 3D ligand .sdf.' if kind=='ligand' else '.'))
    data = upload.file.read(1_000_001)
    if len(data)>1_000_000: raise HTTPException(413, f'{kind.capitalize()} file exceeds 1 MB.')
    try: value = data.decode('ascii')
    except UnicodeError: raise HTTPException(422, 'PDBQT must be plain ASCII text.')
    if upload.filename.lower().endswith('.sdf'):
        if '\x00' in value or 'M  END' not in value: raise HTTPException(422,'Ligand SDF is not a valid molfile.')
        return data
    if not re.search(r'^ATOM  |^HETATM', value, re.M) or '\x00' in value:
        raise HTTPException(422, f'{kind.capitalize()} PDBQT contains no atoms.')
    if kind=='ligand' and ('ROOT' not in value or 'TORSDOF' not in value):
        raise HTTPException(422, 'The ligand must be a prepared PDBQT with ROOT and TORSDOF records.')
    return data

def pdb_for_viewer(pdbqt):
    """Convert coordinate/element columns for display only; Vina uses PDBQT."""
    lines=[]
    elements={'A':'C','NA':'N','OA':'O','SA':'S','HD':'H'}
    for line in pdbqt.splitlines():
        if line.startswith(('ATOM  ','HETATM')):
            atom_type=line.split()[-1].upper()
            element=elements.get(atom_type,atom_type.capitalize())
            lines.append(line[:66].ljust(76)+element.rjust(2))
    return '\n'.join(lines)+'\nEND\n'

@router.get('/example')
def example(user=Depends(current_user)):
    return {'name':'Imatinib with ABL kinase (PDB 1IEP)',
            'receptor':'rec_1iep.pdbqt','ligand':'imatinib_protomer-1.pdbqt',
            'center':[15.190,53.903,16.917],'size':[18.664,26.739,23.526],
            'source':'https://github.com/forlilab/Meeko/tree/develop/example/tutorial1',
            'structure_source':'https://www.rcsb.org/structure/1IEP',
            'protein_sequence':(EXAMPLE/'ABL1_P00519.fasta').read_text().split('\n',1)[1].strip(),
            'protein_source':'https://www.uniprot.org/uniprotkb/P00519/entry',
            'note':'Prepared structures from the Meeko tutorial. Docking reproduces a computational pose search, not a measured binding affinity.'}

@router.get('/example/{name}')
def example_file(name:str,user=Depends(current_user)):
    if name not in ('rec_1iep.pdbqt','imatinib_protomer-1.pdbqt','imatinib_3d.sdf','ABL1_P00519.fasta'):
        raise HTTPException(404,'Example file not found.')
    return FileResponse(EXAMPLE/name,media_type='text/plain',filename=name)

@router.get('/ligand-3d/{cid}')
def pubchem_ligand_3d(cid:int,user=Depends(current_user)):
    """Source a PubChem 3D conformer; do not claim it is a bound pose."""
    if cid<1: raise HTTPException(422,'Enter a positive PubChem CID.')
    try:
        response=search.fetch(f'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/SDF',
                              {'record_type':'3d'})
    except HTTPException as exc:
        if exc.status_code==404: raise HTTPException(404,'PubChem has no 3D conformer for this compound.') from exc
        raise
    if len(response.content)>1_000_000: raise HTTPException(413,'PubChem 3D SDF exceeds the 1 MB docking upload limit.')
    if b'M  END' not in response.content: raise HTTPException(502,'PubChem did not return a usable 3D SDF.')
    return Response(response.content,media_type='chemical/x-mdl-sdfile',
                    headers={'Content-Disposition':f'attachment; filename="pubchem-{cid}-3d.sdf"',
                             'X-Structure-Source':f'PubChem CID {cid}'})

@router.post('/run')
def dock(receptor:UploadFile|None=File(None),ligand:UploadFile|None=File(None),
         example_input:bool=Form(False),center_x:float=Form(15.190),center_y:float=Form(53.903),
         center_z:float=Form(16.917),size_x:float=Form(18.664),size_y:float=Form(26.739),
         size_z:float=Form(23.526),predict_affinity:bool=Form(False),protein_sequence:str=Form(''),
         user=Depends(current_user),db=Depends(get_db)):
    center=(center_x,center_y,center_z); size=(size_x,size_y,size_z)
    if any(not -999 < x < 999 for x in center) or any(not 4 <= x <= 40 for x in size):
        raise HTTPException(422,'Box center must be finite; each box side must be 4–40 Å.')
    sdf_input=bool(not example_input and ligand and ligand.filename.lower().endswith('.sdf'))
    if example_input:
        receptor_data=(EXAMPLE/'rec_1iep.pdbqt').read_bytes()
        ligand_data=(EXAMPLE/'imatinib_protomer-1.pdbqt').read_bytes()
    else:
        receptor_data=prepared_file(receptor,'receptor')
        ligand_data=prepared_file(ligand,'ligand')
    with tempfile.TemporaryDirectory(prefix='deepdta-dock-') as directory:
        directory=Path(directory)
        rp,lp,op=directory/'receptor.pdbqt',directory/'ligand.pdbqt',directory/'poses.pdbqt'
        rp.write_bytes(receptor_data)
        if sdf_input:
            sdf=directory/'ligand.sdf';sdf.write_bytes(ligand_data)
            prepare=Path(sys.executable).parent/('mk_prepare_ligand.exe' if platform.system()=='Windows' else 'mk_prepare_ligand.py')
            if not prepare.is_file(): raise HTTPException(503,'Meeko ligand preparation is unavailable on this server.')
            try: converted=subprocess.run([str(prepare),'-i',str(sdf),'-o',str(lp)],capture_output=True,text=True,timeout=30)
            except subprocess.TimeoutExpired: raise HTTPException(504,'Ligand preparation timed out.')
            if converted.returncode or not lp.is_file():
                raise HTTPException(422,'Meeko could not prepare this 3D SDF. Check coordinates, bond orders and protonation.')
        else: lp.write_bytes(ligand_data)
        command=[str(binary_path()),'--receptor',str(rp),'--ligand',str(lp),'--out',str(op),
                 '--center_x',str(center_x),'--center_y',str(center_y),'--center_z',str(center_z),
                 '--size_x',str(size_x),'--size_y',str(size_y),'--size_z',str(size_z),
                 '--cpu','1','--exhaustiveness','8','--num_modes','5','--seed','7']
        try: run=subprocess.run(command,capture_output=True,text=True,timeout=120,check=False)
        except subprocess.TimeoutExpired: raise HTTPException(504,'Docking exceeded the two-minute limit. Try a smaller ligand or box.')
        if run.returncode or not op.is_file():
            raise HTTPException(422,'Vina could not dock these prepared structures. Check atom types, hydrogens and box placement.')
        scores=[float(x) for x in re.findall(r'^REMARK VINA RESULT:\s+(-?\d+(?:\.\d+)?)',op.read_text(),re.M)]
        if not scores: raise HTTPException(502,'Vina returned no readable poses.')
        pose=op.read_text().split('ENDMDL',1)[0]+'ENDMDL\n'
        ligand_smiles=re.search(r'^REMARK SMILES\s+(.+)$',lp.read_text(),re.M)
    affinity=None; affinity_error=None
    if predict_affinity:
        if not protein_sequence.strip(): affinity_error='A complete protein sequence is required for the KIBA prediction.'
        elif not ligand_smiles: affinity_error='The prepared ligand file has no REMARK SMILES identity; docking succeeded, but KIBA needs a SMILES string.'
        else:
            try:
                from .main import PredictInput, run_prediction, serialize
                prediction=run_prediction(PredictInput(smiles=ligand_smiles.group(1).strip(),sequence=protein_sequence,
                    dataset='kiba',drug_name='Imatinib (3D example)' if example_input else 'Uploaded 3D ligand',
                    protein_name='ABL1 (UniProt P00519)' if example_input else 'Supplied full target sequence'),user,db)
                affinity=serialize(prediction)
            except (HTTPException,ValueError,ValidationError,ml.ModelUnavailable) as exc:
                db.rollback();affinity_error=getattr(exc,'detail',str(exc))
    return {'scores_kcal_mol':scores,'best_score_kcal_mol':scores[0],
            'pose_pdbqt':pose,'pose_pdb':pdb_for_viewer(pose),
            'receptor_pdb':pdb_for_viewer(receptor_data.decode('ascii')),
            'affinity_prediction':affinity,'affinity_error':affinity_error,
            'engine':'AutoDock Vina 1.2.7','seed':7,'exhaustiveness':8,'center':center,'size':size,
            'example':example_input,'ligand_prepared_from_sdf':sdf_input,'source':'https://autodock-vina.readthedocs.io/en/stable/',
            'warning':'Vina docking energy is a computed scoring-function result, not a measured Kd, pKd, or probability of binding. Receptor preparation, protonation, binding-site choice and flexibility can change the result. Optional KIBA inference uses ligand SMILES and the supplied protein sequence; it does not learn from the docked pose.'}
