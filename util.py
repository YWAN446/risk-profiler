"""
Utility functions for the Risk Profiler application
"""
import re
from pathlib import Path
from typing import List, Optional, Any, Dict


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

def coerce_model_output_to_dict(obj: Any) -> Dict[str, Any]:
    """
    Convert pydantic_ai outputs to a plain dict.

    Handles:
    - dict
    - ModelResponse with ToolCallPart(args='...json...')
    - objects with .text containing JSON
    """

    # Already a dict
    if isinstance(obj, dict):
        return obj

    # Case 1: ModelResponse with tool calls
    if hasattr(obj, "parts") and obj.parts:
        for part in obj.parts:
            if hasattr(part, "args"):
                try:
                    payload = json.loads(part.args)

                    # Some models wrap inside {"response": {...}}
                    if isinstance(payload, dict):
                        if "response" in payload and isinstance(payload["response"], dict):
                            return payload["response"]
                        return payload
                except Exception:
                    continue

    # Case 2: fallback to .text JSON
    text = getattr(obj, "text", None)
    if isinstance(text, str) and text.strip():
        t = text.strip()
        start = t.find("{")
        end = t.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                payload = json.loads(t[start:end+1])
                if isinstance(payload, dict):
                    if "response" in payload and isinstance(payload["response"], dict):
                        return payload["response"]
                    return payload
            except Exception:
                pass

    return {}
