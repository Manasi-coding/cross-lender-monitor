import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { getJson } from "./api.js";
import { Icon } from "./components.jsx";

const Ctx = createContext({ overview: null, refresh: () => {}, failed: false });
export const useShared = () => useContext(Ctx);

const NAV = [
  ["/", "Overview", "grid"],
  ["/borrowers", "Borrowers", "layers"],
  ["/facilities", "Triage", "chart"],
  ["/review", "Review", "search"],
  ["/decisions", "Decisions", "flag"],
  ["/metrics", "Metrics", "check"],
  ["/filings", "Filings", "doc"],
];

function readTheme() {
  try {
    return window.localStorage.getItem("theme") ?? "light";
  } catch {
    return "light";
  }
}

export default function App() {
  const [overview, setOverview] = useState(null);
  const [failed, setFailed] = useState(false);
  const [theme, setTheme] = useState(readTheme);
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const location = useLocation();

  const refresh = useCallback(() => {
    getJson("/api/overview").then(
      (o) => {
        setOverview(o);
        setFailed(false);
      },
      () => setFailed(true),
    );
  }, []);
  useEffect(refresh, [refresh]);

  // Refetch the shared overview (the Review badge) when the tab regains focus, so it
  // never shows a stale pendingReviewCount after a decision was made elsewhere. No polling or
  // simulated updates: this only runs on a real focus event.
  useEffect(() => {
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [refresh]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem("theme", theme);
    } catch {
      // storage can be blocked; the toggle still works for this visit
    }
  }, [theme]);

  const search = (e) => {
    e.preventDefault();
    navigate(q.trim() ? `/borrowers?search=${encodeURIComponent(q.trim())}` : "/borrowers");
  };

  return (
    <Ctx.Provider value={{ overview, refresh, failed }}>
      <div className="flex min-h-screen flex-col md:flex-row" style={{ background: "var(--color-bg)" }}>
        <nav
          className="flex flex-col p-5 md:w-60 md:shrink-0"
          style={{ background: "var(--color-sidebar-bg)" }}
          aria-label="Main"
        >
          <div className="mb-6 flex items-center gap-2.5">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl" style={{ background: "var(--color-brand)", color: "var(--color-sidebar-active-text)" }}>
              <Icon name="layers" size={18} />
            </span>
            <p className="text-sm font-bold uppercase tracking-wide leading-tight text-white">
              Valuation<br />Monitor
            </p>
          </div>
          <ul className="flex flex-wrap gap-1.5 md:block md:space-y-1">
            {NAV.map(([to, label, icon]) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={to === "/"}
                  className={({ isActive }) =>
                    `sidebar-link flex items-center justify-between gap-2 rounded-xl px-3 py-2 text-sm font-medium transition-colors ${isActive ? "" : "sidebar-link-inactive"}`
                  }
                  style={({ isActive }) => ({
                    color: isActive ? "var(--color-sidebar-active-text)" : "var(--color-sidebar-text)",
                    background: isActive ? "var(--color-sidebar-active-bg)" : "transparent",
                  })}
                >
                  <span className="flex items-center gap-2.5">
                    <Icon name={icon} size={17} />
                    {label}
                  </span>
                  {label === "Review" && overview && overview.pendingReviewCount > 0 && (
                    <span
                      className="rounded-full px-1.5 py-0.5 text-xs font-semibold"
                      style={{ background: "var(--color-brand)", color: "var(--color-sidebar-active-text)" }}
                    >
                      {overview.pendingReviewCount}
                    </span>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="min-w-0 flex-1 p-6 md:p-8">
          <header className="mb-6 flex items-center gap-3">
            <form onSubmit={search} className="flex-1" role="search">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search borrowers, facilities or lenders"
                aria-label="Search borrowers, facilities or lenders"
                maxLength={200}
                className="w-full max-w-md rounded-xl border px-3.5 py-2 text-sm outline-none transition-colors placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-brand)]"
                style={{ background: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text)" }}
              />
            </form>
            <button className="btn-secondary" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle theme">
              {theme === "dark" ? "Light" : "Dark"}
            </button>
          </header>
          {failed && (
            <div role="alert" className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-3 text-sm" style={{ borderColor: "var(--color-flagged)", background: "var(--color-flagged-light)", color: "var(--color-flagged)" }}>
              <span>The overview could not be loaded, so counts and period tags are hidden.</span>
              <button className="btn-secondary" onClick={refresh}>Retry</button>
            </div>
          )}
          <main key={location.pathname} className="animate-page-in">
            <Outlet />
          </main>
        </div>
      </div>
    </Ctx.Provider>
  );
}
