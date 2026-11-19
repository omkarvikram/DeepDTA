import type {Prediction} from './api';

export default function EvidenceStatus({prediction,evidence}:{prediction:Prediction,evidence?:any}){
 const comparable=evidence?.records?.filter((record:any)=>record.numerically_comparable).length||0;
 return <section className="evidence-status" aria-label="Evidence status">
  <h3>What supports this result?</h3>
  <div className="evidence-status-row"><span className="evidence-dot model-dot"/><div><strong>Model prediction</strong><small>{prediction.dataset==='davis'?'Davis predicted pKd':'Two-input KIBA predicted score'} · saved with model version</small></div><span className="evidence-state">Available</span></div>
  <div className="evidence-status-row"><span className="evidence-dot reference-dot"/><div><strong>Recorded KIBA value</strong><small>Separate supplied dataset lookup; never treated as this prediction</small></div><span className="evidence-state">Check separately</span></div>
  <div className="evidence-status-row"><span className="evidence-dot assay-dot"/><div><strong>Published assay record</strong><small>{evidence?`${evidence.returned||0} matching record(s) saved; ${comparable} eligible for numeric comparison`:'Not fetched for this prediction'}</small></div><span className="evidence-state">{evidence?'Snapshot saved':'Not checked'}</span></div>
  <p className="evidence-status-limit">Published records can support a comparison; they do not independently validate the model. Training overlap and exact assay constructs remain unverified.</p>
 </section>
}
