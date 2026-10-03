#!/usr/bin/env bash
# send_packet.sh — SAFE dispatch wrapper (D-031 dispatch law).
# Usage: send_packet.sh <TXXX> [create|send] [message-file-for-send]
# Sources replay-state/env.sh FIRST and HARD-FAILS unless the PAT env var is
# live — a dispatch_worker run without it sends the LITERAL
# [REDACTED:github_token] placeholder to the worker (T041 incident,
# 2026-10-03: worker completed 45 files but push 401'd; T035 same, caught
# pre-admission). _subst_pat only substitutes from the ENVIRONMENT.
# Rebuilt verbatim 2026-10-03 after reset-4 rolled the tree back.
set -euo pipefail
NAME="${1:?usage: send_packet.sh <TXXX> [create|send] [msg-file]}"
MODE="${2:-create}"
MY=/home/z/my-project
SCRIPTS=/home/z/replay2/scripts
# shellcheck disable=SC1091
source "$MY/replay-state/env.sh"
if [ -z "${GITHUB_OPERATOR_PAT:-}" ]; then
  echo "FATAL: GITHUB_OPERATOR_PAT not in env after sourcing env.sh — refusing to dispatch (placeholder would leak to worker)" >&2
  exit 1
fi
cd "$SCRIPTS"
if [ "$MODE" = "create" ]; then
  python3 stage_packet.py "$NAME"
  exec python3 dispatch_worker.py create "$NAME" "flags/pkt_${NAME}_staged.md"
elif [ "$MODE" = "send" ]; then
  MSG="${3:?send mode needs a message file}"
  exec python3 dispatch_worker.py send "$NAME" "@$MSG"
else
  echo "FATAL: unknown mode $MODE" >&2; exit 1
fi
