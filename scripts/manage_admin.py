#!/usr/bin/env python3
"""Offline management for LearnAnything system administrators."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.user_manager import UserManager


def _manager(base_dir: str = None) -> UserManager:
    return UserManager(Path(base_dir).resolve()) if base_dir else UserManager()


def _find_user(manager: UserManager, username: str) -> dict:
    user = manager.get_user_by_username(username)
    if not user:
        raise ValueError(f"User does not exist: {username}")
    if user["user_id"] in ("default", "anonymous"):
        raise ValueError("Passwordless local users cannot be system administrators")
    return user


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List, promote, or demote LearnAnything system administrators."
    )
    parser.add_argument("--base-dir", help="Override the LearnAnything data directory")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List users and system roles")
    for command in ("promote", "demote"):
        sub = subparsers.add_parser(command)
        sub.add_argument("username")
    args = parser.parse_args()

    manager = _manager(args.base_dir)
    if args.command == "list":
        for user in manager.list_users():
            print(f"{user['username']}\t{user['user_id']}\t{user['system_role']}")
        return 0

    try:
        user = _find_user(manager, args.username)
        role = "admin" if args.command == "promote" else "user"
        manager.set_system_role(user["user_id"], role)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"{args.username}: system_role={role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
