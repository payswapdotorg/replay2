# PA-14 Execution Runbook — ADCOS row 5 closure (TL in-session work)

**Prepared:** 2026-09-26 00:45 UTC (Task 110, holding pattern)
**Trigger:** the operator issues the RoamLink ADCOS application credentials
out-of-band in ADCOS production and delivers the four values.
**Status:** BLOCKED on operator issuance. No ADCOS_* credentials exist on the
tree or in the vault. The RL-108 probe honestly reports `not-configured`
(exit-distinct) and RL-118 §7.1 row 5 stays a named-skip.

## The four values the operator issues (names per the frozen env contract)

- `ADCOS_API_BASE_URL` — the production ADCOS Developer API origin
- `ADCOS_CLIENT_ID` — the RoamLink application credential (X-ADCOS-Application)
- `ADCOS_CLIENT_SECRET` — the credential secret (X-ADCOS-Credential)
- `ADCOS_WEBHOOK_SECRET` — signs the ADCOS webhook ingress verification

(`ADCOS_API_VERSION` defaults to the pinned `"2.0"` — do not set unless
the operator pins otherwise; only 2.0 is supported:
`packages/contracts/src/env/env-schema.ts` lines 30–49.)

**Delivery channel:** operator message or `~/.secrets/env.sh` (mode 600;
values never printed — names only). `roadmap_watch.py` auto-detects the
names appearing under `~/.secrets/` and notifies the console thread.

## Execution steps (TL, in order)

1. **Receive + stage** the four values in `~/.secrets/env.sh` (mode 600).
   Never echo them; reference by name only.
2. **Set production env** on the Vercel project `roamlink-ten`
   (`prj_lumHhlOR2T8PwbcXHKenxWTrQfg5`), target `production`:
   `POST /v10/projects/{id}/env` per key, `type=encrypted`, then a redeploy
   (v13 `gitSource` github repoId `1370961640` ref `main`,
   `skipAutoDetectionConfirmation=1` — the pattern proven by the PA-017/018
   deploys). Wait READY; verify with `GET /v9/projects/{id}/env`.
3. **Run RL-108** against the real endpoint: the compat probe
   (`packages/compat/src/probe.ts`) — env-driven; expected flip
   `not-configured` -> `compatible` (exit 0). If `incompatible`, STOP and
   report the reason codes to the operator (do not force).
4. **Verify mutation gating**: the compatibility state must open ADCOS
   mutations only when compatible (integration layer; no forced writes).
5. **Verify the webhook path end-to-end**: a signed ADCOS delivery must be
   accepted (HMAC over the canonical envelope, 300s window, dedupe by
   event id); an unsigned delivery must keep failing closed 401.
6. **Re-run the acceptance set** (PA-15 pattern, at the deployed SHA):
   - `corepack pnpm@10.0.0 check`
   - §6b smoke: `BASE_URL=https://roamlink-ten.vercel.app
     node infra/deployment/smoke/run.mjs` (7/7)
   - `pnpm demo:acceptance` — row 5 flips named-skip -> green
7. **Record**: append the additive closure note to the ledger
   (`spec/user-journey-audit.md` §D item 1 — the original finding stands as
   the historical record, mirroring the F-016-1/F-016-2 closure-note
   pattern), update `spec/current-state.md` (ADCOS configured), commit, PR,
   merge, redeploy, verify.
8. **Close**: the §9 completion-definition row "live ADCOS compatibility is
   green" flips -> the campaign is 100% complete (0 open items).

## Invariants (from the frozen architecture)

- RoamLink consumes ONLY the public ADCOS Developer API v2.0 surface.
- No new authority for connectivity sessions / path selection / provider
  identity / ADCOS intent / ADCOS settlement.
- Fail-closed everywhere: unknown/incompatible/not-configured must never
  render as success; the probe's exit codes are distinct by design.
- Secret values never in files under the repo, logs, chats, or PRs; the
  production secret store is the only home for values.
