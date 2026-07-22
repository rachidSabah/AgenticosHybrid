"""
Plugin Loader

Dynamic import, sandboxing, and capability extraction for plugins.
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime
import importlib
import importlib.util
import inspect
import json
import pathlib
import types
import typing
import uuid
from pathlib import Path
from typing import Any

from agentic_os.domain.plugin import (
    PluginCapability,
    PluginInstance,
    PluginManifest,
)
from agentic_os.infrastructure.logging import get_logger

log = get_logger("plugin.loader")


class PluginSandbox:
    """Sandbox for running plugins with restricted permissions."""

    def __init__(
        self,
        plugin_dir: Path,
        memory_limit_mb: int | None = None,
        cpu_limit_percent: int | None = None,
        timeout_seconds: int = 30,
    ):
        self.plugin_dir = plugin_dir
        self.memory_limit_mb = memory_limit_mb
        self.cpu_limit_percent = cpu_limit_percent
        self.timeout_seconds = timeout_seconds
        self._modules: dict[str, types.ModuleType] = {}
        self._globals: dict[str, Any] = {}

    def create_environment(self) -> dict[str, Any]:
        """Create a restricted execution environment."""
        # Build restricted builtins
        safe_builtins = {
            "print": print,
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "frozenset": frozenset,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sum": sum,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            "sorted": sorted,
            "reversed": reversed,
            "any": any,
            "all": all,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "hasattr": hasattr,
            "getattr": getattr,
            "setattr": setattr,
            "delattr": delattr,
            "type": type,
            "object": object,
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "AttributeError": AttributeError,
            "RuntimeError": RuntimeError,
            "NotImplementedError": NotImplementedError,
            "json": json,
            "datetime": datetime,
            "pathlib": pathlib,
            "typing": typing,
            "dataclasses": dataclasses,
            "uuid": uuid,
        }

        return {
            "__builtins__": safe_builtins,
            "PLUGIN_DIR": str(self.plugin_dir),
            "plugin_api": self._create_plugin_api(),
        }

    def _create_plugin_api(self) -> dict[str, Any]:
        """Create the plugin API exposed to sandboxed code."""
        return {
            "register_capability": self._register_capability,
            "get_config": self._get_config,
            "set_config": self._set_config,
            "emit_event": self._emit_event,
            "log": self._plugin_log,
        }

    def _register_capability(self, name: str, description: str, **schemas: Any) -> None:
        """Register a capability from within the plugin."""
        self._globals.setdefault("_capabilities", []).append(
            PluginCapability(
                name=name,
                description=description,
                input_schema=schemas.get("input_schema", {}),
                output_schema=schemas.get("output_schema", {}),
                tags=schemas.get("tags", ()),
            )
        )

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self._globals.get("_config", {}).get(key, default)

    def _set_config(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        self._globals.setdefault("_config", {})[key] = value

    def _emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Emit an event to the host."""
        self._globals.setdefault("_events", []).append({"type": event_type, "payload": payload})

    def _plugin_log(self, level: str, message: str) -> None:
        """Log from plugin."""
        levels = {"debug": log.debug, "info": log.info, "warning": log.warning, "error": log.error}
        levels.get(level, log.info)(f"[plugin] {message}")

    def get_capabilities(self) -> list[PluginCapability]:
        """Get capabilities registered by the plugin."""
        return self._globals.get("_capabilities", [])

    def get_events(self) -> list[dict[str, Any]]:
        """Get events emitted by the plugin."""
        return self._globals.get("_events", [])


class PluginLoader:
    """
    Loads and manages plugin execution.

    Handles:
    - Dynamic import of plugin modules
    - Sandbox execution
    - Capability extraction
    - Lifecycle management
    """

    def __init__(self, sandbox: PluginSandbox | None = None):
        self.sandbox = sandbox
        self._loaded_modules: dict[str, types.ModuleType] = {}
        self._plugin_instances: dict[str, Any] = {}

    async def load_plugin(self, instance: PluginInstance) -> dict[str, Any]:
        """
        Load a plugin from its install directory.

        Returns metadata including capabilities and entry points.
        """
        plugin_dir = Path(instance.path)
        if not plugin_dir.exists():
            raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")

        # Find entry point
        entry_point = instance.manifest.entry_point or "plugin.py"
        entry_path = plugin_dir / entry_point

        if not entry_path.exists():
            raise FileNotFoundError(f"Entry point not found: {entry_path}")

        # Load the module
        module = await self._load_module(entry_path, instance.manifest.name)
        self._loaded_modules[instance.manifest.name] = module

        # Extract capabilities
        capabilities = self._extract_capabilities(module, instance.manifest)

        # Create plugin instance if it has a class
        plugin_class = self._find_plugin_class(module)
        if plugin_class:
            plugin_obj = await self._instantiate_plugin(plugin_class, instance)
            self._plugin_instances[instance.manifest.name] = plugin_obj

        return {
            "capabilities": capabilities,
            "entry_point": entry_point,
            "module": module.__name__,
            "has_class": plugin_class is not None,
        }

    async def _load_module(self, path: Path, name: str) -> types.ModuleType:
        """Dynamically load a Python module."""
        spec = importlib.util.spec_from_file_location(name, path)
        if not spec or not spec.loader:
            raise ImportError(f"Could not load module from {path}")

        module = importlib.util.module_from_spec(spec)

        # Execute in sandbox if provided
        if self.sandbox:
            env = self.sandbox.create_environment()
            code = path.read_text()
            exec(compile(code, str(path), "exec"), env)
            # Copy defined objects to module
            for key, value in env.items():
                if not key.startswith("_"):
                    setattr(module, key, value)
        else:
            spec.loader.exec_module(module)

        return module

    def _extract_capabilities(
        self, module: types.ModuleType, manifest: PluginManifest
    ) -> list[PluginCapability]:
        """Extract capabilities from module and manifest."""
        capabilities = list(manifest.capabilities)

        # Also check for @capability decorators
        for name in dir(module):
            obj = getattr(module, name)
            if hasattr(obj, "_plugin_capability"):
                cap_info = obj._plugin_capability
                capabilities.append(
                    PluginCapability(
                        name=cap_info.get("name", name),
                        description=cap_info.get("description", ""),
                        input_schema=cap_info.get("input_schema", {}),
                        output_schema=cap_info.get("output_schema", {}),
                        tags=cap_info.get("tags", ()),
                    )
                )

        return capabilities

    def _find_plugin_class(self, module: types.ModuleType) -> type | None:
        """Find the main plugin class in the module."""
        for name in dir(module):
            obj = getattr(module, name)
            if inspect.isclass(obj) and hasattr(obj, "_plugin_main"):
                return obj
        return None

    async def _instantiate_plugin(self, plugin_class: type, instance: PluginInstance) -> Any:
        """Instantiate a plugin class with its configuration."""
        config = instance.config

        # Check if class has async init
        if hasattr(plugin_class, "ainit"):
            obj = plugin_class(config=config)
            await obj.ainit()
        else:
            obj = plugin_class(config=config)

        return obj

    async def call_capability(
        self,
        instance: PluginInstance,
        capability_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call a plugin capability."""
        plugin_obj = self._plugin_instances.get(instance.manifest.name)
        if not plugin_obj:
            raise RuntimeError(f"Plugin {instance.manifest.name} not loaded")

        # Check if capability exists
        if hasattr(plugin_obj, capability_name):
            method = getattr(plugin_obj, capability_name)
            if asyncio.iscoroutinefunction(method):
                return await method(**arguments)
            else:
                return method(**arguments)

        raise AttributeError(f"Capability {capability_name} not found on plugin")

    async def start_plugin(self, instance: PluginInstance) -> None:
        """Start a plugin (call its start method if exists)."""
        plugin_obj = self._plugin_instances.get(instance.manifest.name)
        if plugin_obj and hasattr(plugin_obj, "start"):
            if asyncio.iscoroutinefunction(plugin_obj.start):
                await plugin_obj.start()
            else:
                plugin_obj.start()

    async def stop_plugin(self, instance: PluginInstance) -> None:
        """Stop a plugin (call its stop method if exists)."""
        plugin_obj = self._plugin_instances.get(instance.manifest.name)
        if plugin_obj and hasattr(plugin_obj, "stop"):
            if asyncio.iscoroutinefunction(plugin_obj.stop):
                await plugin_obj.stop()
            else:
                plugin_obj.stop()

    async def unload_plugin(self, name: str) -> None:
        """Unload a plugin completely."""
        if name in self._plugin_instances:
            plugin_obj = self._plugin_instances[name]
            if hasattr(plugin_obj, "cleanup"):
                if asyncio.iscoroutinefunction(plugin_obj.cleanup):
                    await plugin_obj.cleanup()
                else:
                    plugin_obj.cleanup()
            del self._plugin_instances[name]

        if name in self._loaded_modules:
            del self._loaded_modules[name]


# Decorators for plugin authors
def capability(
    name: str,
    description: str,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    tags: list[str] | None = None,
):
    """Decorator to mark a method as a plugin capability."""

    def decorator(func):
        func._plugin_capability = {
            "name": name,
            "description": description,
            "input_schema": input_schema or {},
            "output_schema": output_schema or {},
            "tags": tuple(tags or []),
        }
        return func

    return decorator


def plugin_main(cls):
    """Decorator to mark a class as the main plugin class."""
    cls._plugin_main = True
    return cls


def plugin_config(schema: dict[str, Any]):
    """Decorator to define plugin configuration schema."""

    def decorator(cls):
        cls._plugin_config_schema = schema
        return cls

    return decorator


__all__ = [
    "PluginSandbox",
    "PluginLoader",
    "capability",
    "plugin_main",
    "plugin_config",
]
