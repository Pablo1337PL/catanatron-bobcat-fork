import pytest
from catanatron.web import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_full_sandbox_workflow_and_edge_cases(client):
    # 1. Start Sandbox game (Play both sides: HUMAN vs HUMAN)
    res = client.post(
        "/api/games",
        json={
            "players": ["HUMAN", "HUMAN"],
            "map_template": "BASE",
            "vps_to_win": 15,
            "discard_limit": 9,
            "friendly_robber": True,
        },
    )
    assert res.status_code == 200
    main_id = res.get_json()["game_id"]

    # 2. Play 8 setup moves via Bot Move (empty POST) to complete initial placement
    for step in range(8):
        r = client.post(f"/api/games/{main_id}/actions", json={})
        assert r.status_code == 200
        assert r.get_json()["state_index"] == step + 1

    state_8 = client.get(f"/api/games/{main_id}/states/latest").get_json()
    assert state_8["is_initial_build_phase"] is False
    assert state_8["current_prompt"] == "PLAY_TURN"
    assert len(state_8["variations"]) == 1

    # 3. Time Travel (GET states 0..8)
    for idx in range(9):
        r = client.get(f"/api/games/{main_id}/states/{idx}")
        assert r.status_code == 200
        assert r.get_json()["state_index"] == idx

    # 4. Auto-Branching from move 4
    state_4 = client.get(f"/api/games/{main_id}/states/4").get_json()
    legal_at_4 = state_4["current_playable_actions"][0]
    branch_res = client.post(
        f"/api/games/{main_id}/actions",
        json={"action": legal_at_4, "from_state_index": 4},
    )
    assert branch_res.status_code == 200
    branch_data = branch_res.get_json()
    branch_id = branch_data["game"]["id"]
    assert branch_id != main_id
    assert branch_data["state_index"] == 5

    # Variation Tree must have BOTH Mainline and the new Branch!
    variations = branch_data["variations"]
    assert len(variations) == 2
    assert variations[0]["game_id"] == main_id
    assert variations[0]["head_index"] == 8
    assert variations[1]["game_id"] == branch_id
    assert variations[1]["active"] is True

    # Switching back to Mainline keeps all 8 moves and both variations
    main_check = client.get(f"/api/games/{main_id}/states/latest").get_json()
    assert main_check["state_index"] == 8
    assert len(main_check["variations"]) == 2

    # 5. Control Randomness: Force Dice Roll = 6
    curr_color = main_check["current_color"]
    roll_res = client.post(
        f"/api/games/{main_id}/actions",
        json={"action": [curr_color, "ROLL", None], "forced": {"dice": 6}},
    )
    assert roll_res.status_code == 200
    roll_data = roll_res.get_json()
    assert sum(roll_data["action_records"][-1][1]) == 6

    # 6. Position Editor: Hands & Forced Dev Card
    edit_res = client.post(
        f"/api/games/{main_id}/edit",
        json={
            "op": "set_hand",
            "color": "RED",
            "resources": {"WOOD": 4, "BRICK": 4, "SHEEP": 2, "WHEAT": 2, "ORE": 6},
            "dev_cards": {"KNIGHT": 2, "VICTORY_POINT": 1},
        },
    )
    assert edit_res.status_code == 200
    edited = edit_res.get_json()
    assert edited["player_state"]["P0_ORE_IN_HAND"] == 6

    if edited["current_color"] != "RED":
        client.post(
            f"/api/games/{main_id}/edit",
            json={"op": "set_turn", "current_color": "RED", "phase": "POST_ROLL"},
        )

    buy_res = client.post(
        f"/api/games/{main_id}/actions",
        json={
            "action": ["RED", "BUY_DEVELOPMENT_CARD", None],
            "forced": {"dev_card": "MONOPOLY"},
        },
    )
    assert buy_res.status_code == 200
    assert buy_res.get_json()["player_state"]["P0_MONOPOLY_IN_HAND"] == 1

    # 7. Multi-step Undo
    for _ in range(4):
        u_res = client.post(f"/api/games/{main_id}/branch", json={"undo": True})
        assert u_res.status_code == 200

    # 8. Export & Import JSON
    exp_res = client.get(f"/api/games/{main_id}/export")
    assert exp_res.status_code == 200
    imp_res = client.post("/api/games/import", json=exp_res.get_json())
    assert imp_res.status_code == 200
