import random

# --- Component word banks for dynamic snark generation ---

TONES = [
    "Relax",
    "Calm down",
    "Bro chill",
    "Slow your neurons",
    "Wow okay",
    "Take a deep breath",
    "Hold up",
    "Yo genius",
    "Easy there",
]

TARGETS = [
    "champ",
    "speedrunner",
    "Einstein",
    "my dude",
    "quiz goblin",
    "keyboard athlete",
    "big brain",
    "nerdling",
    "warrior of knowledge",
]

ADDONS = {
    "game_already_running": [
        "a trivia game is already running.",
        "the current trivia isn’t done.",
        "you’re not defusing a bomb.",
        "one trivia at a time, hero.",
        "Monji needs a moment, okay?",
        "just wait like a normal human.",
        "seriously, chill.",
    ],

    "single_already_running": [
        "there’s already a question running.",
        "maybe answer the one already on screen?",
        "no, you can’t stack questions.",
        "finish the question first, champ.",
        "slow down turbo mode.",
    ],

    "nothing_to_stop": [
        "there’s literally nothing running.",
        "what exactly are you trying to stop?",
        "you’re stopping air right now.",
        "Monji can’t stop what doesn’t exist.",
        "nice try but no.",
    ],

    "correct_answer": [
        "even a broken clock is right twice a day.",
        "congrats, you actually used your brain.",
        "look at you, making neurons fire.",
        "not bad, champ.",
        "wow, big brain moment.",
        "I’ll pretend I’m impressed.",
        "alright, relax, it was an easy one.",
        "don’t let this go to your head.",
        "good job… I guess.",
        "nice, but can you do it again?",
    ],

    "nobody_got_it": [
        "absolutely no one got it. Inspirational.",
        "wow… not a single neuron fired today.",
        "y’all collectively missed that harder than I expected.",
        "impressive teamwork. Every one of you got it wrong.",
        "nobody? really? stunning.",
        "I’ve seen potatoes solve harder problems.",
        "the bar was low, and yet… here we are.",
        "I’ll be telling future bots about this performance.",
        "if ignorance was an Olympic sport, this lobby just medaled.",
        "phenomenal failure. truly beautiful.",
    ],

    "hint_1": [
        "wow, you all really need help, huh?",
        "this is getting embarrassing already.",
        "hint 1 because apparently nobody reads.",
        "I wasn’t planning to babysit, but here we go.",
        "brace yourselves, the struggle is real.",
        "already? really? hint one and we’re doing THIS?",
        "fine… here’s a little push for your brain.",
    ],

    "hint_2": [
        "hint 2. the disappointment deepens.",
        "still nothing? absolutely iconic.",
        "my patience is thinning more than your guesses.",
        "okay, neurons… any day now.",
        "wow, even with a hint you guys need another one.",
        "I’m starting to worry about all of you.",
        "hint 2 because hint 1 clearly didn’t help your cause.",
    ],

    "hint_3": [
        "this is the last hint because I refuse to hold your hands any further.",
        "if you don’t get it after this, I’m filing a complaint.",
        "I can't believe I have to reveal THIS much.",
        "final hint. Good luck… you’ll need it.",
        "I swear if nobody gets it after this.",
        "this is basically the full answer at this point.",
    ],
}


def get_snark(category: str) -> str:
    """
    Generate a dynamic, original snark line based on category.
    Combines random tone + target + category-specific addon.
    """
    tone = random.choice(TONES)
    target = random.choice(TARGETS)
    addon_list = ADDONS.get(category, ["I have no idea what you're asking for."])
    addon = random.choice(addon_list)

    return f"{tone}, {target}, {addon}"

if __name__ == "__main__":
    print(get_snark(''))
