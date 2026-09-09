"use client";

/**
 * AgentChat — the "Message the agent" feature, rebuilt as a full
 * chat-grade conversation section: streaming GLM replies with markdown +
 * highlighted code, tool-call cards with results and inline images,
 * model picker, multi-conversation history, image attachments, stop /
 * regenerate, resident-agent notes surfaced inline.
 *
 * Backend: POST /api/agent/chat (SSE). Protocol history lives on the
 * client (serverless-safe); server mirrors prompts to the resident inbox
 * and appends audit transcripts when the FS is writable.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Markdown } from "./Markdown";
import {
  ChatMsg, Conversation, DisplayMeta, ToolCallRec,
  loadConversations, saveConversations, newConversation, loadModel, saveModel, titleFrom,
} from "@/lib/chatStore";

type Caps = {
  hosting: string;
  sdk: boolean;
  tools: Record<string, boolean>;
  models: { id: string; label: string; note: string }[];
  default_model: string;
};

type LiveTool = { id: string; name: string; args: string; preview?: string; ok?: boolean; durationMs?: number; images: string[]; running: boolean };

type RenderItem =
  | { kind: "user"; msg: ChatMsg }
  | { kind: "resident"; msg: ChatMsg }
  | { kind: "assistant"; msg: ChatMsg }
  | { kind: "tools"; text?: string; calls: { call: ToolCallRec; result?: ChatMsg }[] };

const MODEL_FALLBACK = [
  { id: "glm-5.3", label: "GLM-5.3", note: "flagship" },
  { id: "glm-5.3-flash", label: "GLM-5.3-Flash", note: "fast" },
  { id: "glm-5.2", label: "GLM-5.2", note: "prev flagship" },
  { id: "glm-4.6", label: "GLM-4.6", note: "classic" },
];

function timeLabel(ts?: number): string {
  return ts ? new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
}

function argsSummary(name: string, argsRaw: string): string {
  try {
    const a = JSON.parse(argsRaw || "{}");
    const keys = Object.keys(a);
    if (!keys.length) return "";
    const parts: string[] = [];
    for (const k of keys.slice(0, 3)) {
      const v = typeof a[k] === "string" ? a[k] : JSON.stringify(a[k]);
      parts.push(`${k}: ${String(v).slice(0, 60)}`);
    }
    if (keys.length > 3) parts.push(`+${keys.length - 3} more`);
    return parts.join(" · ");
  } catch {
    return argsRaw.slice(0, 80);
  }
}

function ToolCard({ name, args, preview, ok, durationMs, images, running }: LiveTool) {
  const [open, setOpen] = useState(false);
  const dot = running
    ? "bg-amber-400 animate-pulse"
    : ok === false
      ? "bg-red-500"
      : "bg-emerald-500";
  return (
    <div className="border border-neutral-200 rounded-lg bg-white overflow-hidden my-1.5">
      <button
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left hover:bg-neutral-50"
        onClick={() => setOpen((o) => !o)}
      >
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dot}`} />
        <span className="font-mono text-[11px] font-semibold text-neutral-800">{name}</span>
        <span className="text-[10px] text-neutral-400 truncate flex-1 hidden sm:inline">{argsSummary(name, args)}</span>
        {durationMs !== undefined && <span className="text-[10px] text-neutral-400 font-mono shrink-0">{durationMs < 1000 ? `${durationMs}ms` : `${(durationMs / 1000).toFixed(1)}s`}</span>}
        <span className="text-[9px] text-neutral-400 shrink-0">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-neutral-100 px-2.5 py-2">
          <div className="text-[10px] font-mono text-neutral-500 mb-1">arguments</div>
          <pre className="text-[11px] font-mono text-neutral-700 whitespace-pre-wrap break-all mb-2">{args}</pre>
          {preview !== undefined && (
            <>
              <div className="text-[10px] font-mono text-neutral-500 mb-1">result</div>
              <pre className={`text-[11px] font-mono whitespace-pre-wrap break-all ${ok === false ? "text-red-700" : "text-neutral-700"}`}>{preview || "(empty)"}</pre>
            </>
          )}
        </div>
      )}
      {images.length > 0 && (
        <div className="flex gap-1.5 flex-wrap px-2.5 pb-2">
          {images.map((src, i) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={i} src={src} alt={`${name} output ${i + 1}`} className="h-20 rounded border border-neutral-200 object-cover" loading="lazy" />
          ))}
        </div>
      )}
    </div>
  );
}

export function AgentChat() {
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [model, setModel] = useState<string>("glm-5.3");
  const [caps, setCaps] = useState<Caps | null>(null);
  const [input, setInput] = useState("");
  const [attach, setAttach] = useState<string[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [streamTools, setStreamTools] = useState<LiveTool[]>([]);
  const [statusLine, setStatusLine] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [convOpen, setConvOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const stickBottomRef = useRef(true);
  const residentWatermarkRef = useRef<number>(Date.now());
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const streamTextRef = useRef<string>("");
  const streamToolsRef = useRef<LiveTool[]>([]);

  const active = useMemo(() => convs.find((c) => c.id === activeId), [convs, activeId]);

  // ---- init: load conversations / model / capabilities
  useEffect(() => {
    const stored = loadConversations();
    const m = loadModel("glm-5.3");
    setModel(m);
    if (stored.length > 0) {
      setConvs(stored);
      setActiveId(stored[stored.length - 1].id);
    } else {
      const c = newConversation(m);
      setConvs([c]);
      setActiveId(c.id);
    }
  }, []);

  const refreshCaps = useCallback(async () => {
    try {
      const r = await fetch("/api/agent/capabilities", { cache: "no-store" });
      if (r.ok) setCaps(await r.json());
    } catch {
      /* offline */
    }
  }, []);

  useEffect(() => {
    refreshCaps();
    const t = setInterval(refreshCaps, 30000);
    return () => clearInterval(t);
  }, [refreshCaps]);

  const persist = useCallback((list: Conversation[]) => {
    setConvs([...list]);
    saveConversations(list);
  }, []);

  // ---- resident notes: poll the outbox for new lines
  useEffect(() => {
    let stop = false;
    const poll = async () => {
      try {
        const r = await fetch("/api/inbox", { cache: "no-store" });
        if (!r.ok) return;
        const d = (await r.json()) as { thread: { ts: number; from: string; text: string }[] };
        const fresh = d.thread.filter((m) => m.from === "agent" && m.ts > residentWatermarkRef.current);
        if (fresh.length > 0) {
          residentWatermarkRef.current = Math.max(...fresh.map((f) => f.ts));
          setConvs((prev) => {
            const idx = prev.findIndex((c) => c.id === activeId);
            if (idx < 0) return prev;
            const notes: ChatMsg[] = fresh.map((f) => ({ role: "assistant", resident: true, content: f.text, ts: f.ts }));
            const next = [...prev];
            next[idx] = { ...next[idx], messages: [...next[idx].messages, ...notes], updated: Date.now() };
            saveConversations(next);
            return next;
          });
        }
      } catch {
        /* ignore */
      }
    };
    const t = setInterval(() => !stop && poll(), 5000);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [activeId]);

  // ---- auto-scroll when stuck to bottom
  useEffect(() => {
    const el = listRef.current;
    if (el && stickBottomRef.current) el.scrollTop = el.scrollHeight;
  });

  const onScroll = () => {
    const el = listRef.current;
    if (!el) return;
    stickBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  };

  // ---- sending
  const buildProtocol = (conv: Conversation, withLastImages: boolean): unknown[] => {
    const msgs = conv.messages.filter((m) => !m.resident);
    const lastUserIdx = msgs.map((m) => m.role).lastIndexOf("user");
    return msgs.map((m, i) => {
      const base: Record<string, unknown> = { role: m.role, content: m.content ?? "" };
      if (m.tool_calls) base.tool_calls = m.tool_calls;
      if (m.tool_call_id) base.tool_call_id = m.tool_call_id;
      if (withLastImages && i === lastUserIdx && m.images?.length) base.images = m.images;
      return base;
    });
  };

  const send = async (text: string, images: string[]) => {
    const conv = active;
    if (!conv || streaming) return;
    const clean = text.trim();
    if (!clean && images.length === 0) return;

    const userMsg: ChatMsg = { role: "user", content: clean, images: images.length ? images : undefined, ts: Date.now() };
    const updated: Conversation = {
      ...conv,
      title: conv.messages.length === 0 ? titleFrom(clean || "image") : conv.title,
      messages: [...conv.messages, userMsg],
      updated: Date.now(),
    };
    const list = convs.map((c) => (c.id === conv.id ? updated : c));
    persist(list);
    setInput("");
    setAttach([]);
    setError(null);
    setStreaming(true);
    setStreamText("");
    setStreamTools([]);
    setStatusLine("");
    stickBottomRef.current = true;

    const ctl = new AbortController();
    abortRef.current = ctl;
    const pendingMeta = new Map<string, DisplayMeta>();
    streamTextRef.current = "";
    streamToolsRef.current = [];

    try {
      const r = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: buildProtocol(updated, true), model, conversation_id: conv.id }),
        signal: ctl.signal,
      });
      if (!r.ok || !r.body) throw new Error(`chat endpoint HTTP ${r.status}`);

      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          const t = line.trim();
          if (!t.startsWith("data:")) continue;
          let ev: Record<string, unknown>;
          try {
            ev = JSON.parse(t.slice(5).trim());
          } catch {
            continue;
          }
          switch (ev.type) {
            case "status":
              setStatusLine(String(ev.text ?? ""));
              break;
            case "delta":
              setStreamText((prev) => {
                const next = prev + String(ev.text ?? "");
                streamTextRef.current = next;
                return next;
              });
              setStatusLine("");
              break;
            case "tool_call": {
              const lt: LiveTool = { id: String(ev.id), name: String(ev.name), args: String(ev.args ?? "{}"), images: [], running: true };
              streamToolsRef.current = [...streamToolsRef.current, lt];
              setStreamTools((prev) => [...prev, lt]);
              setStatusLine(`running ${lt.name}…`);
              break;
            }
            case "tool_result": {
              const id = String(ev.id);
              const meta: DisplayMeta = {
                name: String(ev.name),
                preview: String(ev.preview ?? ""),
                images: (ev.images as string[]) ?? [],
                ok: Boolean(ev.ok),
                durationMs: Number(ev.durationMs) || 0,
              };
              pendingMeta.set(id, meta);
              streamToolsRef.current = streamToolsRef.current.map((x) =>
                x.id === id
                  ? { ...x, running: false, ok: Boolean(ev.ok), preview: String(ev.preview ?? ""), durationMs: Number(ev.durationMs) || 0, images: (ev.images as string[]) ?? [] }
                  : x
              );
              setStreamTools((prev) =>
                prev.map((x) =>
                  x.id === id
                    ? { ...x, running: false, ok: Boolean(ev.ok), preview: String(ev.preview ?? ""), durationMs: Number(ev.durationMs) || 0, images: (ev.images as string[]) ?? [] }
                    : x
                )
              );
              setStatusLine("");
              break;
            }
            case "turn_done": {
              // commit protocol messages with display metadata merged in
              const added = (ev.messages as ChatMsg[]) ?? [];
              setConvs((prev) => {
                const idx = prev.findIndex((c) => c.id === conv.id);
                if (idx < 0) return prev;
                const withMeta = added.map((m) => {
                  if (m.role === "tool" && m.tool_call_id && pendingMeta.has(m.tool_call_id)) {
                    return { ...m, meta: pendingMeta.get(m.tool_call_id) };
                  }
                  return m;
                });
                const next = [...prev];
                next[idx] = { ...next[idx], messages: [...next[idx].messages, ...withMeta], updated: Date.now() };
                saveConversations(next);
                return next;
              });
              setStreamText("");
              setStreamTools([]);
              break;
            }
            case "error":
              setError(String(ev.message ?? "unknown error"));
              break;
          }
        }
      }
    } catch (e) {
      if (!ctl.signal.aborted) {
        setError(String(e).slice(0, 300));
      } else {
        // stopped by the operator: keep the partial output as a message
        const partialText = streamTextRef.current;
        const partialTools = streamToolsRef.current;
        if (partialText || partialTools.length) {
          setConvs((prev) => {
            const idx = prev.findIndex((c) => c.id === conv.id);
            if (idx < 0) return prev;
            const partial: ChatMsg[] = [];
            if (partialTools.length) {
              partial.push({
                role: "assistant",
                tool_calls: partialTools.map((t, i) => ({
                  id: t.id || `partial-${i}`,
                  type: "function",
                  function: { name: t.name, arguments: t.args },
                })),
              });
              for (const t of partialTools) {
                partial.push({
                  role: "tool",
                  tool_call_id: t.id,
                  content: t.preview ?? "(stopped before completion)",
                  meta: { name: t.name, preview: t.preview ?? "", ok: t.ok, durationMs: t.durationMs, images: t.images },
                });
              }
            }
            if (partialText) partial.push({ role: "assistant", content: `${partialText}\n\n*(stopped by operator)*` });
            const next = [...prev];
            next[idx] = { ...next[idx], messages: [...next[idx].messages, ...partial], updated: Date.now() };
            saveConversations(next);
            return next;
          });
        }
      }
    } finally {
      setStreaming(false);
      setStatusLine("");
      abortRef.current = null;
      streamTextRef.current = "";
      streamToolsRef.current = [];
      setStreamText("");
      setStreamTools([]);
    }
  };

  const stop = () => {
    abortRef.current?.abort();
  };

  const regenerate = () => {
    if (!active || streaming) return;
    const msgs = [...active.messages];
    while (msgs.length > 0) {
      const last = msgs[msgs.length - 1];
      if (last.role === "user") break;
      msgs.pop();
    }
    // drop the trailing user message too; resend its content
    const lastUser = msgs.pop();
    if (!lastUser) return;
    const restored: Conversation = { ...active, messages: msgs, updated: Date.now() };
    persist(convs.map((c) => (c.id === active.id ? restored : c)));
    setTimeout(() => send(lastUser.content ?? "", lastUser.images ?? []), 30);
  };

  const startNewChat = () => {
    const c = newConversation(model);
    persist([...convs, c]);
    setActiveId(c.id);
    setConvOpen(false);
  };

  const deleteConversation = (id: string) => {
    const list = convs.filter((c) => c.id !== id);
    if (list.length === 0) {
      const c = newConversation(model);
      list.push(c);
    }
    persist(list);
    if (activeId === id) setActiveId(list[list.length - 1].id);
  };

  const onPickFiles = (files: FileList | null) => {
    if (!files) return;
    for (const f of Array.from(files).slice(0, 4)) {
      if (!f.type.startsWith("image/")) continue;
      if (f.size > 8 * 1024 * 1024) continue;
      const reader = new FileReader();
      reader.onload = () => {
        const url = String(reader.result);
        if (url.startsWith("data:")) setAttach((prev) => [...prev, url]);
      };
      reader.readAsDataURL(f);
    }
    if (fileRef.current) fileRef.current.value = "";
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(input, attach);
    }
  };

  const autosize = () => {
    const ta = taRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = `${Math.min(ta.scrollHeight, 180)}px`;
    }
  };

  // ---- render items
  const renderItems: RenderItem[] = useMemo(() => {
    const items: RenderItem[] = [];
    const msgs = active?.messages ?? [];
    for (let i = 0; i < msgs.length; i++) {
      const m = msgs[i];
      if (m.resident) {
        items.push({ kind: "resident", msg: m });
        continue;
      }
      if (m.role === "user") {
        items.push({ kind: "user", msg: m });
        continue;
      }
      if (m.role === "assistant" && m.tool_calls?.length) {
        const calls = m.tool_calls.map((call) => {
          const result = msgs.slice(i + 1).find((x) => x.role === "tool" && x.tool_call_id === call.id);
          return { call, result };
        });
        items.push({ kind: "tools", text: m.content, calls });
        continue;
      }
      if (m.role === "assistant") {
        items.push({ kind: "assistant", msg: m });
        continue;
      }
      // tool messages standalone (shouldn't happen) — skip
    }
    return items;
  }, [active]);

  const hostingBadge = caps
    ? caps.hosting === "self-hosted"
      ? { label: "sandbox · full tools", cls: "text-emerald-700 bg-emerald-50 border-emerald-200" }
      : { label: "serverless · cloud tools", cls: "text-sky-700 bg-sky-50 border-sky-200" }
    : { label: "…", cls: "text-neutral-500 bg-neutral-50 border-neutral-200" };

  const models = caps?.models?.length ? caps.models : MODEL_FALLBACK;
  const toolCount = caps ? Object.values(caps.tools).filter(Boolean).length : 13;

  return (
    <div className="border border-neutral-200 rounded-xl bg-white flex flex-col h-full min-h-0">
      {/* header */}
      <div className="px-3 py-2 border-b border-neutral-200 flex items-center gap-2 flex-wrap">
        <span className="text-sm font-semibold">Agent chat</span>
        <span className={`px-1.5 py-0.5 rounded border text-[10px] font-medium ${hostingBadge.cls}`}>{hostingBadge.label}</span>
        <span className="text-[10px] text-neutral-400 font-mono">{toolCount} tools</span>
        <div className="ml-auto flex items-center gap-1.5">
          <select
            className="text-[11px] border border-neutral-300 rounded px-1.5 py-1 bg-white max-w-[130px]"
            value={model}
            onChange={(e) => {
              setModel(e.target.value);
              saveModel(e.target.value);
            }}
            title="model"
            aria-label="agent model"
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
          <button
            className="text-[11px] px-2 py-1 border border-neutral-300 rounded hover:bg-neutral-100"
            onClick={() => setConvOpen((o) => !o)}
            title="conversations"
          >
            {convs.length} chat{convs.length !== 1 ? "s" : ""} {convOpen ? "▲" : "▼"}
          </button>
          <button
            className="text-[11px] px-2 py-1 bg-neutral-900 text-white rounded hover:bg-neutral-700"
            onClick={startNewChat}
            title="new conversation"
          >
            + New
          </button>
        </div>
      </div>

      {/* conversation list */}
      {convOpen && (
        <div className="border-b border-neutral-200 max-h-40 overflow-y-auto bg-neutral-50">
          {convs.map((c) => (
            <div key={c.id} className={`flex items-center gap-2 px-3 py-1.5 text-[12px] ${c.id === activeId ? "bg-white border-l-2 border-neutral-900" : ""}`}>
              <button
                className="flex-1 text-left truncate hover:underline"
                onClick={() => {
                  setActiveId(c.id);
                  setConvOpen(false);
                }}
              >
                {c.title}
                <span className="text-neutral-400 ml-2">{c.messages.length} msg</span>
              </button>
              <span className="text-[10px] text-neutral-400">{new Date(c.updated).toLocaleDateString()}</span>
              <button className="text-[10px] text-red-500 hover:text-red-700" onClick={() => deleteConversation(c.id)} title="delete">
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {/* thread */}
      <div ref={listRef} onScroll={onScroll} className="flex-1 overflow-y-auto px-3 py-3 min-h-0" aria-label="agent conversation">
        {renderItems.length === 0 && !streaming && (
          <div className="text-center py-10 px-4">
            <div className="text-2xl mb-2">✦</div>
            <p className="text-sm text-neutral-500 font-medium">Message the agent</p>
            <p className="text-xs text-neutral-400 mt-2 leading-relaxed">
              Full agent — GLM-5.3 with {toolCount} tools: bash, the live replay browser, web search,
              images, vision, worker sessions, skills. Ask anything; attach images; watch it work.
            </p>
          </div>
        )}

        {renderItems.map((item, idx) => {
          const key = `${activeId}-${idx}`;
          if (item.kind === "user") {
            return (
              <div key={key} className="flex flex-col items-end mb-3">
                {item.msg.images?.length ? (
                  <div className="flex gap-1.5 flex-wrap justify-end mb-1">
                    {item.msg.images.map((src, i) => (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img key={i} src={src} alt="attachment" className="h-24 rounded-lg border border-neutral-200 object-cover" loading="lazy" />
                    ))}
                  </div>
                ) : null}
                {item.msg.content ? (
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-neutral-900 text-white px-3.5 py-2 text-[13.5px] whitespace-pre-wrap break-words">
                    {item.msg.content}
                  </div>
                ) : null}
                <span className="text-[10px] text-neutral-400 mt-0.5">{timeLabel(item.msg.ts)}</span>
              </div>
            );
          }
          if (item.kind === "resident") {
            return (
              <div key={key} className="mb-3">
                <div className="border border-amber-200 bg-amber-50 rounded-lg px-3 py-2 text-[12.5px] text-amber-900 whitespace-pre-wrap break-words">
                  <span className="text-[10px] font-semibold uppercase tracking-wide opacity-70">resident agent · {timeLabel(item.msg.ts)}</span>
                  <div className="mt-0.5">{item.msg.content}</div>
                </div>
              </div>
            );
          }
          if (item.kind === "tools") {
            return (
              <div key={key} className="mb-2">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="w-5 h-5 rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white text-[9px] flex items-center justify-center font-bold">A</span>
                  <span className="text-[10px] text-neutral-400 font-medium">working…</span>
                </div>
                {item.text ? (
                  <div className="ml-6 mb-1 text-neutral-800">
                    <Markdown text={item.text} />
                  </div>
                ) : null}
                <div className="ml-6">
                  {item.calls.map(({ call, result }) => {
                    const meta = result?.meta;
                    const live: LiveTool = {
                      id: call.id,
                      name: call.function.name,
                      args: call.function.arguments,
                      preview: meta?.preview ?? result?.content ?? "",
                      ok: meta?.ok,
                      durationMs: meta?.durationMs,
                      images: meta?.images ?? [],
                      running: false,
                    };
                    return <ToolCard key={call.id} {...live} />;
                  })}
                </div>
              </div>
            );
          }
          // assistant text
          return (
            <div key={key} className="mb-3 group">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="w-5 h-5 rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white text-[9px] flex items-center justify-center font-bold">A</span>
                <span className="text-[10px] text-neutral-400 font-medium">
                  {models.find((m) => m.id === model)?.label ?? "GLM"} · {timeLabel(item.msg.ts)}
                </span>
                <button
                  className="ml-auto text-[10px] text-neutral-400 hover:text-neutral-700 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => navigator.clipboard?.writeText(item.msg.content ?? "")}
                  title="copy"
                >
                  copy
                </button>
              </div>
              <div className="ml-6 text-neutral-900">
                <Markdown text={item.msg.content ?? ""} />
              </div>
            </div>
          );
        })}

        {/* live streaming block */}
        {streaming && (
          <div className="mb-3">
            <div className="flex items-center gap-1.5 mb-1">
              <span className="w-5 h-5 rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white text-[9px] flex items-center justify-center font-bold animate-pulse">A</span>
              <span className="text-[10px] text-neutral-400 font-medium">{statusLine || "thinking…"}</span>
            </div>
            {streamTools.length > 0 && (
              <div className="ml-6 mb-1">
                {streamTools.map((t, i) => (
                  <ToolCard key={`${t.id}-${i}`} {...t} />
                ))}
              </div>
            )}
            {streamText && (
              <div className="ml-6 text-neutral-900">
                <Markdown text={streamText} />
              </div>
            )}
            {!streamText && streamTools.length === 0 && (
              <div className="ml-6 flex gap-1 items-center h-4">
                <span className="w-1.5 h-1.5 rounded-full bg-neutral-400 animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-1.5 h-1.5 rounded-full bg-neutral-400 animate-bounce" style={{ animationDelay: "120ms" }} />
                <span className="w-1.5 h-1.5 rounded-full bg-neutral-400 animate-bounce" style={{ animationDelay: "240ms" }} />
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="border border-red-200 bg-red-50 text-red-700 rounded-lg px-3 py-2 text-[12px] mb-2">{error}</div>
        )}
      </div>

      {/* composer */}
      <div className="border-t border-neutral-200 px-3 py-2.5 pb-[max(0.625rem,env(safe-area-inset-bottom))]">
        {attach.length > 0 && (
          <div className="flex gap-1.5 flex-wrap mb-2">
            {attach.map((src, i) => (
              <div key={i} className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={src} alt="attachment" className="h-16 rounded-lg border border-neutral-200 object-cover" />
                <button
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-neutral-800 text-white text-[10px] leading-none"
                  onClick={() => setAttach((prev) => prev.filter((_, j) => j !== i))}
                  aria-label="remove attachment"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <button
            className="w-8 h-8 rounded-lg border border-neutral-300 hover:bg-neutral-100 flex items-center justify-center text-neutral-500 shrink-0"
            onClick={() => fileRef.current?.click()}
            title="attach image"
            aria-label="attach image"
          >
            +
          </button>
          <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={(e) => onPickFiles(e.target.files)} />
          <textarea
            ref={taRef}
            className="flex-1 resize-none border border-neutral-300 rounded-xl px-3 py-2 text-[13.5px] focus:outline-none focus:ring-2 focus:ring-violet-400 max-h-[180px]"
            rows={1}
            placeholder="message the agent — Enter to send, Shift+Enter for a new line"
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              autosize();
            }}
            onKeyDown={onKey}
            disabled={streaming}
            aria-label="message to the agent"
          />
          {streaming ? (
            <button
              className="h-8 px-3 rounded-xl bg-red-600 hover:bg-red-700 text-white text-[12px] font-medium shrink-0"
              onClick={stop}
            >
              ■ Stop
            </button>
          ) : (
            <>
              {active && active.messages.length > 0 && (
                <button
                  className="h-8 px-2.5 rounded-xl border border-neutral-300 hover:bg-neutral-100 text-[12px] text-neutral-600 shrink-0"
                  onClick={regenerate}
                  title="regenerate last reply"
                >
                  ↻
                </button>
              )}
              <button
                className="h-8 px-3 rounded-xl bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-700 hover:to-fuchsia-700 text-white text-[12px] font-medium shrink-0 disabled:opacity-40"
                onClick={() => send(input, attach)}
                disabled={!input.trim() && attach.length === 0}
              >
                Send ↑
              </button>
            </>
          )}
        </div>
        <div className="text-[10px] text-neutral-400 mt-1 truncate">
          {caps?.sdk === false ? "model backend offline — set ZAI_BASE_URL/ZAI_API_KEY" : "GLM agent · tools stream results live · resident notes appear inline"}
        </div>
      </div>
    </div>
  );
}
