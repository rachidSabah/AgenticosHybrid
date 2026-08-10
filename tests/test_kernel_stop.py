"""Regression test: Kernel.stop() must shut down cleanly even when the
Phase 15-18 controllers were never initialized (background startup skipped
or failed partway).

Previously the shutdown path referenced ``self.persistent_controller`` etc.
which were only assigned deep inside ``_start_subsystems``, so calling
``stop()`` on a freshly-constructed kernel raised ``AttributeError`` and the
backend could not be torn down cleanly.
"""

from __future__ import annotations

import pytest

from agentic_os.kernel import Kernel


@pytest.mark.asyncio
async def test_stop_on_fresh_kernel_does_not_raise():
    """A kernel that never ran background startup must still stop cleanly."""
    kernel = Kernel()
    # No _start_critical / _start_subsystems were awaited, so the Phase 15-18
    # controller attributes were never assigned. stop() must tolerate that.
    await kernel.stop()


@pytest.mark.asyncio
async def test_stop_clears_controller_attributes():
    """stop() must reset the optional controllers to None (idempotent)."""
    kernel = Kernel()
    await kernel.stop()
    for attr in (
        "ecosystem_controller",
        "cluster_controller",
        "evolution_controller",
        "distributed_controller",
        "persistent_controller",
    ):
        assert getattr(kernel, attr) is None
