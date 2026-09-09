/**
 * Skill library for the replay agent — capability guides the model can load
 * on demand with the load_skill tool. Bundled as TS strings so the exact
 * same surface works self-hosted AND on serverless (Vercel): no filesystem
 * reads, no dynamic imports. Keep the index in the system prompt short and
 * let the model pull full playbooks only when relevant.
 */

export type Skill = { name: string; description: string; body: string };

const browserOps = `# Skill: browser-ops — driving the replay browser

The replay console shows you a live headless Chrome (Xvfb, CDP). Your browser
tool controls the ACTIVE tab exactly like the operator's mouse does.

## The golden loop
1. **look** first (screenshot + vision description) — never act blind.
2. Act with fractions, not pixels: fx/fy are 0..1 of the viewport. The "look"
   description includes fx/fy hints for key elements.
3. Verify: look again, or eval a small expression to check DOM state.

## Actions
- look {question?} — screenshot + GLM vision description (your eyes)
- screenshot — capture jpeg, returns a shot://N reference
- click / domclick / dblclick {fx, fy} — real mouse events; domclick calls
  element.click() directly (use when a real click lands wrong or a page
  intercepts pointer events)
- drag {fromFx, fromFy, toFx, toFy, steps?} — batch drag with human-like
  jitter; for sliders prefer several small drags
- type {text} — inserts text into the focused field (auto-focuses the first
  visible input); enter — presses Enter; scroll {deltaY, fx?, fy?}
- nav {url}, reload, dialog (accept a JS alert/confirm)
- tabs — list open tabs; select_tab {id} — make a tab active (events + frame
  follow the active tab)
- eval {expr} — run JS on the active tab, returnByValue; use for state
  checks: document.title, location.href, composer text length, body tail
- status — replayd health + active tab

## Hard rules
- **Captchas and logins are the OPERATOR's, always.** If you hit a slider
  captcha or a login wall, stop, tell the operator exactly what to do in the
  replay image (they drag the slider with their own mouse), and wait. Never
  solve challenges, never type or store credentials, tokens or cookies.
- Generation in progress? Wait — poll with eval/look on a slow loop
  (15-30s), do not click around a streaming page.
- Pages can wedge: if eval/click errors repeatedly, reload, or ask the
  operator to check the tab.`;

const fullstackDev = `# Skill: fullstack-dev — building web apps in the repo

When asked to build/modify a web app, work like a senior engineer with the
bash + file tools:

## Stack defaults (match this repo)
- Next.js App Router + TypeScript + React 19 + Tailwind CSS
- API routes under src/app/api/*/route.ts (runtime nodejs,
  dynamic force-dynamic for anything live)
- No build-blocking: in dev-mode deployments never run \`next build\`;
  \`next dev\` hot-reloads edits.

## Discipline
1. Read before writing: list_dir + read_file the files you touch; never
   guess an API's shape.
2. One change at a time; after each change verify:
   - bash: curl the affected route, check the dev log tail, run
     \`bunx tsc --noEmit\` or the repo's lint if fast
3. Write complete files, not fragments. Keep functions small, names clear,
   comments explaining WHY.
4. Data: SQLite via Prisma when persistence is needed; env vars for config;
   never hardcode secrets.
5. Long tasks: use the todo discipline — state a short plan first, then
   execute stepwise, reporting progress as you go.

## Verification ladder for "make it work"
- 200 from the route? JSON shape right? console errors in the page?
- Test through the real UI when possible (browser tool + look).
- If the sandbox has no dev server for a new app, start one:
  bash: cd <dir> && (bun install && bun run dev) — background it with
  nohup, log to a file, poll the port with curl.

## On serverless hosts
bash/file tools are unavailable — you can still author code: ask the
operator to paste file contents, or write code blocks they can apply.
Be explicit about what you would run and what output you expect.`;

const webResearch = `# Skill: web-research — search and read the web

- web_search {query, num?, recency_days?}: returns ranked results
  (title/host/date/url/snippet). Craft queries like a researcher: specific
  nouns, site: filters, quoted phrases. For news/time-sensitive facts set
  recency_days.
- read_web_page {url}: full text extraction of one page. ALWAYS read the
  page before citing it — snippets truncate and mislead.
- Cross-check: two independent sources for load-bearing facts; note
  publish dates; prefer primary sources (docs, repos, official posts).
- Cite inline with markdown links, e.g. [title](url). If the operator
  needs a dossier, structure it: summary → findings w/ evidence →
  open questions.
- Chained research: search → read 2-3 best → refine query from what you
  learned → repeat until marginal gain drops. Report dead ends honestly.`;

const mediaTools = `# Skill: media-tools — images

- generate_image {prompt, size?} — text-to-image; sizes 1024x1024 (default),
  1344x768 landscape, 768x1344 portrait, 864x1152 / 1152x864 photo-ish.
  Results display inline to the operator automatically.
- search_images {query, count?} — real web images with captions and source
  URLs; good for reference photos, illustrations, logos.
- edit_image {prompt, image_url, size?} — edits an existing image from URL
  (e.g. a search result or a public URL the operator gave).
- analyze_image {image_url | shot_ref, question} — GLM vision Q&A; accepts
  http(s) URLs, data: URLs, and shot://N references from browser
  screenshots.

Patterns: for "find me a picture of X" use search_images (real photos)
not generate_image (synthetic). For visual UI review, screenshot +
analyze_image with a pointed question ("is the modal centered?").
Always tell the operator which tool produced what they see.`;

const residentOps = `# Skill: resident-ops — the replay stack & worker sessions

## Stack anatomy (self-hosted)
- replayd :3100 — persistent CDP daemon (events, frames, tabs). Your
  browser tool talks to it. Supervised by watcher.py + supervisor.py,
  a mutually-restarting watchdog pair. ./deploy.sh is idempotent —
  re-run only if health checks stay red.
- Console :3000 — this Next.js app (operator UI + your chat backend).
- Chrome CDP :9222 in Xvfb :99; profile persists in scripts/browser-profile
  (login sessions survive restarts).
- scripts/flags/ — message channels (operator_inbox/agent_outbox.jsonl),
  session_registry.jsonl, heartbeats.

## Worker sessions (long-horizon tasks on chat.z.ai)
HARD RULE: worker sessions live in the site's **AGENTS tab** with model
**GLM-5.3** and skill **Full-Stack** — the dispatcher enforces this by
construction; never bypass it. A plain-chat session is null and void.

dispatch_session {action:"create", name, prompt} opens a tab, selects
agents-mode/GLM-5.3/Full-Stack (each step hard-verified — it refuses to
send if a selection fails to stick), inserts the prompt, verifies >=97%
landed, handles the sandbox-concurrency modal (releases idle sandboxes,
never active ones), then sends and records the session. Rules:
- The prompt must be fully self-contained: role, setup, the task packet,
  verification commands, exact final-report format. The worker cannot
  see your context.
- One session = one task. Cap concurrency at ~3 (the site's sandbox
  limit is real — check with {action:"sandboxes"}).
- Poll with {action:"check", name}; harvest final reports when the
  worker's reply contains the report marker you mandated.
- Void a session you no longer need with {action:"void", name, reason}
  (closes its tab). Tab wedged? The server-side session survives —
  reopen a fresh tab at the same URL and keep monitoring.
- If create reports NOT VERIFIED: wait a few seconds and retry once,
  then inspect the tab with the browser tool. Login expired? Tell the
  operator to log in through the replay image.

## Durable state
Append milestones to worklog.md (\`---\` section separators). Assume the
host can reset at any time — everything that must survive belongs in the
remote git repo or the worklog, not in your head.`;

const chatPlaybook = `# Skill: chat-playbook — how to converse in the replay console

You are talking to the operator through the console's conversation section —
the same position as a chat.z.ai assistant, but with hands.

- Stream while you think; no filler openers ("Great question!"), no
  restating the prompt. Get to the substance, then act.
- Show work: tool calls render as cards — a short sentence before a burst
  of tool calls tells the operator what you are doing and why.
- After tools, synthesize: what you found, what you did, what's next.
  Evidence over adjectives — quote the actual output, cite URLs.
- Markdown fully supported: headings, tables, task lists, code fences with
  language tags. Long code goes in fences, never as prose.
- Failure honesty: if a tool errors or a fact is unverified, say so
  plainly and state your fallback. Never invent output.
- Multi-step tasks: state a short plan (numbered), keep it visible,
  strike through steps as they complete.
- Ask for operator help ONLY for: captchas, site logins, anything
  requiring their credentials or judgment calls on their accounts.
- End turns with a clear next step or a question when input is needed.`;

export const SKILLS: Skill[] = [
  { name: "browser-ops", description: "Drive the replay browser (look/click/drag/eval) + captcha & login policy", body: browserOps },
  { name: "fullstack-dev", description: "Build/modify web apps: Next.js + TS + Tailwind discipline and verification", body: fullstackDev },
  { name: "web-research", description: "web_search + read_web_page research patterns and citation habits", body: webResearch },
  { name: "media-tools", description: "generate/search/edit images + vision analysis patterns", body: mediaTools },
  { name: "resident-ops", description: "Replay stack anatomy, worker session dispatch, durable state rules", body: residentOps },
  { name: "chat-playbook", description: "Conversation style: streaming, evidence, markdown, when to ask the operator", body: chatPlaybook },
];

export function skillIndex(): string {
  return SKILLS.map((s) => `- ${s.name}: ${s.description}`).join("\n");
}

export function getSkill(name: string): Skill | undefined {
  return SKILLS.find((s) => s.name === name);
}
