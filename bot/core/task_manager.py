import asyncio
import os
import signal
import time
import uuid
from typing import Dict, Optional, Any
from telegram import Message, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter
from bot.logger import logger

class DownloadTask:
    def __init__(self, name: str, user_id: int, user_name: str, engine: str, message: Message):
        self.task_id = str(uuid.uuid4())[:8]
        self.name = name
        self.user_id = user_id
        self.user_name = user_name
        self.engine = engine
        self.message = message
        self.is_cancelled = False
        self.process: Optional[asyncio.subprocess.Process] = None
        self.temp_filepath: Optional[str] = None
        self.start_time = time.time()
        self.last_update_time = 0.0

    def cancel(self):
        """Signals task cancellation and kills subprocess if running."""
        self.is_cancelled = True
        if self.process and self.process.returncode is None:
            try:
                # Terminate the entire process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                logger.info(f"Killed process group for task {self.task_id}")
            except Exception as e:
                logger.warning(f"Could not terminate process for task {self.task_id}: {e}")

        # Delete partially downloaded file
        if self.temp_filepath and os.path.exists(self.temp_filepath):
            try:
                os.remove(self.temp_filepath)
                logger.info(f"Deleted partial file: {self.temp_filepath}")
            except Exception as e:
                logger.warning(f"Failed to remove partial file {self.temp_filepath}: {e}")


class TaskManager:
    def __init__(self):
        self._tasks: Dict[str, DownloadTask] = {}
        self._msg_map: Dict[tuple, str] = {}
        self._lock = asyncio.Lock()

    async def register_task(self, name: str, user_id: int, user_name: str, engine: str, message: Message) -> DownloadTask:
        async with self._lock:
            task = DownloadTask(name, user_id, user_name, engine, message)
            self._tasks[task.task_id] = task
            self._msg_map[(message.chat_id, message.message_id)] = task.task_id
            return task

    async def get_task(self, task_id: str) -> Optional[DownloadTask]:
        async with self._lock:
            return self._tasks.get(task_id)

    async def get_all_tasks(self) -> Dict[str, DownloadTask]:
        async with self._lock:
            return dict(self._tasks)

    async def cancel_task(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task and not task.is_cancelled:
                task.cancel()
                return True
            return False

    async def cancel_by_message(self, chat_id: int, message_id: int) -> Optional[str]:
        async with self._lock:
            task_id = self._msg_map.get((chat_id, message_id))
            if task_id and task_id in self._tasks:
                task = self._tasks[task_id]
                if not task.is_cancelled:
                    task.cancel()
                    return task_id
            return None

    async def cancel_all(self) -> int:
        async with self._lock:
            count = 0
            for task in self._tasks.values():
                if not task.is_cancelled:
                    task.cancel()
                    count += 1
            return count

    async def unregister_task(self, task_id: str):
        async with self._lock:
            task = self._tasks.pop(task_id, None)
            if task and task.message:
                self._msg_map.pop((task.message.chat_id, task.message.message_id), None)

    async def safe_edit_status(
        self,
        task: DownloadTask,
        text: str,
        force: bool = False,
        min_interval: float = 3.0
    ):
        """
        Updates task status message safely while adhering to Telegram's 3-second edit rate limit.
        """
        now = time.time()
        if not force and (now - task.last_update_time < min_interval):
            return

        try:
            await task.message.edit_text(
                text,
                reply_markup=None,
                parse_mode=ParseMode.HTML
            )
            task.last_update_time = now
        except RetryAfter as e:
            logger.warning(f"Telegram FloodWait: Retry after {e.retry_after}s")
            task.last_update_time = now + e.retry_after
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                logger.debug(f"Message edit error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error editing message: {e}")

task_manager = TaskManager()
