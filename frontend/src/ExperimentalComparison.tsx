import {useState} from 'react';
import {post} from './api';
import type {Prediction} from './api';
import EvidenceStatus from './EvidenceStatus';

export default function ExperimentalComparison({prediction,compact=false}:{prediction:Prediction,compact?:boolean}){
 const id=prediction.id;
 const [compound,setCompound]=useState('');
 const [accession,setAccession]=useState('');
 const [data,setData]=useState<any>(prediction.provenance.experimental_evidence||null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const records:any[]=data?.records||[];
 const comparable=records.filter(record=>record.numerically_comparable).length;
 const fetchEvidence=async()=>{
  setBusy(true);setError('');
  try{
   const evidence=await post(`/predictions/${id}/experimental`,{compound_id:compound.trim(),accession:accession.trim()});
   setData(evidence);
  }catch(cause:any){setError(cause.message)}finally{setBusy(false)}
 };
 return <>{compact?<span className={'evidence-compact '+(data?'has-evidence':'')}>Published assay: {data?`${data.returned||0} record(s) saved`:'not checked'}</span>:<EvidenceStatus prediction={prediction} evidence={data}/>}<details className="experimental-comparison">
  <summary>Published assay evidence {data?<span className="badge success">Snapshot saved</span>:<span className="badge">Not checked</span>}</summary>
  <p>Search ChEMBL activity records for this saved prediction. Supplied KIBA inputs can resolve their IDs automatically. Otherwise, enter a ChEMBL compound ID and UniProt accession. This lookup does not run a model or use credits.</p>
  <details className="comparison-rules"><summary>When is a numeric comparison allowed?</summary><ul>
   <li>The saved result must be Davis pKd, and the published endpoint must be an exact Kd with a positive supported concentration.</li>
   <li>Compound structure, including stereochemistry, must match; the submitted protein must match the UniProt reference sequence.</li>
   <li>The assay must directly assign a single protein, with no variant, validity flag or possible duplicate.</li>
   <li>Training-data overlap, the exact laboratory construct and assay conditions remain unverified even when these checks pass.</li>
  </ul></details>
  <div className="two-col"><label>ChEMBL compound ID<input placeholder="Automatic, or CHEMBL1087421" value={compound} maxLength={30} disabled={busy} aria-busy={busy} onChange={event=>setCompound(event.target.value)}/></label>
  <label>UniProt accession<input placeholder="Automatic, or O00141" value={accession} maxLength={20} disabled={busy} aria-busy={busy} onChange={event=>setAccession(event.target.value)}/></label></div>
  <button type="button" className="secondary" disabled={busy} aria-busy={busy} onClick={fetchEvidence}>{busy?'Fetching records…':data?'Refresh published records':'Fetch published records'}</button>
  <p><small>Identifiers are sent to ChEMBL and UniProt. A successful response is saved with this prediction and included in later PDF downloads. A failed refresh leaves the previous saved snapshot intact.</small></p>
  {error&&<div className="message" role="alert">{error}{data?' The prior saved snapshot is still shown below.':''}</div>}
  {data&&<div className="evidence-results" role="status">
   <div className="evidence-summary"><div><span className="eyebrow">PUBLISHED RECORDS - SEPARATE FROM THE MODEL SCORE</span><h3>{data.compound_id} / {data.accession}</h3><p>{data.sequence_match?'UniProt reference sequence matches.':'Reference sequence differs; numeric comparison is disabled.'}</p></div><div><strong>{data.returned||0}</strong><small>records shown</small></div><div><strong>{comparable}</strong><small>numeric comparisons</small></div></div>
   {data.truncated&&<p className="warning-text">Only the first 50 matching records were retrieved.</p>}
   {!records.length&&<p>{data.message||'No matching published records were found. This does not establish absence of binding.'}</p>}
   {records.map(record=><section className="evidence-record" key={record.activity_id}>
    <div className="evidence-record-heading"><h3>{record.endpoint||'Unspecified endpoint'} {record.relation||'?'} {record.value??'not reported'} {record.units||''}</h3><span className={'badge '+(record.numerically_comparable?'success':'warning')}>{record.numerically_comparable?'Comparable Davis Kd':'Context only'}</span></div>
    <p>{record.description||'No assay description supplied.'}</p><p>{record.organism||'Organism not specified'} · {record.year||'Year not specified'} · {record.confidence_description||'Target assignment not specified'}</p>
    {record.numerically_comparable?<p><strong>Experimental pKd {record.experimental_pkd.toFixed(4)} · predicted pKd {data.predicted_score.toFixed(4)} · absolute difference {record.absolute_error_pkd.toFixed(4)}</strong><br/>This is a literature comparison, not independent validation.</p>:<div className="comparison-reasons"><strong>Why no numeric difference?</strong><ul>{record.reasons.map((reason:string)=><li key={reason}>{reason}</li>)}</ul></div>}
    <div className="form-actions"><a href={record.source_url} target="_blank" rel="noreferrer">Activity record ↗</a><a href={record.assay_url} target="_blank" rel="noreferrer">Assay details ↗</a>{record.document_url&&<a href={record.document_url} target="_blank" rel="noreferrer">Publication ↗</a>}</div>
   </section>)}
   <p className="evidence-status-limit">{data.limitations}</p>{data.retrieved_at&&<small>Retrieved {new Date(data.retrieved_at).toLocaleString()}</small>}
  </div>}
 </details></>
}
