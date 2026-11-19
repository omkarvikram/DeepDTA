type Guide = {
  label: string;
  band: 'weak' | 'moderate' | 'strong' | 'unknown';
  explanation: string;
  basis: string;
  caution: string;
  source: string;
};

export default function StrengthGuide({guide}:{guide?:Guide}) {
  if (!guide) return null;
  return <section className={`strength-guide strength-${guide.band}`} aria-label="Predicted binding strength">
    <div className="strength-heading"><span>Predicted binding strength</span><strong>{guide.label}</strong></div>
    <div className="strength-bands" aria-hidden="true">
      {(['weak','moderate','strong'] as const).map(band=><span key={band} className={guide.band===band?'selected':''}>{band}</span>)}
    </div>
    <p>{guide.explanation}</p>
    <small>{guide.basis}</small>
    <small>{guide.caution} <a href={guide.source} target="_blank" rel="noreferrer">Benchmark source ↗</a></small>
  </section>;
}

export function StrengthTag({guide}:{guide?:Guide}) {
  if (!guide) return null;
  return <span className={`strength-tag strength-${guide.band}`} title={guide.caution}>Predicted {guide.label.toLowerCase()}</span>;
}
