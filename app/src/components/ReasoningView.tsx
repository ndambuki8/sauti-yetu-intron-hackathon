import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from "react-native";
import { latestTurn, useConsultation } from "../state/consultation";
import { colors, fonts } from "../theme";
import { ClinicalCard } from "./ClinicalCard";
import { DifferentialPanel } from "./DifferentialPanel";
import { ReasoningGraph } from "./ReasoningGraph";
import { ReasoningTrace } from "./ReasoningTrace";

const SEGMENTS = ["Summary", "Differential", "Evidence", "Map"] as const;
type Segment = (typeof SEGMENTS)[number];

export function ReasoningView() {
  const { state } = useConsultation();
  const turn = latestTurn(state);
  const { width } = useWindowDimensions();
  const wide = width >= 900;
  const [segment, setSegment] = useState<Segment>(turn ? "Summary" : "Map");

  const panel =
    segment === "Summary" ? (
      turn ? <ClinicalCard turn={turn} /> : <Empty label="Summary appears after the first recording." />
    ) : segment === "Differential" ? (
      <DifferentialPanel />
    ) : segment === "Evidence" ? (
      <ReasoningTrace />
    ) : (
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <ReasoningGraph graph={state.graph} />
      </ScrollView>
    );

  return (
    <View style={styles.wrap}>
      <View style={styles.tabs}>
        {SEGMENTS.map((id) => (
          <Pressable
            key={id}
            onPress={() => setSegment(id)}
            style={[styles.tab, segment === id && styles.tabOn]}
          >
            <Text style={[styles.tabText, segment === id && styles.tabTextOn]}>{id}</Text>
          </Pressable>
        ))}
      </View>
      {wide && segment !== "Map" ? (
        <View style={styles.split}>
          <ScrollView horizontal style={styles.mapPane} showsHorizontalScrollIndicator={false}>
            <ReasoningGraph graph={state.graph} />
          </ScrollView>
          <View style={styles.side}>{panel}</View>
        </View>
      ) : (
        panel
      )}
    </View>
  );
}

function Empty({ label }: { label: string }) {
  return <Text style={styles.empty}>{label}</Text>;
}

const styles = StyleSheet.create({
  wrap: { gap: 14 },
  tabs: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  tab: {
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  tabOn: { backgroundColor: colors.ink, borderColor: colors.ink },
  tabText: { fontFamily: fonts.bodyMed, fontSize: 12, color: colors.ink },
  tabTextOn: { color: colors.paper },
  split: { flexDirection: "row", gap: 16, alignItems: "flex-start" },
  mapPane: { flex: 1 },
  side: { width: 340, maxWidth: "42%" },
  empty: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, paddingVertical: 16 },
});
