import { useEffect, useState } from "react";

// TODO(Day 7): temporary page for the dev route GET /api/_dev/holdings. Delete with the route.
// NUMERIC values arrive as strings and are shown as received.
type DevHolding = {
  name: string | null;
  principal: string | null;
  cost: string | null;
  fair_value: string | null;
  source_url: string;
};

export default function DevHoldings() {
  const [rows, setRows] = useState<DevHolding[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/_dev/holdings")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: DevHolding[]) => setRows(data))
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="p-4">Could not load holdings: {error}</p>;
  if (rows === null) return <p className="p-4">Loading</p>;

  return (
    <div className="p-4">
      <h1 className="mb-2 text-lg font-bold">Holdings (temporary dev view), {rows.length} rows</h1>
      <table className="text-sm">
        <thead>
          <tr>
            <th className="text-left pr-4">Name</th>
            <th className="text-right pr-4">Principal</th>
            <th className="text-right pr-4">Cost</th>
            <th className="text-right pr-4">Fair value</th>
            <th className="text-left">Source</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td className="pr-4">{r.name}</td>
              <td className="text-right pr-4">{r.principal ?? ""}</td>
              <td className="text-right pr-4">{r.cost ?? ""}</td>
              <td className="text-right pr-4">{r.fair_value ?? ""}</td>
              <td>
                <a className="underline" href={r.source_url} target="_blank" rel="noreferrer">
                  filing
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
