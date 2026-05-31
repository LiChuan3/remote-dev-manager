"""Live service manager owning the rdm config and service objects."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

from rdm.config import (
    Config,
    DefaultsConfig,
    HostConfig,
    find_config,
    get_service_proxy,
    load_config,
    set_service_proxy,
    _user_config_dir,
)
from rdm.models import Service, Status
from rdm.mount import MountService
from rdm.proxy import ReverseProxyService
from rdm.tunnel import TunnelService

# Map between the lowercase string kind used in the API and ServiceType names.
_KINDS = ("tunnel", "mount", "reverse_proxy")


def _empty_config(config_path: Path) -> Config:
    """Build a minimal in-memory config when no file exists yet."""
    return Config(
        defaults=DefaultsConfig(),
        hosts={},
        tunnels=[],
        mounts=[],
        reverse_proxies=[],
        syncs=[],
        mirrors=[],
        _config_path=config_path,
    )


def _service_kind(svc: Service) -> str:
    """Return the lowercase string kind for a service."""
    return svc.kind.value


class ServiceManager:
    """Owns the config and live :class:`Service` objects for the API."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self.config_path: Path
        self.config: Config
        self.services: dict[tuple[str, str], Service] = {}

        try:
            self.config = load_config(config_path)
            cp = self.config._config_path
            self.config_path = cp if cp is not None else self._default_config_path()
        except FileNotFoundError:
            self.config_path = (
                Path(config_path).resolve()
                if config_path
                else self._default_config_path()
            )
            self.config = _empty_config(self.config_path)

        self._build_services()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _default_config_path() -> Path:
        existing = find_config()
        if existing is not None:
            return existing
        return (_user_config_dir() / "config.yaml").resolve()

    def _build_services(self) -> None:
        """Instantiate services from ``self.config`` (mirrors cli.build_services)."""
        services: dict[tuple[str, str], Service] = {}

        for tc in self.config.tunnels:
            host = self.config.hosts.get(tc.host_ref)
            if host is None:
                continue
            proxy = (
                get_service_proxy(self.config.workspace_path, "tunnel", tc.name)
                or tc.proxy
                or self.config.defaults.proxy
            )
            svc = TunnelService(
                config=tc,
                host=host,
                logs_dir=self.config.logs_dir,
                clash_port=self.config.defaults.clash_port,
            )
            svc.proxy = proxy
            services[("tunnel", tc.name)] = svc

        for mc in self.config.mounts:
            host = self.config.hosts.get(mc.host_ref)
            if host is None:
                continue
            proxy = (
                get_service_proxy(self.config.workspace_path, "mount", mc.name)
                or self.config.defaults.proxy
            )
            svc = MountService(
                config=mc,
                host=host,
                logs_dir=self.config.logs_dir,
                workspace=self.config.workspace_path,
                clash_port=self.config.defaults.clash_port,
            )
            svc.proxy = proxy
            services[("mount", mc.name)] = svc

        for rpc in self.config.reverse_proxies:
            host = self.config.hosts.get(rpc.host_ref)
            if host is None:
                continue
            proxy = (
                get_service_proxy(self.config.workspace_path, "reverse_proxy", rpc.name)
                or self.config.defaults.proxy
            )
            svc = ReverseProxyService(
                config=rpc,
                host=host,
                logs_dir=self.config.logs_dir,
                clash_port=self.config.defaults.clash_port,
            )
            svc.proxy = proxy
            services[("reverse_proxy", rpc.name)] = svc

        self.services = services

    @staticmethod
    def _info(svc: Service) -> dict:
        """Return a ServiceInfo-shaped dict for a service."""
        return {
            "name": svc.name,
            "kind": _service_kind(svc),
            "status": svc.status.name,
            "proxy": svc.proxy,
            "pid": svc.pid,
            "uptime": svc.uptime_str(),
            "last_error": svc.last_error,
            "started_at": svc.started_at,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Re-load config and rebuild services, preserving running ones."""
        with self._lock:
            old = self.services
            try:
                self.config = load_config(str(self.config_path))
            except FileNotFoundError:
                self.config = _empty_config(self.config_path)
            self._build_services()
            # Preserve liveness: reattach to any process that is still running.
            for key, svc in self.services.items():
                old_svc = old.get(key)
                if old_svc is not None and old_svc.status == Status.RUNNING:
                    try:
                        svc.reattach()
                        svc.poll()
                    except Exception:
                        pass

    def poll_all(self) -> None:
        """Poll every service and restart failed services when configured."""
        with self._lock:
            for svc in self.services.values():
                try:
                    svc.poll()
                except Exception:
                    pass
                if not self.config.defaults.auto_restart:
                    continue
                if svc.user_stopped or svc.status != Status.FAILED:
                    continue
                retry_at = svc.next_retry_at or 0.0
                if time.time() < retry_at:
                    continue
                try:
                    svc.restart()
                except Exception as exc:
                    svc.last_error = str(exc)

    def snapshot(self) -> list[dict]:
        """Return ServiceInfo-shaped dicts for all services."""
        with self._lock:
            return [self._info(svc) for svc in self.services.values()]

    def get(self, kind: str, name: str) -> Optional[Service]:
        return self.services.get((kind, name))

    def start(self, kind: str, name: str) -> Optional[dict]:
        with self._lock:
            svc = self.services.get((kind, name))
            if svc is None:
                return None
            svc.user_stopped = False
            svc.start()
            return self._info(svc)

    def stop(self, kind: str, name: str) -> Optional[dict]:
        with self._lock:
            svc = self.services.get((kind, name))
            if svc is None:
                return None
            svc.user_stopped = True
            svc.stop()
            return self._info(svc)

    def stop_all(self) -> list[dict]:
        """Stop every registered long-running service."""
        infos: list[dict] = []
        with self._lock:
            for svc in self.services.values():
                try:
                    svc.user_stopped = True
                    svc.stop()
                except Exception as exc:
                    svc.last_error = str(exc)
                infos.append(self._info(svc))
        return infos

    def restart(self, kind: str, name: str) -> Optional[dict]:
        with self._lock:
            svc = self.services.get((kind, name))
            if svc is None:
                return None
            svc.user_stopped = False
            svc.restart()
            return self._info(svc)

    def set_proxy(self, kind: str, name: str, proxy: str) -> Optional[dict]:
        with self._lock:
            svc = self.services.get((kind, name))
            if svc is None:
                return None
            svc.proxy = proxy
            set_service_proxy(self.config.workspace_path, kind, name, proxy)
            if svc.status == Status.RUNNING:
                try:
                    svc.restart()
                except Exception as exc:
                    svc.last_error = str(exc)
            return self._info(svc)

    def host(self, name: str) -> Optional[HostConfig]:
        return self.config.hosts.get(name)

    def register(self, kind: str, svc: Service) -> None:
        """Register an externally-created service (e.g. ephemeral aiproxy)."""
        with self._lock:
            self.services[(kind, svc.name)] = svc
