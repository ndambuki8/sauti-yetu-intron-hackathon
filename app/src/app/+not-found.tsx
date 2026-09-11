import { Link, Stack } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import { colors, fonts } from "../theme";

export default function NotFound() {
  return (
    <View style={styles.wrap}>
      <Stack.Screen options={{ headerShown: false }} />
      <Text style={styles.brand}>Sauti Yetu</Text>
      <Text style={styles.body}>This screen is not part of the consult.</Text>
      <Link href="/" style={styles.link}>
        Back to the start
      </Link>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    backgroundColor: colors.ink,
    justifyContent: "center",
    padding: 28,
    gap: 12,
  },
  brand: { fontFamily: fonts.display, fontSize: 48, color: colors.paper },
  body: { fontFamily: fonts.body, fontSize: 16, color: colors.mist },
  link: { fontFamily: fonts.bodySemi, fontSize: 16, color: colors.ember, marginTop: 8 },
});
