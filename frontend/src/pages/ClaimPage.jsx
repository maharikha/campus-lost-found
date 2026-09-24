import { useEffect, useId, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import TagCard from "../components/TagCard.jsx";
import { itemName, itemTitle } from "../lib/format.js";

// Smart Claim, part 2: prove it's yours by describing the finder's private detail.
export default function ClaimPage() {
  const { id } = useParams();
  const answerId = useId();
  const [claim, setClaim] = useState(null);
  const [answer, setAnswer] = useState("");
  const [fieldError, setFieldError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.claim(id).then(setClaim).catch((e) => setError(e.message));
  }, [id]);

  async function submit(event) {
    event.preventDefault();
    if (answer.trim().length < 3) {
      setFieldError("Write a few words first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setClaim(await api.verifyClaim(id, answer.trim()));
      setAnswer("");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !claim) {
    return (
      <div className="page__head">
        <h1>We couldn't open this claim</h1>
        <p className="error" role="alert">{error}</p>
      </div>
    );
  }
  if (!claim) return <p className="hint">Loading your claim…</p>;

  const place = claim.kept_at === "With the finder" ? "the security desk" : `the ${(claim.kept_at || "security desk").toLowerCase()}`;
  const title = claim.item ? itemTitle(claim.item) : "Item";

  if (claim.status === "approved" || claim.status === "returned") {
    return (
      <div className="claim">
        <div className="ticket" role="status">
          <h1>{claim.status === "returned" ? "It's back with you" : "It's yours"}</h1>
          <p>
            {claim.status === "returned"
              ? `${title}, handed over. Enjoy having it back.`
              : `Show this code at ${place} to collect your ${itemName(claim.item || {})}.`}
          </p>
          {claim.pickup_code && (
            <div className="ticket__stub">
              <p className="hint">Pickup code</p>
              <p className="ticket__code">{claim.pickup_code}</p>
            </div>
          )}
        </div>
        <p className="section"><Link to="/">Back to the start page</Link></p>
      </div>
    );
  }

  if (claim.status === "flagged" || claim.status === "needs_staff") {
    return (
      <div className="claim">
        <header className="page__head">
          <h1>A person will check this one</h1>
          <p className="lede">
            {claim.status === "flagged"
              ? "Your answers didn't match what the finder recorded. "
              : "The finder didn't leave a private detail, so we can't check ownership online. "}
            Take your student ID to {place}; staff will look at the item with you.
          </p>
        </header>
        {claim.item && <TagCard item={claim.item} side="found" headingLevel={2} />}
      </div>
    );
  }

  const failedOnce = claim.attempts > 0;
  return (
    <div className="claim">
      <header className="page__head">
        <h1>Prove it's yours</h1>
        <p className="lede">
          The finder noted something about this item that isn't in the photo. Describe it and we'll compare.
        </p>
      </header>
      {claim.item && (
        <section className="section section--tight" aria-label="The item you're claiming">
          <TagCard item={claim.item} side="found" headingLevel={2} />
        </section>
      )}
      <form className="form section" onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor={answerId}>{claim.question}</label>
          {failedOnce && (
            <p className="error" role="alert">
              That doesn't match what the finder recorded. Try describing it another way.
            </p>
          )}
          <textarea id={answerId} value={answer} onChange={(e) => { setAnswer(e.target.value); setFieldError(""); }}
            aria-invalid={!!fieldError || undefined} aria-describedby={`${answerId}-hint${fieldError ? ` ${answerId}-error` : ""}`} />
          <p className="hint" id={`${answerId}-hint`}>
            {claim.attempts_left === 1 ? "1 try left" : `${claim.attempts_left} tries left`}. After that, the desk
            checks it with you in person.
          </p>
          {fieldError && <p className="error" id={`${answerId}-error`}>{fieldError}</p>}
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div>
          <button className="btn btn--primary" type="submit" disabled={busy}>
            {busy ? "Checking…" : "Check my answer"}
          </button>
        </div>
      </form>
    </div>
  );
}
