/** Best-effort itemizers for Sahara's free-text extractions.
 * Mirrors the splitting logic in backend/graph.py so the timeline chips and
 * the reasoning graph agree on what counts as one item. */

const SPLIT_RE = /[\n;•]|,\s*(?=[A-Z0-9])/;
const BULLET_RE = /^\s*(?:[-*•]|\d+[.)])\s*/;

export function splitExtraction(text: string, cap = 8): string[] {
  if (!text) return [];
  const items: string[] = [];
  for (const raw of text.split(SPLIT_RE)) {
    const cleaned = raw.replace(BULLET_RE, "").trim().replace(/[.,;]+$/, "");
    if (!cleaned || cleaned.length < 2) continue;
    if (!items.some((i) => i.toLowerCase() === cleaned.toLowerCase())) {
      items.push(cleaned);
    }
    if (items.length >= cap) break;
  }
  return items;
}

/** Red flags come as a comma-separated list or the "None detected" sentinel
 * from backend/triage.py. */
export function splitRedFlags(text: string): string[] {
  if (!text || /^none detected/i.test(text.trim())) return [];
  return text
    .split(/[,;\n]/)
    .map((f) => f.trim())
    .filter((f) => f.length > 1);
}
