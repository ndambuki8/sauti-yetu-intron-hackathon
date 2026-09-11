import { useMemo, useState, type CSSProperties } from "react";
import {
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { colors, fonts } from "../theme";

export function LanguageSelect({
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
  const [open, setOpen] = useState(false);
  const ordered = useMemo(() => {
    const codes = Object.keys(options);
    return [
      ...(preferred ?? []).filter((c) => codes.includes(c)),
      ...codes.filter((c) => !(preferred ?? []).includes(c)),
    ];
  }, [options, preferred]);

  if (Platform.OS === "web") {
    return (
      <View style={styles.wrap}>
        <Text style={styles.title}>{title}</Text>
        <View style={styles.selectShell}>
          <select
            value={value}
            onChange={(e) => onChange(e.target.value)}
            style={webSelectStyle}
          >
            {ordered.map((code) => (
              <option key={code} value={code}>
                {options[code]}
              </option>
            ))}
          </select>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>{title}</Text>
      <Pressable style={styles.field} onPress={() => setOpen(true)}>
        <Text style={styles.fieldText}>{options[value] ?? value}</Text>
        <Text style={styles.caret}>▾</Text>
      </Pressable>
      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>{title}</Text>
            <ScrollView>
              {ordered.map((code) => (
                <Pressable
                  key={code}
                  style={[styles.option, code === value && styles.optionOn]}
                  onPress={() => {
                    onChange(code);
                    setOpen(false);
                  }}
                >
                  <Text style={[styles.optionText, code === value && styles.optionTextOn]}>
                    {options[code]}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

const webSelectStyle: CSSProperties = {
  width: "100%",
  appearance: "none",
  WebkitAppearance: "none",
  border: "none",
  background: "transparent",
  fontFamily: "IBMPlexSans_500Medium, IBM Plex Sans, sans-serif",
  fontSize: 14,
  color: colors.ink,
  padding: "10px 12px",
  outline: "none",
};

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  title: {
    fontFamily: fonts.bodyMed,
    fontSize: 11,
    letterSpacing: 0.8,
    textTransform: "uppercase",
    color: colors.muted,
  },
  selectShell: {
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.paper,
  },
  field: {
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.paper,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  fieldText: { fontFamily: fonts.bodyMed, fontSize: 14, color: colors.ink, flex: 1 },
  caret: { fontFamily: fonts.body, fontSize: 12, color: colors.muted },
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(16,36,31,0.45)",
    justifyContent: "center",
    padding: 24,
  },
  sheet: {
    backgroundColor: colors.paper,
    maxHeight: "70%",
    paddingVertical: 8,
  },
  sheetTitle: {
    fontFamily: fonts.bodySemi,
    fontSize: 13,
    color: colors.muted,
    paddingHorizontal: 16,
    paddingVertical: 10,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  option: { paddingHorizontal: 16, paddingVertical: 12 },
  optionOn: { backgroundColor: "rgba(27,61,52,0.08)" },
  optionText: { fontFamily: fonts.body, fontSize: 16, color: colors.ink },
  optionTextOn: { fontFamily: fonts.bodySemi },
});
