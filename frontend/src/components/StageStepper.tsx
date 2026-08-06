import { useEffect, useState } from "react";

const STAGES = [
  "Uploading audio",
  "Sahara transcription",
  "Clinical extraction",
  "Triage reasoning",
  "Updating reasoning graph",
];

const ADVANCE_MS = 1400;

/** Client-side progress indicator shown while /api/triage is in flight.
 * Advances on a timer; the parent unmounts it when the response lands. */
export default function StageStepper() {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const timer = setInterval(
      () => setActive((i) => Math.min(i + 1, STAGES.length - 1)),
      ADVANCE_MS,
    );
    return () => clearInterval(timer);
  }, []);

  return (
    <ol className="mt-4 space-y-2 rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200">
      {STAGES.map((label, i) => {
        const done = i < active;
        const current = i === active;
        return (
          <li key={label} className="flex items-center gap-2.5 text-xs">
            <span
              className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                done
                  ? "bg-emerald-600 text-white"
                  : current
                    ? "bg-blue-600 text-white"
                    : "bg-slate-200 text-slate-500"
              }`}
            >
              {done ? "✓" : i + 1}
            </span>
            <span
              className={
                done
                  ? "text-emerald-700"
                  : current
                    ? "font-semibold text-blue-700"
                    : "text-slate-400"
              }
            >
              {label}
            </span>
            {current && (
              <span className="ml-auto h-3 w-3 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
            )}
          </li>
        );
      })}
    </ol>
  );
}
