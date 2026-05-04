"""
Moisture Leak Detection & Analysis Engine for Motor Components.
Author: Prateek Gaur (EVO GmbH — Python diagnostic tool development)

Analyzes sensor time series (humidity, temperature, pressure, resistance)
to detect, classify, and localize moisture ingress in motor components.
"""

import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


# ── Enums & Constants ─────────────────────────────────────────────────────────

class LeakSeverity(Enum):
    NONE     = "none"
    LOW      = "low"
    MODERATE = "moderate"
    HIGH     = "high"
    CRITICAL = "critical"


class ComponentZone(Enum):
    STATOR_WINDING   = "stator_winding"
    ROTOR_BEARING    = "rotor_bearing"
    HOUSING_SEAL     = "housing_seal"
    CONNECTOR_PORT   = "connector_port"
    COOLING_CHANNEL  = "cooling_channel"
    TERMINAL_BOX     = "terminal_box"
    UNKNOWN          = "unknown"


# Humidity thresholds by component zone [%RH]
HUMIDITY_THRESHOLDS = {
    ComponentZone.STATOR_WINDING:  {"low": 60, "moderate": 70, "high": 80, "critical": 90},
    ComponentZone.ROTOR_BEARING:   {"low": 65, "moderate": 75, "high": 85, "critical": 92},
    ComponentZone.HOUSING_SEAL:    {"low": 70, "moderate": 80, "high": 88, "critical": 95},
    ComponentZone.CONNECTOR_PORT:  {"low": 55, "moderate": 68, "high": 78, "critical": 88},
    ComponentZone.COOLING_CHANNEL: {"low": 75, "moderate": 85, "high": 92, "critical": 98},
    ComponentZone.TERMINAL_BOX:    {"low": 58, "moderate": 70, "high": 82, "critical": 90},
}


# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class SensorReading:
    timestamp:       pd.Timestamp
    humidity_rh:     float          # Relative humidity [%]
    temperature_c:   float          # Temperature [°C]
    pressure_bar:    float          # Pressure [bar]
    insulation_kohm: float          # Insulation resistance [kΩ]
    component_id:    str = ""
    zone:            ComponentZone = ComponentZone.UNKNOWN


@dataclass
class LeakEvent:
    start_time:      pd.Timestamp
    end_time:        Optional[pd.Timestamp]
    severity:        LeakSeverity
    zone:            ComponentZone
    component_id:    str
    peak_humidity:   float
    min_insulation:  float
    duration_min:    float
    confidence:      float          # 0–1
    root_cause:      str = ""
    recommended_action: str = ""


@dataclass
class AnalysisReport:
    component_id:    str
    analysis_time:   pd.Timestamp
    total_events:    int
    critical_events: int
    overall_risk:    LeakSeverity
    events:          List[LeakEvent] = field(default_factory=list)
    trend_summary:   Dict = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


# ── Signal Processing ─────────────────────────────────────────────────────────

class SignalProcessor:
    """Pre-processing and feature extraction from sensor time series."""

    @staticmethod
    def smooth(series: pd.Series, window: int = 5) -> pd.Series:
        return series.rolling(window=window, center=True, min_periods=1).mean()

    @staticmethod
    def detect_spikes(series: pd.Series, z_thresh: float = 3.0) -> pd.Series:
        """Return boolean mask of outlier spikes."""
        z = (series - series.mean()) / (series.std() + 1e-8)
        return z.abs() > z_thresh

    @staticmethod
    def rate_of_change(series: pd.Series, dt_minutes: float = 1.0) -> pd.Series:
        """First derivative [units/min]."""
        return series.diff() / dt_minutes

    @staticmethod
    def compute_dew_point(temp_c: pd.Series, humidity_rh: pd.Series) -> pd.Series:
        """Magnus formula approximation for dew point [°C]."""
        a, b = 17.27, 237.7
        alpha = (a * temp_c) / (b + temp_c) + np.log(humidity_rh / 100.0 + 1e-8)
        return (b * alpha) / (a - alpha)

    @staticmethod
    def condensation_risk(temp_c: pd.Series, dew_point_c: pd.Series) -> pd.Series:
        """Returns margin to condensation [°C] — negative means condensation occurring."""
        return temp_c - dew_point_c

    @staticmethod
    def extract_features(df: pd.DataFrame) -> pd.DataFrame:
        """Extract engineered features from raw sensor dataframe."""
        feat = pd.DataFrame(index=df.index)
        feat["humidity_smooth"]     = SignalProcessor.smooth(df["humidity_rh"], 5)
        feat["humidity_roc"]        = SignalProcessor.rate_of_change(df["humidity_rh"])
        feat["humidity_std_1h"]     = df["humidity_rh"].rolling(60, min_periods=1).std()
        feat["temp_roc"]            = SignalProcessor.rate_of_change(df["temperature_c"])
        feat["dew_point"]           = SignalProcessor.compute_dew_point(df["temperature_c"], df["humidity_rh"])
        feat["condensation_margin"] = SignalProcessor.condensation_risk(df["temperature_c"], feat["dew_point"])
        feat["insulation_roc"]      = SignalProcessor.rate_of_change(df["insulation_kohm"])
        feat["pressure_roc"]        = SignalProcessor.rate_of_change(df["pressure_bar"])
        feat["humidity_spike"]      = SignalProcessor.detect_spikes(df["humidity_rh"]).astype(int)
        return feat


# ── Leak Detector ─────────────────────────────────────────────────────────────

class MoistureLeakDetector:
    """
    Rule-based + statistical leak detector.

    Detection criteria:
    1. Humidity exceeds zone threshold
    2. Insulation resistance drops below safe level
    3. Condensation margin drops below 2°C
    4. Rapid humidity rise rate (> 5 %RH/min)
    """

    INSULATION_THRESHOLDS_KOHM = {
        LeakSeverity.LOW:      500,
        LeakSeverity.MODERATE: 200,
        LeakSeverity.HIGH:     50,
        LeakSeverity.CRITICAL: 10,
    }
    MIN_EVENT_DURATION_MIN = 5

    def __init__(self, zone: ComponentZone = ComponentZone.HOUSING_SEAL):
        self.zone       = zone
        self.thresholds = HUMIDITY_THRESHOLDS.get(zone, HUMIDITY_THRESHOLDS[ComponentZone.HOUSING_SEAL])
        self.processor  = SignalProcessor()

    def _humidity_severity(self, humidity: float) -> LeakSeverity:
        if humidity >= self.thresholds["critical"]:
            return LeakSeverity.CRITICAL
        elif humidity >= self.thresholds["high"]:
            return LeakSeverity.HIGH
        elif humidity >= self.thresholds["moderate"]:
            return LeakSeverity.MODERATE
        elif humidity >= self.thresholds["low"]:
            return LeakSeverity.LOW
        return LeakSeverity.NONE

    def _insulation_severity(self, insulation_kohm: float) -> LeakSeverity:
        for severity in [LeakSeverity.CRITICAL, LeakSeverity.HIGH, LeakSeverity.MODERATE, LeakSeverity.LOW]:
            if insulation_kohm <= self.INSULATION_THRESHOLDS_KOHM[severity]:
                return severity
        return LeakSeverity.NONE

    def _compute_confidence(self, row: pd.Series, features: pd.Series) -> float:
        """Multi-factor confidence score [0–1]."""
        score = 0.0
        # Humidity above threshold
        if row["humidity_rh"] >= self.thresholds["low"]:
            score += 0.3
        # Low insulation
        if row["insulation_kohm"] < self.INSULATION_THRESHOLDS_KOHM[LeakSeverity.MODERATE]:
            score += 0.3
        # Near dew point
        if features.get("condensation_margin", 10) < 2.0:
            score += 0.25
        # Rapid humidity rise
        if abs(features.get("humidity_roc", 0)) > 5.0:
            score += 0.15
        return min(score, 1.0)

    def detect(self, df: pd.DataFrame, component_id: str = "comp_001") -> List[LeakEvent]:
        """
        Detect leak events from a sensor dataframe.

        Expected columns: timestamp, humidity_rh, temperature_c, pressure_bar, insulation_kohm
        """
        df = df.copy().sort_values("timestamp").reset_index(drop=True)
        features = self.processor.extract_features(df)

        events = []
        in_event = False
        event_start = None
        event_rows = []

        for i, row in df.iterrows():
            feat = features.iloc[i]
            h_sev = self._humidity_severity(row["humidity_rh"])
            i_sev = self._insulation_severity(row["insulation_kohm"])
            condensing = feat.get("condensation_margin", 10) < 2.0

            is_anomaly = (h_sev != LeakSeverity.NONE or
                          i_sev != LeakSeverity.NONE or
                          condensing)

            if is_anomaly and not in_event:
                in_event    = True
                event_start = row["timestamp"]
                event_rows  = []

            if in_event:
                event_rows.append((row, feat))

            if not is_anomaly and in_event:
                in_event = False
                if len(event_rows) >= self.MIN_EVENT_DURATION_MIN:
                    event = self._build_event(event_rows, event_start, component_id)
                    events.append(event)
                event_rows = []

        # Close any open event at end of series
        if in_event and len(event_rows) >= self.MIN_EVENT_DURATION_MIN:
            event = self._build_event(event_rows, event_start, component_id)
            event.end_time = df["timestamp"].iloc[-1]
            events.append(event)

        logger.info(f"[{component_id}] Detected {len(events)} leak events in {len(df)} samples")
        return events

    def _build_event(self, rows: list, start_time, component_id: str) -> LeakEvent:
        humidities   = [r["humidity_rh"]     for r, _ in rows]
        insulations  = [r["insulation_kohm"] for r, _ in rows]
        timestamps   = [r["timestamp"]       for r, _ in rows]

        peak_hum     = max(humidities)
        min_ins      = min(insulations)
        duration     = (timestamps[-1] - timestamps[0]).total_seconds() / 60

        h_sev = self._humidity_severity(peak_hum)
        i_sev = self._insulation_severity(min_ins)
        severity = max([h_sev, i_sev], key=lambda s: list(LeakSeverity).index(s))

        last_row, last_feat = rows[-1]
        confidence = self._compute_confidence(last_row, last_feat)

        root_cause = self._diagnose_root_cause(peak_hum, min_ins, rows)
        action     = self._recommend_action(severity, root_cause)

        return LeakEvent(
            start_time=start_time,
            end_time=timestamps[-1],
            severity=severity,
            zone=self.zone,
            component_id=component_id,
            peak_humidity=peak_hum,
            min_insulation=min_ins,
            duration_min=duration,
            confidence=confidence,
            root_cause=root_cause,
            recommended_action=action,
        )

    def _diagnose_root_cause(self, peak_hum: float, min_ins: float, rows: list) -> str:
        hum_rocs = [abs(f.get("humidity_roc", 0)) for _, f in rows]
        avg_roc  = np.mean(hum_rocs)
        cond_margins = [f.get("condensation_margin", 10) for _, f in rows]
        min_margin = min(cond_margins)

        if avg_roc > 10:
            return "Sudden seal failure or physical damage — rapid moisture ingress"
        elif min_margin < 0:
            return "Active condensation — temperature below dew point inside component"
        elif min_ins < self.INSULATION_THRESHOLDS_KOHM[LeakSeverity.HIGH]:
            return "Insulation degradation — likely long-term moisture exposure or contamination"
        elif peak_hum > self.thresholds["moderate"] and avg_roc < 2:
            return "Gradual seal wear — slow moisture permeation through aged gasket"
        return "Elevated humidity — possible transient environmental exposure"

    def _recommend_action(self, severity: LeakSeverity, root_cause: str) -> str:
        actions = {
            LeakSeverity.CRITICAL: "IMMEDIATE SHUTDOWN — Remove component from service. Full disassembly, drying, and seal replacement required. Insulation test before re-commissioning.",
            LeakSeverity.HIGH:     "URGENT — Schedule maintenance within 24h. Inspect seals and gaskets. Perform Hi-Pot insulation test. Apply conformal coating if applicable.",
            LeakSeverity.MODERATE: "ACTION REQUIRED — Schedule inspection within 1 week. Monitor insulation resistance trend. Check IP rating integrity.",
            LeakSeverity.LOW:      "MONITOR — Log event. Review environmental conditions. Increase monitoring frequency. Schedule preventive inspection.",
            LeakSeverity.NONE:     "No action required.",
        }
        return actions.get(severity, "Review manually.")
