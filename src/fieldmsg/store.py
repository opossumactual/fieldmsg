"""SQLite storage layer for messages, contacts, and announces."""

import sqlite3
import time
from pathlib import Path


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    """Row factory that returns dicts keyed by column name."""
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    peer_hash TEXT NOT NULL,
    direction TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp REAL NOT NULL,
    status TEXT DEFAULT 'pending',
    read INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS contacts (
    hash TEXT PRIMARY KEY,
    nickname TEXT NOT NULL,
    display_name TEXT,
    last_seen REAL,
    trusted INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS announces (
    hash TEXT NOT NULL,
    display_name TEXT,
    hops INTEGER,
    timestamp REAL NOT NULL,
    interface TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_peer ON messages(peer_hash, timestamp);
CREATE INDEX IF NOT EXISTS idx_announces_time ON announces(timestamp);
"""


class Store:
    """SQLite-backed storage for fieldmsg data."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = _dict_factory
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── Messages ──────────────────────────────────────────────────────

    def save_message(
        self,
        msg_id: str,
        peer_hash: str,
        direction: str,
        content: str,
        timestamp: float,
        status: str = "pending",
    ) -> None:
        """INSERT OR REPLACE a message. Incoming messages are unread; outgoing are read."""
        read = 0 if direction == "in" else 1
        self._conn.execute(
            "INSERT OR REPLACE INTO messages (id, peer_hash, direction, content, timestamp, status, read) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (msg_id, peer_hash, direction, content, timestamp, status, read),
        )
        self._conn.commit()

    def get_messages(self, peer_hash: str, limit: int = 200) -> list[dict]:
        """Return messages for a peer ordered by timestamp ASC.

        When a limit is applied, the most recent *limit* messages are returned
        (still in ascending chronological order).
        """
        cur = self._conn.execute(
            "SELECT * FROM messages WHERE peer_hash = ? ORDER BY timestamp DESC LIMIT ?",
            (peer_hash, limit),
        )
        rows = cur.fetchall()
        rows.reverse()
        return rows

    def update_message_status(self, msg_id: str, status: str) -> None:
        """Update the status of a message by id."""
        self._conn.execute(
            "UPDATE messages SET status = ? WHERE id = ?",
            (status, msg_id),
        )
        self._conn.commit()

    def get_conversations(self) -> list[dict]:
        """Return a list of conversation summaries ordered by most recent message.

        Each dict contains: peer_hash, last_message, last_timestamp,
        last_direction, display_name, unread.
        """
        cur = self._conn.execute(
            """
            SELECT
                m.peer_hash,
                m.content   AS last_message,
                m.timestamp AS last_timestamp,
                m.direction AS last_direction,
                COALESCE(c.nickname, m.peer_hash) AS display_name,
                (SELECT COUNT(*) FROM messages u
                 WHERE u.peer_hash = m.peer_hash AND u.read = 0) AS unread
            FROM messages m
            INNER JOIN (
                SELECT peer_hash, MAX(timestamp) AS max_ts
                FROM messages
                GROUP BY peer_hash
            ) latest ON m.peer_hash = latest.peer_hash AND m.timestamp = latest.max_ts
            LEFT JOIN contacts c ON c.hash = m.peer_hash
            ORDER BY m.timestamp DESC
            """
        )
        return cur.fetchall()

    def get_unread_count(self, peer_hash: str) -> int:
        """Count unread messages from a specific peer."""
        cur = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM messages WHERE peer_hash = ? AND read = 0",
            (peer_hash,),
        )
        return cur.fetchone()["cnt"]

    def mark_read(self, peer_hash: str) -> None:
        """Mark all messages from a peer as read."""
        self._conn.execute(
            "UPDATE messages SET read = 1 WHERE peer_hash = ? AND read = 0",
            (peer_hash,),
        )
        self._conn.commit()

    def delete_old_messages(self, max_age_days: int) -> int:
        """Delete messages older than *max_age_days*. Returns count deleted."""
        cutoff = time.time() - (max_age_days * 86400)
        cur = self._conn.execute(
            "DELETE FROM messages WHERE timestamp < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cur.rowcount

    # ── Contacts ──────────────────────────────────────────────────────

    def save_contact(
        self,
        hash: str,
        nickname: str,
        display_name: str | None = None,
        last_seen: float | None = None,
        trusted: int = 0,
    ) -> None:
        """Upsert a contact. On conflict, update nickname and only overwrite
        other fields when explicitly provided (non-None)."""
        existing = self.get_contact(hash)
        if existing is None:
            self._conn.execute(
                "INSERT INTO contacts (hash, nickname, display_name, last_seen, trusted) "
                "VALUES (?, ?, ?, ?, ?)",
                (hash, nickname, display_name, last_seen, trusted),
            )
        else:
            self._conn.execute(
                "UPDATE contacts SET nickname = ?, display_name = ?, last_seen = ?, trusted = ? "
                "WHERE hash = ?",
                (
                    nickname,
                    display_name if display_name is not None else existing["display_name"],
                    last_seen if last_seen is not None else existing["last_seen"],
                    trusted if trusted != 0 else existing["trusted"],
                    hash,
                ),
            )
        self._conn.commit()

    def get_contact(self, hash: str) -> dict | None:
        """Return a contact dict or None."""
        cur = self._conn.execute("SELECT * FROM contacts WHERE hash = ?", (hash,))
        return cur.fetchone()

    def get_contacts(self) -> list[dict]:
        """Return all contacts ordered by nickname (case-insensitive)."""
        cur = self._conn.execute(
            "SELECT * FROM contacts ORDER BY nickname COLLATE NOCASE"
        )
        return cur.fetchall()

    def delete_contact(self, hash: str) -> None:
        """Delete a contact by hash."""
        self._conn.execute("DELETE FROM contacts WHERE hash = ?", (hash,))
        self._conn.commit()

    def find_contact_by_nickname(self, nickname: str) -> dict | None:
        """Case-insensitive nickname lookup. Returns dict or None."""
        cur = self._conn.execute(
            "SELECT * FROM contacts WHERE nickname COLLATE NOCASE = ?",
            (nickname,),
        )
        return cur.fetchone()

    def update_contact_last_seen(
        self, hash: str, timestamp: float, display_name: str | None = None
    ) -> None:
        """Update last_seen (and optionally display_name) for a contact."""
        if display_name is not None:
            self._conn.execute(
                "UPDATE contacts SET last_seen = ?, display_name = ? WHERE hash = ?",
                (timestamp, display_name, hash),
            )
        else:
            self._conn.execute(
                "UPDATE contacts SET last_seen = ? WHERE hash = ?",
                (timestamp, hash),
            )
        self._conn.commit()

    # ── Announces ─────────────────────────────────────────────────────

    def save_announce(
        self,
        hash: str,
        display_name: str | None,
        hops: int,
        timestamp: float,
        interface: str | None,
    ) -> None:
        """Insert an announce record."""
        self._conn.execute(
            "INSERT INTO announces (hash, display_name, hops, timestamp, interface) "
            "VALUES (?, ?, ?, ?, ?)",
            (hash, display_name, hops, timestamp, interface),
        )
        self._conn.commit()

    def get_announces(self, limit: int = 100) -> list[dict]:
        """Return announces ordered by timestamp DESC (most recent first)."""
        cur = self._conn.execute(
            "SELECT * FROM announces ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    # ── General ───────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
