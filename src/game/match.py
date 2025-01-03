import asyncio
from enum import Enum
from datetime import datetime, timedelta
import logging
import random

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

        if player_mode == PLAYER_SOLO_MODE:
            for i in range(2):
                self.players.append(MatchPlayer(-1))
        elif player_mode == PLAYER_DUO_MODE:
            for i in range(4):
                self.players.append(MatchPlayer(-1))
        self.reset_logic_game()
    
    def reset_logic_game(self):
        self.current_turn = 0 
        self.state = MatchState.WAITING
        self.cards_compare.clear()
        for i in range(self.player_mode):
            self.cards_compare.append(-1)

        self.current_round = 0

        print(f"Player mode: {self.player_mode}")
        for i in range(self.player_mode):
            self.cards_compare.append(-1)
        
    def start_match(self):
        self.state = MatchState.PLAYING
        self.start_time = datetime.now()

    def end_match(self):
        self.state = MatchState.ENDED
        self.end_time = datetime.now()

    async def user_join(self, user_id):
        # check user in match
        for player in self.players:
            if player.uid == user_id:
                print('User already in match, can not jion')
                return
        
        # find empty slot
        for i, player in enumerate(self.players):
            if player.uid == -1:
                user_data = await users_info_mgr.get_user_info(user_id)
                self.players[i].uid = user_data.uid
                self.players[i].name = user_data.name
                self.players[i].gold = user_data.gold
                seat_server_id = i
                break

        # send to others that user has joined
        for i, player in enumerate(self.players):
            if player.uid == -1 or player.uid == user_id:
                continue
            print(f"Send to user {player.uid} that user {user_id} has joined")
            pkg = packet_pb2.NewUserJoinMatch()
            pkg.uid = user_id
            pkg.seat_server = seat_server_id

            i += 1

            await game_vars.get_game_client().send_packet(player.uid, CMDs.NEW_USER_JOIN_MATCH, pkg)
        
        await self._send_game_info(user_id)

        if all(player.uid != -1 for player in self.players):
            await self.start_game()

    def update_state(self):
        if self.state == MatchState.PLAYING:
            # Example: end match after 5 minutes
            if datetime.now() > self.start_time + timedelta(minutes=5):
                self.end_match()
        elif self.state == MatchState.WAITING:
            # Example: start match when all players are ready
            if all(player['ready'] for player in self.players):
                self.start_match()

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

        for player in self.players:
            game_info.uids.append(player.uid)
            # game_info.user_names.append(player.user_name)
            game_info.user_golds.append(player.gold)
            game_info.user_names.append(player.name)
            game_info.user_points.append(player.points)

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
        self.cards_compare.clear()
        for i in range(len(self.players)):
            self.cards_compare.append(-1)

        pkg = packet_pb2.StartGame()
        for player in self.players:
            await game_vars.get_game_client().send_packet(player.uid, CMDs.START_GAME, pkg)
        # wait for 3 seconds
        await asyncio.sleep(3)
        await self.deal_card()

    async def user_play_card(self, uid, payload):
        pkg = packet_pb2.PlayCard()
        pkg.ParseFromString(payload)
        card_id = pkg.card_id
        await self._play_card(uid, card_id, auto=False)
    
    async def _play_card(self, uid, card_id, auto=False):
        if self.state != MatchState.PLAYING:
            logger.error("Game is not in progress")
            return
        
        if await self.check_done_round():
            logger.error("Round is done, wait for next round")
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
        
        # check whether the card is valid

        # remove card from player
        print('remove card id: ', card_id)
        player.cards.remove(card_id)
        self.cards_compare[self.current_turn] = card_id
        self.current_turn = (self.current_turn + 1) % len(self.players)

        # send to others
        for i, player in enumerate(self.players):
            if not auto and player.uid == uid:
                continue

            pkg = packet_pb2.PlayCard()
            pkg.uid = uid
            pkg.card_id = card_id
            await game_vars.get_game_client().send_packet(player.uid, CMDs.PLAY_CARD, pkg)

        # Check done round
        is_finish_round = await self.check_done_round()
        if is_finish_round:
            self.current_turn = -1
            await asyncio.sleep(0.5)
            await self.end_round()

    async def check_done_round(self):
        for card in self.cards_compare:
            if card == -1:
                return False
        return True

    async def user_reconnect(self, uid):
       await self._send_game_info(uid)

    async def deal_card(self):
        if self.game_mode == TRESSETTE_MODE:
            # shuffle cards
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
        elif self.game_mode == BRISCOLA_MODE:
            pass

    async def end_round(self):
        win_card = self.get_win_card()
        win_player = self.players[self.cards_compare.index(win_card)]
        win_player.points += 1

        # reset round
        self.cards_compare.clear()
        for _ in range(self.player_mode):
            self.cards_compare.append(-1)

        self.current_round += 1

        pkg = packet_pb2.EndRound()
        # send to others
        for player in self.players:
            pkg.win_uid = win_player.uid
            pkg.win_card = win_card
            pkg.user_points.append(win_player.points)
            await game_vars.get_game_client().send_packet(player.uid, CMDs.END_ROUND, pkg)

        # check end game
        self.current_turn = 0
        if self.state == MatchState.PLAYING:
            # send new round
            await asyncio.sleep(1)
            pkg = packet_pb2.NewRound()
            pkg.current_turn = self.current_turn
            for player in self.players:
                await game_vars.get_game_client().send_packet(player.uid, CMDs.NEW_ROUND, pkg)

    def get_win_card(self):
        win_card = self.cards_compare[0]
        for card in self.cards_compare:
            if card > win_card:
                win_card = card
        return win_card

    async def end_game(self):
        pass