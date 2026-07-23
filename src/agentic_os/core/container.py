"""Typed Dependency Injection Container — Kernel v2 foundation.

A fully-typed DI container with Singleton, Transient, and Scoped lifetimes.
Supports interface-based registration, named aliases, factory functions,
instance injection, dependency declarations, and cycle detection.

Usage:
    container = Container()
    container.register(EventBus, build_bus, singleton=True)
    container.register(ProviderManager, ProviderManagerImpl, depends_on=[EventBus])

    bus = container.resolve(EventBus)  # returns EventBus singleton
    pm = container.resolve(ProviderManager)  # resolves EventBus first, then constructs
"""

from __future__ import annotations

import inspect
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any, Generic, TypeVar, get_type_hints

T = TypeVar("T")
InterfaceT = TypeVar("InterfaceT")


class Lifetime(Enum):
    """Service lifetime — controls when and how instances are created/reused."""

    SINGLETON = auto()  # One instance for the lifetime of the container
    TRANSIENT = auto()  # New instance on every resolve
    SCOPED = auto()  # One instance per resolve scope (scope = container branch)


class RegistrationStatus(Enum):
    """Internal status of a registered service."""

    REGISTERED = auto()
    RESOLVING = auto()  # Currently being resolved (cycle detection)
    RESOLVED = auto()
    FAILED = auto()


@dataclass
class Registration(Generic[T]):
    """Metadata and factory for a single registered service."""

    interface: type[T]
    factory: Callable[..., T] | type[T]
    lifetime: Lifetime = Lifetime.SINGLETON
    name: str | None = None
    depends_on: list[type] | None = None
    singleton_instance: T | None = field(default=None, repr=False)
    status: RegistrationStatus = RegistrationStatus.REGISTERED
    resolving_in: set[int] = field(default_factory=set, repr=False)  # resolve chain IDs
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    description: str | None = None
    tags: set[str] = field(default_factory=set)

    @property
    def key(self) -> str:
        if self.name:
            return f"{self.interface.__name__}:{self.name}"
        return self.interface.__name__


class ContainerError(Exception):
    """Base container exception."""


class CyclicDependencyError(ContainerError):
    """Raised when a cycle is detected during resolution."""


class MissingDependencyError(ContainerError):
    """Raised when a required dependency is not registered."""


class DuplicateRegistrationError(ContainerError):
    """Raised when the same type is registered twice."""


class ResolutionError(ContainerError):
    """Raised when a service cannot be resolved."""


class Container:
    """Typed DI Container — thread-safe, generic, with lifetime management.

    Thread safety: uses a per-container RLock so nested resolves from the
    same thread work safely while blocking concurrent modifications.
    """

    def __init__(self, parent: Container | None = None) -> None:
        self._parent = parent
        self._registrations: dict[str, Registration[Any]] = {}
        self._singletons: dict[str, Any] = {}
        self._scoped: dict[str, Any] = {}
        self._aliases: dict[str, str] = {}
        self._lock = threading.RLock()
        self._resolve_counter = 0
        self._started = False

    # ── Registration ──

    def register(
        self,
        interface: type[T],
        factory: Callable[..., T] | type[T] | T,
        *,
        singleton: bool = True,
        lifetime: Lifetime | None = None,
        name: str | None = None,
        depends_on: list[type] | None = None,
        description: str | None = None,
        tags: set[str] | None = None,
    ) -> Registration[T]:
        """Register a service against its interface type.

        Args:
            interface: The type/Protocol to register against.
            factory: A callable that produces T, a type (auto-instantiated), or
                     an instance (stored as singleton).
            singleton: If True (default), stores as SINGLETON lifetime.
            lifetime: Explicit Lifetime. Overrides ``singleton`` if set.
            name: Optional name for named registrations (multiple impls).
            depends_on: List of types this service depends on.
            description: Human-readable description of the service.
            tags: Set of string tags for categorization/filtering.

        Raises:
            DuplicateRegistrationError: If the interface+name pair is already registered.
        """
        resolved_lifetime = lifetime or (Lifetime.SINGLETON if singleton else Lifetime.TRANSIENT)

        if callable(factory):
            resolved_factory: Callable[..., T] | type[T] = factory  # type: ignore[assignment]
        else:
            # An instance was passed directly — store as singleton factory
            resolved_factory = lambda: factory  # type: ignore[assignment]
            resolved_lifetime = Lifetime.SINGLETON

        reg: Registration[Any] = Registration(
            interface=interface,
            factory=resolved_factory,
            lifetime=resolved_lifetime,
            name=name,
            depends_on=depends_on,
            description=description,
            tags=tags or set(),
        )

        with self._lock:
            key = reg.key
            if key in self._registrations:
                existing = self._registrations[key]
                if not (name and existing.name == name):
                    raise DuplicateRegistrationError(
                        f"Duplicate registration for {key}. "
                        f"Use name= to register multiple implementations."
                    )
            self._registrations[key] = reg

        return reg

    def register_instance(
        self,
        interface: type[T],
        instance: T,
        *,
        name: str | None = None,
        description: str | None = None,
        tags: set[str] | None = None,
    ) -> Registration[T]:
        """Register an existing instance as a singleton service."""
        return self.register(
            interface,
            instance,
            singleton=True,
            name=name,
            description=description,
            tags=tags,
        )

    def alias(self, alias: str, target_key: str) -> None:
        """Create a named alias pointing to an existing registration key."""
        with self._lock:
            if target_key not in self._registrations:
                raise MissingDependencyError(
                    f"Cannot alias '{alias}' -> '{target_key}': target not registered"
                )
            self._aliases[alias] = target_key

    # ── Resolution ──

    def resolve(self, interface: type[T], *, name: str | None = None) -> T:
        """Resolve a service by its interface type.

        Args:
            interface: The type to resolve.
            name: Optional name for named registrations.

        Returns:
            An instance of T.

        Raises:
            MissingDependencyError: If no registration exists.
            CyclicDependencyError: If a cycle is detected.
            ResolutionError: If the factory raised during construction.
        """
        key = self._resolve_key(interface, name)
        with self._lock:
            self._resolve_counter += 1
            resolve_id = self._resolve_counter
            return self._resolve(key, resolve_id, visited=None)

    def try_resolve(self, interface: type[T], *, name: str | None = None) -> T | None:
        """Resolve a service, returning None if not registered."""
        try:
            return self.resolve(interface, name=name)
        except (MissingDependencyError, CyclicDependencyError, ResolutionError):
            return None

    def resolve_all(self, interface: type[T]) -> list[T]:
        """Resolve all named registrations for an interface type.

        Returns:
            A list of all instances registered under ``interface``, including
            the unnamed (default) registration.
        """
        results: list[T] = []
        with self._lock:
            for key, reg in self._registrations.items():
                if reg.interface is interface or key.startswith(f"{interface.__name__}:"):
                    self._resolve_counter += 1
                    try:
                        instance = self._resolve(key, self._resolve_counter, None)
                        results.append(instance)
                    except (MissingDependencyError, CyclicDependencyError, ResolutionError):
                        continue
        return results

    def list_registrations(self) -> list[Registration[Any]]:
        """Return all registrations for introspection."""
        with self._lock:
            return list(self._registrations.values())

    # ── Scope Management ──

    def create_scope(self) -> Container:
        """Create a child scope. Scoped services are resolved once per scope."""
        return Container(parent=self)

    def clear_scoped(self) -> None:
        """Clear all scoped instances. Called at scope end."""
        with self._lock:
            self._scoped.clear()

    # ── Internal Resolution ──

    def _resolve_key(self, interface: type[T], name: str | None) -> str:
        key = f"{interface.__name__}:{name}" if name else interface.__name__
        with self._lock:
            if key not in self._registrations:
                # Check aliases
                if key in self._aliases:
                    return self._aliases[key]
                # Check parent
                if self._parent:
                    return self._parent._resolve_key(interface, name)
            return key

    def _resolve(self, key: str, resolve_id: int, visited: set[str] | None) -> Any:
        """Internal resolve with cycle detection."""
        if visited is None:
            visited = set()

        # Check this container first
        reg = self._registrations.get(key)

        # Fall back to parent
        if reg is None and self._parent:
            return self._parent._resolve(key, resolve_id, visited)

        if reg is None:
            raise MissingDependencyError(f"No registration found for '{key}'")

        # ── Cycle Detection ──
        if key in visited:
            cycle_path = " -> ".join(list(visited) + [key])
            raise CyclicDependencyError(
                f"Cyclic dependency detected: {cycle_path}"
            )

        if resolve_id in reg.resolving_in:
            cycle_parts = [k for k, ids in self._registrations.items() if resolve_id in ids.resolving_in]
            raise CyclicDependencyError(
                f"Cyclic dependency detected resolving '{key}' "
                f"(resolve chain {resolve_id}): {' -> '.join(cycle_parts + [key])}"
            )

        # ── Singleton Cache ──
        if reg.lifetime == Lifetime.SINGLETON:
            if key in self._singletons:
                return self._singletons[key]
            # Check parent singleton
            if self._parent and key in self._parent._singletons:
                return self._parent._singletons[key]

        # ── Scoped Cache ──
        if reg.lifetime == Lifetime.SCOPED:
            if key in self._scoped:
                return self._scoped[key]

        # ── Resolve Dependencies ──
        visited.add(key)
        reg.resolving_in.add(resolve_id)

        try:
            deps = reg.depends_on or []
            resolved_deps: dict[str, Any] = {}

            if deps:
                hints = {}
                try:
                    hints = get_type_hints(reg.factory)
                except (TypeError, NameError, AttributeError):
                    pass

                for dep_type in deps:
                    dep_key = dep_type.__name__
                    resolved_deps[dep_key] = self._resolve(
                        dep_key, resolve_id, visited
                    )

            # ── Construct ──
            instance: Any

            if isinstance(reg.factory, type):
                # Factory is a class — try to match constructor params
                sig = inspect.signature(reg.factory.__init__)
                params = {}
                for p_name, p_param in sig.parameters.items():
                    if p_name == "self":
                        continue
                    # Try to find param type
                    if p_name in resolved_deps:
                        params[p_name] = resolved_deps[p_name]
                    elif p_param.default is not inspect.Parameter.empty:
                        params[p_name] = p_param.default
                    else:
                        # Check type hints for known types
                        if p_name in hints:
                            hint_type = hints[p_name]
                            hint_key = hint_type.__name__
                            try:
                                params[p_name] = self._resolve(
                                    hint_key, resolve_id, visited
                                )
                            except MissingDependencyError:
                                if p_param.default is not inspect.Parameter.empty:
                                    params[p_name] = p_param.default
                instance = reg.factory(**params)
            else:
                # Factory is a callable
                sig = inspect.signature(reg.factory)
                params = {}
                for p_name, p_param in sig.parameters.items():
                    if p_name in resolved_deps:
                        params[p_name] = resolved_deps[p_name]
                    elif p_param.default is not inspect.Parameter.empty:
                        params[p_name] = p_param.default
                    elif p_name in hints:
                        hint_type = hints[p_name]
                        hint_key = hint_type.__name__
                        try:
                            params[p_name] = self._resolve(
                                hint_key, resolve_id, visited
                            )
                        except MissingDependencyError:
                            if p_param.default is not inspect.Parameter.empty:
                                params[p_name] = p_param.default
                instance = reg.factory(**params)

        except CyclicDependencyError:
            raise
        except Exception as exc:
            reg.status = RegistrationStatus.FAILED
            raise ResolutionError(
                f"Failed to resolve '{key}': {exc}"
            ) from exc
        finally:
            reg.resolving_in.discard(resolve_id)
            visited.discard(key)

        # Cache
        if reg.lifetime == Lifetime.SINGLETON:
            self._singletons[key] = instance
            reg.singleton_instance = instance
            reg.status = RegistrationStatus.RESOLVED
        elif reg.lifetime == Lifetime.SCOPED:
            self._scoped[key] = instance

        return instance

    # ── Health & Inspection ──

    def is_registered(self, interface: type, *, name: str | None = None) -> bool:
        """Check if a service type is registered."""
        key = f"{interface.__name__}:{name}" if name else interface.__name__
        with self._lock:
            return key in self._registrations or (
                self._parent is not None and self._parent.is_registered(interface, name=name)
            )

    def get_registration(self, interface: type, *, name: str | None = None) -> Registration | None:
        """Get the Registration metadata for a service type."""
        key = f"{interface.__name__}:{name}" if name else interface.__name__
        with self._lock:
            reg = self._registrations.get(key)
            if reg is None and self._parent:
                return self._parent.get_registration(interface, name=name)
            return reg

    @property
    def registration_count(self) -> int:
        """Number of registered services."""
        with self._lock:
            return len(self._registrations)

    @property
    def singleton_count(self) -> int:
        """Number of resolved singletons."""
        with self._lock:
            return len(self._singletons)

    def reset(self) -> None:
        """Clear all registrations and singletons. For testing."""
        with self._lock:
            self._registrations.clear()
            self._singletons.clear()
            self._scoped.clear()
            self._aliases.clear()
            self._started = False

    def dependency_graph(self) -> dict[str, list[str]]:
        """Return the dependency graph as a dict of key → dependency keys."""
        graph: dict[str, list[str]] = {}
        with self._lock:
            for key, reg in self._registrations.items():
                deps: list[str] = []
                for dep_type in reg.depends_on or []:
                    deps.append(dep_type.__name__)
                graph[key] = deps
        return graph

    def __repr__(self) -> str:
        with self._lock:
            count = len(self._registrations)
        return f"Container({count} registrations, {self.singleton_count} resolved)"
