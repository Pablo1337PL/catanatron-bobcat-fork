"""API additions of the Bobcat fork: 1v1 defaults, seat order, seeds, server
settings (create_app) and 400 for an action the game cannot take."""

import pytest

from catanatron.apply_action import seeded_roll
from catanatron.web import create_app
from catanatron.web.models import db, get_game_state


def _make_client(**app_kwargs):
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test",
        },
        **app_kwargs,
    )
    with app.app_context():
        db.create_all()
    return app.test_client()


@pytest.fixture
def client():
    return _make_client()


def _new_game(client, **body):
    response = client.post("/api/games", json={"players": ["F", "R"], **body})
    assert response.status_code == 200, response.data
    game_id = response.get_json()["game_id"]
    with client.application.app_context():
        return game_id, get_game_state(game_id)


def _latest(client, game_id):
    return client.get(f"/api/games/{game_id}/states/latest").get_json()


def test_rules_default_to_1v1(client):
    _, game = _new_game(client)
    assert game.vps_to_win == 15
    assert game.state.discard_limit == 9
    assert game.state.friendly_robber is True


def test_seats_follow_the_players_list_unless_random(client):
    for order in (["F", "R"], ["R", "F"]):
        _, game = _new_game(client, players=order)
        assert [c.value for c in game.state.colors] == ["RED", "BLUE"]

    starters = {
        _new_game(client, random_seats=True)[1].state.colors[0].value
        for _ in range(30)
    }
    assert starters == {"RED", "BLUE"}


def test_seeds_are_used_and_recorded(client):
    a_id, a = _new_game(client, seed=1, board_seed=2, dice_seed=3)
    _, b = _new_game(client, seed=1, board_seed=2, dice_seed=3)
    assert (a.seed, a.board_seed, a.dice_seed) == (1, 2, 3)
    assert a.state.board.map.land_tiles.keys() == b.state.board.map.land_tiles.keys()
    assert all(
        a.state.board.map.land_tiles[c].number == b.state.board.map.land_tiles[c].number
        for c in a.state.board.map.land_tiles
    )

    # missing seeds are drawn, so every game can be replayed; below 2**31 so
    # a browser (JavaScript numbers) shows them exactly
    _, c = _new_game(client)
    for seed in (c.seed, c.board_seed, c.dice_seed):
        assert 0 <= seed < 2**31

    view = _latest(client, a_id)
    assert view["seeds"] == {"board": 2}  # dice and game seeds only after the end
    assert "dice_seed" not in view["game"] and "seed" not in view["game"]


def test_dice_follow_the_dice_seed_across_requests(client):
    game_id, _ = _new_game(client, players=["F", "F"], dice_seed=5)
    view = _latest(client, game_id)
    for _ in range(80):
        view = client.post(f"/api/games/{game_id}/actions").get_json()
    rolls = [
        tuple(result)
        for (_, action_type, _), result in view["action_records"]
        if action_type == "ROLL"
    ]
    assert len(rolls) > 3
    assert rolls == [seeded_roll(5, i) for i in range(len(rolls))]


def test_bad_seed_is_a_400(client):
    for bad in (-1, "7", 1.5, True):
        response = client.post("/api/games", json={"players": ["F", "R"], "dice_seed": bad})
        assert response.status_code == 400


def test_server_defaults_and_forced_rules():
    client = _make_client(
        game_defaults={"board_seed": 11, "dice_seed": 12, "vps_to_win": 12},
        forced_rules={"vps_to_win": 10, "discard_limit": 7, "friendly_robber": False},
    )
    _, game = _new_game(client, vps_to_win=20, discard_limit=15, friendly_robber=True)
    assert (game.board_seed, game.dice_seed) == (11, 12)
    assert (game.vps_to_win, game.state.discard_limit, game.state.friendly_robber) == (
        10,
        7,
        False,
    )
    _, game = _new_game(client, board_seed=99)
    assert game.board_seed == 99  # the request wins over defaults

    client = _make_client(game_defaults={"vps_to_win": 12})
    assert _new_game(client)[1].vps_to_win == 12
    assert _new_game(client, vps_to_win=14)[1].vps_to_win == 14


def test_illegal_action_is_a_400_and_the_game_goes_on(client):
    game_id, game = _new_game(client, players=["HUMAN", "F"])
    before = _latest(client, game_id)
    assert before["current_color"] == "RED"

    response = client.post(
        f"/api/games/{game_id}/actions", json=["RED", "BUILD_CITY", 7]
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "illegal_action"
    assert body["action"] == ["RED", "BUILD_CITY", 7]
    assert _latest(client, game_id)["state_index"] == before["state_index"]

    response = client.post(f"/api/games/{game_id}/actions", json=["RED", "NOPE", 7])
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_action"

    legal = before["current_playable_actions"][0]
    response = client.post(f"/api/games/{game_id}/actions", json=legal)
    assert response.status_code == 200
    assert response.get_json()["state_index"] == before["state_index"] + 1
