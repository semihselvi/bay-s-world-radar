from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Iterable

try:
    import yaml
except Exception:  # optional until Radar XL requirements are installed
    yaml = None

from radar_xl import config
from radar_xl.models import Candidate


class AgentReachProvider:
    """Use Agent Reach's selected upstream CLIs without coupling to production Radar.

    Agent Reach is a capability/router layer. The actual reads are performed by
    twitter-cli, rdt/OpenCLI and yt-dlp, matching Agent Reach's documented routes.
    """

    name = "agent_reach"

    def __init__(self, timeout: int = 45) -> None:
        self.timeout = timeout
        self.status = self._doctor()

    @staticmethod
    def _which(name: str) -> bool:
        return shutil.which(name) is not None

    def _run(self, args: list[str], timeout: int | None = None) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
                check=False,
            )
            return proc.returncode, proc.stdout or "", proc.stderr or ""
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 127, "", str(exc)

    def _doctor(self) -> dict[str, Any]:
        if not self._which("agent-reach"):
            return {"available": False, "reason": "agent-reach not installed"}
        code, out, err = self._run(["agent-reach", "doctor", "--json"], timeout=30)
        if code != 0:
            return {"available": False, "reason": (err or out)[-500:]}
        try:
            payload = json.loads(out)
            if isinstance(payload, dict):
                payload["available"] = True
                return payload
        except json.JSONDecodeError:
            pass
        return {"available": True, "raw": out[-2000:]}

    @staticmethod
    def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from AgentReachProvider._walk_dicts(child)
        elif isinstance(value, list):
            for child in value:
                yield from AgentReachProvider._walk_dicts(child)

    @staticmethod
    def _iso_from_epoch(value: Any) -> str:
        try:
            num = float(value)
            if num > 10_000_000_000:
                num /= 1000.0
            return datetime.fromtimestamp(num, tz=timezone.utc).isoformat()
        except Exception:
            return ""

    def _twitter(self, query: str, language: str, limit: int) -> list[Candidate]:
        if not self._which("twitter"):
            return []
        args = ["twitter", "search", query, "-t", "Latest", "--max", str(limit), "--json"]
        if language in {"en", "tr", "ru"}:
            args += ["--lang", language]
        code, out, _ = self._run(args)
        if code != 0:
            return []
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            return []

        results: list[Candidate] = []
        seen_ids: set[str] = set()
        for obj in self._walk_dicts(payload):
            tweet_id = str(obj.get("id") or obj.get("tweet_id") or obj.get("rest_id") or "").strip()
            text = str(obj.get("text") or obj.get("full_text") or obj.get("content") or "").strip()
            if not tweet_id or not text or tweet_id in seen_ids:
                continue
            seen_ids.add(tweet_id)
            author_obj = obj.get("author") or obj.get("user") or {}
            if isinstance(author_obj, dict):
                author = str(author_obj.get("username") or author_obj.get("screen_name") or author_obj.get("name") or "")
            else:
                author = str(author_obj or obj.get("username") or obj.get("screen_name") or "")
            author = author.lstrip("@")
            url = str(obj.get("url") or obj.get("permalink") or "")
            if not url and author:
                url = f"https://x.com/{author}/status/{tweet_id}"
            published = str(obj.get("created_at") or obj.get("time") or obj.get("date") or "")
            results.append(
                Candidate(
                    source="Agent Reach / X",
                    source_kind="x",
                    url=url,
                    text=text,
                    author=("@" + author) if author else "",
                    published_at=published,
                    language=language,
                    query=query,
                    metadata={"tweet_id": tweet_id},
                )
            )
        return results[:limit]

    def _reddit(self, query: str, language: str, limit: int) -> list[Candidate]:
        payload: Any = None
        if self._which("rdt"):
            code, out, _ = self._run(["rdt", "search", query, "--limit", str(limit), "--yaml"])
            if code == 0 and yaml is not None:
                try:
                    payload = yaml.safe_load(out)
                except Exception:
                    payload = None
        elif self._which("opencli"):
            code, out, _ = self._run(["opencli", "reddit", "search", query, "-f", "yaml"])
            if code == 0 and yaml is not None:
                try:
                    payload = yaml.safe_load(out)
                except Exception:
                    payload = None
        if payload is None:
            return []

        results: list[Candidate] = []
        seen: set[str] = set()
        for obj in self._walk_dicts(payload):
            title = str(obj.get("title") or "").strip()
            body = str(obj.get("selftext") or obj.get("body") or obj.get("text") or obj.get("content") or "").strip()
            post_id = str(obj.get("id") or obj.get("post_id") or "").strip()
            permalink = str(obj.get("permalink") or obj.get("url") or "").strip()
            if permalink.startswith("/"):
                permalink = "https://www.reddit.com" + permalink
            if not permalink and post_id:
                permalink = f"https://www.reddit.com/comments/{post_id}"
            key = permalink or post_id or (title + body[:80])
            if not key or key in seen or not (title or body):
                continue
            seen.add(key)
            author = str(obj.get("author") or obj.get("username") or "").strip()
            created = obj.get("created_utc") or obj.get("created") or obj.get("timestamp") or ""
            published = self._iso_from_epoch(created) if isinstance(created, (int, float)) else str(created or "")
            results.append(
                Candidate(
                    source="Agent Reach / Reddit",
                    source_kind="reddit",
                    url=permalink,
                    title=title,
                    text=body,
                    author=author,
                    published_at=published,
                    language=language,
                    query=query,
                    metadata={"post_id": post_id},
                )
            )
        return results[:limit]

    def _youtube(self, query: str, language: str, limit: int) -> list[Candidate]:
        if not self._which("yt-dlp"):
            return []
        code, out, _ = self._run(
            ["yt-dlp", "--dump-json", "--skip-download", f"ytsearch{limit}:{query}"],
            timeout=max(self.timeout, 90),
        )
        if code != 0 and not out.strip():
            return []
        results: list[Candidate] = []
        for line in out.splitlines():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = str(obj.get("webpage_url") or obj.get("original_url") or "")
            title = str(obj.get("title") or "")
            description = str(obj.get("description") or "")
            uploader = str(obj.get("uploader") or obj.get("channel") or "")
            upload_date = str(obj.get("upload_date") or "")
            if len(upload_date) == 8 and upload_date.isdigit():
                upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}T00:00:00+00:00"
            results.append(
                Candidate(
                    source="Agent Reach / YouTube",
                    source_kind="youtube",
                    url=url,
                    title=title,
                    text=description,
                    author=uploader,
                    published_at=upload_date,
                    language=language,
                    query=query,
                    metadata={"video_id": obj.get("id", "")},
                )
            )
        return results[:limit]

    def collect(self, queries: list[tuple[str, str]]) -> list[Candidate]:
        if not config.AGENT_REACH_ENABLED:
            return []
        if not self.status.get("available"):
            return []

        results: list[Candidate] = []
        for language, query in queries[: config.MAX_QUERIES_PER_PROVIDER]:
            results.extend(self._twitter(query, language, config.RESULTS_PER_QUERY))
            results.extend(self._reddit(query, language, config.RESULTS_PER_QUERY))

        # YouTube is mainly a discovery supplement; keep its load deliberately small.
        for language, query in queries[: min(4, config.MAX_QUERIES_PER_PROVIDER)]:
            results.extend(self._youtube(query, language, min(5, config.RESULTS_PER_QUERY)))
        return results
