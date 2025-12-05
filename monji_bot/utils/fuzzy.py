# monji_bot/utils/fuzzy.py

from difflib import SequenceMatcher


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

    # Exact match
    if ua == ca:
        return True

    # Substring match for short-ish answers (“new york” vs “new york city”)
    if len(ua) >= 3 and (ua in ca or ca in ua):
        return True

    # Fuzzy ratio
    ratio = SequenceMatcher(None, ua, ca).ratio()
    return ratio >= threshold
