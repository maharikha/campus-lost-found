import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import TagCard from "../components/TagCard.jsx";
import { itemName } from "../lib/format.js";
import { myReports } from "../lib/store.js";

function statusText(report, alerts) {
  if (report.status === "claimed") return "Claimed";
  if (report.status === "returned") return "Returned";
  if (report.kind === "found") return "Waiting for the owner";
  if (alerts.length === 1) return "1 possible match";
  if (alerts.length > 1) return `${alerts.length} possible matches`;
  return "Still looking";
}

export default function Home() {
  const [items, setItems] = useState(null);
  const [lost, setLost] = useState(null);
  const [error, setError] = useState("");
  const [mine, setMine] = useState([]);

  useEffect(() => {
    api.foundItems().then(setItems).catch((e) => setError(e.message));
    api.lostItems().then(setLost).catch((e) => setError(e.message));
    Promise.all(myReports().map((r) => api.report(r.id).catch(() => null))).then((rows) =>
      setMine(rows.filter(Boolean)),
    );
  }, []);

  return (
    <>
      <h1 className="visually-hidden">Campus lost and found</h1>
      {mine.length > 0 && (
        <section className="mine-wrap" aria-labelledby="mine-title">
          <h2 id="mine-title">Your reports</h2>
          <ul className="mine">
            {mine.map(({ report, alerts }) => (
              <li key={report.id}>
                <Link to={`/reports/${report.id}`} className="mine__row">
                  <span className={`side-dot side-dot--${report.kind}`} aria-hidden="true" />
                  <span>
                    {report.kind === "lost" ? `Your lost ${itemName(report)}` : `The ${itemName(report)} you found`}
                  </span>
                  <span className={`mine__status${alerts.length && report.status === "open" ? " mine__status--alert" : ""}`}>
                    {statusText(report, alerts)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="doors" aria-label="Report an item">
        <div className="door door--lost">
          <h2 className="door__title">Lost something?</h2>
          <p>Describe it in your own words. We compare it with every item handed in, photos included.</p>
          <Link className="door__cta" to="/lost">
            Report a lost item
          </Link>
        </div>
        <div className="door door--found">
          <h2 className="door__title">Found something?</h2>
          <p>Take one photo. We fill in the details and alert the owner.</p>
          <Link className="door__cta" to="/found">
            Report a found item
          </Link>
        </div>
      </section>

      <section className="section" aria-labelledby="recent-title">
        <div className="section__head">
          <h2 id="recent-title">Handed in recently</h2>
          <p className="hint">Think one is yours? Describe it and we'll check it for you.</p>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {!items && !error && <p className="hint">Loading items…</p>}
        {items?.length === 0 && (
          <div className="empty">
            Nothing has been handed in yet. Found something? <Link to="/found">Report it</Link> and the owner gets
            an alert.
          </div>
        )}
        {items?.length > 0 && (
          <div className="tag-grid">
            {items.map((item) => (
              <TagCard key={item.id} item={item} side="found">
                <Link className="btn btn--quiet btn--small" to={`/lost?category=${item.category}`}>
                  Check if it's mine
                </Link>
              </TagCard>
            ))}
          </div>
        )}
      </section>

      <section className="section" aria-labelledby="lost-title">
        <div className="section__head">
          <h2 id="lost-title">Reported lost</h2>
          <p className="hint">Seen one of these? Report it as found and the owner gets an alert.</p>
        </div>
        {!lost && !error && <p className="hint">Loading items…</p>}
        {lost?.length === 0 && <div className="empty">No one has reported anything lost yet.</div>}
        {lost?.length > 0 && (
          <div className="tag-grid">
            {lost.map((item) => (
              <TagCard key={item.id} item={item} side="lost">
                <Link className="btn btn--quiet btn--small" to={`/found?category=${item.category}`}>
                  I found this
                </Link>
              </TagCard>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
