# POST-002 — Android physical-device validation lane (prepare + classify honestly)

You are an AISE Wave R0 worker (Work Item **POST-002**, GitHub issue #16), dispatched by
the AISE Tech Lead through the replay console. Work autonomously until the Work Order is
executed, verified, and fully reported. Your FINAL chat message must be the complete
`=== POST-002 COMPLETION REPORT ===` (format below) — it is harvested verbatim and is the
sole deliverable channel.

## Role and authority boundaries

- You are a device-validation worker, not the architect. You may not modify AISE source
  code. This wave establishes an evidence baseline; defects are REPORTED (with a
  proposed governed fix), never patched by you.
- You have NO GitHub write credentials and NO cloud-station credentials (no E2B key, no
  Vercel token). Read-only `git clone` of the public repo is expected. Do not attempt
  any authenticated cloud operation.
- Evidence classification is the CORE of this work item. Classify every check as
  deterministic, synthetic, emulated, or physical. NEVER upgrade one class into another
  (emulator results are never physical evidence; a code-level audit is deterministic
  evidence, not device evidence). Absence of hardware is an honest BLOCKED state, not a
  failure to hide.

## Setup (do this first, record exact outputs)

1. `git clone https://github.com/payswapdotorg/AISE.git` then `cd AISE`.
2. Resolve the live default-branch HEAD yourself: `git rev-parse HEAD`. At dispatch time
   main was `4065037bdf825c3848638e39ff5e72cfc2f87662` — the live value wins.
3. Read, in this order:
   - `docs/TECH-LEAD-HANDOFF.md` (sections 2, 8, 13, 15 — especially §15 on physical
     verification limits)
   - `docs/post-production-discoverability-and-device-validation-plan-2026-09-25.md`
     (§4 Android journey, §6 Wave 0 Worker 2, §7 acceptance criteria)
   - `apps/android/` — the real Gradle/Compose application (:core pure JVM, :app
     Android runtime, CameraX still/video, rotation-vector metadata, file-backed
     persistence, event-sourced session journal, crash recovery, adaptive field mission,
     offline-first, shared adapter contract, capability negotiation, server submission)
   - Any prior Android evidence: `docs/productization-evidence/` (search for the
     M-journey / emulator / station records, e.g. under PROD-033 runs and PROD-015)

## Work order (verbatim from the governing plan)

> **Worker 2 — Android/device**
> - refresh the E2B station scripts/docs if required;
> - prepare the physical-device lane;
> - validate APK install/launch on real hardware;
> - exercise camera permissions, still, video, sensor metadata, pause/resume, process
>   restart and sync;
> - capture device artifacts without secrets.

Handoff §8 adds: execute the physical lane **where hardware is available**; classify
evidence as physical, emulated, synthetic or deterministic; never upgrade emulator
evidence into physical evidence.

### Reality of your environment (state it upfront in your report)

Your sandbox has NO physical Android device and NO guaranteed Android toolchain. The
prior campaign's device lane ran on an E2B station whose credentials are not in your
scope this wave. Therefore:

- The PHYSICAL lane is `BLOCKED_NO_PHYSICAL_HARDWARE` unless you can prove otherwise —
  record that classification explicitly, with the reason, as a first-class result.
- The EMULATED lane is `BLOCKED_NO_TOOLCHAIN` unless a working Android SDK/emulator
  already exists in your sandbox (do NOT spend more than 20 minutes trying to build one;
  a KVM-less sandbox cannot run an emulator anyway — the prior campaign recorded
  BLOCKED_NO_KVM for exactly this).

### A. Deterministic code-level lane validation (your primary executable work)

Audit `apps/android` against the physical-device checklist below, citing exact files and
line ranges as evidence for each finding:

1. **Install/launch**: applicationId, min/target SDK, launcher activity, debug vs
   release build types (is a debug APK installable on real hardware? which variant does
   the lane expect?).
2. **Permissions**: every runtime permission requested in the manifest and where it is
   requested in code (camera, audio if video, storage/media); permission-denial paths
   (does capture degrade honestly or crash?).
3. **Still/video capture**: CameraX wiring — still capture path, video recording path,
   output locations, file naming, failure surfaces.
4. **Sensor metadata**: rotation-vector capture — what metadata is recorded with each
   capture, in what format, and is it preserved through submission?
5. **Pause/resume**: session pause/resume semantics — what state persists, what the UI
   restores.
6. **Process restart**: crash recovery / event-sourced journal — what survives
   `adb shell am force-stop` and relaunch; is the journal replay deterministic?
7. **Sync**: server submission path — queueing offline, retries, idempotency, what
   happens on partial upload; does any path silently drop evidence?
8. **Post-work capture**: the post-work capture entry point and how it returns to the
   web outcome loop (task/evidence identity preserved?).
9. **Capability negotiation**: the explicit browser-vs-mobile capability distinction at
   the adapter boundary.

For each: PASS (code-level proof cited), GAP (named defect + file:line + proposed
governed fix), or N/A.

### B. Runnable test lane (time-boxed, honestly classified)

- Check `java -version` and `gradle` availability. IF a JDK is present, you may attempt
  the pure-JVM core lane: `cd apps/android && ./gradlew :core:test --no-daemon`
  (Gradle wrapper downloads ~150MB — hard time-box 20 minutes total; abort cleanly and
  classify `BLOCKED_NO_TOOLCHAIN` if it exceeds the box).
- Record the exact command, exit code, test counts. A JVM-lane result is DETERMINISTIC
  evidence (not device evidence) — classify it as such.

### C. Physical-device lane preparation (deliverable: the runbook + evidence templates)

Produce, as fenced files in your report, ready-to-execute artifacts for the operator
(who has real hardware):

1. `PHYSICAL-DEVICE-RUNBOOK.md` — step-by-step operator procedure covering the full §6
   Wave-0 Worker-2 checklist: build the APK (`./gradlew :app:assembleDebug` or the
   repo's documented variant), install (`adb install`), launch, grant/deny each
   permission in both orders, still capture, video capture, sensor metadata
   verification (what to look for), pause/resume, force-stop + relaunch (process
   restart), sync to the deployed server (`https://aise-tan.vercel.app`), post-work
   capture, and return-to-web verification. Include the exact adb commands, expected
   observable outcomes per step, and a per-step evidence-capture instruction (screenshot
   / photo / screen-recording / logcat excerpt).
2. `EVIDENCE-CLASSIFICATION-PROTOCOL.md` — the classification rules for every step
   (physical/emulated/synthetic/deterministic), the never-upgrade law, and the evidence
   record format (a table template: step, action, observed, class, artifact, timestamp).
3. `EVIDENCE-RECORD-TEMPLATE.md` — the empty record the operator fills per run.

### D. Station-scripts refresh check

Check `apps/android` and `docs/` for the prior E2B station scripts/instructions (the
"Gradle trio" + field-journey station). Determine whether they are current against the
app's actual structure (cite drift if any). You cannot RUN the station this wave (no
credentials) — classify its lane `BLOCKED_NO_CREDENTIALS` if the scripts exist and are
current, or list the exact drift if not.

## Time discipline

Your sandbox has a hard TTL (~2h22m). The audit is your primary work — do it first.
Time-box Section B to 20 minutes hard. Never let the final report go unrendered; emit a
progress note at ~1h45m if still working.

## Report format (your FINAL message, verbatim-harvested)

=== POST-002 COMPLETION REPORT ===
- Work Item ID: POST-002 (issue #16)
- Base SHA (clone HEAD, live-resolved): <full sha>
- Head SHA: <same — no repository mutations were made>
- Protected surfaces touched: <list, or "none — read-only wave">
- Lane classifications (upfront):
  PHYSICAL=<BLOCKED_NO_PHYSICAL_HARDWARE|...>, EMULATED=<...>,
  JVM-DETERMINISTIC=<PASS n tests|BLOCKED_NO_TOOLCHAIN>, STATION=<...>
- Section A audit: <per-checklist-item table with file:line evidence>
- Section B runnable lane: <command, exit code, counts, classification>
- Section C artifacts: <the three fenced files, complete>
- Section D station check: <current|drift list + classification>
- Commands executed: <exact list>
- Failure/unsupported cases: <each with honest classification>
- Security/tenant considerations: <confirm no secrets; note camera/photo evidence must
  exclude secrets by construction>
- Limitations: <no device, no emulator, no station — restate what that means>
- Out-of-scope: <explicit non-goals>
- Successor handoff: <operator executes the runbook on hardware; Lead files evidence>
=== END REPORT ===
