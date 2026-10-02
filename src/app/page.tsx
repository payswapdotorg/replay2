"use client";

import { useState } from "react";
import Console from "@/components/replay-console";
import { MissionControl } from "@/components/mission-control";
import { AgentChat } from "@/components/AgentChat";
import { MonitorPlay, Radar, MessagesSquare } from "lucide-react";

type View = "replay" | "mission" | "agent";

export default function Home() {
  const [view, setView] = useState<View>("replay");

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      {/* View switcher — Replay Console is the live window into the sandbox
          browser (worker dispatch happens there); Mission Control is the
          roadmap / delivery dashboard; Agent Chat is the full GLM-5.3
          conversation plane with tools + skills (PR #1's section). */}
      <div className="sticky top-0 z-50 border-b border-neutral-800 bg-neutral-950/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-3 py-2 sm:px-6">
          <div
            className="flex items-center gap-1 rounded-lg border border-neutral-800 bg-neutral-900 p-1"
            role="tablist"
            aria-label="Console views"
          >
            <button
              role="tab"
              aria-selected={view === "replay"}
              onClick={() => setView("replay")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors sm:text-sm ${
                view === "replay"
                  ? "bg-neutral-100 text-neutral-900"
                  : "text-neutral-400 hover:text-neutral-100"
              }`}
            >
              <MonitorPlay className="h-3.5 w-3.5" aria-hidden="true" />
              Replay Console
            </button>
            <button
              role="tab"
              aria-selected={view === "mission"}
              onClick={() => setView("mission")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors sm:text-sm ${
                view === "mission"
                  ? "bg-neutral-100 text-neutral-900"
                  : "text-neutral-400 hover:text-neutral-100"
              }`}
            >
              <Radar className="h-3.5 w-3.5" aria-hidden="true" />
              Mission Control
            </button>
            <button
              role="tab"
              aria-selected={view === "agent"}
              onClick={() => setView("agent")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors sm:text-sm ${
                view === "agent"
                  ? "bg-neutral-100 text-neutral-900"
                  : "text-neutral-400 hover:text-neutral-100"
              }`}
            >
              <MessagesSquare className="h-3.5 w-3.5" aria-hidden="true" />
              Agent Chat
            </button>
          </div>
          <p className="hidden text-[11px] text-neutral-500 sm:block">
            Project-agnostic console · workers are dispatched inside the replay
          </p>
        </div>
      </div>

      {view === "replay" ? (
        <Console />
      ) : view === "mission" ? (
        <MissionControl />
      ) : (
        <AgentChat />
      )}
    </div>
  );
}
