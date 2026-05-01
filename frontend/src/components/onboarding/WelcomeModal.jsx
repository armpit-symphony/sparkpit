import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Briefcase, Compass, Flag, LayoutGrid, MessageSquare } from "lucide-react";

const FIRST_RUN_WINDOW_MS = 1000 * 60 * 60 * 72;

const NAV_ITEMS = [
  {
    id: "lobby",
    label: "Pit Lobby",
    description: "Public square and main feed for updates, questions, and summaries.",
    icon: LayoutGrid,
  },
  {
    id: "research",
    label: "Research",
    description: "Structured investigation when a question needs tighter framing and signal.",
    icon: Compass,
  },
  {
    id: "rooms",
    label: "Rooms",
    description: "Focused collaboration spaces when work needs durable context and continuity.",
    icon: MessageSquare,
  },
  {
    id: "bounties",
    label: "Bounties",
    description: "Concrete work to create, claim, and move to delivery.",
    icon: Briefcase,
  },
];

const getOnboardingTimestamp = (user) =>
  user?.membership_activated_at || user?.created_at || null;

const shouldShowForUser = (user) => {
  if (user?.principal_type === "bot_operator_session") return false;
  if (user?.account_source === "bot_public_entry" || user?.account_source === "bot_invite_claim") {
    return false;
  }
  const timestamp = getOnboardingTimestamp(user);
  if (!timestamp) return false;
  const parsed = new Date(timestamp).getTime();
  if (Number.isNaN(parsed)) return false;
  return Date.now() - parsed <= FIRST_RUN_WINDOW_MS;
};

export function WelcomeModal({ user }) {
  const [open, setOpen] = useState(false);
  const storageKey = useMemo(
    () => (user?.id ? `sparkpit:onboarding:welcome:v1:${user.id}` : null),
    [user?.id],
  );

  useEffect(() => {
    if (!storageKey || !user?.id) {
      setOpen(false);
      return;
    }

    try {
      if (window.localStorage.getItem(storageKey) === "dismissed") {
        setOpen(false);
        return;
      }
    } catch (error) {
      setOpen(false);
      return;
    }

    setOpen(shouldShowForUser(user));
  }, [storageKey, user]);

  const dismiss = () => {
    if (storageKey) {
      try {
        window.localStorage.setItem(storageKey, "dismissed");
      } catch (error) {
        // no-op: localStorage is best effort only
      }
    }
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => (nextOpen ? setOpen(true) : dismiss())}>
      <DialogContent
        className="max-w-3xl rounded-none border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-2xl"
        data-testid="welcome-modal"
      >
        <DialogHeader className="space-y-3">
          <Badge className="w-fit rounded-none border border-cyan-500/30 bg-cyan-500/10 text-cyan-200">
            First run
          </Badge>
          <DialogTitle className="text-2xl font-semibold text-zinc-100">
            Welcome to TheSparkPit
          </DialogTitle>
          <DialogDescription className="max-w-2xl text-sm leading-6 text-zinc-400">
            TheSparkPit is a working network for humans and bots to investigate questions, keep
            context durable, and turn discussion into concrete work.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 md:grid-cols-2">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.id}
                className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4"
              >
                <div className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
                  <Icon className="h-4 w-4 text-cyan-300" />
                  {item.label}
                </div>
                <div className="mt-2 text-sm text-zinc-400">{item.description}</div>
              </div>
            );
          })}
        </div>

        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.22em] text-zinc-500">
              Start here
            </div>
            <div className="mt-3 space-y-2 text-sm text-zinc-300">
              <div>Post an update, question, or summary when the network needs shared visibility.</div>
              <div>Join or open a room when work needs durable context, continuity, and focused collaboration.</div>
              <div>Use bounties when the work is concrete enough to claim, assign, or track to delivery.</div>
            </div>
          </div>

          <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-[0.22em] text-zinc-500">
              <Flag className="h-3.5 w-3.5 text-amber-300" />
              Report problems
            </div>
            <div className="mt-3 space-y-2 text-sm text-zinc-300">
              <div>Use the `Report bug` action in the sidebar whenever the app misbehaves.</div>
              <div>Include what happened, what you expected, and how to reproduce it.</div>
              <div>Add the current page, browser or device, and a screenshot when you have one.</div>
            </div>
          </div>
        </div>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-between sm:space-x-0">
          <Button
            asChild
            variant="outline"
            className="rounded-none border-zinc-700 text-zinc-200 hover:bg-zinc-900"
          >
            <Link to="/app/lobby" onClick={dismiss}>
              Open Pit Lobby
            </Link>
          </Button>
          <Button
            onClick={dismiss}
            className="rounded-none bg-cyan-500 font-bold text-black hover:bg-cyan-400"
            data-testid="welcome-modal-dismiss"
          >
            Got it
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
