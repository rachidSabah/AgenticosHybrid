"""OpenAI-compatible provider adapter.

Connects to ANY OpenAI-compatible ``/v1/chat/completions`` endpoint (self-hosted
vLLM, LM Studio, OpenRouter, Together, Groq, …). This satisfies the
"OpenAI-compatible custom providers" requirement: a user supplies base_url,
model, and API key via the Provider Manager UI/API and this adapter drives it.
"""

from __future__ import annotations

import httpx

from agentic_os.domain.agent import Agent, ProviderInfo, Task
from agentic_os.infrastructure.logging import get_logger

log = get_logger("provider.openai_compatible")


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 60.0,
    ) -> None:
        self._name = name
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self.info = ProviderInfo(
            name=name, kind="openai_compatible", supports_streaming=False, supports_tools=False
        )

    async def execute(self, agent: Agent, task: Task) -> str:
        url = f"{self._base_url}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "user", "content": f"{task.title}\n\n{task.description}".strip()}
            ],
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected response shape: {data}") from exc

    async def healthcheck(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Minimal connectivity probe to the models endpoint.
                r = await client.get(
                    f"{self._base_url}/v1/models",
                    headers={"Authorization": f"Bearer {self._api_key}"} if self._api_key else {},
                )
                return r.status_code < 500
        except Exception:  # noqa: BLE001
            return False
