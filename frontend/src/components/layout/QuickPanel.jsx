import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useAppData } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import {
  Bot,
  Briefcase,
  ChevronLeft,
  ChevronRight,
  FolderKanban,
  RadioTower,
  Shield,
  Users,
} from "lucide-react";

const ACTIVE_BOUNTY_STATES = new Set(["open", "claimed", "submitted"]);
const OPEN_TASK_STATES = new Set(["open", "claimed", "in_progress"]);

const formatRelativeTime = (value) => {
  if (!value) return "No recent event";

  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "No recent event";

  const deltaMinutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
  if (deltaMinutes < 1) return "Just now";
  if (deltaMinutes < 60) return `${deltaMinutes}m ago`;

  const deltaHours = Math.floor(deltaMinutes / 60);
  if (deltaHours < 24) return `${deltaHours}h ago`;

  const deltaDays = Math.floor(deltaHours / 24);
  return `${deltaDays}d ago`;
};

export const QuickPanel = ({ collapsed = false, onToggleCollapsed }) => {
  const { user } = useAuth();
  const { rooms } = useAppData();
  const [panelData, setPanelData] = useState({
    bounties: [],
    tasks: [],
    bots: [],
    auditEvents: [],
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    const loadPanelData = async () => {
      try {
        const requests = [
          api.get("/bounties"),
          api.get("/tasks"),
          api.get("/bots"),
        ];

        if (user?.role === "admin") {
          requests.push(api.get("/admin/audit"));
        }

        const [bountiesResponse, tasksResponse, botsResponse, auditResponse] =
          await Promise.allSettled(requests);

        if (!active) return;

        setPanelData({
          bounties:
            bountiesResponse.status === "fulfilled"
              ? bountiesResponse.value.data.items || []
              : [],
          tasks:
            tasksResponse.status === "fulfilled"
              ? tasksResponse.value.data.items || []
              : [],
          bots:
            botsResponse.status === "fulfilled" ? botsResponse.value.data.items || [] : [],
          auditEvents:
            auditResponse?.status === "fulfilled"
              ? auditResponse.value.data.items || []
              : [],
        });
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadPanelData();
    const interval = setInterval(loadPanelData, 20000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [user?.role]);

  const summary = useMemo(() => {
    const openBounties = panelData.bounties.filter((bounty) =>
      ACTIVE_BOUNTY_STATES.has(bounty.status),
    ).length;
    const openTasks = panelData.tasks.filter((task) =>
      OPEN_TASK_STATES.has(task.state || task.status || "open"),
    ).length;
    const onlineBots = panelData.bots.filter(
      (bot) => (bot.presence?.status || bot.status) === "online",
    ).length;
    const latestAudit = panelData.auditEvents[0] || null;

    return {
      roomsCount: rooms.length,
      openBounties,
      openTasks,
      onlineBots,
      totalBots: panelData.bots.length,
      auditCount: panelData.auditEvents.length,
      latestAudit,
      starterMode:
        rooms.length === 0 &&
        panelData.bounties.length === 0 &&
        panelData.tasks.length === 0 &&
        panelData.bots.length === 0,
    };
  }, [panelData, rooms.length]);

  const signalCards = [
    {
      label: "Access",
      value: user ? "open" : "offline",
      accent: "text-amber-300",
      icon: Shield,
    },
    {
      label: "Rooms",
      value: summary.roomsCount,
      accent: "text-zinc-100",
      icon: Users,
    },
    {
      label: "Open bounties",
      value: summary.openBounties,
      accent: "text-cyan-300",
      icon: Briefcase,
    },
    {
      label: "Open tasks",
      value: summary.openTasks,
      accent: "text-emerald-300",
      icon: FolderKanban,
    },
  ];

  if (collapsed) {
    return (
      <div className="flex h-full flex-col items-center gap-3 border-r border-zinc-800 bg-zinc-950/60 px-2 py-4 text-zinc-200">
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="flex w-full flex-col items-center gap-2 rounded-none border border-zinc-800 bg-zinc-900/70 px-2 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
          data-testid="quick-panel-toggle-collapsed"
        >
          <ChevronRight className="h-4 w-4 text-cyan-300" />
          Context
        </button>

        <div className="grid w-full gap-2">
          <Link
            to="/app/rooms"
            className="flex h-11 items-center justify-center rounded-none border border-zinc-800 bg-zinc-900/50 text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
            title="Rooms"
          >
            <Users className="h-4 w-4 text-zinc-100" />
          </Link>
          <Link
            to="/app/bounties"
            className="flex h-11 items-center justify-center rounded-none border border-zinc-800 bg-zinc-900/50 text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
            title="Bounties"
          >
            <Briefcase className="h-4 w-4 text-cyan-300" />
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
              {loading ? "..." : summary.roomsCount}
            </Badge>
          </div>
          <div className="flex h-11 items-center justify-center rounded-none border border-zinc-800 bg-zinc-900/50">
            <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
              {loading ? "..." : summary.openTasks + summary.openBounties}
            </Badge>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full border-r border-zinc-800 bg-zinc-950/60 p-4 text-zinc-200">
      <div className="mb-6 flex items-start justify-between gap-3">
        <div>
          <div
            className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500"
            data-testid="quick-panel-title"
          >
            Signal Deck
          </div>
          <div className="mt-3 text-lg font-semibold text-zinc-100">
            Command state
          </div>
          <div className="mt-2 max-w-[18rem] text-xs leading-5 text-zinc-500">
            Rooms, bounties, bots, and audit trails for coordinated work.
          </div>
        </div>
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="rounded-none border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
          data-testid="quick-panel-toggle-expanded"
        >
          <span className="flex items-center gap-2">
            <ChevronLeft className="h-4 w-4 text-cyan-300" />
            Collapse
          </span>
        </button>
      </div>

      <div className="grid gap-3" data-testid="quick-panel-signals">
        {signalCards.map(({ label, value, accent, icon: Icon }) => (
          <div
            key={label}
            className="rounded-none border border-zinc-800 bg-zinc-900/60 p-3"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-[0.2em] text-zinc-500">{label}</span>
              <Icon className="h-3.5 w-3.5 text-zinc-600" />
            </div>
            <div className={`mt-3 text-lg font-semibold ${accent}`}>
              {loading ? "..." : value}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 rounded-none border border-zinc-800 bg-zinc-900/40 p-3">
        <div className="flex items-center justify-between">
          <div className="text-xs font-mono uppercase tracking-[0.2em] text-zinc-500">
            Recent pulse
          </div>
          <Badge className="rounded-none border border-zinc-700 bg-zinc-950/70 text-zinc-300">
            {user?.role === "admin" ? `${summary.auditCount} audit` : `${summary.totalBots} bots`}
          </Badge>
        </div>

        <div className="mt-3 flex items-start gap-3">
          <RadioTower className="mt-0.5 h-4 w-4 text-pink-400" />
          <div className="min-w-0">
            {user?.role === "admin" ? (
              <>
                <div className="text-sm font-semibold text-zinc-100">
                  {summary.latestAudit?.event_type || "Audit feed quiet"}
                </div>
                <div className="mt-1 text-xs text-zinc-500">
                  {summary.latestAudit
                    ? `${formatRelativeTime(summary.latestAudit.created_at)} in admin audit`
                    : "Critical actions will appear here once operators start making moves."}
                </div>
              </>
            ) : (
              <>
                <div className="text-sm font-semibold text-zinc-100">
                  {summary.onlineBots > 0
                    ? `${summary.onlineBots} bot${summary.onlineBots === 1 ? "" : "s"} online`
                    : "Bots standing by"}
                </div>
                <div className="mt-1 text-xs text-zinc-500">
                  {summary.totalBots > 0
                    ? "Registry is live. Bring bots into rooms when work needs extra hands."
                    : "No bot profiles yet. Register one when the first workflow needs automation."}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {summary.starterMode && (
        <div
          className="mt-6 rounded-none border border-amber-500/20 bg-amber-500/5 p-3"
          data-testid="quick-panel-starter-mode"
        >
          <div className="text-xs font-mono uppercase tracking-[0.2em] text-amber-300">
            First moves
          </div>
          <div className="mt-3 space-y-2 text-xs text-zinc-400">
            <div>Forge a room to give work a place to land.</div>
            <div>Post the first bounty to define the mission.</div>
            <div>Register a bot only when a room has work to automate.</div>
          </div>
          <div className="mt-4 flex flex-col gap-2">
            <Link
              to="/app/rooms"
              className="rounded-none border border-zinc-700 px-3 py-2 text-center text-xs font-semibold text-zinc-200 transition-colors hover:border-zinc-500 hover:bg-zinc-900/80"
            >
              Open rooms
            </Link>
            <Link
              to="/app/bounties"
              className="rounded-none border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-center text-xs font-semibold text-cyan-200 transition-colors hover:border-cyan-400/40 hover:bg-cyan-500/15"
            >
              Open mission board
            </Link>
          </div>
        </div>
      )}
    </div>
  );
};
