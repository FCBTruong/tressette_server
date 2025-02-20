import math
from src.game.tressette_config import config as tress_config

exp_levels = tress_config.get("exp_levels")
def calculate_exp_gain(bet_amount: float) -> float:
    """
    Calculate EXP gain based on the bet amount (in gold) using a cubic logarithmic scaling.

    :param bet_amount: The amount of the bet placed.
    :return: Experience points gained from the bet amount.
    """
    if bet_amount <= 0:
        return 0  # No gain for invalid or zero bet amount.

    scaling_factor = 0.01  # Adjust to control the output level.
    log_bet = math.log2(bet_amount)  # Calculate log2 once to avoid redundancy.
    exp_gain = scaling_factor * (log_bet ** 3)  # Cube the logarithm.

    return exp_gain


def convert_exp_to_level(exp):
    level = 1  # Default to level 1 if exp is below the first threshold
    for i in range(1, len(exp_levels)):
        if exp < exp_levels[i]:
            return level
        level += 1
    return level  # Return max level if exp is greater than the highest threshold

