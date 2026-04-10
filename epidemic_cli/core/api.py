from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .discovery import DEFAULT_OLLAMA_URL, DEFAULT_ORCHESTRATOR_URL


class APIRequestError(RuntimeError):
    pass


@dataclass
class ProbeResult:
    ok: bool
    data: Any
    error: str = ""


class OrchestratorAPI:
    def __init__(self, base_url: str = DEFAULT_ORCHESTRATOR_URL, timeout_s: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_s)

    def _request(self, method: str, path: str, *, json_body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(method, url, json=json_body, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            raise APIRequestError(f"{exc.response.status_code} {exc.response.reason_phrase} from {url}") from exc
        except httpx.TimeoutException as exc:
            raise APIRequestError(f"timeout reaching {url}") from exc
        except httpx.HTTPError as exc:
            raise APIRequestError(f"unable to reach {url}") from exc

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, *, payload: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, json_body=payload or {})

    def safe_get(self, path: str, *, params: dict[str, Any] | None = None) -> ProbeResult:
        try:
            return ProbeResult(ok=True, data=self.get(path, params=params))
        except APIRequestError as exc:
            return ProbeResult(ok=False, data=None, error=str(exc))

    def safe_post(self, path: str, *, payload: dict[str, Any] | None = None) -> ProbeResult:
        try:
            return ProbeResult(ok=True, data=self.post(path, payload=payload))
        except APIRequestError as exc:
            return ProbeResult(ok=False, data=None, error=str(exc))


def probe_ollama(base_url: str = DEFAULT_OLLAMA_URL, timeout_s: float = 5.0) -> ProbeResult:
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_s)) as client:
            response = client.get(url)
            response.raise_for_status()
            return ProbeResult(ok=True, data=response.json())
    except httpx.TimeoutException:
        return ProbeResult(ok=False, data=None, error=f"timeout reaching {url}")
    except httpx.HTTPError:
        return ProbeResult(ok=False, data=None, error=f"unable to reach {url}")
