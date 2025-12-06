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
