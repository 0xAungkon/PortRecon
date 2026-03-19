import asyncio
from typing import Optional, Dict, Callable
from loguru import logger
from models.scan import Scan


class QueueManager:
    """Manages scan queue with FIFO processing"""

    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.current_task: Optional[str] = None
        self.is_running = False
        self.task_callbacks: Dict[str, Callable] = {}
        self.cancelled_scans: set[str] = set()

    async def enqueue(self, scan_id: str, callback: Callable) -> None:
        """Enqueue a scan with callback function"""
        await self.queue.put((scan_id, callback))
        self.task_callbacks[scan_id] = callback
        await Scan.set_lock(scan_id, "queued")
        logger.info(f"Scan {scan_id} enqueued")

    async def process(self) -> None:
        """Process queue items sequentially"""
        if self.is_running:
            logger.info("Queue processor already running")
            return

        self.is_running = True
        logger.info("Queue processor started")

        try:
            while True:
                scan_id = None
                try:
                    scan_id, callback = await asyncio.wait_for(
                        self.queue.get(), timeout=1.0
                    )

                    if scan_id in self.cancelled_scans:
                        logger.info(f"Skipping cancelled scan {scan_id} from queue")
                        self.cancelled_scans.discard(scan_id)
                        continue

                    self.current_task = scan_id
                    await Scan.set_lock(scan_id, "processing")
                    logger.info(f"Processing scan {scan_id}")

                    await callback()

                    logger.info(f"Completed scan {scan_id}")
                except asyncio.TimeoutError:
                    continue
                finally:
                    if scan_id:
                        await Scan.clear_lock(scan_id)
                    self.current_task = None
                    if scan_id and scan_id in self.task_callbacks:
                        del self.task_callbacks[scan_id]
        except Exception as e:
            logger.error(f"Queue processor error: {e}")
            self.is_running = False

    def is_processing(self, scan_id: str) -> bool:
        """Check if a scan is currently being processed"""
        return self.current_task == scan_id

    def is_queued(self, scan_id: str) -> bool:
        """Check if a scan is in the queue"""
        return scan_id in self.task_callbacks

    def queue_size(self) -> int:
        """Get current queue size"""
        return self.queue.qsize()

    def cancel(self, scan_id: str) -> None:
        """Mark a scan as cancelled so queued tasks are skipped."""
        self.cancelled_scans.add(scan_id)
        if scan_id in self.task_callbacks:
            del self.task_callbacks[scan_id]


# Global queue manager instance
scan_queue = QueueManager()
