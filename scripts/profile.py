#!/usr/bin/env python3
"""profile.py — resolve the Chrome user-data-dir (the browser profile).

OPERATOR DIRECTIVE (2026-10-05): keep the browser profile from being wiped
by sandbox resets. Observed reset classes remove, among others:
  - /home/z/replay2 (this checkout) — the LEGACY profile location
    (scripts/browser-profile) died with every reset, forcing the operator
    to re-login through the replay image each time;
  - ~/.aise, ~/.secrets, ~/.bashrc, ~/.git-credentials (home dotfiles are
    restored to the provision baseline);
  - additions inside provision dotdirs (~/.local/share/*, ~/.agent-browser/*
    are restored AWAY — proven reset-18);
  - gitignored paths under /home/z/my-project (git clean -X class: the
    local-vault.env experiment died — proven reset-18).
What SURVIVES every observed reset class: VISIBLE, UNIGNORED files under
/home/z/my-project (the platform app: worklog.md, tool-results/, the ported
console src — all survived resets 15-18). Hence the default profile location
is a visible unignored directory inside the platform app:

    /home/z/my-project/browser-profile

Env override: REPLAY_PROFILE_DIR (exported by deploy.sh when set, honored
here) — stations that find a better durable path can redirect without
touching code. LEGACY scripts/browser-profile is AUTO-MIGRATED (moved) on
first resolve, so an existing login session survives the upgrade. Never
store the profile inside this repository.
"""
import os
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
LEGACY = os.path.join(BASE, "browser-profile")
DEFAULT = "/home/z/my-project/browser-profile"


def _has_content(p):
    try:
        return any(os.scandir(p))
    except OSError:
        return False


def resolve():
    """Return the durable profile dir, migrating legacy content if needed."""
    path = os.environ.get("REPLAY_PROFILE_DIR", "").strip() or DEFAULT
    if os.path.isdir(LEGACY):
        try:
            if not os.path.exists(path):
                # fresh durable location: move the whole legacy profile
                os.makedirs(os.path.dirname(path), exist_ok=True)
                shutil.move(LEGACY, path)
                print(f"[profile] legacy profile migrated -> {path}", file=sys.stderr)
            elif not _has_content(path):
                # durable exists but empty (a prior resolve pre-created it):
                # move legacy CONTENT in, then drop the empty legacy dir
                for entry in os.listdir(LEGACY):
                    shutil.move(os.path.join(LEGACY, entry), os.path.join(path, entry))
                os.rmdir(LEGACY)
                print(f"[profile] legacy profile content merged -> {path}", file=sys.stderr)
            # else: durable already has content — it wins (never clobber a
            # newer login with an older legacy profile)
        except Exception as e:  # cross-device move / partial state
            print(f"[profile] WARN: migration failed ({e}); keeping legacy", file=sys.stderr)
            return LEGACY
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        print(f"[profile] FATAL: cannot create {path} ({e})", file=sys.stderr)
        raise
    return path


if __name__ == "__main__":
    print(resolve())
