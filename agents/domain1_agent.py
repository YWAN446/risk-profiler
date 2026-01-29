"""
Pydantic AI Agent for Domain 1: Demographics & Vulnerability Factors Survey
Final stable version:
- Code-controlled question order (prevents skipping/reordering; fixes Case B)
- At most ONE follow-up per question
- If still invalid -> record NA (System note)
- Auto-skip child2 questions if num_children_under_5 < 2
"""

import os
import re
import sys
from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.domain1 import Domain1Data


class Domain1SurveyDeps(BaseModel):
    """Dependencies for the Domain 1 survey agent"""
    conversation_history: list[str] = Field(default_factory=list)


# ---------------------------
# Fixed questions (code-controlled order)
# ---------------------------

QUESTIONS = [
    "How many children under five years old live in your household?",
    "Please tell me the age in months of the first child under five.",
    "Has the first child shown signs of malnutrition, like weight loss or not growing well?",
    "Please tell me the age in months of the second child under five. If there is no second child, say 'No second child'.",
    "Has the second child shown signs of malnutrition, like weight loss or not growing well? If there is no second child, say 'No second child'.",
    "Are there any elderly or immunocompromised members in your household, and who mainly takes care of the small children during the day?",
]


def _extract_int_0_2(text: str) -> Optional[int]:
    """Parse number of children (0/1/2) from respondent answer, if confident."""
    if text is None:
        return None
    s = str(text).strip().lower()

    word_map = {"zero": 0, "none": 0, "one": 1, "two": 2}
    for w, v in word_map.items():
        if re.search(rf"\b{w}\b", s):
            return v

    m = re.search(r"\b([0-9]+)\b", s)
    if m:
        try:
            v = int(m.group(1))
            if v in (0, 1, 2):
                return v
        except Exception:
            return None

    # handle common "no kids"/"no children" -> 0
    if re.search(r"\bno\b", s) and re.search(r"\bchild|children|kid|kids\b", s):
        return 0

    return None


# ---------------------------
# Agents
# ---------------------------

def get_extraction_agent() -> Agent:
    """Convert transcript to flat JSON dict"""
    return Agent(
        "openai:gpt-4o",
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
- Use "Both parents" ONLY if respondent clearly indicates shared caregiving.
- If respondent says mother mainly takes care -> "Single mother".
- father mainly -> "Single father".
- grandparent -> "Grandparent".
- other relative -> "Other relative".
- Q6 mentions elderly and/or immunocompromised -> set those booleans accordingly.
- If respondent says 'No second child', OMIT child2_* keys.
- If a key is unknown (except caregiver), you may omit it.

CRITICAL:
You MUST return the result by CALLING the built-in tool named `response`
with a single argument `response` set to your JSON object.
Do NOT print text. Do NOT wrap in markdown. Do NOT include any other fields.
""",
    )


# ---------------------------
# Validation Agent
# ---------------------------

class ValidationDecision(BaseModel):
    status: Literal["OK", "NEED_FOLLOWUP", "GIVE_UP"]
    followup: Optional[str] = None
    note: Optional[str] = None


def get_validation_agent() -> Agent:
    """Decide whether the latest answer is usable; generate at most one follow-up."""
    return Agent(
        "openai:gpt-4o",
        output_type=ValidationDecision,
        model_settings={"temperature": 0},
        system_prompt="""You are a strict validator for a fixed 6-question household survey.

You will receive:
- question_asked: the exact survey question text (one of Q1–Q6)
- respondent_answer: the respondent's answer
- followup_used: true/false (whether a clarification follow-up was already asked for this SAME question)

Return a ValidationDecision:
- status = OK: answer is usable as-is
- status = NEED_FOLLOWUP: answer is not usable AND followup_used is false; provide ONE follow-up sentence
- status = GIVE_UP: answer is not usable AND followup_used is true

General rules:
- Follow-up must be ONE sentence only.
- Follow-up must ask for the SAME information, not a new question.

Definition of clear Yes/No:
YES: yes, y, yeah, yup, true, 1, 是, 有
NO:  no, n, nope, false, 0, 否, 没有, 无

Q-type rules:

Q1 (count of children under 5):
- OK only if the answer clearly gives a number 0, 1, or 2.
- If unclear and followup_used=false: ask "Please reply with a number: 0, 1, or 2."
- Otherwise GIVE_UP.

Q2/Q4 (age in months):
- OK only if the answer is a single integer 0–60.
- If unclear and followup_used=false: ask "Please provide the age in months as a number from 0 to 60."
- Otherwise GIVE_UP.

Q3/Q5 (malnutrition signs):
- OK if the answer is a clear Yes/No (as defined above).
- If not clear and followup_used=false: ask "Please answer Yes or No."
- Otherwise GIVE_UP.
IMPORTANT: Do NOT ask about "No second child" here if the answer is already a clear Yes/No.

Q6 (elderly/immunocompromised/caregiver):
- OK only if the answer clearly provides:
  (a) elderly yes/no AND (b) immunocompromised yes/no AND (c) who mainly cares for the children.
- If missing any part and followup_used=false: ask
  "Please state: elderly (Yes/No), immunocompromised (Yes/No), and who mainly cares for the children."
- Otherwise GIVE_UP.

Return only the ValidationDecision object.
""",
    )


# ---------------------------
# Runner (interactive)
# ---------------------------

async def run_domain1_survey() -> Optional[Domain1Data]:
    """
    Interactive runner:
    - Code-controlled order Q1..Q6
    - ONE follow-up per question
    - Skip child2 Q4/Q5 when Q1 indicates <2 children
    - If invalid after follow-up -> record NA
    """
    validation_agent = get_validation_agent()
    extraction_agent = get_extraction_agent()
    deps = Domain1SurveyDeps()

    print("=" * 60)
    print("DOMAIN 1: Demographics & Vulnerability Factors Survey")
    print("=" * 60)
    print()

    # Ask Q1 with greeting
    greet_q1 = f'Hello, thank you for participating in our survey today. "{QUESTIONS[0]}"'
    deps.conversation_history.append(f"Agent: {greet_q1}")
    print(f"Agent: {greet_q1}\n")

    q_idx = 0
    followup_used = [False] * 6
    n_children: Optional[int] = None

    def should_skip(idx: int) -> bool:
        if idx == 0:
            return False
        if n_children is None:
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
        q_text = f"\"{QUESTIONS[idx]}\""
        deps.conversation_history.append(f"Agent: {q_text}")
        print(f"Agent: {q_text}\n")

    while q_idx < 6:
        if should_skip(q_idx):
            record_na(q_idx, f"Not applicable given num_children_under_5={n_children}")
            followup_used[q_idx] = False
            q_idx += 1
            if q_idx < 6 and not should_skip(q_idx):
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

        current_q_text = f"\"{QUESTIONS[q_idx]}\""
        vd = await validation_agent.run(
            f"""question_asked: {current_q_text}
respondent_answer: {user_input}
followup_used: {str(followup_used[q_idx]).lower()}"""
        )
        decision: ValidationDecision = vd.output

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
            while q_idx < 6 and should_skip(q_idx):
                record_na(q_idx, f"Not applicable given num_children_under_5={n_children}")
                q_idx += 1
            if q_idx < 6:
                await ask_question(q_idx)
            continue

        # OK
        followup_used[q_idx] = False

        if q_idx == 0:
            n_children = _extract_int_0_2(user_input)

        q_idx += 1
        while q_idx < 6 and should_skip(q_idx):
            record_na(q_idx, f"Not applicable given num_children_under_5={n_children}")
            q_idx += 1
        if q_idx < 6:
            await ask_question(q_idx)

    deps.conversation_history.append("Agent: SURVEY_COMPLETE")
    print("Agent: SURVEY_COMPLETE\n")

    print("\n" + "=" * 60)
    print("Survey Complete! Extracting structured data...")
    print("=" * 60)

    conversation_text = "\n".join(deps.conversation_history)
    extraction_result = await extraction_agent.run(
        f"Extract the household data from this conversation:\n\n{conversation_text}"
    )
    answers = extraction_result.output or {}
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