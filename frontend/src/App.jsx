import { Link, NavLink, Route, Routes } from "react-router-dom";
import ClaimPage from "./pages/ClaimPage.jsx";
import Desk from "./pages/Desk.jsx";
import Home from "./pages/Home.jsx";
import ReportForm from "./pages/ReportForm.jsx";
import ReportPage from "./pages/ReportPage.jsx";

function TagMark() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <path d="M11 3h18v26H11L3 21V11z" fill="#FFC93C" stroke="#16213A" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="11" cy="16" r="2.6" fill="#16213A" />
    </svg>
  );
}

function NotFound() {
  return (
    <div className="page__head">
      <h1>That page doesn't exist</h1>
      <p className="lede">
        The link may be mistyped. <Link to="/">Go to the start page</Link>.
      </p>
    </div>
  );
}

export default function App() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <Link to="/" className="wordmark">
          <TagMark />
          Campus Lost &amp; Found
        </Link>
        <nav className="topnav" aria-label="Main">
          <NavLink to="/lost">
            <span className="nav-long">I lost something</span>
            <span className="nav-short">Lost</span>
          </NavLink>
          <NavLink to="/found">
            <span className="nav-long">I found something</span>
            <span className="nav-short">Found</span>
          </NavLink>
          <NavLink to="/desk">Desk</NavLink>
        </nav>
      </header>
      <main id="main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/lost" element={<ReportForm key="lost" kind="lost" />} />
          <Route path="/found" element={<ReportForm key="found" kind="found" />} />
          <Route path="/reports/:id" element={<ReportPage />} />
          <Route path="/claims/:id" element={<ClaimPage />} />
          <Route path="/desk" element={<Desk />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </>
  );
}
