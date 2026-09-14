import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { DifferentialItem } from "../api/types";
import { latestTurn, useConsultation } from "../state/consultation";
import { colors, fonts } from "../theme";
import { CitationDetails, ProvenanceBadges } from "./ProvenanceBadge";

function pct(p: number): number {
  return Math.round(p * 100);
}

function barColor(p: number): string {
  if (p >= 0.66) return colors.blood;
  if (p >= 0.33) return colors.amber;
  return colors.celadon;
}

function Row({ item, rank }: { item: DifferentialItem; rank: number }) {
  const [open, setOpen] = useState(false);
  return (
    <Pressable onPress={() => setOpen((v) => !v)} style={styles.card}>
      <View style={styles.head}>
        <Text style={styles.rank}>{rank}</Text>
        <Text style={styles.label}>{item.label}</Text>
        <Text style={styles.pct}>{pct(item.probability)}%</Text>
      </View>
      <View style={styles.track}>
        <View
          style={[
            styles.fill,
            {
              width: `${Math.max(3, pct(item.probability))}%`,
              backgroundColor: barColor(item.probability),
            },
          ]}
        />
      </View>
      {open ? (
        <View style={styles.detail}>
          <Text style={styles.muted}>
            Raised from a baseline of {pct(item.prior)}% by:
          </Text>
          <View style={styles.chips}>
            {item.contributing.map((c) => (
              <Text key={c.finding} style={styles.chip}>
                {c.finding} ×{c.lr}
              </Text>
            ))}
          </View>
          {item.department ? (
            <Text style={styles.muted}>Typical route: {item.department}</Text>
          ) : null}
          <ProvenanceBadges source={item.source} />
          <CitationDetails source={item.source} />
        </View>
      ) : null}
    </Pressable>
  );
}

export function DifferentialPanel() {
  const { state } = useConsultation();
  const turn = latestTurn(state);
  const differential = turn?.triage.differential ?? [];

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>Probabilistic differential</Text>
      <Text style={styles.lede}>
        Ranked likelihood from the symptoms heard. A ranking aid, not a diagnosis.
      </Text>
      {differential.length === 0 ? (
        <Text style={styles.empty}>No conditions matched the findings in this recording yet.</Text>
      ) : (
        differential.map((item, i) => <Row key={item.id} item={item} rank={i + 1} />)
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 10 },
  title: { fontFamily: fonts.bodySemi, fontSize: 16, color: colors.ink },
  lede: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, lineHeight: 19 },
  empty: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, paddingVertical: 16 },
  card: {
    backgroundColor: colors.paper,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 12,
    gap: 8,
  },
  head: { flexDirection: "row", alignItems: "center", gap: 8 },
  rank: {
    width: 22,
    height: 22,
    textAlign: "center",
    fontFamily: fonts.bodySemi,
    fontSize: 11,
    color: colors.muted,
    backgroundColor: colors.mist,
    overflow: "hidden",
    lineHeight: 22,
  },
  label: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 14, color: colors.ink },
  pct: { fontFamily: fonts.bodySemi, fontSize: 14, color: colors.ink },
  track: { height: 6, backgroundColor: colors.mist, overflow: "hidden" },
  fill: { height: 6 },
  detail: { gap: 8, paddingTop: 4, borderTopWidth: 1, borderTopColor: colors.line },
  muted: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, lineHeight: 17 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: {
    fontFamily: fonts.bodyMed,
    fontSize: 11,
    color: colors.cedar,
    backgroundColor: colors.mist,
    paddingHorizontal: 7,
    paddingVertical: 3,
    overflow: "hidden",
  },
});
