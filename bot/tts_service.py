"""Queued, persistent TTS service with a replaceable DECTalk-compatible backend."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger("tts")
ROOT = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class TtsConfig:
    enabled: bool = True
    dectalk_executable: str = ""
    dectalk_args: str = "-pre [:np] {text}"
    default_voice: str = "paul"
    max_input_length: int = 500
    max_playback_seconds: float = 20.0
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
            dectalk_args=os.getenv("TTS_DECTALK_ARGS", "-pre [:np] {text}"),
            default_voice=os.getenv("TTS_DEFAULT_VOICE", "paul").strip() or "paul",
            max_input_length=max(1, int(os.getenv("TTS_MAX_INPUT_LENGTH", "500"))),
            max_playback_seconds=max(1, float(os.getenv("TTS_MAX_PLAYBACK_SECONDS", "20"))),
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
    name = "dectalk"

    def __init__(self, executable: str, argument_template: str, default_voice: str):
        self.executable = executable
        self.argument_template = argument_template
        self.default_voice = default_voice

    def available(self):
        return bool(self.executable and Path(self.executable).is_file())

    def _arguments(self, text: str):
        # shlex provides configurable tokenization only; subprocess never invokes a shell.
        tokens = shlex.split(self.argument_template, posix=False)
        return [token.replace("{voice}", self.default_voice).replace("{text}", text) for token in tokens]

    def speak(self, text: str, timeout: float):
        process = None
        try:
            process = subprocess.Popen(
                [self.executable, *self._arguments(text)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            _, stderr = process.communicate(timeout=timeout)
            if process.returncode == 0:
                return True, None
            return False, (stderr or b"").decode("utf-8", "replace")[:300] or f"exit {process.returncode}"
        except subprocess.TimeoutExpired:
            logger.warning("[TTS] DECTalk playback timeout; terminating process")
            if process:
                process.kill(); process.communicate()
            return False, "playback timeout"
        except Exception as exc:
            logger.warning("[TTS] DECTalk invocation failure", exc_info=True)
            if process and process.poll() is None:
                process.kill()
            return False, str(exc)


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
        primary = DectalkProcessBackend(self.config.dectalk_executable, self.config.dectalk_args, self.config.default_voice)
        self.backend = backend or (primary if primary.available() else PyttsxBackend())
        self.tokens = token_store or TokenStore(persistent=self.config.tokens_persist)
        self.queue = asyncio.Queue(maxsize=self.config.max_queue_depth)
        self.pending_users = set(); self.last_global = float("-inf"); self.last_user = {}; self.worker_task = None

    def ensure_worker(self):
        if not self.worker_task or self.worker_task.done(): self.worker_task = asyncio.create_task(self._worker())

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
        return True, f"TTS queued ({self.queue.qsize()} waiting)."

    async def _worker(self):
        while True:
            request = await self.queue.get()
            try:
                ok, error = await asyncio.to_thread(self.backend.speak, request.text, self.config.max_playback_seconds)
                if not ok: logger.warning("[TTS] Playback failed user=%s error=%s; engine reset for next request", request.login, error)
            except Exception:
                logger.warning("[TTS] Worker recovered from backend error", exc_info=True)
            finally:
                self.pending_users.discard(request.user_key); self.queue.task_done()


_shared_service = None


def get_tts_service():
    global _shared_service
    if _shared_service is None:
        _shared_service = TtsService()
    return _shared_service
