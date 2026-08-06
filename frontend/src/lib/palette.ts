/** Clinical color semantics shared by the reasoning graph, its legend, and
 * the urgency badges. Node kinds mirror backend/graph.py. */

export type NodeKind =
  | "patient"
  | "symptom"
  | "finding"
  | "condition"
  | "red_flag"
  | "topic"
  | "department";

export const NODE_KIND_LABELS: Record<NodeKind, string> = {
  patient: "Patient",
  symptom: "Symptom",
  finding: "Finding",
  condition: "Possible condition",
  red_flag: "Red flag",
  topic: "Triage topic",
  department: "Department",
};

/** Strong colors: node borders, legend swatch rings, inspector headings. */
export const NODE_COLORS: Record<NodeKind, string> = {
  patient: "#1e293b",
  symptom: "#0e7490",
  finding: "#0f766e",
  condition: "#b45309",
  red_flag: "#b3271e",
  topic: "#1d4ed8",
  department: "#6d28d9",
};

/** Soft background tints for the pill-shaped nodes. */
export const NODE_TINTS: Record<NodeKind, string> = {
  patient: "#e2e8f0",
  symptom: "#ecfeff",
  finding: "#f0fdfa",
  condition: "#fffbeb",
  red_flag: "#fef2f2",
  topic: "#eff6ff",
  department: "#f5f3ff",
};

/** Label text colors, dark enough to read on the tints. */
export const NODE_TEXT_COLORS: Record<NodeKind, string> = {
  patient: "#0f172a",
  symptom: "#155e75",
  finding: "#115e59",
  condition: "#92400e",
  red_flag: "#991b1b",
  topic: "#1e40af",
  department: "#5b21b6",
};

/** Tailwind classes for the urgency chips (keys match backend/triage.py). */
export const URGENCY_STYLES: Record<string, { badge: string; dot: string }> = {
  EMERGENCY: { badge: "bg-red-600 text-white", dot: "bg-red-600" },
  URGENT: { badge: "bg-amber-500 text-white", dot: "bg-amber-500" },
  ROUTINE: { badge: "bg-emerald-600 text-white", dot: "bg-emerald-600" },
};
