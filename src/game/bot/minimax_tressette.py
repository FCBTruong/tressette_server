import random
import math
import copy

# Card points based on Tressette rules
CARD_POINTS = {
    0: 1, 1: 1, 2: 1, 3: 1,   # Aces
    28: 1/3, 29: 1/3, 30: 1/3, 31: 1/3,  # Kings
    32: 1/3, 33: 1/3, 34: 1/3, 35: 1/3,  # Queens
    36: 1/3, 37: 1/3, 38: 1/3, 39: 1/3    # Jacks
}

# Tressette card ranking (higher is stronger)
TRESSETTE_RANKING = {
    2: 100,  # 3
    1: 99,   # 2
    0: 98,   # Ace
    9: 97,   # K
    8: 96,   # Q
    7: 95,   # J
    6: 94,   # 7
    5: 93,   # 6
    4: 92,   # 5
    3: 91    # 4
}

def get_suit(card):
    return card % 4  

def get_rank(card):
    return TRESSETTE_RANKING.get(card // 4, 0)

def compare_cards(card1, card2, leading_suit):
    """Returns True if card1 wins against card2 given the leading suit."""
    suit1, suit2 = get_suit(card1), get_suit(card2)
    rank1, rank2 = get_rank(card1), get_rank(card2)
    if suit1 == suit2:
        return rank1 > rank2
    elif suit1 == leading_suit:
        return True
    elif suit2 == leading_suit:
        return False
    else:
        return rank1 > rank2

def simulate_trick(lead_card, follow_card, lead_is_bot):
    """
    Simulate a completed trick.
    
    Returns:
      score: positive if bot wins (points gained), negative if loses.
      winner_is_bot: boolean.
    """
    # The leading suit is that of the lead_card.
    leading_suit = get_suit(lead_card)
    # Determine trick winner.
    if lead_is_bot:
        bot_card, opp_card = lead_card, follow_card
    else:
        bot_card, opp_card = follow_card, lead_card

    if compare_cards(bot_card, opp_card, leading_suit):
        # Winner is bot.
        score = CARD_POINTS.get(bot_card, 0) + CARD_POINTS.get(opp_card, 0)
        return score, True
    else:
        score = CARD_POINTS.get(bot_card, 0) + CARD_POINTS.get(opp_card, 0)
        return -score, False

def get_valid_moves(cards, current_card):
    """
    Returns moves (cards) that follow suit if possible; otherwise, all cards.
    """
    if current_card == -1:
        return cards[:]
    valid = [card for card in cards if get_suit(card) == get_suit(current_card)]
    return valid if valid else cards[:]

def minimax(bot_cards, opp_cards, bot_future, opp_future, current_card, is_bot_turn, depth, alpha, beta):
    """
    Recursive minimax search for the current trick.
    
    Parameters:
      bot_cards, opp_cards: current cards in hand.
      bot_future, opp_future: cards that will be drawn after current trick.
      current_card: card already played in this trick (-1 if none).
      is_bot_turn: True if it's the bot's turn to play.
      depth: recursion depth (used as a terminal condition).
      alpha, beta: for alpha-beta pruning.
      
    Returns:
      (score, move): score is the net score difference (bot minus opponent) for optimal play.
                     move is the card the bot should play (only set at the root level).
    """
    # Terminal condition: if both players have played a card for the trick.
    if current_card != -1 and not is_bot_turn:
        # Both moves are played; simulate trick outcome.
        # In our simulation, the card in current_card is the lead card,
        # and the card just played is the follow card.
        # We assume that after this trick, future cards will be drawn (but for simplicity,
        # we stop at one trick).
        score, _ = simulate_trick(current_card, 0, True)  # dummy follow card; already simulated.
        return score, None

    # Terminal condition: depth limit reached.
    if depth == 0:
        return 0, None

    if is_bot_turn:
        best_score = -math.inf
        best_move = None
        valid_moves = get_valid_moves(bot_cards, current_card)
        for card in valid_moves:
            # Copy current state for simulation.
            new_bot = bot_cards.copy()
            new_bot.remove(card)
            # When bot plays, if no card is on the table, this card becomes the lead.
            new_current = card if current_card == -1 else current_card

            # For simplicity, assume opponent will then move.
            score, _ = minimax(new_bot, opp_cards, bot_future, opp_future, new_current, False, depth - 1, alpha, beta)
            if score > best_score:
                best_score = score
                best_move = card
            alpha = max(alpha, best_score)
            if beta <= alpha:
                break
        return best_score, best_move
    else:
        # Opponent turn.
        worst_score = math.inf
        valid_moves = get_valid_moves(opp_cards, current_card)
        for card in valid_moves:
            new_opp = opp_cards.copy()
            new_opp.remove(card)
            # Now the trick is complete; simulate the trick.
            # current_card is lead, and card is opponent's play.
            score, _ = simulate_trick(current_card, card, True)
            # In a full simulation we would add minimax result of subsequent rounds,
            # but here we assume one-trick evaluation.
            if score < worst_score:
                worst_score = score
            beta = min(beta, worst_score)
            if beta <= alpha:
                break
        return worst_score, None

def bot_play(bot_cards, opp_cards, bot_future, opp_future, current_card):
    """
    Returns the card that the bot should play based on minimax search.
    """
    # For simplicity, we set a small depth since we're simulating a single trick.
    depth = 4
    _, move = minimax(bot_cards, opp_cards, bot_future, opp_future, current_card, True, depth, -math.inf, math.inf)
    # If minimax fails to pick a move, default to a valid move.
    if move is None:
        move = get_valid_moves(bot_cards, current_card)[0]
    return move

# Example usage:
if __name__ == "__main__":
    # Example hands (the bot "knows" all cards)
    bot_cards = [32, 3, 18, 5, 16, 11, 4, 10, 17]
    opp_cards = [19, 15, 34, 22, 29, 21, 14, 0]
    bot_future = [1, 12, 23, 35]
    opp_future = [0, 11, 22, 33]
    
    # Case 1: Bot is following (opponent already played a card).
    current_card = 23  # Opponent's card as lead (for example)
    chosen = bot_play_minimax(bot_cards, opp_cards, bot_future, opp_future, current_card)
    print(f"Minimax (following): Bot plays {chosen} (Rank: {get_rank(chosen)}, Suit: {get_suit(chosen)})")
    
    # Case 2: Bot leads (current_card = -1).
    current_card = -1
    chosen = bot_play_minimax(bot_cards, opp_cards, bot_future, opp_future, current_card)
    print(f"Minimax (leading): Bot plays {chosen} (Rank: {get_rank(chosen)}, Suit: {get_suit(chosen)})")
