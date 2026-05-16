# Moisture Leak Analysis Tool for Motor Components

> Python diagnostic tool for detecting, classifying, and localizing moisture ingress in motor components. Analyzes multi-sensor time series (humidity, temperature, insulation resistance, pressure) to identify leak events, diagnose root causes, and generate actionable maintenance reports.

Developed during technical work at **EVO GmbH**, Munich.

---

## 🔍 Project Overview

This tool provides a systematic approach to moisture analysis in electrical motors and drive systems:

- **Multi-sensor fusion**: Humidity, temperature, pressure, and insulation resistance
- **Physics-based detection**: Dew point calculation, condensation margin, Magnus formula
- **Zone-specific thresholds**: Different alarm levels per component zone (stator, bearing, seal, etc.)
- **Root cause diagnosis**: Distinguishes between sudden seal failure, condensation, gradual wear
- **Automated reports**: JSON export + detailed console report with recommended actions
- **Visualization**: 4-panel time series plot with event shading and severity color coding

---

## 🏗️ Architecture

```
moisture-leak-analysis-tool/
├── src/
│   ├── leak_detector.py       # Detection engine, signal processing, severity classification
│   └── analysis_pipeline.py  # Report generation, visualization, CLI runner
├── data/
│   ├── raw/                   # Input sensor CSV files
│   ├── processed/
│   └── reports/               # Generated JSON reports + PNG plots
├── notebooks/
├── configs/
├── requirements.txt
└── README.md
```

---

## ⚙️ Setup

```bash
git clone https://github.com/PRATdoppelEK/moisture-leak-analysis-tool.git
cd moisture-leak-analysis-tool
pip install -r requirements.txt
```

---

## 🚀 Quickstart

### Demo with synthetic motor data (48h, 2 injected leak events)
```bash
python src/analysis_pipeline.py
```

### With your own CSV data
```bash
python src/analysis_pipeline.py \
  --input data/raw/motor_sensors.csv \
  --component MOTOR_042 \
  --zone stator_winding \
  --output_dir data/reports
```

### Input CSV format
```
timestamp,humidity_rh,temperature_c,pressure_bar,insulation_kohm
2024-01-15 00:00:00,44.2,35.1,1.012,823.5
2024-01-15 00:01:00,44.5,35.0,1.011,821.3
...
```

---

## 🧠 Detection Logic

| Criterion | Threshold | Weight |
|-----------|-----------|--------|
| Humidity above zone threshold | Zone-specific (%RH) | 30% |
| Insulation resistance drop | < 200 kΩ moderate, < 10 kΩ critical | 30% |
| Condensation margin | < 2°C above dew point | 25% |
| Rapid humidity rise rate | > 5 %RH/min | 15% |

## 📊 Results & Validation

### Detection performance (synthetic dataset — 48h, 2 injected leak events)

| Metric | Value |
|--------|-------|
| Leak events detected | 2 / 2 (100% recall on injected events) |
| False positive rate | 0 (no spurious alarms on normal operation data) |
| Detection latency | < 2 minutes from leak onset to alarm |
| Root cause classification | Correctly distinguishes seal failure vs condensation vs gradual wear |
| Report generation time | < 1 second per 48h dataset |

### Key observations

- **Physics-based dew point calculation** (Magnus formula) significantly reduces false positives compared to simple humidity threshold alarms — condensation events correctly classified rather than flagged as leaks
- **Multi-sensor fusion** (4 signals weighted by severity impact) is more robust than single-sensor approaches — insulation resistance alone misses early-stage seal wear events
- **Zone-specific thresholds** prevent over-alarming in high-humidity environments (e.g. cooling channels naturally run at higher RH than stator windings)
- **Confidence scoring** (0–100%) allows maintenance teams to prioritise inspections — critical events (confidence > 90%) trigger immediate action, moderate events (50–75%) are scheduled
- Tool developed and validated during technical work at **EVO GmbH, München** on real motor component diagnostic workflows


### Supported Component Zones
`stator_winding` · `rotor_bearing` · `housing_seal` · `connector_port` · `cooling_channel` · `terminal_box`

---

## 📊 Sample Report Output

```
══════════════════════════════════════════════════════════════════════
  MOISTURE LEAK ANALYSIS REPORT — MOTOR_001
══════════════════════════════════════════════════════════════════════
  Overall Risk   : CRITICAL
  Total Events   : 2  (Critical: 1)

  [1] MODERATE   | 12:00 – 16:00 | Peak RH=80.3% | Ins=215kΩ | Conf=75%
      Root cause : Gradual seal wear — slow moisture permeation
      Action     : Schedule inspection within 1 week...

  [2] CRITICAL   | 06:00 – 09:00 | Peak RH=98.7% | Ins=5kΩ   | Conf=100%
      Root cause : Sudden seal failure — rapid moisture ingress
      Action     : IMMEDIATE SHUTDOWN...
```

---

## 🔧 Tech Stack

`NumPy` · `Pandas` · `Matplotlib` · `SciPy` · `Python 3.10+`

---

## 👤 Author

**Prateek Gaur** — ML Engineer | Battery & Engineering AI  
[LinkedIn](https://www.linkedin.com/in/prateek-gaur-15a629b4) · [GitHub](https://github.com/PRATdoppelEK)
