"""
Pydantic AI Agent for Domain 1: Demographics & Vulnerability Factors Survey
"""
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from pydantic import Field
from typing import Optional
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.domain1 import Domain1Data, ChildInfo, CaregiverType


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
        system_prompt="""You are a compassionate and professional survey interviewer collecting information about household demographics and vulnerability factors.

You MUST ask the respondent EXACTLY the following six questions, in this order, using the exact wording inside the quotation marks:

Q1: "How many children under five years old live in your household?"
Q2: "Please tell me the age in months of the first child under five."
Q3: "Has the first child shown signs of malnutrition, like weight loss or not growing well?"
Q4: "Please tell me the age in months of the second child under five. If there is no second child, say 'No second child'."
Q5: "Has the second child shown signs of malnutrition, like weight loss or not growing well? If there is no second child, say 'No second child'."
Q6: "Are there any elderly or immunocompromised members in your household, and who mainly takes care of the small children during the day?"

CRITICAL RULES:
- Start with a very short greeting (one sentence), then immediately ask Q1.
- Ask ONE question at a time and wait for the respondent's answer.
- If the respondent reports N children under five, only ask the age/malnutrition pair for those N children (N can be 0, 1, or 2 in this short form). If fewer than two children, accept 'No second child' for the extra child-specific questions.
- Use simple, clear language suitable for low-literacy settings. You may give brief clarification if the respondent seems confused, but the question sentences themselves MUST stay exactly as written above.
- Do NOT ask any extra questions beyond these six.
- After you have asked all six questions and received answers, reply with exactly:

  SURVEY_COMPLETE

  (in all caps, no additional text).

Do NOT say SURVEY_COMPLETE until all six questions have been answered.
""",
    )


def get_extraction_agent() -> Agent:
    """Get the extraction agent (converts conversation to structured data)"""
    return Agent(
        'openai:gpt-4o',
        output_type=dict,
        model_settings={"temperature": 0},
        system_prompt="""You are a data extraction specialist.

TASK:
From the conversation transcript, produce a SINGLE flat JSON object with keys:

- "num_children_under_5": integer
- For each child i starting from 1 in order (only up to the number given):
  - "child{i}_age": integer (months)
  - "child{i}_malnutrition": boolean (true/false)
- "has_elderly_members": boolean
- "has_immunocompromised_members": boolean
- "primary_caregiver": one of:
  "Both parents", "Single mother", "Single father",
  "Grandparent", "Other relative", "Other", "Unknown"

IMPORTANT:
- Only extract information explicitly stated in the transcript.
- If unknown/unclear, set "primary_caregiver" to "Unknown" (do NOT guess).
- "Parents live together" does NOT imply "Both parents" as primary caregiver.
- Use "Both parents" ONLY if the respondent clearly indicates shared caregiving
  (e.g., "both parents take care", "equally", "shared").
- If the respondent says mother mainly/primarily takes care, use "Single mother".
- If the respondent says father mainly/primarily takes care, use "Single father".
- If the respondent says grandmother/grandparent takes care, use "Grandparent".
- If the respondent says aunt/uncle/relative takes care, use "Other relative".
- If Q6 mentions elderly and/or immunocompromised, set those booleans accordingly.
- If the respondent says 'No second child', OMIT child2_* keys.
- If a key is unknown (except caregiver), you may omit it.

CRITICAL:
You MUST return the result by CALLING the built-in tool named `response` with a single argument `response` set to your JSON object.
Do NOT print text. Do NOT wrap in markdown. Do NOT include any other fields.
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
