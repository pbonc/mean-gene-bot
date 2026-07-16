"""Pure state tracking for Twitch connection health checks."""

from dataclasses import dataclass
from enum import Enum


class WatchdogAction(str, Enum):
    HEALTHY = "healthy"
    DISCONNECT_STARTED = "disconnect_started"
    WAITING = "waiting"
    RECOVERED = "recovered"
    GRACE_EXCEEDED = "grace_exceeded"


@dataclass(frozen=True)
class WatchdogResult:
    action: WatchdogAction
    disconnected_for: float = 0.0


class TwitchWatchdogState:
    """Track a disconnect across polling cycles without doing any I/O."""

    def __init__(self, grace_seconds: int):
        if grace_seconds <= 0:
            raise ValueError("grace_seconds must be positive")
        self.grace_seconds = grace_seconds
        self.disconnected_since: float | None = None

    def observe(self, unhealthy: bool, now: float) -> WatchdogResult:
        if not unhealthy:
            if self.disconnected_since is None:
                return WatchdogResult(WatchdogAction.HEALTHY)
            disconnected_for = max(0.0, now - self.disconnected_since)
            self.disconnected_since = None
            return WatchdogResult(WatchdogAction.RECOVERED, disconnected_for)

        if self.disconnected_since is None:
            self.disconnected_since = now
            return WatchdogResult(WatchdogAction.DISCONNECT_STARTED)

        disconnected_for = max(0.0, now - self.disconnected_since)
        if disconnected_for >= self.grace_seconds:
            return WatchdogResult(WatchdogAction.GRACE_EXCEEDED, disconnected_for)
        return WatchdogResult(WatchdogAction.WAITING, disconnected_for)
