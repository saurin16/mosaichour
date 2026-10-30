"""Private Qloo client. Responses are cached only in process memory."""
import asyncio
import os
import random
import time

import httpx
from dotenv import load_dotenv

load_dotenv()
BASE = os.getenv("QLOO_BASE_URL", "https://hackathon.api.qloo.com")
_sem = asyncio.Semaphore(4)
_cache: dict[tuple, tuple[float, dict]] = {}


class QlooError(RuntimeError):
    pass


class Qloo:
    def __init__(self):
        self.calls: list[dict] = []
        self.client = httpx.AsyncClient(base_url=BASE, headers={"X-Api-Key": os.environ["QLOO_API_KEY"]}, timeout=18)

    async def close(self):
        await self.client.aclose()

    async def get(self, path: str, params: dict, purpose: str) -> dict:
        start = time.perf_counter()
        key = (path, tuple(sorted((k, str(v)) for k, v in params.items())))
        cached = _cache.get(key)
        if cached and time.time() - cached[0] < 6 * 3600:
            self.calls.append({"endpoint": path, "purpose": purpose, "status": 200, "ms": 0, "cached": True})
            return cached[1]
        response = None
        for attempt in range(5):
            async with _sem:
                try:
                    response = await self.client.get(path, params=params)
                except httpx.TimeoutException:
                    response = None
            if response is not None and response.status_code not in (429, 500, 502, 503, 504):
                break
            if attempt < 4:
                retry_after = float(response.headers.get("retry-after", 0) or 0) if response is not None else 0
                await asyncio.sleep(max(retry_after, 0.5 * 2**attempt) + random.uniform(0, 0.2))
        status = response.status_code if response is not None else 504
        self.calls.append({"endpoint": path, "purpose": purpose, "status": status,
                           "ms": round((time.perf_counter() - start) * 1000), "cached": False})
        if status != 200:
            raise QlooError(f"Qloo {path} returned {status}")
        data = response.json()
        _cache[key] = (time.time(), data)
        return data

    async def search(self, query: str, kind: str) -> dict:
        result = await self.get("/search", {"query": query, "types": f"urn:entity:{kind}", "take": 6},
                                f"Resolve the group's {kind} favorite")
        choices = result.get("results", [])
        if not choices:
            raise ValueError(f"No Qloo {kind} match for {query!r}. Try a more specific favorite.")
        exact = next((item for item in choices if item.get("name", "").casefold() == query.strip().casefold()), None)
        return exact or choices[0]

    async def insights(self, kind: str, ids: str) -> list[dict]:
        result = await self.get("/v2/insights", {"filter.type": f"urn:entity:{kind}",
                                                    "signal.interests.entities": ids, "take": 12},
                                f"Find {kind} ideas connected to both favorites")
        return [{"name": e.get("name", ""), "entity_id": e.get("entity_id", "")}
                for e in result.get("results", {}).get("entities", []) if e.get("name")][:10]
