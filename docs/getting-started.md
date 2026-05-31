# Getting Started

This guide walks you through installing rdm, creating your first config, and managing remote services.

## Prerequisites

- **Python 3.10+** -- rdm uses modern type annotations (`X | Y`, `list[X]`) that require 3.10 or later.
- **SSH client** -- OpenSSH (comes with Windows 10+, Linux, macOS).
- **SSHFS** (optional, for mounts):
  - Linux: `apt install sshfs` or `yum install fuse-sshfs`
  - macOS: `brew install macfuse && brew install gromgit/fuse/sshfs-mac`
  - Windows: Install [WinFsp](https://winfsp.dev/) + [SSHFS-Win](https://github.com/winfsp/sshfs-win)
- **rsync** (optional, for sync): Pre-installed on most Linux/macOS systems. On Windows, install via Git for Windows (comes bundled) or MSYS2.

## Installation

### From PyPI (recommended)

```bash
pip install remote-dev-manager
```

This installs the `rdm` command globally.

### From Source

```bash
git clone https://github.com/remote-dev-manager/rdm.git
cd rdm
pip install -e .
```

### Verify Installation

```bash
rdm version
# rdm 0.1.0
```

## Creating Your First Config

Generate a starter configuration file in the current directory:

```bash
rdm init
```

This creates `rdm.yaml` with a commented template. Open it in your editor:

```yaml
version: 1

defaults:
  proxy: direct          # direct | clash | jump:<ssh-alias>
  clash_port: 7897       # local SOCKS5 proxy port
  auto_restart: true
  workspace: ""          # base dir for mounts/logs (default: config dir)
  locale: en             # en | zh

hosts:
  my-server:
    user: ubuntu
    host: 192.168.1.100
    port: 22
    identity: ~/.ssh/id_rsa
```

### Add a Host

Replace the example host with your actual server:

```yaml
hosts:
  gpu-box:
    user: ubuntu
    host: gpu.example.com
    port: 22
    identity: ~/.ssh/gpu_key
```

### Add a Tunnel

Forward a remote Jupyter notebook to your local machine:

```yaml
tunnels:
  - name: jupyter
    host: gpu-box
    forwards:
      - type: local
        local_port: 8888
        remote_port: 8888
```

### Add a Mount (optional)

Mount the remote home directory locally:

```yaml
mounts:
  - name: gpu-home
    host: gpu-box
    remote_path: /home/ubuntu
    # mount_point is auto-assigned to <workspace>/gpu-home if omitted
```

## Starting Services

### CLI

```bash
# Start all services defined in rdm.yaml
rdm up

# Start a specific service
rdm up jupyter

# Check status
rdm status
```

Output:

```
Name      Type    Status   Proxy   PID   Uptime
--------  ------  -------  ------  ----  ------
jupyter   Tunnel  RUNNING  direct  5432  45s
gpu-home  Mount   RUNNING  direct  5433  44s
```

### Stop services

```bash
rdm down          # Stop all
rdm down jupyter  # Stop one
```

## Using the TUI

The TUI is the recommended way to manage services interactively:

```bash
rdm tui
# or simply:
rdm
```

### Keyboard Shortcuts

| Key     | Action                                        |
|---------|-----------------------------------------------|
| Space   | Start or stop the selected service            |
| r       | Restart the selected service                  |
| c       | Cycle proxy mode (direct -> clash -> direct)  |
| l       | Show log panel for the selected service       |
| Escape  | Hide log panel                                |
| u       | Start all services                            |
| d       | Stop all services                             |
| a       | Toggle auto-restart on/off                    |
| q       | Quit the TUI (services keep running)          |

### Auto-Restart

When enabled (default), the supervisor polls every 2 seconds. If a service dies unexpectedly:

1. It retries with exponential backoff (60s base, doubling up to 600s).
2. After 60 seconds of stable running, the backoff resets.
3. Services you explicitly stop (via Space or `rdm down`) are not auto-restarted.

### Log Viewer

Press `l` on any service to open a live log tail in the bottom panel. The log file is stored at `<workspace>/.rdm/logs/<service-name>.log`. Press `Escape` to close the log panel.

## Next Steps

- [Configuration Reference](configuration.md) -- Full documentation of every config field.
- [Claude Code / Codex Setup](claude-code-setup.md) -- Use rdm to route AI tool traffic through a local proxy.
- [config.example.yaml](../config.example.yaml) -- Fully commented example config.
