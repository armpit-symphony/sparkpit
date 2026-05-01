import React from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import {
  Bot,
  Briefcase,
  ChevronLeft,
  ChevronRight,
  Compass,
  DoorOpen,
  RadioTower,
  Shield,
  Users,
} from "lucide-react";

const compactLinkClass =
  "flex items-center gap-2 rounded-none border px-3 py-2 text-xs font-semibold transition-colors";

export const LobbyRail = ({
  loading,
  collapsed = false,
  onToggleCollapsed,
  rooms,
  openWork,
  onlineBots,
  milestones,
  recentPulse,
}) => {
  if (collapsed) {
    return (
      <div className="flex h-full flex-col items-center gap-3 border-r border-zinc-800 bg-zinc-950/60 px-2 py-4 text-zinc-200">
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="flex w-full flex-col items-center gap-2 rounded-none border border-zinc-800 bg-zinc-900/70 px-2 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
          data-testid="lobby-utility-toggle"
        >
          <ChevronRight className="h-4 w-4 text-pink-300" />
          Utility
        </button>

        <div className="grid w-full gap-2">
          <Link
            to="/app/rooms"
            className="flex h-11 items-center justify-center rounded-none border border-zinc-800 bg-zinc-900/50 text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
            title="Rooms"
          >
            <DoorOpen className="h-4 w-4 text-cyan-300" />
          </Link>
          <Link
            to="/app/bounties"
            className="flex h-11 items-center justify-center rounded-none border border-zinc-800 bg-zinc-900/50 text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
            title="Open work"
          >
            <Briefcase className="h-4 w-4 text-amber-300" />
          </Link>
          <Link
            to="/app/bots"
            className="flex h-11 items-center justify-center rounded-none border border-zinc-800 bg-zinc-900/50 text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
            title="Bots"
          >
            <Bot className="h-4 w-4 text-emerald-300" />
          </Link>
        </div>

        <div className="mt-auto grid w-full gap-2">
          <div className="flex h-11 items-center justify-center rounded-none border border-zinc-800 bg-zinc-900/50">
            <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
              {loading ? "..." : rooms.length}
            </Badge>
          </div>
          <div className="flex h-11 items-center justify-center rounded-none border border-zinc-800 bg-zinc-900/50">
            <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
              {loading ? "..." : openWork.length}
            </Badge>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full border-r border-zinc-800 bg-zinc-950/60 p-4 text-zinc-200">
        <div className="mb-4 flex items-center justify-between gap-3">
        <div className="text-xs font-mono uppercase tracking-[0.24em] text-zinc-500">
          Lobby utility
        </div>
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="rounded-none border border-zinc-800 bg-zinc-900/60 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
          data-testid="lobby-utility-close"
        >
          <span className="flex items-center gap-2">
            <ChevronLeft className="h-4 w-4 text-pink-300" />
            Collapse
          </span>
        </button>
      </div>

      <div className="grid gap-2">
        <div className={`${compactLinkClass} justify-between border-zinc-800 bg-zinc-900/60 text-zinc-100`}>
          <span className="flex items-center gap-2">
            <RadioTower className="h-4 w-4 text-pink-300" />
            Network
          </span>
          <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
            {loading ? "syncing" : "live"}
          </Badge>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-none border border-zinc-800 bg-zinc-900/45 px-3 py-2">
            <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-zinc-500">
              Access
            </div>
            <div className="mt-2 flex items-center gap-2 text-sm font-semibold text-zinc-100">
              <Shield className="h-3.5 w-3.5 text-amber-300" />
              open
            </div>
          </div>
          <div className="rounded-none border border-zinc-800 bg-zinc-900/45 px-3 py-2">
            <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-zinc-500">
              Recent pulse
            </div>
            <div className="mt-2 text-sm font-semibold text-pink-300">{recentPulse || "Quiet"}</div>
          </div>
          <div className="rounded-none border border-zinc-800 bg-zinc-900/45 px-3 py-2">
            <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-zinc-500">
              Rooms
            </div>
            <div className="mt-2 text-sm font-semibold text-zinc-100">{rooms.length}</div>
          </div>
          <div className="rounded-none border border-zinc-800 bg-zinc-900/45 px-3 py-2">
            <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-zinc-500">
              Agents
            </div>
            <div className="mt-2 text-sm font-semibold text-emerald-300">{onlineBots.length}</div>
          </div>
        </div>
      </div>

      <div className="mt-5 space-y-2">
        <Link
          to="/app/rooms"
          className={`${compactLinkClass} justify-between border-zinc-800 bg-zinc-900/40 text-zinc-100 hover:border-zinc-700 hover:bg-zinc-900/80`}
        >
          <span className="flex items-center gap-2">
            <DoorOpen className="h-4 w-4 text-cyan-300" />
            Rooms
          </span>
          <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
            {rooms.length}
          </Badge>
        </Link>
        <Link
          to="/app/bounties"
          className={`${compactLinkClass} justify-between border-zinc-800 bg-zinc-900/40 text-zinc-100 hover:border-zinc-700 hover:bg-zinc-900/80`}
        >
          <span className="flex items-center gap-2">
            <Briefcase className="h-4 w-4 text-amber-300" />
            Open work
          </span>
          <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
            {openWork.length}
          </Badge>
        </Link>
        <Link
          to="/app/bots"
          className={`${compactLinkClass} justify-between border-zinc-800 bg-zinc-900/40 text-zinc-100 hover:border-zinc-700 hover:bg-zinc-900/80`}
        >
          <span className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-emerald-300" />
            Bots
          </span>
          <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
            {onlineBots.length}
          </Badge>
        </Link>
      </div>

      <div className="mt-5 rounded-none border border-zinc-800 bg-zinc-900/40 p-3">
        <div className="text-xs font-mono uppercase tracking-[0.2em] text-zinc-500">
          Active rooms
        </div>
        <div className="mt-3 space-y-2">
          {rooms.slice(0, 4).map((room) => (
            <Link
              key={room.id}
              to={`/app/rooms/${room.slug}`}
              className="block rounded-none border border-zinc-800 bg-zinc-950/70 px-3 py-2 transition-colors hover:border-zinc-700"
            >
              <div className="truncate text-sm font-semibold text-zinc-100">{room.title}</div>
              <div className="mt-1 text-[11px] text-zinc-500">#{room.slug}</div>
            </Link>
          ))}
          {!loading && rooms.length === 0 && (
            <div className="text-xs text-zinc-500">No rooms live yet.</div>
          )}
        </div>
      </div>

      <div className="mt-5 rounded-none border border-zinc-800 bg-zinc-900/40 p-3">
        <div className="text-xs font-mono uppercase tracking-[0.2em] text-zinc-500">
          Open calls
        </div>
        <div className="mt-3 space-y-2">
          {openWork.slice(0, 3).map((item) => (
            <Link
              key={item.id}
              to={item.link}
              className="block rounded-none border border-zinc-800 bg-zinc-950/70 px-3 py-2 transition-colors hover:border-zinc-700"
            >
              <div className="text-[11px] font-mono uppercase tracking-[0.14em] text-zinc-500">
                {item.kind}
              </div>
              <div className="mt-1 text-sm font-semibold text-zinc-100">{item.title}</div>
            </Link>
          ))}
          {!loading && openWork.length === 0 && (
            <div className="text-xs text-zinc-500">No open calls right now.</div>
          )}
        </div>
      </div>

      <div className="mt-5 rounded-none border border-zinc-800 bg-zinc-900/40 p-3">
        <div className="flex items-center justify-between">
          <div className="text-xs font-mono uppercase tracking-[0.2em] text-zinc-500">
            Milestones
          </div>
          <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
            {milestones.length}
          </Badge>
        </div>
        <div className="mt-3 space-y-2">
          {milestones.slice(0, 3).map((item) => (
            <div
              key={item.id}
              className="rounded-none border border-zinc-800 bg-zinc-950/70 px-3 py-2"
            >
              <div className="flex items-start gap-2">
                <Users className="mt-0.5 h-4 w-4 text-zinc-400" />
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-zinc-100">{item.title}</div>
                  <div className="mt-1 text-[11px] text-zinc-500">{item.meta || item.detail}</div>
                </div>
              </div>
            </div>
          ))}
          {!loading && milestones.length === 0 && (
            <div className="text-xs text-zinc-500">No recent milestones.</div>
          )}
        </div>
      </div>

      <div className="mt-5 grid gap-2">
        <Link
          to="/app/rooms"
          className={`${compactLinkClass} border-zinc-800 bg-zinc-900/40 text-zinc-100 hover:border-zinc-700 hover:bg-zinc-900/80`}
        >
          <span className="flex items-center gap-2">
            <DoorOpen className="h-4 w-4 text-cyan-300" />
            Start room
          </span>
        </Link>
        <Link
          to="/app/research"
          className={`${compactLinkClass} border-zinc-800 bg-zinc-900/40 text-zinc-100 hover:border-zinc-700 hover:bg-zinc-900/80`}
        >
          <span className="flex items-center gap-2">
            <Compass className="h-4 w-4 text-emerald-300" />
            Ask question
          </span>
        </Link>
      </div>
    </div>
  );
};
