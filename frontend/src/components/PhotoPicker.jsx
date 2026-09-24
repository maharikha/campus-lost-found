import { useEffect, useState } from "react";

export default function PhotoPicker({ id, file, onChange, invalid, describedBy }) {
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  return (
    <div className={`photo-picker${invalid ? " is-invalid" : ""}`}>
      {preview ? <img src={preview} alt="The photo you chose" /> : <span className="photo-picker__empty" aria-hidden="true" />}
      <div className="photo-picker__actions">
        <label htmlFor={id} className="btn btn--quiet">
          {preview ? "Change photo" : "Add a photo"}
        </label>
        {preview && (
          <button type="button" className="link-button" onClick={() => onChange(null)}>
            Remove photo
          </button>
        )}
      </div>
      <input
        id={id}
        type="file"
        accept="image/*"
        className="visually-hidden"
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        onChange={(e) => {
          onChange(e.target.files?.[0] || null);
          e.target.value = "";
        }}
      />
    </div>
  );
}
