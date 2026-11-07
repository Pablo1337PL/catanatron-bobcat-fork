"""A human playing a bot through the web API sees how many development cards
the bot holds, not which; once the game is over every state shows them."""

import pytest

from catanatron.models.enums import DEVELOPMENT_CARDS, Action, ActionType
from catanatron.state_functions import player_key
from catanatron.web import create_app
from catanatron.web.models import db, get_game_state, upsert_game_state

RESOURCES = ["WOOD", "BRICK", "SHEEP", "WHEAT", "ORE"]


@pytest.fixture
def client():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test",
        }
    )
    with app.app_context():
        db.create_all()
    return app.test_client()


def _new_game(client, players, **rules):
    response = client.post(
        "/api/games",
        json={"players": players, "seed": 4, "board_seed": 4, "dice_seed": 4, **rules},
    )
    return response.get_json()["game_id"]


def _play(client, game_id, ticks):
    """Empty posts: the human seat's fallback decides for it."""
    for _ in range(ticks):
        state = client.post(f"/api/games/{game_id}/actions").get_json()
    return state


def _seat(state, color):
    return f"P{state['colors'].index(color)}_"


def _bot_buys_cards(client, game_id, count):
    """The bot buys ``count`` development cards; returns what it drew."""
    with client.application.app_context():
        game = get_game_state(game_id)
        bot = next(p.color for p in game.state.players if p.is_bot)
        key = player_key(game.state, bot)
        for _ in range(count):
            for resource in ("SHEEP", "WHEAT", "ORE"):
                game.state.player_state[f"{key}_{resource}_IN_HAND"] += 1
            game.execute(
                Action(bot, ActionType.BUY_DEVELOPMENT_CARD, None),
                validate_action=False,
            )
            upsert_game_state(game)
        return bot.value, [record.result for record in game.state.action_records[-count:]]


def test_the_bots_development_cards_are_only_counted(client):
    game_id = _new_game(client, ["HUMAN", "R"])
    _play(client, game_id, 30)
    bot, drawn = _bot_buys_cards(client, game_id, 3)

    state = client.get(f"/api/games/{game_id}/states/latest").get_json()
    human = next(c for c in state["colors"] if c != bot)
    theirs, mine = _seat(state, bot), _seat(state, human)
    hand = state["player_state"]

    assert hand[theirs + "NUM_DEVELOPMENT_CARDS_IN_HAND"] == 3
    for card in DEVELOPMENT_CARDS:
        assert theirs + f"{card}_IN_HAND" not in hand
        assert mine + f"{card}_IN_HAND" in hand
    assert theirs + "ACTUAL_VICTORY_POINTS" not in hand
    assert theirs + "KNIGHT_OWNED_AT_START" not in hand
    # The resources stay face up.
    assert all(theirs + f"{r}_IN_HAND" in hand for r in RESOURCES)

    for action, result in state["action_records"][-3:]:
        assert action == [bot, "BUY_DEVELOPMENT_CARD", None]
        assert result is None
    # What the bot holds is folded back into the deck, so the deck's
    # composition does not give it away.
    with client.application.app_context():
        game = get_game_state(game_id)
        deck = list(game.state.development_listdeck)
    unseen = {card: deck.count(card) + drawn.count(card) for card in DEVELOPMENT_CARDS}
    assert state["development_listdeck"] == {c: n for c, n in sorted(unseen.items()) if n}


def test_the_bots_options_are_not_listed_on_its_turn(client):
    game_id = _new_game(client, ["HUMAN", "R"])
    state = _play(client, game_id, 40)

    seen = set()
    for index in range(state["state_index"] + 1):
        past = client.get(f"/api/games/{game_id}/states/{index}").get_json()
        bots_turn = past["current_color"] in past["bot_colors"]
        assert (past["current_playable_actions"] == []) == bots_turn
        seen.add(bots_turn)
    assert seen == {True, False}


def test_bots_alone_show_everything(client):
    game_id = _new_game(client, ["R", "R"])
    state = _play(client, game_id, 30)

    for color in state["colors"]:
        assert _seat(state, color) + "KNIGHT_IN_HAND" in state["player_state"]
    assert state["current_playable_actions"]


def test_after_the_game_every_state_shows_the_cards(client):
    game_id = _new_game(client, ["HUMAN", "R"], vps_to_win=3)
    _play(client, game_id, 30)
    bot, drawn = _bot_buys_cards(client, game_id, 2)
    state = _play(client, game_id, 300)
    assert state["winning_color"] is not None
    human = next(c for c in state["colors"] if c != bot)

    bought_at = next(
        i
        for i, (action, _) in enumerate(state["action_records"])
        if action[1] == "BUY_DEVELOPMENT_CARD"
    )
    for query in ("", f"?as={human}"):
        earlier = client.get(
            f"/api/games/{game_id}/states/{bought_at + 2}{query}"
        ).get_json()
        hand = earlier["player_state"]
        theirs = _seat(earlier, bot)
        assert sum(hand[theirs + f"{card}_IN_HAND"] for card in DEVELOPMENT_CARDS) == 2
        assert theirs + "WOOD_IN_HAND" in hand
        assert [result for _, result in earlier["action_records"][-2:]] == drawn
        assert earlier["current_playable_actions"]
