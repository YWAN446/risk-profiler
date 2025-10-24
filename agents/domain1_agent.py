"""
Pydantic AI Agent for Domain 1: Demographics & Vulnerability Factors Survey
"""
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from typing import Optional
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.domain1 import Domain1Data, ChildInfo, CaregiverType


class Domain1SurveyDeps(BaseModel):
    """Dependencies for the Domain 1 survey agent"""
    conversation_history: list[str] = []


# Global variable to hold the agent instance
_domain1_agent = None


def get_conversation_agent() -> Agent:
    """Get the conversational agent (returns text, not structured data)"""
    return Agent(
        'openai:gpt-4o',
        deps_type=Domain1SurveyDeps,
        system_prompt="""You are a compassionate and professional survey interviewer collecting information about household demographics and vulnerability factors.

Your goal is to collect the following information through conversation:
1. Number of children under 5 years old in the household
2. For EACH child: their age in months and whether they show signs of malnutrition
3. Whether there are elderly household members
4. Whether there are immunocompromised or chronically ill household members
5. Who the primary caregiver is (both parents, single mother, single father, grandparent, other relative, or other)

CRITICAL RULES:
- Ask questions ONE AT A TIME in a conversational manner
- Be empathetic and non-judgamental, especially when asking about sensitive topics like malnutrition
- Use simple, clear language that is easy to understand
- When asking about malnutrition signs, explain that this includes: weight loss, poor growth, lack of energy, or concerns about the child's development
- Keep track of what information you've already collected
- Once you have collected ALL information, respond with exactly: "SURVEY_COMPLETE"

Start by greeting the respondent warmly and asking about the number of children under 5 in their household.
""",
    )


def get_extraction_agent() -> Agent:
    """Get the extraction agent (converts conversation to structured data)"""
    return Agent(
        'openai:gpt-4o',
        output_type=Domain1Data,
        system_prompt="""You are a data extraction specialist. Extract household demographic information from the conversation transcript provided.

Extract the following information:
1. Number of children under 5 years old
2. For EACH child: age in months and malnutrition status
3. Elderly household members (yes/no)
4. Immunocompromised household members (yes/no)
5. Primary caregiver type

IMPORTANT: Only extract information explicitly stated in the conversation. Do not make assumptions or invent data.
""",
    )


# Maintain backward compatibility
def get_domain1_agent() -> Agent:
    """Get or create the Domain 1 agent instance (for backward compatibility)"""
    return get_conversation_agent()


# Convenience property for backward compatibility
@property
def domain1_agent():
    return get_domain1_agent()


async def run_domain1_survey() -> Domain1Data:
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
        "Start the survey by greeting the respondent.",
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
            result = await conversation_agent.run(user_input, deps=deps)
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

                return extraction_result.output

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
