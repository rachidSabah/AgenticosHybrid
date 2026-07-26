"""Tests for RuntimeLauncher — process spawning, command resolution, env/cwd."""

import os
import sys

import pytest

from agentic_os.core.runtime.runtime import Runtime
from agentic_os.core.runtime.runtime_launcher import LaunchResult, RuntimeLauncher
from agentic_os.core.runtime.runtime_process import SubprocessManager


@pytest.fixture
def launcher() -> RuntimeLauncher:
    return RuntimeLauncher()


@pytest.mark.asyncio
class TestRuntimeLauncher:
    async def test_launch_basic(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(name="echo", command=sys.executable, arguments=["-c", "print('hello')"])
        result = await launcher.launch(r)
        assert isinstance(result, LaunchResult)
        assert result.pid > 0
        assert result.runtime_id == r.id
        assert result.runtime_name == "echo"

    async def test_launch_with_env(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(
            name="env-test",
            command=sys.executable,
            arguments=["-c", "import os; print(os.environ.get('MY_VAR', 'missing'))"],
            environment={"MY_VAR": "hello_env"},
        )
        result = await launcher.launch(r)
        assert result.pid > 0
        # Wait for process to finish
        handle = await launcher.get_handle(result.pid)
        assert handle is not None
        if handle.process is not None:
            await handle.process.wait()

    async def test_launch_with_cwd(self, launcher: RuntimeLauncher, tmp_path) -> None:
        r = Runtime(
            name="cwd-test",
            command=sys.executable,
            arguments=["-c", "import os; print(os.getcwd())"],
            working_directory=str(tmp_path),
        )
        result = await launcher.launch(r)
        assert result.working_directory == str(tmp_path)
        handle = await launcher.get_handle(result.pid)
        if handle and handle.process:
            await handle.process.wait()

    async def test_launch_empty_command_raises(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(name="no-cmd", command="")
        with pytest.raises(ValueError, match="no command configured"):
            await launcher.launch(r)

    async def test_launch_nonexistent_command_raises(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(name="bad-cmd", command="/nonexistent/binary")
        with pytest.raises(FileNotFoundError):
            await launcher.launch(r)

    async def test_resolve_path_absolute(self, launcher: RuntimeLauncher) -> None:
        resolved = launcher._resolve_path(sys.executable)
        assert os.path.isabs(resolved)

    async def test_resolve_path_simple(self, launcher: RuntimeLauncher) -> None:
        resolved = launcher._resolve_path("python3")
        # Should either find it or return the original
        assert resolved is not None

    async def test_resolve_runtime_command_explicit_binary(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(name="explicit", binary_path=sys.executable)
        resolved = await launcher._resolve_runtime_command(r)
        assert resolved == sys.executable

    async def test_resolve_runtime_command_executable(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(name="exec", executable=sys.executable)
        resolved = await launcher._resolve_runtime_command(r)
        assert resolved == sys.executable

    async def test_resolve_working_directory_explicit(
        self, launcher: RuntimeLauncher, tmp_path
    ) -> None:
        r = Runtime(name="wd", working_directory=str(tmp_path))
        wd = await launcher._resolve_working_directory(r)
        assert wd == str(tmp_path)

    async def test_resolve_working_directory_fallback(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(name="no-wd", binary_path=sys.executable)
        wd = await launcher._resolve_working_directory(r)
        assert wd is not None

    async def test_build_environment_merges(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(name="env-build", environment={"APP_VAR": "app_value"})
        env = launcher._build_environment(r, EXTRA="extra_val")
        assert env["APP_VAR"] == "app_value"
        assert env["EXTRA"] == "extra_val"
        assert "PATH" in env  # from base env

    async def test_launch_then_stop(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(
            name="stop-test",
            command=sys.executable,
            arguments=["-c", "import time; time.sleep(30)"],
        )
        result = await launcher.launch(r)
        assert result.pid > 0
        stopped = await launcher.stop(result.pid, timeout=5)
        assert stopped is True

    async def test_launch_then_kill(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(
            name="kill-test",
            command=sys.executable,
            arguments=["-c", "import time; time.sleep(30)"],
        )
        result = await launcher.launch(r)
        assert result.pid > 0
        killed = await launcher.kill(result.pid)
        assert killed is True

    async def test_is_running(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(
            name="run-check", command=sys.executable, arguments=["-c", "import time; time.sleep(5)"]
        )
        result = await launcher.launch(r)
        running = await launcher.is_running(result.pid)
        assert running is True
        await launcher.kill(result.pid)

    async def test_get_handle_returns_none_for_unknown(self, launcher: RuntimeLauncher) -> None:
        handle = await launcher.get_handle(999999)
        assert handle is None

    async def test_get_children_empty(self, launcher: RuntimeLauncher) -> None:
        children = await launcher.get_children(1)
        assert isinstance(children, list)

    async def test_process_manager_property(self, launcher: RuntimeLauncher) -> None:
        assert isinstance(launcher.process_manager, SubprocessManager)

    async def test_launch_with_extra_env(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(name="extra-env", command=sys.executable, arguments=["-c", "print('ok')"])
        result = await launcher.launch(r, CUSTOM_VAR="custom_val")
        assert result.pid > 0

    async def test_launch_result_to_dict(self, launcher: RuntimeLauncher) -> None:
        r = Runtime(name="dict", command=sys.executable, arguments=["-c", "print('hi')"])
        result = await launcher.launch(r)
        d = result.to_dict()
        assert d["pid"] == result.pid
        assert d["runtime_name"] == "dict"
        assert "launched_at" in d
        assert "platform" in d
