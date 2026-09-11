import { useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { runCommand } from "../../api/client";
import { Flowchart } from "../../components/Flowchart";
import { startRecording, type Clip, type RecordingHandle } from "../../lib/audio";
import { looksLikeMermaid } from "../../lib/mermaid";
import { useConsultation } from "../../state/consultation";
import { colors, fonts } from "../../theme";

export default function ArtifactsScreen() {
  const { state, dispatch } = useConsultation();
  const [text, setText] = useState("");
  const [recording, setRecording] = useState(false);
  const handle = useRef<RecordingHandle | null>(null);

  const submit = async (opts: { text?: string; audio?: Clip }) => {
    if (!state.sessionId) {
      dispatch({
        type: "analysisFailed",
        message: "Record the patient first so the agent has a consult to work from.",
      });
      return;
    }
    dispatch({ type: "commandStarted" });
    try {
      const response = await runCommand({
        sessionId: state.sessionId,
        text: opts.text,
        audio: opts.audio,
        filename: opts.filename,
      });
      dispatch({ type: "commandFinished", artifacts: response.artifacts });
      setText("");
    } catch (err) {
      dispatch({
        type: "analysisFailed",
        message: err instanceof Error ? err.message : "Command failed",
      });
    }
  };

  const toggleVoice = async () => {
    if (recording && handle.current) {
      try {
        const clip = await handle.current.stop();
        await submit({ audio: clip, text: text.trim() || undefined });
      } finally {
        handle.current = null;
        setRecording(false);
      }
      return;
    }
    try {
      handle.current = await startRecording();
      setRecording(true);
    } catch (err) {
      dispatch({
        type: "analysisFailed",
        message: err instanceof Error ? err.message : "Microphone unavailable",
      });
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <Text style={styles.title}>Ask the consult</Text>
      <Text style={styles.sub}>
        “Prepare a flowchart of probable diseases from these symptoms.” The agent writes from this session only.
      </Text>

      <TextInput
        value={text}
        onChangeText={setText}
        placeholder="Or type the request…"
        placeholderTextColor={colors.muted}
        style={styles.input}
        multiline
      />

      <View style={styles.row}>
        <Pressable onPress={toggleVoice} style={[styles.voice, recording && styles.voiceHot]}>
          <Text style={styles.voiceText}>{recording ? "Stop & send" : "Hold the room — record"}</Text>
        </Pressable>
        <Pressable
          onPress={() => submit({ text: text.trim() })}
          disabled={!text.trim() || state.commanding}
          style={[styles.send, (!text.trim() || state.commanding) && styles.off]}
        >
          <Text style={styles.sendText}>{state.commanding ? "Writing…" : "Ask"}</Text>
        </Pressable>
      </View>

      {state.error ? <Text style={styles.error}>{state.error}</Text> : null}

      {state.artifacts.length === 0 ? (
        <Text style={styles.empty}>No notes yet. Record a patient turn, then ask.</Text>
      ) : (
        [...state.artifacts].reverse().map((art) => (
          <View key={art.id} style={styles.card}>
            <Text style={styles.kind}>{art.intent}</Text>
            <Text style={styles.cardTitle}>{art.title}</Text>
            <Text style={styles.cmd}>“{art.command_text}”</Text>
            {art.kind === "flowchart" || looksLikeMermaid(art.body) ? (
              <Flowchart source={art.body} />
            ) : (
              <Text style={styles.body}>{art.body}</Text>
            )}
            {art.notes ? <Text style={styles.notes}>{art.notes}</Text> : null}
          </View>
        ))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: 20, gap: 14, paddingBottom: 48 },
  title: { fontFamily: fonts.displaySemi, fontSize: 28, color: colors.ink },
  sub: { fontFamily: fonts.body, fontSize: 15, color: colors.muted, lineHeight: 22 },
  input: {
    minHeight: 80,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 12,
    fontFamily: fonts.body,
    fontSize: 16,
    color: colors.ink,
    backgroundColor: colors.paper,
    textAlignVertical: "top",
  },
  row: { flexDirection: "row", gap: 10 },
  voice: {
    flex: 1.4,
    backgroundColor: colors.ember,
    paddingVertical: 14,
    alignItems: "center",
  },
  voiceHot: { backgroundColor: colors.blood },
  voiceText: { fontFamily: fonts.bodySemi, color: colors.paper },
  send: {
    flex: 0.8,
    backgroundColor: colors.ink,
    paddingVertical: 14,
    alignItems: "center",
  },
  sendText: { fontFamily: fonts.bodySemi, color: colors.paper },
  off: { opacity: 0.35 },
  error: { fontFamily: fonts.body, color: colors.blood },
  empty: { fontFamily: fonts.body, color: colors.muted, marginTop: 12 },
  card: {
    backgroundColor: colors.paper,
    padding: 16,
    gap: 8,
    borderWidth: 1,
    borderColor: colors.line,
  },
  kind: {
    fontFamily: fonts.bodyMed,
    fontSize: 11,
    letterSpacing: 1,
    textTransform: "uppercase",
    color: colors.celadon,
  },
  cardTitle: { fontFamily: fonts.displaySemi, fontSize: 20, color: colors.ink },
  cmd: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, fontStyle: "italic" },
  body: { fontFamily: fonts.body, fontSize: 15, color: colors.ink, lineHeight: 22 },
  notes: { fontFamily: fonts.bodyMed, fontSize: 13, color: colors.cedar },
});
