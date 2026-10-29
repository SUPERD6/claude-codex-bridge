"""A hub config that does not parse is no longer silent: stderr says which file, where and what to do, `ccx doctor`
shows it, and ccx writes the hub path so that it reads back on Windows too."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from ccx import config, doctor


@pytest.fixture
def user_cfg(tmp_path, monkeypatch):
    monkeypatch.delenv("CCX_HUB", raising=False)
    monkeypatch.setattr(config, "_WARNED", set())
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return config.user_config_file()


def test_broken_config_warns_on_stderr_with_place_and_hint(user_cfg, capsys):
    user_cfg.write_text('hub = "C:\\Users\\x\\hub"\n', encoding="utf-8")    # \U... is a bad escape in TOML
    assert config.hub_dir() == Path.home() / ".ccx-hub"                     # falls back, as before
    err = capsys.readouterr().err
    assert str(user_cfg) in err and "line 1" in err and "column" in err
    assert "single quotes" in err and "ccx doctor" in err
    config.hub_dir()
    assert capsys.readouterr().err == ""                                    # once per process, not on every call


def test_broken_layout_names_file_line_and_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "_WARNED", set())
    lay = tmp_path / "ccx" / "layout.toml"
    lay.parent.mkdir(parents=True)
    lay.write_text('[layout]\nskills = "a\n', encoding="utf-8")
    with pytest.raises(ValueError) as e:
        config.load_layout(tmp_path)
    for text in (str(e.value), capsys.readouterr().err):
        assert str(lay) in text and "line 2" in text and "single quotes" in text


@pytest.mark.parametrize("path", ["C:\\Users\\x\\new hub", "/home/x/hub", "D:\\it's\\here"])
def test_save_hub_reads_back_exactly(user_cfg, path):
    f = config.save_hub(Path(path))
    assert tomllib.loads(f.read_text(encoding="utf-8"))["hub"] == str(Path(path))
    if "'" not in path:
        assert f"hub = '{Path(path)}'" in f.read_text(encoding="utf-8")       # a literal string: no escapes


def test_doctor_config_row(user_cfg, tmp_path):
    p = config.Paths(tmp_path / "hub")
    assert doctor.config_row(p)[0] == "ok"                                  # no file: defaults
    user_cfg.parent.mkdir(parents=True, exist_ok=True)
    user_cfg.write_text("hub = 'C:/x/hub'\n", encoding="utf-8")
    assert doctor.config_row(p)[0] == "ok"
    user_cfg.write_text('hub = "C:\\new\\tmp"\n', encoding="utf-8")         # parses: \n and \t became controls
    state, detail = doctor.config_row(p)
    assert state == "WARN" and "hub" in detail and "single quotes" in detail
    user_cfg.write_text('hub = "C:\\Users\\hub"\n', encoding="utf-8")
    state, detail = doctor.config_row(p)
    assert state == "FAIL" and str(user_cfg) in detail and "line 1" in detail


def test_doctor_shows_the_config_row(user_cfg, tmp_path, capsys):
    user_cfg.parent.mkdir(parents=True, exist_ok=True)
    user_cfg.write_text('hub = "C:\\Users\\hub"\n', encoding="utf-8")
    doctor.doctor(config.Paths(tmp_path / "hub"))
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if "ccx config" in ln)
    assert "FAIL" in line


def test_doctor_with_a_broken_layout_still_prints_the_table(user_cfg, tmp_path, capsys):
    lay = tmp_path / "hub" / "ccx" / "layout.toml"
    lay.parent.mkdir(parents=True)
    lay.write_text('[layout]\nskills = "a\n', encoding="utf-8")
    assert doctor.doctor(config.Paths(tmp_path / "hub")) is False
    out = capsys.readouterr().out
    assert "FAIL" in next(ln for ln in out.splitlines() if ln.startswith("ccx config"))
    assert "FAIL" in next(ln for ln in out.splitlines() if ln.startswith("hub layout"))
    assert "Claude SessionStart hook" in out and "has agent-delegate" in out  # the rest of the table is there
