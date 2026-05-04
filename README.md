# Moisture Leak Analysis Tool for Motor Components

> Python diagnostic tool for detecting, classifying, and localising moisture ingress in motor components. Analyses multi-sensor time series (humidity, temperature, insulation resistance, pressure) to identify leak events, diagnose root causes, and generate actionable maintenance reports.

Developed during technical work at **EVO GmbH**, Munich — verified in the employer reference (Zeugnis, Dec 2025).

---

## Project overview

Systematic approach to moisture analysis in electrical motors and drive systems:

- **Multi-sensor fusion**: Humidity, temperature, pressure, and insulation resistance
- **Physics-based detection**: Dew point calculation, condensation margin (Magnus formula)
- **Zone-specific thresholds**: Different alarm levels per component zone (stator, bearing, seal, connector, terminal box)
- **Root cause diagnosis**: Distinguishes sudden seal failure vs. condensation vs. gradual wear
- **Automated reports**: JSON export + detailed console report with recommended maintenance actions
- **Visualisation**: 4-panel time series plot with event shading and severity colour coding

---

## Architecture

```
moisture-leak-analysis-tool/
├── src/
│   ├── leak_detector.py       # Detection engine, signal processing, severity classification
│   └── analysis_pipeline.py  # Report generation, visualisation, CLI runner
├── requirements.txt
└── README.md
```

---

## Setup

```bash
git clone https://github.com/PRATdoppelEK/moisture-leak-analysis-tool.git
cd moisture-leak-analysis-tool
pip install -r requirements.txt
```

---

## Quickstart

### Demo with synthetic motor sensor data (runs immediately, no data needed)
```bash
cd src
python analysis_pipeline.py
```

### With your own CSV data
```bash
cd src
python analysis_pipeline.py \
  --input data/raw/motor_sensors.csv \
  --component MOTOR_042 \
  --zone stator_winding
```

Input CSV format:
```
timestamp,humidity_rh,temperature_c,pressure_bar,insulation_kohm
2024-01-15 00:00:00,44.2,35.1,1.012,823.5
```

---

## Detection logic

| Criterion | Threshold | Weight |
|-----------|-----------|--------|
| Humidity above zone threshold | Zone-specific (%RH) | 30% |
| Insulation resistance drop | < 200 kΩ moderate, < 10 kΩ critical | 30% |
| Condensation margin | < 2°C above dew point | 25% |
| Rapid humidity rise rate | > 5 %RH/min | 15% |

Supported zones: `stator_winding` · `rotor_bearing` · `housing_seal` · `connector_port` · `cooling_channel` · `terminal_box`

---

## Tech stack

`NumPy` · `Pandas` · `Matplotlib` · `SciPy` · `Python 3.10+`

---

## Author

**Prateek Gaur** — ML Engineer | Battery & Engineering AI | EVO GmbH (2024–2025)
[LinkedIn](https://www.linkedin.com/in/prateek-gaur-15a629b4) · [GitHub](https://github.com/PRATdoppelEK) · prateekgaur@gmx.de
