import asyncio
from enum import Enum
from datetime import datetime, timedelta
import logging
import random
import traceback

from src.base.network.connection_manager import connection_manager
from src.base.network.packets import packet_pb2
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs
from src.game.game_vars import game_vars
from datetime import datetime, timedelta
from src.game.tressette_config import config as tress_config
import uuid
from src.game.modules import game_exp

class MatchState(Enum):
    WAITING = 0
    PREPARING_START = 1
    PLAYING = 2
    ENDING = 3
    ENDED = 4

PLAYER_SOLO_MODE = 2
PLAYER_DUO_MODE = 4
TRESSETTE_MODE = 0
BRISCOLA_MODE = 1

TIME_AUTO_PLAY = tress_config.get("time_thinking_in_turn")
TAX_PERCENT = tress_config.get("tax_percent")
TIME_START_TO_DEAL = 3.5 # seconds
TIME_DRAW_CARD = 4 # seconds

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

class MatchBot(MatchPlayer):
    def __init__(self, uid, match_mgr):
        super().__init__(uid, match_mgr)
        self.is_bot = True

    async def on_turn(self):
        print('Bot on turn')
        # play a card
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
        # wait for 1 second
        await asyncio.sleep(1)
        await self.match_mgr._play_card(self.uid, card_id=card_id, auto=False)

class Match:
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
        self.bet = 10000
        self.auto_play_count_by_uid = {} # consecutive auto play count
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

        # init slots
        for i in range(player_mode):
            p = MatchPlayer(-1, self)
            self.players.append(p)

    
    async def loop(self):
        try:
            if self.state == MatchState.PLAYING:
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
        except Exception as e:
            traceback.print_exc()
            raise e


    def end_match(self):
        self.state = MatchState.ENDED
        self.end_time = datetime.now()

    async def user_join(self, user_id, is_bot=False):
        # check user in match
        for player in self.players:
            if player.uid == user_id:
                print('User already in match, can not jion')
                return
        if not is_bot:
            user_data = await users_info_mgr.get_user_info(user_id)
        else:
            user_data = await game_vars.get_bots_mgr().get_a_bot()

        # find empty slot
        slot_idx = -1   
        for i, player in enumerate(self.players):
            if player.uid == -1:
                slot_idx = i
                break
        if slot_idx == -1:
            print('Match is full')
            return
        if is_bot:
            match_player = MatchBot(user_id, self)
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

        await self.broadcast_pkg(CMDs.NEW__USER_JOIN_MATCH, pkg, ignore_uids=[user_id])
        
        if not is_bot:
            # send game info to user
            await self._send_game_info(user_id)

        if self.check_room_full():
            await self._prepare_start_game()
        else:
            # add a bot
            # wait for 1 second
            await asyncio.sleep(8)
            await self._check_and_gen_bot()

    async def _check_and_gen_bot(self):
        max_bet_to_gen_bot = tress_config.get('max_bet_to_gen_bot')
        if self.bet > max_bet_to_gen_bot:
            return
        await self.add_bot()
        

    async def add_bot(self):
        print('Add bot')
        # random uid from 2M - 3M
        bot_uid = random.randint(2000000, 3000000)
        await self.user_join(bot_uid, is_bot=True)

    async def _prepare_start_game(self):
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

        for player in self.players:
            game_info.uids.append(player.uid)
            game_info.user_golds.append(player.gold)
            game_info.user_names.append(player.name)
            game_info.user_points.append(player.points)
            game_info.team_ids.append(player.team_id)
            game_info.avatars.append(player.avatar)

            if player.uid == uid:
                game_info.my_cards.extend(player.cards)
        
        print(f"Send game info to user {uid}, game_info: {game_info}")
        await game_vars.get_game_client().send_packet(uid, CMDs.GAME_INFO, game_info)

    # ALERT: This function is called from match_mgr
    async def user_leave(self, uid):
        pkg = packet_pb2.UserLeaveMatch()
        pkg.uid = uid
        await self.broadcast_pkg(CMDs.USER_LEAVE_MATCH, pkg)

        # remove user from match
        for i, player in enumerate(self.players):
            if player.uid == uid:
                self.players[i] = MatchPlayer(-1, self)
                break

        if not self.check_room_full() and self.state == MatchState.PREPARING_START:
            self.state = MatchState.WAITING
            self.time_start = -1

    async def start_game(self):
        self.unique_game_id = str(uuid.uuid4())
        # write logs
        for player in self.players:
            if player.is_bot or player.uid == -1:
                continue
            game_vars.get_logs_mgr().write_log(player.uid, "start_game", "", [self.unique_match_id, self.unique_game_id, self.bet])

        print('Start game')
        self.time_start = -1
        self.state = MatchState.PLAYING
        self.start_time = datetime.now()
        self.current_turn = 0
        self.current_hand = -1
        self.time_auto_play = -1
        self.cards_compare.clear()
        self.auto_play_time_by_uid.clear()
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

        # reset players scores:
        for player in self.players:
            player.points = 0
            player.score_last_trick = 0
            player.cards.clear()
            player.gold_change = 0

            # get pot user need to contribute
            pot_user_need_to_contribute = self.bet
            self.pot_value += pot_user_need_to_contribute

            if player.is_bot:
                continue

            player.gold_change = -pot_user_need_to_contribute

            player_info = await users_info_mgr.get_user_info(player.uid)
            player_info.add_gold(-pot_user_need_to_contribute)
            await player_info.send_update_money()

        for i in range(len(self.players)):
            self.cards_compare.append(-1)

        pkg = packet_pb2.StartGame()
        pkg.pot_value = self.pot_value

        await self.broadcast_pkg(CMDs.START_GAME, pkg)

        # # wait for 3 seconds
        # await asyncio.sleep(TIME_START_TO_DEAL)
        await asyncio.sleep(3)
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
        if self.current_turn == -1 or self.players[self.current_turn].uid != uid:
            logger.error(f"User {uid} is not in turn, current turn: {self.current_turn}, user turn: {self.players[self.current_turn].uid}")
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

            # remove auto play count
            self.auto_play_count_by_uid.pop(uid, None)
        else:
            self.auto_play_count_by_uid[uid] = self.auto_play_count_by_uid.get(uid, 0) + 1
            
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
        pkg = packet_pb2.PlayCard()
        pkg.uid = uid
        pkg.card_id = card_id
        pkg.auto = auto
        pkg.current_turn = self.current_turn
        pkg.hand_suit = self.hand_suit

        await self.broadcast_pkg(CMDs.PLAY_CARD, pkg)

        # Check done hand
        if is_finish_hand:
            print('Finishhand, end hand')
            await self.end_hand()
        else:
            # next uid
            next_uid = self.players[self.current_turn].uid
            await self.players[self.current_turn].on_turn()
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
            # do not send to bots
            if player.is_bot:
                continue
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

        # check is end round
        if len(self.players[0].cards) == 0: # test = 9
            # logic end round
            self.is_end_round = True
        else:
            self.is_end_round = False
        
        if self.is_end_round:
            # calculate last trick
            #BONUS 1 point for the last trick to the team that wins it
            win_player.points += 3 # 1 point for last trick
            win_player.score_last_trick += 3

        pkg = packet_pb2.EndHand()
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
    
    async def _on_end_round(self):
        await self._on_new_round()

    async def _on_new_round(self):
        self.cur_round += 1
        self.is_end_round = False

        # When new round start, all redudant points need to be removed, example 3, 1/3 -> 3, 4 2/3 -> 4
        for player in self.players:
            redundant_points = player.points % 3
            player.points -= redundant_points

        # players need to contribute to pot again
        for player in self.players:
            # get pot user need to contribute
            pot_user_need_to_contribute = self.bet
            self.pot_value += pot_user_need_to_contribute

            if player.is_bot:
                continue

            player.gold_change = -pot_user_need_to_contribute
            player_info = await users_info_mgr.get_user_info(player.uid)
            player_info.add_gold(-pot_user_need_to_contribute)
            await player_info.send_update_money()

        # Send new round
        pkg = packet_pb2.NewRound()
        pkg.current_round = self.cur_round
        pkg.pot_value = self.pot_value

        await self.broadcast_pkg(CMDs.NEW_ROUND, pkg)

        await asyncio.sleep(3)
        await self.deal_card()
        await asyncio.sleep(2)
        await self._handle_new_hand()

    def _is_end_game(self):
        # check if one team reach 21 * 3 points then end game
        self.team_scores = [0, 0]
        for player in self.players:
            self.team_scores[player.team_id] += player.points
            
        # test
        if self.team_scores[0] >= 1 or self.team_scores[1] >= 1:
            return True
        
        if self.team_scores[0] >= 33 or self.team_scores[1] >= 33:
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

        # next turn is the winner of last hand
        if self.win_player is not None:
            self.current_turn = self.players.index(self.win_player)
        else:
            self.current_turn = 0

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
        if self.team_scores[0] > self.team_scores[1]:
            self.win_team = 0
        else:
            self.win_team = 1

        # add gold
        for player in self.players:
            if player.uid == -1 or player.is_bot:
                continue
            user_info = await users_info_mgr.get_user_info(player.uid)
            user_info.game_count += 1
            added_exp = int(game_exp.calculate_exp_gain(self.bet))
            if player.team_id == self.win_team:
                gold_win = int(self.pot_value / self.player_mode * 2)
                player.gold_change += gold_win

                gold_received = int(gold_win - gold_win * TAX_PERCENT)
                user_info.add_gold(gold_received)
                user_info.win_count += 1
                added_exp = added_exp * 2

            user_info.add_exp(added_exp)

            await user_info.commit_to_database('gold', 'game_count', 'win_count', 'exp')
            await user_info.send_update_money()

            game_vars.get_logs_mgr().write_log(player.uid, "end_game", "", [self.unique_match_id, self.unique_game_id, self.bet])

        uids = []
        score_totals = []
        score_last_tricks = []
        score_cards = []
        gold_changes = []
        for player in self.players:
            uids.append(player.uid)
            score_cards.append(player.points - player.score_last_trick)
            score_last_tricks.append(player.score_last_trick)
            score_totals.append(player.points)
            gold_changes.append(player.gold_change)

        
        # send to users
        pkg = packet_pb2.EndGame()
        pkg.win_team_id = self.win_team
        pkg.uids.extend(uids)
        pkg.score_cards.extend(score_cards)
        pkg.score_last_tricks.extend(score_last_tricks)
        pkg.score_totals.extend(score_totals)
        pkg.gold_changes.extend(gold_changes)

        await self.broadcast_pkg(CMDs.END_GAME, pkg)
        
        await asyncio.sleep(3)

         # User can quit the room now
        self.state = MatchState.WAITING 

        # for user register exit room, or auto play, or disconnect
        await self.update_users_staying_endgame()

        # next game
        await asyncio.sleep(1)
        if self.check_room_full():
            await self._prepare_start_game()

    async def update_users_staying_endgame(self):
        # Remove all bots
        for i, player in enumerate(self.players):
            if player.is_bot:
                await self.user_leave(player.uid)
                
        # Kick users auto playing, or register exit room
        for uid in self.register_leave_uids:
            await game_vars.get_match_mgr().handle_user_leave_match(uid)    

        # kick user auto playing consecutively more than 3 times
        for uid, count in self.auto_play_count_by_uid.items():
            if count >= 3:
                await game_vars.get_match_mgr().handle_user_leave_match(uid)

        # Kick user not has enough gold
        for player in self.players:
            if player.is_bot:
                continue
            if player.uid == -1:
                continue
            user_info = await users_info_mgr.get_user_info(player.uid)
            if user_info.gold < self.get_min_gold_play():
                await game_vars.get_match_mgr().handle_user_leave_match(player.uid)
    
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


class MatchLogic:
    pass