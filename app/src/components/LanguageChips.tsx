import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { colors, fonts } from "../theme";

export function LanguageChips({
  title,
  options,
  value,
  onChange,
  preferred,
}: {
  title: string;
  options: Record<string, string>;
  value: string;
  onChange: (code: string) => void;
  preferred?: string[];
}) {
  const codes = Object.keys(options);
  const ordered = [
    ...(preferred ?? []).filter((c) => codes.includes(c)),
    ...codes.filter((c) => !(preferred ?? []).includes(c)),
  ];

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>{title}</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.row}>
        {ordered.map((code) => {
          const active = code === value;
          return (
            <Pressable
              key={code}
              onPress={() => onChange(code)}
              style={[styles.chip, active && styles.chipOn]}
            >
              <Text style={[styles.chipText, active && styles.chipTextOn]}>
                {options[code]}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8 },
  title: {
    fontFamily: fonts.bodyMed,
    fontSize: 12,
    letterSpacing: 0.8,
    textTransform: "uppercase",
    color: colors.muted,
  },
  row: { gap: 8, paddingRight: 16 },
  chip: {
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.45)",
  },
  chipOn: {
    backgroundColor: colors.ink,
    borderColor: colors.ink,
  },
  chipText: { fontFamily: fonts.bodyMed, fontSize: 13, color: colors.ink },
  chipTextOn: { color: colors.paper },
});
