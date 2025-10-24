"""
Domain 1: Demographics & Vulnerability Factors
Purpose: Identify vulnerable populations requiring targeted assessment
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
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
            child for child in self.children
            if child.age_range in [ChildAgeRange.SIX_TO_11_MONTHS, ChildAgeRange.TWELVE_TO_23_MONTHS]
        ]

        malnourished_children = [child for child in self.children if child.has_malnutrition_signs]

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
