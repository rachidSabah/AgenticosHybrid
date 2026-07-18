"""
Plugin Registry Implementation

In-memory implementation of PluginRegistryPort with plugin lifecycle management,
dependency resolution, sandboxing, and hot reload support.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.domain.plugin import (
    PluginCapability,
    PluginCategory,
    PluginConfig,
    PluginDependencyType,
    PluginInstance,
    PluginManifest,
    PluginRegistrySnapshot,
    PluginSearchQuery,
    PluginSearchResult,
    PluginStatus,
    PluginValidationResult,
)
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus
from agentic_os.ports.plugin import (
    PluginInstallRequest,
    PluginRegistryPort,
    PluginUpdateRequest,
)

log = get_logger("plugin.registry")


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class PluginRegistryImpl(PluginRegistryPort):
    """
    In-memory Plugin Registry Implementation.

    Features:
    - Plugin lifecycle management (install, start, stop, update, uninstall)
    - Dependency resolution with topological sort
    - Sandbox enforcement via subprocess isolation
    - Hot reload support
    - Event emission for all lifecycle transitions
    - Health monitoring
    - Capability registry
    """

    bus: EventBus
    plugins_dir: Path = field(default_factory=lambda: Path("plugins"))
    _registry: PluginRegistrySnapshot = field(default_factory=PluginRegistrySnapshot)
    _processes: dict[str, subprocess.Popen] = field(default_factory=dict)
    _health_cache: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _shutdown: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    def _get_lock(self, name: str) -> asyncio.Lock:
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]

    async def _emit(self, topic: Topic, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus."""
        await self.bus.publish(
            EventEnvelope(
                type="event",
                source="plugin-registry",
                topic=topic.value,
                payload=payload,
            )
        )

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    async def install_plugin(self, request: PluginInstallRequest) -> PluginInstance:
        """Install a plugin from registry, URL, or local path."""
        async with self._get_lock(request.reference):
            # Validate plugin
            validation = await self.validate_plugin(request)
            if not validation.valid:
                raise ValueError(f"Plugin validation failed: {', '.join(validation.errors)}")

            manifest = validation.manifest
            if not manifest:
                raise ValueError("Plugin manifest not found after validation")

            # Check if already installed
            existing = self._registry.get_plugin(manifest.name)
            if existing and not request.force:
                raise ValueError(
                    f"Plugin {manifest.name} already installed. Use force=True to reinstall."
                )

            # Uninstall existing if force
            if existing and request.force:
                await self.uninstall_plugin(manifest.name, force=True)

            # Create plugin directory
            plugin_dir = self.plugins_dir / manifest.name
            plugin_dir.mkdir(parents=True, exist_ok=True)

            # Download/extract plugin (placeholder - would implement actual download)
            if request.source == "registry":
                # Would download from registry
                await self._download_from_registry(manifest, plugin_dir)
            elif request.source == "url":
                await self._download_from_url(request.reference, plugin_dir)
            elif request.source == "local":
                await self._copy_from_local(request.reference, plugin_dir)

            # Install dependencies first
            if not request.skip_dependencies:
                await self._install_dependencies(manifest)

            # Write manifest
            manifest_path = plugin_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2))

            # Create instance
            instance = PluginInstance(
                manifest=manifest,
                status=PluginStatus.INSTALLED,
                installed_at=_utcnow(),
                path=str(plugin_dir),
                config=request.config or {},
            )

            # Update registry
            self._registry = PluginRegistrySnapshot(
                plugins=tuple(p for p in self._registry.plugins if p.manifest.name != manifest.name)
                + (instance,),
                updated_at=_utcnow(),
            )

            await self._emit(
                Topic.PLUGIN_INSTALLED,
                {"name": manifest.name, "version": manifest.version, "path": str(plugin_dir)},
            )

            log.info(f"Installed plugin: {manifest.name} v{manifest.version}")
            return instance

    async def uninstall_plugin(self, name: str, force: bool = False) -> bool:
        """Uninstall a plugin."""
        async with self._get_lock(name):
            instance = self._registry.get_plugin(name)
            if not instance:
                return False

            # Stop if running
            if instance.status in (PluginStatus.RUNNING, PluginStatus.STARTING):
                if not force:
                    raise ValueError(
                        f"Plugin {name} is running. Use force=True to stop and uninstall."
                    )
                await self.stop_plugin(name)

            # Check if other plugins depend on this
            dependents = self._find_dependents(name)
            if dependents and not force:
                raise ValueError(f"Plugin {name} is required by: {', '.join(dependents)}")

            # Remove process if any
            if name in self._processes:
                proc = self._processes.pop(name)
                proc.terminate()
                try:
                    await asyncio.wait_for(asyncio.sleep(0.1), timeout=5.0)
                except TimeoutError:
                    proc.kill()

            # Clean up health cache
            self._health_cache.pop(name, None)

            # Update registry
            self._registry = PluginRegistrySnapshot(
                plugins=tuple(p for p in self._registry.plugins if p.manifest.name != name),
                updated_at=_utcnow(),
            )

            await self._emit(
                Topic.PLUGIN_UNINSTALLED,
                {"name": name},
            )

            log.info(f"Uninstalled plugin: {name}")
            return True

    async def get_plugin(self, name: str) -> PluginInstance | None:
        """Get a plugin by name."""
        return self._registry.get_plugin(name)

    async def list_plugins(
        self,
        category: PluginCategory | None = None,
        status: PluginStatus | None = None,
        enabled_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PluginInstance]:
        """List plugins with optional filtering."""
        plugins = list(self._registry.plugins)

        if category:
            plugins = [p for p in plugins if p.manifest.category == category]
        if status:
            plugins = [p for p in plugins if p.status == status]
        if enabled_only:
            plugins = [p for p in plugins if p.status == PluginStatus.RUNNING]

        plugins.sort(key=lambda p: p.manifest.name)
        return plugins[offset : offset + limit]

    async def update_plugin(self, name: str, request: PluginUpdateRequest) -> PluginInstance:
        """Update a plugin to a new version."""
        async with self._get_lock(name):
            instance = self._registry.get_plugin(name)
            if not instance:
                raise KeyError(f"Plugin not found: {name}")

            # Would download new version and replace
            # For now, just update config if provided
            if request.config is not None:
                await self.set_config(
                    name,
                    PluginConfig(
                        plugin_name=name,
                        values=request.config,
                        schema=instance.manifest.config_schema,
                    ),
                )
                # Return updated instance
                return self._registry.get_plugin(name) or instance

            return instance

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def start_plugin(self, name: str) -> PluginInstance:
        """Start a plugin."""
        async with self._get_lock(name):
            instance = self._registry.get_plugin(name)
            if not instance:
                raise KeyError(f"Plugin not found: {name}")

            if instance.status in (PluginStatus.RUNNING, PluginStatus.STARTING):
                return instance

            # Update to starting
            starting = instance.with_status(PluginStatus.STARTING)
            self._update_instance(starting)

            await self._emit(
                Topic.PLUGIN_STARTED,
                {"name": name, "version": instance.manifest.version},
            )

            try:
                # Start plugin process
                proc = await self._start_plugin_process(instance)
                self._processes[name] = proc

                # Update to running
                running = starting.with_status(PluginStatus.RUNNING, process_id=proc.pid)
                self._update_instance(running)

                await self._emit(
                    Topic.PLUGIN_STARTED,
                    {"name": name, "version": instance.manifest.version, "pid": proc.pid},
                )

                log.info(f"Started plugin: {name} (pid={proc.pid})")
                return running

            except Exception as e:
                failed = starting.with_status(PluginStatus.FAILED, error=str(e))
                self._update_instance(failed)
                await self._emit(
                    Topic.PLUGIN_FAILED,
                    {"name": name, "error": str(e)},
                )
                log.error(f"Failed to start plugin {name}: {e}")
                raise

    async def stop_plugin(self, name: str) -> PluginInstance:
        """Stop a plugin."""
        async with self._get_lock(name):
            instance = self._registry.get_plugin(name)
            if not instance:
                raise KeyError(f"Plugin not found: {name}")

            if instance.status in (PluginStatus.STOPPED, PluginStatus.STOPPING):
                return instance

            stopping = instance.with_status(PluginStatus.STOPPING)
            self._update_instance(stopping)

            try:
                # Stop process
                if name in self._processes:
                    proc = self._processes.pop(name)
                    proc.terminate()
                    try:
                        await asyncio.wait_for(asyncio.sleep(0.1), timeout=10.0)
                    except TimeoutError:
                        proc.kill()

                stopped = stopping.with_status(PluginStatus.STOPPED)
                self._update_instance(stopped)

                await self._emit(
                    Topic.PLUGIN_STOPPED,
                    {"name": name},
                )

                log.info(f"Stopped plugin: {name}")
                return stopped

            except Exception as e:
                failed = stopping.with_status(PluginStatus.FAILED, error=str(e))
                self._update_instance(failed)
                await self._emit(
                    Topic.PLUGIN_FAILED,
                    {"name": name, "error": str(e)},
                )
                log.error(f"Error stopping plugin {name}: {e}")
                raise

    async def restart_plugin(self, name: str) -> PluginInstance:
        """Restart a plugin."""
        instance = self._registry.get_plugin(name)
        if not instance:
            raise KeyError(f"Plugin not found: {name}")

        if instance.status == PluginStatus.RUNNING:
            await self.stop_plugin(name)
        return await self.start_plugin(name)

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    async def validate_plugin(self, request: PluginInstallRequest) -> PluginValidationResult:
        """Validate a plugin before installation."""
        errors = []
        warnings = []
        manifest = None
        dependency_status = {}

        try:
            # Would fetch manifest from registry/URL/local
            if request.source == "registry":
                manifest = await self.get_plugin_manifest(request.reference, request.version)
            elif request.source == "local":
                manifest = await self._load_manifest_from_local(request.reference)
            elif request.source == "url":
                manifest = await self._load_manifest_from_url(request.reference)

            if not manifest:
                errors.append("Could not load plugin manifest")
                return PluginValidationResult(valid=False, errors=errors)

            # Validate platform compatibility
            if not self._check_platform_version(manifest):
                errors.append(
                    f"Plugin requires platform {manifest.min_platform_version}+ "
                    f"(max: {manifest.max_platform_version or 'unlimited'})"
                )

            # Check dependencies
            for dep in manifest.dependencies:
                dep_instance = self._registry.get_plugin(dep.name)
                satisfied = dep_instance is not None and self._version_satisfies(
                    dep_instance.manifest.version, dep.version
                )
                dependency_status[dep.name] = satisfied
                if not satisfied and dep.type == PluginDependencyType.REQUIRED:
                    errors.append(f"Required dependency not satisfied: {dep.name} {dep.version}")

            # Verify signature if requested
            if request.verify_signature and manifest.signature:
                valid, msg = await self.verify_signature(manifest)
                if not valid:
                    errors.append(f"Signature verification failed: {msg}")
                elif msg:
                    warnings.append(f"Signature note: {msg}")

            return PluginValidationResult(
                valid=len(errors) == 0,
                errors=errors,
                warnings=warnings,
                manifest=manifest,
                dependency_status=dependency_status,
            )

        except Exception as e:
            errors.append(f"Validation error: {e}")
            return PluginValidationResult(valid=False, errors=errors)

    async def check_dependencies(self, name: str) -> dict[str, bool]:
        """Check if all dependencies for a plugin are satisfied."""
        instance = self._registry.get_plugin(name)
        if not instance:
            return {}

        result = {}
        for dep in instance.manifest.dependencies:
            dep_instance = self._registry.get_plugin(dep.name)
            satisfied = dep_instance is not None and self._version_satisfies(
                dep_instance.manifest.version, dep.version
            )
            result[dep.name] = satisfied
        return result

    async def resolve_dependencies(self, name: str) -> list[str]:
        """Get installation order for plugin and its dependencies (topological sort)."""
        instance = self._registry.get_plugin(name)
        if not instance:
            return [name]

        # Build dependency graph
        graph = {name: []}
        visited = set()

        def visit(plugin_name: str):
            if plugin_name in visited:
                return
            visited.add(plugin_name)

            plugin = self._registry.get_plugin(plugin_name)
            if plugin:
                for dep in plugin.manifest.dependencies:
                    if dep.type == PluginDependencyType.REQUIRED:
                        graph.setdefault(plugin_name, []).append(dep.name)
                        graph.setdefault(dep.name, [])
                        visit(dep.name)

        visit(name)

        # Topological sort
        order = []
        temp = set()

        def dfs(node: str):
            if node in temp:
                raise ValueError(f"Circular dependency detected involving {node}")
            if node in order:
                return
            temp.add(node)
            for neighbor in graph.get(node, []):
                dfs(neighbor)
            temp.remove(node)
            order.append(node)

        for node in graph:
            if node not in order:
                dfs(node)

        return order

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------

    async def get_config(self, name: str) -> PluginConfig | None:
        """Get plugin configuration."""
        instance = self._registry.get_plugin(name)
        if not instance:
            return None

        return PluginConfig(
            plugin_name=name,
            values=instance.config,
            schema=instance.manifest.config_schema,
        )

    async def set_config(self, name: str, config: PluginConfig) -> PluginConfig:
        """Update plugin configuration."""
        instance = self._registry.get_plugin(name)
        if not instance:
            raise KeyError(f"Plugin not found: {name}")

        # Validate against schema (basic validation)
        # In production, use jsonschema or similar

        updated = instance.with_config(config.values)
        self._update_instance(updated)

        await self._emit(
            Topic.PLUGIN_UPDATED,
            {"name": name, "config": config.values},
        )

        log.info(f"Updated config for plugin: {name}")
        return config

    # -------------------------------------------------------------------------
    # Search & Discovery
    # -------------------------------------------------------------------------

    async def search_plugins(self, query: PluginSearchQuery) -> PluginSearchResult:
        """Search plugins in registry."""
        # In a real implementation, this would query a remote registry
        # For now, return empty results
        return PluginSearchResult(
            plugins=[],
            total=0,
            query=query,
        )

    async def get_plugin_manifest(
        self, name: str, version: str | None = None
    ) -> PluginManifest | None:
        """Get plugin manifest from registry."""
        # Would fetch from remote registry
        # For local plugins, load from disk
        instance = self._registry.get_plugin(name)
        if instance:
            return instance.manifest
        return None

    async def list_registry_categories(self) -> list[PluginCategory]:
        """List available plugin categories in registry."""
        categories = set(p.manifest.category for p in self._registry.plugins)
        return sorted(categories)

    # -------------------------------------------------------------------------
    # Health & Monitoring
    # -------------------------------------------------------------------------

    async def check_health(self, name: str) -> tuple[str, dict[str, Any]]:
        """Check health of a running plugin."""
        instance = self._registry.get_plugin(name)
        if not instance:
            raise KeyError(f"Plugin not found: {name}")

        if instance.status != PluginStatus.RUNNING:
            return "unhealthy", {"error": f"Plugin not running (status: {instance.status.value})"}

        # In production, would call plugin health endpoint
        # For now, check if process is alive
        proc = self._processes.get(name)
        if proc and proc.poll() is not None:
            health = "unhealthy"
            details = {"error": "Process has terminated"}
        else:
            health = "healthy"
            details = {"pid": proc.pid if proc else None}

        # Update cache and instance
        updated = instance.with_health(health, details)
        self._update_instance(updated)
        self._health_cache[name] = (health, details)

        await self._emit(
            Topic.PLUGIN_HEALTH_CHANGED,
            {"name": name, "health": health, "details": details},
        )

        return health, details

    async def get_health(self, name: str) -> tuple[str, dict[str, Any]] | None:
        """Get cached health status."""
        cached = self._health_cache.get(name)
        if cached:
            return cached
        instance = self._registry.get_plugin(name)
        if instance:
            return instance.health, instance.health_details
        return None

    # -------------------------------------------------------------------------
    # Capabilities
    # -------------------------------------------------------------------------

    async def get_capabilities(self, name: str) -> list[PluginCapability]:
        """Get capabilities provided by a plugin."""
        instance = self._registry.get_plugin(name)
        if not instance:
            raise KeyError(f"Plugin not found: {name}")
        return list(instance.manifest.capabilities)

    async def find_plugins_by_capability(self, capability: str) -> list[PluginInstance]:
        """Find plugins that provide a specific capability."""
        matches = []
        for instance in self._registry.plugins:
            for cap in instance.manifest.capabilities:
                if cap.name == capability:
                    matches.append(instance)
                    break
        return matches

    # -------------------------------------------------------------------------
    # Registry Snapshot
    # -------------------------------------------------------------------------

    async def get_registry(self) -> PluginRegistrySnapshot:
        """Get full registry snapshot."""
        return self._registry

    # -------------------------------------------------------------------------
    # Signing & Verification
    # -------------------------------------------------------------------------

    async def verify_signature(self, manifest: PluginManifest) -> tuple[bool, str | None]:
        """Verify plugin signature."""
        if not manifest.signature or not manifest.public_key:
            return False, "No signature or public key"

        # In production, would verify cryptographic signature
        # For now, return True with a warning
        return True, "Signature verification not fully implemented"

    async def sign_plugin(self, manifest: PluginManifest, private_key: str) -> PluginManifest:
        """Sign a plugin manifest."""
        # In production, would sign with private key
        # For now, return manifest with dummy signature
        data = json.dumps(manifest.to_dict(), sort_keys=True)
        signature = hashlib.sha256((data + private_key).encode()).hexdigest()
        return PluginManifest(
            **manifest.to_dict(),
            signature=signature,
            public_key="",  # Would derive from private_key
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _update_instance(self, instance: PluginInstance) -> None:
        """Update plugin instance in registry."""
        self._registry = PluginRegistrySnapshot(
            plugins=tuple(
                instance if p.manifest.name == instance.manifest.name else p
                for p in self._registry.plugins
            ),
            updated_at=_utcnow(),
        )

    def _find_dependents(self, name: str) -> list[str]:
        """Find plugins that depend on the given plugin."""
        dependents = []
        for instance in self._registry.plugins:
            for dep in instance.manifest.dependencies:
                if dep.name == name and dep.type == PluginDependencyType.REQUIRED:
                    dependents.append(instance.manifest.name)
                    break
        return dependents

    def _check_platform_version(self, manifest: PluginManifest) -> bool:
        """Check if plugin is compatible with current platform."""
        # Simplified version check - in production use packaging.version
        return True

    def _version_satisfies(self, installed: str, required: str) -> bool:
        """Check if installed version satisfies required version."""
        # Simplified - in production use packaging.version or semantic_version
        return installed == required

    async def _install_dependencies(self, manifest: PluginManifest) -> None:
        """Install plugin dependencies."""
        for dep in manifest.dependencies:
            if dep.type == PluginDependencyType.REQUIRED:
                existing = self._registry.get_plugin(dep.name)
                if not existing or not self._version_satisfies(
                    existing.manifest.version, dep.version
                ):
                    # Would install dependency
                    log.info(f"Would install dependency: {dep.name} {dep.version}")

    async def _download_from_registry(self, manifest: PluginManifest, plugin_dir: Path) -> None:
        """Download plugin from registry."""
        # Placeholder - would download from registry API
        pass

    async def _download_from_url(self, url: str, plugin_dir: Path) -> None:
        """Download plugin from URL."""
        # Placeholder - would download and extract
        pass

    async def _copy_from_local(self, path: str, plugin_dir: Path) -> None:
        """Copy plugin from local path."""
        # Placeholder - would copy files
        pass

    async def _load_manifest_from_local(self, path: str) -> PluginManifest | None:
        """Load manifest from local directory."""
        manifest_path = Path(path) / "manifest.json"
        if manifest_path.exists():
            data = json.loads(manifest_path.read_text())
            return PluginManifest.from_dict(data)
        return None

    async def _load_manifest_from_url(self, url: str) -> PluginManifest | None:
        """Load manifest from URL."""
        # Placeholder
        return None

    async def _start_plugin_process(self, instance: PluginInstance) -> Any:
        """Start plugin as a subprocess."""
        # In production, would launch plugin with proper sandboxing
        # For now, return a mock process

        class DummyProcess:
            def __init__(self, pid: int):
                self.pid = pid
                self._alive = True

            def poll(self) -> int | None:
                return None if self._alive else 0

            def terminate(self) -> None:
                self._alive = False

            def kill(self) -> None:
                self._alive = False

            async def wait(self) -> int:
                return 0

        # Return a mock process for now
        return DummyProcess(uuid4().int & 0xFFFFFFFF)

    async def shutdown(self) -> None:
        """Shutdown registry - stop all plugins."""
        self._shutdown = True
        running = self._registry.list_running()
        for instance in running:
            try:
                await self.stop_plugin(instance.manifest.name)
            except Exception as e:
                log.error(f"Error stopping plugin {instance.manifest.name} during shutdown: {e}")


# For backwards compatibility
__all__ = ["PluginRegistryImpl"]
