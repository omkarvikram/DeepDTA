import {api} from './api';

export const KIBA_EXAMPLES = [
  {drugId:'CHEMBL1984586',proteinId:'P36888',label:'CHEMBL1984586 · P36888',detail:'Recorded test pair · 993-residue target'},
  {drugId:'CHEMBL2000029',proteinId:'P49760',label:'CHEMBL2000029 · P49760',detail:'Recorded test pair · 499-residue target'},
  {drugId:'CHEMBL1967720',proteinId:'P49841',label:'CHEMBL1967720 · P49841',detail:'Recorded test pair · 420-residue target'},
  {drugId:'CHEMBL1975490',proteinId:'P48729',label:'CHEMBL1975490 · P48729',detail:'Recorded test pair · 337-residue target'},
  {drugId:'CHEMBL1968070',proteinId:'P45984',label:'CHEMBL1968070 · P45984',detail:'Recorded test pair · 424-residue target'},
  {drugId:'CHEMBL438485',proteinId:'O00141',label:'CHEMBL438485 · O00141',detail:'Recorded test pair · 431-residue target'},
] as const;

export const DAVIS_EXAMPLES = [
  {id:'acetic',label:'Acetic acid · synthetic sequence',smiles:'CC(=O)O',sequence:'ACDEFGHIKLMNPQRSTVWY',drugName:'Acetic acid',proteinName:'Synthetic test sequence'},
  {id:'ethanol',label:'Ethanol · synthetic sequence',smiles:'CCO',sequence:'MKTAYIAKQRQISFVKSHFSRQDILD',drugName:'Ethanol',proteinName:'Synthetic test sequence'},
  {id:'glycine',label:'Glycine · synthetic sequence',smiles:'NCC(=O)O',sequence:'MALWMRLLPLLALLALWGPGPG',drugName:'Glycine',proteinName:'Synthetic test sequence'},
  {id:'acetone',label:'Acetone · synthetic sequence',smiles:'CC(=O)C',sequence:'ACDEFGHIKLMNPQRSTVWY',drugName:'Acetone',proteinName:'Synthetic test sequence'},
] as const;

export async function loadKibaExample(example:{drugId:string,proteinId:string}){
  const params=new URLSearchParams({drug_id:example.drugId,protein_id:example.proteinId});
  const pair=await api('/kiba/pair?'+params);
  if(pair.status==='unmeasured'||pair.score==null)throw new Error('This pair has no recorded KIBA value.');
  return pair;
}
