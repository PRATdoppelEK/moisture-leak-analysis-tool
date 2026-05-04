"""
Analysis pipeline, report generation, and visualization.
Author: Prateek Gaur
"""

import os
import json
import logging
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from typing import List, Dict

from leak_detector import (
    MoistureLeakDetector, SignalProcessor, LeakEvent,
    AnalysisReport, LeakSeverity, ComponentZone
)

logger = logging.getLogger(__name__)

SEVERITY_COLORS = {
    LeakSeverity.NONE:     "#2ecc71",
    LeakSeverity.LOW:      "#f1c40f",
    LeakSeverity.MODERATE: "#e67e22",
    LeakSeverity.HIGH:     "#e74c3c",
    LeakSeverity.CRITICAL: "#8e44ad",
}


# ── Synthetic Data Generator ──────────────────────────────────────────────────

def generate_synthetic_data(
    component_id: str = "MOTOR_001",
    n_hours: int = 48,
    dt_minutes: float = 1.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate realistic motor sensor data with injected leak events."""
    rng = np.random.default_rng(seed)
    n   = int(n_hours * 60 / dt_minutes)
    t   = pd.date_range("2024-01-15 00:00", periods=n, freq=f"{int(dt_minutes)}min")

    # Baseline signals
    temp     = 35 + 10 * np.sin(2 * np.pi * np.arange(n) / (24 * 60)) + rng.normal(0, 0.5, n)
    humidity = 45 + 5  * np.sin(2 * np.pi * np.arange(n) / (12 * 60)) + rng.normal(0, 1, n)
    pressure = 1.01 + 0.005 * rng.normal(0, 1, n)
    insul    = np.full(n, 800.0) + rng.normal(0, 20, n)

    # Inject leak event 1: gradual at hour 12 (moderate)
    s1, e1 = int(12 * 60), int(16 * 60)
    leak1_profile = np.linspace(0, 35, e1 - s1)
    humidity[s1:e1]  += leak1_profile
    insul[s1:e1]     -= np.linspace(0, 600, e1 - s1)
    temp[s1:e1]      -= np.linspace(0, 5, e1 - s1)

    # Inject leak event 2: sudden at hour 30 (critical)
    s2, e2 = int(30 * 60), int(33 * 60)
    humidity[s2:e2]  += 50 + rng.normal(0, 2, e2 - s2)
    insul[s2:e2]     = np.maximum(5, insul[s2:e2] - 790)
    temp[s2:e2]      -= 8

    humidity = np.clip(humidity, 20, 100)
    insul    = np.clip(insul, 1, 2000)

    return pd.DataFrame({
        "timestamp":       t,
        "humidity_rh":     humidity,
        "temperature_c":   temp,
        "pressure_bar":    pressure,
        "insulation_kohm": insul,
        "component_id":    component_id,
    })


# ── Visualization ─────────────────────────────────────────────────────────────

def plot_analysis(
    df: pd.DataFrame,
    events: List[LeakEvent],
    features: pd.DataFrame,
    title: str = "Moisture Leak Analysis",
    save_path: str = "",
):
    fig = plt.figure(figsize=(15, 12))
    fig.suptitle(title, fontsize=14, fontweight="bold")
    gs = gridspec.GridSpec(4, 1, figure=fig, hspace=0.4)

    axes = [fig.add_subplot(gs[i]) for i in range(4)]
    t = df["timestamp"]

    # Shade event regions on all axes
    for event in events:
        color = SEVERITY_COLORS.get(event.severity, "gray")
        for ax in axes:
            ax.axvspan(event.start_time, event.end_time, alpha=0.15, color=color, zorder=0)

    # Panel 1: Humidity
    axes[0].plot(t, df["humidity_rh"], color="steelblue", linewidth=1)
    axes[0].plot(t, features["humidity_smooth"], color="navy", linewidth=1.5, linestyle="--", label="Smoothed")
    axes[0].axhline(70, color="orange", linestyle=":", linewidth=1, label="Moderate threshold")
    axes[0].axhline(85, color="red",    linestyle=":", linewidth=1, label="High threshold")
    axes[0].set_ylabel("Humidity [%RH]"); axes[0].set_title("Relative Humidity")
    axes[0].legend(fontsize=8); axes[0].grid(alpha=0.3)

    # Panel 2: Temperature + Dew Point
    axes[1].plot(t, df["temperature_c"],     color="darkred",   label="Temperature")
    axes[1].plot(t, features["dew_point"],   color="royalblue", linestyle="--", label="Dew Point")
    axes[1].fill_between(t, df["temperature_c"], features["dew_point"],
                          where=df["temperature_c"] < features["dew_point"],
                          alpha=0.3, color="purple", label="Condensation zone")
    axes[1].set_ylabel("Temperature [°C]"); axes[1].set_title("Temperature vs Dew Point")
    axes[1].legend(fontsize=8); axes[1].grid(alpha=0.3)

    # Panel 3: Insulation Resistance
    axes[2].plot(t, df["insulation_kohm"], color="green", linewidth=1)
    axes[2].axhline(200, color="orange", linestyle=":", label="Moderate alarm")
    axes[2].axhline(50,  color="red",    linestyle=":", label="High alarm")
    axes[2].axhline(10,  color="purple", linestyle=":", label="Critical alarm")
    axes[2].set_ylabel("Insulation [kΩ]"); axes[2].set_title("Insulation Resistance")
    axes[2].legend(fontsize=8); axes[2].grid(alpha=0.3)
    axes[2].set_yscale("log")

    # Panel 4: Condensation Margin
    axes[3].plot(t, features["condensation_margin"], color="teal")
    axes[3].axhline(0, color="red", linestyle="--", linewidth=1.5, label="Condensation threshold")
    axes[3].axhline(2, color="orange", linestyle=":", label="Warning margin (2°C)")
    axes[3].fill_between(t, features["condensation_margin"], 0,
                          where=features["condensation_margin"] < 0,
                          alpha=0.4, color="red")
    axes[3].set_ylabel("Margin [°C]"); axes[3].set_title("Condensation Safety Margin")
    axes[3].legend(fontsize=8); axes[3].grid(alpha=0.3)
    axes[3].set_xlabel("Time")

    # Legend for event severity
    patches = [mpatches.Patch(color=c, alpha=0.4, label=s.value.title())
               for s, c in SEVERITY_COLORS.items() if s != LeakSeverity.NONE]
    fig.legend(handles=patches, loc="lower center", ncol=4, fontsize=9,
               title="Event Severity", bbox_to_anchor=(0.5, -0.01))

    if save_path:
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        logger.info(f"Plot saved: {save_path}")
    plt.show()


# ── Report Builder ────────────────────────────────────────────────────────────

def build_report(component_id: str, events: List[LeakEvent], df: pd.DataFrame) -> AnalysisReport:
    if not events:
        overall = LeakSeverity.NONE
    else:
        severity_order = list(LeakSeverity)
        overall = max(events, key=lambda e: severity_order.index(e.severity)).severity

    critical = sum(1 for e in events if e.severity == LeakSeverity.CRITICAL)

    recs = []
    if overall in [LeakSeverity.CRITICAL, LeakSeverity.HIGH]:
        recs.append("Immediate inspection and maintenance required.")
        recs.append("Perform full IP rating verification after repair.")
    if any(e.min_insulation < 50 for e in events):
        recs.append("Replace insulation materials — Hi-Pot test mandatory before re-start.")
    if len(events) > 3:
        recs.append("Recurring events detected — review root cause and consider design improvement.")
    if not recs:
        recs.append("Continue scheduled monitoring. Review environmental conditions.")

    trend_summary = {
        "mean_humidity":       float(df["humidity_rh"].mean()),
        "max_humidity":        float(df["humidity_rh"].max()),
        "min_insulation_kohm": float(df["insulation_kohm"].min()),
        "condensation_events": int((df["temperature_c"] < SignalProcessor.compute_dew_point(
            df["temperature_c"], df["humidity_rh"])).sum()),
        "total_events":        len(events),
    }

    return AnalysisReport(
        component_id=component_id,
        analysis_time=pd.Timestamp.now(),
        total_events=len(events),
        critical_events=critical,
        overall_risk=overall,
        events=events,
        trend_summary=trend_summary,
        recommendations=recs,
    )


def print_report(report: AnalysisReport):
    print("\n" + "═" * 70)
    print(f"  MOISTURE LEAK ANALYSIS REPORT — {report.component_id}")
    print("═" * 70)
    print(f"  Analysis Time  : {report.analysis_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Overall Risk   : {report.overall_risk.value.upper()}")
    print(f"  Total Events   : {report.total_events}  (Critical: {report.critical_events})")
    print()
    print("  Trend Summary:")
    for k, v in report.trend_summary.items():
        print(f"    {k:<30} : {v}")
    print()
    print("  Detected Events:")
    for i, e in enumerate(report.events, 1):
        print(f"    [{i}] {e.severity.value.upper():<10} | {e.start_time.strftime('%H:%M')} – "
              f"{e.end_time.strftime('%H:%M') if e.end_time else 'ongoing'} "
              f"| Peak RH={e.peak_humidity:.1f}% | Ins={e.min_insulation:.0f}kΩ "
              f"| Conf={e.confidence:.0%}")
        print(f"        Root cause : {e.root_cause}")
        print(f"        Action     : {e.recommended_action[:80]}...")
        print()
    print("  Recommendations:")
    for r in report.recommendations:
        print(f"    • {r}")
    print("═" * 70 + "\n")


def export_report_json(report: AnalysisReport, path: str):
    data = {
        "component_id":   report.component_id,
        "analysis_time":  report.analysis_time.isoformat(),
        "overall_risk":   report.overall_risk.value,
        "total_events":   report.total_events,
        "critical_events":report.critical_events,
        "trend_summary":  report.trend_summary,
        "recommendations":report.recommendations,
        "events": [
            {
                "start":     e.start_time.isoformat(),
                "end":       e.end_time.isoformat() if e.end_time else None,
                "severity":  e.severity.value,
                "zone":      e.zone.value,
                "peak_rh":   e.peak_humidity,
                "min_ins":   e.min_insulation,
                "duration":  e.duration_min,
                "confidence":e.confidence,
                "root_cause":e.root_cause,
                "action":    e.recommended_action,
            }
            for e in report.events
        ],
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Report exported: {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Moisture Leak Analysis Tool")
    p.add_argument("--input",      default="",              help="CSV file with sensor data")
    p.add_argument("--component",  default="MOTOR_001",     help="Component ID")
    p.add_argument("--zone",       default="housing_seal",  help="Component zone")
    p.add_argument("--output_dir", default="data/reports",  help="Output directory")
    p.add_argument("--no_plot",    action="store_true")
    return p.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    args = parse_args()

    # Load or generate data
    if args.input and os.path.exists(args.input):
        df = pd.read_csv(args.input, parse_dates=["timestamp"])
        logger.info(f"Loaded {len(df)} rows from {args.input}")
    else:
        logger.info("No input file — using synthetic motor data with injected leak events")
        df = generate_synthetic_data(component_id=args.component, n_hours=48)

    # Map zone string to enum
    zone_map = {z.value: z for z in ComponentZone}
    zone = zone_map.get(args.zone, ComponentZone.HOUSING_SEAL)

    # Detect leaks
    detector = MoistureLeakDetector(zone=zone)
    events   = detector.detect(df, component_id=args.component)
    features = SignalProcessor.extract_features(df)

    # Build and print report
    report = build_report(args.component, events, df)
    print_report(report)

    # Export
    export_report_json(report, os.path.join(args.output_dir, f"{args.component}_report.json"))

    # Plot
    if not args.no_plot:
        plot_analysis(
            df, events, features,
            title=f"Moisture Leak Analysis — {args.component}",
            save_path=os.path.join(args.output_dir, f"{args.component}_analysis.png"),
        )


if __name__ == "__main__":
    main()
