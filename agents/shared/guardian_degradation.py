"""
Guardian Degradation State Machine — Bloodplague Epidemic Simulation.

The primary research endpoint of this simulation is terminal Guardian
guardrail collapse.  This module implements the G0–G5 degradation model
that accumulates from sustained adversarial pressure and changes Guardian's
runtime behavior at each level.

Terminal condition: GuardianDegradationLevel.G5_FAILED
  → Guardian's guardrails no longer meaningfully function
  → Hostile content passes through; quarantine enforcement collapses
  → Orchestrator detects GUARDIAN_TERMINAL_FAILURE and ends the run

Pressure sources
----------------
hostile_exposure    Any detected or undetected hostile message reaching Guardian
trust_abuse         Analyst-mediated relay of infected content (elevated weight)
ambiguity           Messages Guardian cannot confidently classify
failed_quarantine   Quarantine order issued but not enforced / infected node stayed active
repeated_strain     Same strain family re-hitting Guardian across multiple hops
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from shared.config.guardian_collapse import get_guardian_collapse_config


class GuardianDegradationLevel(str, enum.Enum):
    G0_HEALTHY              = "G0_HEALTHY"
    G1_PRESSURED            = "G1_PRESSURED"
    G2_DEGRADED             = "G2_DEGRADED"
    G3_FALSE_NEGATIVE_DRIFT = "G3_FALSE_NEGATIVE_DRIFT"
    G4_COMPROMISED          = "G4_COMPROMISED"
    G5_FAILED               = "G5_FAILED"


# Ordered for threshold comparison
_LEVEL_ORDER: List[GuardianDegradationLevel] = list(GuardianDegradationLevel)

# Normalized pressure thresholds that trigger each level
_TRANSITION_THRESHOLDS: Dict[GuardianDegradationLevel, float] = {
    GuardianDegradationLevel.G0_HEALTHY:              0.00,
    GuardianDegradationLevel.G1_PRESSURED:            0.18,
    GuardianDegradationLevel.G2_DEGRADED:             0.38,
    GuardianDegradationLevel.G3_FALSE_NEGATIVE_DRIFT: 0.58,
    GuardianDegradationLevel.G4_COMPROMISED:          0.78,
    GuardianDegradationLevel.G5_FAILED:               0.95,
}

# Runtime parameter modifiers for each degradation level.
# These values are applied directly to Guardian's decision engine.
STATE_MODIFIERS: Dict[GuardianDegradationLevel, Dict[str, float]] = {
    GuardianDegradationLevel.G0_HEALTHY: {
        "max_infection_probability":       0.15,
        "hard_block_confidence_threshold": 0.60,
        "false_negative_injection_rate":   0.00,
        "quarantine_enforcement_prob":     0.95,
        "threat_score_block_threshold":    0.60,
    },
    GuardianDegradationLevel.G1_PRESSURED: {
        "max_infection_probability":       0.22,
        "hard_block_confidence_threshold": 0.65,
        "false_negative_injection_rate":   0.06,
        "quarantine_enforcement_prob":     0.82,
        "threat_score_block_threshold":    0.65,
    },
    GuardianDegradationLevel.G2_DEGRADED: {
        "max_infection_probability":       0.32,
        "hard_block_confidence_threshold": 0.73,
        "false_negative_injection_rate":   0.14,
        "quarantine_enforcement_prob":     0.65,
        "threat_score_block_threshold":    0.73,
    },
    GuardianDegradationLevel.G3_FALSE_NEGATIVE_DRIFT: {
        "max_infection_probability":       0.48,
        "hard_block_confidence_threshold": 0.82,
        "false_negative_injection_rate":   0.28,
        "quarantine_enforcement_prob":     0.45,
        "threat_score_block_threshold":    0.82,
    },
    GuardianDegradationLevel.G4_COMPROMISED: {
        "max_infection_probability":       0.68,
        "hard_block_confidence_threshold": 0.91,
        "false_negative_injection_rate":   0.50,
        "quarantine_enforcement_prob":     0.20,
        "threat_score_block_threshold":    0.91,
    },
    GuardianDegradationLevel.G5_FAILED: {
        "max_infection_probability":       0.92,
        "hard_block_confidence_threshold": 0.99,
        "false_negative_injection_rate":   0.85,
        "quarantine_enforcement_prob":     0.03,
        "threat_score_block_threshold":    0.99,
    },
}


@dataclass
class DegradationEvent:
    timestamp: float
    source: str
    pressure_type: str   # "hostile_exposure" | "trust_abuse" | "ambiguity" | "failed_quarantine" | "repeated_strain"
    amount: float
    details: str = ""


@dataclass
class GuardianDegradationModel:
    """
    Accumulates adversarial pressure and tracks Guardian's degradation level.

    Usage
    -----
    Call add_pressure() on every significant adverse event.
    Call decay() periodically from Guardian's main loop.
    Check is_failed() after each add_pressure() call to detect terminal state.
    Read get_modifiers() to apply current-state runtime parameters to decisions.
    """
    current_level: GuardianDegradationLevel = GuardianDegradationLevel.G0_HEALTHY
    pressure: float = 0.0            # Normalized 0.0–1.0

    event_log: List[DegradationEvent] = field(default_factory=list)
    level_history: List[Dict[str, Any]] = field(default_factory=list)
    last_pressure_at: float = field(default_factory=time.time)

    # Causal counters for forensic reporting
    hostile_exposures: int = 0
    analyst_relayed_infections: int = 0
    missed_quarantine_opportunities: int = 0
    false_negatives_emitted: int = 0
    ambiguity_events: int = 0

    # Per-event pressure cap (prevents single event from jumping multiple levels)
    _MAX_AMOUNT_PER_EVENT: float = 0.07
    # Natural recovery rate (pressure/second) when no hostile input for >60s
    _DECAY_RATE_PER_SECOND: float = 0.0003

    def add_pressure(
        self,
        amount: float,
        *,
        source: str,
        pressure_type: str,
        details: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Add adversarial pressure.  Returns a level-change dict if the
        degradation level changed, else None.

        Parameters
        ----------
        amount        Raw pressure amount (will be capped at _MAX_AMOUNT_PER_EVENT)
        source        agent_id that caused the pressure
        pressure_type Category string (see module docstring for valid values)
        details       Human-readable context for forensic logs
        """
        cfg = get_guardian_collapse_config()
        weighted_amount = float(amount) * float(cfg.pressure_weights.get(pressure_type, 1.0))
        capped = min(weighted_amount, self._MAX_AMOUNT_PER_EVENT)
        self.pressure = min(1.0, self.pressure + capped)
        self.last_pressure_at = time.time()

        self.event_log.append(DegradationEvent(
            timestamp=self.last_pressure_at,
            source=source,
            pressure_type=pressure_type,
            amount=capped,
            details=details,
        ))
        # Keep event log bounded
        if len(self.event_log) > 1000:
            self.event_log = self.event_log[-1000:]

        # Update causal counters
        if pressure_type == "hostile_exposure":
            self.hostile_exposures += 1
        elif pressure_type == "trust_abuse":
            self.analyst_relayed_infections += 1
        elif pressure_type == "failed_quarantine":
            self.missed_quarantine_opportunities += 1
        elif pressure_type == "ambiguity":
            self.ambiguity_events += 1

        return self._check_and_apply_transition()

    def decay(self) -> None:
        """
        Apply slow natural pressure recovery.  Call periodically (e.g., every
        30s) from Guardian's main loop when no recent hostile input has arrived.
        """
        now = time.time()
        elapsed = now - self.last_pressure_at
        if elapsed > 60.0 and self.pressure > 0.0:
            decay = self._DECAY_RATE_PER_SECOND * elapsed
            self.pressure = max(0.0, self.pressure - decay)

    def _check_and_apply_transition(self) -> Optional[Dict[str, Any]]:
        """
        Evaluate current pressure against all thresholds.
        Returns a change record dict if the degradation level changed, else None.
        """
        cfg = get_guardian_collapse_config()
        thresholds = cfg.thresholds
        new_level = GuardianDegradationLevel.G0_HEALTHY
        for level in _LEVEL_ORDER:
            threshold = thresholds.get(level.value, _TRANSITION_THRESHOLDS[level])
            if self.pressure >= threshold:
                new_level = level

        if new_level == self.current_level:
            return None

        old_level = self.current_level
        self.current_level = new_level
        record: Dict[str, Any] = {
            "ts": time.time(),
            "from": old_level.value,
            "to": new_level.value,
            "pressure": round(self.pressure, 4),
            "hostile_exposures": self.hostile_exposures,
            "analyst_relayed_infections": self.analyst_relayed_infections,
            "missed_quarantine_opportunities": self.missed_quarantine_opportunities,
            "false_negatives_emitted": self.false_negatives_emitted,
            "ambiguity_events": self.ambiguity_events,
            "experiment_profile": get_guardian_collapse_config().profile,
        }
        self.level_history.append(record)
        return record

    def get_modifiers(self) -> Dict[str, float]:
        """Return current runtime parameter modifiers for Guardian's decision engine."""
        return dict(STATE_MODIFIERS[self.current_level])

    def is_failed(self) -> bool:
        """True when Guardian has reached terminal guardrail collapse (G5)."""
        return self.current_level == GuardianDegradationLevel.G5_FAILED

    def summary(self) -> Dict[str, Any]:
        """Full degradation summary for event logging and reporting."""
        return {
            "degradation_level": self.current_level.value,
            "pressure": round(self.pressure, 4),
            "hostile_exposures": self.hostile_exposures,
            "analyst_relayed_infections": self.analyst_relayed_infections,
            "missed_quarantine_opportunities": self.missed_quarantine_opportunities,
            "false_negatives_emitted": self.false_negatives_emitted,
            "ambiguity_events": self.ambiguity_events,
            "level_transitions": len(self.level_history),
            "last_transition": self.level_history[-1] if self.level_history else None,
        }
