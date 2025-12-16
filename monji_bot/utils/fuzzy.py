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
    for ch in [".", ",", "!", "?", ":", ";", "\"", "'", "’", "(", ")", "[", "]", "-"]:
        text = text.replace(ch, "")
    return " ".join(text.split())


def is_numeric(text: str) -> bool:
    """Return True if the text is a clean integer-like string."""
    t = text.strip()
    return t.isdigit()


def all_numeric(answers) -> bool:
    """Return True if every correct answer is numeric."""
    return all(is_numeric(a) for a in answers)


def is_fuzzy_match(user_answer: str, correct_answer: str, threshold: float = 0.9) -> bool:
    """
    Return True if the user's answer is 'close enough' to the correct answer.
    Used for free-text trivia answers.
    """
    ua = normalize(user_answer)
    ca = normalize(correct_answer)

    if not ua or not ca:
        return False

    ua_tokens = ua.split()
    ca_tokens = ca.split()
    multi_word_correct = len(ca_tokens) > 1

    # If the user answer is only stopwords, auto-fail
    if all(token in STOPWORDS for token in ua_tokens):
        return False

    # Exact match
    if ua == ca:
        return True

    # -----------------------------
    # STRICT RULE FOR MULTI-WORD ANSWERS
    # -----------------------------
    if multi_word_correct:
        ua_set = {t for t in ua_tokens if t not in STOPWORDS}
        ca_set = {t for t in ca_tokens if t not in STOPWORDS}
        return ua_set == ca_set

    # -----------------------------
    # SINGLE-WORD ANSWERS (FUZZY BUT STRICT)
    # -----------------------------
    # Very short answers (<= 4 letters)
    if len(ca) <= 4:
        if ua[0] != ca[0]:
            return False
        ratio = SequenceMatcher(None, ua, ca).ratio()
        return ratio >= 0.9

    # Longer single-word answers
    if abs(len(ua) - len(ca)) > 2:
        return False

    if ua[0] != ca[0] and ua[-1] != ca[-1]:
        return False

    ratio = SequenceMatcher(None, ua, ca).ratio()
    return ratio >= threshold


def is_correct_answer(user_answer: str, correct_answers) -> bool:
    """
    Determines correctness:
      - If all answers are numeric → exact match only.
      - If all answers are single characters → exact match only.
      - Otherwise → fuzzy/text match.
    """
    user_answer = user_answer.strip()

    # NUMERIC MODE
    if all_numeric(correct_answers):
        if not is_numeric(user_answer):
            return False
        try:
            user_val = int(user_answer)
            correct_vals = [int(a) for a in correct_answers]
            return user_val in correct_vals
        except ValueError:
            return False

    # SINGLE CHARACTER MODE
    if all(len(a.strip()) == 1 for a in correct_answers):
        normalized_user = user_answer.lower()
        normalized_correct = [a.strip().lower() for a in correct_answers]
        return normalized_user in normalized_correct

    # TEXT MODE
    for ca in correct_answers:
        if is_fuzzy_match(user_answer, ca):
            return True

    return False
