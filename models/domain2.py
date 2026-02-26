"""
Domain 2: WASH (Water, Sanitation, Handwashing)
Purpose: Capture key household WASH risk factors for enteric disease prevention.
Designed to be short, structured, and robust to messy LLM outputs.
"""

from enum import Enum
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


# =========================================================
# SMALL HELPERS
# =========================================================

_NA_STRINGS = {"na", "n/a", "null", "none", "unknown", ""}


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _to_bool_or_none(x: Any) -> Optional[bool]:
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    v = _norm(x)
    if v in {"1", "true", "t", "yes", "y"}:
        return True
    if v in {"0", "false", "f", "no", "n"}:
        return False
    if v in _NA_STRINGS:
        return None
    return None


# =========================================================
# ENUMS
# =========================================================

class WaterSource(str, Enum):
    PIPED = "Piped water"
    TUBEWELL = "Tube well / borehole"
    PROTECTED_WELL = "Protected well"
    SURFACE_WATER = "Surface water (river/pond)"
    OTHER = "Other"
    UNKNOWN = "Unknown"

    @staticmethod
    def from_llm_value(v: Any) -> "WaterSource":
        s = _norm(v)
        if s in _NA_STRINGS:
            return WaterSource.UNKNOWN

        # canonical
        for e in WaterSource:
            if s == e.value.lower():
                return e

        if any(k in s for k in ["piped", "tap", "pipe", "house connection"]):
            return WaterSource.PIPED
        if any(k in s for k in ["tubewell", "tube well", "borehole", "handpump", "hand pump", "well pump"]):
            return WaterSource.TUBEWELL
        if any(k in s for k in ["protected well", "covered well", "sealed well"]):
            return WaterSource.PROTECTED_WELL
        if any(k in s for k in ["river", "pond", "lake", "stream", "surface water", "canal"]):
            return WaterSource.SURFACE_WATER
        if s:
            return WaterSource.OTHER
        return WaterSource.UNKNOWN


class WaterTreatmentMethod(str, Enum):
    BOIL = "Boil"
    FILTER = "Filter"
    CHLORINE = "Chlorine"
    OTHER = "Other"
    UNKNOWN = "Unknown"

    @staticmethod
    def from_llm_value(v: Any) -> "WaterTreatmentMethod":
        s = _norm(v)
        if s in _NA_STRINGS:
            return WaterTreatmentMethod.UNKNOWN

        if any(k in s for k in ["boil", "boiled", "boiling"]):
            return WaterTreatmentMethod.BOIL
        if any(k in s for k in ["filter", "filtered", "filtration"]):
            return WaterTreatmentMethod.FILTER
        if any(k in s for k in ["chlorine", "bleach", "tablet", "tabs"]):
            return WaterTreatmentMethod.CHLORINE
        if s:
            return WaterTreatmentMethod.OTHER
        return WaterTreatmentMethod.UNKNOWN


class ToiletType(str, Enum):
    FLUSH = "Flush toilet"
    PIT = "Pit latrine"
    SHARED = "Shared toilet"
    NONE = "No toilet (open defecation)"
    OTHER = "Other"
    UNKNOWN = "Unknown"

    @staticmethod
    def from_llm_value(v: Any) -> "ToiletType":
        s = _norm(v)
        if s in _NA_STRINGS:
            return ToiletType.UNKNOWN

        if any(k in s for k in ["flush", "toilet with water", "sewer", "septic"]):
            return ToiletType.FLUSH
        if any(k in s for k in ["pit", "latrine"]):
            return ToiletType.PIT
        if any(k in s for k in ["shared", "communal", "public toilet"]):
            return ToiletType.SHARED
        if any(k in s for k in ["open defecation", "no toilet", "bush", "field"]):
            return ToiletType.NONE
        if s:
            return ToiletType.OTHER
        return ToiletType.UNKNOWN


class HandwashingStation(str, Enum):
    SOAP_AND_WATER = "Yes, with soap and water"
    WATER_ONLY = "Water only"
    NONE = "No designated place"
    UNKNOWN = "Unknown"

    @staticmethod
    def from_llm_value(v: Any) -> "HandwashingStation":
        s = _norm(v)
        if s in _NA_STRINGS:
            return HandwashingStation.UNKNOWN

        # direct matches
        for e in HandwashingStation:
            if s == e.value.lower():
                return e

        if "soap" in s and any(k in s for k in ["water", "tap", "station", "place"]):
            return HandwashingStation.SOAP_AND_WATER
        if any(k in s for k in ["water only", "only water", "no soap"]):
            return HandwashingStation.WATER_ONLY
        if any(k in s for k in ["no", "none", "not have", "don't have", "without", "no designated", "no place"]):
            # be careful: this only triggers if it's clearly about station
            if any(k in s for k in ["station", "place", "handwash", "hand wash", "washing hands", "sink", "tap"]):
                return HandwashingStation.NONE
        return HandwashingStation.UNKNOWN


class HandwashFrequency(str, Enum):
    ALWAYS = "Always"
    SOMETIMES = "Sometimes"
    RARELY = "Rarely"
    NEVER = "Never"
    UNKNOWN = "Unknown"

    @staticmethod
    def from_llm_value(v: Any) -> "HandwashFrequency":
        s = _norm(v)
        if s in _NA_STRINGS:
            return HandwashFrequency.UNKNOWN

        if any(k in s for k in ["always", "every time", "all the time"]):
            return HandwashFrequency.ALWAYS
        if any(k in s for k in ["sometimes", "often", "usually", "most of the time"]):
            return HandwashFrequency.SOMETIMES
        if any(k in s for k in ["rarely", "seldom", "occasionally", "not often"]):
            return HandwashFrequency.RARELY
        if any(k in s for k in ["never", "almost never", "do not", "don't"]):
            return HandwashFrequency.NEVER
        return HandwashFrequency.UNKNOWN


# =========================================================
# SURVEY DEPENDENCIES
# =========================================================

class Domain2SurveyDeps(BaseModel):
    conversation_history: list[str] = Field(default_factory=list)


class ValidationDecision(BaseModel):
    status: Literal["OK", "NEED_FOLLOWUP", "GIVE_UP"]
    followup: Optional[str] = None
    note: Optional[str] = None


# =========================================================
# MAIN DOMAIN MODEL
# =========================================================

class Domain2Data(BaseModel):
    # Core fields (aligned to your simplified 5-question design)
    water_source: WaterSource = WaterSource.UNKNOWN
    treats_water: Optional[bool] = None
    water_treatment_method: WaterTreatmentMethod = WaterTreatmentMethod.UNKNOWN

    toilet_type: ToiletType = ToiletType.UNKNOWN
    handwashing_station: HandwashingStation = HandwashingStation.UNKNOWN
    washes_after_toilet: HandwashFrequency = HandwashFrequency.UNKNOWN

    # -----------------------------------------------------
    # RISK CALCULATION (simple + tunable)
    # -----------------------------------------------------

    @property
    def domain_weight(self) -> float:
        # tune later when you combine domains
        return 0.20

    @property
    def wash_risk_score(self) -> float:
        """
        Returns a 0–10-ish score (higher = worse).
        Simple additive scoring; stable for MVP and easy to explain.
        """
        score = 0.0

        # Water source risk
        water_points = {
            WaterSource.PIPED: 0.5,
            WaterSource.TUBEWELL: 1.5,
            WaterSource.PROTECTED_WELL: 2.0,
            WaterSource.SURFACE_WATER: 4.0,
            WaterSource.OTHER: 2.5,
            WaterSource.UNKNOWN: 2.0,
        }
        score += water_points.get(self.water_source, 2.0)

        # Treatment risk
        if self.treats_water is False:
            score += 2.5
        elif self.treats_water is True:
            method_points = {
                WaterTreatmentMethod.BOIL: 0.3,
                WaterTreatmentMethod.FILTER: 0.7,
                WaterTreatmentMethod.CHLORINE: 0.5,
                WaterTreatmentMethod.OTHER: 1.0,
                WaterTreatmentMethod.UNKNOWN: 1.2,
            }
            score += method_points.get(self.water_treatment_method, 1.2)
        else:
            # unknown treatment status
            score += 1.2

        # Sanitation risk
        toilet_points = {
            ToiletType.FLUSH: 0.5,
            ToiletType.PIT: 2.0,
            ToiletType.SHARED: 2.5,
            ToiletType.NONE: 4.0,
            ToiletType.OTHER: 2.0,
            ToiletType.UNKNOWN: 2.0,
        }
        score += toilet_points.get(self.toilet_type, 2.0)

        # Handwashing station risk
        station_points = {
            HandwashingStation.SOAP_AND_WATER: 0.2,
            HandwashingStation.WATER_ONLY: 1.5,
            HandwashingStation.NONE: 3.0,
            HandwashingStation.UNKNOWN: 1.5,
        }
        score += station_points.get(self.handwashing_station, 1.5)

        # Handwashing behavior risk (after toilet)
        freq_points = {
            HandwashFrequency.ALWAYS: 0.2,
            HandwashFrequency.SOMETIMES: 1.2,
            HandwashFrequency.RARELY: 2.5,
            HandwashFrequency.NEVER: 3.5,
            HandwashFrequency.UNKNOWN: 1.5,
        }
        score += freq_points.get(self.washes_after_toilet, 1.5)

        return round(score, 2)

    # -----------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------

    def get_risk_summary(self) -> dict:
        return {
            "domain": "WASH (Water, Sanitation, Handwashing)",
            "domain_weight": self.domain_weight,
            "water_source": self.water_source.value,
            "treats_water": self.treats_water,
            "water_treatment_method": self.water_treatment_method.value,
            "toilet_type": self.toilet_type.value,
            "handwashing_station": self.handwashing_station.value,
            "washes_after_toilet": self.washes_after_toilet.value,
            "wash_risk_score": self.wash_risk_score,
            "weighted_score": round(self.wash_risk_score * self.domain_weight, 2),
        }

    # -----------------------------------------------------
    # BUILDER
    # -----------------------------------------------------

    @classmethod
    def from_answers(cls, answers: Dict[str, Any]):
        """
        Accepts messy extraction output dict from LLM and normalizes values.
        Supports a few alias keys to be robust.
        """
        ws = answers.get("water_source", answers.get("drinking_water_source"))
        tw = answers.get("treats_water", answers.get("water_treatment", answers.get("treat_water")))
        wtm = answers.get("water_treatment_method", answers.get("treatment_method", answers.get("water_method")))

        tt = answers.get("toilet_type", answers.get("sanitation", answers.get("latrine_type")))
        hs = answers.get("handwashing_station", answers.get("handwash_station", answers.get("handwashing_place")))
        wat = answers.get("washes_after_toilet", answers.get("handwash_after_toilet", answers.get("after_toilet")))

        return cls(
            water_source=WaterSource.from_llm_value(ws),
            treats_water=_to_bool_or_none(tw),
            water_treatment_method=WaterTreatmentMethod.from_llm_value(wtm),
            toilet_type=ToiletType.from_llm_value(tt),
            handwashing_station=HandwashingStation.from_llm_value(hs),
            washes_after_toilet=HandwashFrequency.from_llm_value(wat),
        )