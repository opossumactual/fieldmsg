"""Reticulum + LXMF core: identity, routing, send/receive."""

import logging
import os
import time
from typing import Callable

import LXMF
import RNS
from LXMF.LXMF import display_name_from_app_data

from fieldmsg.config import Config
from fieldmsg.store import Store

log = logging.getLogger(__name__)

# Map LXMF delivery states to human-readable strings.
_STATUS_MAP = {
    LXMF.LXMessage.DELIVERED: "delivered",
    LXMF.LXMessage.SENT: "sent",
    LXMF.LXMessage.FAILED: "failed",
}


class AnnounceHandler:
    """Handles incoming LXMF delivery announces from the Reticulum network."""

    def __init__(self, core: "Core"):
        self.aspect_filter = "lxmf.delivery"
        self.core = core

    def received_announce(self, destination_hash, announced_identity, app_data):
        """Called by Reticulum when an LXMF delivery announce is received."""
        try:
            hex_hash = RNS.hexrep(destination_hash, delimit=False)
            display_name = None
            if app_data is not None:
                display_name = display_name_from_app_data(app_data)

            hops = RNS.Transport.hops_to(destination_hash)
            now = time.time()

            log.info(
                "Announce from %s (%s), %d hops",
                display_name or "unknown",
                hex_hash,
                hops,
            )

            if self.core.store is not None:
                self.core.store.save_announce(
                    hex_hash, display_name, hops, now, None
                )
                # Update contact last_seen if this hash is a known contact
                contact = self.core.store.get_contact(hex_hash)
                if contact is not None:
                    self.core.store.update_contact_last_seen(
                        hex_hash, now, display_name=display_name
                    )

            if self.core.on_announce is not None:
                self.core.on_announce(hex_hash, display_name, hops)

        except Exception:
            log.exception("Error handling announce")


class Core:
    """Wraps Reticulum and LXMF into a clean interface for fieldmsg."""

    def __init__(self, config: Config):
        self.config = config
        self.reticulum: RNS.Reticulum | None = None
        self.identity: RNS.Identity | None = None
        self.lxmf_router: LXMF.LXMRouter | None = None
        self.local_destination: RNS.Destination | None = None
        self.store: Store | None = None

        # Callbacks for TUI/CLI layers
        self.on_message: Callable | None = None
        self.on_announce: Callable | None = None
        self.on_delivery_status: Callable | None = None

    # ── Helpers to resolve paths (test-overridable) ──────────────

    def _fieldmsg_dir(self) -> str:
        return getattr(self.config, "_fieldmsg_dir", self.config.fieldmsg_dir)

    def _identity_path(self) -> str:
        return getattr(self.config, "_identity_path", self.config.identity_path)

    def _storage_path(self) -> str:
        return getattr(self.config, "_storage_path", self.config.storage_path)

    def _db_path(self) -> str:
        return getattr(self.config, "_db_path", self.config.resolve_db_path())

    # ── Lifecycle ────────────────────────────────────────────────

    def setup(self) -> None:
        """Initialise Reticulum, LXMF router, identity, and store.

        Creates the identity file on first run.
        """
        fieldmsg_dir = self._fieldmsg_dir()
        os.makedirs(fieldmsg_dir, exist_ok=True)

        storage_path = self._storage_path()
        os.makedirs(storage_path, exist_ok=True)

        # Reticulum
        self.reticulum = RNS.Reticulum(
            configdir=self.config.rns_config_dir,
        )

        # Identity — load or create
        identity_path = self._identity_path()
        if os.path.isfile(identity_path):
            self.identity = RNS.Identity.from_file(identity_path)
            if self.identity is None:
                log.warning(
                    "Failed to load identity from %s, creating new one",
                    identity_path,
                )
                self.identity = RNS.Identity()
                self.identity.to_file(identity_path)
            else:
                log.info("Loaded identity from %s", identity_path)
        else:
            self.identity = RNS.Identity()
            self.identity.to_file(identity_path)
            log.info("Created new identity at %s", identity_path)

        # LXMF Router
        self.lxmf_router = LXMF.LXMRouter(
            identity=self.identity,
            storagepath=storage_path,
        )
        self.local_destination = self.lxmf_router.register_delivery_identity(
            self.identity,
            display_name=self.config.display_name,
        )
        self.lxmf_router.register_delivery_callback(self._lxmf_delivery)

        # Propagation node
        if self.config.propagation_node:
            try:
                prop_hash = bytes.fromhex(self.config.propagation_node)
                self.lxmf_router.set_outbound_propagation_node(prop_hash)
                log.info(
                    "Propagation node set to %s", self.config.propagation_node
                )
            except Exception:
                log.exception("Failed to set propagation node")

        # Announce handler
        handler = AnnounceHandler(self)
        RNS.Transport.register_announce_handler(handler)

        # SQLite Store
        db_path = self._db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.store = Store(db_path)

        log.info("Core setup complete — %s", self.get_own_hash())

        # Auto-cleanup old messages on startup
        cleaned = self.cleanup_old_messages()
        if cleaned > 0:
            log.info("Cleaned up %d old messages", cleaned)

    def cleanup_old_messages(self) -> int:
        """Delete messages older than max_age_days. Returns count deleted."""
        if self.config.max_age_days > 0 and self.store:
            return self.store.delete_old_messages(self.config.max_age_days)
        return 0

    def shutdown(self) -> None:
        """Clean shutdown of store and Reticulum."""
        if self.store is not None:
            self.store.close()
            self.store = None
        if self.reticulum is not None:
            self.reticulum = None
        log.info("Core shut down")

    # ── Public API ───────────────────────────────────────────────

    def announce(self) -> None:
        """Announce this LXMF destination on the network."""
        if self.lxmf_router is not None and self.local_destination is not None:
            self.lxmf_router.announce(self.local_destination.hash)
            log.info("Announced %s", self.get_own_hash())

    def send_message(self, dest_hash_hex: str, content: str) -> str | None:
        """Send an LXMF message to *dest_hash_hex*.

        Tries DIRECT delivery first (if we can recall the identity), falls
        back to PROPAGATED via the configured propagation node.

        Returns the message-id as a hex string, or None on failure.
        """
        try:
            dest_hash = bytes.fromhex(dest_hash_hex)
        except ValueError:
            log.error("Invalid destination hash: %s", dest_hash_hex)
            return None

        try:
            recalled_identity = RNS.Identity.recall(dest_hash)

            if recalled_identity is not None:
                # Direct delivery
                destination = RNS.Destination(
                    recalled_identity,
                    RNS.Destination.OUT,
                    RNS.Destination.SINGLE,
                    "lxmf",
                    "delivery",
                )
                lxm = LXMF.LXMessage(
                    destination,
                    self.local_destination,
                    content,
                    desired_method=LXMF.LXMessage.DIRECT,
                )
            else:
                # Propagated fallback — no known identity
                lxm = LXMF.LXMessage(
                    None,
                    self.local_destination,
                    content,
                    desired_method=LXMF.LXMessage.PROPAGATED,
                    destination_hash=dest_hash,
                )

            lxm.register_delivery_callback(self._delivery_status)
            lxm.register_failed_callback(self._delivery_status)

            msg_id = RNS.hexrep(lxm.hash, delimit=False)

            # Persist outgoing message
            if self.store is not None:
                self.store.save_message(
                    msg_id,
                    dest_hash_hex,
                    "out",
                    content,
                    time.time(),
                    status="pending",
                )

            self.lxmf_router.handle_outbound(lxm)
            log.info("Sent message %s to %s", msg_id, dest_hash_hex)
            return msg_id

        except Exception:
            log.exception("Failed to send message to %s", dest_hash_hex)
            return None

    def sync_propagation_node(self) -> None:
        """Request messages from the configured propagation node."""
        if not self.config.propagation_node:
            log.warning("No propagation node configured")
            return
        if self.lxmf_router is None or self.identity is None:
            log.warning("Core not set up, cannot sync")
            return
        try:
            self.lxmf_router.request_messages_from_propagation_node(
                self.identity
            )
            log.info("Requested messages from propagation node")
        except Exception:
            log.exception("Failed to sync propagation node")

    def get_own_hash(self) -> str:
        """Return this node's LXMF destination hash as a hex string."""
        if self.local_destination is not None:
            return RNS.hexrep(self.local_destination.hash, delimit=False)
        return ""

    # ── Internal callbacks ───────────────────────────────────────

    def _lxmf_delivery(self, lxmessage):
        """Called when an LXMF message is delivered to us."""
        try:
            msg_id = RNS.hexrep(lxmessage.hash, delimit=False)
            source_hash = RNS.hexrep(lxmessage.source_hash, delimit=False)
            content = lxmessage.content_as_string() or ""
            timestamp = lxmessage.timestamp

            log.info("Received message %s from %s", msg_id, source_hash)

            if self.store is not None:
                self.store.save_message(
                    msg_id,
                    source_hash,
                    "in",
                    content,
                    timestamp,
                    status="delivered",
                )

            if self.on_message is not None:
                self.on_message(msg_id, source_hash, content, timestamp)

        except Exception:
            log.exception("Error handling incoming message")

    def _delivery_status(self, lxmessage):
        """Called when an outbound message delivery status changes."""
        try:
            msg_id = RNS.hexrep(lxmessage.hash, delimit=False)
            status_str = _STATUS_MAP.get(lxmessage.state, "unknown")

            log.info("Delivery status for %s: %s", msg_id, status_str)

            if self.store is not None:
                self.store.update_message_status(msg_id, status_str)

            if self.on_delivery_status is not None:
                self.on_delivery_status(msg_id, status_str)

        except Exception:
            log.exception("Error handling delivery status")
