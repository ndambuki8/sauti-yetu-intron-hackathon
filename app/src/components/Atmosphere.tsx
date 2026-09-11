import { type ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import Svg, { Circle, Defs, RadialGradient, Rect, Stop } from "react-native-svg";
import { colors } from "../theme";

export function Atmosphere({ children }: { children: ReactNode }) {
  return (
    <View style={styles.root}>
      <Svg style={StyleSheet.absoluteFill} preserveAspectRatio="none">
        <Defs>
          <RadialGradient id="glowA" cx="18%" cy="8%" r="55%">
            <Stop offset="0%" stopColor="#3D7A6A" stopOpacity="0.55" />
            <Stop offset="100%" stopColor="#10241F" stopOpacity="0" />
          </RadialGradient>
          <RadialGradient id="glowB" cx="88%" cy="78%" r="50%">
            <Stop offset="0%" stopColor="#C96A2B" stopOpacity="0.22" />
            <Stop offset="100%" stopColor="#10241F" stopOpacity="0" />
          </RadialGradient>
        </Defs>
        <Rect x="0" y="0" width="100%" height="100%" fill={colors.ink} />
        <Rect x="0" y="0" width="100%" height="100%" fill="url(#glowA)" />
        <Rect x="0" y="0" width="100%" height="100%" fill="url(#glowB)" />
        <Circle cx="12%" cy="86%" r="90" fill="#1B3D34" opacity="0.45" />
      </Svg>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.ink },
});
