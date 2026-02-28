"""Logging helpers and telemetry shims for RPG cog.

This module re-exports `log_event` from `bot.telemetry` so imports that expect
`bot.logging_config.log_event` continue to work after refactors.
"""

from bot.telemetry import log_event

__all__ = ["log_event"]
