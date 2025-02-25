

import time
from src.base.network.packets import packet_pb2
from src.game.cmds import CMDs
from src.base.telegram import telegram_bot

time_customer_by_uid = {}
class CustomerServiceMgr:
    async def on_receive_packet(self, uid: int, cmd_id: int, payload):
        match cmd_id:
            case CMDs.CUSTOMER_SERVICE_REPORT:
                await self._handle_customer_service_report(uid, payload)

    async def _handle_customer_service_report(self, uid: int, payload):
        # check to prevent spam, each user only sent support in 24 hours
        if uid in time_customer_by_uid:
            if time_customer_by_uid[uid] + 24 * 3600 > time.time():
                return
        
        time_customer_by_uid[uid] = time.time()
        pkg = packet_pb2.CustomerServiceReport()
        pkg.ParseFromString(payload)
        report_type = pkg.report_type
        report_content = pkg.report_content

        # sub string if too long
        if len(report_content) > 500:
            report_content = report_content[:500] + "..."

        await telegram_bot.send_message(f"User {uid} reported: {report_type} - {report_content}")

        