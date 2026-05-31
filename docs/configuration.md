# Configuration Reference

rdm is configured via a single YAML file. This document describes every field.

> **One file, three front-ends.** The desktop GUI, the `rdm` CLI, and the TUI all read and write **this same config file**. When you add or edit a host/tunnel/mount/reverse-proxy/mirror in the desktop app, the FastAPI sidecar persists the change through `rdm`'s `config_writer` (which preserves your YAML), then reloads. Hand-editing the file and editing it through the GUI are equivalent and interchangeable.

## Config File Locations

rdm searches for a config file in this order:

1. **`$RDM_CONFIG`** environment variable (explicit path)
2. **`./rdm.yaml`** in the current working directory
3. **Platform user config directory:**
   - Linux/macOS: `~/.config/rdm/config.yaml` (respects `$XDG_CONFIG_HOME`)
   - Windows: `%APPDATA%\rdm\config.yaml`

You can also pass a path explicitly:

```bash
rdm -c /path/to/my-config.yaml tui
```

## Top-Level Structure

```yaml
version: 1                # Config schema version (currently always 1)
defaults: { ... }         # Global defaults
hosts: { ... }            # SSH host definitions
tunnels: [ ... ]          # SSH tunnel services
mounts: [ ... ]           # SSHFS mount services
reverse_proxies: [ ... ]  # Reverse proxy tunnel services
syncs: [ ... ]            # File sync definitions
mirrors: [ ... ]          # Code mirror definitions
```

All sections except `version` are optional. An empty config is valid but defines no services.

---

## `defaults`

Global settings that apply to all services unless overridden per-entry.

```yaml
defaults:
  proxy: direct
  clash_port: 7897
  auto_restart: true
  workspace: ""
  locale: en
```

| Field          | Type   | Default    | Description |
|----------------|--------|------------|-------------|
| `proxy`        | string | `"direct"` | Default proxy mode for SSH connections. Values: `direct` (no proxy), `clash` (route through local SOCKS5 proxy), `jump:<alias>` (use another host as SSH jump host). |
| `clash_port`   | int    | `7897`     | Local SOCKS5 proxy port used when `proxy` is `"clash"`. This is the port Clash/V2Ray/mihomo listens on locally. |
| `auto_restart` | bool   | `true`     | Automatically restart services that exit unexpectedly. Uses exponential backoff (base 2s, capped at 300s). |
| `workspace`    | string | `""`       | Base directory for runtime files (`.rdm/` state and logs, mount points). Empty string means the parent directory of the config file. Supports `~` and `$ENV_VAR` expansion. |
| `locale`       | string | `"en"`     | UI language. `en` or `zh`. |

---

## `hosts`

Named SSH host definitions. These are referenced by `host` fields in tunnels, mounts, reverse proxies, and syncs.

```yaml
hosts:
  gpu-server:
    user: ubuntu
    host: 192.168.1.100
    port: 22
    identity: ~/.ssh/gpu_key

  cloud-vps:
    user: root
    host: example.com
    port: 22022
    identity: ~/.ssh/cloud.pem
```

| Field      | Type   | Default | Description |
|------------|--------|---------|-------------|
| `user`     | string | `"root"` | SSH username. |
| `host`     | string | *required* | Hostname or IP address. |
| `port`     | int    | `22`    | SSH port. |
| `identity` | string | `""`    | Path to SSH private key file. Supports `~` expansion. If empty, SSH uses its default key discovery. |

The key name (e.g., `gpu-server`) is used as the reference name throughout the config.

---

## `tunnels`

SSH tunnel services with port forwarding. Each entry becomes a long-running `ssh -N` process.

```yaml
tunnels:
  - name: gpu-jupyter
    host: gpu-server
    proxy: direct             # Optional: override default proxy
    forwards:
      - type: local
        local_port: 8888
        remote_port: 8888
        remote_host: 127.0.0.1

      - type: remote
        local_port: 3000
        remote_port: 3000

      - type: dynamic
        local_port: 1080
```

### Tunnel Entry

| Field      | Type   | Default              | Description |
|------------|--------|----------------------|-------------|
| `name`     | string | *required*           | Unique service name. Used in CLI commands and logs. |
| `host`     | string | *required*           | Reference to a key in `hosts`. |
| `proxy`    | string | `defaults.proxy`     | Proxy mode for this tunnel's SSH connection. Overrides the global default. |
| `forwards` | list   | `[]`                 | List of port forwarding rules. |

### Forward Rule

| Field         | Type   | Default       | Description |
|---------------|--------|---------------|-------------|
| `type`        | string | `"local"`     | Forwarding type: `local` (SSH `-L`), `remote` (SSH `-R`), or `dynamic` (SSH `-D`). |
| `local_port`  | int    | *required*    | Port on the local machine. For `dynamic`, this is the SOCKS proxy port. |
| `remote_host` | string | `"127.0.0.1"` | Host on the remote network to forward to. Only used with `local` and `remote` types. |
| `remote_port` | int    | *required*    | Port on the remote side. Not used with `dynamic`. |

**How they map to SSH flags:**

| Type    | SSH Flag | Meaning |
|---------|----------|---------|
| local   | `-L local_port:remote_host:remote_port` | Access `remote_host:remote_port` via `localhost:local_port` |
| remote  | `-R remote_port:remote_host:local_port` | Remote side can access `localhost:local_port` via `remote:remote_port` |
| dynamic | `-D local_port` | SOCKS5 proxy on `localhost:local_port` tunneled through the remote |

### SSH Options

All tunnels use these hardcoded SSH options:

```
-N                          # No remote command
-o ServerAliveInterval=15   # Send keepalive every 15s
-o ServerAliveCountMax=3    # Disconnect after 3 missed keepalives
-o TCPKeepAlive=yes
-o ExitOnForwardFailure=yes # Fail fast if port binding fails
-o StrictHostKeyChecking=no
-o ConnectTimeout=15
-o BatchMode=yes            # No interactive prompts
```

---

## `mounts`

SSHFS mount services. Each entry mounts a remote directory locally via SFTP.

```yaml
mounts:
  - name: gpu-home
    host: gpu-server
    remote_path: /home/ubuntu
    mount_point: ""
    options: []

  - name: cloud-root
    host: cloud-vps
    remote_path: /
    mount_point: ~/mounts/cloud
    options:
      - reconnect
      - cache=yes
```

| Field         | Type     | Default                         | Description |
|---------------|----------|---------------------------------|-------------|
| `name`        | string   | *required*                      | Unique service name. |
| `host`        | string   | *required*                      | Reference to a key in `hosts`. |
| `remote_path` | string   | `"/"`                           | Directory on the remote server to mount. |
| `mount_point` | string   | `"<workspace>/<name>"`          | Local directory to mount to. If empty, auto-assigned under the workspace directory. Supports `~` expansion. |
| `options`     | list     | `[]`                            | Extra sshfs `-o` options (e.g., `["reconnect", "cache=yes"]`). |

### Platform Notes

**Linux:** Requires `sshfs` (FUSE-based). Install via your package manager. Unmounting uses `fusermount -uz`.

**Windows:** Requires [WinFsp](https://winfsp.dev/) + [SSHFS-Win](https://github.com/winfsp/sshfs-win). rdm looks for `sshfs.exe` at `C:\Program Files\SSHFS-Win\bin\sshfs.exe` first, then falls back to `PATH`. On Windows, sshfs daemonizes itself, so rdm discovers running mounts by scanning process command lines.

**macOS:** Requires macFUSE + sshfs (`brew install macfuse && brew install gromgit/fuse/sshfs-mac`).

---

## `reverse_proxies`

Reverse proxy tunnels using SSH `-R`. The primary use case is exposing a local proxy (Clash/V2Ray) on a remote server so that tools like Claude Code can route their traffic through it.

```yaml
reverse_proxies:
  - name: cloud-clash
    host: cloud-vps
    local_port: 7897
    remote_port: 7897
```

| Field         | Type   | Default    | Description |
|---------------|--------|------------|-------------|
| `name`        | string | *required* | Unique service name. |
| `host`        | string | *required* | Reference to a key in `hosts`. |
| `local_port`  | int    | `7897`     | Port on the local machine to expose (e.g., your Clash SOCKS5 port). |
| `remote_port` | int    | `7897`     | Port to bind on the remote server. After starting, `socks5://127.0.0.1:<remote_port>` on the remote server routes through your local proxy. |

The generated SSH command:

```bash
ssh -N -R <remote_port>:127.0.0.1:<local_port> \
    -o GatewayPorts=no \
    -o ServerAliveInterval=15 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=accept-new \
    user@host
```

`GatewayPorts=no` ensures only localhost on the remote can use the forwarded port (security).

---

## `syncs`

File sync definitions for one-shot rsync push/pull operations. These are NOT long-running services -- you trigger them manually with `rdm sync <name>`.

```yaml
syncs:
  - name: my-project
    host: cloud-vps
    local_path: ./src
    remote_path: /opt/project/src
    mode: push
    exclude:
      - .git
      - node_modules
      - target
      - __pycache__
```

| Field         | Type     | Default  | Description |
|---------------|----------|----------|-------------|
| `name`        | string   | *required* | Unique sync name. |
| `host`        | string   | *required* | Reference to a key in `hosts`. |
| `local_path`  | string   | `"."`    | Local directory. Relative paths are resolved from the config file directory. Supports `~` expansion. |
| `remote_path` | string   | `"~"`   | Remote directory. |
| `mode`        | string   | `"push"` | Default direction: `push` (local to remote) or `pull` (remote to local). Can be overridden at runtime with `rdm sync <name> --pull`. |
| `exclude`     | list     | `[]`     | Patterns to exclude (passed as rsync `--exclude`). Ignored when falling back to scp. |

### rsync vs scp

rdm prefers rsync when available. Benefits of rsync:

- Incremental transfers (only changed bytes)
- `--exclude` patterns
- `--dry-run` support
- Transfer statistics

If rsync is not found on `PATH`, rdm falls back to `scp -r`. In this case:

- Exclude patterns are ignored (with a warning).
- Dry-run mode prints the command but does not execute.

---

## Runtime State

rdm stores runtime state in `<workspace>/.rdm/state.json`. This file tracks:

- **Proxy overrides:** When you cycle a service's proxy mode in the TUI (press `c`), the override is saved here and persists across restarts.

State file format:

```json
{
  "proxy_overrides": {
    "tunnel:gpu-jupyter": "clash",
    "mount:gpu-home": "direct"
  }
}
```

Proxy resolution order:

1. Runtime override in `state.json`
2. Per-service `proxy` field in the YAML config
3. `defaults.proxy`

### Logs

Service logs are written to `<workspace>/.rdm/logs/<service-name>.log` in append mode. Use `rdm log <name>` or the TUI's log viewer (press `l`) to inspect them.

### PID Files

Each running service writes its PID to `<workspace>/.rdm/logs/<service-name>.pid`. On startup, rdm reads these to reattach to existing processes.

---

## Proxy Modes

Three proxy modes are supported for SSH connections:

### `direct`

Connect to the SSH server directly, no proxy.

### `clash`

Route the SSH connection through a local SOCKS5 proxy. The proxy command depends on the platform:

- **Linux/macOS:** `ProxyCommand=nc -x 127.0.0.1:<clash_port> %h %p`
- **Windows:** `ProxyCommand=connect -S 127.0.0.1:<clash_port> %h %p` (uses `connect.exe` from Git for Windows)

### `jump:<alias>`

Use SSH jump host (ProxyJump). The alias is passed directly to `ssh -J`:

```yaml
defaults:
  proxy: jump:bastion-host
```

This adds `-J bastion-host` to the SSH command. The alias can be an SSH config host or `user@host:port`.

---

## Examples

### Minimal: Just a Tunnel

```yaml
version: 1
hosts:
  server:
    user: ubuntu
    host: 10.0.0.5
tunnels:
  - name: jupyter
    host: server
    forwards:
      - type: local
        local_port: 8888
        remote_port: 8888
```

### Claude Code Behind Restricted Network

```yaml
version: 1
defaults:
  proxy: direct
  clash_port: 7897
hosts:
  gpu:
    user: ubuntu
    host: gpu.example.com
    port: 22
    identity: ~/.ssh/gpu_key
reverse_proxies:
  - name: clash-for-claude
    host: gpu
    local_port: 7897
    remote_port: 7897
```

### Full Setup: Tunnel + Mount + Reverse Proxy + Sync

```yaml
version: 1

defaults:
  proxy: clash
  clash_port: 7897
  auto_restart: true

hosts:
  devbox:
    user: dev
    host: devbox.internal.corp
    port: 22022
    identity: ~/.ssh/devbox_ed25519

tunnels:
  - name: jupyter
    host: devbox
    forwards:
      - type: local
        local_port: 8888
        remote_port: 8888
      - type: local
        local_port: 6006
        remote_port: 6006

mounts:
  - name: devbox-workspace
    host: devbox
    remote_path: /home/dev/workspace
    mount_point: ~/mounts/devbox

reverse_proxies:
  - name: devbox-clash
    host: devbox
    local_port: 7897
    remote_port: 7897

syncs:
  - name: ml-project
    host: devbox
    local_path: ./ml-project
    remote_path: /home/dev/workspace/ml-project
    mode: push
    exclude:
      - .git
      - __pycache__
      - "*.pyc"
      - data/
      - wandb/
```

---

## Mirrors

Code mirrors enable smart syncing of remote code repositories to your local machine. Large files like model weights, images, datasets, and compiled binaries are automatically excluded.

### Schema

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | required | Unique name for this mirror |
| `host` | string | required | Reference to a host in `hosts` |
| `remote_path` | string | required | Absolute path on the remote server |
| `local_path` | string | `<workspace>/mirrors/<name>` | Local directory to sync to |
| `direction` | string | `pull` | `pull` (remote→local), `push` (local→remote), or `both` |
| `auto_exclude` | bool | `true` | Enable smart exclusion of large/binary files |
| `max_file_size` | string | `10M` | Skip files larger than this (rsync --max-size format) |
| `exclude` | list | `[]` | Additional glob patterns to exclude |
| `include` | list | `[]` | Patterns to force-include (overrides auto-exclude) |
| `delete` | bool | `false` | Remove local files not present on remote |

### Auto-Excluded File Types

When `auto_exclude: true`, the following categories are filtered:

- **Model weights:** `.pt`, `.pth`, `.onnx`, `.safetensors`, `.bin`, `.h5`, `.hdf5`, `.pkl`, `.ckpt`, `.tflite`, `.pb`
- **Datasets:** `.tar`, `.tar.gz`, `.zip`, `.7z`, `.parquet`, `.arrow`, `.tfrecord`, `.npy`, `.npz`, `.csv`, `.lmdb`
- **Images:** `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.webp`, `.ico`, `.svg`
- **Video/Audio:** `.mp4`, `.avi`, `.mkv`, `.mov`, `.mp3`, `.wav`, `.flac`
- **Compiled:** `.so`, `.dll`, `.dylib`, `.o`, `.a`, `.whl`, `.egg`, `.class`, `.jar`
- **Directories:** `__pycache__/`, `.git/`, `node_modules/`, `.venv/`, `wandb/`, `checkpoints/`, `.cache/`, `build/`, `dist/`

### Example

```yaml
mirrors:
  - name: ml-project
    host: gpu-server
    remote_path: /home/ubuntu/ml-project
    auto_exclude: true
    max_file_size: 10M
    exclude:
      - "data/raw/"
      - "wandb/"
    include:
      - "configs/*.yaml"    # force-include config files
```

### CLI Commands

```bash
rdm mirror browse <host>                    # Discover repos on remote
rdm mirror add <host> <path> --name NAME    # Add mirror to config
rdm mirror pull <name>                      # Pull remote → local
rdm mirror push <name>                      # Push local → remote
rdm mirror status <name>                    # Show pending changes
rdm mirror list                             # List all mirrors
```
