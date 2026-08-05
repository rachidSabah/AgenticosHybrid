"""Selector-safe subprocess runner for provider adapters.

``cli.py`` forces the WindowsSelectorEventLoop policy on Windows because the
default Proactor loop has known stability bugs with concurrent subprocess
pipe I/O (silent process crashes). The Selector loop, however, does NOT
implement ``asyncio.create_subprocess_exec`` — it raises
``NotImplementedError``. Every provider adapter that shelled out to a CLI
agent (opencode, gemini, agy, claude, hermes, ...) therefore failed on every
task under ``agentic_os serve`` on Windows.

This module runs subprocesses in a worker thread (``asyncio.to_thread`` +
``subprocess``) and bridges stdout/stderr lines back to the event loop,
preserving the streaming ``on_output`` callback semantics of the previous
asyncio implementation. It is loop-policy agnostic: it works under both the
Selector and Proactor policies.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any

# Sentinel pushed onto the output queue when the pump thread has finished
# (process exited AND both reader threads have drained their pipes).
_DONE = object()


def _kill_tree(proc: subprocess.Popen) -> None:
    """Terminate the process and, on Windows, its whole child tree.

    ``Popen.kill()`` only terminates the direct process; on Windows child
    processes (e.g. a CLI that spawns a sub-tool) keep running and can hold
    the stdout/stderr pipes open, which would leave the reader threads
    blocked. ``taskkill /F /T`` forcibly terminates the entire tree.
    """
    try:
        proc.kill()
    except OSError:
        pass
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


async def run_cli(
    args: Sequence[str],
    *,
    input_data: bytes | None = None,
    env: Mapping[str, str] | None = None,
    cwd: str | None = None,
    timeout: float = 300.0,
    on_output: Callable[[str, str], Any] | None = None,
) -> tuple[int, bytes, bytes]:
    """Run *args* in a worker thread. Returns ``(returncode, stdout, stderr)``.

    Raises ``TimeoutError`` when *timeout* expires (matching the semantics of
    the previous asyncio-based implementation), and ``RuntimeError`` when the
    binary cannot be started.

    When *on_output* is provided it is awaited for each decoded
    stdout/stderr line as it arrives (line, stream) — errors raised by the
    callback are swallowed so output pumping can never crash execution.
    """
    if on_output is None:
        return await _run_simple(args, input_data=input_data, env=env, cwd=cwd, timeout=timeout)
    return await _run_streaming(
        args,
        input_data=input_data,
        env=env,
        cwd=cwd,
        timeout=timeout,
        on_output=on_output,
    )


async def _run_simple(
    args: Sequence[str],
    *,
    input_data: bytes | None,
    env: Mapping[str, str] | None,
    cwd: str | None,
    timeout: float,
) -> tuple[int, bytes, bytes]:
    """Non-streaming path: Popen + communicate in a worker thread.

    Uses Popen (not ``subprocess.run``) so a timeout can terminate the whole
    process tree — ``subprocess.run`` only kills the direct child, which on
    Windows leaves grandchildren (e.g. a tool spawned by a CLI wrapper)
    running and holding the pipes open.
    """

    def _run() -> tuple[int, bytes, bytes]:
        try:
            proc = subprocess.Popen(
                list(args),
                stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=dict(env) if env is not None else None,
                cwd=cwd,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"failed to start {args[0]}: {exc}") from None
        try:
            stdout, stderr = proc.communicate(input=input_data, timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            raise TimeoutError(f"timed out after {timeout}s") from None
        return proc.returncode, stdout, stderr

    return await asyncio.to_thread(_run)


async def _run_streaming(
    args: Sequence[str],
    *,
    input_data: bytes | None,
    env: Mapping[str, str] | None,
    cwd: str | None,
    timeout: float,
    on_output: Callable[[str, str], Any],
) -> tuple[int, bytes, bytes]:
    """Streaming path: Popen in a worker thread, lines bridged to the loop."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    stdout_store: list[bytes] = []
    stderr_store: list[bytes] = []

    def _pump() -> tuple[int, bytes, bytes]:
        try:
            proc = subprocess.Popen(
                list(args),
                stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=dict(env) if env is not None else None,
                cwd=cwd,
            )
        except FileNotFoundError as exc:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)
            raise RuntimeError(f"failed to start {args[0]}: {exc}") from None

        if input_data is not None:
            try:
                assert proc.stdin is not None
                proc.stdin.write(input_data)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        def _read(stream: Any, name: str, store: list[bytes]) -> None:
            try:
                for raw in iter(stream.readline, b""):
                    if not raw:
                        break
                    store.append(raw)
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    if line:
                        loop.call_soon_threadsafe(queue.put_nowait, (line, name))
            except Exception:
                pass

        readers = [
            threading.Thread(target=_read, args=(proc.stdout, "stdout", stdout_store), daemon=True),
            threading.Thread(target=_read, args=(proc.stderr, "stderr", stderr_store), daemon=True),
        ]
        for t in readers:
            t.start()
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            # Queue the sentinel BEFORE joining so the drain side can finish
            # as soon as the tree is dead; joins below are a bounded cleanup.
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)
            for t in readers:
                t.join(timeout=3)
            raise TimeoutError(f"timed out after {timeout}s") from None
        for t in readers:
            t.join(timeout=5)
        loop.call_soon_threadsafe(queue.put_nowait, _DONE)
        return returncode, b"".join(stdout_store), b"".join(stderr_store)

    async def _drain() -> None:
        while True:
            item = await queue.get()
            if item is _DONE:
                return
            line, name = item
            try:
                await on_output(line, name)
            except Exception:
                pass  # callback errors must not crash execution

    pump_task = asyncio.create_task(asyncio.to_thread(_pump))
    drain_task = asyncio.create_task(_drain())
    try:
        result = await pump_task
    finally:
        await drain_task
    return result
