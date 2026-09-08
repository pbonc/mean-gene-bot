"""Privacy-safe structured observability for community-lore operations."""

from __future__ import annotations

from typing import Any, Callable

from bot.telemetry import log_event


Observer = Callable[[str, dict[str, Any]], None]


def emit(observer: Observer, event: str, **fields: Any) -> None:
    """Emit a lore event; callers provide only bounded, allowlisted scalar fields."""
    try:
        observer(event, fields)
    except Exception:
        # Observability must never affect chat processing or lore policy.
        pass


def default_observer(event: str, fields: dict[str, Any]) -> None:
    log_event(event, fields)


def startup_diagnostics(settings, *, hermes_available: bool, moderation_attached: bool,
                        observer: Observer = default_observer) -> None:
    emit(
        observer,
        "lore.startup.summary",
        capture_enabled=bool(settings.enabled),
        trigger_messages=int(settings.trigger_messages),
        cooldown_seconds=float(settings.cooldown_seconds),
        buffer_messages=int(settings.buffer_messages),
        input_messages=int(settings.input_messages),
        input_characters=int(settings.input_characters),
        max_items=int(settings.max_items),
        hermes_available=bool(hermes_available),
        moderation_attached=bool(moderation_attached),
    )
    if settings.enabled and not moderation_attached:
        emit(observer, "lore.startup.degraded", reason="moderation_unavailable")
