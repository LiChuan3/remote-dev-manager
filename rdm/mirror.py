"""Smart code repository mirroring with auto-exclusion of large files."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from rdm.config import HostConfig, MirrorConfig

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exclusion patterns
# ---------------------------------------------------------------------------

ML_EXCLUDE_PATTERNS: list[str] = [
    # Model weights
    "*.pt", "*.pth", "*.onnx", "*.safetensors", "*.bin",
    "*.h5", "*.hdf5", "*.pkl", "*.pickle",
    "*.ckpt", "*.ckpt.*", "*.tflite", "*.pb", "*.savedmodel/",
    "*.mar", "*.engine",
    # Datasets / archives
    "*.tar", "*.tar.gz", "*.tgz", "*.tar.bz2", "*.tar.xz",
    "*.zip", "*.7z", "*.rar",
    "*.parquet", "*.arrow", "*.feather", "*.tfrecord",
    "*.lmdb/", "*.npy", "*.npz", "*.dat",
    # Images
    "*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp",
    "*.tiff", "*.tif", "*.webp", "*.ico", "*.svg",
    # Video / Audio
    "*.mp4", "*.avi", "*.mkv", "*.mov", "*.wmv", "*.flv",
    "*.mp3", "*.wav", "*.flac", "*.ogg", "*.m4a",
    # Compiled / Binary
    "*.so", "*.dll", "*.dylib", "*.o", "*.a", "*.lib",
    "*.whl", "*.egg", "*.class", "*.jar",
    # Large data
    "*.csv", "*.tsv", "*.jsonl",
    "*.db", "*.sqlite", "*.sqlite3",
]

DEFAULT_EXCLUDE_PATTERNS: list[str] = [
    # Python
    "__pycache__/", "*.pyc", "*.pyo",
    # VCS
    ".git/", ".svn/", ".hg/",
    # Package managers / virtual envs
    "node_modules/", ".venv/", "venv/", "env/", ".tox/", ".nox/",
    # Caches / coverage
    ".mypy_cache/", ".pytest_cache/", ".ruff_cache/", ".coverage", "htmlcov/",
    # OS junk
    ".DS_Store", "Thumbs.db", "desktop.ini",
    # ML experiment tracking
    "wandb/", "mlruns/", "lightning_logs/", "tensorboard/", "runs/",
    # Checkpoints / outputs
    "checkpoints/", "outputs/", "results/", ".cache/",
    # Build artifacts
    "dist/", "build/", "*.egg-info/",
    # IDE
    ".idea/", ".vscode/",
    # Misc
    "*.log", "*.tmp", "*.swp", "*~",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_smart_excludes(
    auto_exclude: bool,
    extra_exclude: list[str],
    include_override: list[str],
) -> list[str]:
    """Combine auto-exclusion patterns with user extras, minus any include overrides."""
    patterns: list[str] = []
    if auto_exclude:
        patterns.extend(DEFAULT_EXCLUDE_PATTERNS)
        patterns.extend(ML_EXCLUDE_PATTERNS)
    patterns.extend(extra_exclude)
    # Remove patterns that match any include_override
    if include_override:
        patterns = [p for p in patterns if p not in include_override]
    return list(dict.fromkeys(patterns))  # deduplicate preserving order


def _ssh_cmd_base(host: HostConfig) -> list[str]:
    """Build base SSH command with port, identity, batch mode."""
    cmd = ["ssh"]
    if host.port and host.port != 22:
        cmd += ["-p", str(host.port)]
    if host.identity:
        cmd += ["-i", str(Path(host.identity).expanduser())]
    cmd += [
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
    ]
    return cmd


def _ssh_exec(
    host: HostConfig,
    command: str,
    timeout: int = 30,
) -> tuple[int, str, str]:
    """Run command on remote via SSH. Returns (returncode, stdout, stderr)."""
    cmd = _ssh_cmd_base(host) + [f"{host.user}@{host.host}", command]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "SSH command timed out"


def _build_rsync_cmd(
    config: MirrorConfig,
    host: HostConfig,
    direction: str,
    dry_run: bool = False,
    excludes: list[str] | None = None,
) -> list[str]:
    """Build rsync command for mirror sync."""
    rsync = shutil.which("rsync") or "rsync"
    cmd = [rsync, "-avz", "--stats", "--human-readable"]

    if dry_run:
        cmd.append("-n")

    if config.max_file_size:
        cmd += ["--max-size", config.max_file_size]

    if config.delete:
        cmd.append("--delete")

    # Include patterns FIRST (rsync processes rules in order)
    for pat in config.include:
        cmd += ["--include", pat]

    # Exclude patterns
    if excludes is None:
        excludes = get_smart_excludes(config.auto_exclude, config.exclude, config.include)
    for pat in excludes:
        cmd += ["--exclude", pat]

    # SSH transport
    ssh_parts = ["ssh"]
    if host.port and host.port != 22:
        ssh_parts += ["-p", str(host.port)]
    if host.identity:
        ssh_parts += ["-i", str(Path(host.identity).expanduser())]
    ssh_parts += ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
    cmd += ["-e", " ".join(ssh_parts)]

    remote_spec = f"{host.user}@{host.host}:{config.remote_path}/"
    local_spec = str(Path(config.local_path).resolve()) + "/"
    # Trailing slashes are important for rsync -- sync CONTENTS not the dir itself

    if direction == "pull":
        cmd += [remote_spec, local_spec]
    else:
        cmd += [local_spec, remote_spec]

    return cmd


def _run_rsync(cmd: list[str]) -> dict[str, Any]:
    """Execute rsync, stream output, parse stats."""
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        lines: list[str] = []
        for line in proc.stdout:  # type: ignore[union-attr]
            sys.stdout.write(line)
            sys.stdout.flush()
            lines.append(line)
        proc.wait()
        output = "".join(lines)

        # Parse stats
        files = 0
        total_bytes = 0
        errors: list[str] = []
        for line in output.splitlines():
            m = re.search(r"Number of regular files transferred:\s*([\d,]+)", line)
            if m:
                files = int(m.group(1).replace(",", ""))
            m = re.search(r"Total transferred file size:\s*([\d,]+)", line)
            if m:
                total_bytes = int(m.group(1).replace(",", ""))
            if "error" in line.lower() and "rsync" in line.lower():
                errors.append(line.strip())

        if proc.returncode not in (0, 23):  # 23 = partial transfer (some files skipped)
            errors.append(f"rsync exited with code {proc.returncode}")

        return {"files_transferred": files, "bytes": total_bytes, "errors": errors}
    except FileNotFoundError:
        return {
            "files_transferred": 0,
            "bytes": 0,
            "errors": ["rsync not found. Install rsync first."],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def mirror_pull(
    config: MirrorConfig,
    host: HostConfig,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Pull remote repo to local with smart filtering."""
    local = Path(config.local_path).resolve()
    local.mkdir(parents=True, exist_ok=True)

    excludes = get_smart_excludes(config.auto_exclude, config.exclude, config.include)
    cmd = _build_rsync_cmd(config, host, "pull", dry_run, excludes)

    print(
        f"{'[DRY RUN] ' if dry_run else ''}"
        f"Pulling {host.user}@{host.host}:{config.remote_path} -> {local}"
    )
    print(
        f"  Auto-exclude: {'on' if config.auto_exclude else 'off'}, "
        f"Max file size: {config.max_file_size}"
    )
    print(f"  Excluding {len(excludes)} patterns")
    print()

    result = _run_rsync(cmd)
    result["local_path"] = str(local)
    return result


def mirror_push(
    config: MirrorConfig,
    host: HostConfig,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Push local changes to remote."""
    local = Path(config.local_path).resolve()
    if not local.exists():
        return {
            "files_transferred": 0,
            "bytes": 0,
            "errors": [f"Local path does not exist: {local}"],
        }

    excludes = get_smart_excludes(config.auto_exclude, config.exclude, config.include)
    cmd = _build_rsync_cmd(config, host, "push", dry_run, excludes)

    print(
        f"{'[DRY RUN] ' if dry_run else ''}"
        f"Pushing {local} -> {host.user}@{host.host}:{config.remote_path}"
    )
    print()

    result = _run_rsync(cmd)
    return result


def mirror_status(
    config: MirrorConfig,
    host: HostConfig,
) -> dict[str, Any]:
    """Show what would change in both directions (dry-run)."""
    excludes = get_smart_excludes(config.auto_exclude, config.exclude, config.include)

    print("=== Changes if PULL (remote -> local) ===")
    pull_cmd = _build_rsync_cmd(config, host, "pull", dry_run=True, excludes=excludes)
    pull_result = _run_rsync(pull_cmd)

    print("\n=== Changes if PUSH (local -> remote) ===")
    push_cmd = _build_rsync_cmd(config, host, "push", dry_run=True, excludes=excludes)
    push_result = _run_rsync(push_cmd)

    return {
        "pull_changes": pull_result["files_transferred"],
        "push_changes": push_result["files_transferred"],
    }


def list_remote_dirs(
    host: HostConfig,
    base_path: str = "~",
    max_depth: int = 2,
) -> list[dict[str, Any]]:
    """SSH to remote and discover directories that look like code projects."""
    markers = [
        ".git", "Cargo.toml", "package.json", "pyproject.toml",
        "setup.py", "setup.cfg", "go.mod", "CMakeLists.txt",
        "Makefile", "pom.xml", "build.gradle", "*.sln",
        "requirements.txt", "environment.yml", "Pipfile",
        "composer.json", "Gemfile", "mix.exs",
    ]

    find_exprs = " -o ".join(f'-name "{m}"' for m in markers)
    # Expand ~ and find project markers, output their parent directories
    cmd = (
        f"cd {base_path} && "
        f'find . -maxdepth {max_depth} -type f \\( {find_exprs} \\) 2>/dev/null '
        f'| while read f; do dirname "$f"; done | sort -u'
    )

    rc, stdout, stderr = _ssh_exec(host, cmd, timeout=30)
    if rc != 0:
        print(
            f"Warning: remote scan returned code {rc}: {stderr.strip()}",
            file=sys.stderr,
        )

    repos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line or line in seen:
            continue
        seen.add(line)

        # Get full path
        if base_path == "~":
            full_path = f"~/{line.lstrip('./')}" if line != "." else "~"
        else:
            full_path = (
                f"{base_path}/{line.lstrip('./')}" if line != "." else base_path
            )

        # Detect what markers are present
        marker_cmd = (
            f"cd {base_path}/{line} 2>/dev/null && "
            f'ls -d {" ".join(markers)} 2>/dev/null'
        )
        _, marker_out, _ = _ssh_exec(host, marker_cmd, timeout=10)
        found_markers = [
            m.strip() for m in marker_out.strip().splitlines() if m.strip()
        ]

        # Get total size
        _, size_out, _ = _ssh_exec(
            host,
            f"du -sh {base_path}/{line} 2>/dev/null | cut -f1",
            timeout=15,
        )
        size = size_out.strip() or "?"

        # Determine project type
        project_type = _detect_type(found_markers)

        repos.append({
            "path": full_path,
            "rel_path": line,
            "markers": found_markers,
            "size": size,
            "type": project_type,
        })

    return repos


def _detect_type(markers: list[str]) -> str:
    """Infer project type from marker files."""
    types: list[str] = []
    if "Cargo.toml" in markers:
        types.append("Rust")
    if "package.json" in markers:
        types.append("Node.js")
    if any(
        m in markers
        for m in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile")
    ):
        types.append("Python")
    if "go.mod" in markers:
        types.append("Go")
    if "CMakeLists.txt" in markers:
        types.append("C/C++")
    if "pom.xml" in markers or "build.gradle" in markers:
        types.append("Java")
    if any(m.endswith(".sln") for m in markers):
        types.append(".NET")
    if "Gemfile" in markers:
        types.append("Ruby")
    if "composer.json" in markers:
        types.append("PHP")
    if "mix.exs" in markers:
        types.append("Elixir")
    if "Makefile" in markers and not types:
        types.append("Make")
    if ".git" in markers and not types:
        types.append("Git")
    return "/".join(types) if types else "Unknown"


def add_mirror_to_config(
    config_path: Path,
    name: str,
    host_ref: str,
    remote_path: str,
    local_path: str = "",
    auto_exclude: bool = True,
) -> None:
    """Append a mirror entry to the YAML config file."""
    import yaml

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if "mirrors" not in data:
        data["mirrors"] = []

    entry: dict[str, Any] = {
        "name": name,
        "host": host_ref,
        "remote_path": remote_path,
        "auto_exclude": auto_exclude,
    }
    if local_path:
        entry["local_path"] = local_path

    # Check for duplicate
    for existing in data["mirrors"]:
        if existing.get("name") == name:
            print(f"Mirror '{name}' already exists in config.")
            return

    data["mirrors"].append(entry)

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"Added mirror '{name}' to {config_path}")


def estimate_mirror_size(
    host: HostConfig,
    remote_path: str,
    auto_exclude: bool = True,
) -> str:
    """Estimate the size of a mirror after exclusions."""
    excludes = get_smart_excludes(auto_exclude, [], [])
    exclude_args = " ".join(
        f'--exclude="{p}"' for p in excludes[:30]
    )  # limit to avoid arg too long

    rsync = shutil.which("rsync") or "rsync"
    ssh_parts = ["ssh"]
    if host.port and host.port != 22:
        ssh_parts += ["-p", str(host.port)]
    if host.identity:
        ssh_parts += ["-i", str(Path(host.identity).expanduser())]

    cmd = (
        f'{rsync} -avzn --stats -e "{" ".join(ssh_parts)}" '
        f"{exclude_args} "
        f"{host.user}@{host.host}:{remote_path}/ /tmp/rdm-dry "
        f'2>/dev/null | grep "Total file size"'
    )

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=60,
        )
        for line in result.stdout.splitlines():
            if "Total file size" in line:
                return line.strip().split(":")[-1].strip()
    except Exception:
        pass
    return "unknown"
