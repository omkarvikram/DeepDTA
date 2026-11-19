"""Separate, practical PDFs for the three exploratory workflows."""
from reportlab.platypus import PageBreak, Spacer

from .reports import make_pdf, para, point, section, source_link


def mutation_pdf(original, mutant, mutations, user):
    change=mutant.score-original.score
    story=[para('Protein mutation comparison','Title'),
           para(f'Researcher: {user.name} | Original record: {original.id} | Mutant record: {mutant.id}','SmallNote')]
    section(story,'The result',
            f"Original predicted pKd: {original.score:.4f}. Mutant predicted pKd: {mutant.score:.4f}. Predicted change: {change:+.4f} pKd. Substitutions: {', '.join(mutations)}.")
    section(story,'What you can do with it',
            'Use the direction of the predicted change to choose mutations for follow-up. A positive change suggests stronger predicted binding in this model; a negative change suggests weaker predicted binding. Compare changes only for the same compound, model and sequence context.')
    section(story,'Limits and how to address them')
    point(story,'The change is not measured',
          'It subtracts two model estimates, each of which can be wrong. The difference is not a validated experimental change.',
          'Measure binding for wild type and mutant in the same assay, with replicates and suitable controls.')
    point(story,'Folding and function were not checked',
          'A substitution can change expression, stability or biological function even if predicted affinity rises.',
          'Check expression, folding or stability, and a relevant functional assay. Review structural evidence if available.')
    point(story,'The Davis model has no calibrated uncertainty',
          'The report cannot assign a probability that the mutant is better.',
          'Use a measured mutant panel to assess and calibrate the ranking before making broad claims.')
    section(story,'Inputs for reproducibility')
    for title,value in [('Compound SMILES',original.smiles),('Original sequence',original.sequence),
                        ('Mutated sequence',mutant.sequence),('Model version',original.model_version)]:
        story.extend([para(title,'Heading3'),para(value,'Sequence'),Spacer(1,7)])
    return make_pdf(story,'DeepDTA Research - Protein mutation comparison')


def optimisation_pdf(records, user):
    ranked=sorted(records,key=lambda record:record.score,reverse=True)
    scale='pKd' if ranked[0].dataset=='davis' else 'KIBA score'
    story=[para('Drug candidate comparison','Title'),
           para(f'Researcher: {user.name} | {len(ranked)} saved candidate predictions','SmallNote')]
    section(story,'What the ranking means',
            f'All listed compounds were scored for the same protein with the {ranked[0].dataset.upper()} model. A higher predicted {scale} suggests a candidate to examine first. The ranking is a screening priority, not measured potency, safety or a treatment recommendation.')
    section(story,'Ranked candidates')
    for rank,record in enumerate(ranked,1):
        story.append(para(f'{rank}. {record.drug_name}: predicted {scale} {record.score:.4f}','Heading3'))
        story.append(para('SMILES: '+record.smiles,'Sequence'))
        d=record.provenance.get('descriptors',{})
        if d:
            story.append(para(f"Calculated properties: MW {d.get('molecular_weight',0):.1f}; LogP {d.get('logp',0):.2f}; hydrogen-bond donors {d.get('hydrogen_bond_donors','n/a')}; acceptors {d.get('hydrogen_bond_acceptors','n/a')}; TPSA {d.get('tpsa',0):.1f}; rule-of-five violations {d.get('lipinski_violations','n/a')}.",'SmallNote'))
        story.extend([para('Saved record: '+record.id,'SmallNote'),Spacer(1,10)])
    section(story,'Limits and how to address them')
    point(story,'The rank order can be wrong',
          'The values are model estimates without a calibrated per-candidate error bar. KIBA scores are not physical Kd values.' if ranked[0].dataset=='kiba' else 'The values are model estimates without an independently verified Davis accuracy metric or a per-candidate error bar.',
          'Measure affinity for shortlisted compounds against the exact target in the same assay, with replicates and controls.')
    point(story,'Calculated properties do not prove drug usefulness',
          'Molecular weight and Lipinski indicators do not establish solubility, permeability, selectivity, metabolism, toxicity or efficacy.',
          'Confirm chemical identity and synthetic feasibility, then perform appropriate ADME, selectivity, toxicity and functional studies.')
    story.append(para('Only successfully scored and saved candidates appear here. Rejected input rows have no score.','SmallNote'))
    section(story,'Target and model')
    story.append(para(ranked[0].sequence,'Sequence'))
    story.append(para(ranked[0].model_version,'Sequence'))
    return make_pdf(story,'DeepDTA Research - Drug candidate comparison')


def structure_pdf(data, user):
    story=[para('3D structure report','Title'),
           para(f"Researcher: {user.name} | RCSB PDB: {data['id']}",'SmallNote')]
    section(story,'What was loaded',data.get('title') or 'No deposited title supplied.')
    story.append(para('Experimental method: '+(', '.join(data.get('methods') or []) or 'Not listed')+'.'))
    if data.get('resolution'):
        story.append(para(f"Reported resolution: {data['resolution']} angstrom."))
    story.append(source_link('Open the RCSB PDB entry',data['source']))
    section(story,'What you can do with the 3D view',
            'Inspect the deposited positions of protein chains and listed small components. It can guide questions about a published complex, but it does not calculate affinity for a new drug-protein pair.')
    if data.get('proteins'):
        section(story,'Deposited macromolecules')
        for protein in data['proteins']:
            story.extend([para(protein.get('name') or 'Unnamed polymer entity'),Spacer(1,5)])
    section(story,'Named deposited compounds')
    if not data.get('ligands'):
        story.append(para('No named non-polymer compound was listed for this structure. No compound name or use can be inferred from the image.'))
    for ligand in data.get('ligands',[]):
        display_name=ligand.get('drug_name') or ligand['name']
        story.append(para(f"{display_name} ({ligand['id']})",'Heading3'))
        if ligand.get('drug_name'):
            story.append(para('Deposited chemical name: '+ligand['name'],'SmallNote'))
        story.append(para(f"Kind: {ligand.get('kind') or 'Deposited non-polymer component'}. Formula: {ligand.get('formula') or 'not supplied'}."))
        if ligand.get('drug_name'):
            story.append(para('RCSB-linked DrugBank name: '+ligand['drug_name']))
        if ligand.get('indication'):
            story.append(para('Database-listed use: '+ligand['indication']))
            story.append(para('This use comes from the linked DrugBank annotation, not from the 3D coordinates. It is not treatment advice.','SmallNote'))
        else:
            story.append(para('Use: no curated indication was supplied. Do not infer a medical or practical use from the 3D image.','SmallNote'))
        story.append(source_link('RCSB chemical component',ligand['component_url']))
        if ligand.get('drugbank_url'):
            story.append(source_link('Linked DrugBank record',ligand['drugbank_url']))
        story.append(Spacer(1,10))
    if data.get('ligands_truncated'):
        story.append(para('Additional deposited components are available at the linked RCSB entry.','SmallNote'))
    if len(data.get('ligands') or [])>1:
        story.extend([PageBreak(),para('Interpretation and next steps','Title')])
    section(story,'Limits and how to address them')
    point(story,'This is not a docking prediction',
          'The coordinates are deposited structure data. They do not show where a new submitted drug would bind or prove a new interaction.',
          'Find a measured structure of the exact protein-compound complex. Treat docking as a hypothesis and verify it experimentally.')
    point(story,'A structure has experimental context',
          'Constructs, mutations, bound components, method and resolution can differ from the biological system of interest.',
          'Read the RCSB validation report and primary publication; confirm the compound and protein identities before drawing conclusions.')
    if data.get('ligands'):
        section(story,'How to verify a compound use',
                'The named ligand and any listed use come from source annotations. Open the linked chemical component and DrugBank records, confirm the exact substance or salt form, and check the current primary label or publication for a clinical or research use. The presence of a compound in one structure does not establish that use.')
        section(story,'How to verify binding for your own pair',
                'Confirm that the deposited compound matches your exact chemical structure and that the protein construct matches your sequence. Then find a measured binding assay for that same pair or perform a suitable assay with controls and replicates. A different ligand, mutation or construct is evidence about a different system.')
    return make_pdf(story,'DeepDTA Research - 3D structure report')
