"""Pydantic v2 request/response models for the rdm API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    """Permissive base model that ignores unknown extra fields."""

    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------------------
# Hosts
# ---------------------------------------------------------------------------

class HostIn(_Base):
    name: str
    user: str
    host: str
    port: int = 22
    identity: str = ""


class HostUpdate(_Base):
    user: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    identity: Optional[str] = None


class SshConfigHost(_Base):
    name: str
    user: str = ""
    host: str
    hostname: str = ""
    port: int = 22
    identity: str = ""
    proxy_jump: str = ""
    proxy_command: str = ""
    source: str = ""
    editable: bool = False


class SshConfigHostIn(_Base):
    name: str
    hostname: str = ""
    user: str = ""
    port: int = 22
    identity: str = ""
    proxy_jump: str = ""
    proxy_command: str = ""


# ---------------------------------------------------------------------------
# Remote connection
# ---------------------------------------------------------------------------

class TestResult(_Base):
    ok: bool = False
    latency_ms: Optional[float] = None
    message: str = ""
    whoami: Optional[str] = None
    hostname: Optional[str] = None
    os: Optional[str] = None


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

class ServiceInfo(_Base):
    name: str
    kind: str
    status: str
    proxy: str
    pid: Optional[int] = None
    uptime: str = "-"
    last_error: Optional[str] = None
    started_at: Optional[float] = None


# ---------------------------------------------------------------------------
# Service definitions
# ---------------------------------------------------------------------------

class ForwardIn(_Base):
    type: str = "local"
    local_port: int
    remote_host: str = "127.0.0.1"
    remote_port: int


class TunnelIn(_Base):
    name: str
    host: str
    proxy: Optional[str] = None
    forwards: list[ForwardIn] = Field(default_factory=list)


class MountIn(_Base):
    name: str
    host: str
    remote_path: str = "/"
    mount_point: str = ""
    options: list[str] = Field(default_factory=list)


class MountDiagnostics(_Base):
    platform: str
    ready: bool = False
    sshfs_found: bool = False
    sshfs_path: str = ""
    sshfs_version: str = ""
    sshfs_win_found: bool = False
    sshfs_win_path: str = ""
    winfsp_found: bool = False
    winfsp_path: str = ""
    missing: list[str] = Field(default_factory=list)


class MountInstallResult(_Base):
    ok: bool = False
    started: bool = False
    message: str = ""
    script_path: str = ""


class ReverseProxyIn(_Base):
    name: str
    host: str
    local_port: int = 7897
    remote_port: int = 7897


class MirrorIn(_Base):
    name: str
    host: str
    remote_path: str
    local_path: str = ""
    direction: str = "pull"
    auto_exclude: bool = True
    max_file_size: str = "10M"
    exclude: list[str] = Field(default_factory=list)
    include: list[str] = Field(default_factory=list)
    delete: bool = False


# ---------------------------------------------------------------------------
# Misc operations
# ---------------------------------------------------------------------------

class ProxyPatch(_Base):
    proxy: str


class AiProxySetupIn(_Base):
    host: str
    local_port: Optional[int] = None  # local Clash port to expose; defaults to config clash_port
    remote_port: int = 7897
    persistent: bool = False
    verify: bool = True
    ensure_tunnel: bool = True


class AiProxyTeardownIn(_Base):
    host: str


class FetchFileIn(_Base):
    host: str
    remote_path: str
    local_path: str = ""


class BrowseIn(_Base):
    path: str = "~"
    depth: int = 3


# Re-exported for convenience / typing of generic JSON payloads.
JsonDict = dict[str, Any]
