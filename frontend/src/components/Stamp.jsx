const LABELS = { high: "Likely yours", medium: "Possible", low: "Unlikely" };

// Confidence as a rubber stamp: the border style carries the meaning,
// so it reads the same without color.
export default function Stamp({ confidence, band }) {
  const pct = Math.round(confidence * 100);
  return (
    <div className={`stamp stamp--${band}`} role="img" aria-label={`${pct}% confident: ${LABELS[band]}`}>
      <span className="stamp__pct">{pct}%</span>
      <span className="stamp__label">{LABELS[band]}</span>
    </div>
  );
}
