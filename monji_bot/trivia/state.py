# monji_bot/trivia/state.py

from dataclasses import dataclass, field
from typing import Dict, List, Optional
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

    correct_candidates: List[CorrectCandidate] = field(default_factory=list)

    @classmethod
    def new(cls, max_rounds: int) -> "GameState":
        return cls(
            round=0,
            max_rounds=max_rounds,
            current_question=None,
            winner_id=None,
            scores={},
            in_progress=True,
            resolving=False,
            midgame_quip_done=False,
        )

    def reset_round(self):
        self.winner_id = None
        self.correct_candidates.clear()
        self.resolving = False
