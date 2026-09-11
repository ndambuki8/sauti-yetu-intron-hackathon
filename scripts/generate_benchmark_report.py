"""Generate the code-switch ASR benchmark report (PDF + raw JSON).

Batch-runs every clip listed in data/samples/metadata.csv through the three
benchmark models (Intron Sahara, OpenAI Whisper, Meta MMS) via
backend.benchmark, aggregates WER/CER/latency overall and per language pair
and noise condition, renders charts, and writes:

    reports/benchmark_report.pdf   the submission report
    reports/results.json           raw per-clip results for reproducibility

Usage (from the project root, venv active, INTRON_API_KEY in .env):

    python -m scripts.generate_benchmark_report
"""

import csv
import json
import re
import statistics
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from fpdf import FPDF

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.benchmark import run_benchmark  # noqa: E402
from backend.config import PROJECT_ROOT, SAMPLES_DIR, SUPPORTED_LANGUAGES  # noqa: E402

REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS = ["Intron Sahara", "OpenAI Whisper", "Meta MMS"]

# Map the human-readable language_pair in metadata.csv to the app code.
PAIR_TO_CODE = {name.lower(): code for code, name in SUPPORTED_LANGUAGES.items()}


def _json_field(row: dict, name: str, default):
    value = row.get(name, "").strip()
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in metadata column {name!r}: {value}") from exc


def _language_code(row: dict) -> str:
    explicit = row.get("language_code", "").strip().lower()
    if explicit in SUPPORTED_LANGUAGES:
        return explicit
    pair = row.get("language_pair", "").strip().lower()
    if pair in PAIR_TO_CODE:
        return PAIR_TO_CODE[pair]
    # Existing sample names carry the language code even when the old CSV
    # accidentally used "English" for every language_pair value.
    match = re.search(r"afrispeech_([a-z]+)_", row.get("filename", "").lower())
    return match.group(1) if match and match.group(1) in SUPPORTED_LANGUAGES else "en"


def load_metadata() -> list[dict]:
    path = SAMPLES_DIR / "metadata.csv"
    with open(path, encoding="utf-8") as fh:
        rows = [row for row in csv.DictReader(fh) if row.get("filename")]
    existing = []
    for row in rows:
        if (SAMPLES_DIR / row["filename"]).exists():
            existing.append(row)
        else:
            print(f"  skipping {row['filename']} (file not found in data/samples)")
    return existing


def run_all(rows: list[dict], agentic: bool = False) -> list[dict]:
    results = []
    for i, row in enumerate(rows, 1):
        language_code = _language_code(row)
        print(f"[{i}/{len(rows)}] {row['filename']} ({row['language_pair']}, lang hint: {language_code})")
        audio_bytes = (SAMPLES_DIR / row["filename"]).read_bytes()
        bench = run_benchmark(
            audio_bytes,
            filename=row["filename"],
            reference_transcript=row["reference_transcript"],
            language_code=language_code,
            switch_points=_json_field(row, "switch_points", []),
            agent_reference={
                "expected_topic": row.get("expected_topic", ""),
                "expected_urgency": row.get("expected_urgency", ""),
                "expected_department": row.get("expected_department", ""),
                "expected_slots": _json_field(row, "expected_slots", {}),
                "expected_entities": _json_field(row, "expected_entities", []),
            }
            if any(row.get(key, "").strip() for key in (
                "expected_topic", "expected_urgency", "expected_department",
                "expected_slots", "expected_entities",
            ))
            else None,
            agentic=agentic,
        )
        results.append({"metadata": row, "benchmark": bench})
        for r in bench["results"]:
            wer = r["wer"] if r["wer"] is not None else "err"
            print(
                f"    {r['model']:16s} WER={wer} RTF={r.get('rtf', '-') } "
                f"({r['error'] or 'ok'})"
            )
    return results


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def aggregate(results: list[dict], key_fn) -> dict:
    """Aggregate transcript, switch-point, RTF, and agentic metrics."""
    groups: dict[str, dict[str, dict[str, list[float]]]] = {}
    for clip in results:
        group = key_fn(clip)
        for r in clip["benchmark"]["results"]:
            bucket = groups.setdefault(group, {}).setdefault(r["model"], {
                "wer": [], "cer": [], "latency": [], "rtf": [],
                "switch_point_wer": [], "intent": [], "slot": [], "entity": [],
            })
            if r["wer"] is not None:
                bucket["wer"].append(r["wer"])
                bucket["cer"].append(r["cer"])
            if r["latency_seconds"] is not None:
                bucket["latency"].append(r["latency_seconds"])
            for metric, source in (("rtf", r.get("rtf")),
                                   ("switch_point_wer", r.get("switch_point", {}).get("wer"))):
                if source is not None:
                    bucket[metric].append(source)
            agent = r.get("agentic") or {}
            for metric, source in (("intent", agent.get("intent_correct")),
                                   ("slot", agent.get("slot_accuracy")),
                                   ("entity", agent.get("entity_error_rate"))):
                if source is not None:
                    bucket[metric].append(float(source))
    return {
        group: {
            model: {
                "mean_wer": _mean(b["wer"]),
                "mean_cer": _mean(b["cer"]),
                "mean_latency": _mean(b["latency"]),
                "mean_rtf": _mean(b["rtf"]),
                "mean_switch_point_wer": _mean(b["switch_point_wer"]),
                "intent_accuracy": _mean(b["intent"]),
                "slot_accuracy": _mean(b["slot"]),
                "entity_error_rate": _mean(b["entity"]),
                "n": len(b["wer"]),
            }
            for model, b in models.items()
        }
        for group, models in groups.items()
    }


def make_charts(overall: dict, by_pair: dict) -> list[Path]:
    REPORTS_DIR.mkdir(exist_ok=True)
    paths = []

    # Chart 1: overall WER by model
    fig, ax = plt.subplots(figsize=(6, 3.2))
    models = [m for m in MODELS if m in overall.get("all", {})]
    wers = [overall["all"][m]["mean_wer"] for m in models]
    plotted = [(m, w) for m, w in zip(models, wers) if w is not None]
    if plotted:
        ax.bar([p[0] for p in plotted], [p[1] for p in plotted], color="#555555")
        ax.set_ylabel("Mean WER (lower is better)")
        ax.set_title("Overall WER by model")
        fig.tight_layout()
        path = REPORTS_DIR / "chart_overall_wer.png"
        fig.savefig(path, dpi=150)
        paths.append(path)
    plt.close(fig)

    # Chart 2: WER by language pair, grouped by model
    pairs = sorted(by_pair.keys())
    if pairs:
        fig, ax = plt.subplots(figsize=(7, 3.6))
        width = 0.8 / max(len(MODELS), 1)
        shades = ["#333333", "#777777", "#bbbbbb"]
        for mi, model in enumerate(MODELS):
            xs, ys = [], []
            for pi, pair in enumerate(pairs):
                stats = by_pair[pair].get(model, {})
                if stats.get("mean_wer") is not None:
                    xs.append(pi + mi * width)
                    ys.append(stats["mean_wer"])
            if xs:
                ax.bar(xs, ys, width=width, label=model, color=shades[mi % 3])
        ax.set_xticks([i + width for i in range(len(pairs))])
        ax.set_xticklabels(pairs, rotation=20, ha="right", fontsize=8)
        ax.set_ylabel("Mean WER")
        ax.set_title("WER by language pair")
        ax.legend(fontsize=8)
        fig.tight_layout()
        path = REPORTS_DIR / "chart_wer_by_pair.png"
        fig.savefig(path, dpi=150)
        paths.append(path)
        plt.close(fig)

    return paths


def _latin1(text: str) -> str:
    """Helvetica (core font) only supports latin-1; replace anything else so
    transcripts with curly quotes/diacritics can't crash the render."""
    return str(text).encode("latin-1", "replace").decode("latin-1")


class ReportPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(130)
        self.cell(0, 6, "Voice Triage Hint - Code-Switch ASR Benchmark Report", align="R")
        self.ln(10)
        self.set_text_color(0)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(130)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")

    def para(self, text):
        """Full-width paragraph. fpdf2's multi_cell leaves the cursor at the
        RIGHT margin by default, which gives the next full-width cell zero
        width and raises "Not enough horizontal space"; always returning the
        cursor to the left margin prevents that."""
        self.set_x(self.l_margin)
        self.multi_cell(0, 5, _latin1(text), new_x="LMARGIN", new_y="NEXT")

    def h1(self, text):
        self.set_font("Helvetica", "B", 16)
        self.set_x(self.l_margin)
        self.multi_cell(0, 8, _latin1(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def h2(self, text):
        self.set_font("Helvetica", "B", 12)
        self.set_x(self.l_margin)
        self.multi_cell(0, 7, _latin1(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_x(self.l_margin)
        self.multi_cell(0, 5.5, _latin1(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def table(self, headers, rows, col_widths):
        self.set_font("Helvetica", "B", 9)
        for h, w in zip(headers, col_widths):
            self.cell(w, 7, _latin1(h), border=1)
        self.ln()
        self.set_font("Helvetica", "", 9)
        for row in rows:
            # crude row-height handling: truncate long cells
            for value, w in zip(row, col_widths):
                text = _latin1(value)
                max_chars = int(w / 1.9)
                if len(text) > max_chars:
                    text = text[: max_chars - 3] + "..."
                self.cell(w, 7, text, border=1)
            self.ln()
        self.ln(3)


def fmt(v):
    return "-" if v is None else v


def build_pdf(results: list[dict], overall: dict, by_pair: dict, by_noise: dict,
              chart_paths: list[Path]) -> Path:
    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.h1("Code-Switch ASR Benchmark Report")
    pdf.body(
        f"Project: Voice Triage Hint - agentic voice triage for code-switching patients\n"
        f"Challenge: MLC (Africa) x Intron Agentic Voice AI Challenge, Deep Learning Indaba 2026\n"
        f"Date: {date.today().isoformat()}\n"
        f"Clips evaluated: {len(results)}"
    )

    pdf.h2("1. Methodology and fairness")
    pdf.body(
        "Three speech-to-text models were compared on the same code-switched audio clips: "
        "Intron Sahara (commercial API optimized for African accents), OpenAI Whisper "
        "(open-source, run locally), and Meta MMS mms-1b-all (open-source, run locally).\n\n"
        "Fairness controls: every model received the identical audio file, converted to "
        "16 kHz mono WAV where required. Every model received the same input-language hint "
        "(Sahara: use_language_asr_input; Whisper: language parameter where the language is "
        "supported, otherwise auto-detect; MMS: the matching language adapter). Hypotheses and "
        "references were normalized identically before scoring: lowercased, punctuation removed, "
        "whitespace collapsed (jiwer). Metrics: Word Error Rate (WER), Character Error Rate (CER) "
        "- CER is included because it is fairer to agglutinative languages such as Swahili and "
        "Kinyarwanda - and wall-clock latency measured around each model call on the same machine "
        "(API latency includes network time; local latency depends on hardware).\n\n"
        "Test data: self-recorded code-switched clips described in data/samples/metadata.csv with "
        "language pair, domain, accent/country, device type, and noise condition per clip."
    )

    pdf.h2("2. Overall results")
    headers = ["Model", "Mean WER", "Mean CER", "Mean latency (s)", "Clips"]
    widths = [55, 30, 30, 40, 20]
    rows = [
        [m, fmt(s["mean_wer"]), fmt(s["mean_cer"]), fmt(s["mean_latency"]), s["n"]]
        for m, s in overall.get("all", {}).items()
    ]
    pdf.table(headers, rows, widths)

    for chart in chart_paths:
        if chart.exists():
            pdf.image(str(chart), w=150)
            pdf.ln(4)

    pdf.h2("3. Results by language pair")
    for pair, models in sorted(by_pair.items()):
        pdf.body(f"Language pair: {pair}")
        rows = [
            [m, fmt(s["mean_wer"]), fmt(s["mean_cer"]), fmt(s["mean_latency"]), s["n"]]
            for m, s in models.items()
        ]
        pdf.table(headers, rows, widths)

    pdf.h2("4. Results by noise condition")
    for noise, models in sorted(by_noise.items()):
        pdf.body(f"Noise condition: {noise}")
        rows = [
            [m, fmt(s["mean_wer"]), fmt(s["mean_cer"]), fmt(s["mean_latency"]), s["n"]]
            for m, s in models.items()
        ]
        pdf.table(headers, rows, widths)

    pdf.h2("5. Boundary and downstream metrics")
    pdf.body(
        "Switch-point WER is the mean WER in a three-word window on each side of an "
        "annotated language boundary. RTF is wall-clock latency divided by decoded "
        "audio duration; values below 1.0 are faster than real time. When expected "
        "agentic labels are present, intent accuracy, slot accuracy, and entity error "
        "rate are reported in the raw JSON. Sahara agentic mode preserves its "
        "telehealth extraction fields; local models receive the same transcript-only "
        "triage function for a comparable baseline."
    )
    for model, stats in sorted(overall.get("all", {}).items()):
        if any(stats.get(key) is not None for key in (
            "mean_switch_point_wer", "intent_accuracy", "slot_accuracy", "entity_error_rate"
        )):
            pdf.body(
                f"{model}: switch-point WER={fmt(stats.get('mean_switch_point_wer'))}, "
                f"intent accuracy={fmt(stats.get('intent_accuracy'))}, "
                f"slot accuracy={fmt(stats.get('slot_accuracy'))}, "
                f"entity error rate={fmt(stats.get('entity_error_rate'))}."
            )

    pdf.h2("6. Per-clip transcripts")
    for clip in results:
        meta = clip["metadata"]
        pdf.set_font("Helvetica", "B", 10)
        pdf.para(
            f"{meta['filename']} | {meta['language_pair']} | {meta['accent_country']} | "
            f"{meta['device_type']} | {meta['noise_condition']}"
        )
        pdf.set_font("Helvetica", "", 9)
        pdf.para(f"Reference: {meta['reference_transcript']}")
        for r in clip["benchmark"]["results"]:
            if r["error"]:
                line = f"{r['model']}: ERROR - {r['error']}"
            else:
                line = (
                    f"{r['model']} (WER {fmt(r['wer'])}, CER {fmt(r['cer'])}, "
                    f"{fmt(r['latency_seconds'])}s): {r['transcript']}"
                )
            pdf.para(line)
        pdf.ln(3)

    pdf.h2("7. Limitations and bias notes")
    pdf.body(
        "The sample set is small and self-recorded by the team, so results indicate trends rather "
        "than statistically significant differences. Accent coverage is limited to the speakers "
        "available to the team; models may perform differently on other regional accents, ages, "
        "and genders. Local model latency is hardware-dependent and not directly comparable to "
        "API latency, which includes network round-trips. Reference transcripts were written by "
        "the speakers themselves; transcription conventions for code-switched text (spelling of "
        "borrowed words) can bias WER slightly for all models equally. Raw per-clip outputs are "
        "provided in reports/results.json for independent verification."
    )

    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = REPORTS_DIR / "benchmark_report.pdf"
    pdf.output(str(out_path))
    return out_path


def main():
    results_path = REPORTS_DIR / "results.json"

    if "--rebuild-only" in sys.argv:
        # Rebuild charts + PDF from a previous run without re-running models.
        if not results_path.exists():
            print(f"No saved results at {results_path}; run without --rebuild-only first.")
            sys.exit(1)
        with open(results_path, encoding="utf-8") as fh:
            saved = json.load(fh)
        results = saved["clips"]
        overall = saved["overall"]
        by_pair = saved["by_language_pair"]
        by_noise = saved["by_noise_condition"]
        print(f"Rebuilding report from {results_path} ({len(results)} clips)...")
        charts = make_charts(overall, by_pair)
        pdf_path = build_pdf(results, overall, by_pair, by_noise, charts)
        print(f"Report written to {pdf_path}")
        return

    rows = load_metadata()
    if not rows:
        print(
            "No audio clips found. Record clips into data/samples/ and register them "
            "in metadata.csv first (see data/samples/README.md)."
        )
        sys.exit(1)

    print(f"Running benchmark on {len(rows)} clip(s) across 3 models...\n")
    agentic = "--agentic" in sys.argv
    print("Agentic Sahara extraction: enabled" if agentic else "Agentic Sahara extraction: disabled")
    results = run_all(rows, agentic=agentic)

    overall = aggregate(results, lambda c: "all")
    by_pair = aggregate(results, lambda c: c["metadata"]["language_pair"])
    by_noise = aggregate(results, lambda c: c["metadata"]["noise_condition"])

    REPORTS_DIR.mkdir(exist_ok=True)
    results_path = REPORTS_DIR / "results.json"
    with open(results_path, "w", encoding="utf-8") as fh:
        json.dump(
            {"overall": overall, "by_language_pair": by_pair,
             "by_noise_condition": by_noise, "clips": results},
            fh, ensure_ascii=False, indent=2,
        )
    print(f"\nRaw results written to {results_path}")

    charts = make_charts(overall, by_pair)
    pdf_path = build_pdf(results, overall, by_pair, by_noise, charts)
    print(f"Report written to {pdf_path}")


if __name__ == "__main__":
    main()
