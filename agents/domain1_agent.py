"""
Pydantic AI Agent for Domain 1: Demographics & Vulnerability Factors Survey
N-children support using template questions from prompts/survey_questions.md

Expected survey_questions.md (parsed by load_questions) contains at least 5 quoted lines:
0) Q1: number of children under five
1) Child age template question (generic "this child" wording)
2) Child malnutrition template question (generic "this child" wording)
3) Household vulnerability question (elderly/immunocompromised)
4) Caregiver question
"""
import sys
import re
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
)

# Load questions from external file
QUESTIONS = load_questions()
assert len(QUESTIONS) >= 5, f"Expected at least 5 questions, got {len(QUESTIONS)}"


# -----------------------------
# Helpers for dynamic questions
# -----------------------------
def extract_nonneg_int(text: str, max_n: int = 20) -> Optional[int]:
    """Extract a non-negative integer from free text. Return None if not found/out of range."""
    m = re.search(r"\b(\d+)\b", str(text or ""))
    if not m:
        return None
    n = int(m.group(1))
    if 0 <= n <= max_n:
        return n
    return None


def ordinal_word(i: int) -> str:
    """1->first, 2->second, 3->third, 4->fourth..."""
    mapping = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}
    return mapping.get(i, f"{i}th")


def label_child_question(template: str, child_i: int) -> str:
    """
    Lightly label a generic template question for the i-th child, without relying on
    'first/second' being present in the template.
    Example:
      template: "Please tell me the age in months of this child under five."
      -> "For the third child: Please tell me the age in months of this child under five."
    """
    ordw = ordinal_word(child_i)
    return f"For the {ordw} child: {template}"


# -----------------------------
# Agents
# -----------------------------
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


# -----------------------------
# Main Survey Runner (CLI)
# -----------------------------
async def run_domain1_survey() -> Optional[Domain1Data]:
    """Run the Domain 1 survey interactively via command line."""
    validation_agent = get_validation_agent()
    extraction_agent = get_extraction_agent()
    deps = Domain1SurveyDeps()

    # Base questions from survey_questions.md (templates)
    q1 = QUESTIONS[0]
    child_age_template = QUESTIONS[1]
    child_mal_template = QUESTIONS[2]
    household_vuln_q = QUESTIONS[3]
    caregiver_q = QUESTIONS[4]

    # Runtime questions expand after Q1
    questions_runtime = [q1]
    num_questions = len(questions_runtime)

    q_idx = 0
    followup_used = [False] * num_questions
    n_children: Optional[int] = None

    def record_na(idx: int, reason: str):
        deps.conversation_history.append(
            f"System: Question recorded as NA. Q{idx+1}: {questions_runtime[idx]} | Reason: {reason}"
        )

    async def ask_question(idx: int):
        q_text = f'"{questions_runtime[idx]}"'
        deps.conversation_history.append(f"Agent: {q_text}")
        print(f"Agent: {q_text}\n")

    print("=" * 60)
    print("DOMAIN 1: Demographics & Vulnerability Factors Survey")
    print("=" * 60)
    print()

    # Ask Q1 upfront
    await ask_question(0)

    while q_idx < num_questions:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
        except KeyboardInterrupt:
            print("\n\nSurvey interrupted by user.")
            return None

        deps.conversation_history.append(f"Respondent: {user_input}")

        # Validate answer (validator now handles caregiver conservatively)
        vd = await validation_agent.run(
            f'question_asked: "{questions_runtime[q_idx]}"\n'
            f"respondent_answer: {user_input}\n"
            f"followup_used: {str(followup_used[q_idx]).lower()}"
        )
        decision: ValidationDecision = vd.response

        # Need follow-up
        if decision.status == "NEED_FOLLOWUP":
            followup_used[q_idx] = True
            followup_text = (decision.followup or "Could you please clarify?").strip()
            deps.conversation_history.append(f"Agent: {followup_text}")
            print(f"Agent: {followup_text}\n")
            continue

        # Give up after 1 follow-up
        if decision.status == "GIVE_UP":
            record_na(q_idx, "Unclear after 1 follow-up")
            followup_used[q_idx] = False
            q_idx += 1
            if q_idx < num_questions:
                await ask_question(q_idx)
            continue

        # Accept answer
        followup_used[q_idx] = False

        # After Q1, expand child questions
        if q_idx == 0:
            n_children = extract_nonneg_int(user_input, max_n=20)

            # Build runtime questions based on n_children
            new_questions = [q1]

            if n_children is None:
                # Should be caught by validator, but keep safe fallback
                n_children = 0

            # Repeat child questions for each child
            for i in range(1, n_children + 1):
                new_questions.append(label_child_question(child_age_template, i))
                new_questions.append(label_child_question(child_mal_template, i))

            # Then household vulnerability + caregiver
            new_questions.append(household_vuln_q)
            new_questions.append(caregiver_q)

            questions_runtime = new_questions
            num_questions = len(questions_runtime)
            followup_used = [False] * num_questions

        # Move to next question
        q_idx += 1
        if q_idx < num_questions:
            await ask_question(q_idx)

    # Finish
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