import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import type { Provenance } from "../api/types";
import { colors, fonts } from "../theme";

function badgeTone(value: string): { bg: string; fg: string } {
  const v = value.toLowerCase();
  if (v === "guideline" || v === "clinician-reviewed") {
    return { bg: "#E8F5EE", fg: colors.leaf };
  }
  if (v === "chart-verified") return { bg: "#E8F2F8", fg: "#1D5F8A" };
  if (v === "expert") return { bg: "#E8EEF8", fg: "#2A4A8A" };
  return { bg: "#F8F0E0", fg: colors.amber };
}

export function ProvenanceBadges({ source }: { source: Provenance }) {
  return (
    <View style={styles.row}>
      <Text
        style={[
          styles.pill,
          {
            backgroundColor: badgeTone(source.evidence_level).bg,
            color: badgeTone(source.evidence_level).fg,
          },
        ]}
      >
        {source.evidence_level}
      </Text>
      <Text
        style={[
          styles.pill,
          {
            backgroundColor: badgeTone(source.review_status).bg,
            color: badgeTone(source.review_status).fg,
          },
        ]}
      >
        {source.review_status}
      </Text>
    </View>
  );
}

export function CitationDetails({ source }: { source: Provenance }) {
  return (
    <View style={styles.cite}>
      <Text style={styles.ref}>{source.ref}</Text>
      {source.mapped_scale ? (
        <Text style={styles.scale}>Scale: {source.mapped_scale}</Text>
      ) : null}
      {source.url ? (
        <Pressable onPress={() => Linking.openURL(source.url!)}>
          <Text style={styles.link}>View reference</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function SourceCitation({ source }: { source: Provenance }) {
  return (
    <View style={styles.block}>
      <ProvenanceBadges source={source} />
      <CitationDetails source={source} />
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  pill: {
    fontFamily: fonts.bodyMed,
    fontSize: 10,
    letterSpacing: 0.3,
    paddingHorizontal: 7,
    paddingVertical: 3,
    overflow: "hidden",
  },
  cite: { gap: 4 },
  ref: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, lineHeight: 17 },
  scale: { fontFamily: fonts.body, fontSize: 12, color: colors.muted },
  link: { fontFamily: fonts.bodySemi, fontSize: 12, color: colors.celadon },
  block: { gap: 8 },
});
