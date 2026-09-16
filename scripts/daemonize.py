#!/usr/bin/env python3
"""daemonize.py — double-fork launcher that survives parent-session kills.

Usage: daemonize.py <logfile> <cmd> [args...]
"""
import os
import subprocess
import sys


def main():
    logfile = sys.argv[1]
    cmd = sys.argv[2:]
    if not cmd:
        print("usage: daemonize.py <logfile> <cmd> [args...]")
        return 2
    logfile = os.path.abspath(logfile)
    pid = os.fork()
    if pid > 0:
        print(f"daemon parent exiting, child forked ({pid})")
        return 0
    os.setsid()
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)
    os.chdir("/")
    os.umask(0o022)
    fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    if fd > 2:
        os.close(fd)
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    if devnull > 2:
        os.close(devnull)
    os.execvp(cmd[0], cmd)
    return 0  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
