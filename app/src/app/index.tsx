import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Atmosphere } from "../components/Atmosphere";
import { colors, fonts } from "../theme";

export default function HomeScreen() {
  const router = useRouter();
  const wide = useWindowDimensions().width >= 900;

  return (
    <Atmosphere>
      <SafeAreaView style={styles.safe}>
        <View style={styles.hero}>
          <Text style={styles.brand}>Sauti Yetu</Text>
          <Text style={styles.headline}>Hear every patient.</Text>
          <Text style={styles.support}>
            Record the consult. We detect the language, translate for you, and keep the clinical picture in view.
          </Text>
          <Pressable style={styles.cta} onPress={() => router.push(wide ? "/session/graph" : "/session")}>
            <Text style={styles.ctaText}>Start session</Text>
          </Pressable>
        </View>
        <Text style={styles.disclaimer}>
          Decision support only — not a medical device.
        </Text>
      </SafeAreaView>
    </Atmosphere>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, justifyContent: "space-between", paddingHorizontal: 28, paddingBottom: 24 },
  hero: { flex: 1, justifyContent: "center", gap: 18, maxWidth: 520 },
  brand: {
    fontFamily: fonts.display,
    fontSize: 56,
    lineHeight: 60,
    color: colors.paper,
    letterSpacing: -2,
  },
  headline: {
    fontFamily: fonts.displaySemi,
    fontSize: 28,
    color: colors.mist,
    letterSpacing: -0.4,
  },
  support: {
    fontFamily: fonts.body,
    fontSize: 17,
    lineHeight: 26,
    color: "rgba(247,244,238,0.78)",
    maxWidth: 420,
  },
  cta: {
    alignSelf: "flex-start",
    backgroundColor: colors.ember,
    paddingHorizontal: 22,
    paddingVertical: 14,
    marginTop: 8,
  },
  ctaText: { fontFamily: fonts.bodySemi, color: colors.paper, fontSize: 16 },
  disclaimer: { fontFamily: fonts.body, fontSize: 12, color: "rgba(247,244,238,0.45)" },
});
