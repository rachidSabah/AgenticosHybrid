"""Shared, Selector-policy-safe subprocess runner.

Under ``asyncio.WindowsSelectorEventLoopPolicy`` (forced in
:mod:`agentic_os.cli`), ``asyncio.create_subprocess_exec`` raises
``NotImplementedError`` immediately. This module runs subprocesses via
``subprocess.Popen`` inside ``asyncio.to_thread`` so it works under
that policy without crashing the event loop.

Key design decisions:

* **No asyncio subprocess APIs.** Everything goes through
  ``subprocess.Popen``.
* **Tree-kill on timeout.** On Windows, ``proc.kill()`` only kills the
  top-level shell (``cmd.exe`` for ``.cmd`` shims) and leaves
  grandchild processes (``node.exe``, ``python.exe``) alive. They keep
  the stdout/stderr pipes open, causing ``proc.wait()`` to stall for
  up to 29 seconds. ``taskkill /F /T /PID <pid>`` kills the entire
  process tree.
* **Streaming via threads + queue.** Reader threads put lines on a
  ``queue.Queue``. The ``_DONE`` sentinel is queued **before** the
  reader threads are joined so joins never stall.
"""

from __future__ import annotations

import asyncio
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Callable

_DONE = object()


def _kill_tree(pid: int) -> None:
    """Kill the entire process tree rooted at *pid*.

    On Windows, uses ``taskkill /F /T /PID <pid>`` which recursively
    kills all descendants. On POSIX, sends SIGKILL to the process group.
    """
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass
    else:
        try:
            os.killpg(os.getpgid(pid), 9)
        except Exception:
            try:
                os.kill(pid, 9)
            except Exception:
                pass


def _run_sync(
    args: list[str],
    input_data: bytes | None,
    env: dict,
    cwd: str | None,
    timeout: float,
    on_output: Callable[[str, str], None] | None,
) -> tuple[int, bytes, bytes]:
    """Synchronous subprocess runner (called via ``asyncio.to_thread``).

    Returns ``(returncode, stdout, stderr)``. On timeout, returns
    ``(-999, b"", b"<timeout marker>")``.
    """
    stdin = subprocess.PIPE if input_data is not None else subprocess.DEVNULL

    if on_output is not None:
        # Streaming mode: spawn reader threads that put lines on a queue.
        proc = subprocess.Popen(
            args,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
        )

        out_q: queue.Queue[tuple[str, str] | object] = queue.Queue()
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []

        def _reader(pipe, stream_name: str, store: list[bytes]) -> None:
            try:
                for line in iter(pipe.readline, b""):
                    store.append(line)
                    try:
                        out_q.put(
                            (line.decode("utf-8", errors="replace").rstrip("\n\r"), stream_name)
                        )
                    except Exception:
                        pass
            finally:
                pipe.close()
                out_q.put(_DONE)

        t_out = threading.Thread(
            target=_reader, args=(proc.stdout, "stdout", stdout_chunks), daemon=True
        )
        t_err = threading.Thread(
            target=_reader, args=(proc.stderr, "stderr", stderr_chunks), daemon=True
        )
        t_out.start()
        t_err.start()

        # Feed stdin
        if input_data is not None and proc.stdin is not None:
            try:
                proc.stdin.write(input_data)
                proc.stdin.close()
            except Exception:
                pass

        # Wait for process with timeout
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc.pid)
            # Bounded joins — reader threads will exit after pipes close
            out_q.put(_DONE)
            t_out.join(timeout=3)
            t_err.join(timeout=3)
            return (
                -999,
                b"",
                b"<timeout: process killed after {timeout}s>".replace(
                    b"{timeout}", str(timeout).encode()
                ),
            )

        # Drain queue — sentinel must be queued BEFORE joining reader threads
        done_count = 0
        expected_done = 2  # stdout reader + stderr reader
        while done_count < expected_done:
            try:
                item = out_q.get(timeout=5)
            except queue.Empty:
                break
            if item is _DONE:
                done_count += 1
            elif on_output is not None:
                line_str, stream_name = item  # type: ignore[assignment, misc]  # ty: ignore[not-iterable]
                try:
                    on_output(line_str, stream_name)
                except Exception:
                    pass

        # Join reader threads (they should have exited by now)
        t_out.join(timeout=3)
        t_err.join(timeout=3)

        stdout = b"".join(stdout_chunks)
        stderr = b"".join(stderr_chunks)
        return proc.returncode or 0, stdout, stderr

    else:
        # Non-streaming mode: use capture_output semantics
        try:
            result = subprocess.run(
                args,
                input=input_data,
                capture_output=True,
                env=env,
                cwd=cwd,
                timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            # Popen path already killed; just return timeout marker
            return (
                -999,
                b"",
                b"<timeout: process killed after {timeout}s>".replace(
                    b"{timeout}", str(timeout).encode()
                ),
            )


async def run_cli(
    args: list[str],
    *,
    input_data: bytes | None = None,
    env: dict | None = None,
    cwd: str | None = None,
    timeout: float = 120.0,
    on_output: Callable[[str, str], None] | None = None,
) -> tuple[int, str, str]:
    """Run a CLI subprocess safely under any asyncio event loop policy.

    Args:
        args: Command and arguments (e.g. ``["claude", "-p", "--output-format", "text"]``).
        input_data: Optional stdin payload.
        env: Environment dict (defaults to ``os.environ``).
        cwd: Working directory for the subprocess.
        timeout: Timeout in seconds.
        on_output: Optional streaming callback ``(line, stream_name)``.

    Returns:
        ``(returncode, stdout_str, stderr_str)``.

    On timeout, returncode is ``-999`` and stderr contains a timeout marker.
    """
    final_env = env if env is not None else dict(os.environ)

    rc, stdout_bytes, stderr_bytes = await asyncio.to_thread(
        _run_sync,
        args,
        input_data,
        final_env,
        cwd,
        timeout,
        on_output,
    )

    stdout_str = stdout_bytes.decode("utf-8", errors="replace")
    stderr_str = stderr_bytes.decode("utf-8", errors="replace")
    return rc, stdout_str, stderr_str
