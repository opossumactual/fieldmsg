"""Tests for the SQLite storage layer."""

import os
import tempfile
import time

import pytest

from fieldmsg.store import Store


@pytest.fixture
def store():
    """Create a temporary Store, yield it, then close and remove."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = Store(path)
    yield s
    s.close()
    # Remove the main db file and any WAL/SHM files
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except FileNotFoundError:
            pass


# ---------- Messages ----------


class TestMessages:
    def test_save_and_get_messages(self, store):
        now = time.time()
        store.save_message("m1", "peer_a", "in", "hello", now, "pending")
        store.save_message("m2", "peer_a", "out", "hi back", now + 1, "sent")
        msgs = store.get_messages("peer_a")
        assert len(msgs) == 2
        assert msgs[0]["id"] == "m1"
        assert msgs[1]["id"] == "m2"
        # incoming should be unread, outgoing should be read
        assert msgs[0]["read"] == 0
        assert msgs[1]["read"] == 1

    def test_get_messages_ordered_by_timestamp(self, store):
        now = time.time()
        store.save_message("m3", "peer_b", "in", "third", now + 2, "pending")
        store.save_message("m1", "peer_b", "in", "first", now, "pending")
        store.save_message("m2", "peer_b", "in", "second", now + 1, "pending")
        msgs = store.get_messages("peer_b")
        assert [m["id"] for m in msgs] == ["m1", "m2", "m3"]

    def test_get_messages_limit(self, store):
        now = time.time()
        for i in range(10):
            store.save_message(f"m{i}", "peer_c", "in", f"msg {i}", now + i, "pending")
        msgs = store.get_messages("peer_c", limit=3)
        assert len(msgs) == 3
        # Should return the 3 most recent, still in ASC order
        assert [m["id"] for m in msgs] == ["m7", "m8", "m9"]

    def test_save_message_replace(self, store):
        now = time.time()
        store.save_message("m1", "peer_a", "out", "original", now, "pending")
        store.save_message("m1", "peer_a", "out", "replaced", now, "sent")
        msgs = store.get_messages("peer_a")
        assert len(msgs) == 1
        assert msgs[0]["content"] == "replaced"
        assert msgs[0]["status"] == "sent"

    def test_update_message_status(self, store):
        now = time.time()
        store.save_message("m1", "peer_a", "out", "hello", now, "pending")
        store.update_message_status("m1", "delivered")
        msgs = store.get_messages("peer_a")
        assert msgs[0]["status"] == "delivered"

    def test_get_conversations(self, store):
        now = time.time()
        # Two peers, peer_b has a more recent message
        store.save_message("m1", "peer_a", "in", "hello a", now, "pending")
        store.save_message("m2", "peer_b", "out", "hello b", now + 1, "sent")
        store.save_message("m3", "peer_a", "in", "hello again a", now + 2, "pending")

        convos = store.get_conversations()
        assert len(convos) == 2
        # Most recent first: peer_a (now+2), then peer_b (now+1)
        assert convos[0]["peer_hash"] == "peer_a"
        assert convos[0]["last_message"] == "hello again a"
        assert convos[0]["last_direction"] == "in"
        assert convos[1]["peer_hash"] == "peer_b"
        assert convos[1]["last_message"] == "hello b"

    def test_get_conversations_display_name_from_contact(self, store):
        now = time.time()
        store.save_message("m1", "peer_a", "in", "hi", now, "pending")
        store.save_contact("peer_a", "Alice")
        convos = store.get_conversations()
        assert convos[0]["display_name"] == "Alice"

    def test_get_conversations_display_name_fallback(self, store):
        now = time.time()
        store.save_message("m1", "peer_x", "in", "hi", now, "pending")
        convos = store.get_conversations()
        # No contact record; display_name should fall back to peer_hash
        assert convos[0]["display_name"] == "peer_x"

    def test_unread_count(self, store):
        now = time.time()
        store.save_message("m1", "peer_a", "in", "one", now, "pending")
        store.save_message("m2", "peer_a", "in", "two", now + 1, "pending")
        store.save_message("m3", "peer_a", "out", "reply", now + 2, "sent")
        assert store.get_unread_count("peer_a") == 2

    def test_unread_count_in_conversations(self, store):
        now = time.time()
        store.save_message("m1", "peer_a", "in", "one", now, "pending")
        store.save_message("m2", "peer_a", "in", "two", now + 1, "pending")
        convos = store.get_conversations()
        assert convos[0]["unread"] == 2

    def test_mark_read(self, store):
        now = time.time()
        store.save_message("m1", "peer_a", "in", "one", now, "pending")
        store.save_message("m2", "peer_a", "in", "two", now + 1, "pending")
        assert store.get_unread_count("peer_a") == 2
        store.mark_read("peer_a")
        assert store.get_unread_count("peer_a") == 0

    def test_delete_old_messages(self, store):
        now = time.time()
        old = now - (31 * 86400)  # 31 days ago
        store.save_message("m_old", "peer_a", "in", "old msg", old, "pending")
        store.save_message("m_new", "peer_a", "in", "new msg", now, "pending")
        deleted = store.delete_old_messages(30)
        assert deleted == 1
        msgs = store.get_messages("peer_a")
        assert len(msgs) == 1
        assert msgs[0]["id"] == "m_new"


# ---------- Contacts ----------


class TestContacts:
    def test_save_and_get_contact(self, store):
        store.save_contact("hash_a", "Alice", display_name="Alice A", last_seen=1000.0, trusted=1)
        c = store.get_contact("hash_a")
        assert c is not None
        assert c["nickname"] == "Alice"
        assert c["display_name"] == "Alice A"
        assert c["last_seen"] == 1000.0
        assert c["trusted"] == 1

    def test_save_contact_upsert_preserves_fields(self, store):
        store.save_contact("hash_a", "Alice", display_name="Alice A", last_seen=1000.0, trusted=1)
        # Update just the nickname; other fields should be preserved
        store.save_contact("hash_a", "Alicia")
        c = store.get_contact("hash_a")
        assert c["nickname"] == "Alicia"
        assert c["display_name"] == "Alice A"
        assert c["last_seen"] == 1000.0
        assert c["trusted"] == 1

    def test_get_contact_missing(self, store):
        assert store.get_contact("nonexistent") is None

    def test_get_contacts_ordered(self, store):
        store.save_contact("h2", "Bob")
        store.save_contact("h1", "Alice")
        store.save_contact("h3", "Charlie")
        contacts = store.get_contacts()
        assert [c["nickname"] for c in contacts] == ["Alice", "Bob", "Charlie"]

    def test_delete_contact(self, store):
        store.save_contact("hash_a", "Alice")
        store.delete_contact("hash_a")
        assert store.get_contact("hash_a") is None

    def test_find_contact_by_nickname(self, store):
        store.save_contact("hash_a", "Alice")
        result = store.find_contact_by_nickname("alice")  # case-insensitive
        assert result is not None
        assert result["hash"] == "hash_a"

    def test_find_contact_by_nickname_missing(self, store):
        assert store.find_contact_by_nickname("nobody") is None

    def test_update_contact_last_seen(self, store):
        store.save_contact("hash_a", "Alice")
        store.update_contact_last_seen("hash_a", 2000.0, display_name="Alice Updated")
        c = store.get_contact("hash_a")
        assert c["last_seen"] == 2000.0
        assert c["display_name"] == "Alice Updated"

    def test_update_contact_last_seen_no_display_name(self, store):
        store.save_contact("hash_a", "Alice", display_name="Original")
        store.update_contact_last_seen("hash_a", 3000.0)
        c = store.get_contact("hash_a")
        assert c["last_seen"] == 3000.0
        assert c["display_name"] == "Original"  # unchanged


# ---------- Announces ----------


class TestAnnounces:
    def test_save_and_get_announces(self, store):
        now = time.time()
        store.save_announce("hash_a", "Alice", 2, now, "lo0")
        store.save_announce("hash_b", "Bob", 1, now + 1, "wlan0")
        announces = store.get_announces()
        # Most recent first
        assert len(announces) == 2
        assert announces[0]["hash"] == "hash_b"
        assert announces[1]["hash"] == "hash_a"

    def test_get_announces_limit(self, store):
        now = time.time()
        for i in range(10):
            store.save_announce(f"hash_{i}", f"Node {i}", i, now + i, "lo0")
        announces = store.get_announces(limit=3)
        assert len(announces) == 3
        # Most recent first
        assert announces[0]["hash"] == "hash_9"

    def test_announce_fields(self, store):
        now = time.time()
        store.save_announce("hash_a", "Alice", 3, now, "wlan0")
        a = store.get_announces(limit=1)[0]
        assert a["hash"] == "hash_a"
        assert a["display_name"] == "Alice"
        assert a["hops"] == 3
        assert a["timestamp"] == now
        assert a["interface"] == "wlan0"
