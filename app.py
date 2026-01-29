"""
Risk Profiler Survey Bot - Gradio Web Interface
"""
import asyncio
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import gradio as gr

from agents.domain1_agent import (
    get_conversation_agent,
    get_extraction_agent,
    Domain1SurveyDeps,
)
from models.domain1 import Domain1Data

# Load environment variables
load_dotenv()


class SurveySession:
    """Manages a single survey session state"""

    def __init__(self):
        self.conversation_agent = get_conversation_agent()
        self.deps = Domain1SurveyDeps()
        self.is_complete = False
        self.result_data = None

    async def get_initial_greeting(self) -> str:
        """Get the agent's initial greeting and first question"""
        result = await self.conversation_agent.run(
            "Start the survey by greeting the respondent and then ask Q1.",
            deps=self.deps,
        )
        agent_response = result.response.text
        self.deps.conversation_history.append(f"Agent: {agent_response}")
        return agent_response

    async def process_response(self, user_input: str) -> str:
        """Process user input and get agent response"""
        if self.is_complete:
            return "The survey is already complete. Please start a new session to take the survey again."

        # Add user input to history
        self.deps.conversation_history.append(f"Respondent: {user_input}")

        # Build prompt for next question
        transcript = "\n".join(self.deps.conversation_history)
        next_step_prompt = f"""You are continuing a fixed 6-question survey.

        Transcript so far:
        {transcript}

        The respondent just answered: "{user_input}"

        Rules:
        - Ask only the NEXT required question from the 6-question script.
        - Do not repeat earlier questions that have already been asked AND answered.
        - If all six questions are answered, reply with SURVEY_COMPLETE (exactly)."""

        result = await self.conversation_agent.run(next_step_prompt, deps=self.deps)
        agent_response = result.response.text
        self.deps.conversation_history.append(f"Agent: {agent_response}")

        # Check if survey is complete
        if "SURVEY_COMPLETE" in agent_response:
            self.is_complete = True
            await self._extract_data()
            return self._format_completion_message()

        return agent_response

    async def _extract_data(self):
        """Extract structured data from conversation"""
        extraction_agent = get_extraction_agent()
        conversation_text = "\n".join(self.deps.conversation_history)
        extraction_result = await extraction_agent.run(
            f"Extract the household data from this conversation:\n\n{conversation_text}"
        )
        answers = extraction_result.response or {}
        self.result_data = Domain1Data.from_answers(answers, strict_len=False)

        # Save results
        self._save_results()

    def _save_results(self):
        """Save survey results to file"""
        if not self.result_data:
            return

        output_dir = Path("survey_results")
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"domain1_survey_{timestamp}.json"

        summary = self.result_data.get_risk_summary()
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "domain": "Domain 1 - Demographics & Vulnerability Factors",
            "data": self.result_data.model_dump(),
            "summary": summary,
        }

        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2)

    def _format_completion_message(self) -> str:
        """Format the completion message with risk summary"""
        if not self.result_data:
            return "Survey complete, but there was an error extracting data."

        summary = self.result_data.get_risk_summary()

        message = """
**Survey Complete!**

---

**Risk Assessment Summary:**

| Metric | Value |
|--------|-------|
| Total Children Under 5 | {total_children} |
| High-Risk Age Children (6-23 months) | {high_risk} |
| Children with Malnutrition Signs | {malnourished} |
| Single-Parent Household | {single_parent} |
| Vulnerable Members Present | {vulnerable} |

---

**Overall Vulnerability Score: {score:.2f}**

Domain Weight: {weight:.0%} | Weighted Score: {weighted:.2f}

---

""".format(
            total_children=summary["total_children"],
            high_risk=summary["high_risk_age_children"],
            malnourished=summary["malnourished_children"],
            single_parent="Yes" if summary["single_parent_household"] else "No",
            vulnerable="Yes" if summary["vulnerable_members_present"] else "No",
            score=summary["overall_vulnerability_score"],
            weight=summary["domain_weight"],
            weighted=summary["weighted_score"],
        )

        # Add individual child scores
        if self.result_data.children:
            message += "**Individual Child Vulnerability Scores:**\n\n"
            for i, child in enumerate(self.result_data.children, 1):
                message += f"- **Child {i}**: {child.age_months} months ({child.age_range.value})"
                if child.has_malnutrition_signs:
                    message += " - Malnutrition signs present"
                message += f" - Score: {child.vulnerability_score:.2f}\n"

        message += "\n\n*Results have been saved. Click 'New Survey' to start again.*"

        return message


# Global session storage (for demo - in production use proper session management)
sessions = {}


def get_or_create_session(session_id: str) -> SurveySession:
    """Get existing session or create new one"""
    if session_id not in sessions:
        sessions[session_id] = SurveySession()
    return sessions[session_id]


async def start_survey(session_id: str):
    """Start a new survey and return initial greeting"""
    # Create fresh session
    sessions[session_id] = SurveySession()
    session = sessions[session_id]
    greeting = await session.get_initial_greeting()
    return [{"role": "assistant", "content": greeting}]


async def chat(message: str, history: list, session_id: str):
    """Process chat message and return response"""
    if not message.strip():
        return history

    session = get_or_create_session(session_id)

    # If no history, start the survey first
    if not history:
        greeting = await session.get_initial_greeting()
        history = [{"role": "assistant", "content": greeting}]

    # Get agent response
    response = await session.process_response(message)

    # Add to history (Gradio 6.x format)
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": response})

    return history


def create_app():
    """Create and configure the Gradio app"""

    with gr.Blocks(title="Risk Profiler Survey Bot") as app:
        gr.Markdown(
            """
        # Risk Profiler Survey Bot
        ### Multi-Domain Risk Assessment System

        This survey collects information to assess risk factors for vulnerable populations.

        **Currently Available:** Domain 1 - Demographics & Vulnerability Factors

        ---
        """
        )

        # Session ID (hidden, for state management)
        session_id = gr.State(value=lambda: datetime.now().strftime("%Y%m%d%H%M%S%f"))

        chatbot = gr.Chatbot(
            label="Survey Conversation",
            height=450,
        )

        with gr.Row():
            msg = gr.Textbox(
                label="Your Response",
                placeholder="Type your answer here and press Enter...",
                scale=4,
                show_label=False,
            )
            submit_btn = gr.Button("Send", variant="primary", scale=1)

        with gr.Row():
            new_survey_btn = gr.Button("New Survey", variant="secondary")
            clear_btn = gr.Button("Clear Chat", variant="secondary")

        gr.Markdown(
            """
        ---

        **Instructions:**
        1. Click "New Survey" to begin the assessment
        2. Answer each question as prompted by the survey bot
        3. After all questions are answered, you'll receive a risk assessment summary
        4. Results are automatically saved to the `survey_results` folder
        """
        )

        # Event handlers
        async def handle_submit(message, history, session_id):
            if not history:
                # Start fresh survey if no history
                session = SurveySession()
                sessions[session_id] = session
                greeting = await session.get_initial_greeting()
                history = [{"role": "assistant", "content": greeting}]

            result = await chat(message, history, session_id)
            return "", result

        async def handle_new_survey(session_id):
            # Generate new session ID for fresh start
            new_session_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
            history = await start_survey(new_session_id)
            return history, new_session_id

        # Wire up events
        msg.submit(
            handle_submit,
            inputs=[msg, chatbot, session_id],
            outputs=[msg, chatbot],
        )

        submit_btn.click(
            handle_submit,
            inputs=[msg, chatbot, session_id],
            outputs=[msg, chatbot],
        )

        new_survey_btn.click(
            handle_new_survey,
            inputs=[session_id],
            outputs=[chatbot, session_id],
        )

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
