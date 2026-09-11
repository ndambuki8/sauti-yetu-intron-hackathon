import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { getPhrases, respond } from "../api/client";
import type { Phrase } from "../api/types";
import { playUri } from "../lib/audio";
import { toWorkerReply, useConsultation } from "../state/consultation";
import { colors, fonts } from "../theme";

export function ReplySheet() {
  const { state, dispatch } = useConsultation();
  const [phrases, setPhrases] = useState<Phrase[]>([]);
  const [text, setText] = useState("");
  const [gender, setGender] = useState<"male" | "female">("female");
  const [speaking, setSpeaking] = useState(false);

  const patientLang =
    state.languageCode === "auto"
      ? state.detectedLanguages[state.detectedLanguages.length - 1] || "en"
      : state.languageCode;
  const hasPatient = state.turns.some((t) => t.kind === "patient");

  useEffect(() => {
    if (!hasPatient) return;
    getPhrases(patientLang)
      .then(setPhrases)
      .catch(() => setPhrases([]));
  }, [patientLang, hasPatient]);

  if (!hasPatient) return null;

  const speak = async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed || speaking) return;
    setSpeaking(true);
    try {
      const response = await respond(trimmed, patientLang, gender);
      const reply = toWorkerReply(response);
      dispatch({ type: "replyAdded", reply });
      setText("");
      await playUri(reply.audioUrl).catch(() => undefined);
    } catch (err) {
      dispatch({
        type: "analysisFailed",
        message: err instanceof Error ? err.message : "Reply failed",
      });
    } finally {
      setSpeaking(false);
    }
  };

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>Speak to the patient</Text>
      <View style={styles.gender}>
        {(["female", "male"] as const).map((g) => (
          <Pressable key={g} onPress={() => setGender(g)} style={[styles.gChip, gender === g && styles.gOn]}>
            <Text style={[styles.gText, gender === g && styles.gTextOn]}>{g}</Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.phrases}>
        {phrases.slice(0, 6).map((p) => (
          <Pressable key={p.english} onPress={() => speak(p.english)} style={styles.phrase}>
            <Text style={styles.phraseText}>{p.english}</Text>
          </Pressable>
        ))}
      </View>
      <TextInput
        value={text}
        onChangeText={setText}
        placeholder="Type in English…"
        placeholderTextColor={colors.muted}
        style={styles.input}
        multiline
      />
      <Pressable
        onPress={() => speak(text)}
        disabled={speaking || !text.trim()}
        style={[styles.send, (!text.trim() || speaking) && styles.sendOff]}
      >
        <Text style={styles.sendText}>{speaking ? "Speaking…" : "Speak reply"}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 10 },
  title: { fontFamily: fonts.bodySemi, fontSize: 15, color: colors.ink },
  gender: { flexDirection: "row", gap: 8 },
  gChip: { borderWidth: 1, borderColor: colors.line, paddingHorizontal: 10, paddingVertical: 6 },
  gOn: { backgroundColor: colors.ink, borderColor: colors.ink },
  gText: { fontFamily: fonts.bodyMed, fontSize: 12, color: colors.ink },
  gTextOn: { color: colors.paper },
  phrases: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  phrase: { backgroundColor: "rgba(27,61,52,0.08)", paddingHorizontal: 10, paddingVertical: 7 },
  phraseText: { fontFamily: fonts.body, fontSize: 12, color: colors.moss },
  input: {
    minHeight: 64,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 10,
    fontFamily: fonts.body,
    fontSize: 15,
    color: colors.ink,
    textAlignVertical: "top",
  },
  send: { backgroundColor: colors.ink, paddingVertical: 12, alignItems: "center" },
  sendOff: { opacity: 0.4 },
  sendText: { fontFamily: fonts.bodySemi, color: colors.paper, fontSize: 14 },
});
