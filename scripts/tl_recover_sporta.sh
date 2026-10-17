#!/usr/bin/env bash
# tl_recover_sporta.sh — DEPRECATED 2026-10-17 (Task 21 poison-kill).
#
# This was the sporta-era ONE-COMMAND recovery script. The operator's
# 2026-10-16 directive fixed the product as payswapdotorg/adcos-2.0 ("not
# zcode, not sporta"), and this script's original content cloned the WRONG
# product repo (payswapdotorg/Sporta-2.0). It is kept ONLY as a delegating
# wrapper so that no restore path — Redis mirror key, private kit mirror,
# public replay2 copy, or a stale workstation habit of typing the old name —
# can ever resurrect a sporta-product station.
#
# Every invocation now forwards to the ADCOS recover script:
set -u
DURABLE_DIR="/home/z/my-project/download/recovery"
ADCOS_SCRIPT="$DURABLE_DIR/tl_recover_adcos.sh"

if [[ -f "$ADCOS_SCRIPT" ]]; then
  echo "[tl_recover_sporta.sh] DEPRECATED — delegating to tl_recover_adcos.sh (operator directive 2026-10-16: adcos-2.0 is the product)" >&2
  exec bash "$ADCOS_SCRIPT" "$@"
fi

# Wrapper itself survived but the real script is missing: fetch the ADCOS
# script from the public mirror before continuing. POISON GUARD: verify the
# fetched copy does not reference the wrong product repo before executing it.
echo "[tl_recover_sporta.sh] tl_recover_adcos.sh missing — fetching from public mirror payswapdotorg/replay2" >&2
if command -v git >/dev/null 2>&1; then
  rm -rf /tmp/tl-adcos-fetch
  if git clone --quiet --depth 1 https://github.com/payswapdotorg/replay2.git /tmp/tl-adcos-fetch 2>/dev/null \
    && [[ -f /tmp/tl-adcos-fetch/scripts/tl_recover_adcos.sh ]] \
    && ! grep -q 'payswapdotorg/Sporta-2\.0\.git' /tmp/tl-adcos-fetch/scripts/tl_recover_adcos.sh; then
    mkdir -p "$DURABLE_DIR"
    cp /tmp/tl-adcos-fetch/scripts/tl_recover_adcos.sh "$ADCOS_SCRIPT"
    chmod +x "$ADCOS_SCRIPT"
    rm -rf /tmp/tl-adcos-fetch
    exec bash "$ADCOS_SCRIPT" "$@"
  fi
  rm -rf /tmp/tl-adcos-fetch
fi
echo "[tl_recover_sporta.sh] FATAL: could not obtain a poison-free tl_recover_adcos.sh — see the bootstrap law in that script's header" >&2
exit 1
