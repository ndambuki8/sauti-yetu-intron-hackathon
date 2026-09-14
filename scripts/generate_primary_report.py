"""Comprehensive benchmark report for data/primary_collection (real health audio).

Covers all four challenge domains:
  1  Linguistic & Core ASR  — WER/CER per model, split by recording type
  2  Agentic Triage Accuracy — topic/urgency/entity scoring (m4a + ogg files)
  3  Code-Switch Robustness  — switch-point WER for annotated sw-en clips
  4  Infrastructure & Latency — RTF, latency distribution, offline penalty

Three recording types:
  naturalistic_health_complaint  — m4a smartphone recordings (15-23s)
  synthetic_triage_phrase        — mp3 short phrases (2-6s)
  whatsapp_voice_note            — ogg/opus WhatsApp PTT recordings (7-31s)

Outputs:
  reports/primary_benchmark_report.pdf
  reports/primary_results.json
  reports/chart_pc_*.png  (5 charts)

Usage (project root, venv active, INTRON_API_KEY set):
  python -m scripts.generate_primary_report
  python -m scripts.generate_primary_report --agentic
  python -m scripts.generate_primary_report --offline
  python -m scripts.generate_primary_report --rebuild-only
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

from backend.benchmark import run_benchmark, run_offline_simulation  # noqa: E402
from backend.config import PROJECT_ROOT, SUPPORTED_LANGUAGES          # noqa: E402

PRIMARY_DIR  = PROJECT_ROOT / "data" / "primary_collection"
REPORTS_DIR  = PROJECT_ROOT / "reports"
MODELS       = ["Intron Sahara", "OpenAI Whisper", "Meta MMS"]
LOCAL_MODELS = ["OpenAI Whisper", "Meta MMS"]

# ── Color palette ─────────────────────────────────────────────────────────────
C = {
    "sahara":   "#1a6b3c",
    "whisper":  "#e07b39",
    "mms":      "#3a7bbf",
    "emergency":"#c0392b",
    "urgent":   "#e67e22",
    "routine":  "#27ae60",
    "header_bg":(26, 82, 118),   # dark teal (r, g, b) for fpdf
    "accent_bg":(240, 248, 255),  # ice blue
    # WER heatmap (0=green … 1=red)
    "wer_good": (200, 235, 200),
    "wer_mid":  (255, 243, 170),
    "wer_bad":  (255, 200, 195),
    # Urgency fills
    "em_fill":  (255, 218, 218),
    "ur_fill":  (255, 243, 215),
    "ro_fill":  (218, 245, 218),
}

MODEL_HEX  = {"Intron Sahara": C["sahara"], "OpenAI Whisper": C["whisper"], "Meta MMS": C["mms"]}
UGY_FILL   = {"EMERGENCY": C["em_fill"], "URGENT": C["ur_fill"], "ROUTINE": C["ro_fill"]}
UGY_LABEL  = {"EMERGENCY": "[EMERGENCY]", "URGENT": "[URGENT]", "ROUTINE": "[ROUTINE]"}

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
        print(f"ERROR: {path} not found. Run bootstrap first:")
        print("  python -m scripts.bootstrap_primary_collection")
        sys.exit(1)
    with open(path, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("filename")]
    existing = []
    for row in rows:
        fpath = PRIMARY_DIR / row["filename"]
        if fpath.exists():
            existing.append(row)
        else:
            print(f"  skipping {row['filename']} (file not found)")
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
        lang = _language_code(row)
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
                               ("slot", ag.get("slot_accuracy")),
                               ("entity", ag.get("entity_error_rate"))):
                if src is not None:
                    bk[mkey].append(float(src))
    return {
        group: {
            model: {
                "mean_wer":           _mean(b["wer"]),
                "mean_cer":           _mean(b["cer"]),
                "mean_latency":       _mean(b["latency"]),
                "mean_rtf":           _mean(b["rtf"]),
                "mean_sp_wer":        _mean(b["sp_wer"]),
                "intent_accuracy":    _mean(b["intent"]),
                "slot_accuracy":      _mean(b["slot"]),
                "entity_error_rate":  _mean(b["entity"]),
                "n": len(b["wer"]),
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


# ─── Charts ───────────────────────────────────────────────────────────────────

def _savefig(fig, name: str) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    p = REPORTS_DIR / name
    fig.savefig(p, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return p


def chart_wer_by_model(overall: dict, by_type: dict) -> Path:
    """Grouped bar: WER by model, split by all three recording types."""
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = range(len(MODELS))
    width = 0.21

    rtype_cfg = [
        ("naturalistic_health_complaint", "m4a naturalistic (15-23s)", 1.0, ""),
        ("whatsapp_voice_note",           "ogg WhatsApp PTT (7-31s)",  0.75, "xx"),
        ("synthetic_triage_phrase",       "mp3 phrase (2-6s)",         0.45, "///"),
    ]
    all_vals = [overall.get("all", {}).get(m, {}).get("mean_wer") for m in MODELS]
    colors_main = [MODEL_HEX[m] for m in MODELS]

    offsets = [-1.5 * width, -0.5 * width, 0.5 * width, 1.5 * width]

    for bi, (rtype, label, alpha, hatch) in enumerate(rtype_cfg):
        raw_vals = [by_type.get(rtype, {}).get(m, {}).get("mean_wer") for m in MODELS]
        # Only plot bars for non-None values
        xs_plot = [xi + offsets[bi] for xi, v in zip(x, raw_vals) if v is not None]
        vals_plot = [v for v in raw_vals if v is not None]
        colors_plot = [c for c, v in zip(colors_main, raw_vals) if v is not None]
        if xs_plot:
            bars = ax.bar(xs_plot, vals_plot, width, label=label, color=colors_plot,
                          alpha=alpha, edgecolor="white", linewidth=0.8, hatch=hatch)
            for bar in bars:
                h = bar.get_height()
                if h is not None and h > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2, h + 0.01, f"{h:.2f}",
                            ha="center", va="bottom", fontsize=6.5, color="#333333")

    # All-clips bar
    xs_all = [xi + offsets[3] for xi, v in zip(x, all_vals) if v is not None]
    vals_all_plot = [v for v in all_vals if v is not None]
    colors_all = [c for c, v in zip(colors_main, all_vals) if v is not None]
    if xs_all:
        bars_all = ax.bar(xs_all, vals_all_plot, width, label="All clips",
                          color=colors_all, alpha=0.85, edgecolor="#555", linewidth=1.0)
        for bar in bars_all:
            h = bar.get_height()
            if h is not None and h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.01, f"{h:.2f}",
                        ha="center", va="bottom", fontsize=6.5, color="#111", fontweight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels([m.replace(" ", "\n") for m in MODELS], fontsize=9)
    ax.set_ylabel("Mean WER  (lower is better)", fontsize=10)
    ax.set_title("Domain 1 — ASR Accuracy by Model & Recording Type\n"
                 "Primary Health Collection  |  Swahili-English, Kenya  |  65 clips",
                 fontsize=10, fontweight="bold")
    ax.set_ylim(0, 1.45)
    ax.axhline(0.3, color="#888", linestyle="--", linewidth=0.7, label="WER = 0.30 target")
    ax.legend(fontsize=8, loc="upper right", ncol=2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor("#fafafa")
    fig.patch.set_facecolor("white")
    return _savefig(fig, "chart_pc_wer_by_model.png")


def chart_rtf(overall: dict) -> Path:
    fig, ax = plt.subplots(figsize=(7, 3.5))
    models  = [m for m in MODELS if overall.get("all", {}).get(m, {}).get("mean_rtf") is not None]
    rtfs    = [overall["all"][m]["mean_rtf"] for m in models]
    lats    = [overall["all"][m].get("mean_latency") or 0 for m in models]
    colors  = [MODEL_HEX[m] for m in models]

    if rtfs:
        bars = ax.barh(models, rtfs, color=colors, edgecolor="white", height=0.5)
        for bar, lat in zip(bars, lats):
            w = bar.get_width()
            ax.text(w + 0.02, bar.get_y() + bar.get_height() / 2,
                    f"RTF {w:.2f}  |  {lat:.1f}s avg",
                    va="center", fontsize=8, color="#333")
        ax.set_xlim(0, max(rtfs) * 1.35)
    else:
        ax.text(0.5, 0.5, "No RTF data", ha="center", transform=ax.transAxes)

    ax.axvline(1.0, color="#c0392b", linestyle="--", linewidth=1.2, label="RTF = 1.0 (real-time)")
    ax.set_xlabel("Real-Time Factor  (lower = faster than real time)", fontsize=9)
    ax.set_title("Domain 4 — Latency & Real-Time Factor\nPrimary Health Collection  |  65 clips",
                 fontsize=10, fontweight="bold")
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor("#fafafa")
    return _savefig(fig, "chart_pc_rtf.png")


def chart_urgency_pie(results: list[dict]) -> Path:
    # Only annotated clips (m4a + ogg)
    annotated = [c for c in results
                 if c["metadata"].get("recording_type") in
                    ("naturalistic_health_complaint", "whatsapp_voice_note")
                 and c["metadata"].get("expected_urgency", "").strip()]
    counts = {"EMERGENCY": 0, "URGENT": 0, "ROUTINE": 0, "Unknown": 0}
    for clip in annotated:
        u = clip["metadata"].get("expected_urgency", "").strip()
        if u in counts:
            counts[u] += 1
        else:
            counts["Unknown"] += 1

    labels, sizes, pie_colors = [], [], []
    color_map = {"EMERGENCY": C["emergency"], "URGENT": C["urgent"],
                 "ROUTINE": C["routine"], "Unknown": "#aaaaaa"}
    for label, count in counts.items():
        if count > 0:
            labels.append(f"{label}\n({count} clips)")
            sizes.append(count)
            pie_colors.append(color_map[label])

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    # Left: urgency pie
    ax = axes[0]
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=pie_colors,
        autopct="%1.0f%%", startangle=140,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5},
        textprops={"fontsize": 9},
    )
    for at in autotexts:
        at.set_fontsize(9); at.set_fontweight("bold"); at.set_color("white")
    ax.set_title("Triage Urgency Distribution\n(annotated health clips)",
                 fontsize=10, fontweight="bold", pad=12)

    # Right: recording type breakdown
    ax2 = axes[1]
    type_counts = {}
    for clip in results:
        rtype = clip["metadata"].get("recording_type", "unknown")
        label = {"naturalistic_health_complaint": "m4a naturalistic",
                 "whatsapp_voice_note": "ogg WhatsApp PTT",
                 "synthetic_triage_phrase": "mp3 short phrase"}.get(rtype, rtype)
        type_counts[label] = type_counts.get(label, 0) + 1
    type_colors = ["#1a6b3c", "#3a7bbf", "#e07b39", "#aaaaaa"]
    ax2.pie(list(type_counts.values()), labels=[f"{k}\n({v})" for k, v in type_counts.items()],
            colors=type_colors[:len(type_counts)], autopct="%1.0f%%", startangle=90,
            wedgeprops={"edgecolor": "white", "linewidth": 1.5},
            textprops={"fontsize": 9})
    ax2.set_title("Recording Type Distribution\n(65 total clips)",
                  fontsize=10, fontweight="bold", pad=12)

    fig.suptitle("Domain 2 — Dataset Composition", fontsize=11, fontweight="bold", y=1.01)
    fig.patch.set_facecolor("white")
    return _savefig(fig, "chart_pc_urgency_pie.png")


def chart_category_wer(results: list[dict]) -> Path:
    """WER by clinical category, grouped by model — m4a files only."""
    cats: dict[str, dict[str, list[float]]] = {}
    for clip in results:
        if clip["metadata"].get("recording_type") != "naturalistic_health_complaint":
            continue
        cat = clip["metadata"].get("clinical_category", "Unknown")
        for r in clip["benchmark"]["results"]:
            if r.get("wer") is not None:
                cats.setdefault(cat, {}).setdefault(r["model"], []).append(r["wer"])

    if not cats:
        # fallback empty chart
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No m4a data", ha="center", transform=ax.transAxes)
        return _savefig(fig, "chart_pc_category_wer.png")

    sorted_cats = sorted(cats.keys())
    n_cats = len(sorted_cats)
    n_models = len(MODELS)
    width = 0.8 / n_models

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
    ax.set_ylabel("Mean WER", fontsize=9)
    ax.set_title("Domain 2 & 3 — WER by Clinical Category (naturalistic m4a)\n"
                 "Swahili-English Healthcare Complaints, Kenya",
                 fontsize=10, fontweight="bold")
    ax.set_ylim(0, 1.1)
    ax.axhline(0.3, color="#888", linestyle="--", linewidth=0.7)
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor("#fafafa")
    return _savefig(fig, "chart_pc_category_wer.png")


def chart_wer_vs_duration(results: list[dict]) -> Path:
    """Scatter: WER vs audio duration, colored by model and shaped by recording type."""
    fig, ax = plt.subplots(figsize=(8, 4))
    markers = {"naturalistic_health_complaint": "o", "synthetic_triage_phrase": "^"}

    for clip in results:
        rtype = clip["metadata"].get("recording_type", "synthetic_triage_phrase")
        marker = markers.get(rtype, "s")
        for r in clip["benchmark"]["results"]:
            dur = r.get("audio_duration_seconds")
            wer = r.get("wer")
            if dur and wer is not None:
                ax.scatter(dur, wer, color=MODEL_HEX.get(r["model"], "#888"),
                           marker=marker, alpha=0.7, s=45, edgecolors="white", linewidths=0.6)

    # Legend for models
    legend_handles = [
        mpatches.Patch(color=MODEL_HEX[m], label=m) for m in MODELS
    ] + [
        plt.Line2D([0], [0], marker="o", color="grey", linestyle="None", markersize=7, label="naturalistic m4a"),
        plt.Line2D([0], [0], marker="^", color="grey", linestyle="None", markersize=7, label="phrase mp3"),
    ]
    ax.legend(handles=legend_handles, fontsize=8, loc="upper right", ncol=2)

    ax.axhline(0.3, color="#888", linestyle="--", linewidth=0.7, alpha=0.7)
    ax.set_xlabel("Audio Duration (seconds)", fontsize=9)
    ax.set_ylabel("WER", fontsize=9)
    ax.set_title("WER vs Audio Duration — Primary Health Collection\n"
                 "(circles = naturalistic m4a; triangles = triage phrase mp3)",
                 fontsize=10, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor("#fafafa")
    return _savefig(fig, "chart_pc_wer_scatter.png")


def make_all_charts(results: list[dict], overall: dict, by_type: dict) -> dict[str, Path]:
    print("\nGenerating charts...")
    charts = {
        "wer_by_model":    chart_wer_by_model(overall, by_type),
        "rtf":             chart_rtf(overall),
        "urgency_pie":     chart_urgency_pie(results),
        "category_wer":    chart_category_wer(results),
        "wer_scatter":     chart_wer_vs_duration(results),
    }
    for name, path in charts.items():
        print(f"  {name:20s} → {path.name}")
    return charts


# ─── PDF ─────────────────────────────────────────────────────────────────────

def _latin1(text: str) -> str:
    return str(text).encode("latin-1", "replace").decode("latin-1")


def fmt(v, p: int = 4) -> str:
    if v is None:
        return "—"
    return f"{v:.{p}f}" if isinstance(v, float) else str(v)


def _wer_fill(wer) -> tuple:
    if wer is None:
        return (235, 235, 235)
    if wer < 0.25:
        return C["wer_good"]
    if wer < 0.45:
        return C["wer_mid"]
    return C["wer_bad"]


class PrimaryReportPDF(FPDF):
    """Custom FPDF subclass with rich formatting helpers."""

    # ── Chrome ───────────────────────────────────────────────────────────────
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

    # ── Typography helpers ────────────────────────────────────────────────────
    def cover_title(self, text: str):
        self.set_font("Helvetica", "B", 20)
        self.set_text_color(*C["header_bg"])
        self.set_x(self.l_margin)
        self.multi_cell(0, 10, _latin1(text), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0)
        self.ln(2)

    def section_header(self, text: str):
        """Full-width section banner with dark background."""
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

    def img(self, path: Path, w: int = 168):
        if path and path.exists():
            self.set_x(self.l_margin)
            self.image(str(path), w=w)
            self.ln(4)

    # ── Table helpers ─────────────────────────────────────────────────────────
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
        """Table with WER columns auto-coloured by value."""
        self._th(headers, widths)
        for row in rows:
            row_fills = [(255, 255, 255)] * len(row)
            # Colour every cell that looks like a WER float (0.xx)
            for ci, val in enumerate(row):
                try:
                    f = float(str(val).replace("—", ""))
                    if 0 <= f <= 1:
                        row_fills[ci] = _wer_fill(f)
                except ValueError:
                    pass
            self._td(row, widths, fills=row_fills, bold_first=True)
        self.ln(2)


# ─── Report sections ──────────────────────────────────────────────────────────

def _cover_page(pdf: PrimaryReportPDF, results: list[dict], flags: dict):
    n_m4a = sum(1 for c in results if c["metadata"].get("recording_type") == "naturalistic_health_complaint")
    n_ogg = sum(1 for c in results if c["metadata"].get("recording_type") == "whatsapp_voice_note")
    n_mp3 = sum(1 for c in results if c["metadata"].get("recording_type") == "synthetic_triage_phrase")
    annotated = sum(1 for c in results if c["metadata"].get("expected_topic", "").strip())
    sw_annotated = sum(1 for c in results
                       if c["benchmark"].get("switch_points"))

    pdf.cover_title("Primary Health Collection\nCode-Switch ASR & Triage Benchmark")
    pdf.body(
        f"Project: Sauti Yetu  —  Agentic voice triage for Swahili-English health consultations\n"
        f"Challenge: Sahara CodeSwitch Africa Challenge 2026  (MLC Africa x Intron)\n"
        f"Report generated: {date.today().isoformat()}",
        size=10,
    )
    pdf.ln(2)
    pdf.kv_row("Dataset", "data/primary_collection/  (real-world health recordings, Kenya)")
    pdf.kv_row("Language pairs", "Swahili-English (all clips)")
    pdf.kv_row("Total clips", f"{len(results)}  ({n_m4a} m4a naturalistic  |  {n_ogg} ogg WhatsApp PTT  |  {n_mp3} mp3 phrase)")
    pdf.kv_row("Annotated for agentic scoring", f"{annotated} clips with expected_topic / entities")
    pdf.kv_row("Switch-point annotated", f"{sw_annotated} clips with language boundary annotations")
    pdf.kv_row("Models benchmarked", "Intron Sahara  |  OpenAI Whisper  |  Meta MMS mms-1b-all")
    pdf.kv_row("Reference transcripts", "Sahara bootstrap transcription (proxy ground truth)")
    pdf.kv_row("Agentic mode", "Enabled" if flags.get("agentic") else "Disabled (re-run with --agentic)")
    pdf.kv_row("Offline pass", "Included" if flags.get("offline") else "Not run (re-run with --offline)")
    pdf.ln(4)
    pdf.body(
        "NOTE ON METHODOLOGY: Because the primary collection has no hand-written ground-truth\n"
        "transcripts, Intron Sahara transcriptions (bootstrap phase) serve as the reference.\n"
        "This means Sahara WER measures its own API variability, while Whisper and MMS WER\n"
        "measure divergence from the Sahara reference. All three model transcripts are shown\n"
        "side-by-side in Section 5 for independent verification.\n\n"
        "RECORDING TYPES:\n"
        "  m4a  — Swahili-English health scenarios, smartphone, indoor quiet (15-23s)\n"
        "  ogg  — WhatsApp Push-to-Talk voice notes, smartphone, ambient noise (7-31s)\n"
        "  mp3  — Short triage phrases, laptop microphone, studio quiet (2-6s)",
        size=8,
    )


def _domain1(pdf: PrimaryReportPDF, results: list[dict], overall: dict,
             by_type: dict, charts: dict):
    pdf.section_header("DOMAIN 1  —  Linguistic & Core ASR Performance")
    pdf.body(
        "Three models transcribed identical audio converted to 16 kHz mono WAV. "
        "WER and CER are computed after identical normalization (lowercase, punctuation "
        "removed, whitespace collapsed). CER is reported alongside WER as it is more "
        "robust for Swahili (agglutinative morphology, code-switch borrowings).\n\n"
        "The primary collection contains two recording types:\n"
        "  m4a — naturalistic health complaints, 15-23s, full patient description\n"
        "  mp3 — short synthetic triage phrases, 2-6s, single utterance"
    )

    pdf.subsection("1a. Overall results (all 50 clips)")
    headers = ["Model", "WER", "CER", "Latency (s)", "RTF", "n clips"]
    widths  = [52, 22, 22, 28, 22, 18]
    rows = [
        [m,
         fmt(s.get("mean_wer")), fmt(s.get("mean_cer")),
         fmt(s.get("mean_latency"), 2), fmt(s.get("mean_rtf"), 2),
         str(s.get("n", "—"))]
        for m, s in overall.get("all", {}).items()
    ]
    pdf.wer_table(headers, rows, widths)

    pdf.subsection("1b. By recording type")
    for rtype, label in [
        ("naturalistic_health_complaint", "Naturalistic health complaints (m4a, 15-23s)"),
        ("whatsapp_voice_note",           "WhatsApp PTT voice notes (ogg/opus, 7-31s)"),
        ("synthetic_triage_phrase",       "Short triage phrases (mp3, 2-6s)"),
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
    pdf.section_header("DOMAIN 2  —  Downstream Agentic Task Accuracy")
    pdf.body(
        "For annotated m4a and ogg clips the pipeline is evaluated on three agentic metrics:\n"
        "  Intent accuracy  — exact normalized match on expected_topic\n"
        "  Slot accuracy    — mean exact match over expected intake card fields\n"
        "  Entity EER       — (missing + spurious entities) / (gold + spurious)\n\n"
        "Entities in expected_entities were derived from clinical scenario filenames "
        "and should be verified after manual listening. The agentic scoring path runs "
        "through run_triage() using Sahara's telehealth extractions (--agentic mode) "
        "or transcript-only fallback for local models."
    )
    pdf.img(charts.get("urgency_pie"))

    # Agentic summary if available
    any_agentic = any(
        any(r.get("agentic") for r in c["benchmark"]["results"]) for c in results
    )
    if any_agentic:
        pdf.subsection("2a. Agentic accuracy summary")
        headers = ["Model", "Intent Acc.", "Slot Acc.", "Entity EER", "n"]
        widths  = [52, 30, 30, 30, 15]
        rows = []
        for m, s in overall.get("all", {}).items():
            if any(s.get(k) is not None for k in ("intent_accuracy", "slot_accuracy", "entity_error_rate")):
                rows.append([m, fmt(s.get("intent_accuracy")), fmt(s.get("slot_accuracy")),
                             fmt(s.get("entity_error_rate")), str(s.get("n", "—"))])
        if rows:
            pdf.table(headers, rows, widths)
    else:
        pdf.body("Re-run with --agentic to populate intent / slot / entity metrics.")

    pdf.subsection("2b. Per-clip triage annotations (annotated health clips)")
    headers2 = ["File", "Type", "Category", "Urgency", "Expected topic"]
    widths2   = [38, 14, 28, 22, 53]
    annotated = [c for c in results if c["metadata"].get("expected_topic", "").strip()]
    if annotated:
        ann_rows = []
        ann_fills = []
        for clip in annotated:
            urg = clip["metadata"].get("expected_urgency", "")
            fill = UGY_FILL.get(urg, (245, 245, 245))
            row_f = [fill, fill, fill, fill]
            rtype = clip["metadata"].get("recording_type", "")
        type_short = {"naturalistic_health_complaint": "m4a",
                      "whatsapp_voice_note": "ogg",
                      "synthetic_triage_phrase": "mp3"}.get(rtype, "?")
        fname = (clip["metadata"]["filename"]
                 .replace("sample_sw_en_", "").replace(".m4a", "")
                 .replace("WhatsApp Ptt 2026-09-14 at ", "WA ").replace(".ogg", ""))
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


def _domain3(pdf: PrimaryReportPDF, results: list[dict], overall: dict):
    pdf.section_header("DOMAIN 3  —  Code-Switch Robustness & In-The-Wild Conditions")
    pdf.body(
        "All m4a clips are real Swahili-English code-switched health complaints recorded "
        "in Kenya — the primary target deployment environment for Sauti Yetu. This "
        "represents genuine 'in-the-wild' data: natural conversational pace, code-switch "
        "patterns from patient to medical English terminology, smartphone microphone, "
        "and indoor acoustic conditions.\n\n"
        "Switch points are annotated as approximate boundaries (one per clip) where the "
        "speaker transitions from Swahili to English medical terms. The ±3-token window "
        "WER at these boundaries isolates model degradation at the exact code-switch "
        "moment — the hardest task for generic ASR."
    )

    # Switch-point summary
    clips_with_sp = [c for c in results if c["benchmark"].get("switch_points")]
    pdf.subsection(f"3a. Switch-point WER  ({len(clips_with_sp)} annotated clips)")

    if clips_with_sp:
        headers = ["Model", "Mean SP-WER", "Overall WER", "Delta (SP - overall)"]
        widths  = [52, 35, 30, 45]
        sp_rows = []
        for m, s in overall.get("all", {}).items():
            sp_wer = s.get("mean_sp_wer")
            ov_wer = s.get("mean_wer")
            delta = round(sp_wer - ov_wer, 4) if (sp_wer is not None and ov_wer is not None) else None
            sp_rows.append([m, fmt(sp_wer), fmt(ov_wer),
                            ("+" if delta and delta > 0 else "") + fmt(delta)])
        pdf.wer_table(headers, sp_rows, widths)
        pdf.body(
            "A positive Delta means the model degrades at code-switch boundaries relative "
            "to its overall WER — a known failure mode for models trained primarily on "
            "monolingual data. Sahara, trained on African code-switched speech, should "
            "show a smaller Delta than the local models."
        )
    else:
        pdf.body(
            "No switch-point annotations are present yet. To activate this metric, "
            "populate the switch_points column in metadata.csv with token_index boundaries "
            "after manually verifying each recording."
        )

    pdf.subsection("3b. Acoustic conditions")
    pdf.body(
        "All primary collection clips were recorded on smartphones (m4a) or laptop "
        "microphones (mp3) in quiet indoor conditions. To benchmark noise robustness, "
        "run: python -m scripts.generate_benchmark_report --noise"
    )


def _domain4(pdf: PrimaryReportPDF, overall: dict, offline_agg: dict | None, charts: dict):
    pdf.section_header("DOMAIN 4  —  Infrastructure & Real-Time Performance")
    pdf.body(
        "RTF (Real-Time Factor) = wall-clock latency / audio duration. RTF < 1.0 means "
        "the model processes audio faster than real time — a hard requirement for "
        "interactive voice triage bots. Intron Sahara latency includes network "
        "round-trip; local model latency depends on hardware (measured on the benchmark "
        "machine). GPU acceleration would reduce Whisper and MMS RTF substantially."
    )

    pdf.subsection("4a. Latency & RTF")
    headers = ["Model", "Mean WER", "Mean RTF", "Mean latency (s)", "n"]
    widths  = [52, 28, 28, 38, 15]
    rows = [
        [m, fmt(s.get("mean_wer")), fmt(s.get("mean_rtf")), fmt(s.get("mean_latency"), 2), str(s.get("n", "—"))]
        for m, s in overall.get("all", {}).items()
    ]
    pdf.wer_table(headers, rows, widths)
    pdf.img(charts.get("rtf"))

    pdf.subsection("4b. Offline / low-connectivity simulation")
    if offline_agg is None:
        pdf.body("Not run in this pass. Re-run with --offline to include local-only results.")
        return

    pdf.body(
        "The offline simulation runs ONLY Whisper and MMS (no Sahara API calls), "
        "simulating operation in remote / low-connectivity environments. "
        "The offline penalty is the WER gap between Sahara and the best local model."
    )
    headers_o = ["Model (offline)", "WER", "CER", "RTF", "n"]
    widths_o  = [52, 28, 28, 28, 15]
    rows_o = [
        [m, fmt(s.get("mean_wer")), fmt(s.get("mean_cer")), fmt(s.get("mean_rtf")), str(s.get("n", "—"))]
        for m, s in offline_agg.items()
    ]
    pdf.wer_table(headers_o, rows_o, widths_o)

    sahara_wer = overall.get("all", {}).get("Intron Sahara", {}).get("mean_wer")
    best_local  = min((s["mean_wer"] for s in offline_agg.values() if s.get("mean_wer") is not None), default=None)
    if sahara_wer is not None and best_local is not None:
        penalty = round(best_local - sahara_wer, 4)
        pdf.body(
            f"Offline penalty: {fmt(best_local)} (best local) - {fmt(sahara_wer)} (Sahara) = "
            f"{'+'if penalty>0 else ''}{fmt(penalty)} WER points."
        )


def _per_clip_section(pdf: PrimaryReportPDF, results: list[dict]):
    pdf.section_header("SECTION 5  —  Per-Clip Transcripts & Model Outputs")
    pdf.body(
        "Clips are grouped: naturalistic m4a first (colour-coded by urgency), then "
        "short-phrase mp3. All three model transcripts are shown side-by-side; "
        "WER is against the Sahara bootstrap reference."
    )

    # ── m4a + ogg clips (colour-coded by urgency) ──
    rich_clips = [c for c in results if c["metadata"].get("recording_type") in
                  ("naturalistic_health_complaint", "whatsapp_voice_note")]
    m4a_clips = [c for c in rich_clips if c["metadata"].get("recording_type") == "naturalistic_health_complaint"]
    ogg_clips = [c for c in rich_clips if c["metadata"].get("recording_type") == "whatsapp_voice_note"]

    if m4a_clips:
        pdf.subsection(f"5a. Naturalistic health complaints  ({len(m4a_clips)} m4a clips)")
        for clip in m4a_clips:
            meta = clip["metadata"]
            urg  = meta.get("expected_urgency", "")
            fill = UGY_FILL.get(urg, (245, 245, 245))
            label = UGY_LABEL.get(urg, "")

            # Clip header
            pdf.set_fill_color(*fill)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_x(pdf.l_margin)
            header_text = (f"{label}  {meta['filename'][:38]}"
                           f"  |  {meta.get('clinical_category', '')}  |  {meta.get('noise_condition', '')}")
            pdf.cell(0, 7, _latin1(header_text), border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

            # Reference
            pdf.set_fill_color(248, 248, 248)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_x(pdf.l_margin)
            ref_text = f"Reference (Sahara bootstrap): {meta.get('reference_transcript', '')}"
            pdf.multi_cell(0, 5, _latin1(ref_text[:240]), border="LR", fill=True,
                           new_x="LMARGIN", new_y="NEXT")

            # Model outputs
            for r in clip["benchmark"]["results"]:
                if r.get("error"):
                    line = f"  {r['model']}: ERROR — {r['error'][:60]}"
                else:
                    wer = fmt(r.get("wer"))
                    cer = fmt(r.get("cer"))
                    rtf = fmt(r.get("rtf"), 2)
                    lat = fmt(r.get("latency_seconds"), 1)
                    text = (r.get("transcript") or "(empty)")[:140]
                    line = f"  {r['model']:16s}  WER {wer}  CER {cer}  RTF {rtf}  ({lat}s):  {text}"
                pdf.set_font("Helvetica", "", 7.5)
                pdf.set_fill_color(255, 255, 255)
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 4.8, _latin1(line), border="LR", fill=True,
                               new_x="LMARGIN", new_y="NEXT")

                # Switch-point detail
                sp = r.get("switch_point", {})
                if sp.get("wer") is not None:
                    pdf.set_font("Helvetica", "I", 7)
                    pdf.set_x(pdf.l_margin + 4)
                    pdf.cell(0, 4.5, _latin1(
                        f"    Switch-point WER: {fmt(sp['wer'])}  ({sp['count']} boundary)"),
                        border=0, new_x="LMARGIN", new_y="NEXT")

                # Agentic detail
                ag = r.get("agentic")
                if ag:
                    pdf.set_font("Helvetica", "I", 7)
                    pdf.set_x(pdf.l_margin + 4)
                    pdf.cell(0, 4.5, _latin1(
                        f"    Agentic: intent={fmt(ag.get('intent_correct'))}  "
                        f"entity EER={fmt(ag.get('entity_error_rate'))}  "
                        f"topic={ag.get('topic', '—')[:35]}"),
                        border=0, new_x="LMARGIN", new_y="NEXT")

            # Close border + spacing
            pdf.set_fill_color(255, 255, 255)
            pdf.set_x(pdf.l_margin)
            pdf.cell(0, 2, "", border="LBR", fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)

    # ── ogg WhatsApp clips ──
    if ogg_clips:
        pdf.subsection(f"5b. WhatsApp PTT voice notes  ({len(ogg_clips)} ogg clips)")
        for clip in ogg_clips:
            meta = clip["metadata"]
            urg  = meta.get("expected_urgency", "")
            fill = UGY_FILL.get(urg, (235, 235, 235))
            label = UGY_LABEL.get(urg, "[?]")
            pdf.set_fill_color(*fill)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_x(pdf.l_margin)
            cat = meta.get("clinical_category", "")
            noise = meta.get("noise_condition", "")
            header_text = f"{label}  {meta['filename'][:42]}  |  {cat}"
            pdf.cell(0, 7, _latin1(header_text), border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.set_fill_color(248, 248, 248)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_x(pdf.l_margin)
            ref_text = f"Reference (Sahara): {meta.get('reference_transcript', '')}"
            pdf.multi_cell(0, 5, _latin1(ref_text[:230]), border="LR", fill=True,
                           new_x="LMARGIN", new_y="NEXT")
            for r in clip["benchmark"]["results"]:
                if r.get("error"):
                    line = f"  {r['model']}: ERROR — {r['error'][:60]}"
                else:
                    line = (f"  {r['model']:16s}  WER {fmt(r.get('wer'))}  "
                            f"CER {fmt(r.get('cer'))}  RTF {fmt(r.get('rtf'),2)}  "
                            f"({fmt(r.get('latency_seconds'),1)}s):  "
                            f"{(r.get('transcript') or '(empty)')[:130]}")
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
            pdf.set_fill_color(255, 255, 255)
            pdf.set_x(pdf.l_margin)
            pdf.cell(0, 2, "", border="LBR", fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)

    # ── mp3 clips ──
    mp3_clips = [c for c in results if c["metadata"].get("recording_type") == "synthetic_triage_phrase"]
    if mp3_clips:
        pdf.subsection(f"5c. Short triage phrases  ({len(mp3_clips)} mp3 clips)")
        headers = ["File", "Ref (Sahara)", "Sahara WER", "Whisper WER", "MMS WER", "Best"]
        widths  = [28, 58, 22, 22, 22, 15]
        rows_mp3, fills_mp3 = [], []
        for clip in mp3_clips:
            meta = clip["metadata"]
            ref  = (meta.get("reference_transcript") or "")[:40]
            wers = {r["model"]: r.get("wer") for r in clip["benchmark"]["results"]}
            best = clip["benchmark"].get("best_model", "—")
            best_short = best.split()[0] if best else "—"
            rows_mp3.append([
                meta["filename"].replace("kelvin_sample_", "ks_"),
                ref,
                fmt(wers.get("Intron Sahara")),
                fmt(wers.get("OpenAI Whisper")),
                fmt(wers.get("Meta MMS")),
                best_short,
            ])
            fills_mp3.append([
                (245, 245, 245),
                (255, 255, 255),
                _wer_fill(wers.get("Intron Sahara")),
                _wer_fill(wers.get("OpenAI Whisper")),
                _wer_fill(wers.get("Meta MMS")),
                (220, 240, 220),
            ])
        pdf.table(headers, rows_mp3, widths, fills=fills_mp3)


def _limitations(pdf: PrimaryReportPDF, n_total: int):
    pdf.section_header("SECTION 6  —  Limitations & Bias Notes")
    pdf.body(
        f"1. PROXY REFERENCE: Reference transcripts were generated by Sahara (bootstrap), "
        f"not hand-written. Sahara WER measures API variability; Whisper and MMS WER "
        f"measures divergence from Sahara — not from human ground truth. Manual "
        f"transcription of at least the m4a files is recommended before submission.\n\n"
        f"2. SAMPLE SIZE: {n_total} clips (20 m4a, 30 mp3). The m4a set covers 19 "
        f"clinical scenarios but only 1 speaker (Kelvin). Speaker diversity bias is real — "
        f"results may not generalise to other Swahili-English speakers or accents.\n\n"
        f"3. SWITCH-POINT ANNOTATIONS: Approximate boundaries set at token_index ~4-5; "
        f"these should be verified by listening to each clip and adjusting the token_index "
        f"to match the exact word where the language changes.\n\n"
        f"4. ENTITY ANNOTATIONS: Expected entities are derived from clip filenames, not "
        f"from manual transcript review. They represent the clinical domain of each clip, "
        f"not necessarily the exact words spoken.\n\n"
        f"5. HARDWARE DEPENDENCY: Local model (Whisper, MMS) latency is CPU-bound; "
        f"RTF would improve significantly with GPU. Sahara includes network round-trip.\n\n"
        f"6. NOISE CONDITIONS: All clips recorded in quiet indoor environments. "
        f"Real clinic deployment will include background noise, overlapping voices, "
        f"and variable microphone quality — run the noise sweep (--noise) to assess."
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

def _build_manifest(rows: list[dict], flags: dict) -> dict:
    import platform as pf
    switch_annotated = sum(bool(_json_field(r, "switch_points", [])) for r in rows)
    downstream_ann   = sum(bool(r.get("expected_topic", "").strip()) for r in rows)
    return {
        "schema_version": "1.0-primary",
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
        "reference_note": "Sahara bootstrap transcription used as proxy ground truth",
        "collection": "data/primary_collection",
    }


def main():
    rebuild_only = "--rebuild-only" in sys.argv
    agentic      = "--agentic"      in sys.argv
    offline_mode = "--offline"      in sys.argv
    flags = {"agentic": agentic, "offline": offline_mode}

    results_path = REPORTS_DIR / "primary_results.json"
    pdf_path     = REPORTS_DIR / "primary_benchmark_report.pdf"

    if rebuild_only:
        if not results_path.exists():
            print(f"No saved results at {results_path}. Run without --rebuild-only first.")
            sys.exit(1)
        with open(results_path, encoding="utf-8") as fh:
            saved = json.load(fh)
        results     = saved["clips"]
        overall     = saved["overall"]
        by_type     = saved["by_recording_type"]
        offline_agg = saved.get("offline_simulation", {}).get("aggregated")
        print(f"Rebuilding from {results_path} ({len(results)} clips)...")
    else:
        rows = load_metadata()
        if not rows:
            print("No clips found. Run bootstrap first:")
            print("  python -m scripts.bootstrap_primary_collection")
            sys.exit(1)

        print(f"\nBenchmarking {len(rows)} clips across 3 models...\n")
        print(f"  agentic : {'yes' if agentic else 'no'}")
        print(f"  offline : {'yes' if offline_mode else 'no'}\n")

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

        manifest = _build_manifest(rows, flags)
        REPORTS_DIR.mkdir(exist_ok=True)
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
        with open(results_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"\nRaw results → {results_path}")

    charts = make_all_charts(results, overall, by_type)

    # Build PDF
    print("\nBuilding PDF report...")
    pdf = PrimaryReportPDF()
    pdf.set_auto_page_break(auto=True, margin=18)

    # Cover
    pdf.add_page()
    _cover_page(pdf, results, flags)

    # Domain 1
    pdf.add_page()
    _domain1(pdf, results, overall, by_type, charts)

    # Domain 2
    pdf.add_page()
    _domain2(pdf, results, overall, charts)

    # Domain 3
    pdf.add_page()
    _domain3(pdf, results, overall)

    # Domain 4
    pdf.add_page()
    _domain4(pdf, overall, offline_agg, charts)

    # Per-clip
    pdf.add_page()
    _per_clip_section(pdf, results)

    # Limitations
    pdf.add_page()
    _limitations(pdf, len(results))

    pdf.output(str(pdf_path))
    print(f"PDF report  → {pdf_path}\n")
    print("All done. Summary:")
    for m, s in overall.get("all", {}).items():
        print(f"  {m:20s}  WER={fmt(s.get('mean_wer'))}  RTF={fmt(s.get('mean_rtf'), 2)}")


if __name__ == "__main__":
    main()
