"""Schedule trigger node — fires a pipeline on a cron schedule."""

from datetime import datetime, timezone
from typing import Any

from mirador.nodes.base import BaseNode, NodeMeta, NodePort


CRON_PRESETS = {
    "every_5min": "*/5 * * * *",
    "every_15min": "*/15 * * * *",
    "every_hour": "0 * * * *",
    "daily_9am": "0 9 * * *",
    "daily_midnight": "0 0 * * *",
    "weekly_monday": "0 9 * * 1",
}


class ScheduleTriggerNode(BaseNode):
    meta = NodeMeta(
        id="schedule_trigger",
        label="Schedule",
        category="trigger",
        description="Run this pipeline on a cron schedule",
        inputs=[],
        outputs=[NodePort(name="out", description="Trigger metadata")],
        config_schema={
            "type": "object",
            "properties": {
                "cron_expression": {
                    "type": "string",
                    "title": "Cron Expression",
                    "description": "Standard cron (min hour dom mon dow)",
                },
                "timezone": {
                    "type": "string",
                    "title": "Timezone",
                    "default": "UTC",
                },
                "enabled": {
                    "type": "boolean",
                    "title": "Enabled",
                    "default": True,
                },
            },
            "required": ["cron_expression"],
        },
    )

    def execute(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "triggered_at": now.isoformat(),
            "cron": config.get("cron_expression", ""),
            "timezone": config.get("timezone", "UTC"),
            "scheduled": True,
        }
