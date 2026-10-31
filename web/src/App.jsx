import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";
import { getJson } from "./api.js";

const Ctx = createContext({ overview: null, refresh: () => {} });
export const useShared = () => useContext(Ctx);

const NAV = [
  ["/", "Overview"],
  ["/borrowers", "Borrowers"],
  ["/facilities", "Triage"],
  ["/review", "Review"],
  ["/metrics", "Metrics"],
  ["/filings", "Filings"],
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
    <Ctx.Provider value={{ overview, refresh }}>
      <div className="flex min-h-screen flex-col md:flex-row">
        <nav className="border-b p-4 md:w-52 md:border-b-0 md:border-r" aria-label="Main">
          <p className="mb-4 font-bold leading-tight">VALUATION<br />MONITOR</p>
          <ul className="flex flex-wrap gap-2 md:block md:space-y-1">
            {NAV.map(([to, label]) => (
              <li key={to}>
                <NavLink to={to} end={to === "/"} className={({ isActive }) => `block rounded px-2 py-1 ${isActive ? "bg-gray-800 text-white dark:bg-gray-200 dark:text-black" : ""}`}>
                  {label}
                  {label === "Review" && overview && ` (${overview.pendingReviewCount})`}
                </NavLink>
              </li>
            ))}
          </ul>
          {overview && (
            <p className="mt-6 hidden text-sm md:block">
              {overview.bdcCount} BDCs<br />
              {overview.quarterCount} {overview.quarterCount === 1 ? "Quarter" : "Quarters"}
            </p>
          )}
        </nav>
        <div className="flex-1 p-4">
          <header className="mb-4 flex items-center gap-2">
            <form onSubmit={search} className="flex-1" role="search">
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search borrowers" aria-label="Search borrowers" maxLength={200} className="w-full max-w-md rounded border px-3 py-1" />
            </form>
            <button className="rounded border px-3 py-1" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle theme">
              {theme === "dark" ? "Light" : "Dark"}
            </button>
          </header>
          {failed && <p role="alert" className="mb-4 rounded border border-red-600 p-2">The overview could not be loaded, so counts and period tags are hidden.</p>}
          <main><Outlet /></main>
        </div>
      </div>
    </Ctx.Provider>
  );
}
