"""
Pydantic AI Agent for Domain 1: Demographics & Vulnerability Factors Survey
"""
import sys
from pathlib import Path
from typing import Optional

from pydantic_ai import Agent

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.domain1 import Domain1Data, Domain1SurveyDeps, ValidationDecision
from util import (
    get_conversation_system_prompt,
    get_extraction_system_prompt,
    get_validation_system_prompt,
    load_questions,
    extract_int_0_2,
)

# Load questions from external file
QUESTIONS = load_questions()


def get_conversation_agent() -> Agent:
    """Get the conversational agent (returns text, not structured data)"""
    return Agent(
        "openai:gpt-4o",
        deps_type=Domain1SurveyDeps,
        system_prompt=get_conversation_system_prompt(),
    )


def get_extraction_agent() -> Agent:
    """Get the extraction agent (converts conversation to structured data)"""
    return Agent(
        "openai:gpt-4o",
        output_type=dict,
        model_settings={"temperature": 0},
        system_prompt=get_extraction_system_prompt(),
    )


def get_validation_agent() -> Agent:
    """Get the validation agent (validates answers and generates follow-ups)"""
    return Agent(
        "openai:gpt-4o",
        output_type=ValidationDecision,
        model_settings={"temperature": 0},
        system_prompt=get_validation_system_prompt(),
    )


async def run_domain1_survey() -> Optional[Domain1Data]:
    """Run the Domain 1 survey interactively via command line."""
    validation_agent = get_validation_agent()
    extraction_agent = get_extraction_agent()
    deps = Domain1SurveyDeps()
    num_questions = len(QUESTIONS)

    print("=" * 60)
    print("DOMAIN 1: Demographics & Vulnerability Factors Survey")
    print("=" * 60)
    print()

    greet_q1 = f'Hello, thank you for participating in our survey today. "{QUESTIONS[0]}"'
    deps.conversation_history.append(f"Agent: {greet_q1}")
    print(f"Agent: {greet_q1}\n")

    q_idx = 0
    followup_used = [False] * num_questions
    n_children: Optional[int] = None

    def should_skip(idx: int) -> bool:
        if idx == 0 or n_children is None:
            return False
        if n_children == 0 and idx in (1, 2, 3, 4):
            return True
        if n_children == 1 and idx in (3, 4):
            return True
        return False

    def record_na(idx: int, reason: str):
        deps.conversation_history.append(
            f"System: Question recorded as NA. Q{idx+1}: {QUESTIONS[idx]} | Reason: {reason}"
        )

    async def ask_question(idx: int):
        q_text = f'"{QUESTIONS[idx]}"'
        deps.conversation_history.append(f"Agent: {q_text}")
        print(f"Agent: {q_text}\n")

    while q_idx < num_questions:
        if should_skip(q_idx):
            record_na(q_idx, f"Not applicable given num_children_under_5={n_children}")
            followup_used[q_idx] = False
            q_idx += 1
            if q_idx < num_questions and not should_skip(q_idx):
                await ask_question(q_idx)
            continue

        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
        except KeyboardInterrupt:
            print("\n\nSurvey interrupted by user.")
            return None

        deps.conversation_history.append(f"Respondent: {user_input}")

        vd = await validation_agent.run(
            f'question_asked: "{QUESTIONS[q_idx]}"\n'
            f"respondent_answer: {user_input}\n"
            f"followup_used: {str(followup_used[q_idx]).lower()}"
        )
        decision: ValidationDecision = vd.response

        if decision.status == "NEED_FOLLOWUP":
            followup_used[q_idx] = True
            followup_text = (decision.followup or "Could you please clarify?").strip()
            deps.conversation_history.append(f"Agent: {followup_text}")
            print(f"Agent: {followup_text}\n")
            continue

        if decision.status == "GIVE_UP":
            record_na(q_idx, "Unclear after 1 follow-up")
            followup_used[q_idx] = False
            q_idx += 1
            while q_idx < num_questions and should_skip(q_idx):
                record_na(q_idx, f"Not applicable given num_children_under_5={n_children}")
                q_idx += 1
            if q_idx < num_questions:
                await ask_question(q_idx)
            continue

        followup_used[q_idx] = False
        if q_idx == 0:
            n_children = extract_int_0_2(user_input)

        q_idx += 1
        while q_idx < num_questions and should_skip(q_idx):
            record_na(q_idx, f"Not applicable given num_children_under_5={n_children}")
            q_idx += 1
        if q_idx < num_questions:
            await ask_question(q_idx)

    deps.conversation_history.append("Agent: SURVEY_COMPLETE")
    print("Agent: SURVEY_COMPLETE\n")
    print("=" * 60)
    print("Survey Complete! Extracting structured data...")
    print("=" * 60)

    conversation_text = "\n".join(deps.conversation_history)
    extraction_result = await extraction_agent.run(
        f"Extract the household data from this conversation:\n\n{conversation_text}"
    )
    answers = extraction_result.response or {}
    return Domain1Data.from_answers(answers, strict_len=False)


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