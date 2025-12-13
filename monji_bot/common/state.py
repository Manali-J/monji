# monji_bot/trivia/state.py

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import random
import discord


@dataclass
class CorrectCandidate:
    message: discord.Message


@dataclass
class GameState:
    round: int
    max_rounds: int
    current_question: Optional[dict]
    winner_id: Optional[int]
    scores: Dict[int, int]

    in_progress: bool
    resolving: bool
    midgame_quip_done: bool

    # NEW (optional but useful)
    mode: str = "trivia"

    correct_candidates: List[CorrectCandidate] = field(default_factory=list)

    @classmethod
    def new(cls, max_rounds: int, mode: str = "trivia") -> "GameState":
        return cls(
            round=0,
            max_rounds=max_rounds,
            current_question=None,
            winner_id=None,
            scores={},
            in_progress=True,
            resolving=False,
            midgame_quip_done=False,
            mode=mode,
        )

    def reset_round(self):
        self.winner_id = None
        self.correct_candidates.clear()
        self.resolving = False

    # -----------------------------
    # SCRAMBLE SUPPORT
    # -----------------------------
    def scramble(self, word: str) -> str:
        """
        Return a scrambled version of the word.
        Guaranteed to be different from the original.
        """
        if len(word) < 2:
            return word

        letters = list(word)

        scrambled = word
        attempts = 0

        # Ensure we don't return the original word
        while scrambled == word and attempts < 10:
            random.shuffle(letters)
            scrambled = "".join(letters)
            attempts += 1

        # Fallback safety (extremely rare)
        if scrambled == word:
            scrambled = "".join(reversed(word))

        return scrambled
