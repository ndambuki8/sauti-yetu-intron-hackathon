import { ScrollView, StyleSheet, Text } from "react-native";
import { ReasoningView } from "../../components/ReasoningView";
import { colors, fonts } from "../../theme";

export default function GraphScreen() {
  return (
    <ScrollView contentContainerStyle={styles.page} horizontal={false}>
      <Text style={styles.title}>Clinical picture</Text>
      <Text style={styles.sub}>
        Summary, ranked conditions, cited evidence, and the map of how this consult connects.
      </Text>
      <ReasoningView />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: 20, gap: 10, paddingBottom: 40 },
  title: { fontFamily: fonts.displaySemi, fontSize: 28, color: colors.ink },
  sub: { fontFamily: fonts.body, fontSize: 15, color: colors.muted, lineHeight: 22, maxWidth: 520 },
});
