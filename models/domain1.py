"""
Domain 1: Demographics & Vulnerability Factors
Purpose: Identify vulnerable populations requiring targeted assessment
"""
import re
from pydantic import BaseModel, Field, field_validator
from typing import List, Any, Dict
from enum import Enum


class ChildAgeRange(str, Enum):
    """Age ranges with associated risk levels"""
    UNDER_6_MONTHS = "0-5 months"
    SIX_TO_11_MONTHS = "6-11 months"  # OR 2.26 (1.50-3.42)
    TWELVE_TO_23_MONTHS = "12-23 months"  # OR 2.31 (1.62-3.31) - peak
    TWO_TO_FIVE_YEARS = "24-60 months"


class ChildInfo(BaseModel):
    """Information about a child in the household"""
    age_months: int = Field(..., ge=0, le=60, description="Child's age in months")
    has_malnutrition_signs: bool = Field(
        ...,
        description="Has the child shown signs of malnutrition (weight loss, growth problems)?"
    )

    @property
    def age_range(self) -> ChildAgeRange:
        """Determine the child's age range category"""
        if self.age_months < 6:
            return ChildAgeRange.UNDER_6_MONTHS
        elif 6 <= self.age_months < 12:
            return ChildAgeRange.SIX_TO_11_MONTHS
        elif 12 <= self.age_months < 24:
            return ChildAgeRange.TWELVE_TO_23_MONTHS
        else:
            return ChildAgeRange.TWO_TO_FIVE_YEARS

    @property
    def vulnerability_score(self) -> float:
        """Calculate vulnerability score based on age and nutritional status"""
        # Base score from age (using OR values as weights)
        age_scores = {
            ChildAgeRange.UNDER_6_MONTHS: 1.0,
            ChildAgeRange.SIX_TO_11_MONTHS: 2.26,
            ChildAgeRange.TWELVE_TO_23_MONTHS: 2.31,  # peak vulnerability
            ChildAgeRange.TWO_TO_FIVE_YEARS: 1.5
        }
        score = age_scores[self.age_range]

        # Adjust for malnutrition (aOR 1.14)
        if self.has_malnutrition_signs:
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
        """
        Map LLM extracted caregiver string (human-readable) to enum safely.
        Accepts values like "Single mother" / "Both parents" / "Unknown".
        """
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

# ---------- small parsing helpers ----------
def _to_int(x: Any, default: int = 0) -> int:
    try:
        return int(str(x).strip())
    except Exception:
        return default

def _to_bool(x: Any, default: bool = False) -> bool:
    if isinstance(x, bool):
        return x
    v = str(x or "").strip().lower()
    if v in {"1", "true", "t", "yes", "y", "是", "有"}:
        return True
    if v in {"0", "false", "f", "no", "n", "否", "无"}:
        return False
    return default


class Domain1Data(BaseModel):
    """Complete data model for Domain 1: Demographics & Vulnerability Factors"""

    # Household composition
    num_children_under_5: int = Field(..., ge=0, description="Number of children under 5 years")
    children: List[ChildInfo] = Field(default_factory=list, description="Details of each child")

    # Vulnerable household members
    has_elderly_members: bool = Field(..., description="Are there elderly household members?")
    has_immunocompromised_members: bool = Field(
        ...,
        description="Are there immunocompromised or chronically ill members?"
    )

    # Caregiver information
    primary_caregiver: CaregiverType = Field(..., description="Who is the primary caregiver?")

    @field_validator('children')
    @classmethod
    def validate_children_count(cls, v, info):
        """Ensure number of children matches the count"""
        num_children = info.data.get('num_children_under_5', 0)
        if len(v) != num_children:
            raise ValueError(
                f"Number of children details ({len(v)}) must match num_children_under_5 ({num_children})"
            )
        return v

    @property
    def domain_weight(self) -> float:
        """Domain 1 weight in overall risk assessment"""
        return 0.10

    @property
    def overall_vulnerability_score(self) -> float:
        """Calculate overall vulnerability score for the household"""
        if not self.children:
            return 0.0

        # Average child vulnerability
        avg_child_score = sum(child.vulnerability_score for child in self.children) / len(self.children)

        # Adjust for household factors
        household_multiplier = 1.0

        # Single parent increases vulnerability (affects supervision capacity)
        if self.primary_caregiver in [CaregiverType.SINGLE_MOTHER, CaregiverType.SINGLE_FATHER]:
            household_multiplier *= 1.15

        # Elderly or immunocompromised members increase vulnerability
        if self.has_elderly_members:
            household_multiplier *= 1.10
        if self.has_immunocompromised_members:
            household_multiplier *= 1.10

        return round(avg_child_score * household_multiplier, 2)

    def get_risk_summary(self) -> dict:
        """Generate a summary of risk factors"""
        high_risk_children = [
            c for c in self.children
            if c.age_range in [ChildAgeRange.SIX_TO_11_MONTHS, ChildAgeRange.TWELVE_TO_23_MONTHS]
               or c.has_malnutrition_signs  
        ]
        malnourished_children = [c for c in self.children if c.has_malnutrition_signs]

        return {
            "domain": "Demographics & Vulnerability Factors",
            "domain_weight": self.domain_weight,
            "total_children": self.num_children_under_5,
            "high_risk_age_children": len(high_risk_children),
            "malnourished_children": len(malnourished_children),
            "single_parent_household": self.primary_caregiver in [
                CaregiverType.SINGLE_MOTHER,
                CaregiverType.SINGLE_FATHER
            ],
            "vulnerable_members_present": self.has_elderly_members or self.has_immunocompromised_members,
            "overall_vulnerability_score": self.overall_vulnerability_score,
            "weighted_score": round(self.overall_vulnerability_score * self.domain_weight, 2)
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

        Behavior:
          - If strict_len=False (default): will trim/pad children list to match N before constructing
          - If strict_len=True: rely on the validator (raises if len != N)
        """

        raw_n = answers.get("num_children_under_5", answers.get("num_children", 0))
        n_explicit = _to_int(raw_n, 0)
        if n_explicit < 0:
            n_explicit = 0

        max_index = 0
        for key in answers.keys():
            # child{i}_age / child{i}_malnutrition / child{i}_malnourished / child{i}_mal / child{i}_is_malnourished
            m = re.match(r"child(\d+)_(age|malnutrition|malnourished|mal|is_malnourished)", key)
            if m:
                idx = int(m.group(1))
                if idx > max_index:
                    max_index = idx

            # age_child{i}
            m2 = re.match(r"age_child(\d+)", key)
            if m2:
                idx = int(m2.group(1))
                if idx > max_index:
                    max_index = idx

        n_inferred = max_index

        if n_explicit > 0:
            n = n_explicit
        else:
            n = n_inferred

        if n < 0:
            n = 0

        children: List[ChildInfo] = []
        for i in range(1, max(n, 0) + 1):
            age = _to_int(
                answers.get(
                    f"child{i}_age",
                    answers.get(f"age_child{i}", 0)
                ),
                0
            )
            mal = _to_bool(
                answers.get(
                    f"child{i}_malnutrition",
                    answers.get(
                        f"child{i}_malnourished",
                        answers.get(
                            f"child{i}_mal",
                            answers.get(f"child{i}_is_malnourished", False)
                        )
                    )
                )
            )
            children.append(ChildInfo(age_months=age, has_malnutrition_signs=mal))

        if not strict_len:
            if len(children) > n:
                children = children[:n]
            while len(children) < n:
                children.append(ChildInfo(age_months=0, has_malnutrition_signs=False))

        has_elderly = _to_bool(answers.get("has_elderly_members", answers.get("elderly", False)))
        has_immuno = _to_bool(answers.get("has_immunocompromised_members", answers.get("immunocompromised", False)))
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