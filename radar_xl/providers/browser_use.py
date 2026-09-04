from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

from radar_xl import config


class BrowserUseProvider:
    """High-cost fallback for pages that normal readers cannot access.

    It is intentionally not a discovery engine. Radar XL calls it only for a
    specific URL/task and only when both the feature flag and task budget are set.
    """

    name = "browser_use"
    base_url = "https://api.browser-use.com/api/v2"

    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout
        self.api_key = os.getenv("BROWSER_USE_API_KEY", "").strip()
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update(
                {
                    "X-Browser-Use-API-Key": self.api_key,
                    "Content-Type": "application/json",
                }
            )
        self.used_tasks = 0

    @property
    def available(self) -> bool:
        return bool(
            config.BROWSER_USE_ENABLED
            and self.api_key
            and config.BROWSER_USE_MAX_TASKS > 0
            and self.used_tasks < config.BROWSER_USE_MAX_TASKS
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.session.request(method, self.base_url + path, timeout=self.timeout, **kwargs)
            if response.status_code not in {200, 201}:
                return {"ok": False, "status": response.status_code, "error": response.text[:500]}
            data = response.json()
            return data if isinstance(data, dict) else {"ok": False, "error": "non-object response"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def extract_url(self, url: str, objective: str = "Extract the main user-generated post or discussion text") -> dict[str, Any]:
        if not self.available:
            return {"ok": False, "reason": "disabled_or_budget_exhausted"}

        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "author": {"type": "string"},
                "text": {"type": "string"},
                "published_at": {"type": "string"},
                "source_url": {"type": "string"},
            },
            "required": ["text", "source_url"],
        }
        task = (
            f"Open only this URL: {url}. {objective}. "
            "Do not post, submit forms, send messages, buy anything, or change account settings. "
            "Return only information visible on the page."
        )
        created = self._request(
            "POST",
            "/tasks",
            json={"task": task, "structuredOutput": json.dumps(schema)},
        )
        task_id = str(created.get("id") or "")
        if not task_id:
            return {"ok": False, "reason": "task_create_failed", "detail": created}
        self.used_tasks += 1

        deadline = time.time() + 180
        status = ""
        while time.time() < deadline:
            state = self._request("GET", f"/tasks/{task_id}/status")
            status = str(state.get("status") or "").lower()
            if status in {"finished", "completed", "done", "stopped", "failed", "error"}:
                break
            time.sleep(4)

        result = self._request("GET", f"/tasks/{task_id}")
        output = result.get("output")
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                output = {"text": output, "source_url": url}
        if not isinstance(output, dict):
            output = {}
        return {
            "ok": bool(output),
            "task_id": task_id,
            "status": status or result.get("status"),
            "output": output,
        }
