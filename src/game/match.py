import asyncio
from enum import Enum
from datetime import datetime, timedelta
import logging
import random
import traceback

from src.base.network.packets import packet_pb2
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs
from src.game.game_vars import game_vars
from datetime import datetime, timedelta

class MatchState(Enum):
	WAITING = 0
	PLAYING = 1
	ENDING = 2
	ENDED = 3

PLAYER_SOLO_MODE = 2
PLAYER_DUO_MODE = 4
TRESSETTE_MODE = 0
BRISCOLA_MODE = 1

TIME_AUTO_PLAY = 10 # seconds
TIME_START_TO_DEAL = 3.5 # seconds


# 0 - 39
TRESSETTE_CARDS = [i for i in range(40)]

class LeaveMatchErrors(Enum):
    SUCCESS = 0
    NOT_IN_MATCH = 1
    MATCH_STARTED = 2
# Configure the logger
logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("game_match")  # Name your logger

class MatchPlayer:
    def __init__(self, uid):
        self.uid = uid
        self.name = ""
        self.gold = 0
        self.cards = [] # id of cards
        self.points = 0
        self.score_last_trick = 0
        self.team_id = -1
    
    def reset_game(self):
        self.cards.clear()
        self.points = 0
        self.score_last_trick = 0

class Match:
    cards_compare = []
    def __init__(self, match_id, game_mode=TRESSETTE_MODE, player_mode=PLAYER_SOLO_MODE):
        self.match_id = match_id
        self.start_time = datetime.now()
        self.end_time = None
        self.game_mode = game_mode
        self.player_mode = player_mode
        self.players: list[MatchPlayer] = []
        self.cards = []
        self.win_player = None
        self.hand_suit = -1
        self.auto_play_time_by_uid = {}

        if player_mode == PLAYER_SOLO_MODE:
            for i in range(2):
                p = MatchPlayer(-1)
                self.players.append(p)
                p.team_id = i
        elif player_mode == PLAYER_DUO_MODE:
            for i in range(4):
                p = MatchPlayer(-1)
                p.team_id = i % 2
                self.players.append(p)
        self.reset_logic_game()
    
    async def loop(self):
        try:
            if self.state == MatchState.PLAYING:
                if self.time_auto_play != -1 and datetime.now().timestamp() > self.time_auto_play:
                    card_id = self.players[self.current_turn].cards[0]
                    if self.hand_suit != -1:
                        # find suitable card
                        for card in self.players[self.current_turn].cards:
                            if card % 4 == self.hand_suit:
                                card_id = card
                                break

                    await self._play_card(self.players[self.current_turn].uid, card_id, auto=True)
            elif self.state == MatchState.WAITING:
                if self.check_room_full() and self.time_start != -1 and datetime.now().timestamp() > self.time_start:
                    await self.start_game()
        except Exception as e:
            traceback.print_exc()
            raise e
    def reset_logic_game(self):
        self.current_turn = -1
        self.time_auto_play = -1
        self.state = MatchState.WAITING
        self.cards_compare.clear()
        for i in range(self.player_mode):
            self.cards_compare.append(-1)

        self.current_hand = 0

        print(f"Player mode: {self.player_mode}")
        for i in range(self.player_mode):
            self.cards_compare.append(-1)

    def end_match(self):
        self.state = MatchState.ENDED
        self.end_time = datetime.now()

    async def user_join(self, user_id):
        # check user in match
        for player in self.players:
            if player.uid == user_id:
                print('User already in match, can not jion')
                return
        
        user_data = await users_info_mgr.get_user_info(user_id)
        # find empty slot
        for i, player in enumerate(self.players):
            if player.uid == -1:
                self.players[i].uid = user_data.uid
                self.players[i].name = user_data.name
                self.players[i].gold = user_data.gold
                seat_server_id = i
                team_id = self.players[i].team_id
                break

        # send to others that user has joined
        for i, player in enumerate(self.players):
            if player.uid == -1 or player.uid == user_id:
                continue
            print(f"Send to user {player.uid} that user {user_id} has joined")
            pkg = packet_pb2.NewUserJoinMatch()
            pkg.uid = user_id
            pkg.name = user_data.name
            pkg.seat_server = seat_server_id
            pkg.team_id = team_id

            await game_vars.get_game_client().send_packet(player.uid, CMDs.NEW_USER_JOIN_MATCH, pkg)
        
        await self._send_game_info(user_id)

        if self.check_room_full():
            self.time_start = datetime.now().timestamp() + TIME_START_TO_DEAL
            # Send to all players that game is starting, wait for 3 seconds
            pkg = packet_pb2.PrepareStartGame()
            pkg.time_start = int(self.time_start)
            print('Game is starting, wait for 3 seconds')
            for player in self.players:
                await game_vars.get_game_client().send_packet(player.uid, CMDs.PREPARE_START_GAME, pkg)

    def check_can_join(self, uid: int):
        if self.state == MatchState.WAITING:
            return True
        return False
    
    def check_room_full(self):
        for player in self.players:
            if player.uid == -1:
                return False
        return True
    
    async def _send_game_info(self, uid):
        logger.info(f"Sending game info to user {uid}")
        game_info = packet_pb2.GameInfo()
        game_info.match_id = self.match_id
        game_info.game_mode = self.game_mode
        game_info.player_mode = self.player_mode
        game_info.game_state = self.state.value
        game_info.current_turn = self.current_turn
        game_info.cards_compare.extend(self.cards_compare)
        game_info.remain_cards = len(self.cards)
        game_info.hand_suit = self.hand_suit # current suit of hand

        for player in self.players:
            game_info.uids.append(player.uid)
            # game_info.user_names.append(player.user_name)
            game_info.user_golds.append(player.gold)
            game_info.user_names.append(player.name)
            game_info.user_points.append(player.points)
            game_info.team_ids.append(player.team_id)

            if player.uid == uid:
                game_info.my_cards.extend(player.cards)
        
        print(f"Send game info to user {uid}, game_info: {game_info}")
        await game_vars.get_game_client().send_packet(uid, CMDs.GAME_INFO, game_info)

    async def user_leave(self, uid): 
        for i, player in enumerate(self.players):
            if player.uid == uid:
                self.players[i].uid = -1
                break

        # noti to others
        for player in self.players:
            if player.uid == -1:
                continue

            print(f"Send to user {player.uid} that user {uid} has left")

            pkg = packet_pb2.UserLeaveMatch()
            pkg.uid = uid
            await game_vars.get_game_client().send_packet(player.uid, CMDs.USER_LEAVE_MATCH, pkg)
    
    async def start_game(self):
        self.state = MatchState.PLAYING
        self.start_time = datetime.now()
        self.current_turn = 0
        self.current_hand = -1
        self.time_auto_play = -1
        self.cards_compare.clear()
        self.auto_play_time_by_uid.clear()
        for i in range(len(self.players)):
            self.cards_compare.append(-1)

        pkg = packet_pb2.StartGame()
        for player in self.players:
            await game_vars.get_game_client().send_packet(player.uid, CMDs.START_GAME, pkg)
        # # wait for 3 seconds
        # await asyncio.sleep(TIME_START_TO_DEAL)
        await self.deal_card()
        # wait for 2 seconds
        await asyncio.sleep(2)
        await self._handle_new_hand()

    async def user_play_card(self, uid, payload):
        pkg = packet_pb2.PlayCard()
        pkg.ParseFromString(payload)
        card_id = pkg.card_id
        await self._play_card(uid, card_id, auto=False)
    
    async def _play_card(self, uid, card_id, auto=False):
        # # test
        # await self.end_game()
        # return
        if self.state != MatchState.PLAYING:
            logger.error("Game is not in progress")
            return
        
        if await self.check_done_hand():
            logger.error("hand is done, wait for next hand")
            return
    

        # check whether it is user turn
        if self.players[self.current_turn].uid != uid:
            logger.error(f"User {uid} is not in turn")
            return
        
        # check whether user has the card
        player = self.players[self.current_turn]
        if card_id not in player.cards:
            logger.error(f"User {uid} does not have card {card_id}")
            return
        
        if self.hand_suit == -1:
            self.hand_suit = card_id % 4
        else:
            card_suit = card_id % 4
            if card_suit != self.hand_suit:
                for card in player.cards:
                    if card % 4 == self.hand_suit:
                        logger.error(f"User {uid} must play card with suit {self.hand_suit}")
                        return

        # Now user can play card
        if not auto:
            # remove auto play time
            self.auto_play_time_by_uid.pop(uid, None)
            
        # remove card from player
        print('remove card id: ', card_id, ' auto: ', auto)
        player.cards.remove(card_id)
        self.cards_compare[self.current_turn] = card_id
        self.time_auto_play = -1

        is_finish_hand = await self.check_done_hand()
        if not is_finish_hand:
            self.current_turn = (self.current_turn + 1) % len(self.players)
        else:
            self.current_turn = -1
    
        # send to others
        for i, player in enumerate(self.players):
            pkg = packet_pb2.PlayCard()
            pkg.uid = uid
            pkg.card_id = card_id
            pkg.auto = auto
            pkg.current_turn = self.current_turn
            pkg.hand_suit = self.hand_suit
            await game_vars.get_game_client().send_packet(player.uid, CMDs.PLAY_CARD, pkg)

        # Check done hand
        if is_finish_hand:
            await self.end_hand()
        else:
            # next uid
            next_uid = self.players[self.current_turn].uid
            if self.auto_play_time_by_uid.get(next_uid):
                self.time_auto_play = self.auto_play_time_by_uid[next_uid] + TIME_AUTO_PLAY
            else:
                self.time_auto_play = TIME_AUTO_PLAY + datetime.now().timestamp()

    async def check_done_hand(self):
        for card in self.cards_compare:
            if card == -1:
                return False
        return True

    async def user_reconnect(self, uid):
       await self._send_game_info(uid)

    async def deal_card(self):
        self.cards = TRESSETTE_CARDS.copy()
        random.shuffle(self.cards)
        print(f"Cards: {self.cards}")
        for i, player in enumerate(self.players):
            player.cards = self.cards[i*10: (i+1)*10]
        
        # remove cards dealt
        self.cards = self.cards[10 * len(self.players):]

        # send to users
        for player in self.players:
            pkg = packet_pb2.DealCard()
            pkg.cards.extend(player.cards)
            pkg.remain_cards = len(self.cards)
            await game_vars.get_game_client().send_packet(player.uid, CMDs.DEAL_CARD, pkg)
    

    async def end_hand(self):
        win_card = self.get_win_card_in_hand()
        win_player = self.players[self.cards_compare.index(win_card)]
        self.win_player = win_player
        win_score = self.get_win_score_in_hand()
        win_player.points += win_score

        # reset hand
        self.cards_compare.clear()
        for _ in range(self.player_mode):
            self.cards_compare.append(-1)

        self.current_hand += 1

        pkg = packet_pb2.EndHand()
        pkg.win_uid = win_player.uid
        pkg.win_card = win_card
        for player in self.players:
            pkg.user_points.append(player.points)

        # send to others
        await asyncio.sleep(0.5)
        for player in self.players:
            await game_vars.get_game_client().send_packet(player.uid, CMDs.END_HAND, pkg)

        # effect show win cards
        await asyncio.sleep(2)
        
        # draw new cards
        if self._is_end_game():
            await self.end_game()
            return
        if len(self.cards) != 0:
            await self._handle_draw_card()
            await asyncio.sleep(3)

        await self._handle_new_hand()
    
    def _is_end_game(self):
        if len(self.cards) == 0 and all(player.cards == [] for player in self.players):
            return True
        return False
    
    async def _handle_draw_card(self):
        draw_cards = []
        for player in self.players:
            new_card = self._draw_card()
            player.cards.append(new_card)
            draw_cards.append(new_card)
        
        # send to users
        pkg = packet_pb2.DrawCard()
        pkg.cards.extend(draw_cards)
        for player in self.players:
            await game_vars.get_game_client().send_packet(player.uid, CMDs.DRAW_CARD, pkg)

    async def _handle_new_hand(self):
        self.current_hand += 1
        self.hand_suit = -1

        # next turn is the winner of last hand
        if self.win_player:
            self.current_turn = self.players.index(self.win_player)
        else:
            self.current_turn = 0

        self.time_auto_play = TIME_AUTO_PLAY + datetime.now().timestamp()

        pkg = packet_pb2.NewHand()
        pkg.current_turn = self.current_turn
        for player in self.players:
            await game_vars.get_game_client().send_packet(player.uid, CMDs.NEW_HAND, pkg)

    def _draw_card(self):
        card = self.cards.pop(0)
        return card


    def get_win_card_in_hand(self):
        # valid cards in hand, same defined suit
        cards_valid = []
        for card in self.cards_compare:
            if card % 4 == self.hand_suit:
                cards_valid.append(card)

        win_card = cards_valid[0]
        for card in cards_valid:
            if CARD_STRONGS[card // 4] > CARD_STRONGS[win_card // 4]:
                win_card = card
        return win_card

    def get_win_score_in_hand(self):
        total_score = 0
        for card in self.cards_compare:
            total_score += CARD_VALUES[card]
        return total_score

        

    async def end_game(self):
        self.state = MatchState.ENDED
        win_uids = [self.players[0].uid]
        score_totals = []
        score_last_tricks = []
        score_cards = []
        for player in self.players:
            score_cards.append(player.points - player.score_last_trick)
            score_last_tricks.append(player.score_last_trick)
            score_totals.append(player.points)
        # send to users
        pkg = packet_pb2.EndGame()
        print(f"End game, win_uids: {win_uids}")
        pkg.win_uids.extend(win_uids)
        pkg.score_cards.extend(score_cards)
        pkg.score_last_tricks.extend(score_last_tricks)
        pkg.score_totals.extend(score_totals)
        for player in self.players:
            await game_vars.get_game_client().send_packet(player.uid, CMDs.END_GAME, pkg)
        
        await asyncio.sleep(2)
        self.state = MatchState.WAITING

# Value mapping for Traditional Tresette (values multiplied by 3 to avoid floats)
CARD_VALUES = {
    0: 3, 1: 3, 2: 3, 3: 3,  # Aces (1 point * 3)
    4: 0, 5: 0, 6: 0, 7: 0,  # 2s
    8: 1, 9: 1, 10: 1, 11: 1,  # 3s (1 point * 3)
    12: 0, 13: 0, 14: 0, 15: 0,  # 4s
    16: 0, 17: 0, 18: 0, 19: 0,  # 5s
    20: 0, 21: 0, 22: 0, 23: 0,  # 6s
    24: 0, 25: 0, 26: 0, 27: 0,  # 7s
    28: 1, 29: 1, 30: 1, 31: 1,  # Jacks (1/3 point * 3 = 1)
    32: 1, 33: 1, 34: 1, 35: 1,  # Queens (1/3 point * 3 = 1)
    36: 1, 37: 1, 38: 1, 39: 1   # Kings (1/3 point * 3 = 1)
}

# Three (2) -> Two(1) -> ACE(0) -> King (9) -> Queen (8) -> Jack (7) -> 7 (6) -> 6 (5) -> 5 (4) -> 4 (3)
CARD_STRONGS = {
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