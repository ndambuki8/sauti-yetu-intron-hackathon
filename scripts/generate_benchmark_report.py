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


def run_all(rows: list[dict]) -> list[dict]:
    results = []
    for i, row in enumerate(rows, 1):
        language_code = PAIR_TO_CODE.get(row["language_pair"].strip().lower(), "en")
        print(f"[{i}/{len(rows)}] {row['filename']} ({row['language_pair']}, lang hint: {language_code})")
        audio_bytes = (SAMPLES_DIR / row["filename"]).read_bytes()
        bench = run_benchmark(
            audio_bytes,
            filename=row["filename"],
            reference_transcript=row["reference_transcript"],
            language_code=language_code,
        )
        results.append({"metadata": row, "benchmark": bench})
        for r in bench["results"]:
            wer = r["wer"] if r["wer"] is not None else "err"
            print(f"    {r['model']:16s} WER={wer} ({r['error'] or 'ok'})")
    return results


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def aggregate(results: list[dict], key_fn) -> dict:
    """Aggregate WER/CER/latency per model, grouped by key_fn(clip)."""
    groups: dict[str, dict[str, dict[str, list[float]]]] = {}
    for clip in results:
        group = key_fn(clip)
        for r in clip["benchmark"]["results"]:
            bucket = groups.setdefault(group, {}).setdefault(
                r["model"], {"wer": [], "cer": [], "latency": []}
            )
            if r["wer"] is not None:
                bucket["wer"].append(r["wer"])
                bucket["cer"].append(r["cer"])
            if r["latency_seconds"] is not None:
                bucket["latency"].append(r["latency_seconds"])
    return {
        group: {
            model: {
                "mean_wer": _mean(b["wer"]),
                "mean_cer": _mean(b["cer"]),
                "mean_latency": _mean(b["latency"]),
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

    def h1(self, text):
        self.set_font("Helvetica", "B", 16)
        self.multi_cell(0, 8, text)
        self.ln(2)

    def h2(self, text):
        self.set_font("Helvetica", "B", 12)
        self.multi_cell(0, 7, text)
        self.ln(1)

    def body(self, text):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def table(self, headers, rows, col_widths):
        self.set_font("Helvetica", "B", 9)
        for h, w in zip(headers, col_widths):
            self.cell(w, 7, h, border=1)
        self.ln()
        self.set_font("Helvetica", "", 9)
        for row in rows:
            # crude row-height handling: truncate long cells
            for value, w in zip(row, col_widths):
                text = str(value)
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

    pdf.h2("5. Per-clip transcripts")
    for clip in results:
        meta = clip["metadata"]
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(
            0, 5.5,
            f"{meta['filename']} | {meta['language_pair']} | {meta['accent_country']} | "
            f"{meta['device_type']} | {meta['noise_condition']}",
        )
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, f"Reference: {meta['reference_transcript']}")
        for r in clip["benchmark"]["results"]:
            if r["error"]:
                line = f"{r['model']}: ERROR - {r['error']}"
            else:
                line = (
                    f"{r['model']} (WER {fmt(r['wer'])}, CER {fmt(r['cer'])}, "
                    f"{fmt(r['latency_seconds'])}s): {r['transcript']}"
                )
            pdf.multi_cell(0, 5, line)
        pdf.ln(3)

    pdf.h2("6. Limitations and bias notes")
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
    rows = load_metadata()
    if not rows:
        print(
            "No audio clips found. Record clips into data/samples/ and register them "
            "in metadata.csv first (see data/samples/README.md)."
        )
        sys.exit(1)

    print(f"Running benchmark on {len(rows)} clip(s) across 3 models...\n")
    results = run_all(rows)

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
