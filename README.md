# Risk Profiler Survey Bot

Risk Profiler is a **Pydantic AI–powered conversational survey system** designed to collect household-level risk factors related to diarrheal disease and environmental health risks.

The system uses **large language models (LLMs)** to conduct structured surveys through a chat interface and automatically extract responses into structured data for **risk scoring and vulnerability assessment**.

The tool supports both a **command-line interface (CLI)** and a **web-based chat interface using Gradio**.

---

# Features

- Conversational survey powered by LLMs
- Structured data extraction using Pydantic models
- Multi-domain risk assessment framework
- Automatic risk score calculation
- Web-based chat interface (Gradio)
- Command-line survey mode
- Editable survey prompts via Markdown files

---

# Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create `.env` file with your OpenAI API key:
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

# Running the Survey

### Web Interface (Gradio)

Launch the web-based chat interface:
```bash
python app.py
```

Then open http://127.0.0.1:7860 in your browser. Click "New Survey" to begin.

### Command Line Interface

Run the survey in your terminal:
```bash
python main.py
```

# Risk Domains

The Risk Profiler collects information across three domains, each representing a different category of risk factors.

## Domain 1 — Demographics & Vulnerability Factors

Weight: 10%

This domain captures household demographic and biological vulnerability factors, especially those related to young children.

Key variables include:
	•	Number of children under 5 years old
	•	Child age (in months) to identify vulnerability windows
	•	Signs of child malnutrition
	•	Presence of elderly household members
	•	Presence of immunocompromised household members
	•	Primary caregiver of young children

## Domain 2 — WASH (Water, Sanitation, and Hygiene)

Weight: 20%

This domain collects information about household water sources, sanitation infrastructure, and hygiene behaviors.

Key variables include:
	•	Primary drinking water source
	•	Whether drinking water is treated
	•	Water treatment method (e.g., boiling)
	•	Type of toilet facility
	•	Availability of a handwashing station
	•	Presence of soap at the handwashing location
	•	Handwashing frequency after toilet use

These indicators are commonly used in global health and WASH risk assessments.

⸻

## Domain 3 — Environmental & Temporal Risk Factors

Weight: 20%

This domain captures recent environmental events and community health signals that may increase the risk of diarrheal disease.

Key variables include:
	•	Recent extreme weather events (heatwave, heavy rainfall, flooding)
	•	Timing of the most recent event
	•	Reports of diarrhoea in the community
	•	Household water supply interruptions
	•	Whether water storage behavior changed due to interruptions

These questions help identify short-term environmental exposure risks.

# Project Structure

```
risk-profiler/
├── app.py                     # Gradio web interface
├── main.py                    # Command-line survey interface
├── util.py                    # Utility functions
│
├── agents/                    # LLM survey agents
│   ├── domain1_agent.py
│   ├── domain2_agent.py
│   └── domain3_agent.py
│
├── models/                    # Pydantic data models and scoring logic
│   ├── domain1.py
│   ├── domain2.py
│   └── domain3.py
│
├── prompts/                   # Editable prompt templates
│   ├── conversation_system_prompt.md
│   ├── survey_questions_domain1.md
│   ├── survey_questions_domain2.md
│   ├── survey_questions_domain3.md
│   ├── extraction_system_prompt.md
│   └── validation_system_prompt.md
│
├── survey_results/            # Saved JSON survey outputs
│
├── requirements.txt
└── .env.example
```

# Customizing Prompts

Survey prompts are stored as markdown files in the `prompts/` directory for easy editing:

- **conversation_system_prompt.md** - Defines the agent's tone, interaction style, and survey administration rules
- **survey_questions.md** - Contains the exact wording for all survey questions (parsed at runtime)
- **extraction_system_prompt.md** - Instructions for extracting structured data from conversations
- **validation_system_prompt.md** - Rules for validating answers and generating follow-up questions

# Output

Survey responses are automatically saved as structured JSON files in the survey_results/ directory.

Example output fields include:
	•	household demographics
	•	WASH indicators
	•	environmental exposures
	•	calculated domain risk scores
	•	final aggregated risk score

## Future Improvements

Planned extensions for the system include:
	•	Integrated multi-domain scoring framework
	•	Improved follow-up question logic
	•	Survey response validation improvements
	•	Dashboard for visualizing risk distributions
	•	Integration with epidemiological risk models

## License

This project is for academic research and educational purposes.
