import { StyleSheet, Text, View } from "react-native";
import type { Turn } from "../api/types";
import { colors, fonts, urgencyColor } from "../theme";

export function ClinicalCard({ turn }: { turn: Turn }) {
  const urgency = turn.triage.urgency;
  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <Text style={[styles.badge, { backgroundColor: urgencyColor[urgency] ?? colors.muted }]}>
          {urgency}
        </Text>
        <Text style={styles.meta}>
          {turn.triage.topic} · {turn.triage.suggested_department}
        </Text>
      </View>
      <Text style={styles.kicker}>Heard as</Text>
      <Text style={styles.transcript}>{turn.transcriptDoctor}</Text>
      {turn.transcript !== turn.transcriptDoctor ? (
        <Text style={styles.original}>Patient: {turn.transcript}</Text>
      ) : null}
      {turn.summary ? <Text style={styles.summary}>{turn.summary}</Text> : null}
      {turn.redFlags.length ? (
        <Text style={styles.flag}>Red flags: {turn.redFlags.join(", ")}</Text>
      ) : null}
      {turn.triage.clarifying_questions.length ? (
        <View style={styles.qs}>
          {turn.triage.clarifying_questions.slice(0, 3).map((q) => (
            <Text key={q} style={styles.q}>
              {q}
            </Text>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.paper,
    padding: 18,
    gap: 8,
    borderWidth: 1,
    borderColor: colors.line,
  },
  row: { flexDirection: "row", alignItems: "center", gap: 10, flexWrap: "wrap" },
  badge: {
    color: colors.paper,
    fontFamily: fonts.bodySemi,
    fontSize: 11,
    letterSpacing: 0.8,
    paddingHorizontal: 8,
    paddingVertical: 4,
    overflow: "hidden",
  },
  meta: { fontFamily: fonts.bodyMed, fontSize: 13, color: colors.muted, flex: 1 },
  kicker: {
    fontFamily: fonts.bodyMed,
    fontSize: 11,
    letterSpacing: 1,
    textTransform: "uppercase",
    color: colors.celadon,
    marginTop: 6,
  },
  transcript: { fontFamily: fonts.body, fontSize: 17, lineHeight: 24, color: colors.ink },
  original: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, fontStyle: "italic" },
  summary: { fontFamily: fonts.body, fontSize: 14, color: colors.cedar, lineHeight: 20 },
  flag: { fontFamily: fonts.bodySemi, fontSize: 13, color: colors.blood },
  qs: { gap: 4, marginTop: 4 },
  q: { fontFamily: fonts.body, fontSize: 13, color: colors.moss },
});
