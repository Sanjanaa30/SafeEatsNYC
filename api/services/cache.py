"""Small in-process time-to-live cache for repeated dashboard reads."""

from threading import Lock
from time import monotonic
from typing import Generic, TypeVar

Value = TypeVar("Value")


class TtlCache(Generic[Value]):
    """Keep copies of values for a short, bounded period."""

    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._values: dict[str, tuple[float, Value]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Value | None:
        with self._lock:
            cached = self._values.get(key)
            if cached is None:
                return None
            created_at, value = cached
            if monotonic() - created_at >= self.ttl_seconds:
                self._values.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Value) -> None:
        with self._lock:
            self._values[key] = (monotonic(), value)
