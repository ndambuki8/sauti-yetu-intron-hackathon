import type { ReactNode } from "react";

/**
 * Lightweight CSS-only tooltip. Replaces prototype-style helper paragraphs
 * with on-demand hints, keeping the surface clean. Accessible via title
 * fallback and keyboard focus.
 */
export default function Tooltip({
  label,
  children,
  side = "top",
  className = "",
}: {
  label: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom";
  className?: string;
}) {
  const pos =
    side === "top"
      ? "bottom-full mb-2 left-1/2 -translate-x-1/2"
      : "top-full mt-2 left-1/2 -translate-x-1/2";
  return (
    <span className={`group/tt relative inline-flex ${className}`} tabIndex={0}>
      {children}
      <span
        role="tooltip"
        className={`pointer-events-none absolute z-50 ${pos} w-max max-w-[240px] whitespace-normal rounded-lg bg-slate-900 px-2.5 py-1.5 text-left text-[11px] font-medium leading-snug text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover/tt:opacity-100 group-focus/tt:opacity-100`}
      >
        {label}
      </span>
    </span>
  );
}

export function InfoIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className={className} aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm.75-11.25a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0ZM9.25 9a.75.75 0 0 1 1.5 0v4a.75.75 0 0 1-1.5 0V9Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

export function ShieldIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className={className} aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M9.66 2.24a1 1 0 0 1 .68 0l6 2.14a1 1 0 0 1 .66.94V10c0 3.86-2.5 6.79-6.66 8.2a1 1 0 0 1-.68 0C5.5 16.79 3 13.86 3 10V5.32a1 1 0 0 1 .66-.94l6-2.14Zm3.09 5.5a.75.75 0 0 0-1.18-.92l-2.4 3.06-1.02-1.02a.75.75 0 1 0-1.06 1.06l1.62 1.62a.75.75 0 0 0 1.12-.07l2.9-3.73Z"
        clipRule="evenodd"
      />
    </svg>
  );
}
