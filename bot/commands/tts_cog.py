import asyncio
import logging
import multiprocessing as mp
import os
import threading
import time
import uuid
from queue import Empty

try:
    import pythoncom
except ImportError:  # pragma: no cover - optional dependency
    pythoncom = None

try:
    import pyttsx3
except ImportError:  # pragma: no cover - optional dependency
    pyttsx3 = None

from twitchio.ext import commands
from bot.commands.base_command import mod_only

logger = logging.getLogger("tts")
_TTS_VOICES: list = []
_TTS_DEFAULT_VOICE_ID: str | None = None
_TTS_LOCK = threading.Lock()

if pyttsx3:
    try:
        _engine = pyttsx3.init()
        _TTS_VOICES = list(_engine.getProperty("voices"))
        _TTS_DEFAULT_VOICE_ID = _engine.getProperty("voice")
        _engine.stop()
        logger.info(
            "[TTS] Voice init complete voices=%d default_voice=%s",
            len(_TTS_VOICES),
            _TTS_DEFAULT_VOICE_ID,
        )
    except Exception:
        logger.warning("[TTS] Failed to enumerate voices", exc_info=True)
        _TTS_VOICES = []
        _TTS_DEFAULT_VOICE_ID = None


def _format_voice_listing() -> str:
    if not pyttsx3 or not _TTS_VOICES:
        return "TTS voices unavailable (pyttsx3 missing/failed)."
    rows = []
    for idx, voice in enumerate(_TTS_VOICES, start=1):
        rows.append(f"{idx}. {voice.name}")
        if len(rows) >= 10:
            rows.append("(and more available)")
            break
    return " | ".join(rows)


def _tts_perform(message: str, voice_id: str | None, request_id: str) -> bool:
    """Synchronous helper that powers pyttsx3 in the background thread."""
    start_time = time.monotonic()
    thread_name = threading.current_thread().name
    voice_label = voice_id or _TTS_DEFAULT_VOICE_ID
    lock_request_time = time.monotonic()
    logger.info(
        "[TTS][%s] Worker thread %s starting voice=%s len=%d",
        request_id,
        thread_name,
        voice_label,
        len(message),
    )
    logger.info(
        "[TTS][%s] Pre-lock state start_method=%s active_children=%d",
        request_id,
        mp.get_start_method(allow_none=True),
        len(mp.active_children()),
    )
    with _TTS_LOCK:
        lock_acquired_time = time.monotonic()
        lock_wait = lock_acquired_time - lock_request_time
        if lock_wait >= 0.001:
            logger.info(
                "[TTS][%s] Waited %.3fs for TTS lock", request_id, lock_wait
            )
        worker_queue: mp.Queue = mp.Queue(maxsize=1)
        worker = mp.Process(
            target=_tts_worker_process,
            args=(message, voice_id, request_id, worker_queue),
            daemon=True,
        )
        timeout_seconds = 12.0
        try:
            logger.info(
                "[TTS][%s] Starting worker daemon=%s name=%s",
                request_id,
                worker.daemon,
                worker.name,
            )
            worker.start()
            logger.info(
                "[TTS][%s] Worker started pid=%s",
                request_id,
                worker.pid,
            )
            worker.join(timeout_seconds)
            join_elapsed = time.monotonic() - lock_acquired_time
            logger.info(
                "[TTS][%s] Worker join complete elapsed=%.3fs alive=%s exitcode=%s",
                request_id,
                join_elapsed,
                worker.is_alive(),
                worker.exitcode,
            )
            if worker.is_alive():
                logger.warning(
                    "[TTS][%s] Worker exceeded %.1fs timeout; terminating",
                    request_id,
                    timeout_seconds,
                )
                worker.terminate()
                worker.join(2.0)
                logger.warning(
                    "[TTS][%s] Worker terminated alive=%s exitcode=%s",
                    request_id,
                    worker.is_alive(),
                    worker.exitcode,
                )
                return False
            if worker.exitcode not in (0, None):
                logger.warning("[TTS][%s] Worker exited with code %s", request_id, worker.exitcode)
            try:
                result = worker_queue.get_nowait()
            except Empty:
                logger.warning(
                    "[TTS][%s] Queue empty on immediate read; retrying with timeout",
                    request_id,
                )
                try:
                    result = worker_queue.get(timeout=0.5)
                except Empty:
                    result = {"ok": False, "error": "No result from worker queue"}
            logger.info("[TTS][%s] Worker result payload=%s", request_id, result)
            if result.get("ok"):
                logger.info(
                    "[TTS][%s] Playback succeeded voice=%s duration=%.3fs",
                    request_id,
                    voice_label,
                    float(result.get("duration", 0.0)),
                )
                return True
            logger.warning(
                "[TTS][%s] Playback failure voice=%s error=%s",
                request_id,
                voice_label,
                result.get("error", "unknown"),
            )
            return False
        except Exception:
            elapsed = time.monotonic() - start_time
            logger.warning(
                "[TTS][%s] Playback failure voice=%s message=%s duration=%.3fs",
                request_id,
                voice_id,
                message[:200],
                elapsed,
                exc_info=True,
            )
            return False
        finally:
            try:
                worker_queue.close()
            except Exception:
                pass
            logger.info(
                "[TTS][%s] Lock section finished total_elapsed=%.3fs",
                request_id,
                time.monotonic() - start_time,
            )


def _tts_worker_process(message: str, voice_id: str | None, request_id: str, result_queue: mp.Queue) -> None:
    engine = None
    start_time = time.monotonic()
    selected_voice = voice_id or _TTS_DEFAULT_VOICE_ID
    pid = os.getpid() if hasattr(os, "getpid") else None
    try:
        if pythoncom:
            pythoncom.CoInitialize()
        engine = pyttsx3.init()
        default_voice = _TTS_DEFAULT_VOICE_ID
        if voice_id:
            engine.setProperty("voice", voice_id)
        elif default_voice:
            engine.setProperty("voice", default_voice)
        engine.say(message)
        engine.runAndWait()
        duration = time.monotonic() - start_time
        result_queue.put(
            {
                "ok": True,
                "duration": duration,
                "pid": pid,
                "voice": selected_voice,
                "len": len(message),
            }
        )
    except Exception as exc:
        try:
            result_queue.put(
                {
                    "ok": False,
                    "error": str(exc),
                    "pid": pid,
                    "voice": selected_voice,
                    "len": len(message),
                }
            )
        except Exception:
            pass
    finally:
        if engine:
            try:
                engine.stop()
            except Exception:
                pass
        if pythoncom:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def _select_tts_voice(index: int | None):
    if not _TTS_VOICES:
        return None, None
    if index is None or index < 1 or index > len(_TTS_VOICES):
        index = 1
    return _TTS_VOICES[index - 1], index


async def _speak_text_with_voice(message: str, voice_index: int | None):
    if not pyttsx3:
        return False, None, None
    voice, resolved_index = _select_tts_voice(voice_index)
    voice_id = voice.id if voice else None
    voice_name = voice.name if voice else None
    voice_label = voice_name or voice_id or _TTS_DEFAULT_VOICE_ID
    request_id = uuid.uuid4().hex[:8]
    logger.info(
        "[TTS][%s] Queued playback voice=%s index=%s message=%s",
        request_id,
        voice_label,
        resolved_index,
        message[:140],
    )
    logger.info(
        "[TTS][%s] Dispatch details selected_voice_id=%s message_len=%d",
        request_id,
        voice_id,
        len(message),
    )
    logger.info("[TTS][%s] Waiting for completion event voice=%s", request_id, voice_label)
    start_time = time.monotonic()
    success = await asyncio.to_thread(_tts_perform, message, voice_id, request_id)
    duration = time.monotonic() - start_time
    logger.info(
        "[TTS][%s] Request complete success=%s voice=%s index=%s duration=%.3fs",
        request_id,
        success,
        voice_label,
        resolved_index,
        duration,
    )
    return success, voice_name, resolved_index


class TtsCog(commands.Cog):
    """Host-wide text-to-speech commands driven by pyttsx3."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="tts")
    @mod_only
    async def tts(self, ctx, *args):
        """Play a message through the host's Windows TTS engine."""
        if not args:
            await ctx.send(
                "Usage: !tts voices | !tts [voice_index] <message>. Voice index defaults to 1."
            )
            return

        first = args[0].strip()
        if first.lower() == "voices":
            logger.info("[TTS] Voice list requested by %s", ctx.author.name)
            await ctx.send(f"Available voices: {_format_voice_listing()}")
            return

        voice_index = None
        message_parts = list(args)
        if message_parts[0].isdigit() and len(message_parts) > 1:
            voice_index = int(message_parts.pop(0))
            logger.info(
                "[TTS] Parsed voice index %s from command by %s",
                voice_index,
                ctx.author.name,
            )

        message_text = " ".join(message_parts).strip()
        if not message_text:
            await ctx.send("Please provide a message for TTS to speak.")
            return

        if not pyttsx3:
            await ctx.send("TTS unavailable because pyttsx3 is not installed on this host.")
            return

        speech_text = f"{ctx.author.name} says {message_text}"
        logger.info(
            "[TTS] Command invoked by %s voice_index=%s message=%s",
            ctx.author.name,
            voice_index,
            message_text,
        )

        success, voice_name, resolved_index = await _speak_text_with_voice(
            speech_text, voice_index
        )
        logger.info(
            "[TTS] Command completed by %s success=%s resolved_voice=%s resolved_index=%s",
            ctx.author.name,
            success,
            voice_name,
            resolved_index,
        )
        if not success:
            await ctx.send("TTS playback failed. Check the host audio device and logs.")
            return


def prepare(bot: commands.Bot):
    bot.add_cog(TtsCog(bot))
    print("[COG] TtsCog loaded")
