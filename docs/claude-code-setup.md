# Claude Code / Codex Setup Guide

This guide explains how to use rdm to run Claude Code or Codex CLI on a remote server that cannot directly reach API endpoints (`api.anthropic.com`, `api.openai.com`).

## The Problem

Your remote server (GPU box, cloud VPS, etc.) cannot reach AI API endpoints. This may be due to network restrictions, firewalls, or geographic blocking. Without connectivity, Claude Code and Codex CLI fail with connection timeouts or network errors.

## The Solution

Use an SSH reverse tunnel to expose your local machine's proxy (Clash, V2Ray, etc.) on the remote server. The remote tools then route their API traffic through your local proxy.

### Architecture

```
    REMOTE SERVER                        LOCAL MACHINE
+---------------------+            +---------------------+
|                     |            |                     |
|  Claude Code /      |            |  Clash / V2Ray      |
|  Codex CLI          |            |  (SOCKS5 :7897)     |
|       |             |            |       |             |
|       v             |   SSH -R   |       v             |
|  localhost:7897  ----+============+----  :7897          |
|  (reverse tunnel)   |            |       |             |
|                     |            |       v             |
|  HTTPS_PROXY=       |            |  api.anthropic.com  |
|  socks5://          |            |  api.openai.com     |
|  127.0.0.1:7897     |            |  (unrestricted)     |
+---------------------+            +---------------------+
```

**Traffic flow:**
1. Claude Code on the remote server sends HTTPS requests
2. The `HTTPS_PROXY` environment variable redirects them to `localhost:7897`
3. The SSH reverse tunnel forwards port 7897 to your local machine
4. Your local Clash/V2Ray forwards the traffic to the internet
5. The API response travels back the same path

## Prerequisites

- **Local machine:** A working proxy (Clash, Clash Verge, V2Ray, mihomo, etc.) with SOCKS5 enabled
- **Remote server:** SSH access with TCP forwarding allowed
- **rdm:** Installed on your local machine (`pip install remote-dev-manager`)

## Step 1: Verify Your Local Proxy

Confirm Clash (or your proxy of choice) is running and the SOCKS5 port is accessible:

```bash
# Default Clash SOCKS5 port is 7897
# Test it:
curl -x socks5://127.0.0.1:7897 https://api.anthropic.com -I
# Expected: HTTP 401 or similar (not a connection error)
```

If your proxy uses a different port, note it -- you will configure it in `clash_port`.

## Step 2: Create the rdm Config

Create `rdm.yaml` on your local machine:

```yaml
version: 1

defaults:
  proxy: direct
  clash_port: 7897

hosts:
  remote-gpu:
    user: ubuntu
    host: your-server-ip-or-hostname
    port: 22
    identity: ~/.ssh/your_key

reverse_proxies:
  - name: clash-for-ai
    host: remote-gpu
    local_port: 7897       # Must match your Clash SOCKS5 port
    remote_port: 7897      # Port to expose on the remote server
```

### If SSH itself needs a proxy

If you cannot SSH directly to the remote server (e.g., it is in another country and your ISP blocks it), set the proxy for the SSH connection too:

```yaml
defaults:
  proxy: clash             # SSH connection itself goes through Clash
  clash_port: 7897
```

Or set it per-service if only some connections need it:

```yaml
tunnels:
  - name: keepalive
    host: remote-gpu
    proxy: clash           # This tunnel's SSH goes through Clash
```

## Step 3: Start the Reverse Proxy

```bash
# Start just the reverse proxy:
rdm up clash-for-ai

# Or start everything and manage via TUI:
rdm tui
```

Verify it is running:

```bash
rdm status
```

Expected output:

```
Name            Type           Status   Proxy   PID    Uptime
--------------  -------------  -------  ------  -----  ------
clash-for-ai    Reverse Proxy  RUNNING  direct  12345  30s
```

## Step 4: Configure the Remote Server

SSH into your remote server and set the proxy environment variables:

```bash
ssh remote-gpu
```

Add these to `~/.bashrc` (or `~/.zshrc`):

```bash
# Proxy for AI tools (routed through SSH reverse tunnel)
export HTTPS_PROXY=socks5://127.0.0.1:7897
export HTTP_PROXY=socks5://127.0.0.1:7897
export ALL_PROXY=socks5://127.0.0.1:7897
export NO_PROXY=localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
```

Reload:

```bash
source ~/.bashrc
```

### Alternative: Session-Only Variables

If you do not want the proxy to be permanent, set it only in the current session:

```bash
export HTTPS_PROXY=socks5://127.0.0.1:7897
export HTTP_PROXY=socks5://127.0.0.1:7897
export ALL_PROXY=socks5://127.0.0.1:7897
```

## Step 5: Verify the Connection

On the remote server, test that traffic routes correctly:

```bash
# Test basic connectivity
curl -x socks5://127.0.0.1:7897 https://www.google.com -I
# Expected: HTTP/2 200

# Test Anthropic API
curl -x socks5://127.0.0.1:7897 https://api.anthropic.com/v1/messages -I
# Expected: HTTP 401 (authentication required)

# Test OpenAI API (for Codex)
curl -x socks5://127.0.0.1:7897 https://api.openai.com/v1/models -I
# Expected: HTTP 401
```

If any of these fail with "Connection refused" or timeout, see the Troubleshooting section below.

## Step 6: Launch Claude Code or Codex

```bash
# Claude Code
claude

# Codex CLI
codex
```

The tools will automatically use the `HTTPS_PROXY` / `ALL_PROXY` environment variables.

## Codex CLI Specific Notes

Codex CLI uses the OpenAI API (`api.openai.com`). The same reverse tunnel setup works. Make sure `HTTPS_PROXY` is set, as Codex respects the standard proxy environment variables.

If Codex ignores the proxy, try setting it explicitly when launching:

```bash
HTTPS_PROXY=socks5://127.0.0.1:7897 codex
```

## Troubleshooting

### "Connection refused" on port 7897

The reverse tunnel is not running, or it failed to bind.

1. Check rdm status: `rdm status` (on your local machine)
2. Check the log: `rdm log clash-for-ai`
3. Common cause: port 7897 is already in use on the remote server. Change `remote_port` to something else (e.g., 17897) and update the environment variables accordingly.

### Clash is not running

If Clash exits or restarts, the reverse tunnel stays up but traffic fails. Restart Clash on your local machine. The tunnel does not need restarting.

### SSH connection drops

rdm's reverse proxy service uses these keepalive settings:

- `ServerAliveInterval=15` -- sends a keepalive every 15 seconds
- `ServerAliveCountMax=3` -- disconnects after 3 missed keepalives (45s total)
- `ExitOnForwardFailure=yes` -- fails immediately if the port cannot be bound

If the connection drops frequently:

1. Enable auto-restart in rdm (on by default): the supervisor will reconnect with exponential backoff.
2. Check your network stability.
3. If using `proxy: clash` for the SSH connection itself, ensure Clash is stable.

### Port conflict on remote

If something else is already using port 7897 on the remote server:

```bash
# On the remote server:
ss -tlnp | grep 7897
```

If occupied, change `remote_port` in your config to an unused port:

```yaml
reverse_proxies:
  - name: clash-for-ai
    host: remote-gpu
    local_port: 7897      # Keep this as your local Clash port
    remote_port: 17897    # Use a different remote port
```

Update the environment variable on the remote:

```bash
export HTTPS_PROXY=socks5://127.0.0.1:17897
```

### SSH server blocks reverse tunneling

The SSH server must allow TCP forwarding. In `/etc/ssh/sshd_config`:

```
AllowTcpForwarding yes
```

After editing, restart sshd: `sudo systemctl restart sshd`

### Slow API responses

The added latency from the SSH tunnel is typically 1-5ms (if local and remote are on the same continent) or 50-200ms (cross-continent). This is negligible for API calls that take seconds.

If you experience significant slowness:

1. Check your local proxy's performance: `curl -x socks5://127.0.0.1:7897 -w '%{time_total}\n' -o /dev/null -s https://api.anthropic.com`
2. Ensure Clash is not routing through a slow node.
3. Consider using a VPS that is geographically closer to the API endpoint as an intermediate hop.

## Performance Tips

### SSH Keepalive

The default keepalive interval (15s) is aggressive enough for most setups. If you have an unstable connection, you can add a tunnel entry with a shorter interval by editing the SSH config on your local machine (`~/.ssh/config`).

### Reconnection

rdm's auto-restart with exponential backoff handles reconnection automatically. The worst case is a 600-second (10 minute) delay between retries after many consecutive failures. Once the connection stabilizes for 60 seconds, the backoff resets.

In the TUI, you can manually restart a failed service immediately by pressing `r`.

### Multiple AI Tools

The same reverse tunnel works for all tools that respect proxy environment variables. You can run Claude Code, Codex, and any other tool simultaneously through the same tunnel.

### Using a Different Remote Port for Each Tool

This is usually unnecessary since all tools can share one SOCKS5 proxy port. But if you need isolation:

```yaml
reverse_proxies:
  - name: claude-proxy
    host: remote-gpu
    local_port: 7897
    remote_port: 7897

  - name: codex-proxy
    host: remote-gpu
    local_port: 7897     # Same local proxy
    remote_port: 7898    # Different remote port
```

Then on the remote:

```bash
# For Claude Code:
HTTPS_PROXY=socks5://127.0.0.1:7897 claude

# For Codex:
HTTPS_PROXY=socks5://127.0.0.1:7898 codex
```

## Complete Working Example

**Local machine:** `rdm.yaml`

```yaml
version: 1

defaults:
  proxy: direct
  clash_port: 7897
  auto_restart: true

hosts:
  gpu:
    user: ubuntu
    host: 203.0.113.50
    port: 22
    identity: ~/.ssh/gpu_ed25519

tunnels:
  - name: jupyter
    host: gpu
    forwards:
      - type: local
        local_port: 8888
        remote_port: 8888

reverse_proxies:
  - name: clash-for-ai
    host: gpu
    local_port: 7897
    remote_port: 7897
```

**Local machine:** Start services

```bash
rdm up
```

**Remote server:** `~/.bashrc` additions

```bash
export HTTPS_PROXY=socks5://127.0.0.1:7897
export HTTP_PROXY=socks5://127.0.0.1:7897
export ALL_PROXY=socks5://127.0.0.1:7897
export NO_PROXY=localhost,127.0.0.1
```

**Remote server:** Launch

```bash
source ~/.bashrc
claude
```
