"""Balanced dice: a one-to-one port of colonist.io's ``DiceControllerBalanced``.

The 36 combinations of two dice are a deck of cards that is reshuffled once
fewer than 13 are left. Before each draw every total is weighted by the share
of its cards still in the deck, then

* reduced by 34% for each time it was rolled among the last 5 rolls,
* for a 7: scaled by how far the roller is from their fair share of the 7s
  rolled so far, plus 0.4 per 7 in the current streak of 7s (against the
  player who rolled them, for everybody else), clamped to [0, 2].

A total is drawn with probability proportional to its weight, and one of its
remaining combinations uniformly. The Cities & Knights event die
(``throwEventDice``) is not ported: the engine has no such die.

Everything the controller remembers follows from the rolls of the game (who
rolled which dice, in order), so :func:`balanced_dice_after` rebuilds it from
``state.action_records`` -- for a game loaded from storage, say.

Two deviations, both on paths the original never takes in practice:

* ``Math.random()`` is the ``rng`` passed in (the game's stream, or a stream
  seeded by the game's ``dice_seed``).
* ``getWeightedDice`` can pick a total with no cards left only when
  ``Math.random()`` hits a boundary exactly (the original then returns
  ``undefined``); here that goes the way of its error branch, a 3 and a 4.
  Recording a roll whose total has no cards left (a search trying a roll
  this deck cannot produce) updates the memory of rolls but takes no card.
"""

import logging
from typing import Dict, List, Optional, Tuple

DicePair = Tuple[int, int]

MINIMUM_CARDS_BEFORE_RESHUFFLING = 13
PROBABILITY_REDUCTION_FOR_RECENTLY_ROLLED = 0.34
PROBABILITY_REDUCTION_FOR_SEVEN_STREAKS = 0.4
MAXIMUM_RECENT_ROLL_MEMORY = 5
TOTAL_COMBINATIONS = 36
IGNORE_0_AND_1 = 2  # index of a total in the deck = total - 2

logger = logging.getLogger(__name__)


def standard_dice_deck() -> List[Tuple[int, List[DicePair]]]:
    """Every combination of two dice, grouped by total (2..12)."""
    return [
        (total, [(d1, total - d1) for d1 in range(1, 7) if 1 <= total - d1 <= 6])
        for total in range(2, 13)
    ]


class _TotalDeck:
    __slots__ = ("total_dice", "dice_pairs", "probability_weighting", "recently_rolled_count")

    def __init__(self, total_dice):
        self.total_dice = total_dice
        self.dice_pairs: List[DicePair] = []
        self.probability_weighting = 0.0
        self.recently_rolled_count = 0


class BalancedDice:
    """The state of one game's balanced dice (``DiceControllerBalanced``)."""

    def __init__(self, number_of_players: int):
        self.number_of_players = number_of_players

        self._init_weighted_dice_deck()
        self._reshuffle_weighted_dice_deck()
        self._update_weighted_dice_deck_probabilities()

        self.recent_rolls: List[int] = []
        self.seven_streak_color = None  # PlayerColor.None
        self.seven_streak_count = 0
        # Insertion-ordered, as the Map of the original
        self.total_sevens_rolled_by_player: Dict = {}

    def copy(self) -> "BalancedDice":
        other = BalancedDice.__new__(BalancedDice)
        other.number_of_players = self.number_of_players
        other.weighted_dice_deck = []
        for deck in self.weighted_dice_deck:
            copied = _TotalDeck(deck.total_dice)
            copied.dice_pairs = list(deck.dice_pairs)
            copied.probability_weighting = deck.probability_weighting
            copied.recently_rolled_count = deck.recently_rolled_count
            other.weighted_dice_deck.append(copied)
        other.cards_left_in_deck = self.cards_left_in_deck
        other.recent_rolls = list(self.recent_rolls)
        other.seven_streak_color = self.seven_streak_color
        other.seven_streak_count = self.seven_streak_count
        other.total_sevens_rolled_by_player = dict(self.total_sevens_rolled_by_player)
        return other

    # ===== The controller's public calls

    def throw_dice(self, player_color, rng) -> DicePair:
        """Draws the next roll of ``player_color`` (mutates the deck)."""
        self._init_total_sevens(player_color)
        return self._draw_weighted_card(player_color, rng)

    def record_roll(self, player_color, dice: DicePair) -> None:
        """Takes ``dice`` as ``player_color``'s next roll: the same steps as a
        draw, with the card already chosen (replays, and searches that try
        each outcome)."""
        self._init_total_sevens(player_color)
        self._prepare_draw(player_color)
        deck = self.weighted_dice_deck[dice[0] + dice[1] - IGNORE_0_AND_1]
        drawn = tuple(dice)
        if drawn not in deck.dice_pairs:
            # The same total, other faces: any remaining card of that total
            drawn = deck.dice_pairs[0] if deck.dice_pairs else None
        self._take_card(deck, drawn, player_color)

    def probabilities(self, player_color) -> Dict[int, float]:
        """Chance of each total (2..12) for ``player_color``'s next roll,
        without drawing."""
        dice = self.copy()
        dice._init_total_sevens(player_color)
        dice._prepare_draw(player_color)
        total_probability_weight = dice._get_total_probability_weight()
        if total_probability_weight <= 0:
            return {7: 1.0}  # the original's error branch: a 3 and a 4
        return {
            deck.total_dice: deck.probability_weighting / total_probability_weight
            for deck in dice.weighted_dice_deck
        }

    # ===== drawWeightedCard and its steps

    def _draw_weighted_card(self, player_color, rng) -> DicePair:
        self._prepare_draw(player_color)
        return self._get_weighted_dice(player_color, rng)

    def _prepare_draw(self, player_color):
        if self.cards_left_in_deck < MINIMUM_CARDS_BEFORE_RESHUFFLING:
            self._reshuffle_weighted_dice_deck()
        self._update_weighted_dice_deck_probabilities()
        self._adjust_weighted_dice_deck_based_on_recent_rolls()
        self._adjust_seven_probability_based_on_sevens(player_color)

    def _init_weighted_dice_deck(self):
        self.weighted_dice_deck = [_TotalDeck(total) for total in range(2, 13)]

    def _reshuffle_weighted_dice_deck(self):
        for total_dice_index, (_, dice_pairs_for_total_dice) in enumerate(
            standard_dice_deck()
        ):
            self.weighted_dice_deck[total_dice_index].dice_pairs = dice_pairs_for_total_dice
        self.cards_left_in_deck = TOTAL_COMBINATIONS

    def _update_weighted_dice_deck_probabilities(self):
        for deck in self.weighted_dice_deck:
            deck.probability_weighting = len(deck.dice_pairs) / self.cards_left_in_deck

    def _get_weighted_dice(self, player_color, rng) -> DicePair:
        total_probability_weight = self._get_total_probability_weight()

        target_random_number = rng.random() * total_probability_weight
        for deck in self.weighted_dice_deck:
            if target_random_number <= deck.probability_weighting:
                if not deck.dice_pairs:
                    break  # see the module docstring
                drawn_card = deck.dice_pairs[int(rng.random() * len(deck.dice_pairs))]
                self._take_card(deck, drawn_card, player_color)
                return drawn_card
            target_random_number -= deck.probability_weighting

        logger.error("Something seriously wrong with weighted dice deck")
        default_roll_if_error = (3, 4)
        return default_roll_if_error

    def _take_card(self, deck, drawn_card: Optional[DicePair], player_color):
        """What ``getWeightedDice`` does once a card is chosen."""
        if drawn_card is not None:
            deck.dice_pairs.remove(drawn_card)
            self.cards_left_in_deck -= 1

        self.recent_rolls.append(deck.total_dice)
        deck.recently_rolled_count += 1

        if len(self.recent_rolls) > MAXIMUM_RECENT_ROLL_MEMORY:
            self._update_recently_rolled()
        if deck.total_dice == 7:
            self._update_seven_rolls(player_color)

    def _get_total_probability_weight(self) -> float:
        return sum(deck.probability_weighting for deck in self.weighted_dice_deck)

    def _update_recently_rolled(self):
        total_dice_five_rolls_ago = self.recent_rolls[0]
        self.weighted_dice_deck[
            total_dice_five_rolls_ago - IGNORE_0_AND_1
        ].recently_rolled_count -= 1
        self.recent_rolls.pop(0)

    def _adjust_weighted_dice_deck_based_on_recent_rolls(self):
        for deck in self.weighted_dice_deck:
            probability_reduction = (
                deck.recently_rolled_count * PROBABILITY_REDUCTION_FOR_RECENTLY_ROLLED
            )
            probability_multiplier = 1 - probability_reduction
            deck.probability_weighting *= probability_multiplier
            if deck.probability_weighting < 0:
                deck.probability_weighting = 0

    def _init_total_sevens(self, player_color):
        if player_color in self.total_sevens_rolled_by_player:
            return
        self.total_sevens_rolled_by_player[player_color] = 0

    def _update_seven_rolls(self, player_color):
        sevens_rolled_by_player = self.total_sevens_rolled_by_player.get(player_color, 0)
        self.total_sevens_rolled_by_player[player_color] = sevens_rolled_by_player + 1

        if player_color == self.seven_streak_color:
            self.seven_streak_count += 1
            return

        self.seven_streak_color = player_color
        self.seven_streak_count = 1

    def _adjust_seven_probability_based_on_sevens(self, player_color):
        if self.number_of_players < 2:
            return
        streak_adjustment_percentage = self._get_streak_adjustment_constant(player_color)
        player_sevens_adjustment_percentage = self._get_seven_imbalance_adjustment(
            player_color
        )

        seven_probability_adjustment = (
            1 * player_sevens_adjustment_percentage + streak_adjustment_percentage
        )

        minimum_adjustment = 0
        maximum_adjustment = 2
        if seven_probability_adjustment < minimum_adjustment:
            seven_probability_adjustment = minimum_adjustment
        if seven_probability_adjustment > maximum_adjustment:
            seven_probability_adjustment = maximum_adjustment

        seven_index = 7 - IGNORE_0_AND_1
        self.weighted_dice_deck[seven_index].probability_weighting *= (
            seven_probability_adjustment
        )

    def _get_streak_adjustment_constant(self, player_color) -> float:
        is_streak_for_or_against_player = (
            -1 if self.seven_streak_color == player_color else 1
        )
        return (
            PROBABILITY_REDUCTION_FOR_SEVEN_STREAKS
            * self.seven_streak_count
            * is_streak_for_or_against_player
        )

    def _get_seven_imbalance_adjustment(self, player_color) -> float:
        total_sevens = self._get_total_sevens_rolled()
        if total_sevens < len(self.total_sevens_rolled_by_player):
            return 1

        sevens_per_player = self.total_sevens_rolled_by_player.get(player_color, 0)

        percentage_of_total_sevens = sevens_per_player / total_sevens
        ideal_percentage_of_total_sevens = 1 / len(self.total_sevens_rolled_by_player)

        return 1 + (
            (ideal_percentage_of_total_sevens - percentage_of_total_sevens)
            / ideal_percentage_of_total_sevens
        )

    def _get_total_sevens_rolled(self) -> int:
        return sum(self.total_sevens_rolled_by_player.values())


def balanced_dice_after(number_of_players: int, action_records) -> BalancedDice:
    """The dice of a balanced game after the rolls in ``action_records``."""
    from catanatron.models.enums import ActionType

    dice = BalancedDice(number_of_players)
    for record in action_records:
        if record.action.action_type == ActionType.ROLL:
            dice.record_roll(record.action.color, record.result or record.action.value)
    return dice


def roll_outcomes(state, color) -> List[Tuple[DicePair, float]]:
    """``[(dice, probability)]`` of ``color``'s next roll, one entry per total
    that can come up; for balanced dice the dice are a combination still in
    the deck (``record_roll`` then takes exactly that card)."""
    from catanatron.models.map import number_probability

    dice = state.dice_deck
    if dice is None:
        return [((total // 2, (total + 1) // 2), number_probability(total)) for total in range(2, 13)]
    outcomes = []
    for total, p in dice.probabilities(color).items():
        if p <= 0:
            continue
        pairs = dice.weighted_dice_deck[total - IGNORE_0_AND_1].dice_pairs
        outcomes.append((pairs[0] if pairs else (total // 2, (total + 1) // 2), p))
    return outcomes
