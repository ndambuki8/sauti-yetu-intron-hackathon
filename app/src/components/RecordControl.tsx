import { useEffect, useRef } from "react";
import { Animated, Pressable, StyleSheet, Text, View } from "react-native";
import { colors, fonts } from "../theme";

export function RecordControl({
  recording,
  disabled,
  onPress,
  label,
}: {
  recording: boolean;
  disabled?: boolean;
  onPress: () => void;
  label: string;
}) {
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!recording) {
      pulse.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 900, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 900, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [recording, pulse]);

  const scale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.18] });
  const opacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.35, 0] });

  return (
    <View style={styles.wrap}>
      <View style={styles.stage}>
        <Animated.View style={[styles.ring, { transform: [{ scale }], opacity }]} />
        <Pressable
          onPress={onPress}
          disabled={disabled}
          style={[styles.button, recording && styles.buttonHot, disabled && styles.buttonOff]}
        >
          <View style={[styles.core, recording && styles.coreHot]} />
        </Pressable>
      </View>
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", gap: 16 },
  stage: { width: 168, height: 168, alignItems: "center", justifyContent: "center" },
  ring: {
    position: "absolute",
    width: 168,
    height: 168,
    borderRadius: 84,
    backgroundColor: colors.ember,
  },
  button: {
    width: 128,
    height: 128,
    borderRadius: 64,
    backgroundColor: colors.ember,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: colors.emberDeep,
    shadowOpacity: 0.35,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 8 },
  },
  buttonHot: { backgroundColor: colors.blood },
  buttonOff: { opacity: 0.4 },
  core: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.paper,
  },
  coreHot: { width: 34, height: 34, borderRadius: 6 },
  label: {
    fontFamily: fonts.bodyMed,
    fontSize: 15,
    color: colors.ink,
    letterSpacing: 0.3,
  },
});
