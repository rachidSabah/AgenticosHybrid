"""Conftest for runtime tests — provides event loop cleanup fixtures.

Windows Proactor event loop note:
When asyncio subprocesses are created and not explicitly cleaned up before the
event loop closes, the Proactor IOCP issues pipe close events that can bleed
into the next test's event loop via the Windows kernel pipe handle pool.

This conftest adds a finalizer that cancels pending background tasks and
awaits subprocess termination to prevent cross-test contamination.
"""

from __future__ import annotations

import asyncio
import gc
import sys

import pytest

if sys.platform == "win32":

    @pytest.fixture(autouse=True)
    async def cleanup_subprocess_pipes():
        """On Windows, ensure all pending async tasks are cancelled and
        garbage-collected before the event loop exits, preventing
        ConnectionResetError bleed-through into subsequent tests."""
        yield
        # Cancel all non-current tasks created in this event loop
        loop = asyncio.get_running_loop()
        current = asyncio.current_task()
        tasks = [t for t in asyncio.all_tasks(loop) if t is not current]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        # Force GC to flush __del__ on ProactorBasePipeTransport
        gc.collect()
        # Allow the event loop to process any remaining callbacks
        await asyncio.sleep(0)
