# monji_bot/utils/fuzzy.py

from difflib import SequenceMatcher

# Very small set of “useless” words that should not count as an answer by themselves
STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "and",
    "or",
    "to",
    "in",
    "on",
    "at",
    "for",
}


def normalize(text: str) -> str:
    """Lowercase, strip spaces, remove basic punctuation."""
    text = text.strip().lower()
    for ch in [".", ",", "!", "?", ":", ";", "\"", "'", "’", "(", ")", "[", "]"]:
        text = text.replace(ch, "")
    return " ".join(text.split())


def is_numeric(text: str) -> bool:
    """Return True if the text is a clean integer-like string."""
    t = text.strip()
    return t.isdigit()


def all_numeric(answers) -> bool:
    """Return True if every correct answer is numeric."""
    return all(is_numeric(a) for a in answers)


def is_fuzzy_match(user_answer: str, correct_answer: str, threshold: float = 0.8) -> bool:
    """
    Return True if the user's answer is 'close enough' to the correct answer.
    Used for free-text trivia answers.
    """
    ua = normalize(user_answer)
    ca = normalize(correct_answer)

    if not ua or not ca:
        return False

    # Split into tokens
    ua_tokens = ua.split()
    ca_tokens = ca.split()
    multi_word_correct = len(ca_tokens) > 1

    # If the user answer is only stopwords (e.g. "the", "of the"), auto-fail
    if all(token in STOPWORDS for token in ua_tokens):
        return False

    # Exact match
    if ua == ca:
        return True

    # Substring match:
    # - For single-word correct answers, allow normal substring matching.
    # - For multi-word correct answers, only allow if the user also gave at least 2 words.
    if len(ua) >= 3:
        if not multi_word_correct and (ua in ca or ca in ua):
            return True
        if multi_word_correct and len(ua_tokens) >= 2 and (ua in ca or ca in ua):
            return True

    # Fuzzy ratio on the full strings
    ratio = SequenceMatcher(None, ua, ca).ratio()
    return ratio >= threshold


def is_correct_answer(user_answer: str, correct_answers) -> bool:
    """
    Determines correctness:
      - If all answers are numeric → exact match only (with int normalization).
      - If all answers are single characters → exact match only (case-insensitive).
      - Otherwise → fuzzy match.
    """
    user_answer = user_answer.strip()

    # NUMERIC MODE: all correct answers are numeric → strict numeric comparison
    if all_numeric(correct_answers):
        if not is_numeric(user_answer):
            return False

        try:
            user_val = int(user_answer)
            correct_vals = [int(a) for a in correct_answers]
            return user_val in correct_vals
        except ValueError:
            return False

    # SINGLE CHARACTER MODE: all correct answers are single characters (e.g., "A", "B")
    if all(len(a.strip()) == 1 for a in correct_answers):
        # Case-insensitive exact match
        normalized_user = user_answer.lower()
        normalized_correct = [a.strip().lower() for a in correct_answers]
        return normalized_user in normalized_correct

    # TEXT MODE: use fuzzy matching against any correct answer
    for ca in correct_answers:
        if is_fuzzy_match(user_answer, ca):
            return True

    return False
