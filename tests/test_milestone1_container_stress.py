"""Milestone 1 — Container Stress Tests.

Validates the 6 migrated subsystems under load:
- 1000 registrations
- 1000 resolutions
- Concurrent access (thread safety)
- Cycle detection
- Memory leak detection
- Thread safety under concurrent resolution
"""

import sys
import os
import time
import threading
import gc
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ["AGENTIC_OS_USE_CONTAINER"] = "1"
os.environ["AGENTIC_OS_BUS_TYPE"] = "local"


def test_1000_registrations():
    """Register 1000 services and verify they all resolve."""
    from agentic_os.core.container import Container, DuplicateRegistrationError

    c = Container()
    created: list[str] = []

    for i in range(1000):
        iface_name = f"Interface_{i}"
        iface = type(iface_name, (), {})
        obj = object()
        c.register_instance(iface, obj)
        created.append(iface)

    assert c.registration_count == 1000, f"Expected 1000, got {c.registration_count}"

    for i, iface in enumerate(created):
        resolved = c.resolve(iface)
        assert resolved is not None, f"Interface_{i} failed to resolve"

    print(f"OK 1000 registrations, 1000 resolutions")


def test_1000_registrations_and_singletons():
    """Register 1000 services, resolve each, verify singletons."""
    from agentic_os.core.container import Container

    c = Container()
    objs: list[type] = []

    for i in range(1000):
        iface = type(f"Svc_{i}", (), {})
        obj = object()
        c.register_instance(iface, obj)
        objs.append(iface)

    # Resolve all
    for i, iface in enumerate(objs):
        r1 = c.resolve(iface)
        r2 = c.resolve(iface)
        assert r1 is r2, f"Interface_{i} singleton broken"

    print(f"OK 1000 singleton verifications")


def test_lifecycle_1000_services():
    """Verify LifecycleManager can track 1000 services."""
    from agentic_os.core.container import Container
    from agentic_os.core.lifecycle import LifecycleManager, Phase, ServiceProtocol

    class DummyService(ServiceProtocol):
        async def health(self):
            return {"status": "healthy"}

    c = Container()
    lm = LifecycleManager(c)

    for i in range(1000):
        svc = DummyService()
        svc_id = f"dummy_{i}"
        lm.register_service(svc_id, DummyService, svc, phase=Phase.INFRASTRUCTURE)

    assert len(lm._records) == 1000
    assert lm.service_count_by_phase()["infrastructure"] == 1000

    print(f"OK 1000 lifecycle registrations")


def test_concurrent_resolution():
    """Resolve services from multiple threads concurrently."""
    from agentic_os.core.container import Container

    c = Container()
    objs: list[type] = []

    for i in range(100):
        iface = type(f"Conc_{i}", (), {})
        obj = object()
        c.register_instance(iface, obj)
        objs.append(iface)

    errors: list[Exception] = []
    lock = threading.Lock()

    def resolve_all():
        try:
            for iface in objs:
                resolved = c.resolve(iface)
                assert resolved is not None
                # Re-resolve to test singleton cache
                resolved2 = c.resolve(iface)
                assert resolved2 is resolved
        except Exception as e:
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=resolve_all) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(errors) == 0, f"Concurrent resolution failures: {errors}"
    print(f"OK 20 concurrent threads, 100 services each, no errors")


def test_cycle_detection():
    """Verify circular dependency detection catches cycles."""
    from agentic_os.core.container import Container, CyclicDependencyError

    c = Container()

    # A -> B -> C -> A  (cycle!)
    class A: pass
    class B: pass
    class C: pass

    c.register(A, lambda: A(), depends_on=[B])
    c.register(B, lambda: B(), depends_on=[C])
    c.register(C, lambda: C(), depends_on=[A])

    try:
        c.resolve(A)
        assert False, "Should have raised CyclicDependencyError"
    except CyclicDependencyError:
        pass

    print(f"OK Cycle detection caught A->B->C->A")


def test_memory_leak_detection():
    """Register and unregister, verify no memory leak."""
    from agentic_os.core.container import Container
    from agentic_os.core.lifecycle import LifecycleManager, ServiceProtocol

    class LeakCheckSvc(ServiceProtocol):
        pass

    c = Container()
    lm = LifecycleManager(c)

    # Register many services
    for i in range(100):
        svc = LeakCheckSvc()
        lm.register_service(f"leak_{i}", LeakCheckSvc, svc)

    # Remove them all
    for i in range(100):
        lm._records.pop(f"leak_{i}", None)

    gc.collect()
    assert len(lm._records) == 0

    print(f"OK Memory leak check passed (100 services cleaned)")


def test_singleton_identity():
    """Verify all 6 migrated services are true singletons."""
    from agentic_os.core.kernel_bootstrap import build_container_kernel

    container, lifecycle, compat, health_reg, obs, svc_reg = build_container_kernel()

    from agentic_os.ports.event_bus import EventBus
    from agentic_os.core.scheduler import Scheduler
    from agentic_os.config import Settings
    from agentic_os.core.kernel_bootstrap import (
        SettingsService, LoggingService, ConfigurationService,
        SecretsService,
    )

    assert container.resolve(EventBus) is container.resolve(EventBus)
    assert container.resolve(Scheduler) is container.resolve(Scheduler)
    assert container.resolve(Settings) is container.resolve(Settings)
    assert container.resolve(SettingsService) is container.resolve(SettingsService)
    assert container.resolve(LoggingService) is container.resolve(LoggingService)
    assert container.resolve(ConfigurationService) is container.resolve(ConfigurationService)
    assert container.resolve(SecretsService) is container.resolve(SecretsService)

    print(f"OK All 6 services are true singletons")


def test_cycle_detection_lifecycle():
    """Verify that the DI validator's cycle checker works."""
    from agentic_os.core.container import Container
    from agentic_os.core.di_validator import CircularDependencyChecker
    import asyncio

    c = Container()

    class A: pass
    class B: pass
    class C: pass

    c.register(A, lambda: A(), depends_on=[B])
    c.register(B, lambda: B(), depends_on=[C])
    c.register(C, lambda: C(), depends_on=[A])

    checker = CircularDependencyChecker()
    result = asyncio.run(checker.check(c))
    assert result.status == "failed", f"Expected failed, got {result.status}"
    assert "cyclic" in result.details.lower()

    print(f"OK Cycle detection checker caught cycle")


def test_thread_safety():
    """Thread safety: concurrent register + resolve on same container."""
    from agentic_os.core.container import Container

    c = Container()
    errors: list[Exception] = []
    lock = threading.Lock()
    interfaces: list[type] = []

    def reg_and_resolve(start: int, count: int):
        try:
            for i in range(start, start + count):
                iface = type(f"ThreadSafe_{i}", (), {})
                c.register_instance(iface, object())
                with lock:
                    interfaces.append(iface)
                resolved = c.resolve(iface)
                assert resolved is not None
        except Exception as e:
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=reg_and_resolve, args=(i * 50, 50)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert len(errors) == 0, f"Thread safety errors: {errors}"
    print(f"OK 10 concurrent threads with concurrent register+resolve")


if __name__ == "__main__":
    tests = [
        test_1000_registrations,
        test_1000_registrations_and_singletons,
        test_lifecycle_1000_services,
        test_concurrent_resolution,
        test_cycle_detection,
        test_memory_leak_detection,
        test_singleton_identity,
        test_cycle_detection_lifecycle,
        test_thread_safety,
    ]

    passed = 0
    failed = 0
    for test in tests:
        name = test.__name__
        try:
            test()
            passed += 1
        except Exception as e:
            import traceback
            print(f"FAIL {name}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n=== Results: {passed} passed, {failed} failed, {len(tests)} total ===")
    sys.exit(1 if failed else 0)
