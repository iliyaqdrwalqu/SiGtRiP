\
"""db_init.py — Инициализация SQLite схемы"""
from __future__ import annotations
import sqlite3, os
from src.argos_logger import get_logger
log = get_logger("argos.db")

DB_PATH = os.getenv("ARGOS_DB","data/argos_memory.db")

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT DEFAULT 'general',
            key TEXT NOT NULL,
            value TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT, text TEXT, category TEXT DEFAULT 'ai',
            ts DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, content TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command TEXT, interval_sec INTEGER, run_at REAL,
            last_run REAL DEFAULT 0, runs INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS context_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            summary TEXT NOT NULL,
            messages_covered INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit(); conn.close()
    log.info("DB инициализирована: %s", DB_PATH)


class ContextDB:
    """
    Вспомогательный класс для работы с историей диалога и сжатой памятью
    (Context Anchor — Якорь контекста).
    """

    def __init__(self, db_path: str = DB_PATH):
        self._path = db_path
        os.makedirs("data", exist_ok=True)

    def _connect(self):
        return sqlite3.connect(self._path)

    def get_recent_history(self, limit: int = 50) -> list[dict]:
        """Возвращает последние `limit` сообщений из истории диалога."""
        try:
            conn = self._connect()
            cur = conn.execute(
                "SELECT role, text, ts FROM chat_history ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            conn.close()
            return [{"role": r[0], "text": r[1], "ts": r[2]} for r in reversed(rows)]
        except Exception as e:
            log.warning("ContextDB.get_recent_history: %s", e)
            return []

    def save_summary(self, summary: str, messages_covered: int = 0) -> None:
        """Сохраняет сжатое резюме диалога."""
        if not summary:
            return
        try:
            conn = self._connect()
            conn.execute(
                "INSERT INTO context_summaries (summary, messages_covered) VALUES (?, ?)",
                (summary[:2000], messages_covered),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            log.warning("ContextDB.save_summary: %s", e)

    def get_latest_summary(self) -> str:
        """Возвращает последнее сохранённое резюме или пустую строку."""
        try:
            conn = self._connect()
            cur = conn.execute(
                "SELECT summary FROM context_summaries ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()
            conn.close()
            return row[0] if row else ""
        except Exception as e:
            log.warning("ContextDB.get_latest_summary: %s", e)
            return ""

    def clear_old_history(self, keep_last: int = 10) -> None:
        """Удаляет старые сообщения, оставляя только последние `keep_last`."""
        try:
            conn = self._connect()
            conn.execute(
                """DELETE FROM chat_history WHERE id NOT IN (
                    SELECT id FROM chat_history ORDER BY id DESC LIMIT ?
                )""",
                (keep_last,),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            log.warning("ContextDB.clear_old_history: %s", e)
