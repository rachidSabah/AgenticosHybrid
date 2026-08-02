"""Tests for SubprocessManager — spawn/kill, signal handling, status transitions."""

import asyncio
import sys

import pytest

from agentic_os.core.runtime.runtime_process import (
    ProcessStatus,
    SubprocessHandle,
    SubprocessManager,
)


@pytest.fixture
def proc_mgr() -> SubprocessManager:
    return SubprocessManager()


@pytest.mark.asyncio
class TestSubprocessManager:
    async def test_spawn_basic(self, proc_mgr: SubprocessManager) -> None:
        handle = await proc_mgr.spawn(
            name="echo",
            command=sys.executable,
            args=["-c", "print('hello')"],
        )
        assert handle.pid > 0
        assert handle.name == "echo"
        assert handle.status == ProcessStatus.RUNNING

    async def test_spawn_with_env(self, proc_mgr: SubprocessManager) -> None:
        handle = await proc_mgr.spawn(
            name="env-check",
            command=sys.executable,
            args=["-c", "import os; print(os.environ.get('TEST_VAR', 'no'))"],
            env={"TEST_VAR": "yes"},
        )
        assert handle.pid > 0
        await handle.process.wait() if handle.process else None

    async def test_spawn_with_cwd(self, proc_mgr: SubprocessManager, tmp_path) -> None:
        handle = await proc_mgr.spawn(
            name="cwd-check",
            command=sys.executable,
            args=["-c", "import os; print(os.getcwd())"],
            cwd=str(tmp_path),
        )
        assert handle.pid > 0
        if handle.process:
            stdout, _ = await handle.process.communicate()
            assert str(tmp_path) in stdout.decode()

    async def test_spawn_nonexistent_raises(self, proc_mgr: SubprocessManager) -> None:
        with pytest.raises(FileNotFoundError):
            await proc_mgr.spawn(name="bad", command="/nonexistent/cmd")

    async def test_get_handle(self, proc_mgr: SubprocessManager) -> None:
        handle = await proc_mgr.spawn(
            name="get-me",
            command=sys.executable,
            args=["-c", "print('hi')"],
        )
        gotten = await proc_mgr.get_handle(handle.pid)
        assert gotten is not None
        assert gotten.pid == handle.pid

    async def test_get_handle_unknown(self, proc_mgr: SubprocessManager) -> None:
        assert await proc_mgr.get_handle(999999) is None

    async def test_get_status(self, proc_mgr: SubprocessManager) -> None:
        handle = await proc_mgr.spawn(
            name="status-check",
            command=sys.executable,
            args=["-c", "print('ok')"],
        )
        status = await proc_mgr.get_status(handle.pid)
        assert status in (ProcessStatus.RUNNING, ProcessStatus.STOPPED)

    async def test_get_status_unknown(self, proc_mgr: SubprocessManager) -> None:
        status = await proc_mgr.get_status(999999)
        assert status == ProcessStatus.UNKNOWN

    async def test_kill_by_pid(self, proc_mgr: SubprocessManager) -> None:
        handle = await proc_mgr.spawn(
            name="kill-me",
            command=sys.executable,
            args=["-c", "import time; time.sleep(30)"],
        )
        result = await proc_mgr.kill(handle.pid, "SIGKILL")
        assert result is True
        status = await proc_mgr.get_status(handle.pid)
        assert status == ProcessStatus.STOPPED

    async def test_kill_unknown_pid(self, proc_mgr: SubprocessManager) -> None:
        result = await proc_mgr.kill(999999)
        assert result is False

    async def test_kill_already_stopped(self, proc_mgr: SubprocessManager) -> None:
        handle = await proc_mgr.spawn(
            name="quick-exit",
            command=sys.executable,
            args=["-c", "print('bye')"],
        )
        if handle.process:
            await handle.process.wait()
        result = await proc_mgr.kill(handle.pid, "SIGKILL")
        assert result is True  # already stopped is ok

    async def test_terminate(self, proc_mgr: SubprocessManager) -> None:
        handle = await proc_mgr.spawn(
            name="term-me",
            command=sys.executable,
            args=["-c", "import time; time.sleep(30)"],
        )
        result = await proc_mgr.terminate(handle.pid)
        assert result is True

    async def test_terminate_all(self, proc_mgr: SubprocessManager) -> None:
        h1 = await proc_mgr.spawn(
            name="ta1",
            command=sys.executable,
            args=["-c", "import time; time.sleep(30)"],
        )
        h2 = await proc_mgr.spawn(
            name="ta2",
            command=sys.executable,
            args=["-c", "import time; time.sleep(30)"],
        )
        await proc_mgr.terminate_all()
        assert (await proc_mgr.get_status(h1.pid)) == ProcessStatus.STOPPED
        assert (await proc_mgr.get_status(h2.pid)) == ProcessStatus.STOPPED

    async def test_list_handles(self, proc_mgr: SubprocessManager) -> None:
        await proc_mgr.spawn(
            name="list-a",
            command=sys.executable,
            args=["-c", "print('a')"],
        )
        await proc_mgr.spawn(
            name="list-b",
            command=sys.executable,
            args=["-c", "print('b')"],
        )
        handles = await proc_mgr.list_handles()
        assert len(handles) == 2

    async def test_list_by_name(self, proc_mgr: SubprocessManager) -> None:
        await proc_mgr.spawn(
            name="grouped",
            command=sys.executable,
            args=["-c", "print('1')"],
        )
        await proc_mgr.spawn(
            name="grouped",
            command=sys.executable,
            args=["-c", "print('2')"],
        )
        handles = await proc_mgr.list_by_name("grouped")
        assert len(handles) == 2

    async def test_remove(self, proc_mgr: SubprocessManager) -> None:
        handle = await proc_mgr.spawn(
            name="remove-me",
            command=sys.executable,
            args=["-c", "print('bye')"],
        )
        if handle.process:
            await handle.process.wait()
        result = await proc_mgr.remove(handle.pid)
        assert result is True
        assert await proc_mgr.get_handle(handle.pid) is None

    async def test_remove_unknown(self, proc_mgr: SubprocessManager) -> None:
        assert await proc_mgr.remove(999999) is False

    async def test_subprocess_handle_properties(self) -> None:
        handle = SubprocessHandle(pid=123, name="test", command="echo")
        assert handle.running is True
        assert handle.status == ProcessStatus.RUNNING
        handle.status = ProcessStatus.STOPPED
        assert handle.running is False
        assert handle.uptime >= 0

    async def test_wait_returns_exit_code(self, proc_mgr: SubprocessManager) -> None:
        handle = await proc_mgr.spawn(
            name="wait-test",
            command=sys.executable,
            args=["-c", "exit(42)"],
        )
        code = await proc_mgr.wait(handle.pid, timeout=10)
        assert code == 42

    async def test_wait_nonexistent(self, proc_mgr: SubprocessManager) -> None:
        code = await proc_mgr.wait(999999)
        assert code is None

    async def test_concurrent_spawn(self, proc_mgr: SubprocessManager) -> None:
        async def spawn_one(i: int) -> SubprocessHandle:
            return await proc_mgr.spawn(
                name=f"concurrent-{i}",
                command=sys.executable,
                args=["-c", "print('x')"],
            )

        handles = await asyncio.gather(*[spawn_one(i) for i in range(5)])
        assert len(handles) == 5
        assert all(h.pid > 0 for h in handles)
