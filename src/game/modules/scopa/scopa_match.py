

import asyncio
from datetime import datetime, timezone
import logging
import random
import traceback
import uuid
from src.base.logs.logs_mgr import write_log
from src.base.network import connection_manager
from src.base.network.packets import packet_pb2
from src.config import settings
from src.constants import REASON_KICK_NOT_ENOUGH_GOLD
from src.game.game_vars import game_vars
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs
from src.game.match import PLAYER_SOLO_MODE, TAX_PERCENT, TIME_AUTO_PLAY, TIME_START_TO_DEAL, Match, MatchPlayer, MatchState, PlayCardErrors
from src.game.modules import game_exp

logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("scopa_match")  # Name your logger


class ScopaMatch(Match):
    def __init__(self, match_id, bet, player_mode, point_mode):
        self.match_id = match_id
        self.start_time = datetime.now()
        self.end_time = None
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
        self.hand_in_round = -1
        self.enable_bet_win_score = True

        
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
                pass
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

        await self.broadcast_pkg(CMDs.NEW_USER_JOIN_MATCH, pkg, ignore_uids=[user_id])
        
        if not is_bot:
            # send game info to user
            await self._send_game_info(user_id)

        if self.check_room_full():
            await self._prepare_start_game()
            self._clear_coroutine_gen_bot()
        else:
            await self._check_and_gen_bot()

    async def _check_and_gen_bot(self):
        return False
    
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
        if user_info.game_count < 3: # New user will play withbot
            return 2
        return 10
    
    async def _coroutine_gen_bot(self, time_delay_gen_bot):
        return

    def _clear_coroutine_gen_bot(self):
        if self.task_gen_bot is not None:
            self.task_gen_bot.cancel()
            self.task_gen_bot = None

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
        return 0
    
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
        pass

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
        self.cards = []
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
    

    async def end_hand(self):
        pass
    
    async def _on_end_round(self):
        # wait for 2 seconds
        await asyncio.sleep(2)
        await self._on_new_round()

    async def _on_new_round(self):
        pass

    def _is_end_game(self):
        return False
    
    async def _handle_draw_card(self):
        return

    async def _handle_new_hand(self):
        return

    def _draw_card(self):
        card = self.cards.pop(0)
        return card

    def can_quit_game(self, uid):
        return self.state == MatchState.WAITING or self.state == MatchState.PREPARING_START
    
    def get_win_card_in_hand(self):
        return

    def get_win_score_in_hand(self):
        return 0

        
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
                continue

            user_info = await users_info_mgr.get_user_info(player.uid)
            user_info.game_count += 1
            added_exp = int(game_exp.calculate_exp_gain(self.bet))

            if player.team_id == self.win_team:
                user_info.add_gold(gold_received)
                user_info.win_count += 1
                added_exp = added_exp * 2

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

         # User can quit the room now
        self.state = MatchState.WAITING 

        # for user register exit room, or auto play, or disconnect
        await self.update_users_staying_endgame()

        # next game
        await asyncio.sleep(5)
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
            bot_uid = random.randint(5000000, 30000000)
            await self.user_join(bot_uid, is_bot=True)

    def user_return_to_table(self, uid):
        self.users_auto_play.pop(uid, None)