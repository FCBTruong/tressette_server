from src.game.tressette_constants import *

def pick_winning_card_first(A, B):
    A_sorted = sorted(A, key=lambda card: TRESSETTE_CARD_STRONGS[card // 4])  # Sort A by strength

    for card in A_sorted:
        suit = card % 4  # Get suit of current card
        B_suit_cards = [b for b in B if b % 4 == suit]  # Get B's cards of same suit
        
        if not B_suit_cards or all(TRESSETTE_CARD_STRONGS[card // 4] > TRESSETTE_CARD_STRONGS[b // 4] for b in B_suit_cards):
            # If no matching suit in B, or this card beats all matching ones
            return card

    return min(A, key=lambda c: (TRESSETTE_CARD_VALUES[c], TRESSETTE_CARD_STRONGS[c // 4]))


