"""Tests for file-handling features added to the root telegram_bot.py."""
import asyncio
import io
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers to import root telegram_bot without a real Telegram token ─────────

def _import_bot_module():
    """Import telegram_bot.py from the repo root with a dummy token."""
    for mod_name in list(sys.modules):
        if mod_name.startswith("aiogram"):
            del sys.modules[mod_name]

    aiogram_mod = types.ModuleType("aiogram")

    class _Bot:
        def __init__(self, token):
            pass

        async def download(self, document, *, destination):
            pass

    class _Dispatcher:
        def message(self, *a, **kw):
            def _decorator(fn):
                return fn
            return _decorator

    aiogram_mod.Bot = _Bot
    aiogram_mod.Dispatcher = _Dispatcher
    # F is used as F.document — any object with a .document attribute works
    aiogram_mod.F = SimpleNamespace(document=object(), text=object(), voice=object())
    sys.modules["aiogram"] = aiogram_mod

    aiogram_filters = types.ModuleType("aiogram.filters")
    aiogram_filters.Command = lambda *a, **kw: (lambda fn: fn)
    sys.modules["aiogram.filters"] = aiogram_filters

    aiogram_types = types.ModuleType("aiogram.types")
    aiogram_types.Message = object
    aiogram_types.BufferedInputFile = lambda data, filename="": data
    sys.modules["aiogram.types"] = aiogram_types

    env_patch = {"TELEGRAM_TOKEN": "999999999:AABBCCDDEEFFGGHHIIJJKKLLMMNNOOPPtest"}
    with patch.dict(os.environ, env_patch):
        sys.modules.pop("telegram_bot", None)
        import importlib.util as ilu
        root = os.path.join(os.path.dirname(__file__), "..", "telegram_bot.py")
        spec = ilu.spec_from_file_location("telegram_bot", root)
        mod = ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


_bot_mod = _import_bot_module()


# ── _read_file_content ────────────────────────────────────────────────────────

def test_read_file_content_utf8_text():
    """Plain UTF-8 text should be decoded and returned with a content header."""
    raw = "Привет, мир!\nСтрока 2.".encode("utf-8")
    result = _bot_mod._read_file_content(raw, "hello.txt")
    assert "📄 Содержимое файла:" in result
    assert "Привет, мир!" in result


def test_read_file_content_latin1_text():
    """Latin-1 text that is not valid UTF-8 should still be decoded."""
    raw = "caf\xe9".encode("latin-1")  # 'café' in latin-1, invalid as UTF-8
    result = _bot_mod._read_file_content(raw, "text.txt")
    assert "📄 Содержимое файла:" in result
    assert "caf" in result


def test_read_file_content_binary_file():
    """Files containing null bytes should be reported as binary data."""
    raw = b"MZ\x90\x00\x03\x00\x00\x00"  # PE executable header (contains nulls)
    result = _bot_mod._read_file_content(raw, "program.exe")
    assert "бинарные данные" in result
    assert "📄" not in result


def test_read_file_content_truncates_long_text():
    """Text exceeding MAX_FILE_DISPLAY_CHARS must be truncated with a note."""
    long_text = "Тест " * 2000  # well over 3000 characters
    raw = long_text.encode("utf-8")
    result = _bot_mod._read_file_content(raw, "big.txt")
    assert "показано" in result
    # The displayed portion must not exceed the limit plus the truncation note
    assert len(result) < len(long_text)


def test_read_file_content_short_text_not_truncated():
    """Text shorter than MAX_FILE_DISPLAY_CHARS must not get the truncation note."""
    short_text = "Краткое содержание."
    raw = short_text.encode("utf-8")
    result = _bot_mod._read_file_content(raw, "short.txt")
    assert "показано" not in result
    assert short_text in result


def test_read_file_content_empty_file():
    """An empty file should return the content header with an empty body."""
    result = _bot_mod._read_file_content(b"", "empty.txt")
    assert "📄 Содержимое файла:" in result


# ── handle_document ───────────────────────────────────────────────────────────

def _make_document_message(
    file_name="test.txt",
    file_size=100,
    mime_type="text/plain",
    file_id="abc123",
):
    """Return a mock aiogram Message with a document attachment."""
    doc = SimpleNamespace(
        file_id=file_id,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
    )
    message = SimpleNamespace(
        document=doc,
        chat=SimpleNamespace(id=42, type="private"),
        from_user=SimpleNamespace(id=1, username="testuser", full_name="Test User"),
        answer=AsyncMock(),
    )
    return message


def test_handle_document_too_large_sends_warning():
    """Files over MAX_FILE_READ_BYTES should trigger a size-limit warning."""
    async def _run():
        mod = _import_bot_module()
        msg = _make_document_message(
            file_size=mod.MAX_FILE_READ_BYTES + 1,
            file_name="huge.bin",
        )

        async def _fake_save(*args, **kwargs):
            pass

        with patch.object(mod, "save_message", side_effect=_fake_save):
            await mod.handle_document(msg)

        calls = [str(c) for c in msg.answer.call_args_list]
        assert any("слишком большой" in c for c in calls)

    asyncio.run(_run())


def test_handle_document_text_file_sends_content():
    """A small text file should be downloaded, decoded, and sent back."""
    async def _run():
        mod = _import_bot_module()
        content_bytes = "Привет из файла!".encode("utf-8")
        msg = _make_document_message(file_size=len(content_bytes))

        async def _fake_save(*args, **kwargs):
            pass

        async def _fake_download(doc, *, destination):
            destination.write(content_bytes)

        with patch.object(mod, "save_message", side_effect=_fake_save), \
             patch.object(mod, "bot") as mock_bot:
            mock_bot.download = AsyncMock(side_effect=_fake_download)
            await mod.handle_document(msg)

        all_text = " ".join(str(c) for c in msg.answer.call_args_list)
        assert "Привет из файла!" in all_text

    asyncio.run(_run())


def test_handle_document_saves_to_history():
    """Receiving a file must persist a history entry describing the file."""
    async def _run():
        mod = _import_bot_module()
        content_bytes = b"data"
        msg = _make_document_message(file_name="report.txt", file_size=len(content_bytes))
        saved_texts = []

        async def _capture_save(chat_id, user_id, username, full_name, text):
            saved_texts.append(text)

        async def _fake_download(doc, *, destination):
            destination.write(content_bytes)

        with patch.object(mod, "save_message", side_effect=_capture_save), \
             patch.object(mod, "bot") as mock_bot:
            mock_bot.download = AsyncMock(side_effect=_fake_download)
            await mod.handle_document(msg)

        assert any("report.txt" in t for t in saved_texts), (
            f"Expected file name in saved history; got: {saved_texts}"
        )

    asyncio.run(_run())


def test_handle_document_missing_filename_uses_default():
    """A document with no file_name must use the default placeholder name."""
    async def _run():
        mod = _import_bot_module()
        content_bytes = b"ok"
        msg = _make_document_message(file_name=None, file_size=len(content_bytes))

        async def _fake_save(chat_id, user_id, username, full_name, text):
            pass

        async def _fake_download(doc, *, destination):
            destination.write(content_bytes)

        with patch.object(mod, "save_message", side_effect=_fake_save), \
             patch.object(mod, "bot") as mock_bot:
            mock_bot.download = AsyncMock(side_effect=_fake_download)
            # Should not raise even with no file name
            await mod.handle_document(msg)

        # Check reply contains the default placeholder
        all_text = " ".join(str(c) for c in msg.answer.call_args_list)
        assert "неизвестный_файл" in all_text

    asyncio.run(_run())
