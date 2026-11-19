import type {Prediction} from './api';

export default function NumericalAccuracy({prediction}:{prediction:Prediction}){
 const accuracy=prediction.provenance?.numerical_accuracy;
 if(prediction.dataset==='davis'){const m=prediction.provenance?.metrics?.test;return <section className="confidence-panel" aria-label="Davis numerical accuracy"><h3>Davis evaluation and prediction accuracy</h3>{m&&<p><strong>Benchmark MSE: {m.mse.toFixed(4)} · Concordance: {m.concordance_index.toFixed(4)}</strong><br/>RMSE: {m.rmse.toFixed(4)} pKd across {m.n.toLocaleString()} pairs.</p>}<p>{m?'These numbers describe error across a dataset. They do not tell us the probability that this individual value is correct.':'This saved prediction has no verified benchmark attached.'}</p><small>{prediction.provenance?.benchmark_note} A per-prediction accuracy percentage requires separate calibration against compatible experimental Kd values with training overlap checked.</small></section>;}

 if(accuracy?.status!=='available')return <section className="confidence-panel" aria-label="Numerical accuracy unavailable"><h3>Numerical accuracy</h3><p>No validated percentage is available for this input.</p><small>{accuracy?.reason||'No matching calibration evidence was saved with this prediction.'}</small></section>;
 const percent=Number(accuracy.estimated_accuracy_percent);
 const interval=accuracy.prediction_interval;
 return <section className="confidence-panel" aria-label="Numerical accuracy estimate">
  <span className="eyebrow">ACCURACY OF THE VALUE · KIBA SCORE</span>
  <div className="accuracy-heading"><strong>{percent.toFixed(1)}%</strong><span>estimated within ±{Number(accuracy.tolerance_kiba).toFixed(1)} KIBA units</span></div>
  <div className="accuracy-meter" role="img" aria-label={`${percent.toFixed(1)} percent of comparable calibration predictions were within plus or minus ${accuracy.tolerance_kiba} KIBA units`}><i style={{width:`${Math.max(0,Math.min(100,percent))}%`}}/></div>
  <p>For predictions in this score range, {percent.toFixed(1)}% of {Number(accuracy.score_band_calibration_pairs).toLocaleString()} held-out calibration pairs were this close to their recorded KIBA values. A separate audit group scored {Number(accuracy.score_band_audit_percent).toFixed(1)}% across {Number(accuracy.score_band_audit_pairs).toLocaleString()} pairs.</p>
  <div className="accuracy-range"><span>90% prediction range</span><strong>{Number(interval.lower).toFixed(3)} to {Number(interval.upper).toFixed(3)}</strong><small>KIBA units · {Number(interval.audit_coverage_percent).toFixed(1)}% observed audit coverage</small></div>
  <small>This estimates closeness of the numerical value, not whether binding occurs. It is a group estimate for familiar drug and protein inputs; it is not certainty for this exact pair or validation on new molecules or targets.</small>
 </section>;
}
