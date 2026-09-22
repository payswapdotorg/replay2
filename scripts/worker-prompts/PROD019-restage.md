STAGING CORRECTION — PROD-019 delivery re-stage required (Lead harvest audit).

Your completion report and DELIVERY.txt list 32 changed files, but the staged
delivery/ tree in the workspace contains only 22 of them plus DELIVERY.txt.
ALL TEN TEST FILES are missing from delivery/ (the 9 :core test sources under
apps/android/core/src/test/kotlin/org/payswap/aise/core/adapter/ —
AdapterContractVersionTest, AdapterCorpus, AdapterCorpusConformanceTest,
AuthoritativeFieldsMirrorTest, CapabilityNegotiationTest,
ClientCapabilityProfileTest, CompatibilityCheckerAlignmentTest,
FieldJourneyTest, TaskIntentWire — plus the :app test
apps/android/app/src/test/kotlin/org/payswap/aise/app/field/FieldJourneyRuntimeTest.kt).

TASK — a file-copy correction ONLY. Do NOT modify any code, do NOT re-run
gates, do NOT amend or re-create the commit, do NOT change DELIVERY.txt:

1. cd /home/z/AISE (your repo clone, exactly as you left it).
2. Run: git diff --name-only 7d21d47147a3df14a0e6138131de6d9add672d27..HEAD
   That list is the authority — 32 paths.
3. For EVERY path in that list, check whether the file already exists under
   the workspace delivery/ tree; copy the missing ones in, preserving
   repo-relative paths (same loop as packet §6). This is only the test
   sources named above, but let the git list decide, not this message.
4. Verify every one of the 32 paths now exists under delivery/ (and nothing
   else changed).
5. Reply with EXACTLY this line and nothing else:
   RE-STAGE COMPLETE — <N> files copied, all 32 diff paths present under delivery/, commit 0429c5132661f4056075f49755fa48330b8af1bc unchanged.
