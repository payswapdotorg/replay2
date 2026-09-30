# FLAUZ P2-FIX WORKER ORDER — <P2-FIX-ID> (<short-slug>)

> Instantiated by the TL2 station from this template at claim time.
> Fill every `<slot>`; delete nothing. The finding text is quoted VERBATIM
> in §1 — the worker never reinterprets the finding.

## §0 Stop clauses (read first)

- If any instruction here conflicts with `docs/FLAUZ-PROGRAM/` governance,
  STOP and report the conflict in your report — do not improvise.
- **Boundary loss-stop:** you own exactly ONE partition (§3). If a complete
  fix would require touching another partition or another TL's surface,
  implement your half, then STOP at the boundary and report the residue
  explicitly (what remains, which owner it needs, why you did not cross).
- Credential-free delivery: no secrets, no tokens, no network credentials.
  The bundle is delivered through the staging directory only.
- If you cannot reproduce the finding at the pinned base, STOP and report —
  a non-reproducible finding goes back to TL4, it is not yours to close.

## §1 The finding (verbatim, from TL4)

```text
<PASTE THE FULL FINDING HERE — Observed behavior / Evidence level / Exact
reproduction / Owning TL / Acceptance test / Architecture impact — unchanged>
```

## §2 Fixed facts

- **Pinned base:** `<FULL-40-CHAR-SHA>` (flauz main at claim time) — branch
  `flauz-p2fix/<id-lower>` is cut FROM THIS SHA ONLY; rebase is forbidden.
- **Work-order id:** `<P2-FIX-ID>` — every artifact, branch, marker and
  report line carries it.
- **minimal-diff law:** the smallest diff that satisfies §1's acceptance
  test. Drive-by refactors, formatting sweeps and unrelated fixes are
  defects, not contributions.
- **GATE-FROZEN law:** `build/flauz/scripts/agentos-battery.mjs`, the
  doctored controls and the verifiers stay BYTE-IDENTICAL to the pinned
  base (sha256 of each in your report). The acceptance instrument is
  frozen — the fix must pass it, never edit it.
- **Hygiene:** additive-only inside the partition; no new `.mjs` files; no
  schema primitive lists; imports respect extension boundaries.

## §3 Partitions — you own exactly ONE

- **A — agent runtime:** orchestration, retry, cancellation, leases,
  recovery, durable execution.
- **B — model fabric:** provider routing, live provider behavior, model
  capabilities, context/tool policy, model state.
- **C — collaboration/state:** A2A, workflows, memory, approvals, takeover,
  execution integration.

**YOUR PARTITION: <A|B|C>** — the other two are read-only context.

## §4 Evidence levels (never promote)

```text
fixture   < battery   < runtime
```

- Claim exactly the highest level ACTUALLY achieved. Fixture evidence is
  never wording for a runtime claim. Runtime claims (live provider, live
  CDP/Chromium, live environment) need runtime receipts in the report:
  command, exit code, and the observable that proves the behavior.

## §5 Deliverables & staging law

1. Targeted tests: the finding's acceptance test from §1, plus regression
   guards for the touched contract. Test names carry the finding id.
2. Staging (credential-free bundle delivery):
   - workspace root `flauz-delivery/<id-lower>-<slug>/`
   - `MANIFEST` with per-file `sha256` and a tree self-check line
   - the report file inside the same directory
3. Report markers (exact):
   ```text
   FLAUZ-<ID-NORMALIZED>-REPORT BEGIN
   FLAUZ-<ID-NORMALIZED>-REPORT END
   ```
4. In-sandbox receipts mandated in the report: baseline AND after suite
   counts, `tsc` exit code, battery `--selftest`, and the sha256 table for
   the frozen instrument files.

## §6 Session laws

- You run as an agents-tab session, model GLM-5.3, skill Full-Stack
  (chat-tab sessions are NULL AND VOID — operator directive 2026-09-08).
- Report ends with: `Pushed: <sha>` + test summary (the station verifies
  the push via ls-remote before harvest).
- Stop-and-report is always an acceptable outcome (§0); silent partial
  delivery is not.
