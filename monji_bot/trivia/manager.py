# monji_bot/trivia/manager.py

import json
import random
from pathlib import Path
from typing import Dict, List, Any

# Type alias for clarity
Question = Dict[str, Any]

QUESTIONS: List[Question] = []


def load_questions() -> None:
    """
    Load questions from questions.json into the global QUESTIONS list.
    Expected format:
    [
      {
        "question": "What is the capital of France?",
        "answers": ["paris"]
      },
      ...
    ]
    """
    global QUESTIONS

    # questions.json lives next to this file
    path = Path(__file__).with_name("questions.json")

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("ERROR: questions.json not found. Monji has nothing to ask.")
        QUESTIONS = []
        return
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse questions.json: {e}")
        QUESTIONS = []
        return

    valid: List[Question] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            print(f"Skipping entry #{idx}: not an object.")
            continue

        q_text = item.get("question")
        answers = item.get("answers")

        if not q_text or not isinstance(answers, list) or not answers:
            print(f"Skipping entry #{idx}: invalid question or answers.")
            continue

        valid.append(
            {
                "question": str(q_text),
                "answers": [str(a) for a in answers],
            }
        )

    QUESTIONS = valid
    print(f"Loaded {len(QUESTIONS)} trivia questions.")


def get_random_question() -> Question | None:
    """
    Return a random question dict, or None if there are no questions.
    """
    if not QUESTIONS:
        return None
    return random.choice(QUESTIONS)
