CONTINUATION — PROD-020 post-delivery gap fix (same task, same session).

Your previous turn died mid-verification, and the sandbox pod recycled AFTER your reconstruction. Current state of delivery/ in the live pod: 33 payload files — local-state.ts and local-state.test.ts are MISSING AGAIN (your reconstruction was lost with the pod). Everything else (adapter, shell, fixtures, evidence docs, DELIVERY.txt listing 34 files) survived intact.

TASK (small, surgical — you already did the hard part):
1. Re-create delivery/apps/desktop/src/adapter/local-state.ts and delivery/apps/desktop/src/adapter/local-state.test.ts with the SAME reconstruction you completed last turn (the full behavioral spec is in your context from the surviving-consumers analysis: index.ts / session.ts / menus.ts / menus.test.ts / profile.ts imports — createInMemoryPersistence, createLocalConvenienceStore, LocalConvenienceStore, PersistencePort, RecentProjectRecord, OfflineIntentRecord, non-authoritative stamping, offline-queue replay).
2. Verify exactly as before: isolated bun test (16/16 expected) + strict tsc clean.
3. Confirm delivery/ now matches the DELIVERY.txt manifest (34 payload files) — update DELIVERY.txt line counts only if your reconstruction differs.
4. Reply with a short COMPLETION REPORT: files re-emitted, test/typecheck results, manifest check.

Constraints unchanged: local-state is the local convenience store — NON-AUTHORITATIVE by construction, never a source of record; no scope creep beyond these two files.
