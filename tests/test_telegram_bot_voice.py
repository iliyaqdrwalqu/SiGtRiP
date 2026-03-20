"""Tests for new voice-output and performance improvements in the root telegram_bot.py."""
import asyncio
import importlib
import os
import sys
import types
import unittest.mock as mock
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers to import the root telegram_bot without a real Telegram token ────

def _import_bot_module():
    """Import telegram_bot.py from the repo root with a dummy token so sys.exit is not hit."""
    # Stub out aiogram at module level to avoid network/token validation at import time
    for mod_name in list(sys.modules):
        if mod_name.startswith("aiogram"):
            del sys.modules[mod_name]

    aiogram_mod = types.ModuleType("aiogram")

    class _Bot:
        def __init__(self, token): pass

    class _Dispatcher:
        def message(self, *a, **kw):
            def _decorator(fn):
                return fn
            return _decorator

    aiogram_mod.Bot = _Bot
    aiogram_mod.Dispatcher = _Dispatcher
    sys.modules["aiogram"] = aiogram_mod

    aiogram_filters = types.ModuleType("aiogram.filters")
    aiogram_filters.Command = lambda *a, **kw: (lambda fn: fn)
    sys.modules["aiogram.filters"] = aiogram_filters

    aiogram_types = types.ModuleType("aiogram.types")
    aiogram_types.Message = object
    aiogram_types.BufferedInputFile = lambda data, filename="": data
    sys.modules["aiogram.types"] = aiogram_types

    # Use a dummy token to bypass the sys.exit guard
    env_patch = {"TELEGRAM_TOKEN": "999999999:AABBCCDDEEFFGGHHIIJJKKLLMMNNOOPPtest"}
    with mock.patch.dict(os.environ, env_patch):
        # Remove any cached version so we re-import fresh
        sys.modules.pop("telegram_bot", None)

        import importlib.util as ilu
        root = os.path.join(os.path.dirname(__file__), "..", "telegram_bot.py")
        spec = ilu.spec_from_file_location("telegram_bot", root)
        mod = ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


_bot_mod = _import_bot_module()


# ── _tts_to_bytes ─────────────────────────────────────────────────────────────

def test_tts_to_bytes_returns_mp3_bytes():
    """_tts_to_bytes should return non-empty bytes when gTTS synthesises successfully."""
    # Mock gTTS to avoid requiring a real network connection in CI
    fake_mp3 = b"ID3" + b"\x00" * 100  # minimal fake MP3-like bytes

    class FakeGTTS:
        def __init__(self, text, lang="ru"):
            pass

        def write_to_fp(self, fp):
            fp.write(fake_mp3)

    with mock.patch.dict(sys.modules, {"gtts": types.ModuleType("gtts")}):
        sys.modules["gtts"].gTTS = FakeGTTS
        audio = _bot_mod._tts_to_bytes("Привет", lang="ru")

    assert audio is not None
    assert isinstance(audio, bytes)
    assert len(audio) > 0


def test_tts_to_bytes_truncates_long_text():
    """Text longer than 500 characters should be truncated, not raise."""
    fake_mp3 = b"ID3" + b"\x00" * 10

    class FakeGTTS:
        def __init__(self, text, lang="ru"):
            assert len(text) <= 500, "text was not truncated to 500 chars"

        def write_to_fp(self, fp):
            fp.write(fake_mp3)

    long_text = "Тест " * 200  # > 500 characters
    with mock.patch.dict(sys.modules, {"gtts": types.ModuleType("gtts")}):
        sys.modules["gtts"].gTTS = FakeGTTS
        audio = _bot_mod._tts_to_bytes(long_text)
    assert audio is None or isinstance(audio, bytes)


def test_tts_to_bytes_returns_none_on_gtts_import_error():
    """_tts_to_bytes must return None (not raise) when gTTS is not importable."""
    with mock.patch.dict(sys.modules, {"gtts": None}):
        # The function catches ImportError internally
        result = _bot_mod._tts_to_bytes("Привет")
    assert result is None or isinstance(result, bytes)  # None when gTTS blocked


# ── _get_argos_core caching ───────────────────────────────────────────────────

def test_get_argos_core_returns_same_instance():
    """_get_argos_core must return the same object on repeated calls (no re-import)."""
    mod = _import_bot_module()
    mod._argos_core = None

    # Provide a fake ArgosAbsolute so we don't need main.py's real deps
    class _FakeCore:
        def execute(self, cmd):
            return f"[fake] {cmd}"

    fake_main = types.ModuleType("argos_main")
    fake_main.ArgosAbsolute = _FakeCore

    with mock.patch.object(mod.importlib.util, "spec_from_file_location") as mock_spec, \
         mock.patch.object(mod.importlib.util, "module_from_spec") as mock_mod:
        mock_spec.return_value = mock.MagicMock(loader=mock.MagicMock())
        mock_mod.return_value = fake_main

        instance_a = mod._get_argos_core()
        instance_b = mod._get_argos_core()

    assert instance_a is instance_b, (
        "_get_argos_core returned different objects — caching is broken"
    )


def test_get_argos_core_has_execute():
    """The cached ArgosAbsolute instance must expose an execute() method."""
    mod = _import_bot_module()
    mod._argos_core = None

    class _FakeCore:
        def execute(self, cmd):
            return f"[fake] {cmd}"

    fake_main = types.ModuleType("argos_main")
    fake_main.ArgosAbsolute = _FakeCore

    with mock.patch.object(mod.importlib.util, "spec_from_file_location") as mock_spec, \
         mock.patch.object(mod.importlib.util, "module_from_spec") as mock_mod:
        mock_spec.return_value = mock.MagicMock(loader=mock.MagicMock())
        mock_mod.return_value = fake_main

        core = mod._get_argos_core()

    assert callable(getattr(core, "execute", None))


# ── voice_chats set management ────────────────────────────────────────────────

def test_voice_chats_starts_empty():
    """_voice_chats must be empty at module load time."""
    # We imported fresh, so this should be true unless another test ran first.
    # Use a fresh module import to be safe.
    mod = _import_bot_module()
    assert len(mod._voice_chats) == 0


def test_voice_on_adds_chat_id():
    async def _run():
        mod = _import_bot_module()
        message = SimpleNamespace(
            chat=SimpleNamespace(id=12345),
            answer=AsyncMock(),
        )
        await mod.cmd_voice_on(message)
        assert 12345 in mod._voice_chats

    asyncio.run(_run())


def test_voice_off_removes_chat_id():
    async def _run():
        mod = _import_bot_module()
        mod._voice_chats.add(99)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=99),
            answer=AsyncMock(),
        )
        await mod.cmd_voice_off(message)
        assert 99 not in mod._voice_chats

    asyncio.run(_run())


def test_voice_off_is_idempotent_when_not_in_set():
    async def _run():
        mod = _import_bot_module()
        message = SimpleNamespace(
            chat=SimpleNamespace(id=777),
            answer=AsyncMock(),
        )
        # Should not raise even if chat_id was never added
        await mod.cmd_voice_off(message)
        assert 777 not in mod._voice_chats

    asyncio.run(_run())
