import { useEffect, useId, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import ColorPicker from "../components/ColorPicker.jsx";
import PhotoPicker from "../components/PhotoPicker.jsx";
import { categoryName, label, localNow } from "../lib/format.js";
import { rememberReport } from "../lib/store.js";

const COPY = {
  lost: {
    title: "Report a lost item",
    intro: "Describe it the way you'd describe it to a friend. We compare your words with every item handed in, photos included.",
    category: "What did you lose?",
    description: "Describe it",
    descriptionHint: "Stickers, scratches, the case, what was inside. Details are what find it.",
    writing: "Is anything written or stuck on it?",
    writingHint: "A name, roll number, label or logo. Used only for matching, never shown.",
    location: "Where did you last have it?",
    time: "When did you last see it?",
    photo: "Photo",
    photoHint: "An old photo from your gallery helps a lot.",
    contact: "Where should we alert you?",
    contactHint: "Use your email to get an alert the moment a match is handed in. Never shown to anyone.",
    submit: "Save and show matches",
    busy: "Searching…",
  },
  found: {
    title: "Report a found item",
    intro: "Start with a photo and we'll suggest the details. Anyone who reported it lost gets an alert straight away.",
    category: "What is it?",
    description: "Describe it",
    descriptionHint: "What it is and exactly where you found it. Put any names or numbers you can see on it in the private question below, not here.",
    writing: "Any name, number or text on it?",
    writingHint: "Kept private. Used only to match it with the owner.",
    location: "Where did you find it?",
    time: "When did you find it?",
    photo: "Photo",
    photoHint: "One clear photo of the item on its own.",
    secret: "Something only the owner would know",
    secretHint: "A detail that isn't visible in your photo: a mark, what's inside, the lock screen. It's never shown; the owner has to describe it to claim the item.",
    keptAt: "Where are you leaving it?",
    contact: "Your email or phone",
    contactHint: "Optional. Add your email and we'll tell you when the owner collects it.",
    submit: "Save and alert owners",
    busy: "Saving…",
  },
};

const EMPTY = { category: "", colors: [], brand: "", description: "", location: "", time: "", writing: "", secret: "", keptAt: "", contact: "" };

export default function ReportForm({ kind }) {
  const copy = COPY[kind];
  const formId = useId();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [meta, setMeta] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [values, setValues] = useState({ ...EMPTY, category: params.get("category") || "", time: localNow() });
  const [photo, setPhoto] = useState(null);
  const [suggested, setSuggested] = useState("");
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    api
      .meta()
      .then((m) => {
        setMeta(m);
        setValues((v) => ({ ...v, keptAt: v.keptAt || m.kept_at[0] }));
      })
      .catch((e) => setLoadError(e.message));
  }, []);

  const id = (name) => `${formId}-${name}`;
  const describedBy = (name, hint = true) =>
    [hint && `${id(name)}-hint`, errors[name] && `${id(name)}-error`].filter(Boolean).join(" ") || undefined;
  const update = (name) => (e) => setValues((v) => ({ ...v, [name]: e.target.value }));

  async function choosePhoto(file) {
    setPhoto(file);
    setSuggested("");
    setErrors((e) => ({ ...e, photo: undefined }));
    if (!file) return;
    try {
      const tags = await api.autotag(file);
      const fill = {};
      if (!values.category && tags.category !== "other") fill.category = tags.category;
      if (!values.colors.length && tags.colors?.length) fill.colors = tags.colors;
      if (kind === "found" && !values.writing && tags.writing) fill.writing = tags.writing;
      if (Object.keys(fill).length) {
        setValues((v) => ({ ...v, ...fill }));
        const names = Object.keys(fill).map((k) => ({ category: "the category", colors: "the colors", writing: "the writing" })[k]);
        setSuggested(`We filled in ${names.join(" and ")} from your photo. Change anything that's wrong.`);
      }
    } catch {
      /* suggestions are a bonus; the form works without them */
    }
  }

  function validate() {
    const e = {};
    if (kind === "found" && !photo) e.photo = "Add a photo so the owner can recognize it.";
    if (!values.category) e.category = "Choose what kind of item it is.";
    if (kind === "lost" && values.description.trim().length < 8) e.description = "Describe it in a few more words.";
    if (kind === "found" && !values.location) e.location = "Choose where you found it.";
    if (kind === "found" && values.secret.trim().length < 4) e.secret = "Add one detail only the owner would know.";
    if (kind === "lost" && !values.contact.trim()) e.contact = "Add an email or phone number so we can alert you.";
    return e;
  }

  async function submit(event) {
    event.preventDefault();
    const found = validate();
    setErrors(found);
    const first = Object.keys(found)[0];
    if (first) {
      document.getElementById(id(first))?.focus();
      return;
    }
    setBusy(true);
    setSubmitError("");
    const body = new FormData();
    const fields = {
      kind, description: values.description.trim(), category: values.category, colors: values.colors.join(","),
      brand: values.brand.trim(), location: values.location, time: values.time,
      text_on_item: values.writing.trim(), contact: values.contact.trim(),
    };
    if (kind === "found") Object.assign(fields, { secret_details: values.secret.trim(), kept_at: values.keptAt });
    Object.entries(fields).forEach(([k, v]) => body.append(k, v));
    if (photo) body.append("photo", photo);
    try {
      const res = await api.createReport(body);
      rememberReport(res.report.id, kind);
      navigate(`/reports/${res.report.id}`);
    } catch (e) {
      setSubmitError(e.message);
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <div className="page__head">
        <h1>{copy.title}</h1>
        <p className="error" role="alert">{loadError}</p>
      </div>
    );
  }
  if (!meta) return <p className="hint">Loading the form…</p>;

  const photoField = (
    <fieldset className="field">
      <legend id={`${id("photo")}-label`}>
        {copy.photo}
        {kind === "lost" && <span className="optional"> (optional)</span>}
      </legend>
      <p className="hint" id={`${id("photo")}-hint`}>{copy.photoHint}</p>
      <PhotoPicker id={id("photo")} file={photo} onChange={choosePhoto} invalid={!!errors.photo} describedBy={describedBy("photo")} />
      {suggested && <p className="note note--found" role="status">{suggested}</p>}
      <FieldError id={id("photo")} error={errors.photo} />
    </fieldset>
  );

  return (
    <div className={`page page--${kind}`}>
      <header className="page__head">
        <h1>{copy.title}</h1>
        <p className="lede">{copy.intro}</p>
      </header>

      <form className="form" onSubmit={submit} noValidate>
        {kind === "found" && photoField}

        <div className="field">
          <label htmlFor={id("category")}>{copy.category}</label>
          <select id={id("category")} value={values.category} onChange={update("category")}
            aria-invalid={!!errors.category || undefined} aria-describedby={describedBy("category", false)}>
            <option value="">Choose one</option>
            {meta.categories.map((c) => (
              <option key={c} value={c}>{categoryName(c).charAt(0).toUpperCase() + categoryName(c).slice(1)}</option>
            ))}
          </select>
          <FieldError id={id("category")} error={errors.category} />
        </div>

        <fieldset className="field">
          <legend id={`${id("colors")}-label`}>
            Colors <span className="optional">(pick up to 3)</span>
          </legend>
          <ColorPicker colors={meta.colors} value={values.colors} labelledBy={`${id("colors")}-label`}
            onChange={(colors) => setValues((v) => ({ ...v, colors }))} />
        </fieldset>

        <div className="field">
          <label htmlFor={id("description")}>{copy.description}</label>
          <p className="hint" id={`${id("description")}-hint`}>{copy.descriptionHint}</p>
          <textarea id={id("description")} value={values.description} onChange={update("description")}
            aria-invalid={!!errors.description || undefined} aria-describedby={describedBy("description")} />
          <FieldError id={id("description")} error={errors.description} />
        </div>

        <div className="field">
          <label htmlFor={id("brand")}>Brand <span className="optional">(optional)</span></label>
          <input id={id("brand")} type="text" value={values.brand} onChange={update("brand")} autoComplete="off" />
        </div>

        <div className="row">
          <div className="field">
            <label htmlFor={id("location")}>{copy.location}</label>
            <select id={id("location")} value={values.location} onChange={update("location")}
              aria-invalid={!!errors.location || undefined} aria-describedby={describedBy("location", false)}>
              <option value="">{kind === "lost" ? "Not sure" : "Choose a place"}</option>
              {meta.zones.map((z) => (
                <option key={z} value={z}>{label(z).charAt(0).toUpperCase() + label(z).slice(1)}</option>
              ))}
            </select>
            <FieldError id={id("location")} error={errors.location} />
          </div>
          <div className="field">
            <label htmlFor={id("time")}>{copy.time}</label>
            <input id={id("time")} type="datetime-local" value={values.time} onChange={update("time")} max={localNow()} />
          </div>
        </div>

        <div className="field">
          <label htmlFor={id("writing")}>{copy.writing} <span className="optional">(optional)</span></label>
          <p className="hint" id={`${id("writing")}-hint`}>{copy.writingHint}</p>
          <input id={id("writing")} type="text" value={values.writing} onChange={update("writing")}
            autoComplete="off" aria-describedby={describedBy("writing")} />
        </div>

        {kind === "found" && (
          <>
            <div className="field secret">
              <label htmlFor={id("secret")}>{copy.secret}</label>
              <p className="hint" id={`${id("secret")}-hint`}>{copy.secretHint}</p>
              <input id={id("secret")} type="text" value={values.secret} onChange={update("secret")} autoComplete="off"
                aria-invalid={!!errors.secret || undefined} aria-describedby={describedBy("secret")} />
              <FieldError id={id("secret")} error={errors.secret} />
            </div>
            <div className="field">
              <label htmlFor={id("keptAt")}>{copy.keptAt}</label>
              <select id={id("keptAt")} value={values.keptAt} onChange={update("keptAt")}>
                {meta.kept_at.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </div>
          </>
        )}

        {kind === "lost" && photoField}

        <div className="field">
          <label htmlFor={id("contact")}>
            {copy.contact}
            {kind === "found" && <span className="optional"> (optional)</span>}
          </label>
          <p className="hint" id={`${id("contact")}-hint`}>{copy.contactHint}</p>
          <input id={id("contact")} type="text" inputMode="email" autoComplete="email" value={values.contact}
            onChange={update("contact")} aria-invalid={!!errors.contact || undefined} aria-describedby={describedBy("contact")} />
          <FieldError id={id("contact")} error={errors.contact} />
        </div>

        {submitError && <p className="error" role="alert">{submitError}</p>}
        <div>
          <button className={`btn ${kind === "lost" ? "btn--primary" : "btn--ink"}`} type="submit" disabled={busy}>
            {busy ? copy.busy : copy.submit}
          </button>
        </div>
      </form>
    </div>
  );
}

function FieldError({ id, error }) {
  if (!error) return null;
  return (
    <p className="error" id={`${id}-error`}>
      {error}
    </p>
  );
}
