import { Tabs, useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View, useWindowDimensions } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { RecordSession } from "../../components/RecordSession";
import { deleteSession } from "../../api/client";
import { useConsultation } from "../../state/consultation";
import { colors, fonts } from "../../theme";

export default function SessionLayout() {
  const wide = useWindowDimensions().width >= 900;
  const router = useRouter();
  const { state, dispatch } = useConsultation();

  const end = () => {
    if (state.sessionId) deleteSession(state.sessionId);
    dispatch({ type: "reset" });
    router.replace("/");
  };

  return (
    <View style={styles.root}>
      <SafeAreaView edges={["top"]} style={styles.headerSafe}>
        <View style={styles.header}>
          <Pressable onPress={end}>
            <Text style={styles.brand}>Sauti Yetu</Text>
          </Pressable>
          <Text style={styles.chip}>
            {state.sessionId ? `Session ${state.sessionId.slice(0, 6)}` : "New session"}
          </Text>
          <Pressable onPress={end}>
            <Text style={styles.end}>End</Text>
          </Pressable>
        </View>
      </SafeAreaView>
      <View style={[styles.body, wide && styles.bodyWide]}>
        {wide ? (
          <View style={styles.rail}>
            <RecordSession compact />
          </View>
        ) : null}
        <View style={styles.main}>
          <Tabs
            initialRouteName={wide ? "graph" : "index"}
            screenOptions={{
              headerShown: false,
              tabBarActiveTintColor: colors.ember,
              tabBarInactiveTintColor: colors.muted,
              tabBarLabelStyle: { fontFamily: fonts.bodyMed, fontSize: 12 },
              tabBarStyle: {
                backgroundColor: colors.paper,
                borderTopColor: colors.line,
              },
            }}
          >
            <Tabs.Screen
              name="index"
              options={{
                title: "Record",
                href: wide ? null : "/session",
              }}
            />
            <Tabs.Screen name="graph" options={{ title: "Picture" }} />
            <Tabs.Screen name="artifacts" options={{ title: "Notes" }} />
          </Tabs>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.linen },
  headerSafe: { backgroundColor: colors.ink },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  brand: { fontFamily: fonts.display, fontSize: 20, color: colors.paper, letterSpacing: -0.4 },
  chip: { fontFamily: fonts.body, fontSize: 12, color: colors.mist },
  end: { fontFamily: fonts.bodySemi, fontSize: 14, color: colors.ember },
  body: { flex: 1 },
  bodyWide: { flexDirection: "row" },
  rail: {
    width: 400,
    borderRightWidth: 1,
    borderRightColor: colors.line,
    backgroundColor: colors.linen,
  },
  main: { flex: 1, backgroundColor: colors.linen },
});
