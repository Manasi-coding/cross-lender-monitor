import { useCallback, useEffect, useRef, useState } from "react";
import type { LabelHolding, LabelNext, LabelRequest, LabelResponse, LabelValue } from "./types";

// Dev only labeling page (frontend.md 4.9). It is not linked from any menu.
// It shows raw attributes and independent evidence only. E11 never sends a score, status, band or phase.

const KEEP = 5;
const NAME_KEY = "labeledBy";

type Done = { sample: LabelNext; label: LabelValue };
type Load =
  | { kind: "loading" }
  | { kind: "off" }
  | { kind: "empty" }
  | { kind: "error"; message: string }
  | { kind: "ready"; sample: LabelNext };

function readName(): string {
  try {
    return window.localStorage.getItem(NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveName(v: string) {
  try {
    window.localStorage.setItem(NAME_KEY, v);
  } catch {
    // storage can be blocked; the field still works for this visit
  }
}

function show(v: string | null): string {
  return v === null || v === "" ? "Not yet measured" : v;
}

function Card({ title, h }: { title: string; h: LabelHolding }) {
  return (
    <div className="flex-1 min-w-64 border border-gray-400 p-3">
      <h2 className="font-bold mb-2">{title}</h2>
      <p className="text-lg mb-2 break-words">{show(h.rawName)}</p>
      <p>Instrument: {h.instrumentType}</p>
      <p>Maturity: {show(h.maturityDate)}</p>
      <p>Spread: {h.spreadBps === null ? "Not yet measured" : `${h.spreadBps} bps`}</p>
      <p>Industry: {show(h.industry)}</p>
      <p className="mt-2 font-semibold">Footnotes</p>
      <p className="whitespace-pre-wrap break-words">{show(h.footnotes)}</p>
      <p className="mt-2 font-semibold">Names of this borrower in other filings</p>
      {h.crossFilingNames.length === 0 ? (
        <p>None found. This is not evidence either way.</p>
      ) : (
        <ul className="list-disc ml-5">
          {h.crossFilingNames.map((n) => (
            <li key={n} className="break-words">
              {n}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Label() {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [labeledBy, setLabeledBy] = useState<string>(readName);
  const [history, setHistory] = useState<Done[]>([]);
  const [viewing, setViewing] = useState<number | null>(null); // index into history; null means the live sample
  const [note, setNote] = useState<string | null>(null);
  const busy = useRef(false);

  const loadNext = useCallback(async () => {
    try {
      const res = await fetch("/api/label/next");
      if (res.status === 404) return setLoad({ kind: "off" });
      if (res.status === 204) return setLoad({ kind: "empty" });
      if (!res.ok) return setLoad({ kind: "error", message: `HTTP ${res.status}` });
      setLoad({ kind: "ready", sample: (await res.json()) as LabelNext });
    } catch (e) {
      setLoad({ kind: "error", message: (e as Error).message });
    }
  }, []);

  useEffect(() => {
    void loadNext();
  }, [loadNext]);

  const shown: LabelNext | null =
    viewing !== null ? (history[viewing]?.sample ?? null) : load.kind === "ready" ? load.sample : null;

  const submit = useCallback(
    async (label: LabelValue) => {
      if (busy.current || !shown) return;
      const name = labeledBy.trim();
      if (!name) {
        setNote("Type your name in the Labeled by field first.");
        return;
      }
      busy.current = true;
      try {
        const body: LabelRequest = { sampleId: shown.sampleId, label, labeledBy: name };
        const res = await fetch("/api/label", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (res.status === 404) {
          const err = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
          // the route is not mounted ("No such route.") or the sample id is unknown ("No such sample.")
          if (err?.error?.message === "No such sample.") setNote("That sample was not found.");
          else setLoad({ kind: "off" });
          return;
        }
        if (!res.ok) {
          setNote(`The label was not saved (HTTP ${res.status}).`);
          return;
        }
        (await res.json()) as LabelResponse;
        setNote(null);
        if (viewing !== null) {
          // a correction: keep the new label and return to the live sample, which is still unlabeled
          setHistory((h) => h.map((d, i) => (i === viewing ? { ...d, label } : d)));
          setViewing(null);
        } else {
          setHistory((h) => [...h, { sample: shown, label }].slice(-KEEP));
          await loadNext();
        }
      } catch (e) {
        setNote(`The label was not saved: ${(e as Error).message}`);
      } finally {
        busy.current = false;
      }
    },
    [shown, labeledBy, viewing, loadNext],
  );

  const back = useCallback(() => {
    if (history.length === 0) return;
    setViewing((v) => (v === null ? history.length - 1 : Math.max(0, v - 1)));
  }, [history.length]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "m") void submit("MATCH");
      else if (k === "n") void submit("NO_MATCH");
      else if (k === "u") void submit("UNSURE");
      else if (k === "b") back();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [submit, back]);

  return (
    <div className="p-4 max-w-5xl">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
        <h1 className="text-lg font-bold">Label pair</h1>
        {load.kind === "ready" && (
          <p>
            Progress {load.sample.progress.labeled} / {load.sample.progress.total}
          </p>
        )}
      </div>
      <label className="block mb-3">
        Labeled by{" "}
        <input
          className="border border-gray-400 px-1"
          value={labeledBy}
          onChange={(e) => {
            setLabeledBy(e.target.value);
            saveName(e.target.value);
          }}
        />
      </label>

      {load.kind === "loading" && <p>Loading</p>}
      {load.kind === "off" && <p>Labeling is turned off on this server.</p>}
      {load.kind === "empty" && viewing === null && <p>Every drawn sample is labeled.</p>}
      {load.kind === "error" && <p>Could not load the next sample: {load.message}</p>}

      {shown && (
        <>
          {viewing !== null && (
            <p className="mb-2 font-semibold">
              Correcting sample {shown.sampleId}, currently labeled {history[viewing].label}. Press M, N or U to send
              the new label.
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            <Card title="Holding A" h={shown.holdingA} />
            <Card title="Holding B" h={shown.holdingB} />
          </div>
        </>
      )}

      {load.kind !== "off" && (shown || history.length > 0) && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button className="border border-gray-500 px-3 py-1" disabled={!shown} onClick={() => void submit("MATCH")}>
            M Match
          </button>
          <button className="border border-gray-500 px-3 py-1" disabled={!shown} onClick={() => void submit("NO_MATCH")}>
            N No match
          </button>
          <button className="border border-gray-500 px-3 py-1" disabled={!shown} onClick={() => void submit("UNSURE")}>
            U Unsure
          </button>
          <button className="border border-gray-500 px-3 py-1" disabled={history.length === 0} onClick={back}>
            B Back
          </button>
        </div>
      )}
      {note && <p className="mt-2 font-semibold">{note}</p>}

      <div className="mt-4">
        <p>
          A MATCH needs at least one independent signal: the industry, a footnote, a name in another filing, or a
          credit agreement. Otherwise choose Unsure.
        </p>
        <p>Principal size is not evidence.</p>
        <p>
          The other filing names list matches exact normalized names only, so it can miss a spelling variant. An empty
          list is not evidence.
        </p>
      </div>
    </div>
  );
}
