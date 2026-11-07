"""Every game saved by the web API records when each action was played and,
for a roll or a monopoly, how it changed the hands."""

import sqlite3
import time

import pytest

from catanatron.models.enums import Action, ActionType
from catanatron.state_functions import player_key
from catanatron.web import create_app
from catanatron.web.models import (
    StoredAction,
    db,
    get_game_state,
    upsert_game_state,
)

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


def _new_game(client):
    response = client.post(
        "/api/games",
        json={"players": ["R", "R"], "seed": 3, "board_seed": 3, "dice_seed": 3},
    )
    return response.get_json()["game_id"]


def _play(client, game_id, ticks):
    for _ in range(ticks):
        state = client.post(f"/api/games/{game_id}/actions").get_json()
    return state


def _hand(state, color):
    seat = state["colors"].index(color)
    return {r: state["player_state"][f"P{seat}_{r}_IN_HAND"] for r in RESOURCES}


def test_every_action_has_the_time_it_was_played(client):
    before = time.time()
    game_id = _new_game(client)
    state = _play(client, game_id, 40)
    after = time.time()

    details = state["action_details"]
    assert len(details) == len(state["action_records"]) == 40
    times = [d["played_at"] for d in details]
    assert before <= state["created_at"] <= times[0]
    assert times == sorted(times)
    assert times[-1] <= after

    # An earlier state carries the times of the actions up to it.
    earlier = client.get(f"/api/games/{game_id}/states/10").get_json()
    assert earlier["created_at"] == state["created_at"]
    assert [d["played_at"] for d in earlier["action_details"]] == times[:10]


def test_a_roll_says_what_it_paid_to_each_seat(client):
    game_id = _new_game(client)
    state = _play(client, game_id, 120)

    paying_rolls = 0
    for index, (record, details) in enumerate(
        zip(state["action_records"], state["action_details"])
    ):
        action, dice = record
        if action[1] != "ROLL":
            continue
        assert details["resource_changes"] is not None
        before = client.get(f"/api/games/{game_id}/states/{index}").get_json()
        after = client.get(f"/api/games/{game_id}/states/{index + 1}").get_json()
        for color in state["colors"]:
            expected = {
                r: n - _hand(before, color)[r]
                for r, n in _hand(after, color).items()
                if n != _hand(before, color)[r]
            }
            assert details["resource_changes"].get(color, {}) == expected
            assert all(n > 0 for n in expected.values())
        if sum(dice) == 7:
            assert details["resource_changes"] == {}
        paying_rolls += bool(details["resource_changes"])
    assert paying_rolls > 0


def test_private_changes_are_not_shown(client):
    """What a steal took or a discard gave up stays in the database only."""
    game_id = _new_game(client)
    state = _play(client, game_id, 120)

    for record, details in zip(state["action_records"], state["action_details"]):
        if record[0][1] not in ("ROLL", "PLAY_MONOPOLY"):
            assert details["resource_changes"] is None
    with client.application.app_context():
        stored = db.session.query(StoredAction).filter_by(uuid=game_id).all()
        assert all(row.resource_changes is not None for row in stored)


def test_a_monopoly_says_how_many_cards_it_took(client):
    game_id = _new_game(client)
    state = _play(client, game_id, 30)
    assert not state["is_initial_build_phase"]

    with client.application.app_context():
        game = get_game_state(game_id)
        me = game.state.current_color()
        other = next(c for c in game.state.colors if c != me)
        mine, theirs = player_key(game.state, me), player_key(game.state, other)
        game.state.player_state[f"{mine}_MONOPOLY_IN_HAND"] = 1
        game.state.player_state[f"{mine}_MONOPOLY_OWNED_AT_START"] = True
        game.state.player_state[f"{mine}_HAS_PLAYED_DEVELOPMENT_CARD_IN_TURN"] = False
        game.state.player_state[f"{theirs}_WHEAT_IN_HAND"] = 4
        upsert_game_state(game)  # the hands before the monopoly
        game.execute(
            Action(me, ActionType.PLAY_MONOPOLY, "WHEAT"), validate_action=False
        )
        upsert_game_state(game)

    state = client.get(f"/api/games/{game_id}/states/latest").get_json()
    assert state["action_records"][-1][0][1] == "PLAY_MONOPOLY"
    assert state["action_details"][-1]["resource_changes"] == {
        me.value: {"WHEAT": 4},
        other.value: {"WHEAT": -4},
    }


def test_actions_saved_together_have_no_changes(client):
    """Only a single new action can be compared with the previous head."""
    game_id = _new_game(client)
    with client.application.app_context():
        game = get_game_state(game_id)
        for _ in range(5):
            game.play_tick()
        upsert_game_state(game)

    details = client.get(f"/api/games/{game_id}/states/latest").get_json()[
        "action_details"
    ]
    assert len(details) == 5
    assert all(d["resource_changes"] is None for d in details)
    assert all(d["played_at"] is not None for d in details)


def test_a_database_from_before_the_timestamps_gets_the_new_columns(
    tmp_path, monkeypatch
):
    path = tmp_path / "games.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE games (
            uuid VARCHAR(64) PRIMARY KEY, schema_version INTEGER NOT NULL,
            player_specs VARCHAR NOT NULL, base_index INTEGER NOT NULL,
            base_state VARCHAR NOT NULL, head_index INTEGER NOT NULL,
            head_state VARCHAR NOT NULL
        );
        CREATE TABLE game_actions (
            uuid VARCHAR(64) REFERENCES games(uuid), "index" INTEGER,
            payload VARCHAR NOT NULL, PRIMARY KEY (uuid, "index")
        );
        """
    )
    connection.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")

    client = create_app({"TESTING": True}).test_client()
    game_id = _new_game(client)
    state = _play(client, game_id, 3)

    columns = {
        table: {row[1] for row in sqlite3.connect(path).execute(f"PRAGMA table_info({table})")}
        for table in ("games", "game_actions")
    }
    assert "created_at" in columns["games"]
    assert {"played_at", "resource_changes"} <= columns["game_actions"]
    assert all(d["played_at"] is not None for d in state["action_details"])
