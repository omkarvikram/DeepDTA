import React,{useState} from 'react';
import {api} from './api';

type Record={id:string,title:string,methods:string[],resolution:number|null,source:string,coordinates:string};

export default function StructureLookup({onSelect,context='viewer'}:{onSelect?:(id:string)=>void,context?:'viewer'|'docking'}){
 const [query,setQuery]=useState(''),[result,setResult]=useState<{total:number,records:Record[]}|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const searchName=async(e:React.FormEvent)=>{e.preventDefault();setBusy(true);setError('');setResult(null);
  try{setResult(await api('/structures/search?q='+encodeURIComponent(query.trim())))}catch(err:any){setError(err.message)}finally{setBusy(false)}};
 return <div className="structure-lookup">
  <h3>Find a deposited structure by name</h3>
  <p>Search the RCSB Protein Data Bank by a protein or structure name. A specific term such as “EGFR kinase” gives more useful results than “EGFR” alone.</p>
  <form className="toolbar" onSubmit={searchName}><input aria-label="Protein or structure name" required minLength={2} maxLength={100} value={query} onChange={e=>setQuery(e.target.value)} placeholder="Protein or structure name"/><button className="secondary" disabled={busy} aria-busy={busy}>{busy?'Searching PDB…':'Search PDB'}</button></form>
  {error&&<div className="message" role="status">{error}</div>}
  {result&&<p className="example-caption">{result.total?`Showing up to six of ${result.total.toLocaleString()} matching PDB entries. Check the title and organism at RCSB before choosing one.`:'No matching deposited structure was found. Try a broader protein name or a PDB ID.'}</p>}
  {result?.records.map(item=><div className="structure-hit" key={item.id}><div><strong>{item.id} · {item.title}</strong><small>{item.methods.join(', ')||'Method not listed'}{item.resolution?` · ${item.resolution} Å resolution`:''}</small></div><div className="structure-hit-actions">{onSelect&&<button type="button" className="example-chip" onClick={()=>onSelect(item.id)}>View in 3D</button>}<a href={item.source} target="_blank" rel="noreferrer">RCSB record ↗</a><a href={item.coordinates} target="_blank" rel="noreferrer">Download mmCIF ↗</a></div></div>)}
  {context==='docking'&&<p className="example-caption">A deposited mmCIF is source coordinates, not a ready receptor PDBQT. Prepare the receptor, choose a binding pocket, and upload its PDBQT below. A ligand also needs a prepared PDBQT or 3D SDF.</p>}
 </div>
}

export function Ligand3DLookup(){
 const [query,setQuery]=useState(''),[records,setRecords]=useState<any[]|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const searchName=async(e:React.FormEvent)=>{e.preventDefault();setBusy(true);setError('');setRecords(null);
  try{setRecords(await api('/search/drugs?q='+encodeURIComponent(query.trim())+'&kind=name'))}catch(err:any){setError(err.message)}finally{setBusy(false)}};
 return <div className="structure-lookup"><h3>Find a ligand 3D file by compound name</h3><p>Look up a compound in PubChem, confirm its identity, then download a 3D SDF for the ligand upload. Try “aspirin” or “imatinib”.</p>
  <form className="toolbar" onSubmit={searchName}><input aria-label="Compound name for 3D SDF" required minLength={2} maxLength={100} value={query} onChange={e=>setQuery(e.target.value)} placeholder="Compound name"/><button className="secondary" disabled={busy} aria-busy={busy}>{busy?'Searching PubChem…':'Search compound'}</button></form>
  {error&&<div className="message" role="status">{error}</div>}
  {records?.length===0&&<p>No PubChem compound matched this name. Try another name or use a known CID.</p>}
  {records?.slice(0,3).map(item=><div className="structure-hit" key={item.cid}><div><strong>PubChem CID {item.cid} · {item.name}</strong><small>{item.formula||'Formula not listed'} · {item.molecular_weight||'—'} g/mol</small></div><div className="structure-hit-actions"><a className="example-chip" href={`/api/docking/ligand-3d/${item.cid}`}>Download 3D SDF</a><a href={item.url} target="_blank" rel="noreferrer">Confirm in PubChem ↗</a></div></div>)}
  <p className="example-caption">PubChem 3D conformers are usually computed shapes, not experimental bound poses. A compound may have no 3D conformer, and protonation or tautomer choice may need adjustment before docking.</p>
 </div>
}
