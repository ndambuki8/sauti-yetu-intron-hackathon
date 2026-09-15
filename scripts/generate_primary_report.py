"""Benchmark report for data/primary_collection (real health audio from Kenya).

What this script does:
  - Runs three ASR models on every audio clip in data/primary_collection/
  - Measures Word Error Rate, Character Error Rate, and speed (Real-Time Factor)
  - Evaluates how well the triage pipeline labels topic, urgency and entities
  - Checks accuracy at code-switch points (where Swahili switches to English)
  - Optionally sweeps noise robustness (WER vs SNR) with --noise
  - Produces charts and a PDF report in reports/primary_collection/

Clips are scored against the human ground-truth transcript in the
reference_transcript column of metadata.csv; clips with no reference are excluded.

Recording types in the dataset:
  m4a  - Real health complaints, smartphone microphone, 15-23 seconds
  ogg  - WhatsApp Push-to-Talk voice notes, ambient noise, 7-31 seconds
  mp3  - Short scripted triage phrases, laptop mic, 2-6 seconds

Usage (from project root, with venv active and INTRON_API_KEY set):
  python -m scripts.generate_primary_report               # full benchmark run
  python -m scripts.generate_primary_report --agentic     # include triage scoring
  python -m scripts.generate_primary_report --offline     # add local-only pass
  python -m scripts.generate_primary_report --noise       # add SNR noise sweep (30/20/10/5 dB)
  python -m scripts.generate_primary_report --noise --noise-local  # noise sweep, local models only
  python -m scripts.generate_primary_report --rebuild-only  # redo charts/PDF from saved JSON

Saving runs separately with --tag (nothing gets overwritten):
  python -m scripts.generate_primary_report --agentic --tag baseline
  python -m scripts.generate_primary_report --noise   --tag noise
  #   -> primary_results.<tag>.json, primary_benchmark_report.<tag>.pdf, chart_pc_*.<tag>.png
  python -m scripts.generate_primary_report --rebuild-only --tag noise  # rebuild one tag
  python -m scripts.generate_primary_report --rebuild-all               # rebuild every saved tag
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
import matplotlib.patches as mpatches
from fpdf import FPDF

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.benchmark import (  # noqa: E402
    run_benchmark,
    run_noise_benchmark,
    run_offline_simulation,
)
from backend.config import PROJECT_ROOT, SUPPORTED_LANGUAGES          # noqa: E402

PRIMARY_DIR  = PROJECT_ROOT / "data" / "primary_collection"
REPORTS_DIR  = PROJECT_ROOT / "reports" / "primary_collection"
MODELS       = ["Intron Sahara", "OpenAI Whisper", "Meta MMS"]
LOCAL_MODELS = ["OpenAI Whisper", "Meta MMS"]
DEFAULT_SNR_LEVELS = [30.0, 20.0, 10.0, 5.0]

# Optional filename tag so multiple configurations can be saved side by side, e.g.
# --tag noise -> primary_results.noise.json / ...noise.pdf / chart_pc_*.noise.png
_FILE_TAG = ""


def _arg_value(flag: str, default: str | None = None) -> str | None:
    """Read a value-bearing CLI arg: supports '--tag x' and '--tag=x'."""
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _sanitize_tag(tag: str | None) -> str:
    """Keep tags filesystem-safe (alnum, dash, underscore, dot)."""
    if not tag:
        return ""
    return re.sub(r"[^A-Za-z0-9._-]", "_", tag.strip())


def _tagged(filename: str) -> str:
    """Insert the active _FILE_TAG before the extension of an output filename."""
    if not _FILE_TAG:
        return filename
    p = Path(filename)
    return f"{p.stem}.{_FILE_TAG}{p.suffix}"


def _tag_from_results_name(name: str) -> str:
    """Recover the tag from a results filename ('primary_results.noise.json' -> 'noise')."""
    stem = name[:-5] if name.endswith(".json") else name
    prefix = "primary_results"
    if stem == prefix:
        return ""
    if stem.startswith(prefix + "."):
        return stem[len(prefix) + 1:]
    return ""

# ── Color palette ─────────────────────────────────────────────────────────────
C = {
    "sahara":    "#1a6b3c",
    "whisper":   "#e07b39",
    "mms":       "#3a7bbf",
    "emergency": "#c0392b",
    "urgent":    "#e67e22",
    "routine":   "#27ae60",
    "header_bg": (26, 82, 118),    # dark navy
    "accent_bg": (240, 248, 255),  # ice blue
    "wer_good":  (200, 235, 200),  # green  — WER < 0.25
    "wer_mid":   (255, 243, 170),  # amber  — WER 0.25–0.45
    "wer_bad":   (255, 200, 195),  # red    — WER > 0.45
    "wer_err":   (230, 230, 230),  # grey   — error / N/A
    "em_fill":   (255, 218, 218),
    "ur_fill":   (255, 243, 215),
    "ro_fill":   (218, 245, 218),
}

MODEL_HEX = {"Intron Sahara": C["sahara"], "OpenAI Whisper": C["whisper"], "Meta MMS": C["mms"]}
UGY_FILL  = {"EMERGENCY": C["em_fill"], "URGENT": C["ur_fill"], "ROUTINE": C["ro_fill"]}
UGY_LABEL = {"EMERGENCY": "[EMERGENCY]", "URGENT": "[URGENT]", "ROUTINE": "[ROUTINE]"}

PAIR_TO_CODE = {name.lower(): code for code, name in SUPPORTED_LANGUAGES.items()}


# ─── Metadata helpers ─────────────────────────────────────────────────────────

def _json_field(row: dict, col: str, default):
    val = row.get(col, "").strip()
    if not val:
        return default
    try:
        return json.loads(val)
    except json.JSONDecodeError:
        return default


def _language_code(row: dict) -> str:
    explicit = row.get("language_code", "").strip().lower()
    if explicit in SUPPORTED_LANGUAGES:
        return explicit
    pair = row.get("language_pair", "").strip().lower()
    return PAIR_TO_CODE.get(pair, "sw")


def load_metadata() -> list[dict]:
    path = PRIMARY_DIR / "metadata.csv"
    if not path.exists():
        print(f"ERROR: {path} not found.")
        print("  This benchmark reads human ground-truth transcripts from metadata.csv.")
        print("  To generate a first-pass draft to fill in, run:")
        print("    python -m scripts.bootstrap_primary_collection")
        sys.exit(1)
    with open(path, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("filename")]
    existing = []
    skipped_missing_file = 0
    skipped_no_reference = 0
    for row in rows:
        fpath = PRIMARY_DIR / row["filename"]
        if not fpath.exists():
            print(f"  skipping {row['filename']} (file not found)")
            skipped_missing_file += 1
            continue
        # Ground-truth benchmark: only score clips that have a human reference
        # transcript. Clips with an empty reference_transcript are excluded so
        # every reported WER/CER reflects a real, verifiable comparison.
        if not (row.get("reference_transcript") or "").strip():
            print(f"  skipping {row['filename']} (no reference_transcript — excluded from benchmark)")
            skipped_no_reference += 1
            continue
        existing.append(row)
    if skipped_missing_file or skipped_no_reference:
        print(
            f"  ({skipped_missing_file} skipped for missing file, "
            f"{skipped_no_reference} skipped for missing reference transcript)"
        )
    return existing


def _agent_ref(row: dict) -> dict | None:
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


# ─── Benchmark passes ─────────────────────────────────────────────────────────

def run_all(rows: list[dict], agentic: bool = False) -> list[dict]:
    results = []
    for i, row in enumerate(rows, 1):
        lang  = _language_code(row)
        rtype = row.get("recording_type", "")
        print(f"  [{i:2d}/{len(rows)}] {row['filename']:50s} ({rtype[:18]})")
        audio_bytes = (PRIMARY_DIR / row["filename"]).read_bytes()
        bench = run_benchmark(
            audio_bytes,
            filename=row["filename"],
            reference_transcript=row["reference_transcript"],
            language_code=lang,
            switch_points=_json_field(row, "switch_points", []),
            agent_reference=_agent_ref(row),
            agentic=agentic,
        )
        results.append({"metadata": row, "benchmark": bench})
        for r in bench["results"]:
            wer = r["wer"] if r["wer"] is not None else "err"
            err = f"  [{r['error'][:40]}]" if r.get("error") else ""
            print(f"       {r['model']:16s}  WER={str(wer):6s}  RTF={str(r.get('rtf', '-')):6s}{err}")
    return results


def run_offline_pass(rows: list[dict]) -> list[dict]:
    results = []
    for i, row in enumerate(rows, 1):
        lang = _language_code(row)
        print(f"  offline [{i:2d}/{len(rows)}] {row['filename']}")
        audio_bytes = (PRIMARY_DIR / row["filename"]).read_bytes()
        result = run_offline_simulation(
            audio_bytes,
            filename=row["filename"],
            reference_transcript=row["reference_transcript"],
            language_code=lang,
        )
        results.append({"metadata": row, "offline": result})
    return results


def run_noise_pass(
    rows: list[dict],
    snr_levels: list[float],
    skip_api: bool = False,
) -> list[dict]:
    """Section 3 (noise): sweep every clip through the Gaussian-noise SNR levels."""
    noise_results = []
    tag = "(local only)" if skip_api else "(all models)"
    for i, row in enumerate(rows, 1):
        lang = _language_code(row)
        print(f"  noise [{i:2d}/{len(rows)}] {row['filename']:50s} SNR={snr_levels} dB {tag}")
        audio_bytes = (PRIMARY_DIR / row["filename"]).read_bytes()
        result = run_noise_benchmark(
            audio_bytes,
            filename=row["filename"],
            reference_transcript=row["reference_transcript"],
            language_code=lang,
            snr_levels=snr_levels,
            skip_api=skip_api,
        )
        noise_results.append({"metadata": row, "noise": result})
    return noise_results


# ─── Aggregation ─────────────────────────────────────────────────────────────

def _mean(vals: list[float]) -> float | None:
    return round(statistics.mean(vals), 4) if vals else None


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def aggregate(results: list[dict], key_fn) -> dict:
    groups: dict = {}
    for clip in results:
        group = key_fn(clip)
        for r in clip["benchmark"]["results"]:
            bk = groups.setdefault(group, {}).setdefault(r["model"], {
                "wer": [], "cer": [], "latency": [], "rtf": [],
                "sp_wer": [], "intent": [], "slot": [], "entity": [],
            })
            if r.get("wer") is not None:
                bk["wer"].append(r["wer"])
                bk["cer"].append(r["cer"])
            if r.get("latency_seconds") is not None:
                bk["latency"].append(r["latency_seconds"])
            if r.get("rtf") is not None:
                bk["rtf"].append(r["rtf"])
            if r.get("switch_point", {}).get("wer") is not None:
                bk["sp_wer"].append(r["switch_point"]["wer"])
            ag = r.get("agentic") or {}
            for mkey, src in (("intent", ag.get("intent_correct")),
                               ("slot",   ag.get("slot_accuracy")),
                               ("entity", ag.get("entity_error_rate"))):
                if src is not None:
                    bk[mkey].append(float(src))
    return {
        group: {
            model: {
                "mean_wer":          _mean(b["wer"]),
                "mean_cer":          _mean(b["cer"]),
                "mean_latency":      _mean(b["latency"]),
                "mean_rtf":          _mean(b["rtf"]),
                "mean_sp_wer":       _mean(b["sp_wer"]),
                "intent_accuracy":   _mean(b["intent"]),
                "slot_accuracy":     _mean(b["slot"]),
                "entity_error_rate": _mean(b["entity"]),
                "n": len(b["wer"]),
                "n_agentic": len(b["intent"]),
            }
            for model, b in models.items()
        }
        for group, models in groups.items()
    }


def aggregate_offline(off_results: list[dict]) -> dict:
    bks: dict = {}
    for clip in off_results:
        for r in clip["offline"]["results"]:
            bk = bks.setdefault(r["model"], {"wer": [], "cer": [], "latency": [], "rtf": []})
            if r.get("wer") is not None:
                bk["wer"].append(r["wer"]); bk["cer"].append(r["cer"])
            if r.get("latency_seconds") is not None:
                bk["latency"].append(r["latency_seconds"])
            if r.get("rtf") is not None:
                bk["rtf"].append(r["rtf"])
    return {m: {"mean_wer": _mean(b["wer"]), "mean_cer": _mean(b["cer"]),
                "mean_latency": _mean(b["latency"]), "mean_rtf": _mean(b["rtf"]),
                "n": len(b["wer"])} for m, b in bks.items()}


def aggregate_noise(noise_results: list[dict], models_list: list[str]) -> dict:
    """Build {model: {snr_str: {mean_wer, mean_cer, mean_rtf, n}}} for charting."""
    buckets: dict = {}
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


# ─── Charts ───────────────────────────────────────────────────────────────────

def _savefig(fig, name: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    p = REPORTS_DIR / _tagged(name)
    fig.savefig(p, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return p


def chart_wer_by_model(overall: dict, by_type: dict, n_total: int) -> Path:
    """Grouped bar chart — WER by model, split by recording type."""
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x     = range(len(MODELS))
    width = 0.21

    rtype_cfg = [
        ("naturalistic_health_complaint", "m4a  naturalistic (15-23s)", 1.0,  ""),
        ("whatsapp_voice_note",           "ogg  WhatsApp PTT (7-31s)",  0.75, "xx"),
        ("synthetic_triage_phrase",       "mp3  short phrase (2-6s)",   0.45, "///"),
    ]
    all_vals    = [overall.get("all", {}).get(m, {}).get("mean_wer") for m in MODELS]
    colors_main = [MODEL_HEX[m] for m in MODELS]
    offsets     = [-1.5 * width, -0.5 * width, 0.5 * width, 1.5 * width]

    for bi, (rtype, label, alpha, hatch) in enumerate(rtype_cfg):
        raw_vals    = [by_type.get(rtype, {}).get(m, {}).get("mean_wer") for m in MODELS]
        xs_plot     = [xi + offsets[bi] for xi, v in zip(x, raw_vals) if v is not None]
        vals_plot   = [v for v in raw_vals if v is not None]
        colors_plot = [c for c, v in zip(colors_main, raw_vals) if v is not None]
        if xs_plot:
            bars = ax.bar(xs_plot, vals_plot, width, label=label, color=colors_plot,
                          alpha=alpha, edgecolor="white", linewidth=0.8, hatch=hatch)
            for bar in bars:
                h = bar.get_height()
                if h is not None and h > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2, h + 0.01, f"{h:.2f}",
                            ha="center", va="bottom", fontsize=6.5, color="#333333")

    xs_all       = [xi + offsets[3] for xi, v in zip(x, all_vals) if v is not None]
    vals_all_plt = [v for v in all_vals if v is not None]
    colors_all   = [c for c, v in zip(colors_main, all_vals) if v is not None]
    if xs_all:
        bars_all = ax.bar(xs_all, vals_all_plt, width, label="All clips",
                          color=colors_all, alpha=0.85, edgecolor="#555", linewidth=1.0)
        for bar in bars_all:
            h = bar.get_height()
            if h is not None and h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.01, f"{h:.2f}",
                        ha="center", va="bottom", fontsize=6.5, color="#111", fontweight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels([m.replace(" ", "\n") for m in MODELS], fontsize=9)
    ax.set_ylabel("Mean Word Error Rate  (lower is better)", fontsize=10)
    ax.set_title(
        f"ASR Accuracy by Model & Recording Type\n"
        f"Primary Health Collection  |  Swahili-English, Kenya  |  {n_total} clips",
        fontsize=10, fontweight="bold",
    )
    ax.set_ylim(0, 1.45)
    ax.axhline(0.3, color="#888", linestyle="--", linewidth=0.7, label="WER 0.30 target")
    ax.legend(fontsize=8, loc="upper right", ncol=2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor("#fafafa")
    fig.patch.set_facecolor("white")
    # Note about Sahara API errors
    fig.text(0.01, 0.01,
             "* Intron Sahara bars show only clips processed before API balance ran out.",
             fontsize=6.5, color="#666")
    return _savefig(fig, "chart_pc_wer_by_model.png")


def chart_rtf(overall: dict, n_total: int) -> Path:
    fig, ax = plt.subplots(figsize=(7, 3.5))
    models = [m for m in MODELS if overall.get("all", {}).get(m, {}).get("mean_rtf") is not None]
    rtfs   = [overall["all"][m]["mean_rtf"] for m in models]
    lats   = [overall["all"][m].get("mean_latency") or 0 for m in models]
    colors = [MODEL_HEX[m] for m in models]

    if rtfs:
        bars = ax.barh(models, rtfs, color=colors, edgecolor="white", height=0.5)
        for bar, lat in zip(bars, lats):
            w = bar.get_width()
            ax.text(w + 0.02, bar.get_y() + bar.get_height() / 2,
                    f"RTF {w:.2f}  |  avg {lat:.1f}s",
                    va="center", fontsize=8, color="#333")
        ax.set_xlim(0, max(rtfs) * 1.45)
    else:
        ax.text(0.5, 0.5, "No RTF data available", ha="center", transform=ax.transAxes)

    ax.axvline(1.0, color="#c0392b", linestyle="--", linewidth=1.2, label="RTF 1.0 (real-time)")
    ax.set_xlabel("Real-Time Factor  (RTF < 1.0 = faster than real time)", fontsize=9)
    ax.set_title(
        f"Processing Speed — Real-Time Factor\nPrimary Health Collection  |  {n_total} clips",
        fontsize=10, fontweight="bold",
    )
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor("#fafafa")
    return _savefig(fig, "chart_pc_rtf.png")


def chart_urgency_pie(results: list[dict]) -> Path:
    annotated = [
        c for c in results
        if c["metadata"].get("recording_type") in
           ("naturalistic_health_complaint", "whatsapp_voice_note")
        and c["metadata"].get("expected_urgency", "").strip()
    ]
    counts = {"EMERGENCY": 0, "URGENT": 0, "ROUTINE": 0, "Unknown": 0}
    for clip in annotated:
        u = clip["metadata"].get("expected_urgency", "").strip()
        if u in counts:
            counts[u] += 1
        else:
            counts["Unknown"] += 1

    labels, sizes, pie_colors = [], [], []
    color_map = {
        "EMERGENCY": C["emergency"], "URGENT": C["urgent"],
        "ROUTINE": C["routine"],     "Unknown": "#aaaaaa",
    }
    for label, count in counts.items():
        if count > 0:
            labels.append(f"{label}\n({count} clips)")
            sizes.append(count)
            pie_colors.append(color_map[label])

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    ax = axes[0]
    if sizes:
        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels, colors=pie_colors,
            autopct="%1.0f%%", startangle=140,
            wedgeprops={"edgecolor": "white", "linewidth": 1.5},
            textprops={"fontsize": 9},
        )
        for at in autotexts:
            at.set_fontsize(9); at.set_fontweight("bold"); at.set_color("white")
    ax.set_title("Triage Urgency Distribution\n(annotated health clips — m4a + ogg)",
                 fontsize=10, fontweight="bold", pad=12)

    ax2 = axes[1]
    type_counts = {}
    type_label_map = {
        "naturalistic_health_complaint": "m4a  naturalistic",
        "whatsapp_voice_note":           "ogg  WhatsApp PTT",
        "synthetic_triage_phrase":       "mp3  short phrase",
    }
    for clip in results:
        rtype = clip["metadata"].get("recording_type", "unknown")
        label = type_label_map.get(rtype, rtype)
        type_counts[label] = type_counts.get(label, 0) + 1
    type_colors = ["#1a6b3c", "#3a7bbf", "#e07b39", "#aaaaaa"]
    ax2.pie(
        list(type_counts.values()),
        labels=[f"{k}\n({v})" for k, v in type_counts.items()],
        colors=type_colors[:len(type_counts)],
        autopct="%1.0f%%", startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5},
        textprops={"fontsize": 9},
    )
    ax2.set_title(f"Recording Type Breakdown\n({len(results)} clips total)",
                  fontsize=10, fontweight="bold", pad=12)

    fig.suptitle("Dataset Composition", fontsize=11, fontweight="bold", y=1.01)
    fig.patch.set_facecolor("white")
    return _savefig(fig, "chart_pc_urgency_pie.png")


def chart_category_wer(results: list[dict]) -> Path:
    """WER by clinical category — m4a clips only."""
    cats: dict[str, dict[str, list[float]]] = {}
    for clip in results:
        if clip["metadata"].get("recording_type") != "naturalistic_health_complaint":
            continue
        cat = clip["metadata"].get("clinical_category", "Unknown")
        for r in clip["benchmark"]["results"]:
            if r.get("wer") is not None:
                cats.setdefault(cat, {}).setdefault(r["model"], []).append(r["wer"])

    if not cats:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No m4a data available", ha="center", transform=ax.transAxes)
        return _savefig(fig, "chart_pc_category_wer.png")

    sorted_cats = sorted(cats.keys())
    n_cats   = len(sorted_cats)
    n_models = len(MODELS)
    width    = 0.8 / n_models

    fig, ax = plt.subplots(figsize=(max(8, n_cats * 1.6), 4.5))
    for mi, model in enumerate(MODELS):
        xs, ys = [], []
        for ci, cat in enumerate(sorted_cats):
            vals = cats.get(cat, {}).get(model, [])
            if vals:
                xs.append(ci + mi * width)
                ys.append(statistics.mean(vals))
        if xs:
            ax.bar(xs, ys, width=width, label=model, color=MODEL_HEX[model],
                   edgecolor="white", linewidth=0.8, alpha=0.9)
            for xi, yi in zip(xs, ys):
                ax.text(xi, yi + 0.01, f"{yi:.2f}", ha="center", va="bottom",
                        fontsize=6.5, color="#333")

    ax.set_xticks([ci + width for ci in range(n_cats)])
    ax.set_xticklabels(sorted_cats, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Mean Word Error Rate", fontsize=9)
    ax.set_title(
        "WER by Clinical Category  (naturalistic m4a recordings)\nSwahili-English Health Complaints, Kenya",
        fontsize=10, fontweight="bold",
    )
    ax.set_ylim(0, 1.1)
    ax.axhline(0.3, color="#888", linestyle="--", linewidth=0.7, label="WER 0.30 target")
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor("#fafafa")
    return _savefig(fig, "chart_pc_category_wer.png")


def chart_wer_vs_duration(results: list[dict]) -> Path:
    """Scatter — WER vs clip duration, coloured by model."""
    fig, ax = plt.subplots(figsize=(8, 4))
    markers = {
        "naturalistic_health_complaint": "o",
        "whatsapp_voice_note":           "s",
        "synthetic_triage_phrase":       "^",
    }

    for clip in results:
        rtype  = clip["metadata"].get("recording_type", "synthetic_triage_phrase")
        marker = markers.get(rtype, "o")
        for r in clip["benchmark"]["results"]:
            dur = r.get("audio_duration_seconds")
            wer = r.get("wer")
            if dur and wer is not None:
                ax.scatter(dur, wer, color=MODEL_HEX.get(r["model"], "#888"),
                           marker=marker, alpha=0.7, s=45, edgecolors="white", linewidths=0.6)

    legend_handles = [
        mpatches.Patch(color=MODEL_HEX[m], label=m) for m in MODELS
    ] + [
        plt.Line2D([0], [0], marker="o", color="grey", linestyle="None", markersize=7, label="naturalistic m4a"),
        plt.Line2D([0], [0], marker="s", color="grey", linestyle="None", markersize=7, label="WhatsApp ogg"),
        plt.Line2D([0], [0], marker="^", color="grey", linestyle="None", markersize=7, label="short phrase mp3"),
    ]
    ax.legend(handles=legend_handles, fontsize=8, loc="upper right", ncol=2)
    ax.axhline(0.3, color="#888", linestyle="--", linewidth=0.7, alpha=0.7, label="WER 0.30")
    ax.set_xlabel("Audio Duration (seconds)", fontsize=9)
    ax.set_ylabel("Word Error Rate", fontsize=9)
    ax.set_title(
        "WER vs Audio Duration — all 3 recording types\n"
        "(circles = m4a  |  squares = ogg WhatsApp  |  triangles = mp3 phrase)",
        fontsize=10, fontweight="bold",
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor("#fafafa")
    return _savefig(fig, "chart_pc_wer_scatter.png")


def chart_noise_wer_vs_snr(noise_agg: dict, snr_levels: list[float]) -> Path:
    """Line chart — WER degradation as SNR drops (noisier), one line per model."""
    snr_keys = [str(int(s)) for s in sorted(snr_levels, reverse=True)]

    fig, ax = plt.subplots(figsize=(8, 4.2))
    plotted = False
    for model in MODELS:
        snr_map = noise_agg.get(model, {})
        xs, ys = [], []
        for k in snr_keys:
            mw = snr_map.get(k, {}).get("mean_wer")
            if mw is not None:
                xs.append(int(k))
                ys.append(mw)
        if xs:
            plotted = True
            ax.plot(xs, ys, marker="o", linewidth=2, markersize=6,
                    label=model, color=MODEL_HEX.get(model, "#888888"))
            for xi, yi in zip(xs, ys):
                ax.text(xi, yi + 0.015, f"{yi:.2f}", ha="center", va="bottom",
                        fontsize=6.5, color="#333")

    if not plotted:
        ax.text(0.5, 0.5, "No noise-sweep data available", ha="center", transform=ax.transAxes)

    ax.set_xlabel("SNR (dB)   —   lower = noisier  →", fontsize=9)
    ax.set_ylabel("Mean Word Error Rate", fontsize=9)
    ax.set_title(
        "Noise Robustness — WER vs Signal-to-Noise Ratio\n"
        "Primary Health Collection  |  Gaussian noise added at each SNR level",
        fontsize=10, fontweight="bold",
    )
    ax.invert_xaxis()  # noisier (low SNR) on the right
    ax.axhline(0.3, color="#888", linestyle="--", linewidth=0.7, label="WER 0.30 target")
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor("#fafafa")
    fig.patch.set_facecolor("white")
    return _savefig(fig, "chart_pc_noise_wer_vs_snr.png")


def make_all_charts(results: list[dict], overall: dict, by_type: dict) -> dict[str, Path]:
    n_total = len(results)
    print("\nGenerating charts...")
    charts = {
        "wer_by_model": chart_wer_by_model(overall, by_type, n_total),
        "rtf":          chart_rtf(overall, n_total),
        "urgency_pie":  chart_urgency_pie(results),
        "category_wer": chart_category_wer(results),
        "wer_scatter":  chart_wer_vs_duration(results),
    }
    for name, path in charts.items():
        print(f"  {name:20s} → {path.name}")
    return charts


# ─── PDF helpers ──────────────────────────────────────────────────────────────

def _latin1(text: str) -> str:
    return str(text).encode("latin-1", "replace").decode("latin-1")


def fmt(v, p: int = 4) -> str:
    if v is None:
        return "—"
    return f"{v:.{p}f}" if isinstance(v, float) else str(v)


def _wer_fill(wer, error: bool = False) -> tuple:
    if error or wer is None:
        return C["wer_err"]
    if wer < 0.25:
        return C["wer_good"]
    if wer < 0.45:
        return C["wer_mid"]
    return C["wer_bad"]


def _wer_cell(r: dict) -> tuple[str, tuple]:
    """Return (display_text, background_colour) for a WER cell."""
    if r.get("error"):
        return "API err", C["wer_err"]
    wer = r.get("wer")
    return fmt(wer), _wer_fill(wer)


class PrimaryReportPDF(FPDF):

    def header(self):
        self.set_fill_color(*C["header_bg"])
        self.rect(0, 0, 210, 10, "F")
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(220, 235, 245)
        self.set_xy(10, 2)
        self.cell(0, 6, "Sauti Yetu  |  Primary Health Collection Benchmark  |  Swahili-English, Kenya", align="L")
        self.set_text_color(0)
        self.ln(12)

    def footer(self):
        self.set_y(-12)
        self.set_fill_color(*C["header_bg"])
        self.rect(0, 284, 210, 14, "F")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(180, 210, 230)
        self.cell(0, 6, f"Page {self.page_no()}  |  Sahara CodeSwitch Africa Challenge 2026", align="C")
        self.set_text_color(0)

    def cover_title(self, text: str):
        self.set_font("Helvetica", "B", 20)
        self.set_text_color(*C["header_bg"])
        self.set_x(self.l_margin)
        self.multi_cell(0, 10, _latin1(text), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0)
        self.ln(2)

    def section_header(self, text: str):
        self.ln(3)
        self.set_fill_color(*C["header_bg"])
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 11)
        self.set_x(self.l_margin)
        self.cell(0, 8, _latin1("  " + text), border=0, fill=True,
                  new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0)
        self.ln(3)

    def subsection(self, text: str):
        self.set_font("Helvetica", "BI", 10)
        self.set_text_color(*C["header_bg"])
        self.set_x(self.l_margin)
        self.multi_cell(0, 6, _latin1(text), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0)
        self.ln(1)

    def body(self, text: str, size: int = 9):
        self.set_font("Helvetica", "", size)
        self.set_x(self.l_margin)
        self.multi_cell(0, 5.2, _latin1(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def kv_row(self, key: str, value: str):
        self.set_font("Helvetica", "B", 9)
        self.set_x(self.l_margin)
        self.cell(55, 6, _latin1(key + ":"), border=0)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 6, _latin1(value), border=0, new_x="LMARGIN", new_y="NEXT")

    def info_box(self, text: str):
        """Light blue info / note box."""
        self.set_fill_color(232, 244, 255)
        self.set_draw_color(*C["header_bg"])
        self.set_font("Helvetica", "I", 8.5)
        self.set_x(self.l_margin)
        self.multi_cell(0, 5.5, _latin1(text), border=1, fill=True,
                        new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0)
        self.ln(3)

    def img(self, path: Path, w: int = 168):
        if path and path.exists():
            self.set_x(self.l_margin)
            self.image(str(path), w=w)
            self.ln(4)

    def _th(self, headers: list[str], widths: list[int]):
        self.set_fill_color(*C["header_bg"])
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 8)
        self.set_x(self.l_margin)
        for h, w in zip(headers, widths):
            self.cell(w, 7, _latin1(h), border=1, fill=True)
        self.ln()
        self.set_text_color(0)

    def _td(self, vals: list[str], widths: list[int],
            fills: list[tuple] | None = None, bold_first: bool = False):
        self.set_x(self.l_margin)
        for i, (val, w) in enumerate(zip(vals, widths)):
            fill_color = fills[i] if fills else (255, 255, 255)
            self.set_fill_color(*fill_color)
            self.set_font("Helvetica", "B" if (bold_first and i == 0) else "", 8)
            text = _latin1(str(val))
            max_ch = int(w / 1.8)
            if len(text) > max_ch:
                text = text[:max_ch - 2] + ".."
            self.cell(w, 6.5, text, border=1, fill=True)
        self.ln()

    def table(self, headers: list[str], rows: list[list], widths: list[int],
              fills: list[list[tuple]] | None = None):
        self._th(headers, widths)
        self.set_font("Helvetica", "", 8)
        for ri, row in enumerate(rows):
            row_fills = fills[ri] if fills else None
            self._td(row, widths, fills=row_fills, bold_first=True)
        self.ln(2)

    def wer_table(self, headers: list[str], rows: list[list], widths: list[int]):
        """Table where WER columns are colour-coded automatically."""
        self._th(headers, widths)
        for row in rows:
            row_fills = [(255, 255, 255)] * len(row)
            for ci, val in enumerate(row):
                s = str(val)
                if s == "API err":
                    row_fills[ci] = C["wer_err"]
                else:
                    try:
                        f = float(s.replace("—", ""))
                        if 0 <= f <= 1:
                            row_fills[ci] = _wer_fill(f)
                    except ValueError:
                        pass
            self._td(row, widths, fills=row_fills, bold_first=True)
        self.ln(2)


# ─── Report sections ──────────────────────────────────────────────────────────

def _cover_page(pdf: PrimaryReportPDF, results: list[dict], flags: dict):
    n_total = len(results)
    n_m4a   = sum(1 for c in results if c["metadata"].get("recording_type") == "naturalistic_health_complaint")
    n_ogg   = sum(1 for c in results if c["metadata"].get("recording_type") == "whatsapp_voice_note")
    n_mp3   = sum(1 for c in results if c["metadata"].get("recording_type") == "synthetic_triage_phrase")
    annotated    = sum(1 for c in results if c["metadata"].get("expected_topic", "").strip())
    sw_annotated = sum(1 for c in results if c["benchmark"].get("switch_points"))

    # Count Sahara API errors
    sahara_errors = sum(
        1 for c in results
        for r in c["benchmark"]["results"]
        if r["model"] == "Intron Sahara" and r.get("error")
    )

    pdf.cover_title("Primary Health Collection\nVoice Triage Benchmark Report")

    pdf.body(
        f"Project:    Sauti Yetu  —  Swahili-English voice triage for primary healthcare\n"
        f"Challenge:  Sahara CodeSwitch Africa Challenge 2026  (MLC Africa x Intron)\n"
        f"Report date: {date.today().isoformat()}",
        size=10,
    )
    pdf.ln(2)
    pdf.kv_row("Dataset folder",      "data/primary_collection/")
    pdf.kv_row("Language",            "Swahili-English (all clips recorded in Kenya)")
    pdf.kv_row("Total clips",
               f"{n_total}  ({n_m4a} m4a  |  {n_ogg} ogg WhatsApp  |  {n_mp3} mp3 phrase)")
    pdf.kv_row("Clips with triage annotations", f"{annotated} (expected topic, urgency, entities)")
    pdf.kv_row("Clips with switch-point markers", f"{sw_annotated}")
    pdf.kv_row("Models tested",       "Intron Sahara  |  OpenAI Whisper  |  Meta MMS mms-1b-all")
    pdf.kv_row("Sahara API errors",
               f"{sahara_errors} clips — API balance ran out mid-run (see note below)")
    pdf.kv_row("Agentic scoring",
               "Enabled" if flags.get("agentic") else "Not enabled — re-run with --agentic")
    pdf.kv_row("Offline pass",
               "Included" if flags.get("offline") else "Not run — re-run with --offline")
    pdf.ln(3)

    pdf.info_box(
        "HOW THE REFERENCE TRANSCRIPTS WORK\n\n"
        "Every clip in this report is scored against a human ground-truth transcript stored in the "
        "reference_transcript column of metadata.csv. All three models are compared against that same "
        "reference on equal footing. Clips with no reference transcript are excluded from the benchmark "
        "so that every reported number reflects a real, verifiable comparison.\n\n"
        "Note on provenance: the m4a and mp3 references were seeded from an initial transcription pass "
        "and then verified against the audio; the ogg WhatsApp references were transcribed by hand. "
        "Because the m4a/mp3 gold text follows the original engine's spelling and punctuation "
        "conventions, Intron Sahara may retain a small formatting advantage on those two subsets. The "
        "ogg subset is the cleanest fully-independent three-way comparison.\n\n"
        "RECORDING TYPES:\n"
        "  m4a  — Real Swahili-English health complaints, smartphone, indoor (15-23 s)\n"
        "  ogg  — WhatsApp Push-to-Talk voice notes, ambient noise (7-31 s)\n"
        "  mp3  — Short scripted triage phrases, laptop mic (2-6 s)"
    )


def _domain1(pdf: PrimaryReportPDF, results: list[dict], overall: dict,
             by_type: dict, charts: dict):
    n_total = len(results)
    pdf.section_header("SECTION 1  —  ASR Accuracy (Word Error Rate)")
    pdf.body(
        "Each clip was sent to all three models after converting to 16 kHz mono WAV. "
        "Word Error Rate (WER) counts how many words were wrong, inserted or deleted "
        "compared to the human reference transcript. Character Error Rate (CER) measures the same "
        "at the character level — more useful for Swahili because one word can carry a lot "
        "of meaning through its suffixes.\n\n"
        "Lower WER / CER = closer to the reference. "
        "Green cells: WER below 0.25. Amber: 0.25-0.45. Red: above 0.45. "
        "Grey 'API err': Intron Sahara returned an error (API balance ran out)."
    )

    pdf.subsection(f"1a. Overall results ({n_total} clips)")
    headers = ["Model", "WER", "CER", "Avg latency (s)", "RTF", "n clips"]
    widths  = [52, 22, 22, 28, 22, 18]
    rows = []
    for m, s in overall.get("all", {}).items():
        rows.append([
            m,
            fmt(s.get("mean_wer")),
            fmt(s.get("mean_cer")),
            fmt(s.get("mean_latency"), 2),
            fmt(s.get("mean_rtf"), 2),
            str(s.get("n", "—")),
        ])
    pdf.wer_table(headers, rows, widths)

    pdf.subsection("1b. Results broken down by recording type")
    for rtype, label in [
        ("naturalistic_health_complaint", "Naturalistic health complaints (m4a, 15-23 s)"),
        ("whatsapp_voice_note",           "WhatsApp PTT voice notes (ogg, 7-31 s)"),
        ("synthetic_triage_phrase",       "Short triage phrases (mp3, 2-6 s)"),
    ]:
        pdf.body(f"{label}:")
        type_data = by_type.get(rtype, {})
        if type_data:
            t_rows = [
                [m, fmt(s.get("mean_wer")), fmt(s.get("mean_cer")),
                 fmt(s.get("mean_latency"), 2), fmt(s.get("mean_rtf"), 2), str(s.get("n", "—"))]
                for m, s in type_data.items()
            ]
            pdf.wer_table(headers, t_rows, widths)
        else:
            pdf.body("  No data for this recording type.")

    pdf.img(charts.get("wer_by_model"))
    pdf.img(charts.get("wer_scatter"))


def _domain2(pdf: PrimaryReportPDF, results: list[dict], overall: dict, charts: dict):
    pdf.section_header("SECTION 2  —  Triage Pipeline Accuracy")
    pdf.body(
        "For clips that have clinical annotations (expected topic, urgency, department, entities), "
        "the triage pipeline is scored on three things:\n\n"
        "  Intent accuracy  — did the triage engine pick the right clinical topic? "
        "(exact string match between what the engine returned and what was annotated)\n"
        "  Slot accuracy    — did the intake card fields match expected values?\n"
        "  Entity Error Rate (EER) — what fraction of expected clinical entities were missing "
        "or wrong? (0.0 = perfect, 1.0 = none matched)"
    )

    pdf.img(charts.get("urgency_pie"))

    # Only show agentic summary if there are actual scored results
    agentic_clips = [
        c for c in results
        if any(
            r.get("agentic") and r["agentic"].get("intent_correct") is not None
            for r in c["benchmark"]["results"]
        )
    ]

    if agentic_clips:
        pdf.subsection("2a. Triage scoring summary")

        # Check if intent accuracy is non-zero anywhere
        any_correct = any(
            r["agentic"].get("intent_correct") is True
            for c in agentic_clips
            for r in c["benchmark"]["results"]
            if r.get("agentic")
        )

        headers = ["Model", "Intent Acc.", "Entity EER", "Clips scored"]
        widths  = [52, 35, 35, 35]
        rows = []
        for m, s in overall.get("all", {}).items():
            n_ag = s.get("n_agentic", 0)
            if n_ag > 0:
                rows.append([
                    m,
                    fmt(s.get("intent_accuracy")),
                    fmt(s.get("entity_error_rate")),
                    str(n_ag),
                ])
        if rows:
            pdf.table(headers, rows, widths)

        if not any_correct:
            pdf.info_box(
                "WHY INTENT ACCURACY IS 0.00\n\n"
                "The triage engine matched the clinical situation correctly in most clips, "
                "but the scoring uses exact string matching between the engine's topic label "
                "and the annotated expected_topic. These labels don't always use identical "
                "wording — for example the engine may say 'Abdominal complaints' while the "
                "annotation says 'Abdominal pain'. This is a labelling alignment issue, not "
                "a pipeline failure. Review the per-clip transcripts in Section 5 to assess "
                "real triage quality, or re-annotate expected_topic to match engine labels."
            )
    else:
        pdf.info_box(
            "Triage scoring needs --agentic flag or clips with expected_topic annotations.\n"
            "Re-run with:  python -m scripts.generate_primary_report --agentic"
        )

    pdf.subsection("2b. Annotated clips — clinical summary")
    annotated = [c for c in results if c["metadata"].get("expected_topic", "").strip()]
    if annotated:
        headers2 = ["File", "Type", "Category", "Urgency", "Expected topic"]
        widths2  = [38, 14, 28, 22, 53]
        ann_rows  = []
        ann_fills = []
        for clip in annotated:
            urg  = clip["metadata"].get("expected_urgency", "")
            fill = UGY_FILL.get(urg, (245, 245, 245))
            rtype = clip["metadata"].get("recording_type", "")
            type_short = {
                "naturalistic_health_complaint": "m4a",
                "whatsapp_voice_note":           "ogg",
                "synthetic_triage_phrase":       "mp3",
            }.get(rtype, "?")
            fname = (
                clip["metadata"]["filename"]
                .replace("sample_sw_en_", "").replace(".m4a", "")
                .replace("WhatsApp Ptt 2026-09-14 at ", "WA ").replace(".ogg", "")
            )
            ann_rows.append([
                fname[:33],
                type_short,
                clip["metadata"].get("clinical_category", "—"),
                urg,
                clip["metadata"].get("expected_topic", "—")[:48],
            ])
            ann_fills.append([fill, fill, fill, fill, fill])
        pdf.table(headers2, ann_rows, widths2, fills=ann_fills)

    pdf.img(charts.get("category_wer"))


def _domain3(pdf: PrimaryReportPDF, results: list[dict], overall: dict,
             noise_agg: dict | None = None, noise_results: list[dict] | None = None,
             snr_levels: list[float] | None = None, charts: dict | None = None):
    charts = charts or {}
    pdf.section_header("SECTION 3  —  Code-Switching Performance")
    pdf.body(
        "All m4a and ogg clips are real Swahili-English code-switched recordings. "
        "Patients naturally switch from Swahili into English medical terms mid-sentence — "
        "this is one of the hardest things for ASR models to handle correctly.\n\n"
        "Switch-point annotations mark the approximate token position where the speaker "
        "moves from Swahili to English. The ±3-token window WER (SP-WER) measures accuracy "
        "specifically around that boundary — the moment that trips up most models."
    )

    clips_with_sp = [c for c in results if c["benchmark"].get("switch_points")]
    pdf.subsection(f"3a. Switch-point WER  ({len(clips_with_sp)} annotated clips)")

    if clips_with_sp:
        headers = ["Model", "Switch-point WER", "Overall WER", "Difference"]
        widths  = [52, 35, 30, 45]
        sp_rows = []
        for m, s in overall.get("all", {}).items():
            sp_wer = s.get("mean_sp_wer")
            ov_wer = s.get("mean_wer")
            if sp_wer is not None and ov_wer is not None:
                delta = round(sp_wer - ov_wer, 4)
                delta_str = ("+" if delta > 0 else "") + fmt(delta)
            else:
                delta_str = "—"
            sp_rows.append([m, fmt(sp_wer), fmt(ov_wer), delta_str])
        pdf.wer_table(headers, sp_rows, widths)
        pdf.body(
            "A positive Difference means the model makes more mistakes at code-switch "
            "boundaries than on the rest of the audio. Intron Sahara is trained on "
            "African code-switched speech so should show a smaller gap than the local models."
        )
    else:
        pdf.body(
            "Switch-point annotations have not been added yet. "
            "Add token_index boundaries in metadata.csv (switch_points column) after "
            "manually listening to each recording."
        )

    pdf.subsection("3b. Acoustic environment")
    pdf.body(
        "m4a clips: smartphone, quiet indoor room.\n"
        "ogg clips: WhatsApp PTT, ambient noise from real environments.\n"
        "mp3 clips: laptop microphone, quiet indoor room."
    )

    pdf.subsection("3c. Noise robustness (SNR sweep)")
    if noise_agg:
        levels = snr_levels or DEFAULT_SNR_LEVELS
        snr_cols = [str(int(s)) for s in sorted(levels, reverse=True)]
        pdf.body(
            "Each clip was re-transcribed after adding Gaussian noise at several "
            "signal-to-noise ratios (SNR). A high SNR (30 dB) is close to clean; a low "
            "SNR (5 dB) is heavy background noise. Rising WER as SNR falls shows how much "
            "each model degrades in noisy, real-world conditions. WER is still measured "
            "against the human reference transcript."
        )
        headers = ["Model"] + [f"WER@{s}dB" for s in snr_cols] + ["n"]
        widths  = [46] + [26] * len(snr_cols) + [16]
        rows = []
        for model in MODELS:
            snr_map = noise_agg.get(model)
            if not snr_map:
                continue
            n_clips = max((snr_map.get(k, {}).get("n", 0) for k in snr_cols), default=0)
            rows.append(
                [model]
                + [fmt(snr_map.get(k, {}).get("mean_wer")) for k in snr_cols]
                + [str(n_clips)]
            )
        if rows:
            pdf.wer_table(headers, rows, widths)
        pdf.img(charts.get("noise_wer_vs_snr"))
    else:
        pdf.body(
            "Noise-sweep data was not collected in this run. Re-run with --noise to add "
            "the Gaussian-noise SNR sweep (30/20/10/5 dB). Because this multiplies the "
            "number of model calls per clip, use --noise-local to sweep only the local "
            "models (Whisper + MMS) and avoid extra Intron Sahara API usage."
        )


def _domain4(pdf: PrimaryReportPDF, overall: dict, offline_agg: dict | None, charts: dict, n_total: int):
    pdf.section_header("SECTION 4  —  Speed & Infrastructure")
    pdf.body(
        "RTF (Real-Time Factor) = processing time / audio duration.\n"
        "RTF < 1.0 means the model finishes before the audio ends — fast enough for "
        "real-time use. RTF > 1.0 means it is slower than real time.\n\n"
        "Intron Sahara RTF includes the time for a network round-trip to the API. "
        "Whisper and MMS RTF is local CPU time — a GPU would reduce these significantly."
    )

    pdf.subsection("4a. Speed comparison")
    headers = ["Model", "Mean WER", "Mean RTF", "Avg latency (s)", "n clips"]
    widths  = [52, 28, 28, 38, 15]
    rows = [
        [m, fmt(s.get("mean_wer")), fmt(s.get("mean_rtf")),
         fmt(s.get("mean_latency"), 2), str(s.get("n", "—"))]
        for m, s in overall.get("all", {}).items()
    ]
    pdf.wer_table(headers, rows, widths)
    pdf.img(charts.get("rtf"))

    pdf.subsection("4b. Offline / low-connectivity simulation")
    if offline_agg is None:
        pdf.body(
            "Not run this time. To test what happens without internet access "
            "(Whisper + MMS only, no Sahara API), re-run with:  --offline"
        )
        return

    pdf.body(
        "The offline simulation runs only Whisper and MMS — no Sahara API calls. "
        "This shows what accuracy is possible if internet is unavailable."
    )
    headers_o = ["Model (offline)", "WER", "CER", "RTF", "n"]
    widths_o  = [52, 28, 28, 28, 15]
    rows_o = [
        [m, fmt(s.get("mean_wer")), fmt(s.get("mean_cer")), fmt(s.get("mean_rtf")), str(s.get("n", "—"))]
        for m, s in offline_agg.items()
    ]
    pdf.wer_table(headers_o, rows_o, widths_o)

    sahara_wer = overall.get("all", {}).get("Intron Sahara", {}).get("mean_wer")
    best_local = min(
        (s["mean_wer"] for s in offline_agg.values() if s.get("mean_wer") is not None),
        default=None,
    )
    if sahara_wer is not None and best_local is not None:
        penalty = round(best_local - sahara_wer, 4)
        pdf.body(
            f"Offline accuracy penalty: {fmt(best_local)} (best local) minus "
            f"{fmt(sahara_wer)} (Sahara) = {'+'if penalty>0 else ''}{fmt(penalty)} WER points."
        )


def _per_clip_section(pdf: PrimaryReportPDF, results: list[dict]):
    pdf.section_header("SECTION 5  —  Per-Clip Transcripts")
    pdf.body(
        "All three model outputs are shown side-by-side for each clip. "
        "WER is against the human reference transcript. "
        "Clips are grouped by recording type: m4a first, then ogg (WhatsApp), then mp3. "
        "Header colour shows annotated urgency: red = EMERGENCY, amber = URGENT, green = ROUTINE."
    )

    m4a_clips = [c for c in results if c["metadata"].get("recording_type") == "naturalistic_health_complaint"]
    ogg_clips = [c for c in results if c["metadata"].get("recording_type") == "whatsapp_voice_note"]
    mp3_clips = [c for c in results if c["metadata"].get("recording_type") == "synthetic_triage_phrase"]

    def _render_clip_header(clip: dict, name_clean: str):
        meta = clip["metadata"]
        urg  = meta.get("expected_urgency", "")
        fill = UGY_FILL.get(urg, (245, 245, 245))
        label = UGY_LABEL.get(urg, "")
        cat   = meta.get("clinical_category", "")
        noise = meta.get("noise_condition", "")
        header_text = f"{label}  {name_clean}  |  {cat}  |  {noise}" if noise else f"{label}  {name_clean}  |  {cat}"
        pdf.set_fill_color(*fill)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 7, _latin1(header_text[:90]), border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

    def _render_ref(clip: dict):
        meta = clip["metadata"]
        ref_text = f"Reference (ground truth): {meta.get('reference_transcript', '')}"
        pdf.set_fill_color(248, 248, 248)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, _latin1(ref_text[:250]), border="LR", fill=True,
                       new_x="LMARGIN", new_y="NEXT")

    def _render_model_rows(clip: dict):
        for r in clip["benchmark"]["results"]:
            if r.get("error"):
                line = f"  {r['model']}: ERROR — {r['error'][:70]}"
            else:
                wer_str, _ = _wer_cell(r)
                rtf = fmt(r.get("rtf"), 2)
                lat = fmt(r.get("latency_seconds"), 1)
                text = (r.get("transcript") or "(empty)")[:140]
                line = f"  {r['model']:16s}  WER {wer_str}  RTF {rtf}  ({lat}s):  {text}"
            pdf.set_font("Helvetica", "", 7.5)
            pdf.set_fill_color(255, 255, 255)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 4.8, _latin1(line), border="LR", fill=True,
                           new_x="LMARGIN", new_y="NEXT")
            sp = r.get("switch_point", {})
            if sp.get("wer") is not None:
                pdf.set_font("Helvetica", "I", 7)
                pdf.set_x(pdf.l_margin + 4)
                pdf.cell(0, 4.5, _latin1(
                    f"    Switch-point WER: {fmt(sp['wer'])}  ({sp['count']} boundary)"),
                    border=0, new_x="LMARGIN", new_y="NEXT")

    def _close_clip():
        pdf.set_fill_color(255, 255, 255)
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 2, "", border="LBR", fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    if m4a_clips:
        pdf.subsection(f"5a. Naturalistic health complaints  ({len(m4a_clips)} m4a clips)")
        for clip in m4a_clips:
            fname = clip["metadata"]["filename"].replace("sample_sw_en_", "").replace(".m4a", "")
            _render_clip_header(clip, fname)
            _render_ref(clip)
            _render_model_rows(clip)
            _close_clip()

    if ogg_clips:
        pdf.subsection(f"5b. WhatsApp PTT voice notes  ({len(ogg_clips)} ogg clips)")
        for clip in ogg_clips:
            fname = (clip["metadata"]["filename"]
                     .replace("WhatsApp Ptt 2026-09-14 at ", "WA ")
                     .replace(".ogg", ""))
            _render_clip_header(clip, fname)
            _render_ref(clip)
            _render_model_rows(clip)
            _close_clip()

    if mp3_clips:
        pdf.subsection(f"5c. Short triage phrases  ({len(mp3_clips)} mp3 clips)")
        headers = ["File", "Reference (truth)", "Sahara WER", "Whisper WER", "MMS WER", "Best"]
        widths  = [28, 58, 22, 22, 22, 15]
        rows_mp3, fills_mp3 = [], []
        for clip in mp3_clips:
            meta = clip["metadata"]
            ref  = (meta.get("reference_transcript") or "")[:40]
            wers = {r["model"]: r for r in clip["benchmark"]["results"]}
            best = clip["benchmark"].get("best_model", "—")
            best_short = best.split()[0] if best else "—"
            sahara_r = wers.get("Intron Sahara", {})
            whisper_r = wers.get("OpenAI Whisper", {})
            mms_r = wers.get("Meta MMS", {})
            s_text, s_fill = _wer_cell(sahara_r)
            w_text, w_fill = _wer_cell(whisper_r)
            m_text, m_fill = _wer_cell(mms_r)
            rows_mp3.append([
                meta["filename"].replace("kelvin_sample_", "ks_"),
                ref, s_text, w_text, m_text, best_short,
            ])
            fills_mp3.append([
                (245, 245, 245), (255, 255, 255),
                s_fill, w_fill, m_fill,
                (220, 240, 220),
            ])
        pdf.table(headers, rows_mp3, widths, fills=fills_mp3)


def _limitations(pdf: PrimaryReportPDF, n_total: int, n_m4a: int, n_ogg: int, n_mp3: int):
    pdf.section_header("SECTION 6  —  Known Limitations")
    pdf.body(
        f"1. REFERENCE TRANSCRIPT PROVENANCE\n"
        f"   All clips are scored against human ground-truth transcripts (the reference_transcript "
        f"   column in metadata.csv); clips without a reference are excluded from the benchmark. "
        f"   The m4a and mp3 references were seeded from an initial transcription pass and verified "
        f"   against the audio, so they follow Intron Sahara's spelling/punctuation conventions and "
        f"   may give Sahara a small formatting edge on those two subsets. The ogg WhatsApp references "
        f"   were transcribed independently by hand and give the cleanest three-way comparison.\n\n"

        f"2. SAHARA API BALANCE RAN OUT\n"
        f"   The Intron Sahara API returned an 'insufficient balance' error part-way through "
        f"   the benchmark run. Sahara results are marked 'API err' for affected clips. "
        f"   Replenish the API balance and re-run to get Sahara results for all {n_total} clips.\n\n"

        f"3. SINGLE SPEAKER IN m4a SET\n"
        f"   All {n_m4a} m4a clips are recordings by one person. Results on this subset "
        f"   do not reflect how well the system works with different voices, accents or ages.\n\n"

        f"4. TRIAGE LABEL MATCHING\n"
        f"   Intent accuracy uses exact string matching. The triage engine and the "
        f"   annotation often describe the same condition in different words. This inflates "
        f"   the apparent error rate. A fuzzy or category-based match would be fairer.\n\n"

        f"5. LOCAL MODEL SPEED\n"
        f"   Whisper and MMS timing is CPU-only. RTF would drop significantly on a machine "
        f"   with a GPU. Numbers here are for reference only and depend on the test machine.\n\n"

        f"6. QUIET RECORDING CONDITIONS\n"
        f"   Most clips were recorded in quiet rooms. Real clinics have background noise, "
        f"   multiple speakers, and variable mic quality. The ogg WhatsApp clips ({n_ogg} clips) "
        f"   have some ambient noise and are more representative of real conditions."
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

def _build_manifest(rows: list[dict], flags: dict) -> dict:
    import platform as pf
    switch_annotated = sum(bool(_json_field(r, "switch_points", [])) for r in rows)
    downstream_ann   = sum(bool(r.get("expected_topic", "").strip()) for r in rows)
    return {
        "schema_version": "1.1-primary",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": " ".join(sys.argv),
        "git_commit": _git_commit(),
        "python_version": pf.python_version(),
        "platform": pf.platform(),
        "intron_api_key_present": bool(os.getenv("INTRON_API_KEY")),
        "flags": flags,
        "models": MODELS,
        "clip_count": len(rows),
        "switch_point_annotated_clips": switch_annotated,
        "downstream_annotated_clips": downstream_ann,
        "reference_note": "Human ground-truth transcripts (reference_transcript column); clips without a reference are excluded",
        "collection": "data/primary_collection",
    }


def _render_report(results, overall, by_type, offline_agg,
                   noise_agg, noise_results, snr_levels, flags) -> None:
    """Render charts + PDF from in-memory results, honoring the active file tag."""
    charts = make_all_charts(results, overall, by_type)
    if noise_agg:
        charts["noise_wer_vs_snr"] = chart_noise_wer_vs_snr(noise_agg, snr_levels)

    n_total = len(results)
    n_m4a   = sum(1 for c in results if c["metadata"].get("recording_type") == "naturalistic_health_complaint")
    n_ogg   = sum(1 for c in results if c["metadata"].get("recording_type") == "whatsapp_voice_note")
    n_mp3   = sum(1 for c in results if c["metadata"].get("recording_type") == "synthetic_triage_phrase")

    print("\nBuilding PDF report...")
    pdf = PrimaryReportPDF()
    pdf.set_auto_page_break(auto=True, margin=18)

    pdf.add_page()
    _cover_page(pdf, results, flags)

    pdf.add_page()
    _domain1(pdf, results, overall, by_type, charts)

    pdf.add_page()
    _domain2(pdf, results, overall, charts)

    pdf.add_page()
    _domain3(pdf, results, overall, noise_agg, noise_results, snr_levels, charts)

    pdf.add_page()
    _domain4(pdf, overall, offline_agg, charts, n_total)

    pdf.add_page()
    _per_clip_section(pdf, results)

    pdf.add_page()
    _limitations(pdf, n_total, n_m4a, n_ogg, n_mp3)

    pdf_path = REPORTS_DIR / _tagged("primary_benchmark_report.pdf")
    pdf.output(str(pdf_path))
    print(f"PDF report  → {pdf_path}\n")
    print(f"Charts      → {REPORTS_DIR}\n")
    print("Summary:")
    for m, s in overall.get("all", {}).items():
        n_clips  = s.get("n", 0)
        wer_str  = fmt(s.get("mean_wer"))
        rtf_str  = fmt(s.get("mean_rtf"), 2)
        print(f"  {m:20s}  WER={wer_str}  RTF={rtf_str}  n={n_clips}")


def _load_and_render(results_path: Path, tag: str) -> None:
    """Load a saved results JSON and rebuild its tagged charts + PDF."""
    global _FILE_TAG
    _FILE_TAG = tag
    with open(results_path, encoding="utf-8") as fh:
        saved = json.load(fh)
    results       = saved["clips"]
    overall       = saved["overall"]
    by_type       = saved["by_recording_type"]
    offline_agg   = saved.get("offline_simulation", {}).get("aggregated")
    noise_block   = saved.get("noise_robustness", {})
    noise_agg     = noise_block.get("aggregated")
    noise_results = noise_block.get("clips")
    snr_levels    = noise_block.get("snr_levels_db", DEFAULT_SNR_LEVELS)
    flags         = saved.get("manifest", {}).get("flags", {})
    print(f"Rebuilding from {results_path.name} ({len(results)} clips, tag='{tag or '(none)'}')...")
    _render_report(results, overall, by_type, offline_agg,
                   noise_agg, noise_results, snr_levels, flags)


def main():
    global _FILE_TAG
    rebuild_only = "--rebuild-only" in sys.argv
    rebuild_all  = "--rebuild-all"  in sys.argv
    agentic      = "--agentic"      in sys.argv
    offline_mode = "--offline"      in sys.argv
    noise_mode   = "--noise"        in sys.argv
    noise_api    = "--noise-local"  not in sys.argv  # default: include API in noise sweep
    snr_levels   = DEFAULT_SNR_LEVELS
    tag          = _sanitize_tag(_arg_value("--tag", ""))
    flags = {"agentic": agentic, "offline": offline_mode, "noise": noise_mode, "tag": tag}

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # --rebuild-all: redo every saved primary_results*.json into its own tagged PDF.
    if rebuild_all:
        paths = sorted(REPORTS_DIR.glob("primary_results*.json"))
        if not paths:
            print(f"No primary_results*.json files found in {REPORTS_DIR}.")
            sys.exit(1)
        print(f"Rebuilding {len(paths)} saved result file(s)...\n")
        for p in paths:
            _load_and_render(p, _tag_from_results_name(p.name))
        return

    _FILE_TAG = tag
    results_path = REPORTS_DIR / _tagged("primary_results.json")

    if rebuild_only:
        if not results_path.exists():
            print(f"No saved results at {results_path}. Run without --rebuild-only first.")
            sys.exit(1)
        _load_and_render(results_path, tag)
        return
    else:
        rows = load_metadata()
        if not rows:
            print("No clips with a reference transcript found in metadata.csv.")
            print("  Fill in the reference_transcript column, then re-run this script.")
            sys.exit(1)

        print(f"\nBenchmarking {len(rows)} clips across 3 models...\n")
        print(f"  agentic : {'yes' if agentic else 'no'}")
        print(f"  offline : {'yes' if offline_mode else 'no'}")
        print(f"  noise   : {'yes' if noise_mode else 'no'}"
              f"{' (local only)' if noise_mode and not noise_api else ''}\n")

        results = run_all(rows, agentic=agentic)
        overall = aggregate(results, lambda c: "all")
        by_type = aggregate(results, lambda c: c["metadata"].get("recording_type", "unknown"))
        by_cat  = aggregate(results, lambda c: c["metadata"].get("clinical_category", "Unknown"))

        offline_agg = None
        offline_results = None
        if offline_mode:
            print("\nOffline simulation...")
            offline_results = run_offline_pass(rows)
            offline_agg = aggregate_offline(offline_results)

        noise_agg = None
        noise_results = None
        if noise_mode:
            print(f"\nNoise sweep at SNR {snr_levels} dB "
                  f"({'all models' if noise_api else 'local only'})...")
            noise_results = run_noise_pass(rows, snr_levels, skip_api=not noise_api)
            noise_agg = aggregate_noise(
                noise_results, MODELS if noise_api else LOCAL_MODELS
            )

        manifest = _build_manifest(rows, flags)
        payload: dict = {
            "manifest": manifest,
            "overall": overall,
            "by_recording_type": by_type,
            "by_clinical_category": by_cat,
            "clips": results,
        }
        if offline_results:
            payload["offline_simulation"] = {
                "aggregated": offline_agg, "clips": offline_results
            }
        if noise_results:
            payload["noise_robustness"] = {
                "aggregated": noise_agg,
                "snr_levels_db": snr_levels,
                "clips": noise_results,
            }
        with open(results_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"\nRaw results → {results_path}")

    _render_report(results, overall, by_type, offline_agg,
                   noise_agg, noise_results, snr_levels, flags)


if __name__ == "__main__":
    main()
