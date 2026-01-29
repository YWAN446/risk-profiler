"""
Utility functions for the Risk Profiler application
"""
import re
from pathlib import Path
from typing import List, Optional


# Path to prompts directory
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(filename: str) -> str:
    """Load a prompt from a markdown file"""
    prompt_path = PROMPTS_DIR / filename
    return prompt_path.read_text(encoding="utf-8")


def get_conversation_system_prompt() -> str:
    """Build the full conversation system prompt from components"""
    base_prompt = load_prompt("conversation_system_prompt.md")
    questions = load_prompt("survey_questions.md")
    return f"{base_prompt}\n\n{questions}"


def get_extraction_system_prompt() -> str:
    """Load the extraction system prompt"""
    return load_prompt("extraction_system_prompt.md")


def get_validation_system_prompt() -> str:
    """Load the validation system prompt"""
    return load_prompt("validation_system_prompt.md")


def load_questions() -> List[str]:
    """Parse survey questions from the markdown file"""
    content = load_prompt("survey_questions.md")
    questions = []
    for line in content.split("\n"):
        line = line.strip()
        # Questions are enclosed in double quotes
        if line.startswith('"') and line.endswith('"'):
            questions.append(line[1:-1])  # Remove surrounding quotes
    return questions


def extract_int_0_2(text: str) -> Optional[int]:
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
