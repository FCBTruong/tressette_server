import asyncio
from enum import Enum
from datetime import datetime, timedelta, timezone
import logging
import random
import traceback
from abc import ABC, abstractmethod

from src.base.logs.logs_mgr import write_log
from src.base.network.connection_manager import connection_manager
from src.base.network.packets import packet_pb2
from src.config.settings import settings
from src.constants import *
from src.game import game_logic
from src.game.bot.minimax_tressette import find_optimal_card
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs
from src.game.game_vars import game_vars
from datetime import datetime, timedelta
from src.game.tressette_config import config as tress_config
import uuid
from src.game.modules import game_exp
from src.game.tressette_constants import *

class MatchState(Enum):
    WAITING = 0
    PREPARING_START = 1
    PLAYING = 2
    ENDING = 3
    ENDED = 4

class PlayCardErrors(Enum):
    SUCCESS = 0
    NOT_IN_GAME = 1
    NOT_YOUR_TURN = 2
    INVALID_CARD = 3
    NOT_FOUND_CARD = 4
    INVALID_SUIT = 5
    NOT_IN_HAND = 6

PLAYER_SOLO_MODE = 2
PLAYER_DUO_MODE = 4
TRESSETTE_MODE = 0
BRISCOLA_MODE = 1

SERVER_SCORE_ONE_POINT = 3

TIME_AUTO_PLAY = tress_config.get("time_thinking_in_turn")
TIME_AUTO_PLAY_SEVERE = min(3, TIME_AUTO_PLAY)
TAX_PERCENT = tress_config.get("tax_percent")
TIME_START_TO_DEAL = 3.5 # seconds
TIME_DRAW_CARD = 4 # seconds
TIME_MATCH_MAXIMUM = 60 * 60 # 1 hour -> after this match will be destroyed
SCORE_WIN_GAME_ELEVEN = 11 * SERVER_SCORE_ONE_POINT
SCORE_WIN_GAME_TWENTY_ONE = 21 * SERVER_SCORE_ONE_POINT
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
    def __init__(self, uid: int, match_mgr: "Match"):
        self.uid = uid
        self.name = ""
        self.avatar = ""
        self.gold = 0
        self.cards = [] # id of cards
        self.points = 0
        self.score_last_trick = 0
        self.team_id = -1
        self.is_bot = False
        self.match_mgr = match_mgr
        self.gold_change = 0
        self.is_in_game = False

    
    def reset_game(self):
        self.cards.clear()
        self.points = 0
        self.score_last_trick = 0

    async def on_turn(self):
        pass

    async def auto_play(self):
        if len(self.cards) == 0:
            return
        card_id = self.cards[0]
        cur_hand_suit = self.match_mgr.hand_suit
        if cur_hand_suit != -1:
            # find suitable card
            for card in self.cards:
                if card % 4 == cur_hand_suit:
                    card_id = card
                    break

        await self.match_mgr._play_card(self.uid, card_id=card_id, auto=True)
    
    def random_chat(self):
        pass

class MatchBot(MatchPlayer):
    bot_model = 'C'
    def __init__(self, uid, match_mgr):
        super().__init__(uid, match_mgr)
        self.is_bot = True

    async def on_turn(self):
        print('Bot on turn')
        # play a card
        if len(self.cards) == 0:
            return
        card_id = self.get_card_to_play()
        # wait for 1 second
        time_thinking = random.randrange(1, 3)
        await asyncio.sleep(time_thinking)
        await self.match_mgr._play_card(self.uid, card_id=card_id, auto=False)

        # send back to client current cards for testing
        if settings.ENABLE_CHEAT:
            await self._send_cheat_view_card()
    
    async def _send_cheat_view_card(self):
        print('Send cheat view card')
        pkg = packet_pb2.CheatViewCardBot()
        pkg.cards.extend(self.cards)
        await self.match_mgr.broadcast_pkg(CMDs.CHEAT_VIEW_CARD_BOT, pkg)
    
    def get_card_to_play(self) -> int:
        card_id = self.cards[0]
        cur_hand_suit = self.match_mgr.hand_suit
        if cur_hand_suit != -1:
            # find suitable card
            for card in self.cards:
                if card % 4 == cur_hand_suit:
                    card_id = card
                    break
        return card_id
    
    def random_chat(self):
        if random.random() < 0.1:  # 10% chance to send a chat
            async def delayed_chat():
                await asyncio.sleep(random.uniform(0.5, 3))  # Random delay between 0.5s and 3s
                await self.match_mgr.broadcast_chat_emoticon(self.uid, random.choice(CHAT_EMO_IDS))
            
            asyncio.create_task(delayed_chat())  # Run in background

    
class MatchBotIntermediate(MatchBot):
    bot_model = 'A'
    def get_card_to_play(self) -> int:
        cards_on_table = [card for card in self.match_mgr.cards_compare if card != -1]

        if not cards_on_table:
            return self.cards[0]  # Play the first card if nothing is on the table

        strong_card = max(cards_on_table, key=lambda c: TRESSETTE_CARD_STRONGS[c // 4])

        cur_hand_suit = self.match_mgr.hand_suit
        cards_valid = [card for card in self.cards if card % 4 == cur_hand_suit]

        if not cards_valid:
            weakest_card = min(self.cards, key=lambda c: (TRESSETTE_CARD_VALUES[c], TRESSETTE_CARD_STRONGS[c // 4]))
            return weakest_card

        # Find the smallest valid card
        min_card = min(cards_valid, key=lambda c: TRESSETTE_CARD_VALUES[c])

        # Find the smallest card that can win
        winning_cards = [card for card in cards_valid if TRESSETTE_CARD_STRONGS[card // 4] > TRESSETTE_CARD_STRONGS[strong_card // 4]]

        return min(winning_cards, key=lambda c: TRESSETTE_CARD_VALUES[c]) if winning_cards else min_card

class MatchBotAdvance(MatchBot):
    bot_model = 'B'
    def _pick_best_card(self):
        try :
            print("_pick_best_card")
            opponent = None
            for p in self.match_mgr.players:
                if p.uid != self.uid:
                    opponent = p
                    break
            opponent_cards = opponent.cards
            should_player_card = game_logic.pick_winning_card_first(self.cards, opponent_cards)
            # play card that can win, if can not win, play weakest and smallest card
            return should_player_card

        except Exception as e:
            print(e)
            return self.cards[0]
    
    def get_card_to_play(self) -> int:
        cards_on_table = [card for card in self.match_mgr.cards_compare if card != -1]

        if not cards_on_table:
            return self._pick_best_card()  # Play the first card if nothing is on the table

        strong_card = max(cards_on_table, key=lambda c: TRESSETTE_CARD_STRONGS[c // 4])

        cur_hand_suit = self.match_mgr.hand_suit
        cards_valid = [card for card in self.cards if card % 4 == cur_hand_suit]

        if not cards_valid:
            weakest_card = min(self.cards, key=lambda c: (TRESSETTE_CARD_VALUES[c], TRESSETTE_CARD_STRONGS[c // 4]))
            return weakest_card

        # Find the smallest valid card
        min_card = min(cards_valid, key=lambda c: TRESSETTE_CARD_VALUES[c])

        # Find the smallest card that can win
        winning_cards = [card for card in cards_valid if TRESSETTE_CARD_STRONGS[card // 4] > TRESSETTE_CARD_STRONGS[strong_card // 4]]

        return min(winning_cards, key=lambda c: TRESSETTE_CARD_VALUES[c]) if winning_cards else min_card

class MatchBotSuper(MatchBot):
    bot_model = 'D'
   
    
    def get_card_to_play(self) -> int:
        # only for solo mode
        bot_cards = self.cards.copy()
        opp_cards = []
        for p in self.match_mgr.players:
            if p.uid != self.uid:
                opp_cards = p.cards.copy()
                break
        bot_future_cards = []
        opp_future_cards = []
        i = 0
        for c in self.match_mgr.cards:
            if i % 2 == 0:
                opp_future_cards.append(c)
            else:
                bot_future_cards.append(c)
            i += 1
        if len(self.match_mgr.cards_compare) > 0:
            current_card = self.match_mgr.cards_compare[0]
        else:
            current_card = None

        if current_card == -1:
            current_card = None
        
        bot_score = self.match_mgr.team_scores[self.team_id]
        player_score = self.match_mgr.team_scores[1 - self.team_id]
        leading_player = 'player' if current_card is not None else 'bot'
        max_depth = 3
        if settings.DEV_MODE:
            print("leading_player", leading_player)
            print("bot_score", bot_score)
            print("player_score", player_score)
            print("bot_cards", bot_cards)
            print("opp_cards", opp_cards)
            print("bot_future_cards", bot_future_cards)
            print("opp_future_cards", opp_future_cards)
            print("current_card", current_card)
            print("max_depth", max_depth)
            print("point_to_win", self.match_mgr.point_to_win)

        card = find_optimal_card(
            leading_player,
            self.match_mgr.team_scores[self.team_id],
            self.match_mgr.team_scores[1 - self.team_id], 
            bot_cards, opp_cards, bot_future_cards, opp_future_cards,
            get_suit=get_suit,
            get_score=get_score,
            get_stronger_card=get_stronger_card,
            point_to_win=self.match_mgr.point_to_win,
            leading_card=current_card,
            max_depth=max_depth,
            )
        return card
  

class Match(ABC):
    players: list[MatchPlayer]
    @abstractmethod
    async def user_play_card(self, uid, payload):
        pass

    @abstractmethod
    async def user_join(self, user_id, is_bot=False):
        pass

    @abstractmethod
    async def user_leave(self, uid, reason = 0):
        pass

    @abstractmethod
    async def user_reconnect(self, uid):
        pass

    @abstractmethod
    async def loop(self):
        pass

    @abstractmethod
    async def broadcast_chat_emoticon(self, uid, emoticon):
        pass

    @abstractmethod
    async def broadcast_chat_message(self, uid, message):
        pass

    @abstractmethod
    def user_return_to_table(self, uid):
        pass

    @abstractmethod
    def user_ready(self, uid):
        pass

    @abstractmethod
    def check_room_full(self) -> bool:
        pass

class TressetteMatch(Match):
    def __init__(self, match_id, bet, player_mode, point_mode):
        self.match_id = match_id
        self.start_time = datetime.now()
        self.end_time = None
        self.game_mode = TRESSETTE_MODE
        self.player_mode = player_mode
        self.players: list[MatchPlayer] = []
        self.cards = []
        self.win_player = None
        self.hand_suit = -1
        self.bet = bet
        self.auto_play_count_by_uid = {} # consecutive auto play count
        self.users_auto_play = {} # uids that are auto play, server will not wait for them
        self.state = MatchState.WAITING
        self.current_turn = -1
        self.register_leave_uids = set()
        self.win_team = -1
        self.team_scores = [0, 0]
        self.pot_value = 0
        self.cur_round = 0
        self.is_end_round = False
        self.unique_match_id = str(uuid.uuid4())
        self.cards_compare = []
        self.task_gen_bot = None
        self.unique_game_id = ""
        self.is_public = True
        self.napoli_claimed_status = {}
        self.hand_in_round = -1
        self.enable_bet_win_score = True
        self.game_ready = True
        self.user_ready_status = {}

        
        self.point_to_win = point_mode * 3 # 11, 21

        # init slots
        for i in range(player_mode):
            p = MatchPlayer(-1, self)
            self.players.append(p)

    def set_public(self, is_public):
        self.is_public = is_public
    
    async def loop(self):
        try:
            if self.state == MatchState.PLAYING:
                # check overtime
                if datetime.now() - self.start_time > timedelta(seconds=TIME_MATCH_MAXIMUM):
                    await self.end_game()
                    return
                
                # check auto play
                if self.current_turn != -1 and self.time_auto_play != -1 and datetime.now().timestamp() > self.time_auto_play:
                    player = self.players[self.current_turn]
                    if player:
                        await player.auto_play()
            elif self.state == MatchState.PREPARING_START:
                if self.time_start != -1 and datetime.now().timestamp() > self.time_start:
                    if self.check_room_full():
                        await self.start_game()
                    else:
                        self.state = MatchState.WAITING
                        self.time_start = -1
            elif self.state == MatchState.WAITING:
                if self.game_ready and self.check_room_full():
                    await self._prepare_start_game()
        except Exception as e:
            traceback.print_exc()
            raise e

    async def user_join(self, user_id, is_bot=False):
        # check user in match
        for player in self.players:
            if player.uid == user_id:
                print('User already in match, can not jion')
                return
        if not is_bot:
            user_data = await users_info_mgr.get_user_info(user_id)
        else:
            user_data = game_vars.get_bots_mgr().fake_data_for_bot(user_id, self.bet)

        # find empty slot
        slot_idx = -1   
        for i, player in enumerate(self.players):
            if player.uid == -1:
                slot_idx = i
                break
        if slot_idx == -1:
            print('Match is full')
            return
        
        self.user_ready_status[user_id] = True
        if is_bot:
            bot_model = 0 # bot medium

            if self.player_mode == PLAYER_SOLO_MODE:
                # get info user to decide bot model
                for player in self.players:
                    if player.uid != -1 and not player.is_bot:
                        user_info = await users_info_mgr.get_user_info(player.uid)
                        win_rate = 0
                        if user_info.game_count > 0:
                            win_rate = user_info.win_count * 1.0 / user_info.game_count

                        # BOT 0: Medium, BOT 2: Stupid, BOT 1: Hard
                        if user_info.game_count == 0:
                            bot_model = 2 # bot 2 is stupid
                        elif user_info.game_count < 5:
                            if win_rate > 0.5:
                                bot_model = 0
                            else:
                                bot_model = 2
                        else:
                            if win_rate > 0.3:
                                bot_model = random.choice([0, 3])
                            else:
                                bot_model = 2
                        break
            else:
                bot_model = 0 # currently only one model for duo mode

            if bot_model == 0:
                print("bot model medium...")
                match_player = MatchBotIntermediate(user_id, self)
            elif bot_model == 2:
                print("bot model stupid...")
                match_player = MatchBot(user_id, self)
            elif bot_model == 3:
                print("bot model super...")
                match_player = MatchBotSuper(user_id, self)
            else:
                print("bot model advance...")
                match_player = MatchBotAdvance(user_id, self)
            
            if settings.DEV_MODE:
                match_player = MatchBotSuper(user_id, self)

        else:
            match_player = MatchPlayer(user_id, self)

        match_player.name = user_data.name
        match_player.gold = user_data.gold
        match_player.avatar = user_data.avatar
        # calculate team id
        if self.player_mode == PLAYER_SOLO_MODE:
            match_player.team_id = slot_idx
        else:
            match_player.team_id = slot_idx % 2

        seat_server_id = slot_idx
        self.players[slot_idx] = match_player
        team_id = match_player.team_id

        pkg = packet_pb2.NewUserJoinMatch()
        pkg.uid = user_id
        pkg.name = user_data.name
        pkg.seat_server = seat_server_id
        pkg.team_id = team_id
        pkg.avatar = user_data.avatar
        pkg.gold = user_data.gold
        pkg.is_vip = await users_info_mgr.check_user_vip(user_id)

        if settings.DEV_MODE:
            pkg.is_vip = True

        await self.broadcast_pkg(CMDs.NEW__USER_JOIN_MATCH, pkg, ignore_uids=[user_id])
        
        if not is_bot:
            # send game info to user
            await self._send_game_info(user_id)

        if self.state == MatchState.WAITING:
            if self.check_room_full():
                self._clear_coroutine_gen_bot()
            else:
                await self._check_and_gen_bot()

    async def _check_and_gen_bot(self):
        print("check and gen bott")
        if not self.is_public:
            return
        print("check and g2en bott")
        
        if self.state != MatchState.WAITING:
            return
        
        if self.bet > 0:
            max_bet_to_gen_bot = tress_config.get('max_bet_to_gen_bot') if self.player_mode == PLAYER_SOLO_MODE else tress_config.get('max_bet_to_gen_bot_duo')
            if self.bet > max_bet_to_gen_bot:
                return
            
            ccu = await game_vars.get_game_live_performance().get_ccu()
            if ccu > tress_config.get('ccu_to_gen_bot'):
                return # not gen bot if ccu > 100
            
        print("check and3 g2en bott")
        if self.task_gen_bot is not None:
            self.task_gen_bot.cancel()

        print("check and g2en 2bott")
        time_delay_gen_bot = await self._get_ideal_delay_bot_time()
        self.task_gen_bot = asyncio.create_task(self._coroutine_gen_bot(time_delay_gen_bot))
    
    async def _get_ideal_delay_bot_time(self):
        # only for solo mode
        # get user 
        user_info = None
        for player in self.players:
            if player.uid != -1 and not player.is_bot:
                user_info = await users_info_mgr.get_user_info(player.uid)
                break
        if not user_info:
            return 5
        
        if settings.DEV_MODE:
            return 1
        
        if self.player_mode != PLAYER_SOLO_MODE:
            return random.randint(10, 50)
        
        if user_info.game_count < 1: # New user will play withbot
            return 1
        elif user_info.game_count > 10:
            return random.randint(15, 30)
        elif user_info.game_count > 20:
            return random.randint(20, 50)
        return random.randint(10, 15)
    
    async def _coroutine_gen_bot(self, time_delay_gen_bot):
        await asyncio.sleep(time_delay_gen_bot)
        bot_uid = game_vars.get_bots_mgr().get_free_bot_uid()
        await self.user_join(bot_uid, is_bot=True)

    def _clear_coroutine_gen_bot(self):
        if self.task_gen_bot is not None:
            self.task_gen_bot.cancel()
            self.task_gen_bot = None

    async def _prepare_start_game(self):
        # before really start game, check if all players are ready
        # check if all players are ready
        is_all_ready = True
        for player in self.players:
            if player.uid == -1 or player.is_bot:
                continue
            if not self.user_ready_status.get(player.uid, False):
                print('Not all players are ready')
                is_all_ready = False
                # Kick user out of match
                await game_vars.get_match_mgr().handle_user_leave_match(player.uid)  
                continue
        if not is_all_ready:
            print('Not all players are ready')
            return
        
        self.state = MatchState.PREPARING_START
        self.time_start = datetime.now().timestamp() + TIME_START_TO_DEAL
        # Send to all players that game is starting, wait for 3 seconds
        pkg = packet_pb2.PrepareStartGame()
        pkg.time_start = int(self.time_start)
        print('Game is starting, wait for 3 seconds')

        await self.broadcast_pkg(CMDs.PREPARE_START_GAME, pkg)


    def check_can_join(self, uid: int):
        if self.state == MatchState.WAITING:
            return True
        return False
    
    def get_min_gold_play(self):
        return self.bet * tress_config.get('bet_multiplier_min')
    
    def check_room_full(self) -> bool:
        for player in self.players:
            if player.uid == -1:
                return False
        return True
    
    def check_room_empty(self):
        for player in self.players:
            if player.uid != -1:
                return False
        return True
    
    def check_has_real_players(self):
        for player in self.players:
            if player.uid != -1 and not player.is_bot:
                return True
        return False
    
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
        game_info.is_registered_leave = uid in self.register_leave_uids
        game_info.bet = self.bet
        game_info.pot_value = self.pot_value
        game_info.current_round = self.cur_round
        game_info.hand_in_round = self.hand_in_round
        game_info.point_to_win = self.point_to_win
        game_info.enable_bet_win_score = self.enable_bet_win_score

        for player in self.players:
            game_info.uids.append(player.uid)
            game_info.user_golds.append(player.gold)
            game_info.user_names.append(player.name)
            game_info.user_points.append(player.points)
            game_info.team_ids.append(player.team_id)
            game_info.avatars.append(player.avatar)
            
            is_player_vip = await users_info_mgr.check_user_vip(player.uid)
            game_info.is_vips.append(is_player_vip)

            if player.uid == uid:
                game_info.my_cards.extend(player.cards)
        
        await game_vars.get_game_client().send_packet(uid, CMDs.GAME_INFO, game_info)

    # ALERT: This function is called from match_mgr
    async def user_leave(self, uid, reason = 0):
        pkg = packet_pb2.UserLeaveMatch()
        pkg.uid = uid
        pkg.reason = reason
        await self.broadcast_pkg(CMDs.USER_LEAVE_MATCH, pkg)

        # remove user from match
        for i, player in enumerate(self.players):
            if player.uid == uid:
                self.players[i] = MatchPlayer(-1, self)
                break

        if not self.check_room_full() and self.state == MatchState.PREPARING_START:
            self.state = MatchState.WAITING
            self.time_start = -1

        await self._check_and_gen_bot()

    async def start_game(self):
        self.unique_game_id = str(uuid.uuid4())
        # write logs
        for player in self.players:
            if player.is_bot or player.uid == -1:
                continue
            write_log(player.uid, "start_game", "", [self.unique_match_id, self.unique_game_id, self.bet, \
                                                                              self.player_mode, self.game_mode])

        print('Start game')
        self.state = MatchState.PLAYING
        self.game_ready = False
        self.user_ready_status.clear()
        self.start_time = datetime.now()
        self.current_turn = 0
        self.current_hand = -1
        self.time_auto_play = -1
        self.cards_compare.clear()
        self.hand_suit = -1
        self.win_player = None
        self.win_card = -1
        self.win_score = 0
        self.auto_play_count_by_uid.clear()
        self.register_leave_uids.clear()
        self.win_team = -1
        self.team_scores = [0, 0]
        self.pot_value = 0
        self.cur_round = 1
        self.is_end_round = False
        self.napoli_claimed_status.clear()
        self.hand_in_round = -1

        # Init player golds
        for player in self.players:
            if player.is_bot:
                continue
            p_info = await users_info_mgr.get_user_info(player.uid)
            player.gold = p_info.gold

        # reset players scores:
        for player in self.players:
            player.points = 0
            player.score_last_trick = 0
            player.cards.clear()
            player.gold_change = 0

            # get pot user need to contribute
            pot_user_need_to_contribute = self.bet

            # add to debt, to remove later
            if not player.is_bot:
                game_vars.get_debt_mgr().add_debt_ingame(player.uid, pot_user_need_to_contribute)
            player.gold -= pot_user_need_to_contribute

            self.pot_value += pot_user_need_to_contribute
            player.gold_change -= pot_user_need_to_contribute

        for i in range(len(self.players)):
            self.cards_compare.append(-1)

        players_gold = []
        for player in self.players:
            players_gold.append(player.gold)

        pkg = packet_pb2.StartGame()
        pkg.pot_value = self.pot_value
        pkg.players_gold.extend(players_gold)

        await self.broadcast_pkg(CMDs.START_GAME, pkg)

        # effect put pot value
        await asyncio.sleep(3 if self.bet > 0 else 1)
        await self.deal_card()

        # wait for 2 seconds
        await asyncio.sleep(2)
        await self._handle_new_hand()

    async def user_play_card(self, uid, payload):
        print(f"Receive play card from user {uid}")
        pkg = packet_pb2.PlayCard()
        pkg.ParseFromString(payload)
        card_id = pkg.card_id
        await self._play_card(uid, card_id, auto=False)
    
    async def _send_card_play_response(self, uid, status: PlayCardErrors):
        pkg = packet_pb2.PlayCardResponse()
        pkg.status = status.value
        await game_vars.get_game_client().send_packet(uid, CMDs.PLAY_CARD_RESPONSE, pkg)

    async def _play_card(self, uid, card_id, auto=False):
        # # test
        # await self.end_game()
        # return
        if self.state != MatchState.PLAYING:
            logger.error("Game is not in progress")
            await self._send_card_play_response(uid, PlayCardErrors.NOT_IN_GAME)
            return
        
        if self.check_done_hand():
            logger.error("hand is done, wait for next hand")
            await self._send_card_play_response(uid, PlayCardErrors.NOT_IN_HAND)
            return
    

        # check whether it is user turn
        if self.current_turn == -1 or self.players[self.current_turn].uid != uid:
            logger.error(f"User {uid} is not in turn, current turn: {self.current_turn}, user turn: {self.players[self.current_turn].uid}")
            await self._send_card_play_response(uid, PlayCardErrors.NOT_YOUR_TURN)
            return
        
        # check whether user has the card
        player = self.players[self.current_turn]
        if card_id not in player.cards:
            logger.error(f"User {uid} does not have card {card_id}")
            await self._send_card_play_response(uid, PlayCardErrors.NOT_FOUND_CARD)
            return
        
        if self.hand_suit == -1:
            self.hand_suit = card_id % 4
        else:
            card_suit = card_id % 4
            if card_suit != self.hand_suit:
                for card in player.cards:
                    if card % 4 == self.hand_suit:
                        logger.error(f"User {uid} must play card with suit {self.hand_suit}")
                        await self._send_card_play_response(uid, PlayCardErrors.INVALID_SUIT)
                        return

        # Now user can play card
        if not auto:
            self.users_auto_play.pop(uid, None)
            self.auto_play_count_by_uid.pop(uid, None)
        else:
            self.auto_play_count_by_uid[uid] = self.auto_play_count_by_uid.get(uid, 0) + 1
            if self.auto_play_count_by_uid[uid] >= 3:
                self.users_auto_play[uid] = True
            
        # remove card from player
        print('remove card id: ', card_id, ' auto: ', auto)
        player.cards.remove(card_id)
        self.cards_compare[self.current_turn] = card_id
        self.time_auto_play = -1

        is_finish_hand = self.check_done_hand()
        if not is_finish_hand:
            self.current_turn = (self.current_turn + 1) % len(self.players)
        else:
            self.current_turn = -1
    
        # send to others
        pkg = packet_pb2.PlayCard()
        pkg.uid = uid
        pkg.card_id = card_id
        pkg.auto = auto
        pkg.current_turn = self.current_turn
        pkg.hand_suit = self.hand_suit

        # Check done hand
        if is_finish_hand:
            print('Finishhand, end hand')

            # add some information to package PlayCard (is end hand, who win, win point ...)
            await self.end_hand(pkg)
        else:
            await self.broadcast_pkg(CMDs.PLAY_CARD, pkg)

            # next uid
            next_uid = self.players[self.current_turn].uid
            await self.players[self.current_turn].on_turn()

            if next_uid in self.users_auto_play:
                # people that are auto play
                self.time_auto_play = TIME_AUTO_PLAY_SEVERE + datetime.now().timestamp()
            else:
                # normal people
                self.time_auto_play = TIME_AUTO_PLAY + datetime.now().timestamp()

    def check_done_hand(self):
        for card in self.cards_compare:
            if card == -1:
                return False
        return True

    async def user_reconnect(self, uid):
       # remove state auto play if has
       self.auto_play_count_by_uid.pop(uid, None)
       self.users_auto_play.pop(uid, None)

       await self._send_game_info(uid)

    async def deal_card(self):
        self.cards = TRESSETTE_CARDS.copy()
        random.shuffle(self.cards)
        print(f"Cards: {self.cards}")
        for i, player in enumerate(self.players):
            player.cards = self.cards[i*10: (i+1)*10]

        # TEST CARDS, DONT USE THIS FUNCTION LIVE
        # if settings.DEV_MODE:
        #     self.players[0].cards = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        
        # remove cards dealt
        self.cards = self.cards[10 * len(self.players):]

        # send to users
        for player in self.players:
            # do not send to bots
            if player.is_bot:
                continue
            pkg = packet_pb2.DealCard()
            pkg.cards.extend(player.cards)
            pkg.remain_cards = len(self.cards)
            await game_vars.get_game_client().send_packet(player.uid, CMDs.DEAL_CARD, pkg)
    

    async def end_hand(self, play_card_pkg):
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

        # check is end round
        if len(self.players[0].cards) == 0: # test = 9
            # logic end round
            self.is_end_round = True
        else:
            self.is_end_round = False
            # if settings.DEV_MODE:
            #     self.is_end_round = True
        
        if self.is_end_round:
            # calculate last trick
            #BONUS 1 point for the last trick to the team that wins it
            win_player.points += 3
            win_player.score_last_trick += 3

        play_card_pkg.is_end_hand = True
        play_card_pkg.win_uid = win_player.uid
        play_card_pkg.win_card = win_card
        play_card_pkg.win_point = win_score
        play_card_pkg.is_end_round = self.is_end_round
        await self.broadcast_pkg(CMDs.PLAY_CARD, play_card_pkg)

        # this end hand packet will not use in the future
        pkg = packet_pb2.EndHand()
        pkg.is_end_round = self.is_end_round
        pkg.win_uid = win_player.uid
        pkg.win_card = win_card
        pkg.win_point = win_score
        for player in self.players:
            pkg.user_points.append(player.points)

        # send to others
        await asyncio.sleep(0.5)

        await self.broadcast_pkg(CMDs.END_HAND, pkg)

        # effect show win cards
        await asyncio.sleep(2)
        
        # # draw new cards
        if self._is_end_game():
            await self.end_game()
            return
        
        if not self.is_end_round:
            # Still has cards to draw
            if len(self.cards) > 0:
                await self._handle_draw_card()
                await asyncio.sleep(TIME_DRAW_CARD)
            await self._handle_new_hand()
        else:
            # create new round
            await self._on_end_round()

        for p in self.players:
            if p.is_bot:
                p.random_chat()
    
    async def _on_end_round(self):
        # wait for 2 seconds
        await asyncio.sleep(2)
        await self._on_new_round()

    async def _on_new_round(self):
        self.cur_round += 1
        self.is_end_round = False
        self.napoli_claimed_status.clear()
        self.hand_in_round = -1

        # When new round start, all redudant points need to be removed, example 3, 1/3 -> 3, 4 2/3 -> 4
        for player in self.players:
            redundant_points = player.points % 3
            player.points -= redundant_points

        players_gold = []
        # players need to contribute to pot again
        for player in self.players:
            # get pot user need to contribute
            pot_user_need_to_contribute = self.bet
            self.pot_value += pot_user_need_to_contribute
            player.gold_change -= pot_user_need_to_contribute

            player.gold -= pot_user_need_to_contribute
            if not player.is_bot:
                game_vars.get_debt_mgr().add_debt_ingame(player.uid, pot_user_need_to_contribute)

            players_gold.append(player.gold)

        # Send new round
        pkg = packet_pb2.NewRound()
        pkg.current_round = self.cur_round
        pkg.pot_value = self.pot_value
        pkg.players_gold.extend(players_gold)

        await self.broadcast_pkg(CMDs.NEW_ROUND, pkg)

        await asyncio.sleep(3 if self.bet > 0 else 1)
        await self.deal_card()
        await asyncio.sleep(2)
        await self._handle_new_hand()

    def _is_end_game(self):
        # check if one team reach 21 * 3 points then end game
        self.team_scores = [0, 0]
        for player in self.players:
            self.team_scores[player.team_id] += player.points
        # if settings.DEV_MODE:
        #     return True
        
        if self.team_scores[0] >= self.point_to_win or self.team_scores[1] >= self.point_to_win:
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

        await self.broadcast_pkg(CMDs.DRAW_CARD, pkg)

    async def _handle_new_hand(self):
        self.current_hand += 1
        self.hand_suit = -1
        self.hand_in_round += 1

        # next turn is the winner of last hand
        if self.win_player is not None:
            self.current_turn = self.players.index(self.win_player)
        else:
            self.current_turn = 0

        if self.win_player and self.win_player.uid in self.users_auto_play:
            # people that are auto play
            self.time_auto_play = TIME_AUTO_PLAY_SEVERE + datetime.now().timestamp()
        else:
            self.time_auto_play = TIME_AUTO_PLAY + datetime.now().timestamp()

        print(f"New hand")
        pkg = packet_pb2.NewHand()
        pkg.current_turn = self.current_turn

        await self.broadcast_pkg(CMDs.NEW_HAND, pkg)

        await self.players[self.current_turn].on_turn()

    def _draw_card(self):
        card = self.cards.pop(0)
        return card

    def can_quit_game(self):
        return self.state == MatchState.WAITING or self.state == MatchState.PREPARING_START
    
    def get_win_card_in_hand(self):
        # valid cards in hand, same defined suit
        cards_valid = []
        for card in self.cards_compare:
            if card % 4 == self.hand_suit:
                cards_valid.append(card)

        win_card = cards_valid[0]
        for card in cards_valid:
            if TRESSETTE_CARD_STRONGS[card // 4] > TRESSETTE_CARD_STRONGS[win_card // 4]:
                win_card = card
        return win_card

    def get_win_score_in_hand(self):
        total_score = 0
        for card in self.cards_compare:
            total_score += TRESSETTE_CARD_VALUES[card]
        return total_score

        

    async def end_game(self):
        self.state = MatchState.ENDED

        if self.team_scores[0] > self.team_scores[1]:
            self.win_team = 0
        else:
            self.win_team = 1

        diff_score = abs(self.team_scores[0] - self.team_scores[1]) // 3
        total_team_lose_pay = 0

        if self.enable_bet_win_score:
            for player in self.players:
                if player.team_id != self.win_team:
                    glose = min(player.gold, self.bet * diff_score)
                    total_team_lose_pay += glose
                    player.gold -= glose
                    player.gold_change -= glose
                    game_vars.get_debt_mgr().add_debt_ingame(player.uid, glose)

        gold_win_score_one_player = int(total_team_lose_pay // (self.player_mode / 2))

        pot_received_one_player = int(self.pot_value // (self.player_mode / 2))

        # add gold
        for player in self.players:
            if player.team_id == self.win_team:
                gold_win = pot_received_one_player + gold_win_score_one_player
                gold_received = int(gold_win - gold_win * TAX_PERCENT)
                player.gold += gold_received
                player.gold_change += gold_win
        
            if player.uid == -1 or player.is_bot:
                is_bot_win = '0'
                if player.team_id == self.win_team:
                    is_bot_win = '1'
                write_log(-1, "end_game_bot", player.bot_model, [is_bot_win, self.unique_match_id, self.unique_game_id, self.bet])
                continue

            user_info = await users_info_mgr.get_user_info(player.uid)
            user_info.game_count += 1
            added_exp = int(game_exp.calculate_exp_gain(self.bet))

            if player.team_id == self.win_team:
                user_info.add_gold(gold_received)
                user_info.win_count += 1
                added_exp = added_exp * 2

                await game_vars.get_ranking_mgr().on_user_win_game(player.uid)

            user_info.add_exp(added_exp)
            gold_debt = game_vars.get_debt_mgr().get_debt_ingame(player.uid)
            user_info.add_gold(-gold_debt)
            # reset debt
            game_vars.get_debt_mgr().remove_debt_ingame(player.uid)

            await user_info.commit_to_database('gold', 'game_count', 'win_count', 'exp')
            await user_info.send_update_money()
            write_log(player.uid, "end_game", "", [self.unique_match_id, self.unique_game_id, self.bet, player.gold_change])

        uids = []
        score_totals = []
        score_last_tricks = []
        score_cards = []
        gold_changes = []
        players_gold = []
        for player in self.players:
            uids.append(player.uid)
            score_cards.append(player.points - player.score_last_trick)
            score_last_tricks.append(player.score_last_trick)
            score_totals.append(player.points)
            gold_changes.append(player.gold_change)
            players_gold.append(player.gold)

        
        # send to users
        pkg = packet_pb2.EndGame()
        pkg.win_team_id = self.win_team
        pkg.uids.extend(uids)
        pkg.score_cards.extend(score_cards)
        pkg.score_last_tricks.extend(score_last_tricks)
        pkg.score_totals.extend(score_totals)
        pkg.gold_changes.extend(gold_changes)
        pkg.players_gold.extend(players_gold)
        pkg.gold_win_score = gold_win_score_one_player

        await self.broadcast_pkg(CMDs.END_GAME, pkg)
        
        await asyncio.sleep(3)

        self.state = MatchState.WAITING
        # for user register exit room, or auto play, or disconnect
        await self.update_users_staying_endgame() 

        #reset game: score
        for player in self.players:
            player.points = 0
            player.cards.clear()

        # next game
        await asyncio.sleep(9)
        self.game_ready = True

    async def update_users_staying_endgame(self):
        # Remove all bots
        for i, player in enumerate(self.players):
            if player.is_bot:
                should_remove_bot = True
                if self.player_mode == PLAYER_DUO_MODE:
                    # mode 2v2, remove randomly
                    should_remove_bot = random.randint(0, 1) == 0
                else:
                    should_remove_bot = random.randint(0, 1) == 0
                if player.gold < self.get_min_gold_play():
                    should_remove_bot = True
                if should_remove_bot:
                    await self.user_leave(player.uid)
                    # clean bot data
                    game_vars.get_bots_mgr().destroy_bot(player.uid)
            
                
        # Kick users auto playing, or register exit room
        for uid in self.register_leave_uids:
            await game_vars.get_match_mgr().handle_user_leave_match(uid)    

        # kick user auto playing consecutively more than 3 times
        for uid in self.users_auto_play:
            await game_vars.get_match_mgr().handle_user_leave_match(uid)

        # Kick user not has enough gold
        for player in self.players:
            if player.is_bot:
                continue
            if player.uid == -1:
                continue
            user_info = await users_info_mgr.get_user_info(player.uid)
            if user_info.gold < self.get_min_gold_play():
                await game_vars.get_match_mgr().handle_user_leave_match(player.uid, REASON_KICK_NOT_ENOUGH_GOLD)
    
        # update user connection, kick user that is disconnected
        for player in self.players:
            # not check for bots
            if player.is_bot:
                continue
            uid = player.uid
            if uid == -1:
                continue
            is_active = connection_manager.check_user_active_online(uid)
            if not is_active:
                await game_vars.get_match_mgr().handle_user_leave_match(uid)
    
    async def broadcast_pkg(self, cmd_id, pkg, ignore_uids=[]):
        for player in self.players:
            if player.is_bot or player.uid == -1:
                continue
            if player.uid in ignore_uids:
                continue
            await game_vars.get_game_client().send_packet(player.uid, cmd_id, pkg)

    async def broadcast_chat_message(self, uid, message):
        pkg = packet_pb2.InGameChatMessage()
        pkg.uid = uid
        pkg.chat_message = message

        await self.broadcast_pkg(CMDs.NEW_INGAME_CHAT_MESSAGE, pkg, ignore_uids=[uid])

    async def broadcast_chat_emoticon(self, uid, emoticon):
        pkg = packet_pb2.InGameChatEmoticon()
        pkg.uid = uid
        pkg.emoticon = emoticon

        await self.broadcast_pkg(CMDs.CHAT_EMOTICON, pkg)

    def register_leave(self, uid):
        print(f"User {uid} register leave")
        self.register_leave_uids.add(uid)

    def deregister_leave(self, uid):
        self.register_leave_uids.discard(uid)

    def get_num_players(self):
        count = 0
        for player in self.players:
            if player.uid != -1:
                count += 1
        return count

    async def cheat_add_bot(self):
        if settings.ENABLE_CHEAT:
            bot_uid = game_vars.get_bots_mgr().get_free_bot_uid()
            await self.user_join(bot_uid, is_bot=True)

    async def receive_game_action_napoli(self, uid, payload):
        if self.napoli_claimed_status.get(uid):
            return
    
        p = None
        for player in self.players:
            if player.uid == uid:
                p = player
                break
        if p is None:
            return
        napoli_sets = self.find_napoli(p.cards)
        if len(napoli_sets) == 0:
            return
        
        napoli_suits = []
        for napoli_set in napoli_sets:
            set_suit = napoli_set[0] % 4
            napoli_suits.append(set_suit)

        self.napoli_claimed_status[uid] = True
        # add 3 (1 point) for each napoli set
        point_add = len(napoli_sets) * SERVER_SCORE_ONE_POINT
        p.points += point_add

        # send to all users
        pkg = packet_pb2.GameActionNapoli()
        pkg.uid = uid
        pkg.point_add = point_add
        pkg.suits.extend(napoli_suits)

        await self.broadcast_pkg(CMDs.GAME_ACTION_NAPOLI, pkg)

    def find_napoli(self, hand):
        napoli_sets = []
        
        # Check for Napoli in each suit
        for suit in range(4):
            ace = suit
            two = suit + 4
            three = suit + 8

            if ace in hand and two in hand and three in hand:
                napoli_sets.append([ace, two, three])
        
        return napoli_sets
    
    def user_return_to_table(self, uid):
        self.users_auto_play.pop(uid, None)

    def user_ready(self, uid):
        print("user " + str(uid) + " is ready to play")
        self.user_ready_status[uid] = True
        pass


