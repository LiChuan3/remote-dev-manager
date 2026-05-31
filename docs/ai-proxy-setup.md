# AI Proxy Setup (Claude Code / Codex on remote servers)

This is the deep dive on rdm's flagship feature: making **Claude Code** and **Codex CLI** work on a remote server that can't reach the AI provider APIs directly.

---

## The problem

You SSH into a GPU box / cloud VPS / corporate dev server and want to run an AI coding tool there (so it has the GPUs, the data, and the real execution environment). But the server can't reach:

- `api.anthropic.com` (Claude Code)
- `api.openai.com` (Codex CLI)

…because it sits behind a firewall, a corporate egress filter, or the GFW. Your **laptop**, however, has a working proxy (Clash / mihomo / V2Ray) that *can* reach those endpoints.

## The solution

Reverse-tunnel your laptop's proxy port onto the server, then point the server's AI tools at it via `HTTPS_PROXY` / `ALL_PROXY`. The server's requests travel back down the SSH tunnel and exit through *your* proxy.

```
+---------------------------+        SSH Reverse Tunnel (-R)        +---------------------------+
|     Remote Server         |  <=================================>  |      Local Machine        |
|                           |                                       |                           |
|  Claude Code / Codex CLI  |                                       |  Clash / mihomo / V2Ray   |
|          |                |                                       |   listening on :7897      |
|          v                |                                       |          |                |
|  ALL_PROXY / HTTPS_PROXY  |    ssh -R 7897:127.0.0.1:7897 host    |          v                |
|  = socks5://127.0.0.1:7897| ------------------------------------> |   Internet (unrestricted) |
+---------------------------+                                       +---------------------------+
```

`socks5://127.0.0.1:7897` on the **remote** is the tunnel's bound port; it forwards to `127.0.0.1:7897` on your **local** machine, where Clash listens.

---

## Prerequisites

1. A working **local proxy** (Clash / mihomo / V2Ray) — typically SOCKS5 on `127.0.0.1:7897`. If yours uses a different port, set `defaults.clash_port` accordingly.
2. SSH access to the remote host (configured as a `host` in `rdm.yaml`).
3. The remote `sshd` must allow port forwarding (`AllowTcpForwarding yes`, the default).

---

## Option A — Desktop app (one click)

1. Add the host on the **Hosts** page and **Test** it.
2. **Enable AI Proxy** for that host. Under the hood rdm:
   1. Ensures a reverse-proxy tunnel for the host is running (`ssh -R <remote_port>:127.0.0.1:<clash_port>`).
   2. Writes `~/.rdm_proxy.sh` on the remote (optionally appending a source line to `~/.bashrc` when *persistent* is on).
   3. Verifies connectivity by curling Anthropic / OpenAI / Google endpoints **through** the tunnel.
3. The app shows the verification result and gives you ready-to-run launch commands for `claude` and `codex`.
4. **Disable AI Proxy** tears it down: stops the tunnel and removes `~/.rdm_proxy.sh` (and the `~/.bashrc` line).

The relevant sidecar endpoints (for reference):

- `POST /api/ai-proxy/setup` — `{ host, remote_port, persistent, verify, ensure_tunnel }`
- `POST /api/ai-proxy/teardown` — `{ host }`
- `GET  /api/ai-proxy/status?host=<name>&remote_port=7897`

---

## Option B — CLI (manual)

### 1. Define a reverse proxy in `rdm.yaml`

```yaml
version: 1

defaults:
  clash_port: 7897        # your local Clash SOCKS5 port

hosts:
  dev-server:
    user: ubuntu
    host: your-server.example.com
    port: 22
    identity: ~/.ssh/id_rsa

reverse_proxies:
  - name: clash-for-ai
    host: dev-server
    local_port: 7897      # local Clash port to expose
    remote_port: 7897     # port to bind on the remote
```

### 2. Start the reverse tunnel

```bash
rdm up clash-for-ai
# or interactively: rdm tui  (then press Space on the service)
```

This runs, roughly:

```bash
ssh -N -R 7897:127.0.0.1:7897 \
    -o GatewayPorts=no \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes -o BatchMode=yes \
    -o StrictHostKeyChecking=accept-new \
    ubuntu@your-server.example.com
```

`GatewayPorts=no` keeps the forwarded port bound to the remote's loopback only.

### 3. Set the proxy env on the remote

rdm's one-click path writes this for you; doing it manually, create `~/.rdm_proxy.sh` on the server:

```bash
# ~/.rdm_proxy.sh
export ALL_PROXY=socks5://127.0.0.1:7897
export HTTPS_PROXY=socks5://127.0.0.1:7897
export HTTP_PROXY=socks5://127.0.0.1:7897
export NO_PROXY=localhost,127.0.0.1,::1
```

Then `source ~/.rdm_proxy.sh` in any shell that runs `claude` / `codex`.

---

## The `~/.rdm_proxy.sh` env file

rdm writes exactly this on the remote (with `<port>` = `remote_port`):

```bash
# Added by remote-dev-manager — route AI tool traffic through local Clash via SSH reverse tunnel
export ALL_PROXY=socks5://127.0.0.1:<port>
export HTTPS_PROXY=socks5://127.0.0.1:<port>
export HTTP_PROXY=socks5://127.0.0.1:<port>
export NO_PROXY=localhost,127.0.0.1,::1
```

`NO_PROXY` keeps loopback traffic off the tunnel.

### Persistence (`~/.bashrc`)

With *persistent* enabled, rdm appends (at most once, guarded by a `grep`) this line to `~/.bashrc`:

```bash
[ -f ~/.rdm_proxy.sh ] && source ~/.rdm_proxy.sh
```

so every new login shell on the remote picks up the proxy automatically. Teardown removes both the env file and this line.

---

## Verifying connectivity

rdm verifies by curling the AI endpoints **through the SOCKS proxy** on the remote (note `socks5h://`, so DNS resolves remotely through the tunnel):

```bash
# run on the remote
curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
    -x socks5h://127.0.0.1:7897 https://api.anthropic.com/v1/messages
```

A reachable-but-unauthorized response (e.g. `401`, `403`, `404`, `405`, `200`, `429`) counts as **success** — it means the request reached the endpoint. A code of `000` (or empty) means the proxy/tunnel isn't working. rdm checks Anthropic, OpenAI, and Google, and treats the proxy as OK if **Anthropic or OpenAI** is reachable.

---

## Launching Claude Code / Codex on the remote

With the tunnel up and the env file in place, launch over an interactive SSH session (PTY via `-t`), sourcing the env first. rdm generates these for you:

```bash
# Claude Code
ssh -t user@host 'source ~/.rdm_proxy.sh; claude'

# Codex
ssh -t user@host 'source ~/.rdm_proxy.sh; codex'
```

You can add a `cd` to a working directory in the same remote command if you like:

```bash
ssh -t user@host 'cd /home/ubuntu/project; source ~/.rdm_proxy.sh; claude'
```

### Codex-specific notes

- Codex honors the same `ALL_PROXY` / `HTTPS_PROXY` / `HTTP_PROXY` variables, so the shared `~/.rdm_proxy.sh` covers it.
- If a tool uses a strict allowlist or its own proxy setting, make sure it inherits the environment (i.e. you actually `source ~/.rdm_proxy.sh` in the shell that launches it). The persistent `~/.bashrc` hook is the most reliable way to guarantee this for login shells.

---

## Troubleshooting

**`AllowTcpForwarding` disabled.**
If the reverse tunnel binds but traffic never flows, the remote `sshd` may forbid forwarding. Check `/etc/ssh/sshd_config` for `AllowTcpForwarding yes` (and `PermitOpen` not over-restricting), then restart `sshd`.

**Port conflict on the remote.**
If `remote_port` (default 7897) is already bound on the server, the reverse tunnel fails fast (`ExitOnForwardFailure=yes`). Pick a different `remote_port` and update the env file accordingly, or free the port.

**Clash isn't running locally.**
Verification returns `000` for every endpoint. Confirm your local proxy is up and listening on `clash_port` (default 7897): `curl -x socks5h://127.0.0.1:7897 https://api.anthropic.com -I` from your **laptop**.

**Wrong local port.**
If Clash listens on something other than 7897, set `defaults.clash_port` (and `reverse_proxies[].local_port`) to match. The remote-side `remote_port` is independent and only needs to be free on the server.

**SSH drops / tunnel dies.**
The tunnel uses `ServerAliveInterval=15` + `ServerAliveCountMax=3` keepalives, and rdm's supervisor auto-restarts it with exponential backoff. Check the service log (`rdm log <name>` or the GUI/TUI log viewer) if it keeps failing — common causes are network flaps or the remote killing idle forwards.

**`401` is fine.**
A `401`/`403` from `api.anthropic.com` during verification is **expected** (no API key on the probe) and means connectivity works. Only `000`/empty indicates a real failure.
