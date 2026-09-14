import { useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { createSession, runTriage } from "../api/client";
import { pickAudio, startRecording, type Clip, type RecordingHandle } from "../lib/audio";
import { latestTurn, useConsultation } from "../state/consultation";
import { colors, fonts } from "../theme";
import { ClinicalCard } from "./ClinicalCard";
import { LanguageSelect } from "./LanguageSelect";
import { PatientContextForm } from "./PatientContextForm";
import { RecordControl } from "./RecordControl";
import { ReplySheet } from "./ReplySheet";
import { Timeline } from "./Timeline";

const MAX_RECORD_MS = 120_000;

export function RecordSession({ compact = false }: { compact?: boolean }) {
  const { state, dispatch } = useConsultation();
  const [consented, setConsented] = useState(false);
  const [recording, setRecording] = useState(false);
  const [ready, setReady] = useState<Clip | null>(null);
  const handle = useRef<RecordingHandle | null>(null);
  const turn = latestTurn(state);

  const stopRecording = async () => {
    if (!handle.current) return;
    try {
      const clip = await handle.current.stop();
      handle.current = null;
      setReady(clip);
    } catch (err) {
      dispatch({
        type: "analysisFailed",
        message: err instanceof Error ? err.message : "Could not stop recording",
      });
    } finally {
      setRecording(false);
    }
  };

  useEffect(() => {
    if (!recording) return;
    const timer = setTimeout(() => {
      void stopRecording();
    }, MAX_RECORD_MS);
    return () => clearTimeout(timer);
  }, [recording]);

  const status = state.analysing
    ? "Listening through Sahara…"
    : recording
      ? "Recording — tap to stop"
      : ready
        ? "Clip ready — analyse"
        : consented
          ? "Tap to record the patient"
          : "Consent required before recording";

  const toggleRecord = async () => {
    if (!consented || state.analysing) return;
    if (recording && handle.current) {
      await stopRecording();
      return;
    }
    try {
      handle.current = await startRecording();
      setRecording(true);
      setReady(null);
    } catch (err) {
      dispatch({
        type: "analysisFailed",
        message: err instanceof Error ? err.message : "Microphone unavailable",
      });
    }
  };

  const pick = async () => {
    if (!consented || state.analysing) return;
    const clip = await pickAudio();
    if (clip) setReady(clip);
  };

  const analyse = async () => {
    if (!ready || state.analysing) return;
    dispatch({ type: "analysisStarted" });
    try {
      let sessionId = state.sessionId;
      if (!sessionId) {
        sessionId = await createSession(state.doctorLanguage, state.languageCode);
        dispatch({ type: "sessionStarted", sessionId });
      }
      const languageName =
        state.languageCode === "auto"
          ? "Auto-detect"
          : (state.languages[state.languageCode] ?? state.languageCode);
      const response = await runTriage(
        ready,
        state.languageCode,
        state.doctorLanguage,
        sessionId,
        state.patient,
      );
      dispatch({ type: "turnAdded", response, languageName });
      setReady(null);
    } catch (err) {
      dispatch({
        type: "analysisFailed",
        message: err instanceof Error ? err.message : "Triage failed",
      });
    }
  };

  return (
    <ScrollView contentContainerStyle={[styles.page, compact && styles.compact]} keyboardShouldPersistTaps="handled">
      <Pressable
        onPress={() => setConsented((v) => !v)}
        style={[styles.consent, consented && styles.consentOn]}
      >
        <View style={[styles.box, consented && styles.boxOn]} />
        <Text style={styles.consentText}>
          The patient consents to this recording. Audio is sent for transcription and not stored by Sauti Yetu.
        </Text>
      </Pressable>

      <PatientContextForm />

      <LanguageSelect
        title="Your language"
        options={state.doctorLanguages}
        value={state.doctorLanguage}
        onChange={(code) => dispatch({ type: "doctorLanguageChanged", doctorLanguage: code })}
        preferred={["en", "fr"]}
      />
      <LanguageSelect
        title="Patient language"
        options={state.languages}
        value={state.languageCode}
        onChange={(code) => dispatch({ type: "languageChanged", languageCode: code })}
        preferred={["auto", "sw", "en", "fr"]}
      />

      <RecordControl
        recording={recording}
        analysing={state.analysing}
        disabled={!consented || state.analysing}
        onPress={toggleRecord}
        label={status}
      />

      <View style={styles.actions}>
        <Pressable onPress={pick} disabled={!consented} style={[styles.ghost, !consented && styles.off]}>
          <Text style={styles.ghostText}>Pick conversation</Text>
        </Pressable>
        <Pressable
          onPress={analyse}
          disabled={!ready || state.analysing}
          style={[styles.primary, (!ready || state.analysing) && styles.off]}
        >
          <Text style={styles.primaryText}>{state.analysing ? "Working…" : "Analyse"}</Text>
        </Pressable>
      </View>

      {state.error ? <Text style={styles.error}>{state.error}</Text> : null}
      {turn ? <ClinicalCard turn={turn} /> : null}
      <ReplySheet />
      <Timeline items={state.turns} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: 20, gap: 18, paddingBottom: 48 },
  compact: { padding: 16 },
  consent: {
    flexDirection: "row",
    gap: 12,
    alignItems: "flex-start",
    padding: 12,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: "rgba(255,255,255,0.5)",
  },
  consentOn: { borderColor: colors.celadon },
  box: { width: 18, height: 18, borderWidth: 1, borderColor: colors.ink, marginTop: 2 },
  boxOn: { backgroundColor: colors.celadon, borderColor: colors.celadon },
  consentText: { flex: 1, fontFamily: fonts.body, fontSize: 13, color: colors.ink, lineHeight: 19 },
  actions: { flexDirection: "row", gap: 10 },
  ghost: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.ink,
    paddingVertical: 12,
    alignItems: "center",
  },
  ghostText: { fontFamily: fonts.bodySemi, color: colors.ink },
  primary: {
    flex: 1,
    backgroundColor: colors.ink,
    paddingVertical: 12,
    alignItems: "center",
  },
  primaryText: { fontFamily: fonts.bodySemi, color: colors.paper },
  off: { opacity: 0.35 },
  error: { fontFamily: fonts.body, color: colors.blood, fontSize: 13 },
});
