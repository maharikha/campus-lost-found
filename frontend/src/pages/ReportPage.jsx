import { useEffect, useId, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import Stamp from "../components/Stamp.jsx";
import TagCard from "../components/TagCard.jsx";
import { itemName } from "../lib/format.js";

export default function ReportPage() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setData(null);
    setResult(null);
    setError("");
    Promise.all([api.report(id), api.matches(id)])
      .then(([report, matches]) => {
        if (!alive) return;
        setData(report);
        setResult(matches);
      })
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [id]);

  if (error) {
    return (
      <div className="page__head">
        <h1>We couldn't open this report</h1>
        <p className="error" role="alert">{error}</p>
        <p><Link to="/">Go to the start page</Link></p>
      </div>
    );
  }
  if (!data || !result) return <p className="hint">Checking every item handed in…</p>;
  if (data.report.kind === "found") return <FoundConfirmation report={data.report} alerted={result.alerted} />;
  return <LostMatches report={data.report} alerts={data.alerts} result={result} setResult={setResult} />;
}

function LostMatches({ report, alerts, result, setResult }) {
  const navigate = useNavigate();
  const [claimError, setClaimError] = useState("");
  const [claiming, setClaiming] = useState(null);
  const open = report.status === "open";
  const title = itemName(report);

  async function claim(foundId) {
    setClaiming(foundId);
    setClaimError("");
    try {
      const c = await api.startClaim(foundId, report.id);
      navigate(`/claims/${c.id}`);
    } catch (e) {
      setClaimError(e.message);
      setClaiming(null);
    }
  }

  return (
    <>
      <header className="page__head">
        <h1>Matches for your {title}</h1>
        {alerts.length > 0 && (
          <p className="note" role="status">
            {alerts.length === 1
              ? alerts[0].message
              : `${alerts.length} items that may be yours have been handed in. They're listed below.`}
          </p>
        )}
      </header>

      <section className="section section--tight tag-list" aria-label="Your report">
        <TagCard item={report} side="lost" headingLevel={2} />
      </section>

      {!open && (
        <p className="note" role="status">
          You've claimed an item for this report{report.status === "returned" ? " and picked it up" : ""}.
        </p>
      )}

      {result.question && <SmartQuestion reportId={report.id} question={result.question} onAnswered={setResult} />}

      <section className="section" aria-labelledby="matches-title">
        <h2 id="matches-title">
          {result.matches.length ? "Items that could be yours" : "No matches yet"}
        </h2>
        {claimError && <p className="error" role="alert">{claimError}</p>}
        {result.matches.length === 0 && (
          <div className="empty">
            Nothing handed in looks like your {title} yet. We check every new item as it comes in and will alert you
            straight away.
          </div>
        )}
        <div className="tag-list">
          {result.matches.map((m) => (
            <TagCard key={m.report.id} item={m.report} side="found" aside={<Stamp confidence={m.confidence} band={m.band} />}>
              <Reasons pros={m.pros} cons={m.cons} />
              {open && m.report.status === "open" && (
                <button type="button" disabled={claiming !== null}
                  className={`btn btn--small ${m.band === "low" ? "btn--quiet" : "btn--primary"}`}
                  onClick={() => claim(m.report.id)}>
                  {claiming === m.report.id ? "Starting…" : "This is mine"}
                </button>
              )}
            </TagCard>
          ))}
        </div>
      </section>
    </>
  );
}

function Reasons({ pros, cons }) {
  const uid = useId();
  if (!pros.length && !cons.length) return null;
  return (
    <div className="reasons">
      {pros.length > 0 && (
        <>
          <h4 className="visually-hidden" id={`${uid}-yes`}>Why it fits</h4>
          <ul className="why why--yes" aria-labelledby={`${uid}-yes`}>
            {pros.map((p) => <li key={p}>{p}</li>)}
          </ul>
        </>
      )}
      {cons.length > 0 && (
        <>
          <h4 className="visually-hidden" id={`${uid}-no`}>What doesn't fit</h4>
          <ul className="why why--no" aria-labelledby={`${uid}-no`}>
            {cons.map((c) => <li key={c}>{c}</li>)}
          </ul>
        </>
      )}
    </div>
  );
}

// Smart Claim, part 1: when several items look alike, one answer narrows them down.
function SmartQuestion({ reportId, question, onAnswered }) {
  const inputId = useId();
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (!answer.trim()) {
      setError("Type an answer first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      onAnswered(await api.answer(reportId, question.attribute, answer.trim()));
      setAnswer("");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ask" aria-labelledby={`${inputId}-q`}>
      <p className="ask__lead">A few items look alike. One answer will narrow it down.</p>
      <h2 className="ask__question" id={`${inputId}-q`}>{question.text}</h2>
      <form onSubmit={submit} noValidate>
        <label htmlFor={inputId} className="visually-hidden">Your answer</label>
        <input id={inputId} type="text" value={answer} autoComplete="off"
          onChange={(e) => { setAnswer(e.target.value); setError(""); }}
          aria-invalid={!!error || undefined} aria-describedby={error ? `${inputId}-error` : undefined} />
        <button className="btn" type="submit" disabled={busy}>{busy ? "Checking…" : "Answer"}</button>
      </form>
      {error && <p className="error" id={`${inputId}-error`} role="alert">{error}</p>}
    </section>
  );
}

function FoundConfirmation({ report, alerted }) {
  const withFinder = report.kept_at === "With the finder";
  return (
    <>
      <header className="page__head">
        <h1>Thanks for handing it in</h1>
        <p className="lede">
          {alerted > 0
            ? `We alerted ${alerted === 1 ? "1 person" : `${alerted} people`} whose lost report matches this item.`
            : "Nobody has reported it lost yet. When they do, it will be the first thing they see."}{" "}
          {withFinder
            ? "Keep it safe for now; the desk will contact you if the owner claims it."
            : `Please take it to the ${(report.kept_at || "security desk").toLowerCase()}.`}
        </p>
      </header>
      <section className="section section--tight" aria-label="The item you found">
        <TagCard item={report} side="found" headingLevel={2}>
          <p className="hint">The detail only the owner knows stays private.</p>
        </TagCard>
      </section>
      <p className="section">
        <Link className="btn btn--quiet" to="/found">Report another item</Link>
      </p>
    </>
  );
}
