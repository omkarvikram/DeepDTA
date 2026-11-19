export default function ModelValidation({model}:{model:any}){
 if(!model)return null;
 if(model.dataset==='davis'){const m=model.metrics?.test;return <section className="model-validation" aria-label="Davis model evaluation"><h3>Davis model evaluation</h3>{m?<><p><strong>MSE {m.mse.toFixed(4)} · Concordance index {m.concordance_index.toFixed(4)}</strong></p><p>{m.n.toLocaleString()} benchmark pairs. RMSE {m.rmse.toFixed(4)} pKd. Lower MSE and higher concordance are better.</p><p>{model.benchmark_note}</p></>:<p>No verified benchmark is attached to this model.</p>}<p>{model.external_validation?.reason||model.limitations}</p></section>;}
 const pair=model.metrics?.test;
 const exposure=model.test_exposure;
 const cold=model.cold_benchmarks?.results;
 const rows=[['Unseen drugs','cold_drug'],['Unseen proteins','cold_protein'],['Unseen both','cold_both']] as const;
 return <section className="model-validation" aria-label="KIBA validation evidence">
  <h3>How well has KIBA been tested?</h3>
  {pair&&<p><strong>Deployed model - held-out pairs:</strong> {pair.n.toLocaleString()} test pairs; RMSE {pair.rmse.toFixed(3)}, Spearman {pair.spearman.toFixed(3)}. Drugs and proteins can overlap training.</p>}
  {exposure&&<p><strong>What that test covers:</strong> Of {exposure.test_pairs.toLocaleString()} test rows, {exposure.unseen_drug_rows} had an unseen exact drug input and {exposure.unseen_protein_rows} had an unseen exact protein sequence. {exposure.exact_fit_pair_repeats} rows repeated an exact fitting pair and {exposure.exact_validation_pair_only_repeats} repeated a validation-only pair. The {exposure.new_pairs_of_seen_entities.toLocaleString()} new pairs of familiar inputs had RMSE {exposure.new_pairs_of_seen_entities_rmse.toFixed(3)}. A separate test is needed to evaluate generalisation to unseen drugs or proteins.</p>}
  {cold&&<><p><strong>Separate cold-split benchmark models:</strong> retrained from scratch with entire drugs, proteins or both held out from training. These results assess the modelling approach; they are not measurements of the deployed model on those pairs.</p><div className="table-wrap"><table><thead><tr><th>Test split</th><th>Pairs</th><th>RMSE</th><th>Mean baseline RMSE</th><th>Spearman</th></tr></thead><tbody>{rows.map(([label,key])=>{const row=cold[key];return row?<tr key={key}><td>{label}</td><td>{row.metrics.n.toLocaleString()}</td><td>{row.metrics.rmse.toFixed(3)}</td><td>{row.metrics.training_mean_baseline_rmse.toFixed(3)}</td><td>{row.metrics.spearman.toFixed(3)}</td></tr>:null})}</tbody></table></div><p>{model.cold_benchmarks.limitations}</p></>}
  <p><strong>Independent external validation:</strong> {model.external_validation?.reason||'Not established.'}</p>
 </section>
}
