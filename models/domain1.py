"""
Domain 1: Demographics & Vulnerability Factors
Purpose: Identify vulnerable populations requiring targeted assessment
"""
import re
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ChildAgeRange(str, Enum):
    """Age ranges with associated risk levels"""
    UNDER_6_MONTHS = "0-5 months"
    SIX_TO_11_MONTHS = "6-11 months"         # OR 2.26 (1.50-3.42)
    TWELVE_TO_23_MONTHS = "12-23 months"     # OR 2.31 (1.62-3.31) - peak
    TWO_TO_FIVE_YEARS = "24-60 months"


class ChildInfo(BaseModel):
    """Information about a child in the household"""
    age_months: Optional[int] = Field(None, ge=0, le=60, description="Child's age in months")
    has_malnutrition_signs: Optional[bool] = Field(
        None,
        description="Has the child shown signs of malnutrition (weight loss, growth problems)?"
    )

    @property
    def age_range(self) -> Optional[ChildAgeRange]:
        """Determine the child's age range category, or None if age unknown."""
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
        """Calculate vulnerability score based on age and nutritional status.
        Returns None if age unknown (cannot score).
        """
        ar = self.age_range
        if ar is None:
            return None

        age_scores = {
            ChildAgeRange.UNDER_6_MONTHS: 1.0,
            ChildAgeRange.SIX_TO_11_MONTHS: 2.26,
            ChildAgeRange.TWELVE_TO_23_MONTHS: 2.31,  # peak vulnerability
            ChildAgeRange.TWO_TO_FIVE_YEARS: 1.5,
        }
        score = age_scores[ar]

        # Adjust for malnutrition (aOR 1.14) only if explicitly True
        if self.has_malnutrition_signs is True:
            score *= 1.14

        return round(score, 2)


class CaregiverType(str, Enum):
    """Primary caregiver types"""
    BOTH_PARENTS = "Both parents"
    SINGLE_MOTHER = "Single mother"
    SINGLE_FATHER = "Single father"
    GRANDPARENT = "Grandparent"
    OTHER_RELATIVE = "Other relative"
    OTHER = "Other"
    UNKNOWN = "Unknown"

    @staticmethod
    def from_llm_value(v: Any) -> "CaregiverType":
        """Map LLM extracted caregiver string (human-readable) to enum safely."""
        s = str(v or "").strip()
        mapping = {
            "Both parents": CaregiverType.BOTH_PARENTS,
            "Single mother": CaregiverType.SINGLE_MOTHER,
            "Single father": CaregiverType.SINGLE_FATHER,
            "Grandparent": CaregiverType.GRANDPARENT,
            "Other relative": CaregiverType.OTHER_RELATIVE,
            "Other": CaregiverType.OTHER,
            "Unknown": CaregiverType.UNKNOWN,
        }
        return mapping.get(s, CaregiverType.UNKNOWN)


class Domain1SurveyDeps(BaseModel):
    """Dependencies for the Domain 1 survey agent"""
    conversation_history: list[str] = Field(default_factory=list)


class ValidationDecision(BaseModel):
    """Validation result for survey answers"""
    status: Literal["OK", "NEED_FOLLOWUP", "GIVE_UP"]
    followup: Optional[str] = None
    note: Optional[str] = None


# ---------- small parsing helpers ----------
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


class Domain1Data(BaseModel):
    """Complete data model for Domain 1: Demographics & Vulnerability Factors"""

    # Household composition
    num_children_under_5: Optional[int] = Field(
        None, ge=0, description="Number of children under 5 years (None if unknown)"
    )
    children: List[ChildInfo] = Field(default_factory=list, description="Details of each child")

    # Vulnerable household members
    has_elderly_members: Optional[bool] = Field(None, description="Are there elderly household members?")
    has_immunocompromised_members: Optional[bool] = Field(
        None,
        description="Are there immunocompromised or chronically ill members?"
    )

    # Caregiver information
    primary_caregiver: CaregiverType = Field(CaregiverType.UNKNOWN, description="Who is the primary caregiver?")

    @property
    def domain_weight(self) -> float:
        """Domain 1 weight in overall risk assessment"""
        return 0.10

    @property
    def overall_vulnerability_score(self) -> float:
        """Calculate overall vulnerability score for the household.
        Uses only children with computable scores (age known).
        """
        scores = [c.vulnerability_score for c in self.children if c.vulnerability_score is not None]
        if not scores:
            return 0.0

        avg_child_score = sum(scores) / len(scores)

        household_multiplier = 1.0

        # Single parent increases vulnerability (affects supervision capacity)
        if self.primary_caregiver in (CaregiverType.SINGLE_MOTHER, CaregiverType.SINGLE_FATHER):
            household_multiplier *= 1.15

        # Elderly or immunocompromised members increase vulnerability only if explicitly True
        if self.has_elderly_members is True:
            household_multiplier *= 1.10
        if self.has_immunocompromised_members is True:
            household_multiplier *= 1.10

        return round(avg_child_score * household_multiplier, 2)

    def get_risk_summary(self) -> dict:
        """Generate a summary of risk factors (robust to NA/None)."""

        # Age-risk counts should ONLY depend on known age ranges
        high_risk_age_children = [
            c for c in self.children
            if c.age_range in (ChildAgeRange.SIX_TO_11_MONTHS, ChildAgeRange.TWELVE_TO_23_MONTHS)
        ]

        malnourished_children = [c for c in self.children if c.has_malnutrition_signs is True]

        # Optional: overall high-risk child if age high-risk OR malnutrition
        high_risk_children_any = [
            c for c in self.children
            if (
                c.age_range in (ChildAgeRange.SIX_TO_11_MONTHS, ChildAgeRange.TWELVE_TO_23_MONTHS)
                or c.has_malnutrition_signs is True
            )
        ]

        vulnerable_members_present = (self.has_elderly_members is True) or (self.has_immunocompromised_members is True)

        return {
            "domain": "Demographics & Vulnerability Factors",
            "domain_weight": self.domain_weight,
            "total_children": self.num_children_under_5,
            "high_risk_age_children": len(high_risk_age_children),
            "malnourished_children": len(malnourished_children),
            "high_risk_children_any": len(high_risk_children_any),
            "single_parent_household": self.primary_caregiver in (
                CaregiverType.SINGLE_MOTHER,
                CaregiverType.SINGLE_FATHER
            ),
            "vulnerable_members_present": vulnerable_members_present,
            "overall_vulnerability_score": self.overall_vulnerability_score,
            "weighted_score": round(self.overall_vulnerability_score * self.domain_weight, 2),
        }

    # ---------- builder: robustly construct from extracted answers ----------
    @classmethod
    def from_answers(cls, answers: Dict[str, Any], *, strict_len: bool = False) -> "Domain1Data":
        """
        Build Domain1Data from a flat dict extracted from the conversation.

        Accepted keys (any subset):
          - "num_children_under_5" / "num_children": int
          - For i=1..N:
              - "child{i}_age" / "age_child{i}": int (months)
              - "child{i}_malnutrition" / "child{i}_malnourished" / "child{i}_mal" / "child{i}_is_malnourished": bool
          - "has_elderly_members" / "elderly": bool
          - "has_immunocompromised_members" / "immunocompromised": bool
          - "primary_caregiver" / "caregiver": str (mapped to CaregiverType)

        NA/unknown may be omitted by the extraction agent; if "NA" strings appear,
        helpers will convert them to None.

        Behavior:
          - strict_len=False (default): do NOT fabricate missing children; keep whatever is present.
          - strict_len=True: require len(children) == num_children_under_5 when that count is known.
        """

        # --- infer max child index from keys ---
        max_index = 0
        for key in answers.keys():
            m = re.match(r"child(\d+)_(age|malnutrition|malnourished|mal|is_malnourished)", key)
            if m:
                max_index = max(max_index, int(m.group(1)))
            m2 = re.match(r"age_child(\d+)", key)
            if m2:
                max_index = max(max_index, int(m2.group(1)))

        # --- number of children (explicit preferred, else inferred) ---
        raw_n = answers.get("num_children_under_5", answers.get("num_children"))
        n_explicit = _to_int_or_none(raw_n)
        n_inferred = max_index if max_index > 0 else None
        n = n_explicit if n_explicit is not None else n_inferred
        if isinstance(n, int) and n < 0:
            n = 0

        # --- children: do NOT fabricate defaults ---
        children: List[ChildInfo] = []
        upper = max_index
        if isinstance(n, int) and n > upper:
            upper = n

        for i in range(1, upper + 1):
            age = _to_int_or_none(answers.get(f"child{i}_age", answers.get(f"age_child{i}")))
            mal = _to_bool_or_none(
                answers.get(
                    f"child{i}_malnutrition",
                    answers.get(
                        f"child{i}_malnourished",
                        answers.get(
                            f"child{i}_mal",
                            answers.get(f"child{i}_is_malnourished")
                        )
                    )
                )
            )

            # Only add a child record if we have any information for that child.
            if age is not None or mal is not None:
                children.append(ChildInfo(age_months=age, has_malnutrition_signs=mal))

        if strict_len and isinstance(n, int):
            if len(children) != n:
                raise ValueError(
                    f"Number of children details ({len(children)}) must match num_children_under_5 ({n})"
                )

        has_elderly = _to_bool_or_none(answers.get("has_elderly_members", answers.get("elderly")))
        has_immuno = _to_bool_or_none(answers.get("has_immunocompromised_members", answers.get("immunocompromised")))
        caregiver = CaregiverType.from_llm_value(
            answers.get("primary_caregiver", answers.get("caregiver", "Unknown"))
        )

        return cls(
            num_children_under_5=n,
            children=children,
            has_elderly_members=has_elderly,
            has_immunocompromised_members=has_immuno,
            primary_caregiver=caregiver,
        )