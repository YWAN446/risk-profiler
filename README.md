# Risk Profiler Survey Bot

A Pydantic AI-powered survey bot for collecting risk factor information across 7 domains.

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

3. Run the survey:
```bash
python main.py
```

## Domains

### Domain 1: Demographics & Vulnerability Factors (10% weight)
- Child age and vulnerability windows
- Child nutritional status
- Household composition

## Project Structure

- `models/domain1.py` - Pydantic models for Domain 1 data
- `agents/domain1_agent.py` - Pydantic AI agent for Domain 1 survey
- `main.py` - Main survey application
