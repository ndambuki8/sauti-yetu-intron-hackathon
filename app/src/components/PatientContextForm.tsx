import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { useState } from "react";
import type { PatientInput } from "../api/types";
import { latestTurn, useConsultation } from "../state/consultation";
import { colors, fonts } from "../theme";

const SEX = [
  { id: "", label: "Unknown" },
  { id: "female", label: "Female" },
  { id: "male", label: "Male" },
];

const AVPU = ["", "A", "V", "P", "U"];

export function PatientContextForm() {
  const { state, dispatch } = useConsultation();
  const [vitalsOpen, setVitalsOpen] = useState(false);
  const turn = latestTurn(state);
  const flagged = new Set(turn?.triage.auto_detected ?? []);
  const p = state.patient;

  const set = (patch: Partial<PatientInput>) =>
    dispatch({ type: "patientChanged", patient: { ...p, ...patch } });

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>Age, sex, pregnancy</Text>
      {flagged.size ? (
        <Text style={styles.warn}>
          Taken from the recording: {Array.from(flagged).join(", ")}. Confirm before the next clip.
        </Text>
      ) : null}
      <View style={styles.row}>
        <Field
          label="Age"
          value={p.age}
          onChange={(age) => set({ age })}
          flagged={flagged.has("age")}
          keyboard="numeric"
        />
        <View style={styles.flex}>
          <Text style={styles.label}>Sex</Text>
          <View style={styles.chips}>
            {SEX.map((opt) => (
              <Pressable
                key={opt.id || "unknown"}
                onPress={() => set({ sex: opt.id })}
                style={[styles.chip, p.sex === opt.id && styles.chipOn]}
              >
                <Text style={[styles.chipText, p.sex === opt.id && styles.chipTextOn]}>{opt.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      </View>
      <Pressable
        onPress={() =>
          set({ pregnant: p.pregnant === true ? null : true })
        }
        style={[styles.consent, p.pregnant && styles.consentOn, flagged.has("pregnancy") && styles.flagged]}
      >
        <View style={[styles.box, p.pregnant && styles.boxOn]} />
        <Text style={styles.consentText}>Pregnant</Text>
      </Pressable>

      <Pressable onPress={() => setVitalsOpen((v) => !v)}>
        <Text style={styles.toggle}>{vitalsOpen ? "Hide vitals" : "Optional vitals"}</Text>
      </Pressable>
      {vitalsOpen ? (
        <View style={styles.vitals}>
          <Field label="HR" value={p.hr} onChange={(hr) => set({ hr })} keyboard="numeric" />
          <Field label="RR" value={p.rr} onChange={(rr) => set({ rr })} keyboard="numeric" />
          <Field label="Temp °C" value={p.temp} onChange={(temp) => set({ temp })} keyboard="numeric" />
          <Field label="SpO2" value={p.spo2} onChange={(spo2) => set({ spo2 })} keyboard="numeric" />
          <View style={styles.flex}>
            <Text style={styles.label}>AVPU</Text>
            <View style={styles.chips}>
              {AVPU.map((opt) => (
                <Pressable
                  key={opt || "none"}
                  onPress={() => set({ avpu: opt })}
                  style={[styles.chip, p.avpu === opt && styles.chipOn]}
                >
                  <Text style={[styles.chipText, p.avpu === opt && styles.chipTextOn]}>
                    {opt || "—"}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        </View>
      ) : null}
    </View>
  );
}

function Field({
  label,
  value,
  onChange,
  flagged,
  keyboard,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  flagged?: boolean;
  keyboard?: "numeric";
}) {
  return (
    <View style={styles.flex}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        keyboardType={keyboard ?? "default"}
        style={[styles.input, flagged && styles.flagged]}
        placeholder="—"
        placeholderTextColor={colors.muted}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 10 },
  title: { fontFamily: fonts.bodySemi, fontSize: 14, color: colors.ink },
  warn: { fontFamily: fonts.body, fontSize: 12, color: colors.ember, lineHeight: 17 },
  row: { flexDirection: "row", gap: 10 },
  flex: { flex: 1, gap: 4 },
  label: { fontFamily: fonts.bodyMed, fontSize: 11, color: colors.muted, letterSpacing: 0.4 },
  input: {
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.paper,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontFamily: fonts.body,
    fontSize: 14,
    color: colors.ink,
  },
  flagged: { borderColor: colors.ember },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: {
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  chipOn: { backgroundColor: colors.ink, borderColor: colors.ink },
  chipText: { fontFamily: fonts.bodyMed, fontSize: 12, color: colors.ink },
  chipTextOn: { color: colors.paper },
  consent: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 4 },
  consentOn: {},
  box: { width: 16, height: 16, borderWidth: 1, borderColor: colors.ink },
  boxOn: { backgroundColor: colors.celadon, borderColor: colors.celadon },
  consentText: { fontFamily: fonts.body, fontSize: 13, color: colors.ink },
  toggle: { fontFamily: fonts.bodySemi, fontSize: 13, color: colors.celadon },
  vitals: { gap: 10 },
});
