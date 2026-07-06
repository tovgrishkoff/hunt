"""
Scheduler Module - Automated Pipeline Execution.

Provides scheduled and on-demand pipeline execution
using APScheduler for background job management.
"""

import asyncio
from datetime import datetime
from typing import Any, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import get_settings
from .logger import get_logger
from .models import Platform, PipelineResult

logger = get_logger(__name__)


class ContentScheduler:
    """
    Background scheduler for automated content generation.

    Supports cron-based scheduling, interval-based execution,
    and on-demand pipeline triggers.
    """

    def __init__(self) -> None:
        """Initialize the content scheduler."""
        self.settings = get_settings()
        self.scheduler = AsyncIOScheduler(timezone=self.settings.timezone)
        self._engine = None
        self._job_results: dict[str, PipelineResult] = {}

    def _get_engine(self):
        """Lazy load the content engine to avoid circular imports."""
        if self._engine is None:
            from .main import ContentEngine
            self._engine = ContentEngine(auto_init_knowledge=True)
        return self._engine

    async def _execute_pipeline(
        self,
        job_id: str,
        topic: str,
        platforms: list[Platform],
        schedule: bool = True,
        generate_images: bool = True,
    ) -> PipelineResult:
        """Execute pipeline and store result."""
        logger.info(f"Executing scheduled job: {job_id}")

        try:
            engine = self._get_engine()
            result = await engine.run_pipeline(
                topic=topic,
                platforms=platforms,
                schedule=schedule,
                generate_images=generate_images,
            )
            self._job_results[job_id] = result
            return result
        except Exception as e:
            logger.error(f"Scheduled job {job_id} failed: {e}")
            raise

    def add_cron_job(
        self,
        job_id: str,
        topic: str,
        cron_expression: str,
        platforms: list[Platform] | None = None,
        schedule: bool = True,
        generate_images: bool = True,
    ) -> str:
        """
        Add a cron-scheduled content generation job.

        Args:
            job_id: Unique identifier for the job
            topic: Content topic to generate
            cron_expression: Cron expression (e.g., "0 9 * * *" for 9 AM daily)
            platforms: Target platforms
            schedule: Whether to schedule via Metricool
            generate_images: Whether to generate images

        Returns:
            Job ID
        """
        if platforms is None:
            platforms = [Platform(p) for p in self.settings.default_platforms]

        parts = cron_expression.split()
        trigger = CronTrigger(
            minute=parts[0] if len(parts) > 0 else "*",
            hour=parts[1] if len(parts) > 1 else "*",
            day=parts[2] if len(parts) > 2 else "*",
            month=parts[3] if len(parts) > 3 else "*",
            day_of_week=parts[4] if len(parts) > 4 else "*",
        )

        self.scheduler.add_job(
            self._execute_pipeline,
            trigger=trigger,
            id=job_id,
            kwargs={
                "job_id": job_id,
                "topic": topic,
                "platforms": platforms,
                "schedule": schedule,
                "generate_images": generate_images,
            },
            replace_existing=True,
        )

        logger.info(f"Added cron job '{job_id}' with schedule: {cron_expression}")
        return job_id

    def add_interval_job(
        self,
        job_id: str,
        topic_generator: Callable[[], str],
        hours: int = 24,
        platforms: list[Platform] | None = None,
        schedule: bool = True,
        generate_images: bool = True,
    ) -> str:
        """
        Add an interval-based content generation job.

        Args:
            job_id: Unique identifier for the job
            topic_generator: Function that returns a topic string
            hours: Interval in hours
            platforms: Target platforms
            schedule: Whether to schedule via Metricool
            generate_images: Whether to generate images

        Returns:
            Job ID
        """
        if platforms is None:
            platforms = [Platform(p) for p in self.settings.default_platforms]

        async def wrapped_execution():
            topic = topic_generator()
            return await self._execute_pipeline(
                job_id=job_id,
                topic=topic,
                platforms=platforms,
                schedule=schedule,
                generate_images=generate_images,
            )

        self.scheduler.add_job(
            wrapped_execution,
            trigger=IntervalTrigger(hours=hours),
            id=job_id,
            replace_existing=True,
        )

        logger.info(f"Added interval job '{job_id}' with {hours}h interval")
        return job_id

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")
            return False

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return jobs

    def get_job_result(self, job_id: str) -> PipelineResult | None:
        """Get the result of a completed job."""
        return self._job_results.get(job_id)

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Content scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Content scheduler stopped")

    async def run_once(
        self,
        topic: str,
        platforms: list[Platform] | None = None,
        schedule: bool = True,
        generate_images: bool = True,
    ) -> PipelineResult:
        """Execute pipeline once immediately."""
        if platforms is None:
            platforms = [Platform(p) for p in self.settings.default_platforms]

        job_id = f"manual_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        return await self._execute_pipeline(
            job_id=job_id,
            topic=topic,
            platforms=platforms,
            schedule=schedule,
            generate_images=generate_images,
        )


async def run_scheduler_demo() -> None:
    """Demo scheduler with sample jobs."""
    import random

    scheduler = ContentScheduler()

    topics = [
        "5 morning habits for productivity",
        "How to stay focused while working from home",
        "Building a growth mindset",
        "Time management tips for entrepreneurs",
        "The power of daily routines",
    ]

    def random_topic() -> str:
        return random.choice(topics)

    scheduler.add_cron_job(
        job_id="daily_morning_post",
        topic="Daily motivation and productivity tip",
        cron_expression="0 8 * * *",
        platforms=[Platform.INSTAGRAM, Platform.TELEGRAM],
    )

    scheduler.add_cron_job(
        job_id="pinterest_weekly",
        topic="Weekly business growth strategies",
        cron_expression="0 14 * * 1",
        platforms=[Platform.PINTEREST],
    )

    scheduler.add_interval_job(
        job_id="rotating_content",
        topic_generator=random_topic,
        hours=12,
        platforms=[Platform.INSTAGRAM],
    )

    print("Scheduled jobs:")
    for job in scheduler.list_jobs():
        print(f"  - {job['id']}: Next run at {job['next_run']}")

    scheduler.start()

    try:
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        scheduler.stop()


if __name__ == "__main__":
    asyncio.run(run_scheduler_demo())
