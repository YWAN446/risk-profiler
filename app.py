"""
Risk Profiler Survey Bot - Gradio Web Interface
Multi-domain: Domain 1 + Domain 2
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
    get_domain2_conversation_agent,
    get_domain2_extraction_agent,
)
from models.domain2 import Domain2SurveyDeps, Domain2Data

from util import coerce_model_output_to_dict

load_dotenv()

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return default


class SurveySession:
    def __init__(self, domain_id: str):
        self.domain_id = domain_id
        self.is_complete = False
        self.result_data = None

        if domain_id == "domain1":
            self.conversation_agent = get_domain1_conversation_agent()
            self.extraction_agent = get_domain1_extraction_agent()
            self.deps = Domain1SurveyDeps()
            self.data_cls = Domain1Data
            self.domain_name = "Domain 1 - Demographics & Vulnerability Factors"
            self.next_step_template = _read_text(PROMPTS_DIR / "domain1_next_step.md")
            self.output_prefix = "domain1_survey"

        elif domain_id == "domain2":
            self.conversation_agent = get_domain2_conversation_agent()
            self.extraction_agent = get_domain2_extraction_agent()
            self.deps = Domain2SurveyDeps()
            self.data_cls = Domain2Data
            self.domain_name = "Domain 2 - WASH (Water, Sanitation, Handwashing)"
            self.next_step_template = _read_text(PROMPTS_DIR / "domain2_next_step.md")
            self.completion_template = _read_text(PROMPTS_DIR / "domain2_completion.md")
            self.output_prefix = "domain2_survey"

        else:
            raise ValueError(f"Unknown domain_id: {domain_id}")

    async def get_initial_greeting(self) -> str:
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

    async def _extract_data(self):
        conversation_text = "\n".join(self.deps.conversation_history)

        result = await self.extraction_agent.run(
            f"Extract the {self.domain_name} data from this conversation:\n\n{conversation_text}"
        )

        raw = None
        if hasattr(result, "output") and result.output is not None:
            raw = result.output
        else:
            raw = result.response

        answers = coerce_model_output_to_dict(raw) or {}

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
            "data": self.result_data.model_dump(),
            "summary": summary,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

    def _format_completion_message(self) -> str:
        if not self.result_data:
            return "Survey complete, but there was an error extracting data."

        summary = self.result_data.get_risk_summary()

        # Domain2 uses template
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

        # Domain1 uses your original message style (short version)
        return f"""**Survey Complete!**

Overall Vulnerability Score: {summary.get('overall_vulnerability_score', 0.0):.2f}
Weighted Score: {summary.get('weighted_score', 0.0):.2f}

*Results saved. Click 'New Survey' to start again.*
"""


sessions = {}


def get_or_create_session(session_id: str, domain_id: str) -> SurveySession:
    if session_id not in sessions:
        sessions[session_id] = SurveySession(domain_id=domain_id)
    return sessions[session_id]


async def start_survey(session_id: str, domain_id: str):
    sessions[session_id] = SurveySession(domain_id=domain_id)
    greeting = await sessions[session_id].get_initial_greeting()
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
            ],
            value="domain1",
            label="Select Domain",
        )

        chatbot = gr.Chatbot(label="Survey Conversation", height=450)

        with gr.Row():
            msg = gr.Textbox(placeholder="Type your answer here and press Enter...", scale=4, show_label=False)
            submit_btn = gr.Button("Send", variant="primary", scale=1)

        with gr.Row():
            new_survey_btn = gr.Button("New Survey", variant="secondary")
            clear_btn = gr.Button("Clear Chat", variant="secondary")

        gr.Markdown(ui_instructions)

        async def handle_submit(message, history, session_id, domain_id):
            if not history:
                sessions[session_id] = SurveySession(domain_id=domain_id)
                greeting = await sessions[session_id].get_initial_greeting()
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