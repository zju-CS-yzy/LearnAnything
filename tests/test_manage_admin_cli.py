import sys

from core.user_manager import UserManager
from scripts import manage_admin


def _run_cli(monkeypatch, base_dir, *arguments):
    monkeypatch.setattr(
        sys,
        "argv",
        ["manage_admin.py", "--base-dir", str(base_dir), *arguments],
    )
    return manage_admin.main()


def test_cli_can_list_promote_and_demote_users(tmp_path, monkeypatch, capsys):
    data_dir = tmp_path / "data"
    manager = UserManager(data_dir)
    alice = manager.create_user("alice", "alice-pass")
    bob = manager.create_user("bob", "bob-pass")

    assert _run_cli(monkeypatch, data_dir, "promote", "alice") == 0
    assert _run_cli(monkeypatch, data_dir, "promote", "bob") == 0
    assert _run_cli(monkeypatch, data_dir, "demote", "alice") == 0
    assert manager.get_system_role(alice["user_id"]) == "user"
    assert manager.get_system_role(bob["user_id"]) == "admin"

    capsys.readouterr()
    assert _run_cli(monkeypatch, data_dir, "list") == 0
    output = capsys.readouterr().out
    assert f"alice\t{alice['user_id']}\tuser" in output
    assert f"bob\t{bob['user_id']}\tadmin" in output


def test_cli_rejects_passwordless_and_last_admin_changes(
    tmp_path, monkeypatch, capsys
):
    data_dir = tmp_path / "data"
    manager = UserManager(data_dir)
    manager.create_user("alice", "alice-pass")

    assert _run_cli(monkeypatch, data_dir, "promote", "default") == 1
    assert "Passwordless local users" in capsys.readouterr().err

    assert _run_cli(monkeypatch, data_dir, "promote", "alice") == 0
    capsys.readouterr()
    assert _run_cli(monkeypatch, data_dir, "demote", "alice") == 1
    assert "last system administrator" in capsys.readouterr().err
