export const colors = {
  ink: "#10241F",
  moss: "#1B3D34",
  cedar: "#2C5348",
  celadon: "#3D7A6A",
  mist: "#D7E4DE",
  linen: "#F4F0E8",
  paper: "#FBF8F2",
  ember: "#C96A2B",
  emberDeep: "#9A4C1A",
  blood: "#B3271E",
  amber: "#C9841A",
  leaf: "#2F7D56",
  muted: "#5C6F68",
  line: "rgba(16,36,31,0.12)",
};

export const fonts = {
  display: "Syne_800ExtraBold",
  displaySemi: "Syne_700Bold",
  body: "IBMPlexSans_400Regular",
  bodyMed: "IBMPlexSans_500Medium",
  bodySemi: "IBMPlexSans_600SemiBold",
};

export const urgencyColor: Record<string, string> = {
  EMERGENCY: colors.blood,
  URGENT: colors.amber,
  ROUTINE: colors.leaf,
};
