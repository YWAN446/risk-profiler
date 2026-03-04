"""
Domain 2 Agent: WASH (Water, Sanitation, Handwashing)
- Conversation agent: asks questions in order with at most one follow-up.
- Extraction agent: converts conversation to structured JSON (dict).
"""

from pathlib import Path
from pydantic_ai import Agent

from models.domain2 import Domain2SurveyDeps


PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

DOMAIN2_CONVO_PROMPT = (PROMPTS_DIR / "domain2_conversation_system_prompt.md").read_text(encoding="utf-8")
DOMAIN2_VALIDATION_PROMPT = (PROMPTS_DIR / "domain2_validation_system_prompt.md").read_text(encoding="utf-8")
DOMAIN2_EXTRACTION_PROMPT = (PROMPTS_DIR / "domain2_extraction_system_prompt.md").read_text(encoding="utf-8")


def get_domain2_conversation_agent() -> Agent:
    """
    Agent that runs the survey conversation for Domain 2.
    Note: we keep temperature low for consistency and to reduce drifting.
    """
    return Agent(
        "openai:gpt-4o",
        system_prompt=DOMAIN2_CONVO_PROMPT,
        deps_type=Domain2SurveyDeps,
        model_settings={"temperature": 0.2},
    )


def get_domain2_validation_agent() -> Agent:
    """
    Optional validator agent. You can call this before accepting an answer.
    Output type is dict so you can parse status/followup.
    """
    return Agent(
        "openai:gpt-4o",
        system_prompt=DOMAIN2_VALIDATION_PROMPT,
        output_type=dict,
        model_settings={"temperature": 0},
    )


def get_domain2_extraction_agent() -> Agent:
    """
    Extracts structured Domain 2 JSON from the full conversation.
    """
    return Agent(
        "openai:gpt-4o",
        system_prompt=DOMAIN2_EXTRACTION_PROMPT,
        output_type=dict,
        model_settings={"temperature": 0},
    )