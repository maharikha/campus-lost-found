const SWATCHES = {
  black: "#1f2023", white: "#ffffff", gray: "#9aa1ab", blue: "#2f6fe0", red: "#d93025",
  green: "#1e8e3e", yellow: "#f7c21a", orange: "#f28b24", pink: "#ef6ea8", purple: "#8e4fc2", brown: "#8a5a33",
};

export default function ColorPicker({ colors, value, onChange, labelledBy }) {
  function toggle(color) {
    onChange(value.includes(color) ? value.filter((c) => c !== color) : [...value, color].slice(-3));
  }
  return (
    <div className="chips" role="group" aria-labelledby={labelledBy}>
      {colors.map((color) => (
        <button key={color} type="button" className="chip" aria-pressed={value.includes(color)} onClick={() => toggle(color)}>
          <span className="chip__dot" style={{ background: SWATCHES[color] || color }} aria-hidden="true" />
          {color}
        </button>
      ))}
    </div>
  );
}
