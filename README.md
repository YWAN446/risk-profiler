# Risk Profiler Survey Bot

A Pydantic AI-powered survey bot for collecting risk factor information across multiple domains. Features both a command-line interface and a web-based chat interface.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create `.env` file with your OpenAI API key:
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

## Running the Survey

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

## Domains

### Domain 1: Demographics & Vulnerability Factors (10% weight)
- Number of children under 5 years old
- Child age and vulnerability windows (evidence-based risk scoring)
- Child nutritional status (malnutrition indicators)
- Household composition (elderly, immunocompromised members)
- Primary caregiver identification

## Project Structure

```
risk-profiler/
├── app.py                  # Gradio web interface
├── main.py                 # Command-line interface
├── agents/
│   └── domain1_agent.py    # Pydantic AI agents (conversation & extraction)
├── models/
│   └── domain1.py          # Pydantic data models with risk scoring
├── prompts/
│   ├── conversation_system_prompt.md   # Survey agent behavior & guidelines
│   ├── survey_questions.md             # The 6 survey questions
│   └── extraction_system_prompt.md     # Data extraction agent instructions
├── survey_results/         # Auto-saved JSON survey results
├── requirements.txt
└── .env.example
```

## Customizing Prompts

Survey prompts are stored as markdown files in the `prompts/` directory for easy editing:

- **conversation_system_prompt.md** - Defines the agent's tone, interaction style, and survey administration rules
- **survey_questions.md** - Contains the exact wording for all survey questions
- **extraction_system_prompt.md** - Instructions for extracting structured data from conversations

## Risk Scoring

The system uses evidence-based odds ratios for vulnerability assessment:

| Age Range | Odds Ratio |
|-----------|------------|
| 0-5 months | 1.0 |
| 6-11 months | 2.26 |
| 12-23 months | 2.31 |
| 24-60 months | 1.5 |

Additional multipliers:
- Malnutrition signs: 1.14x
- Single parent household: 1.15x
- Elderly members: 1.10x
- Immunocompromised members: 1.10x
