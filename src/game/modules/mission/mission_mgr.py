
import json


with open('config/mission.json', 'r') as file:
    config = json.load(file)

missions = config['missions']

class MissionMgr:
    async def send_mission_info(self, uid):
        # load mission info from db
        
        pass

    async def user_claim_reward(self, uid):
        pass

    async def user_complete_mission(self, uid, mission_id):
        pass
    pass