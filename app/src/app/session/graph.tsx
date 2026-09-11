import { ScrollView, StyleSheet, Text } from "react-native";
import { ReasoningGraph } from "../../components/ReasoningGraph";
import { useConsultation } from "../../state/consultation";
import { colors, fonts } from "../../theme";

export default function GraphScreen() {
  const { state } = useConsultation();
  return (
    <ScrollView contentContainerStyle={styles.page} horizontal={false}>
      <Text style={styles.title}>Clinical picture</Text>
      <Text style={styles.sub}>
        How this consult connects — symptoms, topics, probable conditions, and where to send the patient.
      </Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <ReasoningGraph graph={state.graph} />
      </ScrollView>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: 20, gap: 10, paddingBottom: 40 },
  title: { fontFamily: fonts.displaySemi, fontSize: 28, color: colors.ink },
  sub: { fontFamily: fonts.body, fontSize: 15, color: colors.muted, lineHeight: 22, maxWidth: 520 },
});
