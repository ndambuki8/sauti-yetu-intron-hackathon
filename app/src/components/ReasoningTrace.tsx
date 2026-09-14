import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { Discriminator } from "../api/types";
import { latestTurn, useConsultation } from "../state/consultation";
import { colors, fonts, urgencyColor } from "../theme";
import { CitationDetails, ProvenanceBadges } from "./ProvenanceBadge";

function SignCard({ sign }: { sign: Discriminator }) {
  const [open, setOpen] = useState(false);
  return (
    <Pressable onPress={() => setOpen((v) => !v)} style={styles.card}>
      <View style={styles.signHead}>
        <Text style={styles.signLabel}>{sign.label}</Text>
        <ProvenanceBadges source={sign.source} />
      </View>
      {open ? (
        <View style={styles.detail}>
          <Text style={styles.muted}>
            Heard in the recording: “{sign.keyword}”
          </Text>
          <CitationDetails source={sign.source} />
        </View>
      ) : null}
    </Pressable>
  );
}

export function ReasoningTrace() {
  const { state } = useConsultation();
  const turn = latestTurn(state);

  if (!turn) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyTitle}>Reasoning appears after the first recording</Text>
        <Text style={styles.lede}>
          Urgency, why it was reached, and the guideline behind every clinical sign.
        </Text>
      </View>
    );
  }

  const t = turn.triage;
  const discriminators = t.matched_discriminators ?? [];
  const redFlags = discriminators.filter((d) => d.is_red_flag);
  const prioritySigns = discriminators.filter((d) => !d.is_red_flag);

  return (
    <View style={styles.wrap}>
      <View style={styles.banner}>
        <Text style={[styles.badge, { backgroundColor: urgencyColor[t.urgency] ?? colors.muted }]}>
          {t.urgency}
        </Text>
        <Text style={styles.meta}>
          {t.topic} · {t.suggested_department}
        </Text>
      </View>

      <Text style={styles.section}>Why this urgency</Text>
      {t.acuity ? (
        <View style={styles.card}>
          <Text style={styles.body}>
            Escalated to {t.urgency} by the sign {t.acuity.discriminator}.
          </Text>
          <ProvenanceBadges source={t.acuity.source} />
          <CitationDetails source={t.acuity.source} />
        </View>
      ) : (
        <Text style={styles.lede}>
          Urgency reflects the presenting complaint. No acute discriminators were detected.
        </Text>
      )}

      {t.topic_source ? (
        <>
          <Text style={styles.section}>Basis for the topic</Text>
          <View style={styles.card}>
            <Text style={styles.bodySemi}>{t.topic}</Text>
            <ProvenanceBadges source={t.topic_source} />
            <CitationDetails source={t.topic_source} />
          </View>
          {t.other_possible_topics.length ? (
            <Text style={styles.muted}>Also considered: {t.other_possible_topics.join("; ")}</Text>
          ) : null}
        </>
      ) : null}

      {redFlags.length ? (
        <>
          <Text style={[styles.section, { color: colors.blood }]}>Red flags ({redFlags.length})</Text>
          {redFlags.map((sign) => (
            <SignCard key={sign.id} sign={sign} />
          ))}
        </>
      ) : null}

      {prioritySigns.length ? (
        <>
          <Text style={[styles.section, { color: colors.amber }]}>
            Priority signs ({prioritySigns.length})
          </Text>
          {prioritySigns.map((sign) => (
            <SignCard key={sign.id} sign={sign} />
          ))}
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 10 },
  empty: { paddingVertical: 20, gap: 8 },
  emptyTitle: { fontFamily: fonts.bodySemi, fontSize: 16, color: colors.ink },
  lede: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, lineHeight: 19 },
  banner: { flexDirection: "row", alignItems: "center", gap: 10, flexWrap: "wrap" },
  badge: {
    color: colors.paper,
    fontFamily: fonts.bodySemi,
    fontSize: 11,
    letterSpacing: 0.8,
    paddingHorizontal: 8,
    paddingVertical: 4,
    overflow: "hidden",
  },
  meta: { fontFamily: fonts.bodyMed, fontSize: 13, color: colors.muted, flex: 1 },
  section: {
    fontFamily: fonts.bodyMed,
    fontSize: 11,
    letterSpacing: 0.8,
    textTransform: "uppercase",
    color: colors.celadon,
    marginTop: 6,
  },
  card: {
    backgroundColor: colors.paper,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 12,
    gap: 8,
  },
  body: { fontFamily: fonts.body, fontSize: 14, color: colors.ink, lineHeight: 20 },
  bodySemi: { fontFamily: fonts.bodySemi, fontSize: 14, color: colors.ink },
  muted: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, lineHeight: 17 },
  signHead: { gap: 8 },
  signLabel: { fontFamily: fonts.bodySemi, fontSize: 14, color: colors.ink },
  detail: { gap: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: colors.line },
});
