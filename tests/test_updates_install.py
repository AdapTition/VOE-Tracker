import json
from pathlib import Path

from voe_explorer.install import install_self, install_target, is_transient_location
from voe_explorer.updates import UpdateInfo, cached_update, check_latest, parse_version

ENV = {"TEMP": r"C:\Users\u\AppData\Local\Temp", "TMP": r"C:\Users\u\AppData\Local\Temp",
       "USERPROFILE": r"C:\Users\u", "LOCALAPPDATA": r"C:\Users\u\AppData\Local"}


def test_parse_version():
    assert parse_version("v0.2.0") == (0, 2, 0) and parse_version("1.10") == (1, 10)


def test_newer_version_detected():
    calls = []

    def fetch(url):
        calls.append(url)
        return json.dumps({"tag_name": "v0.2.0", "html_url": "https://x"})

    assert check_latest("me/voe-explorer-releases", "0.1.0", fetch) == UpdateInfo("0.2.0", "https://x")
    assert calls == ["https://api.github.com/repos/me/voe-explorer-releases/releases/latest"]
    assert check_latest("me/r", "0.2.0", fetch) is None


def test_no_repo_or_no_network_is_silent():
    def boom(url):
        raise AssertionError("must not fetch")

    assert check_latest("", "0.1.0", boom) is None
    assert check_latest("me/r", "0.1.0", lambda url: None) is None
    assert check_latest("me/r", "0.1.0", lambda url: "not json") is None


def test_transient_locations():
    assert is_transient_location(Path(r"C:\Users\u\AppData\Local\Temp\Temp1_VOE.zip\VOE Explorer.exe"), ENV)
    assert is_transient_location(Path(r"C:\Users\u\Downloads\VOE Explorer.exe"), ENV)
    assert not is_transient_location(Path(r"C:\Users\u\AppData\Local\VOE Explorer\VOE Explorer.exe"), ENV)
    assert not is_transient_location(Path(r"C:\Users\u\Desktop\VOE Explorer.exe"), ENV)


def test_install_target():
    assert install_target(ENV) == Path(r"C:\Users\u\AppData\Local\VOE Explorer\VOE Explorer.exe")


def test_install_self_copies_and_creates_shortcut(tmp_path):
    exe = tmp_path / "dl" / "VOE Explorer.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ fake")
    env = {"LOCALAPPDATA": str(tmp_path / "local")}
    commands = []
    target = install_self(exe, env, commands.append)
    assert target.read_bytes() == b"MZ fake"
    assert len(commands) == 1 and commands[0][0] == "powershell"
    script = commands[0][-1]
    assert "CreateShortcut" in script and "VOE Explorer.lnk" in script and str(target) in script


class _Mem(dict):
    def put(self, key, value):
        self[key] = value


def test_same_day_cache_ignores_version_already_installed():
    mem = _Mem()
    fetch = lambda url: json.dumps({"tag_name": "v0.2.0", "html_url": "https://x"})
    assert cached_update(mem, "me/r", "0.1.0", "2026-10-17", fetch) == {"version": "0.2.0", "url": "https://x"}
    # user installs 0.2.0 the same day: the cached 0.2.0 is not newer, no banner, no refetch
    no_fetch = lambda url: (_ for _ in ()).throw(AssertionError("must not fetch"))
    assert cached_update(mem, "me/r", "0.2.0", "2026-10-17", no_fetch) is None
    # next day: fetched again
    assert cached_update(mem, "me/r", "0.2.0", "2026-10-18", fetch) is None
