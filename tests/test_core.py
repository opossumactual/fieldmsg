"""Tests for the Reticulum + LXMF core module.

RNS and LXMF are fully mocked since we cannot start a real Reticulum
instance inside the test runner.
"""

import os
import tempfile
import time
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

from fieldmsg.config import Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_dir: str) -> Config:
    """Return a Config whose paths all point into *tmp_dir*."""
    cfg = Config(display_name="TestNode")
    cfg._fieldmsg_dir = tmp_dir
    cfg._storage_path = os.path.join(tmp_dir, "storage")
    cfg._identity_path = os.path.join(tmp_dir, "identity")
    cfg._db_path = os.path.join(tmp_dir, "messages.db")
    return cfg


def _fake_hexrep(data, delimit=False):
    """Deterministic hex representation for tests."""
    if isinstance(data, bytes):
        return data.hex()
    return str(data)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir():
    """Create a temporary directory for each test."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def mock_rns():
    """Patch the RNS module used by core."""
    with patch.dict("sys.modules", {}):
        with patch("fieldmsg.core.RNS") as rns:
            # RNS.Reticulum() returns a mock instance
            rns.Reticulum.return_value = MagicMock()

            # Identity
            mock_identity = MagicMock()
            mock_identity.hexhash = "ab" * 16
            rns.Identity.return_value = mock_identity
            rns.Identity.from_file.return_value = mock_identity
            rns.Identity.recall.return_value = None

            # hexrep
            rns.hexrep.side_effect = _fake_hexrep

            # Destination
            mock_dest = MagicMock()
            mock_dest.hash = b"\xab" * 16
            rns.Destination.return_value = mock_dest
            rns.Destination.OUT = 0x01
            rns.Destination.SINGLE = 0x00

            # Transport
            rns.Transport.hops_to.return_value = 2
            rns.Transport.register_announce_handler = MagicMock()

            yield rns


@pytest.fixture
def mock_lxmf():
    """Patch the LXMF module used by core."""
    with patch("fieldmsg.core.LXMF") as lxmf:
        mock_router = MagicMock()
        mock_dest = MagicMock()
        mock_dest.hash = b"\xcd" * 16

        mock_router.register_delivery_identity.return_value = mock_dest
        lxmf.LXMRouter.return_value = mock_router

        # LXMessage class-level constants
        lxmf.LXMessage.DIRECT = 0x02
        lxmf.LXMessage.PROPAGATED = 0x03
        lxmf.LXMessage.DELIVERED = 0x08
        lxmf.LXMessage.SENT = 0x04
        lxmf.LXMessage.FAILED = 0xFF

        # LXMessage instances
        mock_lxm = MagicMock()
        mock_lxm.hash = b"\xef" * 16
        mock_lxm.source_hash = b"\xab" * 16
        mock_lxm.content_as_string.return_value = "hello"
        mock_lxm.timestamp = time.time()
        mock_lxm.state = 0x08  # DELIVERED
        lxmf.LXMessage.return_value = mock_lxm

        yield lxmf


@pytest.fixture
def mock_display_name():
    """Patch display_name_from_app_data."""
    with patch("fieldmsg.core.display_name_from_app_data") as fn:
        fn.return_value = "TestPeer"
        yield fn


# ---------------------------------------------------------------------------
# Tests: Setup & Identity
# ---------------------------------------------------------------------------

class TestCoreSetup:
    """Core.setup initialises Reticulum, identity, LXMF router, and store."""

    def test_creates_new_identity_when_no_file(
        self, tmp_dir, mock_rns, mock_lxmf, mock_display_name
    ):
        from fieldmsg.core import Core

        cfg = _make_config(tmp_dir)
        core = Core(cfg)
        core.setup()

        # Identity.from_file should NOT be called (no file exists)
        mock_rns.Identity.from_file.assert_not_called()
        # A new Identity should be created
        mock_rns.Identity.assert_called()
        # to_file should be called to persist the new identity
        core.identity.to_file.assert_called_once_with(cfg._identity_path)

        core.shutdown()

    def test_loads_existing_identity_from_file(
        self, tmp_dir, mock_rns, mock_lxmf, mock_display_name
    ):
        from fieldmsg.core import Core

        cfg = _make_config(tmp_dir)
        # Create a fake identity file so the path exists
        with open(cfg._identity_path, "wb") as f:
            f.write(b"fake-identity-data")

        core = Core(cfg)
        core.setup()

        mock_rns.Identity.from_file.assert_called_once_with(cfg._identity_path)
        # identity should be the one returned by from_file
        assert core.identity == mock_rns.Identity.from_file.return_value

        core.shutdown()

    def test_creates_new_identity_when_from_file_returns_none(
        self, tmp_dir, mock_rns, mock_lxmf, mock_display_name
    ):
        from fieldmsg.core import Core

        cfg = _make_config(tmp_dir)
        # File exists but from_file returns None (corrupt)
        with open(cfg._identity_path, "wb") as f:
            f.write(b"corrupt")
        mock_rns.Identity.from_file.return_value = None

        core = Core(cfg)
        core.setup()

        # Should fall through to creating a new identity
        mock_rns.Identity.assert_called()

        core.shutdown()

    def test_registers_delivery_callback(
        self, tmp_dir, mock_rns, mock_lxmf, mock_display_name
    ):
        from fieldmsg.core import Core

        cfg = _make_config(tmp_dir)
        core = Core(cfg)
        core.setup()

        mock_lxmf.LXMRouter.return_value.register_delivery_callback.assert_called_once()

        core.shutdown()

    def test_registers_announce_handler(
        self, tmp_dir, mock_rns, mock_lxmf, mock_display_name
    ):
        from fieldmsg.core import Core

        cfg = _make_config(tmp_dir)
        core = Core(cfg)
        core.setup()

        mock_rns.Transport.register_announce_handler.assert_called_once()

        core.shutdown()

    def test_store_created(
        self, tmp_dir, mock_rns, mock_lxmf, mock_display_name
    ):
        from fieldmsg.core import Core

        cfg = _make_config(tmp_dir)
        core = Core(cfg)
        core.setup()

        assert core.store is not None

        core.shutdown()

    def test_creates_directories(
        self, tmp_dir, mock_rns, mock_lxmf, mock_display_name
    ):
        from fieldmsg.core import Core

        # Use a subdirectory that doesn't exist yet
        sub = os.path.join(tmp_dir, "sub", "fieldmsg")
        cfg = _make_config(sub)
        core = Core(cfg)
        core.setup()

        assert os.path.isdir(sub)
        assert os.path.isdir(cfg._storage_path)

        core.shutdown()

    def test_propagation_node_set_when_configured(
        self, tmp_dir, mock_rns, mock_lxmf, mock_display_name
    ):
        from fieldmsg.core import Core

        cfg = _make_config(tmp_dir)
        cfg.propagation_node = "ab" * 16
        core = Core(cfg)
        core.setup()

        mock_lxmf.LXMRouter.return_value.set_outbound_propagation_node.assert_called_once()

        core.shutdown()


# ---------------------------------------------------------------------------
# Tests: Send Message
# ---------------------------------------------------------------------------

class TestSendMessage:
    """Core.send_message creates an LXMessage and hands it to the router."""

    @pytest.fixture(autouse=True)
    def _setup_core(self, tmp_dir, mock_rns, mock_lxmf, mock_display_name):
        """Set up a Core instance for each send-message test."""
        from fieldmsg.core import Core

        self.cfg = _make_config(tmp_dir)
        self.core = Core(self.cfg)
        self.core.setup()
        self.mock_rns = mock_rns
        self.mock_lxmf = mock_lxmf

        yield

        self.core.shutdown()

    def test_send_direct_when_identity_recalled(self):
        """When Identity.recall returns an identity, use DIRECT method."""
        recalled = MagicMock()
        self.mock_rns.Identity.recall.return_value = recalled

        msg_id = self.core.send_message("aa" * 16, "hello there")

        assert msg_id is not None
        # LXMessage should be created with DIRECT method
        call_kwargs = self.mock_lxmf.LXMessage.call_args
        assert call_kwargs.kwargs.get("desired_method") == 0x02  # DIRECT
        # Router's handle_outbound should be called
        self.mock_lxmf.LXMRouter.return_value.handle_outbound.assert_called_once()

    def test_send_propagated_when_identity_unknown(self):
        """When Identity.recall returns None, use PROPAGATED method."""
        self.mock_rns.Identity.recall.return_value = None

        msg_id = self.core.send_message("bb" * 16, "hello via prop")

        assert msg_id is not None
        call_kwargs = self.mock_lxmf.LXMessage.call_args
        assert call_kwargs.kwargs.get("desired_method") == 0x03  # PROPAGATED
        assert call_kwargs.kwargs.get("destination_hash") == bytes.fromhex("bb" * 16)

    def test_send_returns_msg_id(self):
        """send_message returns a hex message ID."""
        msg_id = self.core.send_message("cc" * 16, "test")
        assert msg_id is not None
        assert len(msg_id) > 0

    def test_send_saves_to_store(self):
        """Outgoing message is persisted in the store."""
        msg_id = self.core.send_message("dd" * 16, "persist me")
        assert msg_id is not None

        msgs = self.core.store.get_messages("dd" * 16)
        assert len(msgs) == 1
        assert msgs[0]["direction"] == "out"
        assert msgs[0]["content"] == "persist me"
        assert msgs[0]["status"] == "pending"

    def test_send_invalid_hex_returns_none(self):
        """An invalid hex hash returns None."""
        msg_id = self.core.send_message("not-hex", "fail")
        assert msg_id is None

    def test_send_registers_callbacks(self):
        """Delivery and failed callbacks are registered on the LXMessage."""
        self.core.send_message("ee" * 16, "callbacks")
        lxm = self.mock_lxmf.LXMessage.return_value
        lxm.register_delivery_callback.assert_called_once()
        lxm.register_failed_callback.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: Receive Message (delivery callback)
# ---------------------------------------------------------------------------

class TestReceiveMessage:
    """Core._lxmf_delivery processes incoming messages correctly."""

    @pytest.fixture(autouse=True)
    def _setup_core(self, tmp_dir, mock_rns, mock_lxmf, mock_display_name):
        from fieldmsg.core import Core

        self.cfg = _make_config(tmp_dir)
        self.core = Core(self.cfg)
        self.core.setup()
        self.mock_rns = mock_rns

        yield

        self.core.shutdown()

    def test_incoming_message_saved_to_store(self):
        """An incoming LXMF message is saved to the store."""
        lxm = MagicMock()
        lxm.hash = b"\x11" * 16
        lxm.source_hash = b"\x22" * 16
        lxm.content_as_string.return_value = "incoming msg"
        lxm.timestamp = time.time()

        self.core._lxmf_delivery(lxm)

        source_hex = _fake_hexrep(b"\x22" * 16)
        msgs = self.core.store.get_messages(source_hex)
        assert len(msgs) == 1
        assert msgs[0]["content"] == "incoming msg"
        assert msgs[0]["direction"] == "in"
        assert msgs[0]["status"] == "delivered"

    def test_incoming_message_fires_callback(self):
        """The on_message callback is invoked for incoming messages."""
        callback = MagicMock()
        self.core.on_message = callback

        lxm = MagicMock()
        lxm.hash = b"\x33" * 16
        lxm.source_hash = b"\x44" * 16
        lxm.content_as_string.return_value = "callback test"
        lxm.timestamp = 1234567890.0

        self.core._lxmf_delivery(lxm)

        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[2] == "callback test"
        assert args[3] == 1234567890.0

    def test_incoming_message_none_content(self):
        """If content_as_string returns None, store empty string."""
        lxm = MagicMock()
        lxm.hash = b"\x55" * 16
        lxm.source_hash = b"\x66" * 16
        lxm.content_as_string.return_value = None
        lxm.timestamp = time.time()

        self.core._lxmf_delivery(lxm)

        source_hex = _fake_hexrep(b"\x66" * 16)
        msgs = self.core.store.get_messages(source_hex)
        assert len(msgs) == 1
        assert msgs[0]["content"] == ""

    def test_callback_exception_does_not_crash(self):
        """A failing on_message callback must not crash the core."""
        self.core.on_message = MagicMock(side_effect=RuntimeError("boom"))

        lxm = MagicMock()
        lxm.hash = b"\x77" * 16
        lxm.source_hash = b"\x88" * 16
        lxm.content_as_string.return_value = "oops"
        lxm.timestamp = time.time()

        # Should not raise
        self.core._lxmf_delivery(lxm)


# ---------------------------------------------------------------------------
# Tests: Delivery Status
# ---------------------------------------------------------------------------

class TestDeliveryStatus:
    """Core._delivery_status maps LXMF states to status strings."""

    @pytest.fixture(autouse=True)
    def _setup_core(self, tmp_dir, mock_rns, mock_lxmf, mock_display_name):
        from fieldmsg.core import Core

        self.cfg = _make_config(tmp_dir)
        self.core = Core(self.cfg)
        self.core.setup()
        self.mock_lxmf = mock_lxmf

        yield

        self.core.shutdown()

    def test_delivered_status(self):
        lxm = MagicMock()
        lxm.hash = b"\xaa" * 16
        lxm.state = 0x08  # DELIVERED

        callback = MagicMock()
        self.core.on_delivery_status = callback

        self.core._delivery_status(lxm)

        callback.assert_called_once()
        assert callback.call_args[0][1] == "delivered"

    def test_sent_status(self):
        lxm = MagicMock()
        lxm.hash = b"\xbb" * 16
        lxm.state = 0x04  # SENT

        callback = MagicMock()
        self.core.on_delivery_status = callback

        self.core._delivery_status(lxm)

        assert callback.call_args[0][1] == "sent"

    def test_failed_status(self):
        lxm = MagicMock()
        lxm.hash = b"\xcc" * 16
        lxm.state = 0xFF  # FAILED

        callback = MagicMock()
        self.core.on_delivery_status = callback

        self.core._delivery_status(lxm)

        assert callback.call_args[0][1] == "failed"

    def test_updates_store_status(self):
        # Save an outgoing message first
        msg_hex = _fake_hexrep(b"\xdd" * 16)
        self.core.store.save_message(
            msg_hex, "peer", "out", "test", time.time(), "pending"
        )

        lxm = MagicMock()
        lxm.hash = b"\xdd" * 16
        lxm.state = 0x08  # DELIVERED

        self.core._delivery_status(lxm)

        msgs = self.core.store.get_messages("peer")
        assert msgs[0]["status"] == "delivered"


# ---------------------------------------------------------------------------
# Tests: Announce Handler
# ---------------------------------------------------------------------------

class TestAnnounceHandler:
    """AnnounceHandler processes incoming announces."""

    @pytest.fixture(autouse=True)
    def _setup_core(
        self, tmp_dir, mock_rns, mock_lxmf, mock_display_name
    ):
        from fieldmsg.core import Core

        self.cfg = _make_config(tmp_dir)
        self.core = Core(self.cfg)
        self.core.setup()
        self.mock_rns = mock_rns
        self.mock_display_name = mock_display_name

        yield

        self.core.shutdown()

    def test_announce_saved_to_store(self):
        from fieldmsg.core import AnnounceHandler

        handler = AnnounceHandler(self.core)
        handler.received_announce(b"\x99" * 16, MagicMock(), b"app-data")

        announces = self.core.store.get_announces()
        assert len(announces) == 1
        assert announces[0]["display_name"] == "TestPeer"
        assert announces[0]["hops"] == 2

    def test_announce_fires_callback(self):
        from fieldmsg.core import AnnounceHandler

        callback = MagicMock()
        self.core.on_announce = callback

        handler = AnnounceHandler(self.core)
        handler.received_announce(b"\xaa" * 16, MagicMock(), b"data")

        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[1] == "TestPeer"
        assert args[2] == 2

    def test_announce_updates_known_contact(self):
        from fieldmsg.core import AnnounceHandler

        hash_hex = _fake_hexrep(b"\xbb" * 16)
        self.core.store.save_contact(hash_hex, "OldName")

        handler = AnnounceHandler(self.core)
        handler.received_announce(b"\xbb" * 16, MagicMock(), b"data")

        contact = self.core.store.get_contact(hash_hex)
        assert contact["last_seen"] is not None
        assert contact["display_name"] == "TestPeer"

    def test_announce_with_none_app_data(self):
        from fieldmsg.core import AnnounceHandler

        handler = AnnounceHandler(self.core)
        # app_data=None should not crash
        handler.received_announce(b"\xcc" * 16, MagicMock(), None)

        announces = self.core.store.get_announces()
        assert len(announces) == 1
        assert announces[0]["display_name"] is None

    def test_announce_exception_does_not_crash(self):
        from fieldmsg.core import AnnounceHandler

        self.core.on_announce = MagicMock(side_effect=RuntimeError("boom"))

        handler = AnnounceHandler(self.core)
        # Should not raise
        handler.received_announce(b"\xdd" * 16, MagicMock(), b"data")


# ---------------------------------------------------------------------------
# Tests: Other Core methods
# ---------------------------------------------------------------------------

class TestCoreMethods:
    """Miscellaneous Core method tests."""

    @pytest.fixture(autouse=True)
    def _setup_core(self, tmp_dir, mock_rns, mock_lxmf, mock_display_name):
        from fieldmsg.core import Core

        self.cfg = _make_config(tmp_dir)
        self.core = Core(self.cfg)
        self.core.setup()
        self.mock_rns = mock_rns
        self.mock_lxmf = mock_lxmf

        yield

        self.core.shutdown()

    def test_get_own_hash(self):
        h = self.core.get_own_hash()
        assert isinstance(h, str)
        assert len(h) > 0

    def test_announce_calls_router(self):
        self.core.announce()
        self.mock_lxmf.LXMRouter.return_value.announce.assert_called_once()

    def test_sync_no_propagation_node(self):
        """sync_propagation_node with no configured node just logs a warning."""
        self.cfg.propagation_node = ""
        # Should not raise
        self.core.sync_propagation_node()

    def test_sync_with_propagation_node(self):
        self.cfg.propagation_node = "ff" * 16
        self.core.sync_propagation_node()
        self.mock_lxmf.LXMRouter.return_value.request_messages_from_propagation_node.assert_called_once()

    def test_shutdown_closes_store(self):
        store = self.core.store
        self.core.shutdown()
        assert self.core.store is None
        # Verify the store was closed (connection no longer usable)

    def test_get_own_hash_before_setup(self):
        from fieldmsg.core import Core

        core = Core(self.cfg)
        assert core.get_own_hash() == ""
