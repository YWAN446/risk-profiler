"""
agents/domain3_agent.py

Domain 3 Agent: Temporal / Seasonal Factors

Responsibilities
---------------
Conversation agent:
    Runs the Domain 3 survey using the standardized question script.

Validation agent:
    Validates each user response and determines whether a clarification
    question is needed.

Extraction agent:
    Converts the full conversation into structured JSON for Domain3Data.

This mirrors Domain 2's agent structure for consistency.
"""

from pathlib import Path

from pydantic_ai import Agent

from models.domain3 import Domain3SurveyDeps


# --------------------------------------------------
# Prompt directory
# --------------------------------------------------

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


# --------------------------------------------------
# Load prompts
# --------------------------------------------------

DOMAIN3_CONVO_PROMPT = (
    PROMPTS_DIR / "domain3_conversation_system_prompt.md"
).read_text(encoding="utf-8")

DOMAIN3_SURVEY_QUESTIONS = (
    PROMPTS_DIR / "domain3_survey_questions.md"
).read_text(encoding="utf-8")

DOMAIN3_VALIDATION_PROMPT = (
    PROMPTS_DIR / "domain3_validation_system_prompt.md"
).read_text(encoding="utf-8")

DOMAIN3_EXTRACTION_PROMPT = (
    PROMPTS_DIR / "domain3_extraction_system_prompt.md"
).read_text(encoding="utf-8")


# --------------------------------------------------
# Agents
# --------------------------------------------------

def get_domain3_conversation_agent() -> Agent:
    """
    Agent that runs the Domain 3 survey conversation.

    The survey question script is appended to the system prompt
    so the model always follows the standardized question order.
    """
    return Agent(
        "openai:gpt-4o",
        system_prompt=DOMAIN3_CONVO_PROMPT + "\n\n" + DOMAIN3_SURVEY_QUESTIONS,
        deps_type=Domain3SurveyDeps,
        model_settings={"temperature": 0.2},
    )


def get_domain3_validation_agent() -> Agent:
    """
    Validator agent for Domain 3 answers.
    Determines whether the response is valid or needs clarification.
    """
    return Agent(
        "openai:gpt-4o",
        system_prompt=DOMAIN3_VALIDATION_PROMPT,
        output_type=dict,
        model_settings={"temperature": 0},
    )


def get_domain3_extraction_agent() -> Agent:
    """
    Extracts structured Domain 3 JSON from the full conversation.
    """
    return Agent(
        "openai:gpt-4o",
        system_prompt=DOMAIN3_EXTRACTION_PROMPT,
        output_type=dict,
        model_settings={"temperature": 0},
    )