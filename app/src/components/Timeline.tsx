import { Pressable, StyleSheet, Text, View } from "react-native";
import type { TimelineItem } from "../api/types";
import { playUri } from "../lib/audio";
import { colors, fonts } from "../theme";

export function Timeline({ items }: { items: TimelineItem[] }) {
  if (!items.length) return null;
  return (
    <View style={styles.list}>
      {items.map((item, i) =>
        item.kind === "patient" ? (
          <View key={`p-${item.index}-${i}`} style={styles.patient}>
            <Text style={styles.who}>
              Patient · {item.languageName}
              {item.detectedLanguage ? ` (${item.detectedLanguage})` : ""}
            </Text>
            <Text style={styles.body}>{item.transcriptDoctor}</Text>
          </View>
        ) : (
          <Pressable
            key={`w-${item.timestamp}-${i}`}
            style={styles.worker}
            onPress={() => playUri(item.audioUrl).catch(() => undefined)}
          >
            <Text style={styles.who}>You · tap to replay</Text>
            <Text style={styles.body}>{item.translatedText}</Text>
            {item.englishFallback ? (
              <Text style={styles.note}>Spoken in accented English</Text>
            ) : null}
          </Pressable>
        ),
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: 10 },
  patient: {
    backgroundColor: "rgba(27,61,52,0.06)",
    padding: 14,
    borderLeftWidth: 3,
    borderLeftColor: colors.celadon,
    gap: 4,
  },
  worker: {
    backgroundColor: "rgba(201,106,43,0.08)",
    padding: 14,
    borderLeftWidth: 3,
    borderLeftColor: colors.ember,
    gap: 4,
  },
  who: {
    fontFamily: fonts.bodyMed,
    fontSize: 11,
    letterSpacing: 0.7,
    textTransform: "uppercase",
    color: colors.muted,
  },
  body: { fontFamily: fonts.body, fontSize: 15, color: colors.ink, lineHeight: 22 },
  note: { fontFamily: fonts.body, fontSize: 12, color: colors.muted },
});
