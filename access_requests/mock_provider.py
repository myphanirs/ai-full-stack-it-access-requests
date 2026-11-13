"""Replay saved provider responses without credentials or network access."""

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path
from threading import Event, Lock


class MockProviderError(RuntimeError):
    """A scripted provider failure or an exhausted response script."""


@dataclass(frozen=True)
class ScriptedResponse:
    """A saved reply, optionally held until a caller-controlled event is set."""

    path: Path
    started: Event | None = None
    release: Event | None = None


class MockProvider:
    """Consume one scripted response per call, recording the source messages."""

    def __init__(self, responses: Iterable[ScriptedResponse]):
        self._responses = deque(responses)
        self._calls: list[str] = []
        self._lock = Lock()

    @property
    def calls(self) -> list[str]:
        """Return a snapshot of calls in response-assignment order."""
        with self._lock:
            return list(self._calls)

    def extract(self, message: str) -> dict:
        # Assign responses atomically, but never hold the lock while waiting:
        # a delayed call must leave subsequent responses available.
        with self._lock:
            self._calls.append(message)
            if not self._responses:
                raise MockProviderError("Mock response script exhausted")
            response = self._responses.popleft()

        if response.started is not None:
            response.started.set()
        if response.release is not None:
            response.release.wait()

        reply = json.loads(response.path.read_text(encoding="utf-8"))
        if "error" in reply:
            raise MockProviderError(reply["error"]["message"])
        return reply
