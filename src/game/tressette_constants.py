
TRESSETTE_CARD_STRONGS = {
    2: 100,
    1: 99,
    0: 98,
    9: 97,
    8: 96,
    7: 95,
    6: 94,
    5: 93,
    4: 92,
    3: 91
}


TRESSETTE_CARD_VALUES = {
    0: 3, 1: 3, 2: 3, 3: 3,  # Aces (1 point * 3)
    4: 1, 5: 1, 6: 1, 7: 1,  # 2s
    8: 1, 9: 1, 10: 1, 11: 1,  # 3s (1 point * 3)
    12: 0, 13: 0, 14: 0, 15: 0,  # 4s
    16: 0, 17: 0, 18: 0, 19: 0,  # 5s
    20: 0, 21: 0, 22: 0, 23: 0,  # 6s
    24: 0, 25: 0, 26: 0, 27: 0,  # 7s
    28: 1, 29: 1, 30: 1, 31: 1,  # Jacks (1/3 point * 3 = 1)
    32: 1, 33: 1, 34: 1, 35: 1,  # Queens (1/3 point * 3 = 1)
    36: 1, 37: 1, 38: 1, 39: 1   # Kings (1/3 point * 3 = 1)
}

def get_score(card):
    return TRESSETTE_CARD_VALUES[card]

def get_suit(card):
    # Returns suit as remainder of dividing by 4 (0..3).
    return card % 4

def get_stronger_card(card1, card2):
    # Compare rank strengths based on card//4 => rank
    rank1 = card1 // 4
    rank2 = card2 // 4
    if TRESSETTE_CARD_STRONGS[rank1] > TRESSETTE_CARD_STRONGS[rank2]:
        return card1
    elif TRESSETTE_CARD_STRONGS[rank1] < TRESSETTE_CARD_STRONGS[rank2]:
        return card2
    else:
        return None  # Tie in strength
