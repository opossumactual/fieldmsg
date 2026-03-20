# fieldmsg

Lightweight LXMF messenger for [Reticulum](https://reticulum.network). NomadNet stripped down to just messaging — no page hosting, no Micron parser, no node browser.

## Install

```bash
git clone https://github.com/opossumactual/fieldmsg.git
cd fieldmsg
pip install -e .
```

Requires Python 3.10+ and a running Reticulum instance (`rnsd` or standalone).

### Dependencies

Installed automatically:
- `rns` — Reticulum network stack
- `lxmf` — LXMF messaging protocol
- `textual` — TUI framework
- `tomli` — TOML parsing (Python < 3.11 only)

## Usage

```bash
fieldmsg                                    # launch TUI
fieldmsg --daemon                           # headless, no TUI
fieldmsg send <dest_hash> "message"         # send from CLI
fieldmsg --generate-config                  # print example config
fieldmsg --rnsconfig /path/to/rns/config    # use specific Reticulum config
```

On first run, fieldmsg creates `~/.fieldmsg/` with an auto-generated identity and default config.

## TUI Layout

```
+------------+-----------------+--------------------------+
| Sidebar    | Conversations   | Chat with Alice          |
|            |                 |                          |
| > Inbox    |  Alice (2)      | [10:32] > Hey            |
|   Announces|  Bob            | [10:33] You: Yeah  [ok] |
|   Contacts |                 |                          |
|            |                 +--------------------------|
|            |                 | Type a message...   [cr] |
+------------+-----------------+--------------------------+
 ^q Quit  ^i Inbox  ^a Ann  ^o Con  ^n New  ^r Announce
```

### Keybindings

| Key | Action |
|-----|--------|
| `Ctrl+Q` | Quit |
| `Ctrl+I` | Inbox |
| `Ctrl+A` | Announces |
| `Ctrl+O` | Contacts |
| `Ctrl+N` | New message (enter nickname or hash) |
| `Ctrl+R` | Announce on network |
| `/` | Search conversations |
| `Tab` | Move between sidebar, conversation list, compose |
| `Enter` | Select / send message |
| `d` | Delete conversation (inbox) or contact (contacts) |
| `e` | Edit contact nickname |
| `a` | Add to contacts (announces) |
| `c` | Clear announce list |

## Configuration

`~/.fieldmsg/config.toml`

```toml
[identity]
display_name = "Field Unit Alpha"

[lxmf]
propagation_node = ""       # destination hash of preferred propagation node
sync_interval = 300         # seconds between propagation syncs
announce_at_start = true    # announce on startup
announce_interval = 600     # periodic re-announce interval, 0 to disable

[storage]
db_path = "~/.fieldmsg/messages.db"
max_age_days = 90           # auto-cleanup old messages, 0 to disable
```

Generate a fresh config: `fieldmsg --generate-config > ~/.fieldmsg/config.toml`

## Daemon Mode

Run fieldmsg headless for unattended nodes:

```bash
fieldmsg --daemon
```

A systemd service file is included:

```bash
sudo cp systemd/fieldmsg.service /etc/systemd/system/fieldmsg@.service
sudo systemctl enable --now fieldmsg@yourusername
```

## Data Storage

All data lives in `~/.fieldmsg/`:

```
~/.fieldmsg/
  identity          # auto-generated Reticulum identity
  config.toml       # configuration
  messages.db       # SQLite database (messages, contacts, announces)
  storage/          # LXMF router state
  fieldmsg.log      # log output (TUI mode)
```

## CLI Send

Send a message without the TUI:

```bash
fieldmsg send ab01cd23ef456789ab01cd23ef456789 "hello from the field"
```

Waits up to 30 seconds for delivery confirmation, then exits.

## License

MIT
