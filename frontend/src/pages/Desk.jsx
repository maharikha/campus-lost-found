import { useCallback, useEffect, useId, useState } from "react";
import { api } from "../api.js";
import { categoryName, itemName, itemTitle, label, when } from "../lib/format.js";

const STATUS = { pending: "Answering", approved: "Ready for pickup", returned: "Returned", flagged: "Needs a person", needs_staff: "Needs a person" };

// For the lost-and-found desk. Put this behind a staff login before real use.
export default function Desk() {
  const codeId = useId();
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [code, setCode] = useState("");
  const [handover, setHandover] = useState({ ok: "", error: "" });

  const load = useCallback(() => {
    api.stats().then(setStats).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function confirm(event) {
    event.preventDefault();
    if (code.trim().length < 6) {
      setHandover({ ok: "", error: "Pickup codes have 6 characters." });
      return;
    }
    try {
      const res = await api.confirmPickup(code.trim().toUpperCase());
      setHandover({ ok: `Handed over: the ${res.item ? itemName(res.item) : "item"}. Its claim is closed.`, error: "" });
      setCode("");
      load();
    } catch (e) {
      setHandover({ ok: "", error: e.message });
    }
  }

  const counts = stats?.counts;
  const maxHot = Math.max(1, ...(stats?.hotspots || []).map(([, n]) => n));
  const maxCat = Math.max(1, ...(stats?.categories || []).map(([, n]) => n));

  return (
    <>
      <header className="page__head">
        <h1>Lost-and-found desk</h1>
        <p className="lede">Hand items over, see what needs a person, and spot where things go missing.</p>
      </header>

      <form className="handover" onSubmit={confirm} noValidate>
        <div className="field">
          <label htmlFor={codeId}>Pickup code</label>
          <input id={codeId} type="text" value={code} maxLength={6} autoComplete="off" spellCheck="false"
            onChange={(e) => { setCode(e.target.value); setHandover({ ok: "", error: "" }); }}
            aria-invalid={!!handover.error || undefined} aria-describedby={`${codeId}-status`} />
        </div>
        <button className="btn btn--ink" type="submit">Mark as handed over</button>
        <p id={`${codeId}-status`} className={handover.error ? "error" : handover.ok ? "ok" : "hint"} role="status">
          {handover.error || handover.ok || "Ask the owner for the code on their phone."}
        </p>
      </form>

      {error && <p className="error" role="alert">{error}</p>}
      {counts && (
        <>
          <ul className="numbers">
            <li><strong>{counts.found_open}</strong><span>Items waiting for owners</span></li>
            <li><strong>{counts.lost_open}</strong><span>Open lost reports</span></li>
            <li><strong>{counts.claimed}</strong><span>Claimed, not yet collected</span></li>
            <li><strong>{counts.returned}</strong><span>Returned to owners</span></li>
            <li><strong>{counts.alerts}</strong><span>Owner alerts sent</span></li>
            <li className={counts.flagged ? "numbers__alert" : ""}><strong>{counts.flagged}</strong><span>Claims that need a person</span></li>
          </ul>

          <div className="desk-grid">
            <section aria-labelledby="hot-title">
              <h2 id="hot-title">Where things go missing</h2>
              {stats.hotspots.length === 0 ? <p className="hint">No locations reported yet.</p> : (
                <ul className="bars">
                  {stats.hotspots.map(([place, n]) => (
                    <li key={place}>
                      <span>{label(place)}</span>
                      <span className="bars__track" aria-hidden="true"><span className="bars__fill" style={{ width: `${(n / maxHot) * 100}%` }} /></span>
                      <span>{n}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section aria-labelledby="cat-title">
              <h2 id="cat-title">Most reported items</h2>
              <ul className="bars bars--found">
                {stats.categories.map(([cat, n]) => (
                  <li key={cat}>
                    <span>{categoryName(cat)}</span>
                    <span className="bars__track" aria-hidden="true"><span className="bars__fill" style={{ width: `${(n / maxCat) * 100}%` }} /></span>
                    <span>{n}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <section className="section" aria-labelledby="claims-title">
            <div className="section__head">
              <h2 id="claims-title">Recent claims</h2>
              <button type="button" className="btn btn--quiet btn--small" onClick={load}>Refresh</button>
            </div>
            {stats.claims.length === 0 ? <p className="hint">No claims yet.</p> : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th scope="col">Item</th><th scope="col">Status</th><th scope="col">Wrong answers</th><th scope="col">Started</th></tr>
                  </thead>
                  <tbody>
                    {stats.claims.map((c) => (
                      <tr key={c.id}>
                        <td>{c.item ? itemTitle(c.item) : "Deleted item"}</td>
                        <td><span className={`status status--${c.status}`}>{STATUS[c.status] || c.status}</span></td>
                        <td>{c.status === "approved" || c.status === "returned" ? Math.max(0, c.attempts - 1) : c.attempts}</td>
                        <td>{when(c.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}
