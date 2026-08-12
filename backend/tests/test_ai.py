from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cinevoice import ai


@pytest.mark.parametrize(
    ("compensate_delay", "expected_delay_flag"),
    [(True, None), (False, "--no-delay-compensation")],
)
def test_python_cli_uses_supported_delay_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    compensate_delay: bool,
    expected_delay_flag: str | None,
) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    commands: list[list[str]] = []

    monkeypatch.setattr(ai, "find_deepfilter", lambda: "/opt/bin/deepFilter")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        output_dir = Path(command[command.index("--output-dir") + 1])
        (output_dir / "source_DeepFilterNet3.wav").write_bytes(b"enhanced")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(ai.subprocess, "run", fake_run)

    result, temporary = ai.run_deepfilter(
        source,
        mode="auto",
        compensate_delay=compensate_delay,
        post_filter=True,
    )
    try:
        command = commands[0]
        assert result.output_path is not None
        assert result.output_path.read_bytes() == b"enhanced"
        assert "--compensate-delay" not in command
        if expected_delay_flag:
            assert expected_delay_flag in command
        else:
            assert "--no-delay-compensation" not in command
        assert "--pf" in command
    finally:
        temporary.cleanup()


def test_find_deepfilter_discovers_active_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "deepFilter"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)

    monkeypatch.delenv("CINEVOICE_DEEPFILTER_PATH", raising=False)
    monkeypatch.setattr(ai.sys, "executable", str(tmp_path / "python"))
    monkeypatch.setattr(ai.shutil, "which", lambda _: None)
    ai.find_deepfilter.cache_clear()
    try:
        assert ai.find_deepfilter() == str(executable)
    finally:
        ai.find_deepfilter.cache_clear()


def test_find_deepfilter_rejects_a_broken_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = tmp_path / "deepFilter"
    broken.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    broken.chmod(0o755)

    monkeypatch.setenv("CINEVOICE_DEEPFILTER_PATH", str(broken))
    monkeypatch.setattr(ai.sys, "executable", str(tmp_path / "python"))
    monkeypatch.setattr(ai.shutil, "which", lambda _: None)
    ai.find_deepfilter.cache_clear()
    try:
        assert ai.find_deepfilter() is None
    finally:
        ai.find_deepfilter.cache_clear()
