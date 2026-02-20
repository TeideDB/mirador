"""Pipeline scheduler — runs pipelines on cron schedules using APScheduler."""

import logging
from datetime import datetime, timezone
from typing import Any

from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Active scheduler instance (set during app lifespan)
_scheduler: AsyncScheduler | None = None

# Track registered jobs: pipeline_key -> job_id
_jobs: dict[str, str] = {}

# Run history: pipeline_key -> list of {timestamp, status, error?}
_run_history: dict[str, list[dict[str, Any]]] = {}
_MAX_HISTORY = 50


def _parse_cron(expression: str, tz: str = "UTC") -> CronTrigger:
    """Parse a standard 5-field cron expression into an APScheduler CronTrigger."""
    parts = expression.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Expected 5-field cron expression, got {len(parts)} fields: '{expression}'")
    minute, hour, day, month, dow = parts
    return CronTrigger(
        minute=minute, hour=hour, day=day, month=month, day_of_week=dow,
        timezone=tz,
    )


async def _run_pipeline_job(project_slug: str, workflow_name: str) -> None:
    """Job callback: load and execute a pipeline."""
    from mirador.engine.registry import NodeRegistry
    from mirador.engine.executor import PipelineExecutor
    from mirador.storage.projects import ProjectStore

    key = f"{project_slug}/{workflow_name}"
    entry: dict[str, Any] = {"timestamp": datetime.now(timezone.utc).isoformat()}

    try:
        store = ProjectStore()
        pipeline = store.load_pipeline(project_slug, workflow_name)
        if pipeline is None:
            entry["status"] = "error"
            entry["error"] = "Workflow not found"
            logger.error("Scheduled run failed: workflow %s not found", key)
            return

        registry = NodeRegistry()
        registry.discover()
        executor = PipelineExecutor(registry)
        executor.run(pipeline)
        entry["status"] = "ok"
        logger.info("Scheduled run completed: %s", key)
    except Exception as exc:
        entry["status"] = "error"
        entry["error"] = str(exc)
        logger.exception("Scheduled run failed: %s", key)
    finally:
        history = _run_history.setdefault(key, [])
        history.append(entry)
        if len(history) > _MAX_HISTORY:
            _run_history[key] = history[-_MAX_HISTORY:]


async def sync_schedules(project_slug: str, workflow_name: str, pipeline: dict) -> None:
    """Sync schedule for a single pipeline. Call after save/update."""
    if _scheduler is None:
        return

    key = f"{project_slug}/{workflow_name}"

    # Remove existing job for this pipeline
    if key in _jobs:
        try:
            await _scheduler.remove_job(_jobs[key])
        except Exception:
            pass
        del _jobs[key]

    # Find schedule trigger node(s)
    for node in pipeline.get("nodes", []):
        if node.get("type") != "schedule_trigger":
            continue
        cfg = node.get("config", {})
        cron_expr = cfg.get("cron_expression")
        enabled = cfg.get("enabled", True)

        if not cron_expr or not enabled:
            continue

        tz = cfg.get("timezone", "UTC")
        try:
            trigger = _parse_cron(cron_expr, tz)
        except ValueError as exc:
            logger.warning("Invalid cron for %s: %s", key, exc)
            continue

        job_id = await _scheduler.add_schedule(
            _run_pipeline_job,
            trigger,
            args=[project_slug, workflow_name],
            id=key,
        )
        _jobs[key] = job_id
        logger.info("Registered schedule for %s: %s (%s)", key, cron_expr, tz)
        break  # only one schedule trigger per pipeline


async def start_scheduler() -> None:
    """Start the global scheduler. Called during app lifespan startup."""
    global _scheduler
    _scheduler = AsyncScheduler()
    await _scheduler.__aenter__()
    await _scheduler.start_in_background()
    logger.info("Pipeline scheduler started")


async def stop_scheduler() -> None:
    """Stop the global scheduler. Called during app lifespan shutdown."""
    global _scheduler
    if _scheduler is not None:
        await _scheduler.__aexit__(None, None, None)
        _scheduler = None
        _jobs.clear()
        logger.info("Pipeline scheduler stopped")


def get_run_history(project_slug: str, workflow_name: str) -> list[dict[str, Any]]:
    """Return run history for a pipeline."""
    return _run_history.get(f"{project_slug}/{workflow_name}", [])
