

import asyncio
from datetime import datetime, timezone
import logging
import random
import traceback
import uuid
from src.base.logs.logs_mgr import write_log
from src.base.network.connection_manager import connection_manager
from src.base.network.packets import packet_pb2
from src.config.settings import settings
from src.constants import REASON_KICK_NOT_ENOUGH_GOLD
from src.game.game_vars import game_vars
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs
from src.game.match import PLAYER_SOLO_MODE, SETTE_MEZZO_MODE, TAX_PERCENT, TIME_AUTO_PLAY, TIME_START_TO_DEAL, TRESSETTE_CARDS, Match, MatchBot, MatchPlayer, MatchState, PlayCardErrors
from src.game.modules import game_exp

logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("scopa_match")  # Name your logger

TIME_THINKING = 10
BANKER_DEFAULT_UID = -100
BANKER_DEFAULT_TURN = -100
class SetteMezzoPlayer(MatchPlayer):
    # override auto play card
    def __init__(self, uid, match):
        super().__init__(uid, match)
        self.is_done_turn = False
        self.is_in_game = False
    
    async def auto_play(self):
        await self.match_mgr.user_stand(self.uid, None)
        pass
class SetteMezzoMatch(Match):
    def __init__(self, match_id):
        self.match_id = match_id
        self.start_time = datetime.now()
        self.end_time = None
        self.player_mode = 4
        self.players: list[SetteMezzoPlayer] = []
        self.cards = []
        self.win_player = None
        self.hand_suit = -1
        self.bet = 0
        self.auto_play_count_by_uid = {} # consecutive auto play count
        self.users_auto_play = {} # uids that are auto play, server will not wait for them
        self.state = MatchState.WAITING
        self.current_turn = -1
        self.register_leave_uids = set()
        self.win_team = -1
        self.pot_value = 0
        self.cur_round = 0
        self.is_end_round = False
        self.unique_match_id = str(uuid.uuid4())
        self.task_gen_bot = None
        self.unique_game_id = ""
        self.is_public = True
        self.hand_in_round = -1
        self.enable_bet_win_score = True
        self.banker_uid = -1
        self.banker_cards = []
        self.playing_users: list[SetteMezzoPlayer] = []
        self.game_mode = SETTE_MEZZO_MODE
        self.time_auto_play = -1

        # init slots
        for i in range(self.player_mode):
            p = SetteMezzoPlayer(-1, self)
            self.players.append(p)

    def set_public(self, is_public):
        self.is_public = is_public
    
    async def loop(self):
        try:
            if self.state == MatchState.PLAYING:
                if self.current_turn != BANKER_DEFAULT_UID and self.current_turn != -1 and \
                        self.time_auto_play != -1 and datetime.now().timestamp() > self.time_auto_play:
                    player = self.playing_users[self.current_turn]
                    if player:
                        await player.auto_play()

            elif self.state == MatchState.PREPARING_START:
                if self.time_start != -1 and datetime.now().timestamp() > self.time_start:
                    if self.check_has_real_players():
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
        
        if is_bot:
            match_player = SetteMezzoBot(user_id, self)
        else:
            match_player = SetteMezzoPlayer(user_id, self)

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

        pkg = packet_pb2.SetteMezzoNewUserJoinMatch()
        pkg.uid = user_id
        pkg.name = user_data.name
        pkg.seat_server = seat_server_id
        pkg.team_id = team_id
        pkg.avatar = user_data.avatar
        pkg.gold = user_data.gold

        await self.broadcast_pkg(CMDs.SETTE_MEZZO_NEW_USER_JOIN_MATCH, pkg, ignore_uids=[user_id])
        
        if not is_bot:
            # send game info to user
            await self._send_game_info(user_id)

        if self.state == MatchState.WAITING:
            await self._prepare_start_game()
    
      
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
        self.time_start = datetime.now().timestamp()
        # Send to all players that game is starting, wait for 3 seconds
        # pkg = packet_pb2.SetteMezzoPrepareStartGame()
        # print('Game is starting, wait for 3 seconds')

        # await self.broadcast_pkg(CMDs.SETTE_MEZZO_PREPARE_START_GAME, pkg)


    def check_can_join(self, uid: int):
        if self.state == MatchState.WAITING:
            return True
        return False
    
    def get_min_gold_play(self):
        return 1000
    
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
        game_info = packet_pb2.SetteMezzoGameInfo()
        game_info.match_id = self.match_id
        game_info.player_mode = self.player_mode
        game_info.game_state = self.state.value
        game_info.current_turn = self.current_turn
        game_info.is_registered_leave = uid in self.register_leave_uids
        game_info.bet = self.bet
        game_info.pot_value = self.pot_value
        game_info.current_round = self.cur_round
        game_info.hand_in_round = self.hand_in_round
        game_info.play_turn_time = int(self.time_auto_play)

        if not self.check_all_done_turn():
            game_info.banker_cards.extend([-1])
        else:
            game_info.banker_cards.extend(self.banker_cards)

        for player in self.players:
            player_pkg = packet_pb2.SetteMezzoPlayerInfo()
            game_info.uids.append(player.uid)
            game_info.user_golds.append(player.gold)
            game_info.user_names.append(player.name)
            game_info.user_points.append(player.points)
            game_info.team_ids.append(player.team_id)
            game_info.avatars.append(player.avatar)
            game_info.is_in_games.append(player.is_in_game)
            p_cards = []
            for card in player.cards:
                p_cards.append(card)

            player_pkg.card_ids.extend(p_cards)
            game_info.player_infos.append(player_pkg.SerializeToString())
        
        await game_vars.get_game_client().send_packet(uid, CMDs.SETTE_MEZZO_GAME_INFO, game_info)

    # ALERT: This function is called from match_mgr
    async def user_leave(self, uid, reason = 0):
        pkg = packet_pb2.UserLeaveMatch()
        pkg.uid = uid
        pkg.reason = reason
        await self.broadcast_pkg(CMDs.SETTE_MEZZO_USER_LEAVE_MATCH, pkg)

        # remove user from match
        for i, player in enumerate(self.players):
            if player.uid == uid:
                self.players[i] = SetteMezzoPlayer(-1, self)
                break

    async def start_game(self):
        self.unique_game_id = str(uuid.uuid4())
        # write logs
        self.playing_users = []
        for player in self.players:
            if player.uid != -1:
                player.is_in_game = True
                player.is_done_turn = False
                player.cards = []
                self.playing_users.append(player)
                write_log(player.uid, "start_game", "sette_mezzo", [self.unique_match_id, self.unique_game_id, self.bet, \
                                                                                self.player_mode])
        if len(self.playing_users) == 0:
            print('No player in game')
            return

        print('Start game Sette mezo')
        self.state = MatchState.PLAYING
        self.start_time = datetime.now()
        self.current_turn = -1
        self.time_auto_play = -1
        self.win_player = None
        self.auto_play_count_by_uid.clear()
        self.register_leave_uids.clear()
        self.win_team = -1
        self.pot_value = 0
        self.cur_round = 1
        self.is_end_round = False
        self.hand_in_round = -1
        self.banker_cards = []

        # Init player golds
        for player in self.players:
            if not player.is_in_game:
                continue
            if player.is_bot:
                continue
            p_info = await users_info_mgr.get_user_info(player.uid)
            player.gold = p_info.gold

    
        players_gold = []
        for player in self.players:
            players_gold.append(player.gold)

        pkg = packet_pb2.SetteMezzoStartGame()
        pkg.pot_value = self.pot_value
        pkg.players_gold.extend(players_gold)

        self.cards = TRESSETTE_CARDS.copy()
        uids = []
        cards = []
        random.shuffle(self.cards)
        self.banker_cards = self.cards[:1]
        self.cards = self.cards[1:]
        uids = [BANKER_DEFAULT_UID]
        cards.append(-1)

        for player in self.players:
            if player.is_in_game:
                player.cards = self.cards[:1]
                self.cards = self.cards[1:]
                uids.append(player.uid)
                cards.append(player.cards[0])
        
        pkg.uids.extend(uids)
        pkg.cards.extend(cards)

        await self.broadcast_pkg(CMDs.SETTE_MEZZO_START_GAME, pkg)

        # wait for 2 seconds
        await asyncio.sleep(2)
        # random current turn from playing users
        if len(self.playing_users) > 0:
            self.current_turn = random.randint(0, len(self.playing_users) - 1)
        else:
            self.current_turn = 0
       
        self.time_auto_play = TIME_THINKING + datetime.now().timestamp()
        # send to user on turn
        await self.send_update_turn()

    async def user_play_card(self, uid, payload):
        pass
    
    async def _send_card_play_response(self, uid, status: PlayCardErrors):
        pkg = packet_pb2.PlayCardResponse()
        pkg.status = status.value
        await game_vars.get_game_client().send_packet(uid, CMDs.PLAY_CARD_RESPONSE, pkg)

    async def _play_card(self, uid, card_id, auto=False):
        pass

    def check_done_hand(self):
        return True

    async def user_reconnect(self, uid):
       # remove state auto play if has
       self.auto_play_count_by_uid.pop(uid, None)
       self.users_auto_play.pop(uid, None)

       await self._send_game_info(uid)

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
        # check if user is in game
        if self.state == MatchState.WAITING or self.state == MatchState.ENDED:
            return True
        for player in self.playing_users:
            if player.uid == uid:
                return False
        print('User not in game')
        return True
    
    def get_win_card_in_hand(self):
        return

    def get_win_score_in_hand(self):
        return 0

    def get_score_cards(self, cards):
        score = 0
        for card in cards:
            rank = card // 4
            if rank < 7:
                point_add = rank + 1
            else:
                point_add = 0.5
            score += point_add
        return score
    
    async def end_game(self):
        self.state = MatchState.ENDED

        # banker score
        banker_score = self.get_score_cards(self.banker_cards)
        if banker_score > 7.5:
            banker_score = 0
        
        results = []
        for player in self.players:
            if player.is_bot:
                continue
            if player.uid == -1:
                continue
            score = self.get_score_cards(player.cards)
            is_win = False
            
            if score > 7.5:
                score = 0
            else:
                if banker_score < score:
                    is_win = True
            
            
            results.append({
                "uid": player.uid,
                "score": score,
                "is_win": is_win,
                "gold": random.randint(-100000, 100000) # TODO: calculate gold
            })


        # send to users
        pkg = packet_pb2.SetteMezzoEndGame()

        uids = []
        scores = []
        is_wins = []
        golds = []

        for result in results:
            uids.append(result["uid"])
            is_wins.append(result["is_win"])
            golds.append(result["gold"])

        pkg.uids.extend(uids)
        pkg.is_wins.extend(is_wins)
        pkg.golds.extend(golds)

        for player in self.players:
            player.is_in_game = False
        
        # wait for 0.5 seconds
        await asyncio.sleep(1)
        await self.broadcast_pkg(CMDs.SETTE_MEZZO_END_GAME, pkg)
        
        await asyncio.sleep(2)

         # User can quit the room now
        self.state = MatchState.WAITING 

        # for user register exit room, or auto play, or disconnect
        await self.update_users_staying_endgame()

        # next game
        await asyncio.sleep(0)
        if self.check_has_real_players():
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

    def user_ready(self, uid):
        print("user " + str(uid) + " is ready to play")
        self.user_ready_status[uid] = True
        pass

    def check_user_in_turn(self, uid):
        if self.current_turn == -1:
            return False
        # get index in playing users
        idx = -1
        for i, player in enumerate(self.playing_users):
            if player.uid == uid:
                if player.is_done_turn:
                    return False
                idx = i
                break
        if idx == -1:
            return False
        
        # check if user is in turn
        if idx != self.current_turn:
            return False
        return True
    
    def check_all_done_turn(self):
        for player in self.playing_users:
            if not player.is_done_turn:
                return False
        return True
    
    async def user_hit(self, uid, payload):
        if not self.check_user_in_turn(uid):
            return
        
        # draw one more card
        new_card = self.cards.pop(0)
        p = None
        # add to player cards
        for player in self.players:
            if player.uid == uid:
                p = player
                break
        if p is None:
            print('User not found')
            return
        
        p.cards.append(new_card)

        # send to all players
        pkg = packet_pb2.SetteMezzoActionHit()
        pkg.uid = uid
        pkg.card_id = new_card
        await self.broadcast_pkg(CMDs.SETTE_MEZZO_ACTION_HIT, pkg)

        # check if user has 7.5
        score = 0
        for card in p.cards:
            rank = card // 4
            if rank < 7:
                point_add = rank + 1
            else:
                point_add = 0.5
            score += point_add

        if score > 7.5:
            p.is_done_turn = True
            await asyncio.sleep(0.5)
            await self.move_to_next_turn()
        else:
            self.time_auto_play = datetime.now().timestamp() + TIME_THINKING
            await self.send_update_turn()

    async def user_stand(self, uid, payload):
        if not self.check_user_in_turn(uid):
            return
        
        for player in self.players:
            if player.uid == uid:
                player.is_done_turn = True
                break
    
        # send update turn to all players
        pkg = packet_pb2.SetteMezzoActionStand()
        pkg.uid = uid
        pkg.current_turn = -1
        pkg.play_turn_time = -1
        await self.broadcast_pkg(CMDs.SETTE_MEZZO_ACTION_STAND, pkg)

        await self.move_to_next_turn()

    async def move_to_next_turn(self):
        if self.current_turn < len(self.playing_users) - 1:
            self.current_turn += 1
        else:
            self.current_turn = 0
        
        p = self.playing_users[self.current_turn]
        self.time_auto_play = datetime.now().timestamp() + TIME_THINKING
        if p.is_done_turn:
            self.current_turn = BANKER_DEFAULT_TURN
            
        # send update turn to all players
        pkg = packet_pb2.SetteMezzoUpdateTurn()
        pkg.current_turn = self.current_turn
        pkg.play_turn_time = int(self.time_auto_play)
        await self.broadcast_pkg(CMDs.SETTE_MEZZO_UPDATE_TURN, pkg)

        if self.current_turn == BANKER_DEFAULT_TURN:
            # banker turn
            await asyncio.sleep(0.5)
            await self.banker_play()

    async def banker_hit(self):
        # banker hit
        new_card = self.cards.pop(0)
        self.banker_cards.append(new_card)

        # send to all players
        pkg = packet_pb2.SetteMezzoActionHit()
        pkg.uid = BANKER_DEFAULT_UID
        pkg.card_id = new_card
        await self.broadcast_pkg(CMDs.SETTE_MEZZO_ACTION_HIT, pkg)

        # check if banker has 7.5
        score = 0
        for card in self.banker_cards:
            rank = card // 4
            if rank < 7:
                point_add = rank + 1
            else:
                point_add = 0.5
            score += point_add

        if score > 7.5:
            # banker is bursted, end game
            await self.end_game()
        else:
            await self.banker_play()

    async def banker_play(self):
        if len(self.banker_cards) == 1:
            # show banker card
            pkg = packet_pb2.SetteMezzoShowBankerCard()
            pkg.card_id = self.banker_cards[0]
            await self.broadcast_pkg(CMDs.SETTE_MEZZO_SHOW_BANKER_CARD, pkg)
            
        await asyncio.sleep(1)
        should_stand = random.choice([True, False])

        if not should_stand:
            await self.banker_hit()
        else:
            # banker stand
            self.current_turn = -1
            pkg = packet_pb2.SetteMezzoActionStand()
            pkg.uid = BANKER_DEFAULT_UID
            pkg.current_turn = -1
            pkg.play_turn_time = -1
            await self.broadcast_pkg(CMDs.SETTE_MEZZO_ACTION_STAND, pkg)

            # end game
            await self.end_game()

 
    async def send_update_turn(self):
        pkg = packet_pb2.SetteMezzoUpdateTurn()
        pkg.current_turn = self.current_turn
        pkg.play_turn_time = int(self.time_auto_play)
        await self.broadcast_pkg(CMDs.SETTE_MEZZO_UPDATE_TURN, pkg)


class SetteMezzoBot(MatchBot):
    pass


