# Replay Console

A deployable **remote-browser-control console** (a "replay"): a web page that
live-mirrors a headless Chrome and lets a human operate it from anywhere —
click, **drag (streamed in real time)**, type, scroll, switch tabs, log in —
including slider-captcha verification. Plus a **full agent chat**: a
GLM-5.3 conversation section with real tools (bash, the replay browser, web
search, images, vision, worker dispatch, skills) — the same class of
assistant you'd talk to on chat.z.ai, embedded in the console.

Deploy the whole stack into a fresh sandbox with one command and a one-line
login; no rebuilding.

## Stack

```
Xvfb :99 ── Chrome (CDP :9222, persistent profile scripts/browser-profile)
                 │
                 ├── replayd :3100   persistent CDP daemon: frames ~100ms,
                 │                  streamed dragstart/dragmove/dragend (~5ms)
                 │
                 └── watcher ⇄ supervisor   mutual-watchdog pair: each restarts
                    the other if it dies; they also relaunch Chrome, replayd
                    and the console. Logs self-rotate.

Next.js console :3000  (/) ── frame/event/tabs/status/inbox routes proxy to
                 replayd with a bridge.py spawn fallback.
                 /api/agent/chat — the agent conversation backend (SSE).
```

- Console UI: live replay image (native pointer listeners — React synthetic
  handlers proved unreliable), amber drag guide, click feedback line with the
  probed target element, tab bar with auto-focus of new tabs, keyboard box
  (no auto-Enter), and the **Agent chat** column (see below).
- Clicks are sent as **fractions** (fx/fy 0..1); the daemon maps them with the
  live viewport (`Page.getLayoutMetrics`) — immune to image-size/scale skew.
- `scripts/dispatch_worker.py` — create named **agent** sessions in the
  browser (agents tab + GLM-5.3 + Full-Stack skill, every step hard-verified,
  sandbox-concurrency handling) and check/void them. Useful for dispatching
  long-horizon work to AI sessions living inside the replay.

## Agent chat ("Message the agent")

The console's conversation section is a full agent, not a message box:

- **Model**: GLM-5.3 (picker: GLM-5.3 / -Flash / 5.2 / 4.6), streaming with
  native tool calling, thinking phase, 429 backoff.
- **Tools** (13, capability-detected at runtime):
  - *local tier* (self-hosted): `bash`, `read_file`, `write_file`,
    `list_dir`, `browser` (the live replay Chrome: look = screenshot + GLM
    vision, click/domclick/drag/type/eval/tabs…), `dispatch_session`
    (agents-tab worker dispatch incl. sandbox concurrency)
  - *cloud tier* (work on Vercel too): `web_search`, `read_web_page`,
    `generate_image`, `search_images`, `edit_image`, `analyze_image`
    (GLM-4.6V vision), `load_skill`
- **Skills**: bundled playbooks (browser-ops, fullstack-dev, web-research,
  media-tools, resident-ops, chat-playbook) loaded on demand — the system
  prompt stays small, the agent pulls full guidance when relevant.
- **UI**: streaming markdown with syntax-highlighted code blocks + copy,
  tool-call cards with results/durations/inline images, multi-conversation
  history (localStorage — serverless-safe), image attachments (vision
  pre-pass), stop / regenerate, model picker, resident-agent notes inline.
- **Resident bridge**: prompts sent through the chat are mirrored into
  `scripts/flags/operator_inbox.jsonl` (source-tagged) so a resident CLI
  agent watching the inbox stays aware; resident replies (agent_outbox)
  surface inline in the thread.
- **Hard constraints** (enforced by the system prompt): the agent never
  solves captchas and never touches credentials — logins are the operator's,
  driven through the replay image.

### Deploy on Vercel (serverless)

The chat works standalone on Vercel — the cloud tool tier needs no local
stack:

1. Import the repo in Vercel (framework preset: Next.js).
2. Set env vars: `ZAI_BASE_URL` + `ZAI_API_KEY` (the z-ai-web-dev-sdk
   gateway credentials), optionally `AGENT_MODEL` (default `glm-5.3`).
3. Deploy. The console shows the replay pane offline, the chat badge reads
   "serverless · cloud tools", and web search / page reader / image
   generation / image search / edit / vision / skills all work.
4. Optional: point `REPLAYD_URL` at an exposed replayd (e.g. the sandbox
   daemon behind a tunnel) to re-enable the browser + dispatch tools
   remotely.

The local tools (`bash`, files, `browser`, `dispatch_session`) report
unavailability gracefully on serverless — the agent explains the limitation
and adapts (authors code, uses cloud tools) instead of failing silently.
Route config sets `maxDuration = 800` (Vercel clamps per plan).

## Deploy (fresh sandbox)

```bash
git clone https://github.com/payswapdotorg/replay2.git
cd replay2
./deploy.sh
```

`deploy.sh` is **idempotent** — every component is health-checked and only
started when missing; re-running is always safe.

Requirements (present in the standard sandbox): `bun`, `python3` +
`websocket-client` (auto-installed if missing), `Xvfb`, and a Chrome/Chromium
binary (playwright cache auto-discovered; else set `CHROME_BIN=...`).

After deploy:
1. Open the console (the preview panel / port 3000).
2. **Log in to the target site through the replay image** (click Sign in →
   Continue with Email → click the field → type in the box under the replay →
   slider captcha: press and drag slowly on the image, release when aligned).
   The session persists in `scripts/browser-profile` across stack restarts
   (not across sandbox resets — re-login after a reset).

Optional: `cp scripts/env.sh.example scripts/env.sh` and set `REPO=owner/name`
to get a branch/PR summary card in the console.

### Environment variables

| var | default | effect |
|---|---|---|
| `REPLAY_PORT` | `3000` | console port |
| `CDP_PORT` | `9222` | Chrome DevTools port |
| `REPLAYD_PORT` | `3100` | replay daemon port |
| `CHROME_BIN` | auto | chrome binary for launch_stack.py |
| `REPLAY_START_URL` | `https://chat.z.ai/` | first page in the browser |
| `REPLAY_DISPLAY` / `REPLAY_WxH` | `:99` / `1440x900` | Xvfb settings |
| `SKIP_BROWSER=1` | — | console-only redeploy |
| `SKIP_SUPERVISOR=1` | — | don't start watchdogs (parallel test) |

Set all three `*_PORT` vars to run a fully isolated second deployment
beside an existing one (e.g. `REPLAY_PORT=3005 CDP_PORT=9223 REPLAYD_PORT=3101
REPLAY_DISPLAY=:98 ./deploy.sh`).

## Verify a deployment

```bash
curl -s http://127.0.0.1:3100/healthz        # {"ok":true,...}
curl -s http://127.0.0.1:9222/json/version   # Chrome CDP
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/   # 200
curl -s http://127.0.0.1:3000/api/status     # browser_login state
```

Then in the browser: the replay image renders, clicking shows a green ripple +
`clicked → <element>` feedback, a drag shows the amber guide line and the page
follows it live.

## Troubleshooting

- **Stale/frozen page** → hard-refresh the console (Ctrl+Shift+R); check the
  version badge. If frames still don't update: `curl :3100/healthz`; the
  watcher auto-restarts a dead replayd within ~2 min.
- **Clicks land wrong** → toggle **DOM click** mode in the replay header.
- **Login popup events go to the wrong tab** → click the tab in the tab bar
  (new tabs get a ✦ badge and auto-focus).
- **Typing goes nowhere** → the daemon auto-focuses the first visible input;
  click the field first, then type.
- **Everything dead** → re-run `./deploy.sh` (idempotent). The supervisor and
  watcher mutually resurrect each other, so this is rarely needed.
- Logs: `scripts/logs/`, `scripts/watcher.log`, `scripts/dev.log`,
  `scripts/browser.log`.

## Self-test

`python3 scripts/test_drag.py` runs the full pointer pipeline
(pointerdown → held moves → pointerup) against a data-URL test page and
asserts the events landed — proves drag streaming before you trust it with a
captcha.
