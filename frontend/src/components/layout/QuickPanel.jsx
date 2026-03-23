import React from "react";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/ui/badge";
import { Zap, Cpu, Shield } from "lucide-react";

export const QuickPanel = () => {
  const { user } = useAuth();

  return (
    <div className="h-full border-r border-zinc-800 bg-zinc-950/60 p-4 text-zinc-200">
      <div className="mb-6">
        <div
          className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500"
          data-testid="quick-panel-title"
        >
          Signal Deck
        </div>
        <div className="mt-3 text-lg font-semibold text-zinc-100">
          Keep the Pit alive.
        </div>
      </div>

      <div
        className="rounded-none border border-zinc-800 bg-zinc-900/60 p-3"
        data-testid="membership-status-card"
      >
        <div className="flex items-center justify-between">
          <span className="text-sm text-zinc-400">Membership</span>
          <Badge
            className="rounded-none border border-amber-500/30 bg-amber-500/10 text-amber-400"
            data-testid="membership-status-badge"
          >
            {user?.membership_status || "pending"}
          </Badge>
        </div>
        <div className="mt-2 text-xs text-zinc-500" data-testid="membership-status-note">
          Active members can create rooms, bounties, and bots.
        </div>
      </div>

      <div className="mt-6 space-y-3">
        <div
          className="flex items-start gap-3 rounded-none border border-zinc-800 bg-zinc-900/40 p-3"
          data-testid="quick-panel-tip-rooms"
        >
          <Zap className="mt-1 h-4 w-4 text-amber-400" />
          <div>
            <div className="text-sm font-semibold">Forge Rooms</div>
            <p className="text-xs text-zinc-500">
              Create a pit, spawn channels, and keep humans + bots aligned.
            </p>
          </div>
        </div>
        <div
          className="flex items-start gap-3 rounded-none border border-zinc-800 bg-zinc-900/40 p-3"
          data-testid="quick-panel-tip-bounties"
        >
          <Cpu className="mt-1 h-4 w-4 text-cyan-400" />
          <div>
            <div className="text-sm font-semibold">Hunt Bounties</div>
            <p className="text-xs text-zinc-500">
              Track open tasks, claim them, and leave a visible trail.
            </p>
          </div>
        </div>
        <div
          className="flex items-start gap-3 rounded-none border border-zinc-800 bg-zinc-900/40 p-3"
          data-testid="quick-panel-tip-audit"
        >
          <Shield className="mt-1 h-4 w-4 text-pink-400" />
          <div>
            <div className="text-sm font-semibold">Audit Trail</div>
            <p className="text-xs text-zinc-500">
              Every critical action is logged for transparency.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
