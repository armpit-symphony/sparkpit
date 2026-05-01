import React, { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/context/AuthContext";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Activity,
  Bot,
  Briefcase,
  Compass,
  Flag,
  LayoutGrid,
  Lock,
  MessageSquare,
  Settings,
  Shield,
  Wrench,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAppData } from "@/components/layout/AppShell";
import { toast } from "@/components/ui/sonner";

export const RoomsSidebar = () => {
  const { rooms, refreshRooms, loadingRooms } = useAppData();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    title: "",
    slug: "",
    is_public: true,
    room_type: "research",
  });
  const navigate = useNavigate();
  const location = useLocation();
  const isAdmin = user?.role === "admin";
  const isActive = (path) => location.pathname.startsWith(path);
  const joinedRooms = rooms.filter((room) => room.joined);
  const visibleRooms = joinedRooms.length > 0 ? joinedRooms : rooms;
  const activeJoinedRooms = joinedRooms.filter((room) => !room.archived).length;
  const roomSoftCap = 3;
  const nearRoomCap = activeJoinedRooms >= roomSoftCap;
  const navItemClass = (active) =>
    `flex items-center gap-2 rounded-none border px-2 py-2 transition-colors ${
      active
        ? "border-amber-500/40 bg-zinc-900/80 text-zinc-100"
        : "border-transparent text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
    }`;
  const primaryModeClass = (active) =>
    `flex items-center gap-2 rounded-none border px-3 py-2 text-sm font-semibold transition-colors ${
      active
        ? "border-cyan-500/35 bg-cyan-500/10 text-cyan-200"
        : "border-zinc-800 bg-zinc-900/50 text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
    }`;
  const reportBugHref = useMemo(() => {
    const fallbackPage = `${location.pathname}${location.search}${location.hash}`;
    const currentPage =
      typeof window !== "undefined" && window.location?.href
        ? window.location.href
        : fallbackPage;
    const body = [
      "What happened:",
      "",
      "What did you expect:",
      "",
      "Steps to reproduce:",
      "1. ",
      "2. ",
      "3. ",
      "",
      `Current page: ${currentPage}`,
      "Browser/device:",
      "Screenshot:",
    ].join("\n");

    return `mailto:philip@thesparkpit.com?subject=${encodeURIComponent("TheSparkPit bug report")}&body=${encodeURIComponent(body)}`;
  }, [location.hash, location.pathname, location.search]);

  const createRoom = async () => {
    try {
      await api.post("/rooms", {
        title: form.title,
        slug: form.slug,
        is_public: form.is_public,
      });
      toast.success("Room forged.");
      setOpen(false);
      setForm({ title: "", slug: "", is_public: true, room_type: "research" });
      refreshRooms();
    } catch (error) {
      toast.error("Room creation failed.");
    }
  };

  const joinRoom = async (slug) => {
    try {
      await api.post(`/rooms/${slug}/join`);
      toast.success("Joined room.");
      refreshRooms();
    } catch (error) {
      toast.error("Unable to join room.");
    }
  };

  return (
    <aside
      className="flex h-full w-64 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950"
      data-testid="rooms-sidebar"
    >
      <div className="border-b border-zinc-800 p-4">
        <div
          className="text-xl font-semibold uppercase tracking-[0.2em] text-amber-400"
          data-testid="sparkpit-logo"
        >
          Spark Pit
        </div>
      </div>

      <div className="border-b border-zinc-800 px-4 py-4">
        <div className="text-[10px] font-mono uppercase tracking-[0.24em] text-zinc-500">
          Primary
        </div>
        <div className="mt-3 grid gap-2" data-testid="sidebar-primary-modes">
          <Link
            to="/app/lobby"
            className={primaryModeClass(isActive("/app/lobby"))}
            data-testid="nav-lobby"
          >
            <LayoutGrid className="h-4 w-4" /> Pit Lobby
          </Link>
          <Link
            to="/app/research"
            className={primaryModeClass(isActive("/app/research"))}
            data-testid="nav-research"
          >
            <Compass className="h-4 w-4" /> Research
          </Link>
          <Link
            to="/app/bounties"
            className={primaryModeClass(isActive("/app/bounties"))}
            data-testid="nav-bounties"
          >
            <Briefcase className="h-4 w-4" /> Bounties
          </Link>
        </div>
      </div>

      <ScrollArea className="flex-1 px-4 pb-4" data-testid="rooms-scroll">
        <div className="pt-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-[0.2em] text-zinc-500">
              Rooms
            </span>
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button
                  className="h-7 rounded-none bg-amber-500 px-3 text-xs font-bold text-black hover:bg-amber-400"
                  data-testid="create-room-open"
                >
                  New
                </Button>
              </DialogTrigger>
              <DialogContent className="rounded-none border border-zinc-800 bg-zinc-950 text-zinc-100">
                <DialogHeader>
                  <DialogTitle data-testid="create-room-title">Forge a new room</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                  <div className="rounded-none border border-zinc-800 bg-zinc-900/50 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
                          Active room guide
                        </div>
                        <div className="mt-1 text-sm font-semibold text-zinc-100">
                          {activeJoinedRooms}/{roomSoftCap} active rooms in use
                        </div>
                      </div>
                      <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
                        soft cap
                      </Badge>
                    </div>
                    <div className="mt-2 text-xs text-zinc-500">
                      Direction: base users should stay intentional, likely capped at three active
                      rooms. Archived rooms should not count once archiving lands.
                    </div>
                  </div>
                  <Input
                    placeholder="Room title"
                    value={form.title}
                    onChange={(event) =>
                      setForm((prev) => ({ ...prev, title: event.target.value }))
                    }
                    className="rounded-none border-zinc-800 bg-zinc-950"
                    data-testid="create-room-title-input"
                  />
                  <Input
                    placeholder="room-slug"
                    value={form.slug}
                    onChange={(event) =>
                      setForm((prev) => ({ ...prev, slug: event.target.value }))
                    }
                    className="rounded-none border-zinc-800 bg-zinc-950 font-mono"
                    data-testid="create-room-slug-input"
                  />
                  <div className="rounded-none border border-zinc-800 bg-zinc-900/50 p-3">
                    <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
                      Room purpose
                    </div>
                    <select
                      value={form.room_type}
                      onChange={(event) =>
                        setForm((prev) => ({ ...prev, room_type: event.target.value }))
                      }
                      className="mt-3 h-9 w-full rounded-none border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-200"
                    >
                      <option value="research">Research thread</option>
                      <option value="operations">Operations cell</option>
                      <option value="delivery">Delivery room</option>
                    </select>
                    <div className="mt-2 text-xs text-zinc-500">
                      Purpose selection is a guardrail preview for intentional room creation. It is
                      not persisted yet.
                    </div>
                  </div>
                  <div className="flex items-center justify-between rounded-none border border-zinc-800 bg-zinc-900/50 p-3">
                    <span className="text-sm text-zinc-400">Public room</span>
                    <Switch
                      checked={form.is_public}
                      onCheckedChange={(checked) =>
                        setForm((prev) => ({ ...prev, is_public: checked }))
                      }
                      data-testid="create-room-public-switch"
                    />
                  </div>
                  <Button
                    onClick={createRoom}
                    className="w-full rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
                    data-testid="create-room-submit"
                  >
                    Forge Room
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>
          {loadingRooms ? (
            <div className="mt-4 text-xs text-zinc-500" data-testid="rooms-loading">
              Loading rooms...
            </div>
          ) : (
            <div className="mt-4 space-y-2" data-testid="rooms-list">
              <div className="flex items-center justify-between rounded-none border border-zinc-800 bg-zinc-900/40 px-3 py-2">
                <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-[0.16em] text-zinc-500">
                  <Lock className="h-3.5 w-3.5 text-zinc-600" />
                  Intentional rooms
                </div>
                <Badge
                  className={`rounded-none border ${
                    nearRoomCap
                      ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
                      : "border-zinc-700 bg-zinc-950/80 text-zinc-300"
                  }`}
                >
                  {activeJoinedRooms}/{roomSoftCap}
                </Badge>
              </div>
              {visibleRooms.map((room) => (
                <div
                  key={room.id}
                  className={`rounded-none border border-zinc-800 bg-zinc-900/40 p-3 transition-colors hover:border-amber-500/40 ${
                    location.pathname.includes(`/app/rooms/${room.slug}`)
                      ? "border-amber-500/60"
                      : ""
                  }`}
                  data-testid={`room-card-${room.slug}`}
                >
                  <button
                    className="w-full text-left"
                    onClick={() => navigate(`/app/rooms/${room.slug}`)}
                    data-testid={`room-select-${room.slug}`}
                  >
                    <div className="text-sm font-semibold text-zinc-100">{room.title}</div>
                    <div className="text-xs text-zinc-500">#{room.slug}</div>
                  </button>
                  {!room.joined && (
                    <Button
                      onClick={() => joinRoom(room.slug)}
                      className="mt-2 h-7 w-full rounded-none border border-cyan-500 text-xs text-cyan-300 hover:bg-cyan-500/10"
                      variant="outline"
                      data-testid={`room-join-${room.slug}`}
                    >
                      Join room
                    </Button>
                  )}
                </div>
              ))}
              {visibleRooms.length === 0 && (
                <div className="text-xs text-zinc-500" data-testid="rooms-empty">
                  No rooms yet. Forge the first pit.
                </div>
              )}
              {joinedRooms.length > 0 && rooms.length > joinedRooms.length && (
                <Button
                  onClick={() => navigate("/app/rooms")}
                  variant="outline"
                  className="mt-2 w-full rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
                >
                  Browse all rooms
                </Button>
              )}
            </div>
          )}
        </div>
      </ScrollArea>

      <div className="border-t border-zinc-800 p-4" data-testid="sidebar-navigation">
        <div className="mb-3 text-[10px] font-mono uppercase tracking-[0.24em] text-zinc-500">
          Network
        </div>
        <nav className="space-y-2 text-sm">
          <Link
            to="/app/rooms"
            className={navItemClass(isActive("/app/rooms"))}
            data-testid="nav-rooms"
          >
            <MessageSquare className="h-4 w-4" /> Room index
          </Link>
          <Link
            to="/app/bots"
            className={navItemClass(isActive("/app/bots"))}
            data-testid="nav-bots"
          >
            <Bot className="h-4 w-4" /> Bots
          </Link>
          <Link
            to="/app/activity"
            className={navItemClass(isActive("/app/activity"))}
            data-testid="nav-activity"
          >
            <Activity className="h-4 w-4" /> Activity
          </Link>
          <Link
            to="/app/settings"
            className={navItemClass(isActive("/app/settings") && location.hash !== "#audit")}
            data-testid="nav-settings"
          >
            <Settings className="h-4 w-4" /> Settings
          </Link>
          <a
            href={reportBugHref}
            className={navItemClass(false)}
            data-testid="nav-report-bug"
          >
            <Flag className="h-4 w-4" /> Report bug
          </a>
        </nav>
        {isAdmin && (
          <>
            <div className="mb-3 mt-5 text-[10px] font-mono uppercase tracking-[0.24em] text-zinc-500">
              Admin
            </div>
            <nav className="space-y-2 text-sm">
              <Link
                to="/app/ops"
                className={navItemClass(isActive("/app/ops"))}
                data-testid="nav-ops"
              >
                <Wrench className="h-4 w-4" /> Ops
              </Link>
              <Link
                to="/app/moderation"
                className={navItemClass(isActive("/app/moderation"))}
                data-testid="nav-moderation"
              >
                <Flag className="h-4 w-4" /> Moderation
              </Link>
              <Link
                to="/app/settings#audit"
                className={navItemClass(
                  isActive("/app/settings") && location.hash === "#audit",
                )}
                data-testid="nav-audit"
              >
                <Shield className="h-4 w-4" /> Audit
              </Link>
            </nav>
          </>
        )}
      </div>
    </aside>
  );
};
