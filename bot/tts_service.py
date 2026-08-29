"""Queued, persistent TTS service with a replaceable DECTalk-compatible backend."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger("tts")
ROOT = Path(__file__).resolve().parent.parent


def _console(message: str):
    """TTS diagnostics must remain visible even when logging is redirected."""
    print(f"[TTS] {message}", flush=True)


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class TtsConfig:
    enabled: bool = True
    dectalk_executable: str = ""
    dectalk_args: str = "{text}"
    dectalk_phoneme_mode: bool = True
    dectalk_wave_mode: bool = False
    default_voice: str = "paul"
    max_input_length: int = 500
    max_synthesis_seconds: float = 20.0
    max_playback_seconds: float = 60.0
    global_cooldown_seconds: float = 5.0
    user_cooldown_seconds: float = 30.0
    max_queue_depth: int = 5
    one_queued_per_user: bool = True
    mods_bypass_cooldowns: bool = True
    tokens_persist: bool = True

    @classmethod
    def from_env(cls):
        return cls(
            enabled=_env_bool("TTS_ENABLED", True),
            dectalk_executable=os.getenv("TTS_DECTALK_EXECUTABLE", "").strip(),
            dectalk_args=os.getenv("TTS_DECTALK_ARGS", "{text}"),
            dectalk_phoneme_mode=_env_bool("TTS_DECTALK_PHONEME_MODE", True),
            dectalk_wave_mode=_env_bool("TTS_DECTALK_WAVE_MODE", False),
            default_voice=os.getenv("TTS_DEFAULT_VOICE", "paul").strip() or "paul",
            max_input_length=max(1, int(os.getenv("TTS_MAX_INPUT_LENGTH", "500"))),
            max_synthesis_seconds=max(1, float(os.getenv("TTS_MAX_SYNTHESIS_SECONDS", "20"))),
            max_playback_seconds=max(1, float(os.getenv("TTS_MAX_PLAYBACK_SECONDS", "60"))),
            global_cooldown_seconds=max(0, float(os.getenv("TTS_GLOBAL_COOLDOWN_SECONDS", "5"))),
            user_cooldown_seconds=max(0, float(os.getenv("TTS_USER_COOLDOWN_SECONDS", "30"))),
            max_queue_depth=max(1, int(os.getenv("TTS_MAX_QUEUE_DEPTH", "5"))),
            one_queued_per_user=_env_bool("TTS_ONE_QUEUED_PER_USER", True),
            mods_bypass_cooldowns=_env_bool("TTS_MODS_BYPASS_COOLDOWNS", True),
            tokens_persist=_env_bool("TTS_TOKENS_PERSIST", True),
        )


class SpeechBackend(Protocol):
    name: str
    def available(self) -> bool: ...
    def speak(self, text: str, timeout: float) -> tuple[bool, str | None]: ...


class DectalkProcessBackend:
    name = "Perfect Paul / DECtalk"

    def __init__(self, executable: str, argument_template: str, default_voice: str, phoneme_mode: bool = True, fallback=None, synthesis_timeout: float = 20.0, wave_mode: bool = False):
        self.executable = executable
        self.argument_template = argument_template
        self.default_voice = default_voice
        self.phoneme_mode = phoneme_mode
        self.fallback = fallback
        self.synthesis_timeout = synthesis_timeout
        self.wave_mode = wave_mode
        # A cancelled asyncio worker cannot cancel an already-running to_thread call.
        # Serialize at the backend as a final guard against overlapping playback.
        self._playback_lock = threading.Lock()
        self._process_guard = threading.Lock()
        self._active_process = None

    def available(self):
        return bool(self.executable and Path(self.executable).is_file())

    def _arguments(self, text: str):
        # shlex provides configurable tokenization only; subprocess never invokes a shell.
        tokens = shlex.split(self.argument_template, posix=False)
        arguments = [token.replace("{voice}", self.default_voice).replace("{text}", text) for token in tokens]
        if self.phoneme_mode:
            arguments[:0] = ["-pre", "[:phoneme on]"]
        return arguments

    def _command(self, text: str, wave_output: str | None = None):
        arguments = self._arguments(text)
        if wave_output:
            # Perfect Paul requires all options before the final text argument.
            arguments[-1:-1] = ["-w", wave_output]
        return [self.executable, *arguments]

    @staticmethod
    def _terminate(process, label: str):
        if not process or process.poll() is not None:
            return
        if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
                process.wait(timeout=2)
                _console(f"{label} pid={process.pid} shut down gracefully after Ctrl-Break")
                return
            except (OSError, subprocess.TimeoutExpired):
                pass
        process.kill()
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            _console(f"{label} pid={process.pid} did not exit after kill; abandoning handle")

    @staticmethod
    def _playback_command(wave_path: str):
        script = "import sys,winsound; winsound.PlaySound(sys.argv[1], winsound.SND_FILENAME)"
        return [sys.executable, "-c", script, wave_path]

    def _set_active_process(self, process):
        with self._process_guard:
            self._active_process = process

    def cancel_active(self):
        with self._process_guard:
            process = self._active_process
        if process and process.poll() is None:
            _console(f"Cancelling active TTS process pid={process.pid}")
            self._terminate(process, "TTS process")

    def speak(self, text: str, timeout: float):
        with self._playback_lock:
            return self._speak_locked(text, timeout)

    def _speak_locked(self, text: str, timeout: float):
        if not self.wave_mode:
            return self._speak_direct(text, timeout)
        return self._speak_wave(text, timeout)

    def _speak_direct(self, text: str, timeout: float):
        process = None
        try:
            _console(f"Launching Perfect Paul direct audio (characters={len(text)}, timeout={timeout:g}s)")
            process = subprocess.Popen(
                self._command(text),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=(
                    getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                ),
            )
            self._set_active_process(process)
            _, stderr = process.communicate(timeout=timeout)
            if process.returncode == 0:
                _console(f"Perfect Paul direct playback completed (pid={process.pid}, exit=0)")
                return True, None
            error = (stderr or b"").decode("utf-8", "replace")[:300] or f"exit {process.returncode}"
            _console(f"Perfect Paul direct playback failed (pid={process.pid}, exit={process.returncode}): {error}")
            return False, error
        except subprocess.TimeoutExpired:
            _console(f"Perfect Paul direct playback timed out; terminating pid={getattr(process, 'pid', 'unknown')}")
            self._terminate(process, "Perfect Paul")
            return False, "direct playback timeout"
        except OSError as exc:
            _console(f"Perfect Paul launch failed: {exc}; trying pyttsx3 fallback")
            if self.fallback and self.fallback.available():
                return self.fallback.speak(text, timeout)
            return False, str(exc)
        except Exception as exc:
            logger.warning("[TTS] Perfect Paul direct playback failure", exc_info=True)
            self._terminate(process, "Perfect Paul")
            return False, str(exc)
        finally:
            with self._process_guard:
                self._active_process = None

    def _speak_wave(self, text: str, timeout: float):
        synth_process = playback_process = None
        stage = "synthesis"
        with tempfile.TemporaryDirectory(prefix="meangene_tts_") as temp_dir:
            wave_path = str(Path(temp_dir, "speech.wav"))
            try:
                _console(f"Synthesizing Perfect Paul WAV (characters={len(text)}, timeout={self.synthesis_timeout:g}s)")
                synth_process = subprocess.Popen(
                    self._command(text, wave_path),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    creationflags=(
                        getattr(subprocess, "CREATE_NO_WINDOW", 0)
                        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    ),
                )
                self._set_active_process(synth_process)
                _, stderr = synth_process.communicate(timeout=self.synthesis_timeout)
                if synth_process.returncode != 0:
                    error = (stderr or b"").decode("utf-8", "replace")[:300] or f"exit {synth_process.returncode}"
                    _console(f"Perfect Paul synthesis failed (pid={synth_process.pid}, exit={synth_process.returncode}): {error}")
                    return False, error
                if not Path(wave_path).is_file() or Path(wave_path).stat().st_size <= 44:
                    return False, "Perfect Paul completed without producing a playable WAV"

                stage = "WAV playback"
                _console(f"Perfect Paul WAV ready; starting Windows playback ({Path(wave_path).stat().st_size} bytes)")
                playback_process = subprocess.Popen(
                    self._playback_command(wave_path),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    creationflags=(
                        getattr(subprocess, "CREATE_NO_WINDOW", 0)
                        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    ),
                )
                self._set_active_process(playback_process)
                _, stderr = playback_process.communicate(timeout=timeout)
                if playback_process.returncode == 0:
                    _console(f"WAV playback completed (pid={playback_process.pid}, exit=0)")
                    return True, None
                error = (stderr or b"").decode("utf-8", "replace")[:300] or f"WAV player exit {playback_process.returncode}"
                return False, error
            except subprocess.TimeoutExpired:
                logger.warning("[TTS] TTS %s timeout; terminating process", stage)
                active = playback_process or synth_process
                _console(f"TTS {stage} timed out; terminating pid={getattr(active, 'pid', 'unknown')}")
                self._terminate(active, "TTS process")
                return False, f"{stage} timeout"
            except OSError as exc:
                logger.warning("[TTS] Perfect Paul/WAV launch failed; trying pyttsx3 fallback: %s", exc)
                _console(f"Perfect Paul/WAV launch failed: {exc}; trying pyttsx3 fallback")
                if self.fallback and self.fallback.available():
                    return self.fallback.speak(text, timeout)
                return False, str(exc)
            except Exception as exc:
                logger.warning("[TTS] Perfect Paul/WAV failure", exc_info=True)
                _console(f"Perfect Paul/WAV error: {type(exc).__name__}: {exc}")
                self._terminate(playback_process or synth_process, "TTS process")
                return False, str(exc)
            finally:
                with self._process_guard:
                    self._active_process = None


class PyttsxBackend:
    name = "pyttsx3-fallback"

    def available(self):
        try:
            import pyttsx3  # noqa: F401
            return True
        except ImportError:
            return False

    def speak(self, text: str, timeout: float):
        script = (
            "import pyttsx3,sys; e=pyttsx3.init(); "
            "e.say(sys.argv[1]); e.runAndWait(); e.stop()"
        )
        try:
            subprocess.run(
                [os.sys.executable, "-c", script, text], check=True, timeout=timeout,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True, None
        except subprocess.TimeoutExpired:
            logger.warning("[TTS] Fallback playback timeout")
            return False, "playback timeout"
        except Exception as exc:
            logger.warning("[TTS] Fallback invocation failure", exc_info=True)
            return False, str(exc)


class TokenStore:
    def __init__(self, path=ROOT / "data" / "tts_tokens.json", persistent=True):
        self.path = Path(path); self.persistent = persistent; self.data = self._load()

    def _load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {"balances": {}}

    def _save(self):
        if not self.persistent: return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix="tts_tokens_", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream: json.dump(self.data, stream, indent=2)
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp): os.unlink(temp)

    @staticmethod
    def id_key(user_id): return f"id:{user_id}" if user_id else None
    @staticmethod
    def login_key(login): return f"login:{str(login).casefold()}"

    def balance(self, user_id, login):
        balances = self.data["balances"]
        return int(balances.get(self.id_key(user_id), 0) if user_id else balances.get(self.login_key(login), 0)) + (int(balances.get(self.login_key(login), 0)) if user_id else 0)

    def grant(self, login, amount=1):
        key = self.login_key(login); self.data["balances"][key] = int(self.data["balances"].get(key, 0)) + amount; self._save(); return self.data["balances"][key]

    def consume(self, user_id, login):
        balances = self.data["balances"]; id_key = self.id_key(user_id); login_key = self.login_key(login)
        key = id_key if id_key and int(balances.get(id_key, 0)) > 0 else login_key
        if int(balances.get(key, 0)) < 1: return False
        balances[key] -= 1
        if id_key and key == login_key:
            balances[id_key] = int(balances.get(id_key, 0)) + balances.pop(login_key)
        self._save(); return True


@dataclass
class SpeechRequest:
    user_key: str
    login: str
    display: str
    text: str
    accepted_at: float


class TtsService:
    def __init__(self, config=None, backend=None, token_store=None, clock=time.monotonic):
        self.config = config or TtsConfig.from_env(); self.clock = clock
        fallback = PyttsxBackend()
        primary = DectalkProcessBackend(
            self.config.dectalk_executable,
            self.config.dectalk_args,
            self.config.default_voice,
            self.config.dectalk_phoneme_mode,
            fallback,
            self.config.max_synthesis_seconds,
            self.config.dectalk_wave_mode,
        )
        self.backend = backend or (primary if primary.available() else fallback)
        if backend is None and primary.available():
            logger.info("TTS backend: Perfect Paul / DECtalk")
            logger.info("Executable: %s", self.config.dectalk_executable)
            logger.info("Phoneme mode: %s", "enabled" if self.config.dectalk_phoneme_mode else "disabled")
            _console(f"Backend ready: Perfect Paul / DECtalk | {self.config.dectalk_executable} | phoneme mode {'on' if self.config.dectalk_phoneme_mode else 'off'}")
            _console(f"Playback mode: {'temporary WAV' if self.config.dectalk_wave_mode else 'direct DECtalk audio'}")
        elif backend is None:
            reason = "not configured" if not self.config.dectalk_executable else "configured executable does not exist"
            logger.warning("TTS backend: %s (Perfect Paul fallback reason: %s)", self.backend.name, reason)
            _console(f"Backend fallback: {self.backend.name} | Perfect Paul {reason}")
        self.tokens = token_store or TokenStore(persistent=self.config.tokens_persist)
        self.queue = asyncio.Queue(maxsize=self.config.max_queue_depth)
        self.pending_users = set(); self.last_global = float("-inf"); self.last_user = {}; self.worker_task = None
        self.active_request = None; self.last_error = None

    def ensure_worker(self):
        if not self.worker_task or self.worker_task.done():
            if self.worker_task and not self.worker_task.cancelled():
                try:
                    error = self.worker_task.exception()
                except Exception as exc:
                    error = exc
                if error:
                    _console(f"Playback worker had stopped: {type(error).__name__}: {error}; restarting")
            self.worker_task = asyncio.create_task(self._worker(), name="tts-playback-worker")
            _console("Sequential playback worker started")

    def status(self):
        worker = "stopped" if not self.worker_task else ("running" if not self.worker_task.done() else "stopped")
        return {
            "worker": worker,
            "active": self.active_request.display if self.active_request else None,
            "queued": self.queue.qsize(),
            "limit": self.config.max_queue_depth,
            "last_error": self.last_error,
        }

    def reset(self):
        """Cancel current playback and discard the queue without retaining users."""
        old_worker = self.worker_task
        self.worker_task = None
        if old_worker and not old_worker.done():
            old_worker.cancel()
        cancel_backend = getattr(self.backend, "cancel_active", None)
        if callable(cancel_backend):
            cancel_backend()
        discarded = 0
        while True:
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                discarded += 1
                self.queue.task_done()
        self.pending_users.clear()
        self.active_request = None
        self.last_error = None
        _console(f"Queue reset (discarded={discarded}, active_cancelled={'yes' if old_worker else 'no'})")
        return discarded

    def cooldown_reason(self, user_key, is_mod):
        if is_mod and self.config.mods_bypass_cooldowns: return None
        now = self.clock(); global_left = self.config.global_cooldown_seconds - (now - self.last_global)
        user_left = self.config.user_cooldown_seconds - (now - self.last_user.get(user_key, float("-inf")))
        wait = max(global_left, user_left)
        return f"TTS is cooling down for {max(1, int(wait + .999))}s." if wait > 0 else None

    def accept(self, user_key, login, display, text, is_mod):
        if not self.config.enabled: return False, "TTS is currently disabled."
        if not self.backend.available(): return False, "TTS is unavailable; configure a DECTalk executable or pyttsx3 fallback."
        if not text or len(text) > self.config.max_input_length: return False, f"TTS messages must be 1-{self.config.max_input_length} characters."
        reason = self.cooldown_reason(user_key, is_mod)
        if reason: logger.info("[TTS] Cooldown rejection user=%s", login); return False, reason
        if self.config.one_queued_per_user and user_key in self.pending_users: return False, "You already have a TTS message queued."
        request = SpeechRequest(user_key, login, display, text, self.clock())
        try: self.queue.put_nowait(request)
        except asyncio.QueueFull: logger.info("[TTS] Queue rejection user=%s", login); return False, "The TTS queue is full."
        self.pending_users.add(user_key); self.last_global = self.clock(); self.last_user[user_key] = self.clock(); self.ensure_worker()
        logger.info("[TTS] Accepted user=%s access=%s backend=%s len=%d", login, "moderator" if is_mod else "token", self.backend.name, len(text))
        _console(f"Queued @{display} (characters={len(text)}, waiting={self.queue.qsize()}/{self.config.max_queue_depth})")
        return True, f"TTS queued ({self.queue.qsize()} waiting)."

    async def _worker(self):
        _console("Playback worker is ready")
        while True:
            request = await self.queue.get()
            self.active_request = request
            _console(f"Playing @{request.display} (waiting behind={self.queue.qsize()})")
            try:
                watchdog = self.config.max_synthesis_seconds + self.config.max_playback_seconds + 8
                ok, error = await asyncio.wait_for(
                    asyncio.to_thread(self.backend.speak, request.text, self.config.max_playback_seconds),
                    timeout=watchdog,
                )
                if not ok:
                    self.last_error = error or "unknown playback failure"
                    logger.warning("[TTS] Playback failed user=%s error=%s; engine reset for next request", request.login, error)
                    _console(f"Playback failed for @{request.display}: {self.last_error}; continuing queue")
                else:
                    self.last_error = None
                    _console(f"Playback finished for @{request.display}")
            except asyncio.TimeoutError:
                self.last_error = "TTS backend watchdog timeout"
                cancel_backend = getattr(self.backend, "cancel_active", None)
                if callable(cancel_backend):
                    cancel_backend()
                _console(f"Backend watchdog recovered @{request.display}; continuing queue")
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("[TTS] Worker recovered from backend error", exc_info=True)
                _console(f"Worker recovered after @{request.display}: {self.last_error}; continuing queue")
            finally:
                self.active_request = None
                self.pending_users.discard(request.user_key); self.queue.task_done()


_shared_service = None


def get_tts_service():
    global _shared_service
    if _shared_service is None:
        _shared_service = TtsService()
    return _shared_service
