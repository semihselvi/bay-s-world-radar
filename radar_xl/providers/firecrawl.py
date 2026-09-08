from __future__ import annotations

import os
from typing import Any

import requests

from radar_xl import config
from radar_xl.models import Candidate


class FirecrawlProvider:
    name = "firecrawl"
    base_url = "https://api.firecrawl.dev/v2"

    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout
        self.api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )

    @property
    def available(self) -> bool:
        return bool(config.FIRECRAWL_ENABLED and self.api_key and config.FIRECRAWL_MAX_QUERIES > 0)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.session.post(self.base_url + path, json=payload, timeout=self.timeout)
            if response.status_code != 200:
                return {"success": False, "status": response.status_code, "error": response.text[:500]}
            data = response.json()
            return data if isinstance(data, dict) else {"success": False, "error": "non-object response"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def search(self, query: str, language: str, limit: int) -> list[Candidate]:
        payload = {
            "query": query,
            "limit": min(limit, 20),
            "sources": ["web"],
            "includeDomains": config.FIRECRAWL_INCLUDE_DOMAINS,
            "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
        }
        response = self._post("/search", payload)
        if not response.get("success"):
            return []
        data = response.get("data") or {}
        rows = data.get("web") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []

        results: list[Candidate] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            title = str(row.get("title") or "").strip()
            description = str(row.get("description") or "").strip()
            markdown = str(row.get("markdown") or "").strip()
            text = markdown or description
            if not url or not (title or text):
                continue
            results.append(
                Candidate(
                    source="Firecrawl Search",
                    source_kind="web",
                    url=url,
                    title=title,
                    text=text[:12000],
                    published_at=str(row.get("publishedDate") or row.get("date") or ""),
                    language=language,
                    query=query,
                    metadata={
                        "description": description,
                        "firecrawl_source": "search",
                    },
                )
            )
        return results[:limit]

    def scrape_url(self, url: str) -> str:
        """Fallback page reader. Returns clean page text only when explicitly enabled."""
        if not self.available:
            return ""
        response = self._post(
            "/scrape",
            {
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": True,
            },
        )
        if not response.get("success"):
            return ""
        data = response.get("data") or {}
        if isinstance(data, dict):
            return str(data.get("markdown") or "")[:20000]
        return ""

    def collect(self, queries: list[tuple[str, str]]) -> list[Candidate]:
        if not self.available:
            return []
        results: list[Candidate] = []
        budget = min(config.FIRECRAWL_MAX_QUERIES, config.MAX_QUERIES_PER_PROVIDER)
        for language, query in queries[:budget]:
            results.extend(self.search(query, language, config.RESULTS_PER_QUERY))
        return results
