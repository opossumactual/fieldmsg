# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

fieldmsg is a lightweight LXMF messenger built on Reticulum. It's NomadNet stripped to just messaging — no page hosting, no Micron parser, no node browser. Single process, under 500KB.

## Commands

```bash
pip install -e .                    # install in dev mode
fieldmsg                            # launch TUI
fieldmsg --daemon                   # headless mode
fieldmsg send <hash> "msg"          # CLI send
fieldmsg --generate-config          # print example config
fieldmsg --rnsconfig /path/to/rns   # use specific Reticulum config

# Tests
python3 -m pytest tests/ -v         # full suite (105 tests)
python3 -m pytest tests/test_store.py -v                    # single file
python3 -m pytest tests/test_core.py::TestSendMessage -v    # single class
python3 -m pytest tests/test_config.py::TestLoadConfig::test_load_all_sections -v  # single test
```

## Architecture

### Threading Model (critical)

Reticulum runs its own transport thread. LXMF callbacks (`_lxmf_delivery`, `_delivery_status`, `AnnounceHandler.received_announce`) fire on that thread, NOT the main/TUI thread. All UI updates from these callbacks MUST go through `self.app.call_from_thread()`. SQLite is opened with `check_same_thread=False` because both threads write to it.

`RNS.Reticulum()` registers signal handlers, which requires the main thread. That's why `Core.setup()` runs in `run_tui()` BEFORE `app.run()` takes over the event loop.

### Data Flow

```
RNS.Reticulum ←→ LXMF.LXMRouter ←→ Core (callbacks) ←→ Store (SQLite)
                                         ↕
                                    call_from_thread()
                                         ↕
                                    Textual TUI
```

### Module Roles

- **`core.py`** — Wraps RNS + LXMF. Owns identity, router, send/receive, announce handling. Exposes three callbacks: `on_message`, `on_announce`, `on_delivery_status`. The TUI or CLI sets these.
- **`store.py`** — SQLite with WAL mode. All methods return `list[dict]` or `dict | None`. Three tables: messages, contacts, announces.
- **`main.py`** — Entry point. Three modes: `run_tui` (Textual), `run_daemon` (headless loop), `run_send` (fire-and-exit). In TUI mode, suppresses RNS stdout logging to `~/.fieldmsg/fieldmsg.log`.
- **`config.py`** — Dataclass loaded from TOML. Uses `tomllib` (3.11+) with `tomli` fallback. Test-overridable paths via `cfg._fieldmsg_dir`, `cfg._identity_path`, etc.
- **`tui/app.py`** — `FieldMsgApp` with sidebar navigation, view switching, LXMF callback bridges, modal screens for new message/search. Custom "blackout" theme.
- **`tui/inbox.py`** — 3-column layout (conversations list | chat pane). Handles its own LXMF callbacks to avoid the app rebuilding the view on incoming messages. This is the most complex TUI widget.
- **`tui/chat.py`** — Standalone chat view used when opening conversations from announces/contacts/Ctrl+N. `inbox.py` has its own inline chat pane that duplicates some of this logic.

### Key Patterns

**Identity setup:** `Core.setup()` creates/loads identity from `~/.fieldmsg/identity`, then calls `RNS.Identity.remember()` to cache public keys so other local apps (NomadNet) can recall them.

**Message send order:** `handle_outbound(lxm)` FIRST (packs the message, generates `lxm.hash`), THEN read `lxm.hash` and persist to SQLite. Reversing this was a bug — `lxm.hash` is None before packing.

**Callback ownership in inbox:** `InboxView` replaces `core.on_message` and `core.on_delivery_status` with its own handlers on mount, restores them on unmount. It does NOT forward to the app's handler (which would call `_show_inbox()` and rebuild the view). The standalone `ChatView` in `chat.py` does the same save/restore pattern.

**Config test overrides:** Core resolves paths via `getattr(self.config, "_fieldmsg_dir", self.config.fieldmsg_dir)` so tests can set `cfg._fieldmsg_dir = tmp_dir` without touching real `~/.fieldmsg`.

## Data Storage

All state lives in `~/.fieldmsg/`: identity file, config.toml, messages.db (SQLite), storage/ (LXMF router state), fieldmsg.log (TUI mode logging).
