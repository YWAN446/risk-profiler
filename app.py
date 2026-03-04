"""
Risk Profiler Survey Bot - Gradio Web Interface
Multi-domain: Domain 1 + Domain 2 + Domain 3
"""
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import gradio as gr

from agents.domain1_agent import (
    get_conversation_agent as get_domain1_conversation_agent,
    get_extraction_agent as get_domain1_extraction_agent,
    Domain1SurveyDeps,
)
from models.domain1 import Domain1Data

from agents.domain2_agent import (
    get_domain2_conversation_agent,   # optional (kept for compatibility)
    get_domain2_validation_agent,     # ✅ used
    get_domain2_extraction_agent,     # ✅ used
)
from models.domain2 import Domain2SurveyDeps, Domain2Data

# ✅ Domain 3
from agents.domain3_agent import (
    get_domain3_conversation_agent,   # optional (kept for compatibility)
    get_domain3_validation_agent,     # ✅ used
    get_domain3_extraction_agent,     # ✅ used
)
from models.domain3 import Domain3SurveyDeps, Domain3Data

from util import coerce_model_output_to_dict

load_dotenv()

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return default


# -----------------------------
# Domain 2 scripted questions
# -----------------------------
DOMAIN2_QUESTIONS = {
    "Q1": "Could you please tell me your main source of drinking water?",
    "Q2": "Do you treat your drinking water in any way to make it safer?",
    "Q2a": "What method do you use to treat your drinking water?",
    "Q3": "What type of toilet facility do you use?",
    "Q4": "Do you have a designated place for handwashing?",
    "Q5": "How often do you wash your hands after using the toilet?",
}

# -----------------------------
# Domain 3 scripted questions
# -----------------------------
DOMAIN3_QUESTIONS = {
    "Q1": "In the past 14 days, has your community experienced any of the following: a heatwave/very hot weather, heavy rainfall, or flooding? You can say more than one, or say 'none'.",
    "Q2": "About when did the MOST RECENT event happen? Please give a date (YYYY-MM-DD) or how many days ago (0–14). If none, say 'none'.",
    "Q2a": "If you're not sure of the exact date, about how many days ago was it (0–14)?",
    "Q3": "In the past 14 days, have you heard of many people in your community having diarrhoea? Please answer Yes or No.",
    "Q4": "In the past 14 days, has your household had any water supply interruptions? Please answer Yes or No.",
    "Q4a": "Did the interruption cause you to store water longer than usual? Please answer Yes or No.",
}


_YES = {"yes", "y", "yeah", "yup", "true", "1"}
_NO = {"no", "n", "nope", "false", "0"}


def _norm(s) -> str:
    return str(s or "").strip().lower()


def _infer_yesno(user_answer: str):
    """
    Return True/False/None based on yes/no tokens.
    """
    s = _norm(user_answer)
    if not s:
        return None
    tokens = [t for t in s.replace(",", " ").replace(".", " ").split() if t]
    if not tokens:
        return None
    if tokens[0] in _YES:
        return True
    if tokens[0] in _NO:
        return False
    if any(t in _YES for t in tokens):
        return True
    if any(t in _NO for t in tokens):
        return False
    return None


def _infer_treats_water(user_answer: str):
    """
    Deterministic inference for Domain2 Q2:
    - Mentioning a method counts as YES
    - Else parse yes/no tokens
    - Else None
    """
    s = _norm(user_answer)
    if any(
        k in s
        for k in [
            "boil",
            "boiled",
            "boiling",
            "filter",
            "filtered",
            "filtration",
            "chlorine",
            "bleach",
            "tablet",
            "tabs",
        ]
    ):
        return True

    tokens = [t for t in s.replace(",", " ").replace(".", " ").split() if t]
    if not tokens:
        return None

    if tokens[0] in _YES:
        return True
    if tokens[0] in _NO:
        return False

    if any(t in _YES for t in tokens):
        return True
    if any(t in _NO for t in tokens):
        return False

    return None


def _infer_treatment_method(user_answer: str):
    """
    Extract method if user includes it in Q2 answer (e.g., 'yes, boil').
    Return one of: 'boil'/'filter'/'chlorine' or None.
    """
    s = _norm(user_answer)
    if any(k in s for k in ["boil", "boiled", "boiling"]):
        return "boil"
    if any(k in s for k in ["filter", "filtered", "filtration"]):
        return "filter"
    if any(k in s for k in ["chlorine", "bleach", "tablet", "tabs"]):
        return "chlorine"
    return None


# -----------------------------
# Domain 2 Q4 hybrid gate
# -----------------------------
Q4_FOLLOWUP = "Is it usually soap and water, water only, or no designated place?"


def _q4_needs_followup(user_answer: str) -> bool:
    """
    Domain2 Q4 needs a follow-up if the answer does NOT contain enough info to map to:
    - soap+water
    - water only
    - none
    """
    s = _norm(user_answer)
    if not s:
        return True

    # Clear "none / no place"
    neg_markers = ["no", "none", "don't have", "do not have", "without", "no designated"]
    place_markers = ["place", "station", "sink", "tap", "handwash", "hand wash", "washing hands"]
    if any(n in s for n in neg_markers) and any(p in s for p in place_markers):
        return False  # can map to NONE

    # Clear soap+water
    if "soap" in s and any(w in s for w in ["water", "sink", "tap", "tippy", "station", "place"]):
        return False

    # Clear water-only (explicit)
    if any(k in s for k in ["water only", "no soap", "without soap"]):
        return False

    # If they mention water but not soap -> accept as water-only (no follow-up)
    if "water" in s and "soap" not in s:
        return False

    # "sink/tap" without soap mention is ambiguous
    if any(k in s for k in ["sink", "tap"]) and "soap" not in s and "water" not in s:
        return True

    # Very short affirmations / vague answers -> follow up
    if s in {"yes", "y", "yeah", "yup", "sure", "we do", "we have", "sometimes", "maybe"}:
        return True

    # Otherwise: still likely ambiguous for mapping
    return True


def _infer_event_timing(user_answer: str):
    """
    Domain3 Q2 parsing helper:
    - If ISO date (YYYY-MM-DD) -> return {"most_recent_event_date": "...", "event_recency_days": None}
    - If days-ago integer 0–14 -> return {"most_recent_event_date": None, "event_recency_days": int}
    - Else -> return None
    """
    s = _norm(user_answer)
    if not s:
        return None

    # explicit none
    if s in {"none", "no", "n/a", "na"}:
        return {"most_recent_event_date": None, "event_recency_days": None}

    # ISO date
    try:
        dt = s.split()[0]
        datetime.strptime(dt, "%Y-%m-%d")
        return {"most_recent_event_date": dt, "event_recency_days": None}
    except Exception:
        pass

    # days-ago
    import re
    m = re.search(r"\b(\d{1,2})\b", s)
    if m:
        d = int(m.group(1))
        if 0 <= d <= 14:
            return {"most_recent_event_date": None, "event_recency_days": d}

    return None


class SurveySession:
    def __init__(self, domain_id: str):
        self.domain_id = domain_id
        self.is_complete = False
        self.result_data = None

        if domain_id == "domain1":
            # ✅ Domain1 untouched logic
            self.conversation_agent = get_domain1_conversation_agent()
            self.extraction_agent = get_domain1_extraction_agent()
            self.deps = Domain1SurveyDeps()
            self.data_cls = Domain1Data
            self.domain_name = "Domain 1 - Demographics & Vulnerability Factors"
            self.next_step_template = _read_text(PROMPTS_DIR / "domain1_next_step.md")
            self.completion_template = _read_text(PROMPTS_DIR / "domain1_completion.md")
            self.output_prefix = "domain1_survey"

        elif domain_id == "domain2":
            # ✅ Domain2 validator + deterministic flow
            self.conversation_agent = get_domain2_conversation_agent()  # optional
            self.validation_agent = get_domain2_validation_agent()
            self.extraction_agent = get_domain2_extraction_agent()

            self.deps = Domain2SurveyDeps()
            self.data_cls = Domain2Data
            self.domain_name = "Domain 2 - WASH (Water, Sanitation, Handwashing)"
            self.completion_template = _read_text(PROMPTS_DIR / "domain2_completion.md")
            self.output_prefix = "domain2_survey"

            # state machine
            self.d2_qid = "Q1"
            self.d2_followup_asked = False  # one follow-up max per question

            # validated answers (override extraction drift)
            self.d2_validated = {
                "water_source": None,
                "treats_water": None,                 # bool | None
                "water_treatment_method": None,        # "boil"/"filter"/"chlorine"/etc
                "toilet_type": None,
                "handwashing_station": None,
                "washes_after_toilet": None,
            }

        elif domain_id == "domain3":
            # ✅ Domain3 validator + deterministic flow (mirrors Domain2 style)
            self.conversation_agent = get_domain3_conversation_agent()  # optional
            self.validation_agent = get_domain3_validation_agent()
            self.extraction_agent = get_domain3_extraction_agent()

            self.deps = Domain3SurveyDeps()
            self.data_cls = Domain3Data
            self.domain_name = "Domain 3 - Temporal / Seasonal Factors"
            self.completion_template = _read_text(PROMPTS_DIR / "domain3_completion.md")
            self.output_prefix = "domain3_survey"

            # state machine
            self.d3_qid = "Q1"
            self.d3_followup_asked = False  # one follow-up max per question

            # validated answers (override extraction drift)
            self.d3_validated = {
                "recent_heatwave": None,
                "recent_heavy_rain": None,
                "recent_flood": None,
                "most_recent_event_date": None,     # "YYYY-MM-DD"
                "event_recency_days": None,         # int 0-14
                "community_diarrhoea_outbreak": None,  # bool
                "water_interruption": None,            # bool
                "extended_water_storage": None,        # bool
            }

        else:
            raise ValueError(f"Unknown domain_id: {domain_id}")

    async def get_initial_greeting(self) -> str:
        if self.domain_id == "domain2":
            msg = "Hello! Thank you for participating in our survey. " + DOMAIN2_QUESTIONS["Q1"]
            self.deps.conversation_history.append(f"Agent: {msg}")
            return msg

        if self.domain_id == "domain3":
            msg = "Hello! Thank you for participating in our survey. " + DOMAIN3_QUESTIONS["Q1"]
            self.deps.conversation_history.append(f"Agent: {msg}")
            return msg

        # Domain1
        result = await self.conversation_agent.run(
            "Start the survey by greeting the respondent and then ask Q1.",
            deps=self.deps,
        )
        agent_response = result.response.text
        self.deps.conversation_history.append(f"Agent: {agent_response}")
        return agent_response

    async def process_response(self, user_input: str) -> str:
        if self.is_complete:
            return "The survey is already complete. Please click 'New Survey' to start again."

        self.deps.conversation_history.append(f"Respondent: {user_input}")

        # -----------------------------
        # Domain2: deterministic + validator
        # -----------------------------
        if self.domain_id == "domain2":
            next_msg = await self._domain2_next(user_input)
            self.deps.conversation_history.append(f"Agent: {next_msg}")

            if next_msg == "SURVEY_COMPLETE":
                self.is_complete = True
                await self._extract_data()
                return self._format_completion_message()

            return next_msg

        # -----------------------------
        # Domain3: deterministic + validator
        # -----------------------------
        if self.domain_id == "domain3":
            next_msg = await self._domain3_next(user_input)
            self.deps.conversation_history.append(f"Agent: {next_msg}")

            if next_msg == "SURVEY_COMPLETE":
                self.is_complete = True
                await self._extract_data()
                return self._format_completion_message()

            return next_msg

        # -----------------------------
        # Domain1: keep stable prompt flow
        # -----------------------------
        transcript = "\n".join(self.deps.conversation_history)
        next_step_prompt = self.next_step_template.format(
            transcript=transcript,
            user_input=user_input,
        )

        result = await self.conversation_agent.run(next_step_prompt, deps=self.deps)
        agent_response = result.response.text
        self.deps.conversation_history.append(f"Agent: {agent_response}")

        if "SURVEY_COMPLETE" in agent_response:
            self.is_complete = True
            await self._extract_data()
            return self._format_completion_message()

        return agent_response

    # -----------------------------
    # Domain2 core flow
    # -----------------------------
    async def _domain2_next(self, user_input: str) -> str:
        qid = self.d2_qid

        # ✅ Q2 branching is fully deterministic (do NOT rely on validator status for flow)
        if qid == "Q2":
            tw = _infer_treats_water(user_input)  # True/False/None

            if tw is None:
                # unclear -> one follow-up max
                if not self.d2_followup_asked:
                    self.d2_followup_asked = True
                    return "Please answer Yes or No. Do you treat your drinking water?"
                # still unclear -> record NA and move on
                self.d2_validated["treats_water"] = None
                self.d2_followup_asked = False
                self.d2_qid = "Q3"
                return DOMAIN2_QUESTIONS["Q3"]

            # record treats_water
            self.d2_validated["treats_water"] = tw
            self.d2_followup_asked = False

            if tw is False:
                # skip Q2a
                self.d2_qid = "Q3"
                return DOMAIN2_QUESTIONS["Q3"]

            # tw is True -> go Q2a unless method already included
            method = _infer_treatment_method(user_input)
            if method is not None:
                self.d2_validated["water_treatment_method"] = method
                self.d2_qid = "Q3"
                return DOMAIN2_QUESTIONS["Q3"]

            self.d2_qid = "Q2a"
            return DOMAIN2_QUESTIONS["Q2a"]

        # ✅ Q4 hybrid gate: code-driven follow-up trigger (mapping still handled by validator/model)
        if qid == "Q4":
            if _q4_needs_followup(user_input):
                if not self.d2_followup_asked:
                    self.d2_followup_asked = True
                    return Q4_FOLLOWUP

                # still unclear after 1 follow-up -> record NA and move on
                self._domain2_record("Q4", None)
                self.d2_followup_asked = False
                self._domain2_advance()
                return self._domain2_next_question_or_complete()

            # enough info -> fall through to validator path

        # For all other Domain2 questions, use validator to decide OK/follow-up/give-up
        qtext = DOMAIN2_QUESTIONS[qid]
        v = await self.validation_agent.run(
            {
                "question_id": qid,
                "question_text": qtext,
                "user_answer": user_input,
            }
        )

        decision = v.output if hasattr(v, "output") and v.output is not None else v.response

        status_raw = decision.get("status")
        status = (status_raw or "").strip().upper()  # ✅ normalize to avoid ok/OK issues
        followup = decision.get("followup")

        if status not in {"OK", "NEED_FOLLOWUP", "GIVE_UP"}:
            status = "GIVE_UP"

        if status == "NEED_FOLLOWUP":
            if (not self.d2_followup_asked) and followup:
                self.d2_followup_asked = True
                return followup
            status = "GIVE_UP"

        if status == "GIVE_UP":
            self._domain2_record(qid, None)
            self.d2_followup_asked = False
            self._domain2_advance()
            return self._domain2_next_question_or_complete()

        # OK
        self._domain2_record(qid, user_input)
        self.d2_followup_asked = False

        self._domain2_advance()
        return self._domain2_next_question_or_complete()

    def _domain2_record(self, qid: str, value):
        """
        Store validated values in keys compatible with Domain2Data.from_answers().
        """
        if qid == "Q1":
            self.d2_validated["water_source"] = value
        elif qid == "Q2":
            # handled deterministically above
            pass
        elif qid == "Q2a":
            self.d2_validated["water_treatment_method"] = value
        elif qid == "Q3":
            self.d2_validated["toilet_type"] = value
        elif qid == "Q4":
            self.d2_validated["handwashing_station"] = value
        elif qid == "Q5":
            self.d2_validated["washes_after_toilet"] = value

    def _domain2_advance(self):
        """
        Strict order: Q1 -> Q2 -> (Q2a if treats_water True and method missing) -> Q3 -> Q4 -> Q5 -> DONE
        """
        order = ["Q1", "Q2", "Q2a", "Q3", "Q4", "Q5"]
        try:
            idx = order.index(self.d2_qid)
        except ValueError:
            self.d2_qid = "Q5"
            return

        if idx >= len(order) - 1:
            self.d2_qid = "DONE"
            return

        nxt = order[idx + 1]

        # Only ask Q2a if treats_water is True and method not already captured
        if nxt == "Q2a":
            if self.d2_validated.get("treats_water") is not True:
                nxt = "Q3"
            elif self.d2_validated.get("water_treatment_method") is not None:
                nxt = "Q3"

        self.d2_qid = nxt

    def _domain2_next_question_or_complete(self) -> str:
        if self.d2_qid == "DONE":
            return "SURVEY_COMPLETE"
        return DOMAIN2_QUESTIONS[self.d2_qid]

    # -----------------------------
    # Domain3 core flow (mirrors Domain2)
    # -----------------------------
    async def _domain3_next(self, user_input: str) -> str:
        qid = self.d3_qid

        # Q2: deterministic gate to Q2a if timing unclear/vague
        if qid == "Q2":
            timing = _infer_event_timing(user_input)
            if timing is None:
                # If unclear -> send to Q2a once, then GIVE_UP (NA) and move on
                if not self.d3_followup_asked:
                    self.d3_followup_asked = True
                    self.d3_qid = "Q2a"
                    return DOMAIN3_QUESTIONS["Q2a"]

                # still unclear after Q2a attempt
                self.d3_validated["most_recent_event_date"] = None
                self.d3_validated["event_recency_days"] = None
                self.d3_followup_asked = False
                self.d3_qid = "Q3"
                return DOMAIN3_QUESTIONS["Q3"]

            # record timing
            self.d3_validated["most_recent_event_date"] = timing.get("most_recent_event_date")
            self.d3_validated["event_recency_days"] = timing.get("event_recency_days")
            self.d3_followup_asked = False

            self.d3_qid = "Q3"
            return DOMAIN3_QUESTIONS["Q3"]

        # Q2a: must be days 0–14
        if qid == "Q2a":
            timing = _infer_event_timing(user_input)
            # only accept days-ago here (ignore date)
            days = None
            if timing is not None:
                days = timing.get("event_recency_days")

            if days is None:
                # one retry max (validator-style)
                if not self.d3_followup_asked:
                    self.d3_followup_asked = True
                    return "About how many days ago (0–14)?"

                # give up -> NA, move on
                self.d3_validated["event_recency_days"] = None
                self.d3_followup_asked = False
                self.d3_qid = "Q3"
                return DOMAIN3_QUESTIONS["Q3"]

            self.d3_validated["event_recency_days"] = days
            self.d3_validated["most_recent_event_date"] = None
            self.d3_followup_asked = False
            self.d3_qid = "Q3"
            return DOMAIN3_QUESTIONS["Q3"]

        # Q4: if YES -> go Q4a; if NO -> skip Q4a
        if qid == "Q4":
            yn = _infer_yesno(user_input)
            if yn is None:
                if not self.d3_followup_asked:
                    self.d3_followup_asked = True
                    return "Please answer Yes or No."
                # give up
                self.d3_validated["water_interruption"] = None
                self.d3_followup_asked = False
                self.d3_qid = "DONE"
                return "SURVEY_COMPLETE"

            self.d3_validated["water_interruption"] = yn
            self.d3_followup_asked = False

            if yn is True:
                self.d3_qid = "Q4a"
                return DOMAIN3_QUESTIONS["Q4a"]

            # yn is False -> skip Q4a
            self.d3_qid = "DONE"
            return "SURVEY_COMPLETE"

        # Q4a: Yes/No then complete
        if qid == "Q4a":
            yn = _infer_yesno(user_input)
            if yn is None:
                if not self.d3_followup_asked:
                    self.d3_followup_asked = True
                    return "Please answer Yes or No."
                # give up
                self.d3_validated["extended_water_storage"] = None
                self.d3_followup_asked = False
                self.d3_qid = "DONE"
                return "SURVEY_COMPLETE"

            self.d3_validated["extended_water_storage"] = yn
            self.d3_followup_asked = False
            self.d3_qid = "DONE"
            return "SURVEY_COMPLETE"

        # For remaining questions (Q1, Q3), use validator
        qtext = DOMAIN3_QUESTIONS[qid]
        v = await self.validation_agent.run(
            {
                "question_id": qid,
                "question_text": qtext,
                "user_answer": user_input,
            }
        )

        decision = v.output if hasattr(v, "output") and v.output is not None else v.response

        status_raw = decision.get("status")
        status = (status_raw or "").strip().upper()
        followup = decision.get("followup")

        if status not in {"OK", "NEED_FOLLOWUP", "GIVE_UP"}:
            status = "GIVE_UP"

        if status == "NEED_FOLLOWUP":
            if (not self.d3_followup_asked) and followup:
                self.d3_followup_asked = True
                return followup
            status = "GIVE_UP"

        if status == "GIVE_UP":
            self._domain3_record(qid, None)
            self.d3_followup_asked = False
            self._domain3_advance()
            return self._domain3_next_question_or_complete()

        # OK
        self._domain3_record(qid, user_input)
        self.d3_followup_asked = False
        self._domain3_advance()
        return self._domain3_next_question_or_complete()

    def _domain3_record(self, qid: str, value):
        """
        Store validated values in keys compatible with Domain3Data.from_answers().
        Note: We keep Q1 as free text for extraction to interpret multi-select events.
              Q3 is parsed to bool when possible to reduce drift.
        """
        if qid == "Q1":
            # Let extraction detect multi-select events; keep raw text as fallback.
            # Optionally you could implement deterministic keyword parsing here later.
            pass
        elif qid == "Q3":
            self.d3_validated["community_diarrhoea_outbreak"] = _infer_yesno(value) if value is not None else None

    def _domain3_advance(self):
        """
        Strict order: Q1 -> Q2 -> (Q2a only if needed) -> Q3 -> Q4 -> (Q4a only if Q4=Yes) -> DONE

        Note:
        - Whether Q2a is asked is handled in _domain3_next (deterministic gate).
        - Whether Q4a is asked is handled in _domain3_next (deterministic gate).
        """
        order = ["Q1", "Q2", "Q2a", "Q3", "Q4", "Q4a"]
        try:
            idx = order.index(self.d3_qid)
        except ValueError:
            self.d3_qid = "Q4"
            return

        if idx >= len(order) - 1:
            self.d3_qid = "DONE"
            return

        self.d3_qid = order[idx + 1]

    def _domain3_next_question_or_complete(self) -> str:
        if self.d3_qid == "DONE":
            return "SURVEY_COMPLETE"
        return DOMAIN3_QUESTIONS[self.d3_qid]

    async def _extract_data(self):
        conversation_text = "\n".join(self.deps.conversation_history)

        result = await self.extraction_agent.run(
            f"Extract the {self.domain_name} data from this conversation:\n\n{conversation_text}"
        )

        raw = result.output if hasattr(result, "output") and result.output is not None else result.response
        answers = coerce_model_output_to_dict(raw) or {}

        # ✅ Domain2: override extraction drift using validated answers
        if self.domain_id == "domain2":
            for k, v in self.d2_validated.items():
                if v is not None:
                    answers[k] = v
            if self.d2_validated.get("treats_water") is not None:
                answers["treats_water"] = self.d2_validated["treats_water"]

        # ✅ Domain3: override extraction drift using validated answers
        if self.domain_id == "domain3":
            for k, v in self.d3_validated.items():
                if v is not None:
                    answers[k] = v
            # keep explicit bools even if None in some fields
            if self.d3_validated.get("water_interruption") is not None:
                answers["water_interruption"] = self.d3_validated["water_interruption"]
            if self.d3_validated.get("extended_water_storage") is not None:
                answers["extended_water_storage"] = self.d3_validated["extended_water_storage"]
            if self.d3_validated.get("community_diarrhoea_outbreak") is not None:
                answers["community_diarrhoea_outbreak"] = self.d3_validated["community_diarrhoea_outbreak"]

        if self.domain_id == "domain1":
            self.result_data = self.data_cls.from_answers(answers, strict_len=False)
        else:
            self.result_data = self.data_cls.from_answers(answers)

        self._save_results()

    def _save_results(self):
        if not self.result_data:
            return
    
        output_dir = Path("survey_results")
        output_dir.mkdir(exist_ok=True)
    
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"{self.output_prefix}_{timestamp}.json"
    
        summary = self.result_data.get_risk_summary()
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "domain": self.domain_name,
            "data": self.result_data.model_dump(mode="json"),  # ✅ FIX
            "summary": summary,
        }
    
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

    def _format_completion_message(self) -> str:
        if not self.result_data:
            return "Survey complete, but there was an error extracting data."

        summary = self.result_data.get_risk_summary()

        if self.domain_id == "domain2":
            return self.completion_template.format(
                water_source=summary.get("water_source", "Unknown"),
                treats_water=summary.get("treats_water", None),
                water_treatment_method=summary.get("water_treatment_method", "Unknown"),
                toilet_type=summary.get("toilet_type", "Unknown"),
                handwashing_station=summary.get("handwashing_station", "Unknown"),
                washes_after_toilet=summary.get("washes_after_toilet", "Unknown"),
                score=float(summary.get("wash_risk_score", 0.0)),
                weight=float(summary.get("domain_weight", 0.0)),
                weighted=float(summary.get("weighted_score", 0.0)),
            )

        if self.domain_id == "domain3":
            def _v(x):
                if x is True:
                    return "Yes"
                if x is False:
                    return "No"
                if x is None:
                    return "NA"
                return str(x)
        
            mapping = {
                "recent_heatwave": _v(summary.get("recent_heatwave")),
                "recent_heavy_rain": _v(summary.get("recent_heavy_rain")),
                "recent_flood": _v(summary.get("recent_flood")),
                "most_recent_event_date": _v(summary.get("most_recent_event_date")),
                "event_recency_days": _v(summary.get("event_recency_days")),
                "community_diarrhoea_outbreak": _v(summary.get("community_diarrhoea_outbreak")),
                "water_interruption": _v(summary.get("water_interruption")),
                "extended_water_storage": _v(summary.get("extended_water_storage")),
                "risk_multiplier": _v(summary.get("risk_multiplier")),
            }
        
            # ✅ Support both {key} and {{key}} templates
            text = self.completion_template
            for k, val in mapping.items():
                text = text.replace(f"{{{{{k}}}}}", str(val))  # replaces {{key}}
                text = text.replace(f"{{{k}}}", str(val))      # replaces {key}
        
            return text

        # ✅ Domain1 remains template-driven (stable)
        return self.completion_template.format(
            total_children=summary.get("total_children", "Unknown"),
            high_risk_age_children=summary.get("high_risk_age_children", "Unknown"),
            malnourished_children=summary.get("malnourished_children", "Unknown"),
            vulnerable_members_present=(
                "Yes" if summary.get("vulnerable_members_present") is True
                else "No" if summary.get("vulnerable_members_present") is False
                else "Unknown"
            ),
            primary_caregiver_type=summary.get("primary_caregiver_type", "Unknown"),
            overall_vulnerability_score=f"{float(summary.get('overall_vulnerability_score', 0.0)):.2f}",
            domain_weight=f"{float(summary.get('domain_weight', 0.0)):.2f}",
            weighted_score=f"{float(summary.get('weighted_score', 0.0)):.2f}",
        )


# ---------------------------------------------------------
# sessions keyed by (session_id, domain_id) to avoid cross-domain overwrite
# ---------------------------------------------------------
sessions = {}


def _key(session_id: str, domain_id: str):
    return (session_id, domain_id)


def get_or_create_session(session_id: str, domain_id: str) -> SurveySession:
    k = _key(session_id, domain_id)
    if k not in sessions:
        sessions[k] = SurveySession(domain_id=domain_id)
    return sessions[k]


async def start_survey(session_id: str, domain_id: str):
    k = _key(session_id, domain_id)
    sessions[k] = SurveySession(domain_id=domain_id)
    greeting = await sessions[k].get_initial_greeting()
    return [{"role": "assistant", "content": greeting}]


async def chat(message: str, history: list, session_id: str, domain_id: str):
    if not message.strip():
        return history

    session = get_or_create_session(session_id, domain_id)

    if not history:
        greeting = await session.get_initial_greeting()
        history = [{"role": "assistant", "content": greeting}]

    response = await session.process_response(message)

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": response})

    return history


def create_app():
    ui_intro = _read_text(PROMPTS_DIR / "ui_intro.md")
    ui_instructions = _read_text(PROMPTS_DIR / "ui_instructions.md")

    with gr.Blocks(title="Risk Profiler Survey Bot") as app:
        gr.Markdown(ui_intro)

        session_id = gr.State(value=lambda: datetime.now().strftime("%Y%m%d%H%M%S%f"))

        domain_select = gr.Dropdown(
            choices=[
                ("Domain 1 - Demographics & Vulnerability Factors", "domain1"),
                ("Domain 2 - WASH (Water, Sanitation, Handwashing)", "domain2"),
                ("Domain 3 - Temporal / Seasonal Factors", "domain3"),
            ],
            value="domain1",
            label="Select Domain",
        )

        chatbot = gr.Chatbot(label="Survey Conversation", height=450)

        with gr.Row():
            msg = gr.Textbox(
                placeholder="Type your answer here and press Enter...",
                scale=4,
                show_label=False,
            )
            submit_btn = gr.Button("Send", variant="primary", scale=1)

        with gr.Row():
            new_survey_btn = gr.Button("New Survey", variant="secondary")
            clear_btn = gr.Button("Clear Chat", variant="secondary")

        gr.Markdown(ui_instructions)

        async def handle_submit(message, history, session_id, domain_id):
            if not history:
                k = (session_id, domain_id)
                sessions[k] = SurveySession(domain_id=domain_id)
                greeting = await sessions[k].get_initial_greeting()
                history = [{"role": "assistant", "content": greeting}]

            result = await chat(message, history, session_id, domain_id)
            return "", result

        async def handle_new_survey(domain_id):
            new_session_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
            history = await start_survey(new_session_id, domain_id)
            return history, new_session_id

        msg.submit(handle_submit, inputs=[msg, chatbot, session_id, domain_select], outputs=[msg, chatbot])
        submit_btn.click(handle_submit, inputs=[msg, chatbot, session_id, domain_select], outputs=[msg, chatbot])

        new_survey_btn.click(handle_new_survey, inputs=[domain_select], outputs=[chatbot, session_id])
        clear_btn.click(lambda: [], outputs=[chatbot])

    return app


if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        show_error=True,
        theme=gr.themes.Soft(),
    )