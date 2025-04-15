
from datetime import datetime
import random
from src.base.logs.logs_mgr import write_log
from src.base.network.packets import packet_pb2
from src.game.game_vars import game_vars
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs


class AdsMgr:
    async def on_receive_packet(self, uid: int, cmd_id: int, payload):
        match cmd_id:
            case CMDs.CLAIM_ADS_REWARD:
                user_info = await users_info_mgr.get_user_info(uid)
                if not user_info:
                    return
                timestamp_now = int(datetime.now().timestamp())
                if user_info.time_ads_reward > timestamp_now:
                    return
                # user will received another reward after 30 minutes
                user_info.time_ads_reward = timestamp_now + 60 * 30
                user_info.num_claimed_ads += 1
                await user_info.commit_to_database('time_ads_reward', 'num_claimed_ads')

                # send ads reward
                pkg = packet_pb2.AdsReward()
                gold_reward = 100000
                
                if user_info.num_claimed_ads == 1:
                    # First time: 90k–100k
                    gold_reward = random.randint(90000, 100000)
                else:
                    # 30k–60k
                    gold_reward = random.randint(50000, 80000)
               
                gold_reward = round(gold_reward, -3)
                pkg.gold = gold_reward
                pkg.time_ads_reward = user_info.time_ads_reward

                # update user gold
                user_info.add_gold(gold_reward)
                await user_info.commit_gold()
                await user_info.send_update_money()

                write_log(uid, "ads_reward", '', [])

                await game_vars.get_game_client().send_packet(uid, CMDs.CLAIM_ADS_REWARD, pkg)
                pass