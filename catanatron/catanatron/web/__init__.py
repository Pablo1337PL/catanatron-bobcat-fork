import os

from flask import Flask
from flask_cors import CORS


def create_app(test_config=None, game_defaults=None, forced_rules=None, analyzer=None):
    """Create and configure an instance of the Flask application.

    Args:
        test_config (dict, optional): Flask config overrides.
        game_defaults (dict, optional): Settings of new games when a request
            leaves them out, e.g. ``{"board_seed": 100, "dice_seed": 7}`` or
            rules (``vps_to_win``, ``discard_limit``, ``friendly_robber``,
            ``map_template``, ``random_seats``, ``seed``).
        forced_rules (dict, optional): Rules every new game gets regardless of
            the request, e.g. ``{"vps_to_win": 15, "discard_limit": 9,
            "friendly_robber": True}``.
        analyzer (callable, optional): The engine behind
            ``GET /api/games/<id>/states/<index>/analysis``: called with a
            copy of the game, returns the analysis document described in
            :func:`catanatron.web.api.analysis_endpoint`. It may raise
            ValueError for a position it cannot analyze. Without it the
            endpoint answers 501.
    """
    app = Flask(__name__)
    CORS(app)

    # ===== Load base configuration
    database_url = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    secret_key = os.environ.get("SECRET_KEY", "dev")
    app.config.from_mapping(
        SECRET_KEY=secret_key,
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    app.config["GAME_DEFAULTS"] = dict(game_defaults or {})
    app.config["FORCED_RULES"] = dict(forced_rules or {})
    app.config["ANALYZER"] = analyzer
    if test_config is not None:
        app.config.update(test_config)

    # ===== Initialize Database
    from catanatron.web.models import db

    with app.app_context():
        db.init_app(app)
        db.create_all()

    # ===== Initialize Routes
    from . import api

    app.register_blueprint(api.bp)

    return app
