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

export const NODE_COLORS: Record<NodeKind, string> = {
  patient: "#10241F",
  symptom: "#2C6B7A",
  finding: "#2F7D56",
  condition: "#C9841A",
  red_flag: "#B3271E",
  topic: "#1B4F72",
  department: "#3D7A6A",
};

export const NODE_TINTS: Record<NodeKind, string> = {
  patient: "#E2E8E4",
  symptom: "#E8F4F6",
  finding: "#E8F6EF",
  condition: "#FBF3E0",
  red_flag: "#FBECEA",
  topic: "#E8F0F7",
  department: "#E6F2EE",
};
