"""
Domain 1: Demographics & Vulnerability Factors
Purpose: Identify vulnerable populations requiring targeted assessment
"""

import re
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# =========================================================
# SMALL HELPERS
# =========================================================

_NA_STRINGS = {"na", "n/a", "null", "none", "unknown", ""}


def _to_int_or_none(x: Any) -> Optional[int]:
    if x is None:
        return None
    s = str(x).strip()
    if s.lower() in _NA_STRINGS:
        return None
    try:
        return int(s)
    except Exception:
        return None


def _to_bool_or_none(x: Any) -> Optional[bool]:
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    v = str(x).strip().lower()
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

class ChildAgeRange(str, Enum):
    UNDER_6_MONTHS = "0-5 months"
    SIX_TO_11_MONTHS = "6-11 months"
    TWELVE_TO_23_MONTHS = "12-23 months"
    TWO_TO_FIVE_YEARS = "24-60 months"


class CaregiverType(str, Enum):
    """
    3-level caregiver type used across Domain 1:
    - Parents / Grandparents / Other / Unknown
    IMPORTANT: Do NOT infer "Parents" from first-person statements like "I take care"
    unless mother/father/parent is explicitly stated.
    """
    PARENTS = "Parents"
    GRANDPARENTS = "Grandparents"
    OTHER = "Other"
    UNKNOWN = "Unknown"

    @staticmethod
    def from_llm_value(v: Any) -> "CaregiverType":
        s = str(v or "").strip().lower()

        if s in _NA_STRINGS:
            return CaregiverType.UNKNOWN

        # already canonical
        if s == "parents":
            return CaregiverType.PARENTS
        if s == "grandparents":
            return CaregiverType.GRANDPARENTS
        if s == "other":
            return CaregiverType.OTHER
        if s == "unknown":
            return CaregiverType.UNKNOWN

        # Parents: require explicit parent role words (NO first-person inference)
        parent_keywords = [
            "parent", "parents",
            "mom", "mother", "mum",
            "dad", "father",
        ]
        if any(k in s for k in parent_keywords):
            return CaregiverType.PARENTS

        # Grandparents: explicit grandparent role words
        grand_keywords = [
            "grandparent", "grandparents",
            "grandma", "grandmother",
            "grandpa", "grandfather",
        ]
        if any(k in s for k in grand_keywords):
            return CaregiverType.GRANDPARENTS

        # Other: explicit non-parent, non-grandparent caregiver words
        other_keywords = [
            "nanny", "babysitter", "daycare", "nursery",
            "aunt", "uncle", "sister", "brother",
            "neighbor", "family friend", "relative", "caregiver",
            "helper", "teacher",
        ]
        if any(k in s for k in other_keywords):
            return CaregiverType.OTHER

        return CaregiverType.UNKNOWN


# =========================================================
# CHILD MODEL
# =========================================================

class ChildInfo(BaseModel):
    age_months: Optional[int] = Field(None, ge=0, le=60)
    has_malnutrition_signs: Optional[bool] = None

    @property
    def age_range(self) -> Optional[ChildAgeRange]:
        if self.age_months is None:
            return None
        if self.age_months < 6:
            return ChildAgeRange.UNDER_6_MONTHS
        if self.age_months < 12:
            return ChildAgeRange.SIX_TO_11_MONTHS
        if self.age_months < 24:
            return ChildAgeRange.TWELVE_TO_23_MONTHS
        return ChildAgeRange.TWO_TO_FIVE_YEARS

    @property
    def vulnerability_score(self) -> Optional[float]:
        ar = self.age_range
        if ar is None:
            return None

        age_scores = {
            ChildAgeRange.UNDER_6_MONTHS: 1.0,
            ChildAgeRange.SIX_TO_11_MONTHS: 2.26,
            ChildAgeRange.TWELVE_TO_23_MONTHS: 2.31,
            ChildAgeRange.TWO_TO_FIVE_YEARS: 1.5,
        }

        score = age_scores[ar]

        if self.has_malnutrition_signs is True:
            score *= 1.14

        return round(score, 2)


# =========================================================
# SURVEY DEPENDENCIES
# =========================================================

class Domain1SurveyDeps(BaseModel):
    conversation_history: list[str] = Field(default_factory=list)


class ValidationDecision(BaseModel):
    status: Literal["OK", "NEED_FOLLOWUP", "GIVE_UP"]
    followup: Optional[str] = None
    note: Optional[str] = None


# =========================================================
# MAIN DOMAIN MODEL
# =========================================================

class Domain1Data(BaseModel):

    num_children_under_5: Optional[int] = Field(None, ge=0)
    children: List[ChildInfo] = Field(default_factory=list)

    has_vulnerable_members: Optional[bool] = None
    has_elderly_members: Optional[bool] = None
    has_immunocompromised_members: Optional[bool] = None

    primary_caregiver: CaregiverType = CaregiverType.UNKNOWN

    # -----------------------------------------------------
    # RISK CALCULATION
    # -----------------------------------------------------

    @property
    def domain_weight(self) -> float:
        return 0.10

    @property
    def overall_vulnerability_score(self) -> float:
        scores = [
            c.vulnerability_score for c in self.children
            if c.vulnerability_score is not None
        ]
        if not scores:
            return 0.0

        avg_child_score = sum(scores) / len(scores)
        household_multiplier = 1.0

        # Optional: light multiplier for non-parent caregiving (tunable)
        if self.primary_caregiver == CaregiverType.GRANDPARENTS:
            household_multiplier *= 1.05
        elif self.primary_caregiver == CaregiverType.OTHER:
            household_multiplier *= 1.10

        has_vuln = self.has_vulnerable_members
        if has_vuln is None:
            has_vuln = (
                self.has_elderly_members is True
                or self.has_immunocompromised_members is True
            )

        if has_vuln is True:
            household_multiplier *= 1.10

        return round(avg_child_score * household_multiplier, 2)

    # -----------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------

    def get_risk_summary(self) -> dict:
        high_risk_age_children = [
            c for c in self.children
            if c.age_range in (
                ChildAgeRange.SIX_TO_11_MONTHS,
                ChildAgeRange.TWELVE_TO_23_MONTHS,
            )
        ]

        malnourished_children = [
            c for c in self.children if c.has_malnutrition_signs is True
        ]

        vulnerable_members_present = (
            self.has_vulnerable_members is True
            or self.has_elderly_members is True
            or self.has_immunocompromised_members is True
        )

        return {
            "domain": "Demographics & Vulnerability Factors",
            "domain_weight": self.domain_weight,
            "total_children": self.num_children_under_5,
            "high_risk_age_children": len(high_risk_age_children),
            "malnourished_children": len(malnourished_children),
            "primary_caregiver_type": self.primary_caregiver.value,
            "vulnerable_members_present": vulnerable_members_present,
            "overall_vulnerability_score": self.overall_vulnerability_score,
            "weighted_score": round(
                self.overall_vulnerability_score * self.domain_weight, 2
            ),
        }

    # -----------------------------------------------------
    # BUILDER
    # -----------------------------------------------------

    @classmethod
    def from_answers(cls, answers: Dict[str, Any], *, strict_len: bool = False):

        # -------------------------
        # Prefer children[] array
        # -------------------------
        children: List[ChildInfo] = []

        raw_children = answers.get("children")
        if isinstance(raw_children, list):
            for item in raw_children:
                if not isinstance(item, dict):
                    continue

                age = _to_int_or_none(item.get("age_months", item.get("age")))
                mal = _to_bool_or_none(
                    item.get(
                        "has_malnutrition_signs",
                        item.get("malnutrition", item.get("malnourished")),
                    )
                )

                # Keep entries even if only one field is present
                if age is not None or mal is not None:
                    children.append(ChildInfo(age_months=age, has_malnutrition_signs=mal))

        # -------------------------
        # Fallback: flat keys
        # -------------------------
        if not children:
            max_index = 0
            for key in answers.keys():
                m = re.match(r"child(\d+)_", key)
                if m:
                    max_index = max(max_index, int(m.group(1)))

            for i in range(1, max_index + 1):
                age = _to_int_or_none(answers.get(f"child{i}_age"))
                mal = _to_bool_or_none(answers.get(f"child{i}_malnutrition"))

                if age is not None or mal is not None:
                    children.append(ChildInfo(age_months=age, has_malnutrition_signs=mal))

        # -------------------------
        # Number of children
        # -------------------------
        raw_n = answers.get("num_children_under_5", answers.get("num_children"))
        n = _to_int_or_none(raw_n)

        if strict_len and isinstance(n, int) and len(children) != n:
            raise ValueError(
                f"Children detail count ({len(children)}) does not match num_children_under_5 ({n})"
            )

        # -------------------------
        # Vulnerability fields
        # -------------------------
        has_vulnerable = _to_bool_or_none(answers.get("has_vulnerable_members"))
        has_elderly = _to_bool_or_none(answers.get("has_elderly_members"))
        has_immuno = _to_bool_or_none(answers.get("has_immunocompromised_members"))

        raw_cg = (
            answers.get("primary_caregiver")
            or answers.get("caregiver")
            or answers.get("primary_caregiver_type")
        )
        caregiver = CaregiverType.from_llm_value(raw_cg)

        return cls(
            num_children_under_5=n,
            children=children,
            has_vulnerable_members=has_vulnerable,
            has_elderly_members=has_elderly,
            has_immunocompromised_members=has_immuno,
            primary_caregiver=caregiver,
        )