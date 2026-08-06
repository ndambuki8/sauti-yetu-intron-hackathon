import { URGENCY_STYLES } from "../lib/palette";

export default function UrgencyBadge({ urgency }: { urgency: string }) {
  const style = URGENCY_STYLES[urgency] ?? {
    badge: "bg-slate-500 text-white",
    dot: "bg-slate-500",
  };
  return (
    <span className={`chip ${style.badge}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-white/80" />
      {urgency}
    </span>
  );
}
