"""Agent package manager — real signed archives, real verification, real replay.

No mocks: packages are real tar.gz archives built from real files on disk;
signatures are real HMAC-SHA256; tamper tests flip real bytes; rollbacks
re-materialize real files and verify their hashes.
"""

from __future__ import annotations

import pytest

from agentic_os.core.packages.agent_packages import AgentPackageManager, PackageError


@pytest.fixture
def pm(tmp_path):
    return AgentPackageManager(data_dir=str(tmp_path / "pkg"))


@pytest.fixture
def source_dir(tmp_path):
    src = tmp_path / "src"
    (src / "skills").mkdir(parents=True)
    (src / "agent.py").write_text("print('agent entrypoint v1')\n", encoding="utf-8")
    (src / "skills" / "search.md").write_text("# search skill\n", encoding="utf-8")
    return src


def _pack_v1(pm, source_dir, out):
    return pm.pack(
        str(source_dir),
        name="demo-agent",
        version="1.0.0",
        entrypoint="agent.py",
        capabilities=["search"],
        out_path=str(out),
    )


# ── pack + verify ────────────────────────────────────────────────────────────


def test_pack_creates_signed_archive_and_verifies(pm, source_dir, tmp_path):
    out = tmp_path / "demo-agent-1.0.0.agent"
    info = _pack_v1(pm, source_dir, out)
    assert out.is_file()
    assert info["files"] == 2
    assert info["algorithm"] == "HMAC-SHA256"
    verdict = pm.verify(str(out))
    assert verdict["ok"] is True
    assert verdict["signature_ok"] is True
    assert verdict["files_checked"] == 2
    assert verdict["problems"] == []


def test_tampered_payload_file_fails_verification_with_exact_file(pm, source_dir, tmp_path):
    out = tmp_path / "tampered.agent"
    _pack_v1(pm, source_dir, out)
    # flip one byte inside the archive's member by repacking a doctored tree
    import io
    import tarfile

    raw = out.read_bytes()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        members = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
    members["agent.py"] = members["agent.py"] + b"# tampered\n"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            import tarfile as tf

            info = tf.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    out.write_bytes(buf.getvalue())
    verdict = pm.verify(str(out))
    assert verdict["ok"] is False
    assert any("agent.py" in p for p in verdict["problems"])


def test_tampered_signature_fails_verification(pm, source_dir, tmp_path):
    import hashlib
    import io
    import json
    import tarfile

    out = tmp_path / "badsig.agent"
    _pack_v1(pm, source_dir, out)
    with tarfile.open(fileobj=io.BytesIO(out.read_bytes()), mode="r:gz") as tar:
        members = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
    manifest = json.loads(members["manifest.json"].decode("utf-8"))
    # a signature from a DIFFERENT key must not verify
    manifest["signature"] = hashlib.sha256(b"attacker-key").hexdigest()
    members["manifest.json"] = json.dumps(manifest).encode("utf-8")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    out.write_bytes(buf.getvalue())
    verdict = pm.verify(str(out))
    assert verdict["ok"] is False
    assert verdict["signature_ok"] is False


def test_unlisted_extra_file_fails_verification(pm, source_dir, tmp_path):
    import io
    import tarfile

    out = tmp_path / "extra.agent"
    _pack_v1(pm, source_dir, out)
    with tarfile.open(fileobj=io.BytesIO(out.read_bytes()), mode="r:gz") as tar:
        members = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
    members["evil.sh"] = b"rm -rf /\n"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    out.write_bytes(buf.getvalue())
    verdict = pm.verify(str(out))
    assert verdict["ok"] is False
    assert any("evil.sh" in p for p in verdict["problems"])


# ── install / upgrade / rollback ─────────────────────────────────────────────


def test_install_materializes_verified_files(pm, source_dir, tmp_path):
    out = tmp_path / "demo.agent"
    _pack_v1(pm, source_dir, out)
    result = pm.install(str(out))
    assert result["installed"] == "demo-agent@1.0.0"
    assert result["verified"] is True
    installed = pm.list_installed()
    assert len(installed) == 1
    assert installed[0]["name"] == "demo-agent"
    assert installed[0]["current"] == "1.0.0"
    assert installed[0]["entrypoint"] == "agent.py"


def test_tampered_package_is_never_installed(pm, source_dir, tmp_path):
    import io
    import tarfile

    out = tmp_path / "evil.agent"
    _pack_v1(pm, source_dir, out)
    with tarfile.open(fileobj=io.BytesIO(out.read_bytes()), mode="r:gz") as tar:
        members = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
    members["agent.py"] += b"# doctored\n"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    out.write_bytes(buf.getvalue())
    with pytest.raises(PackageError) as exc:
        pm.install(str(out))
    assert "NOT installed" in str(exc.value)
    assert pm.list_installed() == []


def test_upgrade_requires_same_name_and_new_version(pm, source_dir, tmp_path):
    v1 = tmp_path / "v1.agent"
    _pack_v1(pm, source_dir, v1)
    pm.install(str(v1))
    # same version again -> refused
    with pytest.raises(PackageError) as exc:
        pm.upgrade(str(v1))
    assert "already installed" in str(exc.value)
    # v2 upgrade works and keeps both versions on disk
    v2src = tmp_path / "src2"
    v2src.mkdir()
    (v2src / "agent.py").write_text("print('agent entrypoint v2')\n", encoding="utf-8")
    v2 = tmp_path / "v2.agent"
    pm.pack(str(v2src), name="demo-agent", version="1.1.0", out_path=str(v2))
    result = pm.upgrade(str(v2))
    assert result["upgraded_from"] == "1.0.0"
    assert result["installed"] == "demo-agent@1.1.0"
    installed = pm.list_installed()[0]
    assert installed["current"] == "1.1.0"
    assert set(installed["versions"]) == {"1.0.0", "1.1.0"}


def test_upgrade_refused_when_not_installed(pm, source_dir, tmp_path):
    out = tmp_path / "never.agent"
    _pack_v1(pm, source_dir, out)
    with pytest.raises(PackageError) as exc:
        pm.upgrade(str(out))
    assert "use install" in str(exc.value)


def test_rollback_replays_previous_checkpoint(pm, source_dir, tmp_path):
    v1 = tmp_path / "v1.agent"
    _pack_v1(pm, source_dir, v1)
    pm.install(str(v1))
    v2src = tmp_path / "src2"
    v2src.mkdir()
    (v2src / "agent.py").write_text("print('v2')\n", encoding="utf-8")
    (v2src / "extra.txt").write_text("v2 extra\n", encoding="utf-8")
    v2 = tmp_path / "v2.agent"
    pm.pack(str(v2src), name="demo-agent", version="1.1.0", out_path=str(v2))
    pm.upgrade(str(v2))
    assert pm.list_installed()[0]["current"] == "1.1.0"

    result = pm.rollback("demo-agent")
    assert result["rolled_back"] == "demo-agent@1.0.0"
    assert result["from_version"] == "1.1.0"
    assert result["verified"] is True
    # current pointer moved back; the restored file content is the v1 content
    assert pm.list_installed()[0]["current"] == "1.0.0"
    root = pm._installed_root("demo-agent") / "1.0.0" / "agent.py"
    assert b"v1" in root.read_bytes()


def test_rollback_without_earlier_version_refused(pm, source_dir, tmp_path):
    out = tmp_path / "only.agent"
    _pack_v1(pm, source_dir, out)
    pm.install(str(out))
    with pytest.raises(PackageError) as exc:
        pm.rollback("demo-agent")
    assert "nothing to roll back to" in str(exc.value)


def test_rollback_detects_corrupted_checkpoint(pm, source_dir, tmp_path):
    v1 = tmp_path / "v1.agent"
    _pack_v1(pm, source_dir, v1)
    pm.install(str(v1))
    v2src = tmp_path / "src2"
    v2src.mkdir()
    (v2src / "agent.py").write_text("print('v2')\n", encoding="utf-8")
    v2 = tmp_path / "v2.agent"
    pm.pack(str(v2src), name="demo-agent", version="1.1.0", out_path=str(v2))
    pm.upgrade(str(v2))
    # corrupt the v1 checkpoint on disk
    v1file = pm._installed_root("demo-agent") / "1.0.0" / "agent.py"
    v1file.write_text("corrupted!\n", encoding="utf-8")
    with pytest.raises(PackageError) as exc:
        pm.rollback("demo-agent")
    assert "did not verify" in str(exc.value)
    # the installed tree is untouched: current stays 1.1.0
    assert pm.list_installed()[0]["current"] == "1.1.0"


# ── journal ──────────────────────────────────────────────────────────────────


def test_journal_records_real_actions(pm, source_dir, tmp_path):
    out = tmp_path / "j.agent"
    _pack_v1(pm, source_dir, out)
    pm.install(str(out))
    actions = [e["action"] for e in pm.journal()]
    assert "pack" in actions
    assert "install" in actions
