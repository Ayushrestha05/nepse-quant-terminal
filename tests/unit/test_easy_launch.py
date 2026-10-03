from pathlib import Path

from scripts.launch import bootstrap


def test_supported_python_range():
    assert bootstrap.is_supported_python((3, 10, 0))
    assert bootstrap.is_supported_python((3, 12, 4))
    assert bootstrap.is_supported_python((3, 13, 9))
    assert not bootstrap.is_supported_python((3, 9, 18))
    assert not bootstrap.is_supported_python((3, 14, 0))


def test_requirements_hash_changes_with_file_content(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text("textual\n", encoding="utf-8")
    first = bootstrap.requirements_hash(path)
    path.write_text("textual\nrich\n", encoding="utf-8")
    second = bootstrap.requirements_hash(path)

    assert first != second


def test_venv_python_path_is_platform_specific(monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap.os, "name", "nt")
    assert bootstrap.venv_python(tmp_path) == tmp_path / ".venv" / "Scripts" / "python.exe"

    monkeypatch.setattr(bootstrap.os, "name", "posix")
    assert bootstrap.venv_python(tmp_path) == tmp_path / ".venv" / "bin" / "python"


def test_linux_runtime_prefers_a_supported_existing_venv(monkeypatch, tmp_path):
    project_python = tmp_path / ".venv" / "bin" / "python"
    project_python.parent.mkdir(parents=True)
    project_python.touch()
    monkeypatch.setattr(bootstrap, "_python_is_supported", lambda _python: True)

    python, venv_dir = bootstrap.select_linux_runtime(tmp_path)

    assert python == project_python
    assert venv_dir == ".venv"


def test_linux_runtime_falls_back_to_supported_system_python(monkeypatch, tmp_path):
    project_python = tmp_path / ".venv" / "bin" / "python"
    project_python.parent.mkdir(parents=True)
    project_python.touch()
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(bootstrap, "_python_is_supported", lambda python: str(python).endswith("python3.12"))

    python, venv_dir = bootstrap.select_linux_runtime(tmp_path)

    assert str(python) == "/usr/bin/python3.12"
    assert venv_dir == ".venv-linux"


def test_linux_applications_dir_honors_only_absolute_xdg_data_home(tmp_path):
    assert bootstrap.linux_applications_dir({"XDG_DATA_HOME": "/custom/data"}) == Path("/custom/data/applications")
    assert bootstrap.linux_applications_dir({"XDG_DATA_HOME": "relative"}, tmp_path) == tmp_path / ".local/share/applications"


def test_desktop_exec_quote_escapes_desktop_syntax():
    assert bootstrap.desktop_exec_quote('/tmp/A % "Q"/Launch\\Quant.sh') == '"/tmp/A %% \\"Q\\"/Launch\\\\Quant.sh"'


def test_launch_propagates_dashboard_exit_code(monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *_args, **_kwargs: type("Result", (), {"returncode": 23})())

    assert bootstrap.launch_dashboard(tmp_path, Path("python"), terminal=True) == 23


def test_linux_shortcut_install_is_valid_and_idempotent(tmp_path):
    root = tmp_path / "repo with spaces"
    root.mkdir()
    launcher = root / "Launch Quant Terminal.sh"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    applications = tmp_path / "menus with spaces"

    first = bootstrap.install_linux_shortcut(root, applications)
    contents = first.read_text(encoding="utf-8")
    second = bootstrap.install_linux_shortcut(root, applications)

    assert first == second
    assert first.read_text(encoding="utf-8") == contents
    assert f'Exec="{launcher}"' in contents
    assert f"Path={root}" in contents
    assert "Terminal=true" in contents
