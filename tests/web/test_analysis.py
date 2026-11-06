"""GET /api/games/<id>/states/<index>/analysis: the engine is plugged in with
create_app(analyzer=...); the fork itself has none."""

from catanatron.web import create_app
from catanatron.web.models import db, get_game_state, upsert_game_state


def _make_client(analyzer=None):
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test",
        },
        analyzer=analyzer,
    )
    with app.app_context():
        db.create_all()
    return app.test_client()


def _new_game(client, **rules):
    response = client.post(
        "/api/games",
        json={"players": ["R", "R"], "seed": 1, "board_seed": 1, "dice_seed": 1, **rules},
    )
    return response.get_json()["game_id"]


def _analysis(client, game_id, index="latest"):
    return client.get(f"/api/games/{game_id}/states/{index}/analysis")


class FakeAnalyzer:
    def __init__(self):
        self.games = []

    def __call__(self, game):
        self.games.append(game)
        player = game.state.current_color().value
        return {
            "engine": "fake",
            "player": player,
            "win_probability": {c.value: 0.5 for c in game.state.colors},
            "simulations": 1,
            "seconds": 0.0,
            "moves": [],
        }


def test_without_an_analyzer_the_endpoint_answers_501():
    client = _make_client()
    response = _analysis(client, _new_game(client))
    assert response.status_code == 501
    assert response.get_json()["error"] == "no_analyzer"


def test_the_analyzer_gets_the_requested_state():
    analyzer = FakeAnalyzer()
    client = _make_client(analyzer)
    game_id = _new_game(client)
    for _ in range(3):
        client.post(f"/api/games/{game_id}/actions")

    latest = _analysis(client, game_id)
    earlier = _analysis(client, game_id, 1)

    assert latest.status_code == earlier.status_code == 200
    assert latest.get_json()["state_index"] == 3
    assert earlier.get_json()["state_index"] == 1
    assert [len(g.state.action_records) for g in analyzer.games] == [3, 1]
    assert latest.get_json()["engine"] == "fake"


def test_the_analyzer_cannot_change_the_stored_game():
    def mutating_analyzer(game):
        game.play_tick()
        return FakeAnalyzer()(game)

    client = _make_client(mutating_analyzer)
    game_id = _new_game(client)
    _analysis(client, game_id)

    state = client.get(f"/api/games/{game_id}/states/latest").get_json()
    assert state["state_index"] == 0


def test_a_finished_game_is_not_analyzed():
    analyzer = FakeAnalyzer()
    client = _make_client(analyzer)
    # 3 points: random players finish well before the turn limit (no draw)
    game_id = _new_game(client, vps_to_win=3)
    with client.application.app_context():
        game = get_game_state(game_id)
        game.play()
        upsert_game_state(game)
        winner = game.winning_color().value

    body = _analysis(client, game_id).get_json()

    assert analyzer.games == []
    assert body["moves"] == []
    assert body["win_probability"][winner] == 1.0


def test_analyzer_errors():
    def unsupported(game):
        raise ValueError("1v1 only")

    def broken(game):
        raise RuntimeError("weights missing")

    for analyzer, status, error in [
        (unsupported, 400, "unsupported"),
        (broken, 500, "analysis_failed"),
    ]:
        client = _make_client(analyzer)
        response = _analysis(client, _new_game(client))
        assert response.status_code == status
        assert response.get_json()["error"] == error

    client = _make_client(FakeAnalyzer())
    assert _analysis(client, "missing").status_code == 404
