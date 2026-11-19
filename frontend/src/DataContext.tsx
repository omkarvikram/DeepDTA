type Context={
 status:string;
 drug_seen_in_fit?:boolean;
 protein_seen_in_fit?:boolean;
 pair_seen_in_fit?:boolean;
 pair_seen_in_validation?:boolean;
 explanation:string;
 limitations?:string;
};

export default function DataContext({context}:{context?:Context}){
 if(!context)return null;
 return <section className="data-context" aria-label="KIBA training-data context">
  <h3>How familiar were these inputs to the model?</h3>
  <p>{context.explanation}</p>
  {context.status==='available'&&<div className="data-context-grid">
   <span>Exact drug input in fitting data <strong>{context.drug_seen_in_fit?'Yes':'No'}</strong></span>
   <span>Exact protein sequence in fitting data <strong>{context.protein_seen_in_fit?'Yes':'No'}</strong></span>
   <span>Exact pair in fitting data <strong>{context.pair_seen_in_fit?'Yes':'No'}</strong></span>
  </div>}
  {context.status==='available'&&<small>Exact input strings only. This is not a confidence score or a test of chemical similarity.</small>}
 </section>
}
