"""
models/domain3.py

Domain 3: Temporal / Seasonal Factors (Short-term modifiers)

Purpose
-------
Capture short-term contextual risks (last 7–14 days) that can temporarily
increase enteric disease risk (e.g., heatwaves, heavy rainfall, floods).

This domain is designed as a *multiplier* on top of baseline risk from
Domains 1–2, rather than a standalone additive score.

Design goals
------------
- Robust to messy LLM outputs (bool parsing, loose date/recency parsing).
- Explicit logging of an assessment date + most recent event date when possible.
- Simple, explainable multiplier logic with an upper cap.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


# =========================================================
# SMALL HELPERS
# =========================================================

_NA_STRINGS = {
    "na",
    "n/a",
    "null",
    "none",
    "unknown",
    "dont know",
    "don't know",
    "",
    "unsure",
}


def _norm(x: Any) -> str:
    return str(x or "").strip().lower()


def _to_bool_or_none(x: Any) -> Optional[bool]:
    """Parse boolean-ish values from LLM output."""
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    s = _norm(x)
    if s in _NA_STRINGS:
        return None

    if s in {"1", "true", "t", "yes", "y", "yeah", "yup"}:
        return True
    if s in {"0", "false", "f", "no", "n", "nope"}:
        return False

    # soft patterns (avoid over-eager True)
    if any(k in s for k in ["no", "none", "not"]):
        return False

    return None


def _to_int_or_none(x: Any, min_v: int = 0, max_v: int = 14) -> Optional[int]:
    """Extract the first integer from text, constrained to [min_v, max_v]."""
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return None
        s = _norm(x)
        if s in _NA_STRINGS:
            return None

        import re

        m = re.search(r"\b(\d{1,3})\b", s)
        if not m:
            return None
        v = int(m.group(1))
        if v < min_v or v > max_v:
            return None
        return v
    except Exception:
        return None


def _parse_iso_date_or_none(x: Any) -> Optional[date]:
    """Parse YYYY-MM-DD strictly to avoid incorrect guesses."""
    if x is None:
        return None
    s = _norm(x)
    if s in _NA_STRINGS:
        return None
    try:
        return date.fromisoformat(str(x).strip())
    except Exception:
        return None


# =========================================================
# SURVEY DEPENDENCIES
# =========================================================

class Domain3SurveyDeps(BaseModel):
    conversation_history: list[str] = Field(default_factory=list)


class ValidationDecision(BaseModel):
    status: Literal["OK", "NEED_FOLLOWUP", "GIVE_UP"]
    followup: Optional[str] = None
    note: Optional[str] = None


# =========================================================
# MAIN DOMAIN MODEL
# =========================================================

class Domain3Data(BaseModel):
    """Structured outputs for Domain 3."""

    # Event flags (last 14 days)
    recent_heatwave: Optional[bool] = None
    recent_heavy_rain: Optional[bool] = None
    recent_flood: Optional[bool] = None

    # Timing of MOST RECENT event
    most_recent_event_date: Optional[date] = None
    event_recency_days: Optional[int] = Field(
        default=None,
        description="How many days ago the most recent event occurred (0–14).",
    )

    # Local outbreak / service disruption
    community_diarrhoea_outbreak: Optional[bool] = None
    water_interruption: Optional[bool] = None
    extended_water_storage: Optional[bool] = None

    # Always log assessment date (set by app/runtime when possible)
    assessment_date: date = Field(default_factory=date.today)

    @property
    def multiplier_cap(self) -> float:
        return 1.6

    @property
    def risk_multiplier(self) -> float:
        """Compute a short-term multiplier based on flags."""
        m = 1.0

        if self.recent_heatwave is True:
            m += 0.10
        if self.recent_heavy_rain is True:
            m += 0.15
        if self.recent_flood is True:
            m += 0.25
        if self.community_diarrhoea_outbreak is True:
            m += 0.20
        if self.extended_water_storage is True:
            m += 0.10

        return round(min(m, self.multiplier_cap), 2)

    def get_risk_summary(self) -> dict:
        """For logging / saving results."""
        return {
            "domain": "Temporal / Seasonal Factors",
            "assessment_date": self.assessment_date.isoformat(),
            "recent_heatwave": self.recent_heatwave,
            "recent_heavy_rain": self.recent_heavy_rain,
            "recent_flood": self.recent_flood,
            "most_recent_event_date": self.most_recent_event_date.isoformat() if self.most_recent_event_date else None,
            "event_recency_days": self.event_recency_days,
            "community_diarrhoea_outbreak": self.community_diarrhoea_outbreak,
            "water_interruption": self.water_interruption,
            "extended_water_storage": self.extended_water_storage,
            "risk_multiplier": self.risk_multiplier,
        }

    def to_template_dict(self) -> dict:
        """
        For rendering domain3_completion.md (string-friendly values).
        Keeps None as 'NA' so your completion template looks consistent.
        """
        def _v(x: Any) -> str:
            if x is None:
                return "NA"
            if isinstance(x, bool):
                return "Yes" if x else "No"
            return str(x)

        return {
            "recent_heatwave": _v(self.recent_heatwave),
            "recent_heavy_rain": _v(self.recent_heavy_rain),
            "recent_flood": _v(self.recent_flood),
            "most_recent_event_date": _v(self.most_recent_event_date.isoformat() if self.most_recent_event_date else None),
            "event_recency_days": _v(self.event_recency_days),
            "community_diarrhoea_outbreak": _v(self.community_diarrhoea_outbreak),
            "water_interruption": _v(self.water_interruption),
            "extended_water_storage": _v(self.extended_water_storage),
            "risk_multiplier": f"{self.risk_multiplier:.2f}",
            "assessment_date": self.assessment_date.isoformat(),
        }

    @classmethod
    def from_answers(cls, answers: Dict[str, Any], *, assessment_date: Optional[date] = None) -> "Domain3Data":
        """
        Create Domain3Data from extraction JSON.

        assessment_date: lets the app set a trusted date (preferred over LLM inference).
        """
        ad = assessment_date or date.today()

        # Primary keys from extraction prompt
        heat = answers.get("recent_heatwave")
        rain = answers.get("recent_heavy_rain")
        flood = answers.get("recent_flood")

        # Backward-compatible aliases (if needed)
        heat = heat if heat is not None else answers.get("heatwave")
        rain = rain if rain is not None else answers.get("heavy_rain", answers.get("heavy_rainfall"))
        flood = flood if flood is not None else answers.get("flood")

        recency = answers.get("event_recency_days", answers.get("days_since_event", answers.get("days_ago")))
        recency_days = _to_int_or_none(recency, 0, 14)

        event_date = answers.get("most_recent_event_date", answers.get("event_date"))
        parsed_event_date = _parse_iso_date_or_none(event_date)

        # If user didn't provide date but did provide days-ago, derive date for logging
        # BUT: only do this if at least one event flag is True.
        heat_b = _to_bool_or_none(heat)
        rain_b = _to_bool_or_none(rain)
        flood_b = _to_bool_or_none(flood)
        any_event_true = any(v is True for v in [heat_b, rain_b, flood_b])

        if parsed_event_date is None and recency_days is not None and any_event_true:
            parsed_event_date = ad - timedelta(days=recency_days)

        outbreak = answers.get("community_diarrhoea_outbreak")
        if outbreak is None:
            outbreak = answers.get("recent_diarrhoea_outbreak", answers.get("diarrhoea_outbreak"))

        interruption = answers.get("water_interruption")
        if interruption is None:
            interruption = answers.get("seasonal_water_interruption")

        storage = answers.get("extended_water_storage")
        if storage is None:
            storage = answers.get("longer_water_storage")

        return cls(
            recent_heatwave=heat_b,
            recent_heavy_rain=rain_b,
            recent_flood=flood_b,
            most_recent_event_date=parsed_event_date,
            event_recency_days=recency_days,
            community_diarrhoea_outbreak=_to_bool_or_none(outbreak),
            water_interruption=_to_bool_or_none(interruption),
            extended_water_storage=_to_bool_or_none(storage),
            assessment_date=ad,
        )
        