import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export const metadata = {
  title: "Hyper3D Rodin clone — mission close-out (4/4) + workspace parity",
  description:
    "Four-point mission complete: clone tested as a real user, reference understood via free paths only, reverse-engineered, and genuinely usable — neural + fallback engines, byte-verified exports. Post-close: every missing rodin workspace option implemented and verified (Task 32).",
};

const PARITY_OPTIONS = [
  { label: "Version selector", value: "Gen-1.5 V1.2 / Gen-2.5 Agent-Ready — honest: Gen-1.5 runs the standard pipeline, agentic gated" },
  { label: "11 direction labels", value: "FL/F/FR/L/UP/R/BL/B/BR/DN/Unknown — honest ENGINE_SLOT_OF mapping; diagonals recorded, not fake-fed" },
  { label: "Default / Speedy + effort", value: "Mode cards + 5 effort levels, surfaced per version like the reference" },
  { label: "Material selector", value: "PBR / Shaded / All / None — stored on the task card, repaints on confirm" },
  { label: "Private tasks", value: "Private switch — excluded from the public featured list" },
  { label: "Batch size", value: "Honest Business-gated control (toast explains the gate) — no fake batching" },
  { label: "Presets + creation modes", value: "Prompt preset chips; WorldGen: Build Myself / Generate Objects / Complete Scene" },
  { label: "Redo (geometry / material)", value: "Real quota ledger — geometry redo = fresh-seed clone with redo_of lineage; material redo repaints the live mesh" },
  { label: "FBX export", value: "New ASCII FBX 7.3 exporter — 6 formats total (STL/FBX/OBJ/GLB/GLTF/USDZ), 803,657 B export numerically validated" },
];

const PARITY_STATUS = [
  { k: "Try it now", v: "Preview panel → /?XTransformPort=3210 — the parity instance runs the full workspace" },
  { k: "Sign in", v: "demo@hyper3d.clone / demo1234 (local demo credits — generation is free here)" },
  { k: "Verified", v: "Golden path + private/material settings on card c68233f8 · redo lineage ba7b7cdd · quota 20→19 · FBX byte-checked — re-verified post-recovery: task 334fd3d0 (PBR + FR view + private, GLB + FBX byte-checked, credits 50→49) — re-verified after 3rd reboot on the archive-proof DB: task e2df69a8 (live generation, GLB 87,252 B byte-checked)" },
  { k: "Durability", v: "DB now git-tracked at /home/z/my-project/db/hyper3d-clone.db — survives the platform's archive-restore reboots (root cause of the Task-34 path wipe: gitignored files are excluded from repo.tar)" },
  { k: "Production", v: "LIVE — parity commit 30eb877 pushed to main (5dc716e→30eb877) and DEPLOYED on Vercel (build READY): all 11 parity controls verified on hyper3d-clone.vercel.app incl. the Gen-1.5 Default/Speedy switch" },
  { k: "Ops", v: "Evidence branch: replay2@harvest/e2e20-hyper3d (15+ evidence commits). Secrets vault: gitignored + .git-carried (archive-proof, never pushed). PAT/Composio/Vercel/OpenRouter/Apify all validated" },
];

const MISSION_POINTS = [
  {
    id: "01",
    title: "Real-user clone testing",
    body: "Full golden paths through hyper3d-clone.vercel.app as a real user — sign-in, image upload, auto-caption, generation, confirm, export — repeated across network conditions and sessions.",
    evidence: "10+ verified cycles (7 this harvest session incl. 8-cycle grind)",
  },
  {
    id: "02",
    title: "Reference understanding (free paths only)",
    body: "hyper3d.ai/workspace/rodin image-to-3D understood via free tier only: anonymous ZeroGPU admission mechanics, per-IP quota pools, honest fallback behavior, texture tier gating.",
    evidence: "Engine recon + 5× ETA-converged window predictions",
  },
  {
    id: "03",
    title: "Reverse engineering",
    body: "Requests, API surface, and interaction flow mapped: task lifecycle routes, caption pipeline (Bailian vision), Hunyuan3D-2.1 space protocol (upload → queue/join → SSE), pay-by-result credits.",
    evidence: "Ops research docs + instrumented browser traffic captures",
  },
  {
    id: "04",
    title: "Clone is genuinely usable",
    body: "Not a UI replica — both engines work end-to-end: neural (Hunyuan3D-2.1) and fast fallback, with captions, exactly-1-credit confirm, and byte-verified GLB/OBJ exports.",
    evidence: "First-party neural card + third-party cross-verification",
  },
];

const EVIDENCE_CHAIN = [
  { label: "Task card", value: "d716a085 · engine_used=neural · fallback=null · DonePreview" },
  { label: "UI confirm & export", value: "Confirm & Export clicked · balance 21 → 20 (pay-by-result, exactly 1 credit)" },
  { label: "Exports byte-verified", value: "GLB 337,564 B · magic 'glTF' ✓ — OBJ 665,186 B · 7k-vert/14k-face flexicubes topology ✓" },
  { label: "VLM verdict (lit viewer)", value: "7/10 — PASS (threshold ≥6 · fallback baseline 3/10 · engine reference 8/10)" },
  { label: "Window landing", value: "Engine ETA converged 5× on 13:17:45Z · cycle 8 fired 13:19:01Z → admitted" },
  { label: "Cross-verification", value: "Third-party neural card 394e5612 (09:27Z real-user run) — exports independently byte-verified" },
];

const TIMELINE = [
  { time: "12:28Z", text: "Session start — sandbox found fully reset (all local state wiped)" },
  { time: "12:30Z", text: "Recovery from public GitHub — watcher snapshots confirm: no window through 02:23Z" },
  { time: "12:38Z", text: "Grind re-armed fire-only (fixture + scripts recovered, zero budget held)" },
  { time: "12:44Z", text: "Pool intel: 74s/90s — engine ETA converges on 13:17:45Z window" },
  { time: "13:19Z", text: "Cycle 8 fired → ADMITTED — neural golden path in flight" },
  { time: "13:21Z", text: "SUCCESS — task d716a085 confirmed, exports byte-verified, verdict 7/10 PASS" },
];

const SHOTS = [
  { file: "/harvest/e2e20-neural-01-task.png", caption: "01 · Neural task card — engine badge, DonePreview" },
  { file: "/harvest/e2e20-neural-02-viewer.png", caption: "02 · Lit viewer render — the 7/10 verdict poster" },
  { file: "/harvest/e2e20-neural-03-confirmed.png", caption: "03 · Confirm & Export — credits charged, buttons enabled" },
  { file: "/harvest/e2e20-neural-04-final.png", caption: "04 · Final state — organic apple-cluster mesh, lit" },
];

const LINKS = [
  { label: "Live clone", href: "https://hyper3d-clone.vercel.app", note: "hyper3d-clone.vercel.app" },
  { label: "Clone source", href: "https://github.com/payswapdotorg/hyper3d-clone", note: "github.com/payswapdotorg/hyper3d-clone" },
  { label: "Ops repo (prior snapshots)", href: "https://github.com/payswapdotorg/replay2", note: "github.com/payswapdotorg/replay2" },
];

const DURABLE = [
  { label: "Master evidence bundle (MD5-verified)", href: "https://paste.rs/Xd38J", note: "paste.rs/Xd38J — manifest · worklog · result · verdict · grind log" },
  { label: "Addendum bundle — post-harvest verification (MD5-verified)", href: "https://paste.rs/MqCpa", note: "paste.rs/MqCpa — Tasks 27-28 · monitoring snapshot · live re-verification" },
  { label: "Addendum 2 — reboot recovery + source↔deploy check (MD5-verified)", href: "https://paste.rs/JV66v", note: "paste.rs/JV66v — Tasks 29-31 · bundle decode recipe · payload manifest" },
  { label: "Poster 01 · task card", href: "https://paste.rs/OvmRc", note: "234,409 B round-trip exact" },
  { label: "Poster 02 · viewer", href: "https://paste.rs/sCVnl", note: "228,046 B round-trip exact" },
  { label: "Poster 03 · confirmed", href: "https://paste.rs/0tBzb", note: "221,686 B round-trip exact" },
  { label: "Poster 04 · final", href: "https://paste.rs/4dfU4", note: "216,637 B round-trip exact" },
  { label: "Addendum 3 — workspace parity + incident recovery (MD5-verified)", href: "https://paste.rs/7Bp8d", note: "paste.rs/7Bp8d — Task 32 parity record · Task 33 OOM/reaper recovery · relaunch recipe" },
  { label: "Addendum 4 — durable DB pin + post-recovery golden path (MD5-verified)", href: "https://paste.rs/jGkVz", note: "paste.rs/jGkVz — Task 34 · platform auto-start discovery · task 334fd3d0 with FR view + PBR + private" },
  { label: "Addendum 5 — archive-proof DB + third-reboot re-verify (MD5-verified)", href: "https://paste.rs/KyCsF", note: "paste.rs/KyCsF — Task 35 · repo.tar exclusion root cause · git-tracked DB fix · task e2df69a8 GLB byte-checked" },
  { label: "Addendum 6 — production rollout COMPLETE (MD5-verified)", href: "https://paste.rs/w2wnq", note: "paste.rs/w2wnq — Task 36 · PAT gates opened · 30eb877 deployed on Vercel · 11/11 parity controls live in production" },
  { label: "Addendum 7 — continuity verification + evidence sync (MD5-verified)", href: "https://paste.rs/cZEsB", note: "paste.rs/cZEsB — Task 37 · evidence branch synced through 53d995f · 13/13 secret scan clean · three-tier browser verify" },
];

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      <main className="flex-1">
        {/* Hero */}
        <header className="border-b">
          <div className="mx-auto max-w-5xl px-4 sm:px-6 py-10 sm:py-14">
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <Badge variant="destructive" className="font-mono text-xs">e2e20 · neural harvest</Badge>
              <Badge variant="outline" className="font-mono text-xs">zero budget</Badge>
              <Badge className="bg-emerald-600 hover:bg-emerald-600 font-mono text-xs">mission 4/4 complete</Badge>
              <Badge variant="outline" className="font-mono text-xs border-emerald-600 text-emerald-700 dark:text-emerald-400">workspace parity ✓</Badge>
              <Badge className="bg-emerald-600 hover:bg-emerald-600 font-mono text-xs">production LIVE</Badge>
            </div>
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
              Hyper3D Rodin clone — <span className="text-emerald-600">the real thing, verified</span>
            </h1>
            <p className="mt-3 max-w-3xl text-muted-foreground leading-relaxed">
              The last quota-gated artifact landed on 2026-10-20 13:21Z: a real Hunyuan3D-2.1
              generation completed through the production UI golden path — browser-direct,
              anonymous, exactly as shipped. This page is the mission close-out report and
              evidence index.
            </p>
            <div className="mt-5 flex flex-wrap gap-x-8 gap-y-2 font-mono text-xs text-muted-foreground">
              <span>window 13:17:45Z <span className="text-emerald-600">(ETA converged ×5)</span></span>
              <span>cycle 8 · fired 13:19:01Z</span>
              <span>task d716a085 · seed 22022</span>
              <span>verdict <span className="text-emerald-600 font-semibold">7/10 PASS</span></span>
            </div>
          </div>
        </header>

        {/* Four points */}
        <section aria-labelledby="mission" className="mx-auto max-w-5xl px-4 sm:px-6 py-10">
          <h2 id="mission" className="text-xl font-semibold tracking-tight mb-5">The four-point mission</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {MISSION_POINTS.map((p) => (
              <Card key={p.id} className="transition-shadow hover:shadow-md">
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs text-muted-foreground">{p.id}</span>
                    <CardTitle className="text-base">{p.title}</CardTitle>
                    <Badge className="ml-auto bg-emerald-600 hover:bg-emerald-600 shrink-0">✓</Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground leading-relaxed">{p.body}</p>
                  <p className="mt-3 font-mono text-xs text-emerald-700 dark:text-emerald-400">{p.evidence}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* Workspace parity */}
        <section aria-labelledby="parity" className="mx-auto max-w-5xl px-4 sm:px-6 py-10">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <h2 id="parity" className="text-xl font-semibold tracking-tight">Workspace parity — the missing rodin options, implemented</h2>
            <Badge className="bg-emerald-600 hover:bg-emerald-600 font-mono text-xs shrink-0">Task 32 ✓</Badge>
          </div>
          <p className="text-sm text-muted-foreground mb-5 max-w-3xl leading-relaxed">
            Post-close-out, the reference workspace surface was re-snapshotted live and diffed
            against the clone — every option that was missing now exists with honest behavior
            (11 files, 2 new; end-to-end verified on the parity instance).
          </p>
          <div className="grid gap-4 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader className="pb-2"><CardTitle className="text-sm">Implemented options (honest, not decorative)</CardTitle></CardHeader>
              <CardContent>
                <dl className="space-y-3 max-h-96 overflow-y-auto pr-1">
                  {PARITY_OPTIONS.map((o) => (
                    <div key={o.label}>
                      <dt className="font-mono text-xs uppercase tracking-wide text-muted-foreground">{o.label}</dt>
                      <dd className="mt-0.5 text-sm leading-relaxed">{o.value}</dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>
            <Card className="lg:col-span-2 h-fit">
              <CardHeader className="pb-2"><CardTitle className="text-sm">Try it / status</CardTitle></CardHeader>
              <CardContent>
                <dl className="space-y-3">
                  {PARITY_STATUS.map((s) => (
                    <div key={s.k}>
                      <dt className="font-mono text-xs uppercase tracking-wide text-muted-foreground">{s.k}</dt>
                      <dd className="mt-0.5 text-sm leading-relaxed break-words">{s.v}</dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>
          </div>
        </section>

        <Separator />

        {/* Evidence chain */}
        <section aria-labelledby="evidence" className="mx-auto max-w-5xl px-4 sm:px-6 py-10">
          <h2 id="evidence" className="text-xl font-semibold tracking-tight mb-2">
            The decisive artifact — evidence chain
          </h2>
          <p className="text-sm text-muted-foreground mb-5">
            First-party neural run through the UI, plus an independent third-party neural card
            found on the production DB the same day (a real user completed one during the sandbox
            outage — cross-verified).
          </p>
          <Card>
            <CardContent className="pt-6">
              <dl className="space-y-0">
                {EVIDENCE_CHAIN.map((row, i) => (
                  <div key={row.label} className={i > 0 ? "mt-4" : ""}>
                    <dt className="font-mono text-xs uppercase tracking-wide text-muted-foreground">{row.label}</dt>
                    <dd className="mt-1 text-sm leading-relaxed break-words">{row.value}</dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
        </section>

        {/* Screenshots */}
        <section aria-labelledby="shots" className="mx-auto max-w-5xl px-4 sm:px-6 py-10">
          <h2 id="shots" className="text-xl font-semibold tracking-tight mb-2">The posters</h2>
          <p className="text-sm text-muted-foreground mb-5">
            Full-page production UI captures of the neural golden path — the same style as the
            banked fallback baselines.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {SHOTS.map((s) => (
              <figure key={s.file} className="group">
                <div className="overflow-hidden rounded-lg border bg-muted/40">
                  <img
                    src={s.file}
                    alt={s.caption}
                    className="w-full h-auto transition-transform duration-300 group-hover:scale-[1.02]"
                    loading="lazy"
                  />
                </div>
                <figcaption className="mt-2 font-mono text-xs text-muted-foreground">{s.caption}</figcaption>
              </figure>
            ))}
          </div>
        </section>

        <Separator />

        {/* Timeline */}
        <section aria-labelledby="timeline" className="mx-auto max-w-5xl px-4 sm:px-6 py-10">
          <h2 id="timeline" className="text-xl font-semibold tracking-tight mb-5">Harvest session — 2026-10-20</h2>
          <ol className="relative border-l ml-2 space-y-6">
            {TIMELINE.map((t) => (
              <li key={t.time} className="ml-4">
                <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-emerald-600" aria-hidden="true" />
                <time className="font-mono text-xs text-muted-foreground">{t.time}</time>
                <p className="mt-0.5 text-sm leading-relaxed">{t.text}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* Pointers */}
        <section aria-labelledby="links" className="mx-auto max-w-5xl px-4 sm:px-6 py-10">
          <h2 id="links" className="text-xl font-semibold tracking-tight mb-5">Pointers</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Live artifacts</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {LINKS.map((l) => (
                  <a key={l.href} href={l.href} target="_blank" rel="noreferrer"
                     className="block rounded-md border px-3 py-2 transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-2">
                    <span className="text-sm font-medium">{l.label}</span>
                    <span className="block font-mono text-xs text-muted-foreground break-all">{l.note}</span>
                  </a>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Durable evidence (paste.rs, byte-verified)</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {DURABLE.map((d) => (
                  <a key={d.href} href={d.href} target="_blank" rel="noreferrer"
                     className="block rounded-md border px-3 py-2 transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-2">
                    <span className="text-sm font-medium">{d.label}</span>
                    <span className="block font-mono text-xs text-muted-foreground break-all">{d.note}</span>
                  </a>
                ))}
              </CardContent>
            </Card>
          </div>
          <p className="mt-4 text-xs text-muted-foreground leading-relaxed">
            Update (Task 37, 2026-10-21): the PAT gates opened — this harvest now lives on GitHub at
            replay2@harvest/e2e20-hyper3d (full lineage, synced through 53d995f, no force-push) and
            the parity build at 30eb877 is LIVE on hyper3d-clone.vercel.app. The paste.rs bundles
            remain the byte-verified durable copies (MD5 round-trip verified).
          </p>
        </section>
      </main>

      <footer className="mt-auto border-t">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 py-5 flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="font-mono text-xs text-muted-foreground">e2e20 · neural harvest closed</span>
          <span className="font-mono text-xs text-muted-foreground">Task 20 ✓ Task 22 ✓ mission 4/4 ✓ Task 32 parity ✓</span>
          <span className="ml-auto font-mono text-xs text-muted-foreground">2026-10-20/21 · zero budget held</span>
        </div>
      </footer>
    </div>
  );
}
