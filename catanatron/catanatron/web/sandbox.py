"""Sandbox / Analysis Board backend helpers, timeline snapshots, and variation tree."""

import json
import time
import uuid
from collections import defaultdict

from catanatron.game import Game
from catanatron.models.actions import generate_playable_actions
from catanatron.models.board import STATIC_GRAPH
from catanatron.models.decks import starting_resource_bank
from catanatron.models.enums import (
    CITY,
    DEVELOPMENT_CARDS,
    RESOURCES,
    SETTLEMENT,
    ActionPrompt,
    ActionRecord,
    ActionType,
)
from catanatron.models.map import LandTile, Port
from catanatron.models.player import Color
from catanatron.registry import REGISTRY
from catanatron.serialization import (
    SCHEMA_VERSION,
    map_from_json,
    map_to_json,
    state_from_json,
    state_to_json,
)
from catanatron.state_functions import get_state_index, player_key
from catanatron.web.models import StoredAction, StoredGame, db

# Per-game full state snapshots by state_index so jumping to ANY state_index (0..head)
# always works even after board/hand edits!
_STATE_SNAPSHOTS: dict[str, dict[int, str]] = defaultdict(dict)

# Undo stack per game_id: list of (state_json_str, player_specs_json_str)
_SANDBOX_HISTORY: dict[str, list[tuple[str, str]]] = defaultdict(list)

# Variation tree per root_game_id:
# { root_id: [ { "game_id": str, "parent_id": str | None, "fork_index": int, "label": str, "created_at": float } ] }
_VARIATION_TREES: dict[str, list[dict]] = defaultdict(list)
_GAME_TO_ROOT: dict[str, str] = {}


def record_snapshot(game: Game):
    """Store authoritative JSON snapshot for (game.id, state_index)."""
    idx = get_state_index(game.state)
    _STATE_SNAPSHOTS[game.id][idx] = json.dumps(state_to_json(game))


def ensure_in_variation_tree(game: Game, parent_id: str | None = None, fork_index: int = 0, label: str | None = None):
    """Register a game in its variation tree. If parent_id is given, always attach to parent's root tree!"""
    gid = game.id
    if parent_id is not None:
        root_id = _GAME_TO_ROOT.get(parent_id, parent_id)
        _GAME_TO_ROOT[parent_id] = root_id
        # If gid was mistakenly registered as its own root before parent_id was passed, merge it:
        if _GAME_TO_ROOT.get(gid) == gid and gid != root_id:
            _VARIATION_TREES.pop(gid, None)
        _GAME_TO_ROOT[gid] = root_id
    else:
        if gid in _GAME_TO_ROOT:
            return _GAME_TO_ROOT[gid]
        root_id = gid
        _GAME_TO_ROOT[gid] = root_id

    tree = _VARIATION_TREES[root_id]
    if not any(node["game_id"] == root_id for node in tree):
        tree.append({
            "game_id": root_id,
            "parent_id": None,
            "fork_index": 0,
            "label": "Mainline",
            "created_at": time.time(),
        })
    if gid != root_id:
        existing = next((node for node in tree if node["game_id"] == gid), None)
        var_num = len(tree)
        if existing is None:
            tree.append({
                "game_id": gid,
                "parent_id": parent_id,
                "fork_index": fork_index,
                "label": label or f"Var {var_num} (from #{fork_index})",
                "created_at": time.time(),
            })
        elif label:
            existing["label"] = label
    return root_id


def get_variation_tree(game_id: str) -> list[dict]:
    """Return all variations belonging to the same tree as game_id."""
    root_id = _GAME_TO_ROOT.get(game_id, game_id)
    tree = _VARIATION_TREES.get(root_id, [])
    if not tree:
        return [{
            "game_id": game_id,
            "parent_id": None,
            "fork_index": 0,
            "label": "Mainline",
            "head_index": 0,
            "active": True,
        }]
    result = []
    for node in tree:
        stored = db.session.get(StoredGame, node["game_id"])
        head_idx = stored.head_index if stored else node["fork_index"]
        last_move = None
        if stored and head_idx > 0:
            try:
                doc = json.loads(stored.head_state)
                recs = doc.get("action_records", [])
                if recs:
                    act = recs[-1][0]
                    last_move = f"{act[0]} {act[1]}"
            except Exception:
                pass
        result.append({
            **node,
            "head_index": head_idx,
            "last_move": last_move,
            "active": node["game_id"] == game_id,
        })
    return result


def get_game_state_safe(game_id: str, state_index: int | None = None) -> Game | None:
    """Materialize a game at state_index, falling back to _STATE_SNAPSHOTS or replaying from 0
    when base_index was shifted by sandbox edits."""
    from catanatron.web.models import get_game_state
    stored = db.session.get(StoredGame, game_id)
    if stored is None:
        return None
    target = stored.head_index if state_index is None else int(state_index)
    target = max(0, min(target, stored.head_index))

    # 1. Check in-memory exact snapshot first
    snap_str = _STATE_SNAPSHOTS.get(game_id, {}).get(target)
    if snap_str is not None:
        doc = json.loads(snap_str)
        specs = json.loads(stored.player_specs)
        colors = [Color[c] for c in doc["colors"]]
        players = [REGISTRY.build(spec, color) for spec, color in zip(specs, colors)]
        return state_from_json(doc, players)

    # 2. If target >= stored.base_index, standard get_game_state works
    if target >= stored.base_index:
        try:
            game = get_game_state(game_id, target)
            record_snapshot(game)
            return game
        except Exception:
            pass

    # 3. Fallback: truncate action_records on head_state to show earlier move position
    doc = json.loads(stored.head_state)
    doc["action_records"] = doc.get("action_records", [])[:target]
    specs = json.loads(stored.player_specs)
    colors = [Color[c] for c in doc["colors"]]
    players = [REGISTRY.build(spec, color) for spec, color in zip(specs, colors)]
    return state_from_json(doc, players)


def push_sandbox_history(game_id: str):
    """Snapshot current head_state before an edit or move so Undo always works."""
    stored = db.session.get(StoredGame, game_id)
    if stored is not None:
        stack = _SANDBOX_HISTORY[game_id]
        if not stack or stack[-1][0] != stored.head_state:
            stack.append((stored.head_state, stored.player_specs))
            if len(stack) > 150:
                stack.pop(0)


def pop_sandbox_history(game_id: str) -> Game | None:
    """Restore the previous state from _SANDBOX_HISTORY or step back 1 action."""
    stored = db.session.get(StoredGame, game_id, populate_existing=True)
    if stored is None:
        return None

    stack = _SANDBOX_HISTORY.get(game_id)
    if stack:
        prev_doc_str, prev_specs_str = stack.pop()
        doc = json.loads(prev_doc_str)
        specs = json.loads(prev_specs_str)
        colors = [Color[c] for c in doc["colors"]]
        players = [REGISTRY.build(spec, color) for spec, color in zip(specs, colors)]
        game = state_from_json(doc, players)
        overwrite_stored_game_head_only(game, specs)
        record_snapshot(game)
        return game

    if stored.head_index > 0:
        target = stored.head_index - 1
        game = get_game_state_safe(game_id, target)
        if game is not None:
            specs = json.loads(stored.player_specs)
            overwrite_stored_game_head_only(game, specs)
            return game

    return get_game_state_safe(game_id)


def overwrite_stored_game_head_only(game: Game, player_specs: list | None = None):
    """Rewind or update head_index/head_state while keeping base_index intact if possible."""
    session = db.session
    head = get_state_index(game.state)
    document = json.dumps(state_to_json(game))
    stored = session.get(StoredGame, game.id, populate_existing=True)
    if stored is None:
        return overwrite_stored_game_as_base(game, player_specs)
    if player_specs is None:
        player_specs = [REGISTRY.spec_of(p) for p in game.state.players]
    session.query(StoredAction).filter(
        StoredAction.uuid == game.id,
        StoredAction.index >= head,
    ).delete(synchronize_session=False)
    stored.player_specs = json.dumps(player_specs)
    if head < stored.base_index:
        stored.base_index = head
        stored.base_state = document
    stored.head_index = head
    stored.head_state = document
    session.commit()
    record_snapshot(game)
    return stored


def overwrite_stored_game_as_base(game: Game, player_specs: list | None = None):
    """Save an edited or branched game state in DB."""
    session = db.session
    now = time.time()
    head = get_state_index(game.state)
    document = json.dumps(state_to_json(game))
    stored = session.get(StoredGame, game.id, populate_existing=True)

    if player_specs is None:
        player_specs = [REGISTRY.spec_of(p) for p in game.state.players]

    if stored is None:
        stored = StoredGame(
            uuid=game.id,
            schema_version=SCHEMA_VERSION,
            player_specs=json.dumps(player_specs),
            base_index=head,
            base_state=document,
            head_index=head,
            head_state=document,
            created_at=now,
        )
        session.add(stored)
    else:
        session.query(StoredAction).filter(
            StoredAction.uuid == game.id,
            StoredAction.index >= head,
        ).delete(synchronize_session=False)
        stored.player_specs = json.dumps(player_specs)
        stored.base_index = head
        stored.base_state = document
        stored.head_index = head
        stored.head_state = document
    session.commit()
    record_snapshot(game)
    ensure_in_variation_tree(game)
    return stored


def sum_to_dices(total: int) -> tuple[int, int]:
    total = int(total)
    if not 2 <= total <= 12:
        raise ValueError("Dice sum must be between 2 and 12")
    d1 = max(1, min(6, total - 1))
    d2 = total - d1
    if not (1 <= d1 <= 6 and 1 <= d2 <= 6):
        d1 = 6
        d2 = total - 6
    return (d1, d2)


def make_forced_action_record(game: Game, action, forced: dict | None) -> ActionRecord | None:
    if not forced:
        return None
    s = game.state
    if action.action_type == ActionType.ROLL and forced.get("dice") is not None:
        dice_val = forced["dice"]
        if isinstance(dice_val, (list, tuple)) and len(dice_val) == 2:
            dices = (int(dice_val[0]), int(dice_val[1]))
        else:
            dices = sum_to_dices(int(dice_val))
        return ActionRecord(action=action, result=dices)

    if action.action_type == ActionType.BUY_DEVELOPMENT_CARD and forced.get("dev_card"):
        card = str(forced["dev_card"]).upper()
        if card not in DEVELOPMENT_CARDS:
            raise ValueError(f"Unknown development card: {card}")
        if card not in s.development_listdeck:
            s.development_listdeck.append(card)
        return ActionRecord(action=action, result=card)

    if action.action_type == ActionType.MOVE_ROBBER and forced.get("robber_resource"):
        res = str(forced["robber_resource"]).upper()
        _, victim = action.value
        if victim is not None and res in RESOURCES:
            vkey = player_key(s, victim)
            if s.player_state.get(f"{vkey}_{res}_IN_HAND", 0) > 0:
                return ActionRecord(action=action, result=res)
    return None


def rebuild_board_caches_and_vps(game: Game):
    s = game.state
    board = s.board

    s.buildings_by_color = {c: defaultdict(list) for c in s.colors}
    board.board_buildable_ids = set(board.map.land_nodes)

    for node_id, (color, btype) in list(board.buildings.items()):
        s.buildings_by_color[color][btype].append(node_id)
        board.board_buildable_ids.discard(node_id)
        for nbr in STATIC_GRAPH.neighbors(node_id):
            board.board_buildable_ids.discard(nbr)

    clean_roads = {}
    for edge, color in list(board.roads.items()):
        a, b = int(edge[0]), int(edge[1])
        clean_roads[(a, b)] = color
        clean_roads[(b, a)] = color
        s.buildings_by_color[color]["ROAD"].append(tuple(sorted((a, b))))
    for color in s.colors:
        s.buildings_by_color[color]["ROAD"] = sorted(
            list(set(s.buildings_by_color[color]["ROAD"]))
        )
    board.roads = clean_roads

    board.connected_components = defaultdict(list)
    for color in s.colors:
        owned_nodes = set(
            s.buildings_by_color[color][SETTLEMENT] + s.buildings_by_color[color][CITY]
        )
        road_edges = [
            (a, b) for (a, b), c in board.roads.items() if c == color and a < b
        ]
        road_nodes = set()
        for a, b in road_edges:
            road_nodes.add(a)
            road_nodes.add(b)
        start_nodes = owned_nodes | road_nodes
        visited_global = set()
        for start in start_nodes:
            if start in visited_global:
                continue
            if board.is_enemy_node(start, color) and start not in owned_nodes:
                continue
            comp = board.dfs_walk(start, color)
            if comp:
                board.connected_components[color].append(comp)
                visited_global.update(comp)

    board.road_lengths = defaultdict(int)
    for color in s.colors:
        board._recompute_road_length(color)
    board._reassign_longest_road()

    board.buildable_edges_cache = {}
    board.player_port_resources_cache = {}

    army_color = None
    for i, color in enumerate(s.colors):
        if s.player_state.get(f"P{i}_HAS_ARMY"):
            army_color = color
    knights_by_color = {
        color: s.player_state.get(f"P{i}_PLAYED_KNIGHT", 0)
        for i, color in enumerate(s.colors)
    }
    max_k = max(knights_by_color.values(), default=0)
    leaders = [c for c, k in knights_by_color.items() if k == max_k and k >= 3]
    if not leaders:
        army_color = None
    elif army_color in leaders:
        pass
    elif len(leaders) == 1:
        army_color = leaders[0]
    else:
        army_color = None

    bank_res = starting_resource_bank()
    for i, color in enumerate(s.colors):
        prefix = f"P{i}_"
        num_settle = len(s.buildings_by_color[color][SETTLEMENT])
        num_city = len(s.buildings_by_color[color][CITY])
        num_road = len(s.buildings_by_color[color]["ROAD"])

        s.player_state[prefix + "SETTLEMENTS_AVAILABLE"] = max(0, 5 - num_settle)
        s.player_state[prefix + "CITIES_AVAILABLE"] = max(0, 4 - num_city)
        s.player_state[prefix + "ROADS_AVAILABLE"] = max(0, 15 - num_road)

        has_road = board.road_color == color
        has_army = army_color == color
        s.player_state[prefix + "HAS_ROAD"] = has_road
        s.player_state[prefix + "HAS_ARMY"] = has_army
        s.player_state[prefix + "LONGEST_ROAD_LENGTH"] = board.road_lengths.get(color, 0)

        visible_vp = (
            num_settle
            + 2 * num_city
            + (2 if has_road else 0)
            + (2 if has_army else 0)
        )
        vp_cards = s.player_state.get(
            prefix + "VICTORY_POINT_IN_HAND", 0
        ) + s.player_state.get(prefix + "PLAYED_VICTORY_POINT", 0)
        s.player_state[prefix + "VICTORY_POINTS"] = visible_vp
        s.player_state[prefix + "ACTUAL_VICTORY_POINTS"] = visible_vp + vp_cards

        for r_idx, res in enumerate(RESOURCES):
            in_hand = max(0, int(s.player_state.get(f"{prefix}{res}_IN_HAND", 0)))
            s.player_state[f"{prefix}{res}_IN_HAND"] = in_hand
            bank_res[r_idx] = max(0, bank_res[r_idx] - in_hand)

        for card in DEVELOPMENT_CARDS:
            if card != "VICTORY_POINT":
                s.player_state[f"{prefix}{card}_OWNED_AT_START"] = (
                    s.player_state.get(f"{prefix}{card}_IN_HAND", 0) > 0
                )

    s.resource_freqdeck = bank_res
    # If in initial build phase but a player already has >=2 buildings each, switch to PLAY_TURN
    counts_per_color = [
        len(s.buildings_by_color[c][SETTLEMENT]) + len(s.buildings_by_color[c][CITY])
        for c in s.colors
    ]
    if s.is_initial_build_phase and all(c >= 2 for c in counts_per_color):
        s.is_initial_build_phase = False
        s.current_prompt = ActionPrompt.PLAY_TURN

    game.playable_actions = generate_playable_actions(s)
    # Fallback: if in INITIAL_ROAD but the placed settlement has all edges occupied, switch to INITIAL_SETTLEMENT or PLAY_TURN
    if not game.playable_actions and s.is_initial_build_phase:
        s.is_initial_build_phase = False
        s.current_prompt = ActionPrompt.PLAY_TURN
        game.playable_actions = generate_playable_actions(s)


def apply_sandbox_edit(game: Game, payload: dict):
    push_sandbox_history(game.id)
    record_snapshot(game)
    s = game.state
    board = s.board
    op = payload.get("op")

    if op == "set_tile":
        coord = tuple(payload["coordinate"])
        tile = board.map.tiles.get(coord)
        if isinstance(tile, LandTile):
            res = payload.get("resource", tile.resource)
            if res == "DESERT" or res is None:
                res = None
                num = None
            else:
                num = payload.get("number", tile.number)
                if num is None:
                    num = 6
                num = int(num)
            doc = map_to_json(board.map)
            for t in doc["tiles"]:
                if tuple(t["coordinate"]) == coord and t["type"] == "LAND":
                    t["resource"] = res
                    t["number"] = num
            new_map = map_from_json(doc)
            board.map = new_map
            board.buildable_subgraph = STATIC_GRAPH.subgraph(new_map.land_nodes)
        elif isinstance(tile, Port):
            res = payload.get("resource")
            if res == "3:1" or res is None:
                res = None
            doc = map_to_json(board.map)
            for t in doc["tiles"]:
                if tuple(t["coordinate"]) == coord and t["type"] == "PORT":
                    t["resource"] = res
            board.map = map_from_json(doc)

    elif op == "set_node":
        node_id = int(payload["node_id"])
        building = payload.get("building")
        color_str = payload.get("color")
        if not building or not color_str:
            board.buildings.pop(node_id, None)
        else:
            color = Color[color_str]
            btype = CITY if building == "CITY" else SETTLEMENT
            # Enforce Catan distance rule: remove any building on adjacent nodes so engine/MCTS never hits invalid state
            for nbr in STATIC_GRAPH.neighbors(node_id):
                board.buildings.pop(nbr, None)
            board.buildings[node_id] = (color, btype)
            # Ensure at least 1 connected road or component exists if in PLAY_TURN
            total_b = len(board.buildings)
            if total_b >= 2 * len(s.colors) and s.is_initial_build_phase:
                s.is_initial_build_phase = False
                s.current_prompt = ActionPrompt.PLAY_TURN

    elif op == "set_edge":
        edge = tuple(int(x) for x in payload["edge"])
        inv = (edge[1], edge[0])
        color_str = payload.get("color")
        if not color_str:
            board.roads.pop(edge, None)
            board.roads.pop(inv, None)
        else:
            color = Color[color_str]
            board.roads[edge] = color
            board.roads[inv] = color

    elif op == "set_robber":
        coord = tuple(int(x) for x in payload["coordinate"])
        if coord in board.map.land_tiles:
            board.robber_coordinate = coord

    elif op == "set_hand":
        color = Color[payload["color"]]
        idx = s.color_to_index[color]
        prefix = f"P{idx}_"
        resources = payload.get("resources") or {}
        for res, count in resources.items():
            if res in RESOURCES:
                s.player_state[f"{prefix}{res}_IN_HAND"] = max(0, int(count))
        dev_cards = payload.get("dev_cards") or {}
        for card, count in dev_cards.items():
            if card in DEVELOPMENT_CARDS:
                s.player_state[f"{prefix}{card}_IN_HAND"] = max(0, int(count))
        if "played_knight" in payload:
            s.player_state[f"{prefix}PLAYED_KNIGHT"] = max(
                0, int(payload["played_knight"])
            )

    elif op == "set_turn":
        if "current_color" in payload:
            color = Color[payload["current_color"]]
            idx = s.color_to_index[color]
            s.current_player_index = idx
            s.current_turn_index = idx
        phase = payload.get("phase")
        curr_key = player_key(s, s.current_color())
        if phase == "INITIAL_SETTLEMENT":
            s.is_initial_build_phase = True
            s.current_prompt = ActionPrompt.BUILD_INITIAL_SETTLEMENT
            s.is_discarding = False
            s.is_moving_knight = False
            s.is_road_building = False
        elif phase == "INITIAL_ROAD":
            s.is_initial_build_phase = True
            s.current_prompt = ActionPrompt.BUILD_INITIAL_ROAD
            s.is_discarding = False
            s.is_moving_knight = False
            s.is_road_building = False
        elif phase == "PRE_ROLL":
            s.is_initial_build_phase = False
            s.current_prompt = ActionPrompt.PLAY_TURN
            s.player_state[f"{curr_key}_HAS_ROLLED"] = False
            s.player_state[f"{curr_key}_HAS_PLAYED_DEVELOPMENT_CARD_IN_TURN"] = False
            s.is_discarding = False
            s.is_moving_knight = False
            s.is_road_building = False
        elif phase == "POST_ROLL":
            s.is_initial_build_phase = False
            s.current_prompt = ActionPrompt.PLAY_TURN
            s.player_state[f"{curr_key}_HAS_ROLLED"] = True
            s.is_discarding = False
            s.is_moving_knight = False
            s.is_road_building = False
        elif phase == "MOVE_ROBBER":
            s.is_initial_build_phase = False
            s.current_prompt = ActionPrompt.MOVE_ROBBER
            s.is_moving_knight = True
            s.is_discarding = False

    elif op == "clear_board":
        board.buildings.clear()
        board.roads.clear()
        for i in range(len(s.colors)):
            prefix = f"P{i}_"
            for res in RESOURCES:
                s.player_state[f"{prefix}{res}_IN_HAND"] = 0
            for card in DEVELOPMENT_CARDS:
                s.player_state[f"{prefix}{card}_IN_HAND"] = 0
                s.player_state[f"{prefix}PLAYED_{card}"] = 0
            s.player_state[f"{prefix}HAS_ROLLED"] = False
        s.is_initial_build_phase = True
        s.current_prompt = ActionPrompt.BUILD_INITIAL_SETTLEMENT
        s.current_player_index = 0
        s.current_turn_index = 0

    elif op == "set_players":
        player_keys = payload.get("players", ["HUMAN", "HUMAN"])
        new_players = REGISTRY.build_all(player_keys, s.colors)
        s.players = new_players

    rebuild_board_caches_and_vps(game)
    overwrite_stored_game_head_only(game)
