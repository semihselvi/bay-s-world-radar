from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from radar_xl import config


class HermesBridge:
    """Optional second-stage supervisor.

    Radar XL remains fully usable without Hermes. When enabled, Hermes receives
    only the isolated XL result manifest and returns a supervisory summary/plan.
    It is never allowed to write into the production Radar from this bridge.
    """

    def __init__(self, timeout: int = 180) -> None:
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(config.HERMES_ENABLED and shutil.which("hermes"))

    def review_manifest(self, manifest_path: str | Path) -> dict[str, Any]:
        if not self.available:
            return {"ok": False, "reason": "hermes_disabled_or_missing"}

        path = Path(manifest_path).resolve()
        prompt = f"""
You are the BAY-S Radar XL supervisor. Review the JSON manifest at:
{path}

Rules:
- This is an isolated lab. Do NOT modify the existing World Radar, GitHub, Telegram, CRM, Firestore, accounts, or external services.
- Do NOT send messages or perform outreach.
- Evaluate only whether the candidates look like genuine North Cyprus buyer/relocation/investment intent.
- Reject realtor/seller ads, developer promotions, jobs, rentals, service spam, news/editorial content and duplicates.
- Return valid JSON only with keys: hot_count, warm_count, noise_count, top_candidates, provider_notes, next_test.
""".strip()
        try:
            proc = subprocess.run(
                ["hermes", "-z", prompt],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "reason": str(exc)}
        if proc.returncode != 0:
            return {"ok": False, "reason": (proc.stderr or proc.stdout)[-1000:]}
        raw = (proc.stdout or "").strip()
        try:
            parsed = json.loads(raw)
            return {"ok": True, "result": parsed}
        except json.JSONDecodeError:
            return {"ok": True, "raw": raw[:8000]}
