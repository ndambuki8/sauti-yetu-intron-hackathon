"""Generate the comprehensive code-switch ASR benchmark report (PDF + raw JSON).

Covers all four challenge evaluation domains:

  Domain 1 – Linguistic & Core ASR Performance
      Overall WER/CER per model, WER by language pair/accent, switch-point WER.

  Domain 2 – Downstream Agentic Task Accuracy
      Intent recognition accuracy, slot-filling accuracy, entity error rate.
      Activated when expected_* columns are present in metadata.csv and --agentic
      is passed (Sahara telehealth extraction enabled).

  Domain 3 – Environmental & In-The-Wild Robustness
      Noise robustness: WER vs SNR sweep (30/20/10/5 dB) via --noise flag.
      Silence metrics (ratio, pause count, longest pause) per clip.

  Domain 4 – Infrastructure & Real-Time Performance
      RTF (Real-Time Factor) per model, latency distribution, offline simulation
      (local-models-only run) via --offline flag.

Usage (from the project root, venv active, INTRON_API_KEY in .env):

    python -m scripts.generate_benchmark_report                 # baseline
    python -m scripts.generate_benchmark_report --agentic       # + agentic scoring
    python -m scripts.generate_benchmark_report --noise         # + noise sweep (expensive)
    python -m scripts.generate_benchmark_report --offline       # + local-only pass
    python -m scripts.generate_benchmark_report --noise --offline --agentic  # full suite
    python -m scripts.generate_benchmark_report --rebuild-only  # rebuild PDF from JSON
"""

import csv
import json
import os
import platform
import re
import statistics
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from fpdf import FPDF

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.benchmark import (  # noqa: E402
    run_benchmark,
    run_noise_benchmark,
    run_offline_simulation,
)
from backend.config import PROJECT_ROOT, SAMPLES_DIR, SUPPORTED_LANGUAGES  # noqa: E402

REPORTS_DIR = PROJECT_ROOT / "reports" / "afrispeech"
MODELS = ["Intron Sahara", "OpenAI Whisper", "Meta MMS"]
LOCAL_MODELS = ["OpenAI Whisper", "Meta MMS"]
DEFAULT_SNR_LEVELS = [30.0, 20.0, 10.0, 5.0]

# Human-readable language_pair in metadata.csv → Intron app code
PAIR_TO_CODE = {name.lower(): code for code, name in SUPPORTED_LANGUAGES.items()}


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

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
    # Fall back to filename convention: afrispeech_<code>_N.wav
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


# ---------------------------------------------------------------------------
# Benchmark passes
# ---------------------------------------------------------------------------

def _agent_reference(row: dict) -> dict | None:
    """Build agent_reference from metadata if any expected_* field is set."""
    keys = ("expected_topic", "expected_urgency", "expected_department",
            "expected_slots", "expected_entities")
    if not any(row.get(k, "").strip() for k in keys):
        return None
    return {
        "expected_topic":      row.get("expected_topic", ""),
        "expected_urgency":    row.get("expected_urgency", ""),
        "expected_department": row.get("expected_department", ""),
        "expected_slots":      _json_field(row, "expected_slots", {}),
        "expected_entities":   _json_field(row, "expected_entities", []),
    }


def run_all(rows: list[dict], agentic: bool = False) -> list[dict]:
    results = []
    for i, row in enumerate(rows, 1):
        language_code = _language_code(row)
        print(
            f"[{i}/{len(rows)}] {row['filename']} "
            f"({row['language_pair']}, lang hint: {language_code})"
        )
        audio_bytes = (SAMPLES_DIR / row["filename"]).read_bytes()
        bench = run_benchmark(
            audio_bytes,
            filename=row["filename"],
            reference_transcript=row["reference_transcript"],
            language_code=language_code,
            switch_points=_json_field(row, "switch_points", []),
            agent_reference=_agent_reference(row),
            agentic=agentic,
        )
        results.append({"metadata": row, "benchmark": bench})
        for r in bench["results"]:
            wer = r["wer"] if r["wer"] is not None else "err"
            print(
                f"    {r['model']:16s} WER={wer} RTF={r.get('rtf', '-')} "
                f"({r['error'] or 'ok'})"
            )
    return results


def run_noise_pass(
    rows: list[dict],
    snr_levels: list[float],
    skip_api: bool = False,
) -> list[dict]:
    """Domain 3: run all clips through the noise sweep."""
    noise_results = []
    tag = "(local only)" if skip_api else "(all models)"
    for i, row in enumerate(rows, 1):
        language_code = _language_code(row)
        print(
            f"  noise [{i}/{len(rows)}] {row['filename']} "
            f"SNR={snr_levels} dB {tag}"
        )
        audio_bytes = (SAMPLES_DIR / row["filename"]).read_bytes()
        result = run_noise_benchmark(
            audio_bytes,
            filename=row["filename"],
            reference_transcript=row["reference_transcript"],
            language_code=language_code,
            snr_levels=snr_levels,
            skip_api=skip_api,
        )
        noise_results.append({"metadata": row, "noise": result})
    return noise_results


def run_offline_pass(rows: list[dict]) -> list[dict]:
    """Domain 4: local-only run to quantify offline penalty."""
    offline_results = []
    for i, row in enumerate(rows, 1):
        language_code = _language_code(row)
        print(f"  offline [{i}/{len(rows)}] {row['filename']}")
        audio_bytes = (SAMPLES_DIR / row["filename"]).read_bytes()
        result = run_offline_simulation(
            audio_bytes,
            filename=row["filename"],
            reference_transcript=row["reference_transcript"],
            language_code=language_code,
        )
        offline_results.append({"metadata": row, "offline": result})
    return offline_results


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_manifest(rows: list[dict], results: list[dict], flags: dict) -> dict:
    switch_annotated = sum(bool(_json_field(row, "switch_points", [])) for row in rows)
    downstream_annotated = sum(bool(_agent_reference(row)) for row in rows)
    return {
        "schema_version": "3.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": " ".join(sys.argv),
        "git_commit": _git_commit(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "intron_api_key_present": bool(os.getenv("INTRON_API_KEY")),
        "flags": flags,
        "models": MODELS,
        "clip_count": len(rows),
        "switch_point_annotated_clips": switch_annotated,
        "downstream_annotated_clips": downstream_annotated,
        "normalization": ["lowercase", "remove punctuation", "collapse whitespace", "strip"],
        "metrics": {
            "wer": "jiwer word error rate (normalized)",
            "cer": "jiwer character error rate (normalized)",
            "switch_point_wer": "mean WER in ±3-token window around each annotated language boundary",
            "rtf": "wall-clock latency / audio duration; <1.0 means faster than real-time",
            "intent_accuracy": "exact normalized match for expected_topic",
            "slot_accuracy": "mean exact normalized match over expected_slots",
            "entity_error_rate": "(missing gold entities + spurious predicted) / (gold + spurious)",
            "silence_ratio": "fraction of 20ms frames below -40 dBFS",
            "noise_wer_degradation": "WER(noisy) - WER(clean) at each SNR level",
        },
    }


def aggregate(results: list[dict], key_fn) -> dict:
    """Aggregate WER/CER/RTF/agentic/switch-point metrics."""
    groups: dict[str, dict[str, dict[str, list[float]]]] = {}
    for clip in results:
        group = key_fn(clip)
        for r in clip["benchmark"]["results"]:
            bucket = groups.setdefault(group, {}).setdefault(
                r["model"],
                {"wer": [], "cer": [], "latency": [], "rtf": [],
                 "switch_point_wer": [], "intent": [], "slot": [], "entity": []},
            )
            if r["wer"] is not None:
                bucket["wer"].append(r["wer"])
                bucket["cer"].append(r["cer"])
            if r.get("latency_seconds") is not None:
                bucket["latency"].append(r["latency_seconds"])
            if r.get("rtf") is not None:
                bucket["rtf"].append(r["rtf"])
            if r.get("switch_point", {}).get("wer") is not None:
                bucket["switch_point_wer"].append(r["switch_point"]["wer"])
            agent = r.get("agentic") or {}
            for metric, source in (
                ("intent", agent.get("intent_correct")),
                ("slot", agent.get("slot_accuracy")),
                ("entity", agent.get("entity_error_rate")),
            ):
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


def aggregate_noise(noise_results: list[dict], models_list: list[str]) -> dict:
    """Build {model: {snr_str: {mean_wer, mean_cer, mean_rtf, n}}} for charting."""
    buckets: dict[str, dict[str, dict[str, list]]] = {}
    for clip in noise_results:
        for snr_key, level_results in clip["noise"]["levels"].items():
            for r in level_results:
                m = r["model"]
                if m not in models_list:
                    continue
                bk = buckets.setdefault(m, {}).setdefault(
                    snr_key, {"wer": [], "cer": [], "rtf": []}
                )
                if r.get("wer") is not None:
                    bk["wer"].append(r["wer"])
                    bk["cer"].append(r["cer"])
                if r.get("rtf") is not None:
                    bk["rtf"].append(r["rtf"])
    return {
        model: {
            snr: {
                "mean_wer": _mean(v["wer"]),
                "mean_cer": _mean(v["cer"]),
                "mean_rtf": _mean(v["rtf"]),
                "n": len(v["wer"]),
            }
            for snr, v in snr_map.items()
        }
        for model, snr_map in buckets.items()
    }


def aggregate_offline(offline_results: list[dict]) -> dict:
    buckets: dict[str, dict[str, list]] = {}
    for clip in offline_results:
        for r in clip["offline"]["results"]:
            bk = buckets.setdefault(r["model"], {"wer": [], "cer": [], "latency": [], "rtf": []})
            if r.get("wer") is not None:
                bk["wer"].append(r["wer"])
                bk["cer"].append(r["cer"])
            if r.get("latency_seconds") is not None:
                bk["latency"].append(r["latency_seconds"])
            if r.get("rtf") is not None:
                bk["rtf"].append(r["rtf"])
    return {
        model: {
            "mean_wer": _mean(b["wer"]),
            "mean_cer": _mean(b["cer"]),
            "mean_latency": _mean(b["latency"]),
            "mean_rtf": _mean(b["rtf"]),
            "n": len(b["wer"]),
        }
        for model, b in buckets.items()
    }


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------

def _bar_chart(ax, labels, values, ylabel, title, color="#555555"):
    pairs = [(l, v) for l, v in zip(labels, values) if v is not None]
    if not pairs:
        return
    ax.bar([p[0] for p in pairs], [p[1] for p in pairs], color=color)
    ax.set_ylabel(ylabel)
    ax.set_title(title)


def make_charts(overall: dict, by_pair: dict) -> list[Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    paths = []

    # 1: Overall WER by model
    fig, ax = plt.subplots(figsize=(6, 3.2))
    models_in = [m for m in MODELS if m in overall.get("all", {})]
    wers = [overall["all"][m]["mean_wer"] for m in models_in]
    _bar_chart(ax, models_in, wers, "Mean WER (lower is better)", "Domain 1: Overall WER by model")
    fig.tight_layout()
    p = REPORTS_DIR / "chart_overall_wer.png"
    fig.savefig(p, dpi=150)
    paths.append(p)
    plt.close(fig)

    # 2: WER by language pair, grouped by model
    pairs = sorted(by_pair.keys())
    if pairs:
        fig, ax = plt.subplots(figsize=(9, 4))
        width = 0.8 / max(len(MODELS), 1)
        shades = ["#1a6b3c", "#e07b39", "#3a7bbf"]
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
        ax.set_xticklabels(pairs, rotation=30, ha="right", fontsize=7)
        ax.set_ylabel("Mean WER")
        ax.set_title("Domain 1: WER by language pair")
        ax.legend(fontsize=8)
        fig.tight_layout()
        p = REPORTS_DIR / "chart_wer_by_pair.png"
        fig.savefig(p, dpi=150)
        paths.append(p)
        plt.close(fig)

    # 3: RTF by model
    fig, ax = plt.subplots(figsize=(6, 3.2))
    rtfs = [overall["all"].get(m, {}).get("mean_rtf") for m in models_in]
    _bar_chart(ax, models_in, rtfs, "Mean RTF (lower = faster)", "Domain 4: Real-Time Factor by model", color="#2c6fad")
    ax.axhline(1.0, color="red", linestyle="--", linewidth=0.8, label="RTF=1 (real-time)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = REPORTS_DIR / "chart_rtf_by_model.png"
    fig.savefig(p, dpi=150)
    paths.append(p)
    plt.close(fig)

    return paths


def make_noise_charts(noise_agg: dict, snr_levels: list[float]) -> list[Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    paths = []

    snr_keys = [str(int(s)) for s in sorted(snr_levels, reverse=True)]
    colors = {"Intron Sahara": "#1a6b3c", "OpenAI Whisper": "#e07b39", "Meta MMS": "#3a7bbf"}

    # WER vs SNR line chart
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for model, snr_map in noise_agg.items():
        xs, ys = [], []
        for k in snr_keys:
            if snr_map.get(k, {}).get("mean_wer") is not None:
                xs.append(int(k))
                ys.append(snr_map[k]["mean_wer"])
        if xs:
            ax.plot(
                xs, ys, marker="o", label=model,
                color=colors.get(model, "#888888"),
            )
    ax.set_xlabel("SNR (dB)  →  lower = noisier")
    ax.set_ylabel("Mean WER")
    ax.set_title("Domain 3: WER degradation vs noise level")
    ax.invert_xaxis()
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = REPORTS_DIR / "chart_noise_wer_vs_snr.png"
    fig.savefig(p, dpi=150)
    paths.append(p)
    plt.close(fig)

    # CER vs SNR
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for model, snr_map in noise_agg.items():
        xs, ys = [], []
        for k in snr_keys:
            if snr_map.get(k, {}).get("mean_cer") is not None:
                xs.append(int(k))
                ys.append(snr_map[k]["mean_cer"])
        if xs:
            ax.plot(xs, ys, marker="s", label=model, color=colors.get(model, "#888888"))
    ax.set_xlabel("SNR (dB)  →  lower = noisier")
    ax.set_ylabel("Mean CER")
    ax.set_title("Domain 3: CER degradation vs noise level")
    ax.invert_xaxis()
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = REPORTS_DIR / "chart_noise_cer_vs_snr.png"
    fig.savefig(p, dpi=150)
    paths.append(p)
    plt.close(fig)

    return paths


def make_offline_chart(offline_agg: dict, online_agg: dict) -> list[Path]:
    """Compare online vs offline WER per local model."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    local_models = [m for m in LOCAL_MODELS if m in offline_agg]
    if not local_models:
        return paths

    fig, ax = plt.subplots(figsize=(6, 3.4))
    x = range(len(local_models))
    offline_wers = [offline_agg[m]["mean_wer"] for m in local_models]
    online_wers  = [online_agg.get("all", {}).get(m, {}).get("mean_wer") for m in local_models]

    width = 0.35
    ax.bar([xi - width / 2 for xi in x], online_wers,  width=width, label="Online  (clean)", color="#1a6b3c")
    ax.bar([xi + width / 2 for xi in x], offline_wers, width=width, label="Offline (clean)", color="#aaaaaa")
    ax.set_xticks(list(x))
    ax.set_xticklabels(local_models)
    ax.set_ylabel("Mean WER")
    ax.set_title("Domain 4: Online vs Offline local model accuracy")
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = REPORTS_DIR / "chart_offline_comparison.png"
    fig.savefig(p, dpi=150)
    paths.append(p)
    plt.close(fig)
    return paths


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------

def _latin1(text: str) -> str:
    """Helvetica (core font) only supports latin-1; replace anything outside."""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def fmt(v, precision: int = 4) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{precision}f}"
    return str(v)


class ReportPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(130)
        self.cell(0, 6, "Sauti Yetu - Code-Switch ASR & Agentic Triage Benchmark Report", align="R")
        self.ln(10)
        self.set_text_color(0)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(130)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")

    def para(self, text):
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

    def h3(self, text):
        self.set_font("Helvetica", "BI", 10)
        self.set_x(self.l_margin)
        self.multi_cell(0, 6, _latin1(text), new_x="LMARGIN", new_y="NEXT")

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
            for value, w in zip(row, col_widths):
                text = _latin1(str(value))
                max_chars = int(w / 1.9)
                if len(text) > max_chars:
                    text = text[: max_chars - 3] + "..."
                self.cell(w, 7, text, border=1)
            self.ln()
        self.ln(3)

    def image_if_exists(self, path: Path, w: int = 160):
        if path and path.exists():
            self.set_x(self.l_margin)
            self.image(str(path), w=w)
            self.ln(4)


def _domain1_section(pdf: ReportPDF, results: list[dict], overall: dict,
                     by_pair: dict, by_noise: dict, chart_paths: list[Path]):
    pdf.h2("1. Domain 1 - Linguistic & Core ASR Performance")
    pdf.body(
        "Three speech-to-text models were benchmarked on identical audio inputs: "
        "Intron Sahara (commercial API, African-accent optimized), OpenAI Whisper "
        "(open-source, local), and Meta MMS mms-1b-all (open-source, local). "
        "All hypotheses and references were normalized identically: lowercased, "
        "punctuation removed, whitespace collapsed (jiwer). CER is reported alongside "
        "WER because it is fairer for agglutinative languages (Swahili, Kinyarwanda)."
    )

    pdf.h3("1a. Overall results")
    headers = ["Model", "Mean WER", "Mean CER", "Mean latency (s)", "n clips"]
    widths  = [55, 28, 28, 38, 16]
    rows = [
        [m,
         fmt(s.get("mean_wer")),
         fmt(s.get("mean_cer")),
         fmt(s.get("mean_latency"), 2),
         str(s.get("n", "-"))]
        for m, s in overall.get("all", {}).items()
    ]
    pdf.table(headers, rows, widths)
    for p in chart_paths[:2]:
        pdf.image_if_exists(p)

    pdf.h3("1b. Results by language pair / accent")
    headers_lp = ["Model", "WER", "CER", "Latency", "n"]
    widths_lp  = [55, 28, 28, 28, 14]
    for pair, models_data in sorted(by_pair.items()):
        pdf.body(f"Language pair: {pair}")
        rows_lp = [
            [m, fmt(s.get("mean_wer")), fmt(s.get("mean_cer")),
             fmt(s.get("mean_latency"), 2), str(s.get("n", "-"))]
            for m, s in models_data.items()
        ]
        pdf.table(headers_lp, rows_lp, widths_lp)

    pdf.h3("1c. Switch-Point Word Error Rate")
    pdf.body(
        "Switch-point WER is calculated in a +-3-token window centred on each annotated "
        "language boundary (token_index in metadata switch_points column). SOTA models "
        "frequently degrade at code-switch boundaries; this metric isolates that effect.\n\n"
        "NOTE: The current sample set is drawn from AfriSpeech-200 (English read aloud "
        "with African accents). These clips do not contain true intra-sentence code-switches, "
        "so switch-point WER is not yet reported. To enable this metric, record or source "
        "code-switched clips and annotate each switch in the metadata switch_points column as: "
        '[{"token_index": N, "from_language": "sw", "to_language": "en"}]'
    )
    # Print any clips that do have annotated switch points
    switch_clips = [
        c for c in results if c["benchmark"].get("switch_points")
    ]
    if switch_clips:
        pdf.h3("Switch-point annotated clips")
        for clip in switch_clips:
            meta = clip["metadata"]
            pdf.para(f"{meta['filename']} — {len(clip['benchmark']['switch_points'])} boundary/ies")
            for r in clip["benchmark"]["results"]:
                sp = r.get("switch_point", {})
                if sp.get("wer") is not None:
                    pdf.para(f"  {r['model']}: switch-point WER = {fmt(sp['wer'])}")


def _domain2_section(pdf: ReportPDF, results: list[dict], overall: dict):
    pdf.h2("2. Domain 2 - Downstream Agentic Task Accuracy")
    pdf.body(
        "When expected_entities (and optionally expected_topic/urgency/department/slots) are "
        "provided in metadata.csv and the pipeline is run with --agentic, the Sahara telehealth "
        "extraction feeds the triage layer. Three metrics are reported:\n"
        "  - Intent accuracy: exact match on expected_topic\n"
        "  - Slot accuracy: mean exact match over expected_slots fields\n"
        "  - Entity Error Rate (EER): (missing gold entities + spurious predicted) / (gold + spurious)\n\n"
        "Entity annotations cover 14 of the 27 clips (all clinical domain clips). "
        "Entities are the key medical terms that should survive ASR and NLP extraction."
    )

    # Aggregate agentic stats from overall
    any_agentic = False
    headers = ["Model", "Intent Acc.", "Slot Acc.", "Entity EER", "n"]
    widths  = [55, 32, 32, 32, 14]
    rows = []
    for m, s in overall.get("all", {}).items():
        if any(s.get(k) is not None for k in ("intent_accuracy", "slot_accuracy", "entity_error_rate")):
            any_agentic = True
            rows.append([
                m,
                fmt(s.get("intent_accuracy")),
                fmt(s.get("slot_accuracy")),
                fmt(s.get("entity_error_rate")),
                str(s.get("n", "-")),
            ])
    if any_agentic:
        pdf.table(headers, rows, widths)
    else:
        pdf.body(
            "Re-run with --agentic to activate Sahara telehealth extraction and populate "
            "these metrics. Local models also receive triage scoring (transcript-only path) "
            "when expected_* metadata columns are present."
        )

    # Per-clip agentic detail for any annotated clips
    agentic_clips = [c for c in results if any(
        r.get("agentic") for r in c["benchmark"]["results"]
    )]
    if agentic_clips:
        pdf.h3("Per-clip entity extraction detail")
        for clip in agentic_clips[:10]:  # cap to avoid runaway PDF length
            meta = clip["metadata"]
            pdf.para(f"{meta['filename']}:")
            for r in clip["benchmark"]["results"]:
                ag = r.get("agentic")
                if ag:
                    eer = fmt(ag.get("entity_error_rate"))
                    missing = ", ".join(ag.get("missing_entities", [])) or "none"
                    spurious = ", ".join(ag.get("spurious_entities", [])) or "none"
                    pdf.para(
                        f"  {r['model']}: EER={eer} | "
                        f"missing=[{missing}] | spurious=[{spurious}]"
                    )


def _domain3_section(pdf: ReportPDF, noise_agg: dict | None,
                     noise_results: list[dict] | None,
                     noise_chart_paths: list[Path],
                     snr_levels: list[float]):
    pdf.h2("3. Domain 3 - Environmental & In-The-Wild Robustness")
    pdf.body(
        "Real-world African deployments face challenging acoustic environments: "
        "street noise, market chatter, overlapping speakers, and poor microphone quality. "
        "This domain benchmarks resilience via two lenses:\n"
        "  a) Noise robustness: Gaussian noise added at SNR 30/20/10/5 dB simulates "
        "     increasing background noise. WER degradation from clean baseline measures "
        "     model robustness.\n"
        "  b) Silence & pause analysis: fraction of audio that is silent, number of "
        "     distinct pause segments, and longest continuous pause. Graceful handling "
        "     of natural conversational gaps is critical for voice bots."
    )

    if noise_agg is None:
        pdf.body(
            "Noise robustness data not collected in this run. "
            "Re-run with --noise to enable the SNR sweep (adds ~4x model invocations per clip). "
            "Use --noise --offline to sweep only local models and avoid API costs."
        )
        return

    # Noise WER tables per model
    pdf.h3("3a. WER degradation across SNR levels (mean over all clips)")
    snr_cols = [str(int(s)) for s in sorted(snr_levels, reverse=True)]
    headers = ["Model"] + [f"WER@{s}dB" for s in snr_cols]
    widths  = [50] + [28] * len(snr_cols)
    rows = []
    for model in (MODELS if noise_agg else []):
        snr_map = noise_agg.get(model, {})
        row_vals = [model] + [fmt(snr_map.get(k, {}).get("mean_wer")) for k in snr_cols]
        if model in noise_agg:
            rows.append(row_vals)
    if rows:
        pdf.table(headers, rows, widths)
    for p in noise_chart_paths:
        pdf.image_if_exists(p)

    # Silence metrics summary (from clean audio)
    if noise_results:
        pdf.h3("3b. Silence & pause structure (clean audio)")
        pdf.body(
            "Silence ratio is the proportion of 20ms frames below -40 dBFS. "
            "A high ratio (>0.4) may indicate long pauses or non-speech content."
        )
        headers_s = ["File", "Language", "Silence ratio", "Pauses", "Longest pause (s)"]
        widths_s  = [40, 28, 28, 18, 30]
        sil_rows = []
        for clip in noise_results:
            sm = clip["noise"].get("silence_metrics", {})
            sil_rows.append([
                clip["metadata"]["filename"],
                clip["metadata"]["language_pair"],
                fmt(sm.get("silence_ratio")),
                str(sm.get("pause_count", "-")),
                fmt(sm.get("longest_pause_seconds"), 3),
            ])
        pdf.table(headers_s, sil_rows, widths_s)


def _domain4_section(pdf: ReportPDF, overall: dict, offline_agg: dict | None,
                     offline_chart_paths: list[Path], rtf_chart: Path | None):
    pdf.h2("4. Domain 4 - Infrastructure & Real-Time Performance")
    pdf.body(
        "RTF (Real-Time Factor) = wall-clock latency / audio duration. "
        "RTF < 1.0 means the model processes faster than real time, a requirement "
        "for live voice bots and interactive customer support.\n\n"
        "Note: Intron Sahara latency includes network round-trips to the cloud API. "
        "Local model latency depends on the inference machine's hardware. "
        "All measurements were taken on the same machine in this run."
    )

    # RTF summary table
    pdf.h3("4a. Real-Time Factor by model")
    headers = ["Model", "Mean RTF", "Mean latency (s)", "n clips"]
    widths  = [55, 30, 38, 16]
    rows = [
        [m,
         fmt(s.get("mean_rtf")),
         fmt(s.get("mean_latency"), 2),
         str(s.get("n", "-"))]
        for m, s in overall.get("all", {}).items()
    ]
    pdf.table(headers, rows, widths)
    pdf.image_if_exists(rtf_chart)

    # Offline section
    pdf.h3("4b. Offline / Low-Connectivity Simulation")
    pdf.body(
        "Sahara v2 supports offline operation — a key differentiator for remote or "
        "low-connectivity African deployments. The offline simulation runs ONLY the "
        "two local models (Whisper, MMS) to measure what accuracy is achievable without "
        "any API call. The gap between Sahara WER and best local WER is the 'offline penalty'."
    )

    if offline_agg is None:
        pdf.body("Re-run with --offline to collect offline simulation data.")
        return

    headers_o = ["Model", "Mean WER", "Mean CER", "Mean RTF", "n clips"]
    widths_o  = [55, 28, 28, 28, 16]
    rows_o = [
        [m,
         fmt(s.get("mean_wer")),
         fmt(s.get("mean_cer")),
         fmt(s.get("mean_rtf")),
         str(s.get("n", "-"))]
        for m, s in offline_agg.items()
    ]
    pdf.table(headers_o, rows_o, widths_o)

    # Compute offline penalty vs Sahara
    sahara_wer = overall.get("all", {}).get("Intron Sahara", {}).get("mean_wer")
    if sahara_wer is not None and offline_agg:
        best_local_wer = min(
            (s["mean_wer"] for s in offline_agg.values() if s.get("mean_wer") is not None),
            default=None,
        )
        if best_local_wer is not None:
            penalty = round(best_local_wer - sahara_wer, 4)
            pdf.body(
                f"Offline penalty (best local WER - Sahara WER): "
                f"{fmt(best_local_wer)} - {fmt(sahara_wer)} = {fmt(penalty)} WER points. "
                + ("This is the accuracy cost of operating without the Sahara API."
                   if penalty > 0 else
                   "Local models outperform Sahara on this clip set.")
            )

    for p in offline_chart_paths:
        pdf.image_if_exists(p)


def build_pdf(
    results: list[dict],
    overall: dict,
    by_pair: dict,
    by_noise: dict,
    chart_paths: list[Path],
    noise_agg: dict | None,
    noise_results: list[dict] | None,
    noise_chart_paths: list[Path],
    offline_agg: dict | None,
    offline_chart_paths: list[Path],
    snr_levels: list[float],
) -> Path:
    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Title
    pdf.h1("Code-Switch ASR & Agentic Triage Benchmark Report")
    pdf.body(
        f"Project: Sauti Yetu - agentic voice triage for code-switching patients\n"
        f"Challenge: Sahara CodeSwitch Africa Challenge 2026 (MLC Africa x Intron)\n"
        f"Date: {date.today().isoformat()} | Clips evaluated: {len(results)}\n"
        f"Models: Intron Sahara v2 | OpenAI Whisper | Meta MMS mms-1b-all"
    )

    # Methodology
    pdf.h2("0. Methodology & Fairness Controls")
    pdf.body(
        "Fairness controls: every model received the identical audio file, converted to "
        "16 kHz mono WAV via ffmpeg. Every model received the same language hint "
        "(Sahara: use_language_asr_input; Whisper: language parameter or auto-detect; "
        "MMS: the matching language adapter). Hypotheses and references were normalized "
        "identically before scoring: lowercase, punctuation removed, whitespace collapsed (jiwer). "
        "Metrics: WER (word error rate), CER (character error rate — fairer for agglutinative "
        "languages), RTF (real-time factor), switch-point WER, intent accuracy, slot accuracy, "
        "entity error rate. "
        "Noise benchmarks use synthetic Gaussian noise with a fixed random seed (42) for "
        "reproducibility. Raw per-clip outputs are in reports/results.json."
    )

    # All four domains
    rtf_chart = next((p for p in chart_paths if "rtf" in p.name), None)
    domain1_charts = [p for p in chart_paths if "rtf" not in p.name]

    _domain1_section(pdf, results, overall, by_pair, by_noise, domain1_charts)
    pdf.add_page()
    _domain2_section(pdf, results, overall)
    pdf.add_page()
    _domain3_section(pdf, noise_agg, noise_results, noise_chart_paths, snr_levels)
    pdf.add_page()
    _domain4_section(pdf, overall, offline_agg, offline_chart_paths, rtf_chart)

    # Per-clip transcripts
    pdf.add_page()
    pdf.h2("5. Per-Clip Transcripts")
    for clip in results:
        meta = clip["metadata"]
        pdf.set_font("Helvetica", "B", 10)
        pdf.para(
            f"{meta['filename']} | {meta['language_pair']} | "
            f"{meta['accent_country']} | {meta['noise_condition']}"
        )
        pdf.set_font("Helvetica", "", 9)
        pdf.para(f"Reference: {meta['reference_transcript']}")
        for r in clip["benchmark"]["results"]:
            if r["error"]:
                line = f"{r['model']}: ERROR - {r['error']}"
            else:
                line = (
                    f"{r['model']} (WER {fmt(r['wer'])}, CER {fmt(r['cer'])}, "
                    f"RTF {fmt(r.get('rtf'))}, {fmt(r['latency_seconds'], 2)}s): "
                    f"{r['transcript']}"
                )
            pdf.para(line)
            sp = r.get("switch_point", {})
            if sp.get("wer") is not None:
                pdf.para(
                    f"  Switch-point WER: {fmt(sp['wer'])} "
                    f"({sp['count']} annotated boundaries)"
                )
            ag = r.get("agentic")
            if ag:
                pdf.para(
                    f"  Agentic: intent={fmt(ag.get('intent_correct'))}, "
                    f"slot acc={fmt(ag.get('slot_accuracy'))}, "
                    f"entity EER={fmt(ag.get('entity_error_rate'))}"
                )
        pdf.ln(2)

    # Limitations
    pdf.add_page()
    pdf.h2("6. Limitations & Bias Notes")
    pdf.body(
        "1. SAMPLE SET: Clips are from AfriSpeech-200 — English read aloud by African-accented "
        "speakers. These are NOT true code-switched utterances. For switch-point WER and genuine "
        "code-switch evaluation, record or source intra-sentence language-switching clips and "
        "annotate the switch_points column in metadata.csv.\n\n"
        "2. SAMPLE SIZE: 27 clips, 3 per accent group. Results indicate trends rather than "
        "statistically significant differences. A submission-quality benchmark should use at "
        "least 50-100 clips per language pair.\n\n"
        "3. NOISE SIMULATION: Gaussian white noise does not perfectly replicate real-world "
        "interference (market chatter, road noise). For production benchmarking, mix real "
        "noise recordings at controlled SNR levels using tools like pyroomacoustics.\n\n"
        "4. LATENCY: Sahara latency includes network round-trip; local model latency is "
        "hardware-dependent. Both are measured on the same machine but are not directly "
        "comparable. GPU acceleration would dramatically reduce local model RTF.\n\n"
        "5. AGENTIC SCORING: The triage layer is rule-based and keyword-matched. Clinical "
        "clips from AfriSpeech-200 are medical documentation read aloud, not patient "
        "complaints, so intent/topic matching may not reflect real deployment performance.\n\n"
        "6. ENTITY ANNOTATIONS: Expected entities in metadata.csv were hand-labelled from "
        "the reference transcripts. Models are scored on whether extracted entities match "
        "these labels; labelling conventions affect the score."
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "benchmark_report.pdf"
    pdf.output(str(out_path))
    return out_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    results_path = REPORTS_DIR / "results.json"

    # ---- Flags ----
    rebuild_only = "--rebuild-only" in sys.argv
    agentic      = "--agentic"      in sys.argv
    noise_mode   = "--noise"        in sys.argv
    offline_mode = "--offline"      in sys.argv
    noise_api    = "--noise-local"  not in sys.argv  # default: include API in noise sweep

    snr_levels = DEFAULT_SNR_LEVELS

    if rebuild_only:
        if not results_path.exists():
            print(f"No saved results at {results_path}; run without --rebuild-only first.")
            sys.exit(1)
        with open(results_path, encoding="utf-8") as fh:
            saved = json.load(fh)
        results      = saved["clips"]
        overall      = saved["overall"]
        by_pair      = saved["by_language_pair"]
        by_noise     = saved["by_noise_condition"]
        noise_agg    = saved.get("noise_robustness", {}).get("aggregated")
        noise_results = saved.get("noise_robustness", {}).get("clips")
        offline_agg  = saved.get("offline_simulation", {}).get("aggregated")
        offline_results = saved.get("offline_simulation", {}).get("clips", [])
        print(f"Rebuilding report from {results_path} ({len(results)} clips)...")
        charts  = make_charts(overall, by_pair)
        n_charts = make_noise_charts(noise_agg, snr_levels) if noise_agg else []
        o_charts = make_offline_chart(offline_agg, overall) if offline_agg else []
        pdf_path = build_pdf(
            results, overall, by_pair, by_noise, charts,
            noise_agg, noise_results, n_charts,
            offline_agg, o_charts, snr_levels,
        )
        print(f"Report written to {pdf_path}")
        return

    rows = load_metadata()
    if not rows:
        print(
            "No audio clips found. Record clips into data/samples/ and register them "
            "in metadata.csv first (see data/samples/README.md)."
        )
        sys.exit(1)

    print(f"\nRunning benchmark on {len(rows)} clip(s) across 3 models...\n")
    print(f"  --agentic   : {'yes' if agentic else 'no (pass --agentic to enable)'}")
    print(f"  --noise     : {'yes' if noise_mode else 'no (pass --noise to enable SNR sweep)'}")
    print(f"  --offline   : {'yes' if offline_mode else 'no (pass --offline to enable local-only pass)'}")
    print()

    # Domain 1 + 2: standard three-model run
    results  = run_all(rows, agentic=agentic)
    manifest = build_manifest(rows, results, {"agentic": agentic, "noise": noise_mode, "offline": offline_mode})
    overall  = aggregate(results, lambda c: "all")
    by_pair  = aggregate(results, lambda c: c["metadata"]["language_pair"])
    by_noise = aggregate(results, lambda c: c["metadata"]["noise_condition"])

    # Domain 3: noise sweep (optional)
    noise_results: list[dict] | None = None
    noise_agg: dict | None = None
    if noise_mode:
        print(f"\nDomain 3: noise sweep at SNR {snr_levels} dB "
              f"({'all models' if noise_api else 'local only'})...")
        noise_results = run_noise_pass(rows, snr_levels, skip_api=not noise_api)
        noise_agg = aggregate_noise(
            noise_results, MODELS if noise_api else LOCAL_MODELS
        )

    # Domain 4: offline simulation (optional)
    offline_results: list[dict] | None = None
    offline_agg: dict | None = None
    if offline_mode:
        print("\nDomain 4: offline simulation (local models only)...")
        offline_results = run_offline_pass(rows)
        offline_agg = aggregate_offline(offline_results)

    # Persist all results to JSON
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_payload: dict = {
        "manifest": manifest,
        "overall": overall,
        "by_language_pair": by_pair,
        "by_noise_condition": by_noise,
        "clips": results,
    }
    if noise_results is not None:
        json_payload["noise_robustness"] = {
            "aggregated": noise_agg,
            "snr_levels_db": snr_levels,
            "clips": noise_results,
        }
    if offline_results is not None:
        json_payload["offline_simulation"] = {
            "aggregated": offline_agg,
            "clips": offline_results,
        }

    with open(results_path, "w", encoding="utf-8") as fh:
        json.dump(json_payload, fh, ensure_ascii=False, indent=2)
    print(f"\nRaw results written to {results_path}")

    # Charts + PDF
    charts  = make_charts(overall, by_pair)
    n_charts = make_noise_charts(noise_agg, snr_levels) if noise_agg else []
    o_charts = make_offline_chart(offline_agg, overall) if offline_agg else []

    pdf_path = build_pdf(
        results, overall, by_pair, by_noise, charts,
        noise_agg, noise_results, n_charts,
        offline_agg, o_charts, snr_levels,
    )
    print(f"Report written to {pdf_path}")


if __name__ == "__main__":
    main()
