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
    upsert_game_state(game)
    return jsonify({"game_id": game.id})


@bp.route("/games/<string:game_id>/states/<string:state_index>", methods=("GET",))
def get_game_endpoint(game_id, state_index):
    parsed_state_index = _parse_state_index(state_index)
    game = get_game_state(game_id, parsed_state_index)
    if game is None:
        abort(404, description="Resource not found")
    if parsed_state_index is None:
        return _game_response(game)
    return _game_response(game, latest=get_game_state(game_id))


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
    game = get_game_state(game_id)
    if game is None:
        abort(404, description="Resource not found")
    loaded_index = get_state_index(game.state)

    if game.winning_color() is not None:
        return _game_response(game)

    # TODO: remove `or body_is_empty` when fully implement actions in FE
    body_is_empty = (not request.data) or request.json is None or request.json == {}
    if game.state.current_player().is_bot or body_is_empty:
        game.play_tick()
        upsert_game_state(game, expected_index=loaded_index)
    else:
        try:
            action = action_from_json(request.json)
        except (KeyError, ValueError, TypeError, IndexError) as error:
            return _action_error("invalid_action", f"Malformed action: {error}")
        try:
            game.execute(action)
        except ValueError:
            return _action_error(
                "illegal_action", "Action not allowed in the current game state"
            )
        upsert_game_state(game, expected_index=loaded_index)

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
    parsed_state_index = _parse_state_index(state_index)
    game = get_game_state(game_id, parsed_state_index)
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
    view.update(history)
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
