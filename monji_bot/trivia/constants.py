# monji_bot/trivia/constants.py
from monji_bot.common.state import GameState

EVENT_MENTION = "mention"
EVENT_HINT_3 = "hint_3"
EVENT_NO_ANSWER = "no_answer"
EVENT_MID_ROUND_QUIP = "mid_round_quip"

KEY_TEXT = "text"
KEY_HINT = "hint"

HINT_DELAY_SECONDS = 25
HINT_INTERVAL_SECONDS = 20
FINAL_WAIT_SECONDS = 10
WINNER_RESOLUTION_DELAY = 0.8
ROUND_TRANSITION_DELAY = 1.0

# -----------------------------
# CRAIG AUTO-RECORD CONFIG
# -----------------------------
AUTO_RECORD_VC_ID = 1451562698306355342  # VC to auto-record
CRAIG_COMMAND_CHANNEL_ID = 1451564976316878889  # text channel Craig reads


MODE_TRIVIA = "trivia"
MODE_SCRAMBLE = "scramble"

GAMES: dict[int, GameState] = {}
