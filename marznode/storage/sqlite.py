"""SQLite-backed storage for marznode.

Users and their inbound associations are persisted so the node survives
restarts even when the Panel is temporarily unreachable. Inbounds
themselves are config (loaded from disk at backend startup), so they are
kept in-memory just like MemoryStorage; User.inbounds is re-hydrated
from the in-memory inbound registry on each read.
"""

import asyncio
import logging
import sqlite3
from pathlib import Path

import aiosqlite

from .base import BaseStorage
from ..models import Inbound, User

logger = logging.getLogger(__name__)


class SqliteStorage(BaseStorage):
    def __init__(self, db_path: str = "./marznode.db"):
        self._db_path = db_path
        self._inbounds: dict[str, Inbound] = {}
        self._db_lock = asyncio.Lock()
        self._db: aiosqlite.Connection | None = None
        self._init_schema()

    def _init_schema(self) -> None:
        parent = Path(self._db_path).parent
        if str(parent) and parent != Path("."):
            parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL,
                    key TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_inbounds (
                    user_id INTEGER NOT NULL,
                    inbound_tag TEXT NOT NULL,
                    PRIMARY KEY (user_id, inbound_tag),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_user_inbounds_tag
                    ON user_inbounds(inbound_tag);
                """
            )
            conn.commit()

    async def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            async with self._db_lock:
                if self._db is None:
                    db = await aiosqlite.connect(self._db_path)
                    await db.execute("PRAGMA foreign_keys = ON")
                    await db.commit()
                    self._db = db
        return self._db

    def _hydrate_inbounds(self, tags: list[str]) -> list[Inbound]:
        return [self._inbounds[t] for t in tags if t in self._inbounds]

    async def list_users(
        self, user_id: int | None = None
    ) -> list[User] | User | None:
        db = await self._conn()
        if user_id is not None:
            async with db.execute(
                "SELECT id, username, key FROM users WHERE id = ?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                return None
            async with db.execute(
                "SELECT inbound_tag FROM user_inbounds WHERE user_id = ?",
                (user_id,),
            ) as cur:
                tag_rows = await cur.fetchall()
            return User(
                id=row[0],
                username=row[1],
                key=row[2],
                inbounds=self._hydrate_inbounds([r[0] for r in tag_rows]),
            )

        async with db.execute("SELECT id, username, key FROM users") as cur:
            user_rows = await cur.fetchall()
        async with db.execute(
            "SELECT user_id, inbound_tag FROM user_inbounds"
        ) as cur:
            ub_rows = await cur.fetchall()
        tags_by_user: dict[int, list[str]] = {}
        for uid, tag in ub_rows:
            tags_by_user.setdefault(uid, []).append(tag)
        return [
            User(
                id=r[0],
                username=r[1],
                key=r[2],
                inbounds=self._hydrate_inbounds(tags_by_user.get(r[0], [])),
            )
            for r in user_rows
        ]

    async def list_inbounds(
        self,
        tag: list[str] | str | None = None,
        include_users: bool = False,
    ) -> list[Inbound] | Inbound | None:
        if tag is None:
            return list(self._inbounds.values())
        if isinstance(tag, str):
            return self._inbounds.get(tag)
        return [self._inbounds[t] for t in tag if t in self._inbounds]

    async def list_inbound_users(self, tag: str) -> list[User]:
        db = await self._conn()
        async with db.execute(
            """
            SELECT u.id, u.username, u.key
              FROM users u
              JOIN user_inbounds ui ON ui.user_id = u.id
             WHERE ui.inbound_tag = ?
            """,
            (tag,),
        ) as cur:
            user_rows = await cur.fetchall()
        if not user_rows:
            return []
        ids = [r[0] for r in user_rows]
        placeholders = ",".join("?" * len(ids))
        async with db.execute(
            f"SELECT user_id, inbound_tag FROM user_inbounds "
            f"WHERE user_id IN ({placeholders})",
            ids,
        ) as cur:
            ub_rows = await cur.fetchall()
        tags_by_user: dict[int, list[str]] = {}
        for uid, t in ub_rows:
            tags_by_user.setdefault(uid, []).append(t)
        return [
            User(
                id=r[0],
                username=r[1],
                key=r[2],
                inbounds=self._hydrate_inbounds(tags_by_user.get(r[0], [])),
            )
            for r in user_rows
        ]

    async def remove_user(self, user: User) -> None:
        db = await self._conn()
        await db.execute("DELETE FROM users WHERE id = ?", (user.id,))
        await db.commit()

    async def update_user_inbounds(
        self, user: User, inbounds: list[Inbound]
    ) -> None:
        db = await self._conn()
        await db.execute(
            """
            INSERT INTO users (id, username, key) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                key = excluded.key
            """,
            (user.id, user.username, user.key),
        )
        await db.execute(
            "DELETE FROM user_inbounds WHERE user_id = ?", (user.id,)
        )
        if inbounds:
            await db.executemany(
                "INSERT INTO user_inbounds (user_id, inbound_tag) VALUES (?, ?)",
                [(user.id, inb.tag) for inb in inbounds],
            )
        await db.commit()
        user.inbounds = inbounds

    async def flush_users(self) -> None:
        db = await self._conn()
        await db.execute("DELETE FROM users")
        await db.commit()

    def register_inbound(self, inbound: Inbound) -> None:
        self._inbounds[inbound.tag] = inbound

    def remove_inbound(self, inbound: Inbound | str) -> None:
        tag = inbound if isinstance(inbound, str) else inbound.tag
        self._inbounds.pop(tag, None)
