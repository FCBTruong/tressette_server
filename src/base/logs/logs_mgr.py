import asyncio
from src.postgres.orm import PsqlOrm
from src.postgres.sql_models import Logs
from datetime import datetime

class LogsMgr:
    async def _write_log(self, uid, action, sub_action, extras):
        """Internal async function to handle log writing."""
        # Map extras to extra1, extra2, ..., extra10
        extras_mapping = {f"extra{i + 1}": str(extras[i]) for i in range(min(len(extras), 10))}

        async with PsqlOrm.get().session() as session:
            new_log = Logs(
                uid=uid,
                log_time=datetime.utcnow(),
                action=action,
                sub_action=sub_action,
                **extras_mapping  # Unpack extras into the appropriate fields
            )
            session.add(new_log)
            await session.commit()

    def write_log(self, uid, action, sub_action, extras):
        """Public function to trigger log writing without blocking."""
        asyncio.create_task(self._write_log(uid, action, sub_action, extras))
