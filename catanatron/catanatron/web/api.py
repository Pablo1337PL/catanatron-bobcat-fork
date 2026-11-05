import json
import logging
import random
import traceback

from flask import Response, Blueprint, current_app, jsonify, abort, request

from catanatron.web.models import upsert_game_state, get_game_state
from catanatron.serialization import action_from_json, web_view
from catanatron.models.player import Color
from catanatron.game import Game
from catanatron.models.map import build_map
from catanatron.players.minimax import AlphaBetaPlayer
from catanatron.registry import REGISTRY, describe, SpecError
from catanatron.web.players import register_web_players
from catanatron.web.mcts_analysis import GameAnalyzer

bp = Blueprint("api", __name__, url_prefix="/api")
VALID_MAP_TEMPLATES = {"BASE", "MINI", "TOURNAMENT"}

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
    ``seed``, ``board_seed``, ``dice_seed`` (int >= 0 or null; a missing board
    or dice seed is drawn at random, so every game can be replayed).
    """
    if not request.is_json or request.json is None or "players" not in request.json:
        abort(400, description="Missing or invalid JSON body: 'players' key required")

    player_keys = request.json["players"]
    if not isinstance(player_keys, list) or not 2 <= len(player_keys) <= 4:
        abort(400, description="'players' must be a list with 2 to 4 entries")

    map_template = _setting("map_template") or "BASE"
    if map_template not in VALID_MAP_TEMPLATES:
        abort(
            400,
            description="'map_template' must be one of BASE, MINI, or TOURNAMENT",
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

    payload = json.dumps(web_view(game, _perspective(game)))
    return Response(
        response=payload,
        status=200,
        mimetype="application/json",
    )


@bp.route("/games/<string:game_id>/actions", methods=["POST"])
def post_action_endpoint(game_id):
    game = get_game_state(game_id)
    if game is None:
        abort(404, description="Resource not found")

    if game.winning_color() is not None:
        return Response(
            response=json.dumps(web_view(game, _perspective(game))),
            status=200,
            mimetype="application/json",
        )

    # TODO: remove `or body_is_empty` when fully implement actions in FE
    body_is_empty = (not request.data) or request.json is None or request.json == {}
    if game.state.current_player().is_bot or body_is_empty:
        game.play_tick()
        upsert_game_state(game)
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
        upsert_game_state(game)

    return Response(
        response=json.dumps(web_view(game, _perspective(game))),
        status=200,
        mimetype="application/json",
    )


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
    "/games/<string:game_id>/states/<string:state_index>/mcts-analysis", methods=["GET"]
)
def mcts_analysis_endpoint(game_id, state_index):
    """Get MCTS analysis for specific game state."""
    logging.info(f"MCTS analysis request for game {game_id} at state {state_index}")

    # Convert 'latest' to None for consistency with get_game_state
    parsed_state_index = _parse_state_index(state_index)
    try:
        game = get_game_state(game_id, parsed_state_index)
        if game is None:
            logging.error(
                f"Game/state not found: {game_id}/{state_index}"
            )  # Use original state_index for logging
            abort(404, description="Game state not found")

        analyzer = GameAnalyzer(num_simulations=100)
        probabilities = analyzer.analyze_win_probabilities(game)

        logging.info(f"Analysis successful. Probabilities: {probabilities}")
        return Response(
            response=json.dumps(
                {
                    "success": True,
                    "probabilities": probabilities,
                    "state_index": (
                        parsed_state_index
                        if parsed_state_index is not None
                        else len(game.state.action_records)
                    ),
                }
            ),
            status=200,
            mimetype="application/json",
        )

    except Exception as e:
        logging.error(f"Error in MCTS analysis endpoint: {str(e)}")
        logging.error(traceback.format_exc())
        return Response(
            response=json.dumps(
                {"success": False, "error": str(e), "trace": traceback.format_exc()}
            ),
            status=500,
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
