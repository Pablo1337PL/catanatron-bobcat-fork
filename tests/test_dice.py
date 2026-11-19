"""Balanced dice (catanatron.dice): a port of colonist.io's DiceControllerBalanced."""

import random

import pytest

from catanatron.dice import (
    BalancedDice,
    balanced_dice_after,
    roll_outcomes,
)
from catanatron.game import Game
from catanatron.models.enums import Action, ActionType
from catanatron.models.map import number_probability
from catanatron.models.player import Color, RandomPlayer
from catanatron.players.tree_search_utils import execute_spectrum
from catanatron.serialization import state_from_json, state_to_json, web_view

RED, BLUE = Color.RED, Color.BLUE


def _fields(dice: BalancedDice):
    return (
        [tuple(d.dice_pairs) for d in dice.weighted_dice_deck],
        [d.recently_rolled_count for d in dice.weighted_dice_deck],
        dice.cards_left_in_deck,
        list(dice.recent_rolls),
        dice.seven_streak_color,
        dice.seven_streak_count,
        dict(dice.total_sevens_rolled_by_player),
    )


def test_first_roll_has_the_chances_of_two_dice():
    p = BalancedDice(2).probabilities(RED)
    for total in range(2, 13):
        assert p[total] == pytest.approx(number_probability(total))


def test_a_seven_against_the_roller_and_for_the_other_player():
    dice = BalancedDice(2)
    dice.record_roll(RED, (3, 4))
    # 7: 5 of 35 cards left, rolled once in the last 5 rolls (x 0.66)
    base = 5 / 35 * (1 - 0.34)
    # RED: their own streak (-0.4), alone among the rollers with all the 7s (x 1)
    weights_red = {t: len(d.dice_pairs) / 35 for t, d in zip(range(2, 13), dice.weighted_dice_deck)}
    weights_red[7] = base * (1 - 0.4)
    total = sum(weights_red.values())
    assert dice.probabilities(RED)[7] == pytest.approx(weights_red[7] / total)
    # BLUE has not rolled: two rollers, one 7 -> no imbalance yet; the streak is RED's (+0.4)
    weights_blue = dict(weights_red)
    weights_blue[7] = base * (1 + 0.4)
    total = sum(weights_blue.values())
    assert dice.probabilities(BLUE)[7] == pytest.approx(weights_blue[7] / total)


def test_sevens_imbalance():
    dice = BalancedDice(2)
    dice.record_roll(RED, (3, 4))
    dice.record_roll(BLUE, (2, 2))
    # One 7 between two rollers: fewer 7s than rollers, no adjustment yet
    assert dice._get_seven_imbalance_adjustment(RED) == 1
    dice.record_roll(RED, (2, 5))
    # Two 7s, both RED's: RED gets 1 + (1/2 - 1)/(1/2) = 0, BLUE 2
    assert dice._get_seven_imbalance_adjustment(RED) == pytest.approx(0)
    assert dice._get_seven_imbalance_adjustment(BLUE) == pytest.approx(2)
    assert dice.probabilities(RED)[7] == 0


def test_recently_rolled_totals_come_up_less():
    dice = BalancedDice(2)
    for _ in range(2):
        dice.record_roll(RED, (2, 3))
    weights = {t: len(d.dice_pairs) / 34 for t, d in zip(range(2, 13), dice.weighted_dice_deck)}
    weights[5] *= 1 - 2 * 0.34
    assert dice.probabilities(BLUE)[5] == pytest.approx(weights[5] / sum(weights.values()))
    # Five rolls later the 5s are forgotten
    for faces in [(1, 1), (6, 6), (1, 1), (6, 6), (1, 2)]:
        dice.record_roll(RED, faces)
    assert dice.weighted_dice_deck[5 - 2].recently_rolled_count == 0
    assert len(dice.recent_rolls) == 5


def test_reshuffles_below_13_cards():
    dice = BalancedDice(2)
    rng = random.Random(1)
    for i in range(23):
        dice.throw_dice(RED if i % 2 else BLUE, rng)
    assert dice.cards_left_in_deck == 13
    dice.throw_dice(RED, rng)
    assert dice.cards_left_in_deck == 12
    dice.throw_dice(BLUE, rng)  # reshuffled first: 36 - 1
    assert dice.cards_left_in_deck == 35
    assert sum(len(d.dice_pairs) for d in dice.weighted_dice_deck) == 35


def test_a_deck_of_36_cards_between_reshuffles():
    dice = BalancedDice(2)
    rng = random.Random(7)
    drawn = [dice.throw_dice(RED if i % 2 else BLUE, rng) for i in range(24)]
    # 24 different combinations: each card comes up once until the reshuffle
    assert len(set(drawn)) == 24


def test_record_of_a_total_with_no_cards_left_takes_no_card():
    dice = BalancedDice(2)
    dice.record_roll(RED, (1, 1))
    dice.record_roll(BLUE, (1, 1))  # no 2 left: a search trying it must not crash
    assert dice.cards_left_in_deck == 35
    assert dice.recent_rolls == [2, 2]


def _play(dice_seed=None, seed=3, turns=80):
    game = Game(
        [RandomPlayer(RED), RandomPlayer(BLUE)],
        seed=seed,
        dice_seed=dice_seed,
    )
    random.seed(seed)
    while game.winning_color() is None and game.state.num_turns < turns:
        game.play_tick()
    return game


def _rolls(game):
    return [r.result for r in game.state.action_records if r.action.action_type == ActionType.ROLL]


def test_balanced_dice_by_default_fair_dice_on_request():
    game = Game([RandomPlayer(RED), RandomPlayer(BLUE)], seed=1)
    assert game.balanced_dice and isinstance(game.state.dice_deck, BalancedDice)
    fair = Game([RandomPlayer(RED), RandomPlayer(BLUE)], seed=1, balanced_dice=False)
    assert not fair.balanced_dice and fair.state.dice_deck is None


def test_a_dice_seed_replays_the_same_rolls():
    a, b = _play(dice_seed=11), _play(dice_seed=11)
    assert a.balanced_dice
    assert _rolls(a) == _rolls(b) and len(_rolls(a)) > 30


def test_the_log_rebuilds_the_dice():
    game = _play(dice_seed=5)
    rebuilt = balanced_dice_after(2, game.state.action_records)
    assert _fields(rebuilt) == _fields(game.state.dice_deck)


def test_stored_and_loaded():
    game = _play(dice_seed=5)
    loaded = state_from_json(state_to_json(game), [RandomPlayer(RED), RandomPlayer(BLUE)])
    assert loaded.balanced_dice
    assert _fields(loaded.state.dice_deck) == _fields(game.state.dice_deck)
    assert web_view(game)["balanced_dice"] is True
    # A document from before balanced dice: the game had fair dice
    doc = state_to_json(game)
    del doc["game"]["balanced_dice"]
    assert not state_from_json(doc, [RandomPlayer(RED), RandomPlayer(BLUE)]).balanced_dice


def test_copies_roll_on_their_own():
    game = _play(turns=10)
    before = _fields(game.state.dice_deck)
    copy = game.fast_copy()
    while not any(a.action_type == ActionType.ROLL for a in copy.playable_actions):
        copy.execute(copy.playable_actions[0])
    roll = next(a for a in copy.playable_actions if a.action_type == ActionType.ROLL)
    copy.execute(roll)
    assert _fields(game.state.dice_deck) == before
    assert _fields(copy.state.dice_deck) != before


def test_search_uses_the_balanced_chances():
    game = _play(turns=10)
    while not any(a.action_type == ActionType.ROLL for a in game.playable_actions):
        game.execute(game.playable_actions[0])
    color = game.state.current_color()
    outcomes = roll_outcomes(game.state, color)
    assert sum(p for _, p in outcomes) == pytest.approx(1.0)
    expected = game.state.dice_deck.probabilities(color)
    for dice, p in outcomes:
        assert p == pytest.approx(expected[dice[0] + dice[1]])
    spectrum = execute_spectrum(game, Action(color, ActionType.ROLL, None))
    assert sum(p for _, p in spectrum) == pytest.approx(1.0)
    assert len(spectrum) == len(outcomes)
