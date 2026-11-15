import json
import logging
import random
import threading

from flask import Response, Blueprint, current_app, jsonify, abort, request

from catanatron.web.models import (
    StaleGameError,
    get_action_details,
    get_game_state,
    upsert_game_state,
)
from catanatron.serialization import action_from_json, is_over, web_view
from catanatron.state_functions import get_state_index
from catanatron.models.enums import ActionType
from catanatron.models.player import Color
from catanatron.game import Game
from catanatron.models.map import build_map
from catanatron.players.minimax import AlphaBetaPlayer
from catanatron.registry import REGISTRY, describe, SpecError
from catanatron.web.players import register_web_players

bp = Blueprint("api", __name__, url_prefix="/api")
VALID_MAP_TEMPLATES = {"BASE", "TOURNAMENT"}

register_web_players()


@bp.route("/players", methods=("GET",))
def get_players_endpoint():
    """List the players this server can seat, and the params each accepts."""
    return jsonify([describe(key, REGISTRY[key]) for key in sorted(REGISTRY)])


#: Rules of a new game when the request leaves them out: 1v1 (15 points,
#: discard above 9 cards, friendly robber).
DEFAULT_RULES = {"vps_to_win": 15, "discard_limit": 9, "friendly_robber": True}
SEED_FIELDS = ("seed", "board_seed", "dice_seed")


def _setting(name):
    """A new game's setting: the request, else the server's defaults
    (``create_app(game_defaults=...)``), else None."""
    if name in request.json:
        return request.json[name]
    return current_app.config.get("GAME_DEFAULTS", {}).get(name)


def _rule(name, check, description):
    value = _setting(name)
    if value is None:
        value = DEFAULT_RULES[name]
    if not check(value):
        abort(400, description=description)
    return value


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


@bp.route("/games", methods=("POST",))
def post_game_endpoint():
    """Create a game.

    Body: ``players`` (required, seated in this order unless ``random_seats``),
    ``map_template``, ``vps_to_win``, ``discard_limit``, ``friendly_robber``
    (1v1 by default), ``random_seats`` (default false), and the seeds
    ``seed``, ``board_seed``, ``dice_seed`` (int >= 0 or null; a missing seed
    is drawn at random below 2**31, so every game can be replayed).
    """
    if not request.is_json or request.json is None or "players" not in request.json:
        abort(400, description="Missing or invalid JSON body: 'players' key required")

    player_keys = request.json["players"]
    if not isinstance(player_keys, list) or len(player_keys) != 2:
        abort(400, description="'players' must be a list with exactly 2 entries")

    map_template = _setting("map_template") or "BASE"
    if map_template not in VALID_MAP_TEMPLATES:
        abort(
            400,
            description="'map_template' must be BASE or TOURNAMENT",
        )

    rules = {
        "discard_limit": _rule(
            "discard_limit",
            lambda v: _is_int(v) and 5 <= v <= 20,
            "'discard_limit' must be an integer between 5 and 20",
        ),
        "vps_to_win": _rule(
            "vps_to_win",
            lambda v: _is_int(v) and 3 <= v <= 20,
            "'vps_to_win' must be an integer between 3 and 20",
        ),
        "friendly_robber": _rule(
            "friendly_robber",
            lambda v: isinstance(v, bool),
            "'friendly_robber' must be a boolean",
        ),
    }
    # A server can impose its rules regardless of the form (create_app(forced_rules=...))
    rules.update(current_app.config.get("FORCED_RULES") or {})

    random_seats = _setting("random_seats") or False
    if not isinstance(random_seats, bool):
        abort(400, description="'random_seats' must be a boolean")

    seeds = {}
    for name in SEED_FIELDS:
        value = _setting(name)
        if value is not None and not (_is_int(value) and value >= 0):
            abort(400, description=f"'{name}' must be a non-negative integer or null")
        seeds[name] = value
    # Missing seeds are drawn here (not by Game, whose default seed can reach
    # 2**63) so they stay exact as JavaScript numbers and the UI can replay them.
    if seeds["seed"] is None:
        seeds["seed"] = random.randrange(2**31)
    if seeds["board_seed"] is None and map_template != "TOURNAMENT":
        seeds["board_seed"] = random.randrange(2**31)
    if seeds["dice_seed"] is None:
        seeds["dice_seed"] = random.randrange(2**31)

    try:
        players = REGISTRY.build_all(player_keys)
    except SpecError as error:
        abort(400, description=str(error))
    catan_map = build_map(map_template, board_seed=seeds["board_seed"])

    game = Game(
        players=players,
        catan_map=catan_map,
        seat_order=None if random_seats else [p.color for p in players],
        **rules,
        **seeds,
    )
    from catanatron.web.sandbox import record_snapshot, ensure_in_variation_tree
    upsert_game_state(game)
    record_snapshot(game)
    ensure_in_variation_tree(game)
    return jsonify({"game_id": game.id})


@bp.route("/games/<string:game_id>/states/<string:state_index>", methods=("GET",))
def get_game_endpoint(game_id, state_index):
    from catanatron.web.sandbox import get_game_state_safe, ensure_in_variation_tree
    parsed_state_index = _parse_state_index(state_index)
    game = get_game_state_safe(game_id, parsed_state_index)
    if game is None:
        abort(404, description="Resource not found")
    ensure_in_variation_tree(game)
    if parsed_state_index is None:
        return _game_response(game)
    return _game_response(game, latest=get_game_state_safe(game_id))


#: One move at a time per game in this process. Requests run in threads, and a
#: client may ask for the same bot move twice (React StrictMode runs effects
#: twice); two moves played from the same state would both try to save it.
_game_locks = {}
_game_locks_guard = threading.Lock()


def _game_lock(game_id):
    with _game_locks_guard:
        return _game_locks.setdefault(game_id, threading.Lock())


@bp.route("/games/<string:game_id>/actions", methods=["POST"])
def post_action_endpoint(game_id):
    """Play the bot's move (empty body) or the posted one.

    409 ``game_busy`` while another move of this game is being played, and 409
    ``stale_game`` if the game moved on while this one was being decided (e.g.
    another server process); the game is left as the other request saved it.
    """
    lock = _game_lock(game_id)
    if not lock.acquire(blocking=False):
        return _json_error(
            409, "game_busy", "Another move of this game is being played"
        )
    try:
        return _post_action(game_id)
    except StaleGameError as error:
        return _json_error(409, "stale_game", str(error))
    finally:
        lock.release()


def _post_action(game_id):
    import uuid
    from catanatron.web.sandbox import (
        ensure_in_variation_tree,
        get_game_state_safe,
        make_forced_action_record,
        overwrite_stored_game_as_base,
        push_sandbox_history,
        record_snapshot,
    )

    req_json = request.get_json(silent=True)
    body_is_empty = (not request.data) or req_json is None or req_json == {}
    payload = req_json
    forced = None
    from_state_index = None
    if isinstance(payload, dict) and ("action" in payload or "from_state_index" in payload):
        forced = payload.get("forced")
        from_state_index = payload.get("from_state_index")
        payload = payload.get("action")
        body_is_empty = payload is None

    latest_game = get_game_state_safe(game_id)
    if latest_game is None:
        abort(404, description="Resource not found")
    latest_index = get_state_index(latest_game.state)

    # Lichess-style auto-branch: if the user is viewing an earlier state in history
    # and plays a move (or clicks Bot Move), automatically fork a new variation branch!
    is_forking = (
        from_state_index is not None
        and int(from_state_index) < latest_index
    )
    if is_forking:
        fork_idx = int(from_state_index)
        game = get_game_state_safe(game_id, fork_idx)
        parent_id = game_id
        game.id = str(uuid.uuid4())
        # In a forked variation, allow human control on both sides so user can explore freely
        specs = [{"key": "HUMAN", "params": {}} for _ in game.state.colors]
        game.state.players = [
            REGISTRY.build(spec, color)
            for spec, color in zip(specs, game.state.colors)
        ]
        overwrite_stored_game_as_base(game, specs)
        record_snapshot(game)
        loaded_index = get_state_index(game.state)
    else:
        game = latest_game
        loaded_index = latest_index
        if game.winning_color() is not None:
            return _game_response(game)
        push_sandbox_history(game.id)
        record_snapshot(game)

    if game.state.current_player().is_bot or body_is_empty:
        if game.state.current_player().is_bot:
            record = game.play_tick()
        else:
            bot_key = "BOBCAT" if "BOBCAT" in REGISTRY else "AB"
            bot = REGISTRY.build(bot_key, game.state.current_color())
            action = bot.decide(game, game.playable_actions)
            record = game.execute(action)
        upsert_game_state(game, expected_index=loaded_index)
        record_snapshot(game)
    else:
        try:
            action = action_from_json(payload)
        except (KeyError, ValueError, TypeError, IndexError) as error:
            return _action_error("invalid_action", f"Malformed action: {error}")
        try:
            forced_rec = make_forced_action_record(game, action, forced)
            record = game.execute(action, action_record=forced_rec)
        except ValueError as error:
            return _action_error(
                "illegal_action", f"Action not allowed in the current game state: {error}"
            )
        upsert_game_state(game, expected_index=loaded_index)
        record_snapshot(game)

    if is_forking:
        act_label = f"#{fork_idx + 1} {record.action.color.value} {record.action.action_type.value}"
        ensure_in_variation_tree(game, parent_id=parent_id, fork_index=fork_idx, label=act_label)

    return _game_response(game)


@bp.route("/stress-test", methods=["GET"])
def stress_test_endpoint():
    params = AlphaBetaPlayer.Params(depth=2, prunning=True)
    players = [AlphaBetaPlayer(color, params) for color in Color]
    game = Game(players=players)
    game.play_tick()
    return Response(
        response=json.dumps(web_view(game)),
        status=200,
        mimetype="application/json",
    )


@bp.route(
    "/games/<string:game_id>/states/<string:state_index>/analysis", methods=["GET"]
)
def analysis_endpoint(game_id, state_index):
    """Analyze a position with the server's engine (``create_app(analyzer=...)``).

    The analyzer is called as ``analyzer(game, hidden=[...])`` with a copy of
    the game and the colors whose development cards the caller cannot see --
    the same rule as the state view: the bots while a human plays them, none
    once the game is over (``?as=`` does not change it). The analyzer may use
    only what the other seats see: it must not read a hidden seat's cards.
    It returns::

        {
            "engine": "Bobcat az_v1_gen14 · MCTS 1000",   # label for the UI
            "player": "RED",                  # the seat to decide
            "win_probability": {"RED": 0.62, "BLUE": 0.38},
            "simulations": 1000, "seconds": 2.1,
            "moves": [                        # every legal action, best first
                {
                    "action": ["RED", "BUILD_ROAD", [6, 7]],
                    "probability": 0.41,      # the engine's choice (e.g. visit share)
                    "prior": 0.35,            # the policy before searching, or null
                    "visits": 410,
                    "win_probability": {...}, # after this move, or null if unexplored
                    "line": [action, ...],    # expected continuation, the move first
                    "line_end": "chance",     # why it stops: chance, terminal,
                                              # unexplored, or null (depth reached)
                    "line_assumptions": [     # optional: where the line assumes a
                        {"step": 3, "color": "BLUE",  # hidden hand, and which
                         "hand": ["KNIGHT"], "probability": 0.31},
                    ],
                },
            ],
            "opponent_cards": [               # optional: the engine's guess at
                {"color": "BLUE", "count": 2, # each hidden hand
                 "expected": {"KNIGHT": 1.1, ...},
                 "at_least_one": {"KNIGHT": 0.74, ...},
                 "likely_hand": ["KNIGHT", "VICTORY_POINT"],
                 "likely_hand_probability": 0.31},
            ],
            "averaged_over_hands": True,      # optional: a hidden seat to move,
        }                                     # its moves averaged over its hands

    Optional ``"mode"`` (absent or ``"mcts"``: the format above) switches the
    moves to another shape, which the UI draws instead of lines:

    - ``"turn"`` -- a plan of the whole turn after the roll. Each move is
      ``{"action", "win_probability", "prior", "best", "excluded", "plan"}``;
      a plan is ``{"steps": [action, ...], "end": ...}`` with the best actions
      up to the end of the turn or the next random event. ``end`` is
      ``{"type": "end_turn" | "terminal", "win_probability", "refined"?,
      "sims"?}``, ``{"type": "truncated"}`` or ``{"type": "chance",
      "action", "outcomes": [{"result", "probability", "win_probability",
      "plan"}, ...]}`` (the card drawn or resource stolen, likeliest first).
      Also ``"turn_stats"`` and, for a hidden seat, ``"assumed_hand"``.
    - ``"discard"`` -- every set of cards to discard:
      ``{"discard": {"WOOD": 2, ...}, "win_probability", "best"}``.

    ``"turn_fallback": True`` marks a regular analysis where a turn plan was
    too large. The endpoint adds ``state_index``. A finished game is not sent to the
    analyzer. Errors: 404 unknown game, 501 no analyzer, 400 the analyzer
    raised ValueError (e.g. an unsupported number of players), 500 otherwise.
    """
    from catanatron.web.sandbox import get_game_state_safe
    parsed_state_index = _parse_state_index(state_index)
    game = get_game_state_safe(game_id, parsed_state_index)
    if game is None:
        abort(404, description="Game state not found")
    analyzer = current_app.config.get("ANALYZER")
    if analyzer is None:
        return _json_error(501, "no_analyzer", "This server has no analysis engine")

    winner = game.winning_color()
    if winner is not None:
        analysis = {
            "engine": None,
            "player": None,
            "win_probability": {
                c.value: 1.0 if c == winner else 0.0 for c in game.state.colors
            },
            "simulations": 0,
            "seconds": 0.0,
            "moves": [],
        }
    else:
        latest = game if parsed_state_index is None else get_game_state(game_id)
        hidden = [] if is_over(latest) else [c.value for c in _face_down(game)]
        try:
            analysis = analyzer(game.copy(), hidden=hidden)
        except ValueError as error:
            return _json_error(400, "unsupported", str(error))
        except Exception as error:  # the engine is outside this package
            logging.exception("Analysis of %s/%s failed", game_id, state_index)
            return _json_error(500, "analysis_failed", str(error))

    analysis["state_index"] = len(game.state.action_records)
    return jsonify(analysis)


#: Actions whose effect on the hands everybody at the table sees: what a roll
#: pays out and what a monopoly takes. A steal or a discard is private.
PUBLIC_RESOURCE_CHANGES = {ActionType.ROLL, ActionType.PLAY_MONOPOLY}


def _game_response(game, latest=None):
    """The web view of a stored game, plus when it was created and, aligned
    with ``action_records``, ``action_details``: when each action was played
    (Unix time, seconds, or null) and, for a roll or a monopoly, how it changed
    the hands (``{"RED": {"WHEAT": 2}}``, or null where unknown).

    ``latest`` is the game's latest state when ``game`` is an earlier one.
    Until the game is over, a human at the table sees only how many
    development cards the bots hold; after it, every state shows every hand
    (the perspective, ``?as=``, no longer applies).
    """
    over = is_over(latest or game)
    face_down = [] if over else _face_down(game)
    perspective = None if over else _perspective(game)
    view = web_view(game, perspective, face_down)
    history = get_action_details(game.id, len(game.state.action_records))
    for record, details in zip(game.state.action_records, history["action_details"]):
        if record.action.action_type not in PUBLIC_RESOURCE_CHANGES:
            details["resource_changes"] = None
    from catanatron.web.sandbox import get_variation_tree
    view.update(history)
    view["variations"] = get_variation_tree(game.id)
    return Response(
        response=json.dumps(view),
        status=200,
        mimetype="application/json",
    )


def _json_error(status, error, message):
    return Response(
        response=json.dumps({"error": error, "message": message}),
        status=status,
        mimetype="application/json",
    )


def _action_error(error, message):
    """400 for an action the game cannot take; the game is left as it was."""
    return Response(
        response=json.dumps(
            {"error": error, "message": message, "action": request.json}
        ),
        status=400,
        mimetype="application/json",
    )


def _face_down(game):
    """Seats whose development cards a human at the table may not see: the
    bots, while somebody is playing against them."""
    players = game.state.players
    if all(player.is_bot for player in players):
        return []
    return [player.color for player in players if player.is_bot]


def _perspective(game):
    """The seat whose eyes to see the table through, from ``?as=RED``.

    Without it the browser gets the spectator's view, which is every hand
    face up. This is a display mode, not a secret: the client picks it.
    """
    color = request.args.get("as")
    if color is None:
        return None
    seated = [c.value for c in game.state.colors]
    if color.upper() not in seated:
        abort(400, description=f"'as' must be one of {', '.join(seated)}")
    return color.upper()


def _parse_state_index(state_index_str: str):
    """Helper function to parse and validate state_index."""
    if state_index_str == "latest":
        return None
    try:
        return int(state_index_str)
    except ValueError:
        abort(
            400,
            description="Invalid state_index format. state_index must be an integer or 'latest'.",
        )


# ===== Debugging Routes
# @app.route(
#     "/games/<string:game_id>/players/<int:player_index>/features", methods=["GET"]
# )
# def get_game_feature_vector(game_id, player_index):
#     game = get_game_state(game_id)
#     if game is None:
#         abort(404, description="Resource not found")

#     return create_sample(game, game.state.colors[player_index])


# @app.route("/games/<string:game_id>/value-function", methods=["GET"])
# def get_game_value_function(game_id):
#     game = get_game_state(game_id)
#     if game is None:
#         abort(404, description="Resource not found")

#     # model = tf.keras.models.load_model("data/models/mcts-rep-a")
#     model2 = tf.keras.models.load_model("data/models/mcts-rep-b")
#     feature_ordering = get_feature_ordering()
#     indices = [feature_ordering.index(f) for f in NUMERIC_FEATURES]
#     data = {}
#     for color in game.state.colors:
#         sample = create_sample_vector(game, color)
#         # scores = model.call(tf.convert_to_tensor([sample]))

#         inputs1 = [create_board_tensor(game, color)]
#         inputs2 = [[float(sample[i]) for i in indices]]
#         scores2 = model2.call(
#             [tf.convert_to_tensor(inputs1), tf.convert_to_tensor(inputs2)]
#         )
#         data[color.value] = float(scores2.numpy()[0][0])

#     return data


@bp.route("/games", methods=("GET",))
def list_games_endpoint():
    from catanatron.web.models import StoredGame, db
    rows = (
        db.session.query(StoredGame)
        .order_by(StoredGame.created_at.desc())
        .limit(25)
        .all()
    )
    items = []
    for row in rows:
        try:
            head = json.loads(row.head_state)
            specs = json.loads(row.player_specs)
            colors = head.get("colors", ["RED", "BLUE"])
            vps = {
                c: head.get("player_state", {}).get(f"P{i}_ACTUAL_VICTORY_POINTS", 0)
                for i, c in enumerate(colors)
            }
            items.append(
                {
                    "game_id": row.uuid,
                    "created_at": row.created_at,
                    "state_index": row.head_index,
                    "num_turns": head.get("num_turns", 0),
                    "colors": colors,
                    "players": [s.get("key", "HUMAN") for s in specs],
                    "vps": vps,
                }
            )
        except Exception:
            continue
    return jsonify(items)


@bp.route("/games/<string:game_id>/export", methods=("GET",))
def export_game_endpoint(game_id):
    from catanatron.serialization import state_to_json
    from catanatron.web.models import StoredGame, db
    from catanatron.web.sandbox import get_game_state_safe
    state_index = request.args.get("state_index", "latest")
    parsed_index = _parse_state_index(state_index)
    game = get_game_state_safe(game_id, parsed_index)
    if game is None:
        abort(404, description="Game not found")
    stored = db.session.get(StoredGame, game_id)
    doc = state_to_json(game)
    doc["player_specs"] = (
        json.loads(stored.player_specs)
        if stored
        else [REGISTRY.spec_of(p) for p in game.state.players]
    )
    return jsonify(doc)


@bp.route("/games/import", methods=("POST",))
def import_game_endpoint():
    import uuid
    from catanatron.serialization import state_from_json
    from catanatron.web.sandbox import overwrite_stored_game_as_base

    req_json = request.get_json(silent=True)
    if not isinstance(req_json, dict):
        abort(400, description="Expected a game JSON document")
    doc = dict(req_json)
    play_both_sides = bool(doc.pop("play_both_sides", True))
    if "game" not in doc or "colors" not in doc:
        abort(400, description="Invalid game JSON document")
    doc["game"] = dict(doc["game"])
    doc["game"]["id"] = str(uuid.uuid4())
    colors = [Color[c] for c in doc["colors"]]
    if play_both_sides:
        specs = [{"key": "HUMAN", "params": {}} for _ in colors]
    else:
        specs = doc.get("player_specs") or [{"key": "HUMAN", "params": {}} for _ in colors]
    players = [REGISTRY.build(spec, color) for spec, color in zip(specs, colors)]
    try:
        game = state_from_json(doc, players)
    except Exception as error:
        abort(400, description=f"Could not import game: {error}")
    overwrite_stored_game_as_base(game, specs)
    return jsonify({"game_id": game.id})


@bp.route("/games/<string:game_id>/branch", methods=("POST",))
def branch_game_endpoint(game_id):
    import uuid
    from catanatron.web.sandbox import (
        ensure_in_variation_tree,
        get_game_state_safe,
        overwrite_stored_game_as_base,
        overwrite_stored_game_head_only,
        pop_sandbox_history,
        push_sandbox_history,
    )

    body = request.get_json(silent=True) or {}
    if body.get("undo"):
        game = pop_sandbox_history(game_id)
        if game is None:
            abort(404, description="Game not found")
        return _game_response(game)

    state_index = body.get("state_index", "latest")
    in_place = bool(body.get("in_place", False))
    play_both_sides = bool(body.get("play_both_sides", True))
    parsed_index = _parse_state_index(str(state_index))

    game = get_game_state_safe(game_id, parsed_index)
    if game is None:
        abort(404, description="Game state not found")

    if play_both_sides:
        specs = [{"key": "HUMAN", "params": {}} for _ in game.state.colors]
        game.state.players = [
            REGISTRY.build(spec, color)
            for spec, color in zip(specs, game.state.colors)
        ]
    else:
        specs = [REGISTRY.spec_of(p) for p in game.state.players]

    fork_idx = get_state_index(game.state)
    if in_place:
        push_sandbox_history(game_id)
        overwrite_stored_game_head_only(game, specs)
    else:
        parent_id = game_id
        game.id = str(uuid.uuid4())
        overwrite_stored_game_as_base(game, specs)
        ensure_in_variation_tree(game, parent_id=parent_id, fork_index=fork_idx)
    return _game_response(game)


@bp.route("/games/<string:game_id>/edit", methods=("POST",))
def edit_game_endpoint(game_id):
    from catanatron.web.sandbox import apply_sandbox_edit, get_game_state_safe

    req_json = request.get_json(silent=True)
    if not isinstance(req_json, dict):
        abort(400, description="Missing edit payload")
    lock = _game_lock(game_id)
    with lock:
        game = get_game_state_safe(game_id)
        if game is None:
            abort(404, description="Game not found")
        try:
            apply_sandbox_edit(game, req_json)
        except Exception as error:
            return _action_error("edit_failed", str(error))
        return _game_response(game)
