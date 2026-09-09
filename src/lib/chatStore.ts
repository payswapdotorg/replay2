"use client";

/**
 * Client-side conversation store (localStorage) — serverless-safe: the
 * protocol history lives on the client and is sent with each request, so
 * no server-side session state is required. Vercel and sandbox behave
 * identically.
 */

export type ToolCallRec = { id: string; type: "function"; function: { name: string; arguments: string } };

export type DisplayMeta = {
  name?: string;
  args?: string;
  preview?: string;
  images?: string[];
  durationMs?: number;
  ok?: boolean;
};

export type ChatMsg = {
  role: "user" | "assistant" | "tool";
  content?: string;
  images?: string[]; // user attachments (data URLs, display-only)
  tool_calls?: ToolCallRec[]; // assistant
  tool_call_id?: string; // tool
  meta?: DisplayMeta; // tool display metadata (client-only)
  resident?: boolean; // resident CLI agent note (client-only)
  ts?: number;
};

export type Conversation = {
  id: string;
  title: string;
  created: number;
  updated: number;
  model: string;
  messages: ChatMsg[];
};

const KEY = "replay-agent-chats-v1";
const MODEL_KEY = "replay-agent-model";

export function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw) as Conversation[];
    return Array.isArray(arr) ? arr.filter((c) => c && c.id && Array.isArray(c.messages)) : [];
  } catch {
    return [];
  }
}

export function saveConversations(list: Conversation[]) {
  try {
    // cap stored size: keep last 12 conversations, 400 messages total
    const trimmed = list.slice(-12).map((c) => ({
      ...c,
      messages: c.messages.slice(-400).map((m) => ({
        ...m,
        images: (m.images ?? []).map((i) => (i.length > 300000 ? "" : i)).filter(Boolean),
      })),
    }));
    localStorage.setItem(KEY, JSON.stringify(trimmed));
  } catch {
    // quota exceeded — drop oldest conversation and retry once
    try {
      const shrunk = list.slice(-4);
      localStorage.setItem(
        KEY,
        JSON.stringify(shrunk.map((c) => ({ ...c, messages: c.messages.slice(-60) })))
      );
    } catch {
      /* give up silently */
    }
  }
}

export function newConversation(model: string): Conversation {
  return {
    id: `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    title: "New chat",
    created: Date.now(),
    updated: Date.now(),
    model,
    messages: [],
  };
}

export function loadModel(defaultModel: string): string {
  try {
    return localStorage.getItem(MODEL_KEY) || defaultModel;
  } catch {
    return defaultModel;
  }
}

export function saveModel(m: string) {
  try {
    localStorage.setItem(MODEL_KEY, m);
  } catch {
    /* ignore */
  }
}

export function titleFrom(text: string): string {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > 42 ? `${clean.slice(0, 42)}…` : clean || "New chat";
}
