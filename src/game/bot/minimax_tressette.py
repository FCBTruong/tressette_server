def find_optimal_card(
    leading_player,
    bot_score,
    player_score,
    bot_cards,
    player_cards,
    next_bot_cards,
    next_player_cards,
    get_suit,
    get_score,
    get_stronger_card,
    point_to_win,
    leading_card=None,
    max_depth=2,  # <-- added depth parameter
):
    """
    A MINIMAX-style function with limited depth search.
    
    If we reach `depth == 0` (or run out of cards), 
    we estimate a score instead of continuing recursion.
    """

    # Simple memo to avoid recomputing states
    memo = {}

    def heuristic(bot_score, player_score, bot_cards, player_cards):
        """
        Simple heuristic used when we reach `depth == 0`.
        For example, just compute:
        - current bot_score
        - plus sum of bot's card values
        - minus player's potential if you want
        Here we do a naive approach: bot_score - player_score.
        """
        return bot_score - player_score

    def play_hand(
        leading_player,
        bot_score,
        player_score,
        bot_cards,
        player_cards,
        next_bot_cards,
        next_player_cards,
        leading_card,
        depth,
    ):
        """
        Return: (best_final_bot_score, best_final_player_score, best_move)
        'best_move' is relevant only if 'leading_player' == 'bot' on this call.
        """

        # If out of cards, or if we've reached depth limit, use heuristic or final scores.
        if not bot_cards and not player_cards:
            # End of round, no further moves
            return bot_score, player_score, None
        
        if depth <= 0:
            # Return an approximate outcome, using a quick heuristic difference
            # We only need to return a numeric measure, but for consistency we
            # store that measure in bot_score, and keep player's score secondary.
            h_value = heuristic(bot_score, player_score, bot_cards, player_cards)
            # We'll interpret it as if final_bot_score = h_value. 
            # The true player score is still unknown, so store partial data.
            return h_value, player_score, None

        memo_key = (
            leading_player,
            bot_score,
            player_score,
            tuple(bot_cards),
            tuple(player_cards),
            tuple(next_bot_cards),
            tuple(next_player_cards),
            leading_card,
            depth,
        )
        if memo_key in memo:
            return memo[memo_key]

        # --- BOT LEADS ---
        if leading_player == "bot":
            best_final_bot_score = float("-inf")
            best_final_player_score = float("-inf")
            best_bot_move = None

            for bot_card in bot_cards:
                lead_suit = get_suit(bot_card)
                # Player must follow suit if possible
                valid_responses = [
                    c for c in player_cards if get_suit(c) == lead_suit
                ] or player_cards

                # Player tries to minimize bot's final score
                worst_bot_score_for_this_move = float("inf")
                worst_player_score_for_this_move = float("-inf")

                for p_card in valid_responses:
                    # Calculate trick points
                    points = get_score(bot_card) + get_score(p_card)
                    if get_suit(bot_card) == get_suit(p_card):
                        winner = get_stronger_card(bot_card, p_card)
                        if winner == bot_card:
                            new_bot_score = bot_score + points
                            new_player_score = player_score
                            next_leader = "bot"
                        else:
                            new_bot_score = bot_score
                            new_player_score = player_score + points
                            next_leader = "player"
                    else:
                        # Different suit => leading card (bot_card) wins
                        new_bot_score = bot_score + points
                        new_player_score = player_score
                        next_leader = "bot"

                    # Check immediate 21
                    if new_bot_score >= point_to_win or new_player_score >= point_to_win:
                        # If it's possibly last trick: last trick bonus
                        if len(bot_cards) == 1 and len(player_cards) == 1:
                            if next_leader == "bot":
                                new_bot_score += 3
                            else:
                                new_player_score += 3
                        final_bot_s, final_player_s = new_bot_score, new_player_score
                    else:
                        # Remove used cards
                        new_bot_cards = [c for c in bot_cards if c != bot_card]
                        new_player_cards = [c for c in player_cards if c != p_card]

                        # Draw if possible
                        if next_bot_cards and next_player_cards:
                            new_bot_cards.append(next_bot_cards[0])
                            new_player_cards.append(next_player_cards[0])
                            nb_remaining = next_bot_cards[1:]
                            np_remaining = next_player_cards[1:]
                        else:
                            nb_remaining = next_bot_cards
                            np_remaining = next_player_cards

                        # Recurse with depth-1
                        final_bot_s, final_player_s, _ = play_hand(
                            next_leader,
                            new_bot_score,
                            new_player_score,
                            new_bot_cards,
                            new_player_cards,
                            nb_remaining,
                            np_remaining,
                            leading_card=None,  # new leader picks a card
                            depth=depth - 1,
                        )

                    # The player wants to produce the worst outcome for the bot
                    if final_bot_s < worst_bot_score_for_this_move:
                        worst_bot_score_for_this_move = final_bot_s
                        worst_player_score_for_this_move = final_player_s

                # Bot tries to pick the move that yields the best final_bot_score
                if worst_bot_score_for_this_move > best_final_bot_score:
                    best_final_bot_score = worst_bot_score_for_this_move
                    best_final_player_score = worst_player_score_for_this_move
                    best_bot_move = bot_card

            memo[memo_key] = (best_final_bot_score, best_final_player_score, best_bot_move)
            return memo[memo_key]

        # --- PLAYER LEADS ---
        else:
            # If leading_card is None, the player picks a lead from their hand.
            if leading_card is None:
                # Player tries to *minimize* bot's final outcome
                worst_bot_score = float("inf")
                worst_player_score = float("-inf")
                # The "best_move" concept only applies to bot leading,
                # so we set it to None here
                best_bot_move = None

                for p_card in player_cards:
                    new_bot_s, new_player_s, _ = play_hand(
                        "player",
                        bot_score,
                        player_score,
                        bot_cards,
                        player_cards,
                        next_bot_cards,
                        next_player_cards,
                        leading_card=p_card,  # The actual lead
                        depth=depth,
                    )

                    if new_bot_s < worst_bot_score:
                        worst_bot_score = new_bot_s
                        worst_player_score = new_player_s

                memo[memo_key] = (worst_bot_score, worst_player_score, best_bot_move)
                return memo[memo_key]

            else:
                # leading_card is known
                p_card = leading_card
                lead_suit = get_suit(p_card)
                # Bot must respond with same suit if possible
                valid_bot_cards = [c for c in bot_cards if get_suit(c) == lead_suit] or bot_cards

                best_final_bot_score = float("-inf")
                best_final_player_score = float("-inf")
                best_bot_move = None

                for bot_card in valid_bot_cards:
                    points = get_score(p_card) + get_score(bot_card)
                    if get_suit(p_card) == get_suit(bot_card):
                        winner = get_stronger_card(p_card, bot_card)
                        if winner == bot_card:
                            new_bot_score = bot_score + points
                            new_player_score = player_score
                            next_leader = "bot"
                        else:
                            new_bot_score = bot_score
                            new_player_score = player_score + points
                            next_leader = "player"
                    else:
                        # Player's card automatically wins
                        new_bot_score = bot_score
                        new_player_score = player_score + points
                        next_leader = "player"

                    if new_bot_score >= point_to_win or new_player_score >= point_to_win:
                        if len(bot_cards) == 1 and len(player_cards) == 1:
                            if next_leader == "bot":
                                new_bot_score += 3
                            else:
                                new_player_score += 3
                        final_bot_s, final_player_s = new_bot_score, new_player_score
                    else:
                        new_bot_cards = [c for c in bot_cards if c != bot_card]
                        new_player_cards = [c for c in player_cards if c != p_card]

                        # Draw
                        if next_bot_cards and next_player_cards:
                            new_bot_cards.append(next_bot_cards[0])
                            new_player_cards.append(next_player_cards[0])
                            nb_remaining = next_bot_cards[1:]
                            np_remaining = next_player_cards[1:]
                        else:
                            nb_remaining = next_bot_cards
                            np_remaining = next_player_cards

                        final_bot_s, final_player_s, _ = play_hand(
                            next_leader,
                            new_bot_score,
                            new_player_score,
                            new_bot_cards,
                            new_player_cards,
                            nb_remaining,
                            np_remaining,
                            leading_card=None,
                            depth=depth - 1,
                        )

                    # From the bot’s perspective, we want to maximize final_bot_s
                    if final_bot_s > best_final_bot_score:
                        best_final_bot_score = final_bot_s
                        best_final_player_score = final_player_s
                        best_bot_move = bot_card

                memo[memo_key] = (best_final_bot_score, best_final_player_score, best_bot_move)
                return memo[memo_key]

    # Kick off the search
    final_bot_score, final_player_score, bot_move = play_hand(
        leading_player,
        bot_score,
        player_score,
        bot_cards,
        player_cards,
        next_bot_cards,
        next_player_cards,
        leading_card,
        depth=max_depth,
    )

    # If leading_player=='bot', bot_move is what we choose to play right now.
    return bot_move
