"""
Pydantic AI Agent for Domain 1: Demographics & Vulnerability Factors Survey
"""
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from pydantic import Field
from typing import Optional
from pathlib import Path
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.domain1 import Domain1Data, ChildInfo, CaregiverType

# Path to prompts directory
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(filename: str) -> str:
    """Load a prompt from a markdown file"""
    prompt_path = PROMPTS_DIR / filename
    return prompt_path.read_text(encoding="utf-8")


def get_conversation_system_prompt() -> str:
    """Build the full conversation system prompt from components"""
    base_prompt = load_prompt("conversation_system_prompt.md")
    questions = load_prompt("survey_questions.md")
    return f"{base_prompt}\n\n{questions}"


def get_extraction_system_prompt() -> str:
    """Load the extraction system prompt"""
    return load_prompt("extraction_system_prompt.md")


class Domain1SurveyDeps(BaseModel):
    """Dependencies for the Domain 1 survey agent"""
    conversation_history: list[str] = Field(default_factory=list)


# Global variable to hold the agent instance
_domain1_agent = None


def get_conversation_agent() -> Agent:
    """Get the conversational agent (returns text, not structured data)"""
    return Agent(
        'openai:gpt-4o',
        deps_type=Domain1SurveyDeps,
        system_prompt=get_conversation_system_prompt(),
    )


def get_extraction_agent() -> Agent:
    """Get the extraction agent (converts conversation to structured data)"""
    return Agent(
        'openai:gpt-4o',
        output_type=dict,
        model_settings={"temperature": 0},
        system_prompt=get_extraction_system_prompt(),
    )


# Maintain backward compatibility
def get_domain1_agent() -> Agent:
    """Get or create the Domain 1 agent instance (for backward compatibility)"""
    return get_conversation_agent()


# Convenience property for backward compatibility
@property
def domain1_agent():
    return get_domain1_agent()


async def run_domain1_survey() -> Optional[Domain1Data]:
    """
    Run the Domain 1 survey as an interactive conversation
    Returns the completed Domain1Data object
    """
    conversation_agent = get_conversation_agent()
    deps = Domain1SurveyDeps()

    print("=" * 60)
    print("DOMAIN 1: Demographics & Vulnerability Factors Survey")
    print("=" * 60)
    print()

    # Initial greeting from agent
    result = await conversation_agent.run(
        "Start the survey by greeting the respondent and then ask Q1.",
        deps=deps
    )

    agent_response = str(result.output)
    deps.conversation_history.append(f"Agent: {agent_response}")
    print(f"Agent: {agent_response}")
    print()

    # Conversation loop
    while True:
        try:
            # Get user input
            user_input = input("You: ").strip()
            if not user_input:
                continue

            # Add to conversation history
            deps.conversation_history.append(f"Respondent: {user_input}")

            # Get agent response
            transcript = "\n".join(deps.conversation_history)
            next_step_prompt = f"""You are continuing a fixed 6-question survey.

            Transcript so far:
            {transcript}
            
            The respondent just answered: "{user_input}"
            
            Rules:
            - Ask only the NEXT required question from the 6-question script.
            - Do not repeat earlier questions that have already been asked AND answered.
            - If all six questions are answered, reply with SURVEY_COMPLETE (exactly)."""

            result = await conversation_agent.run(next_step_prompt, deps=deps)
            
            agent_response = str(result.output)
            deps.conversation_history.append(f"Agent: {agent_response}")

            # Check if survey is complete
            if "SURVEY_COMPLETE" in agent_response:
                print("\n" + "=" * 60)
                print("Survey Complete! Extracting structured data...")
                print("=" * 60)

                # Use extraction agent to convert conversation to structured data
                extraction_agent = get_extraction_agent()
                conversation_text = "\n".join(deps.conversation_history)
                extraction_result = await extraction_agent.run(
                    f"Extract the household data from this conversation:\n\n{conversation_text}"
                )

                answers = extraction_result.output or {}
                d1 = Domain1Data.from_answers(answers, strict_len=False)

                return d1
                
            # Otherwise, continue conversation
            print(f"Agent: {agent_response}")
            print()

        except KeyboardInterrupt:
            print("\n\nSurvey interrupted by user.")
            return None
        except Exception as e:
            print(f"\nError: {e}")
            print("Let's continue...\n")


if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv

    load_dotenv()

    async def main():
        result = await run_domain1_survey()
        if result:
            print("\n" + "=" * 60)
            print("COLLECTED DATA:")
            print("=" * 60)
            print(result.model_dump_json(indent=2))
            print("\n" + "=" * 60)
            print("RISK SUMMARY:")
            print("=" * 60)
            summary = result.get_risk_summary()
            for key, value in summary.items():
                print(f"{key}: {value}")

    asyncio.run(main())
