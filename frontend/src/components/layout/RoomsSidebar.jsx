import React, { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageSquare, Bot, Briefcase, Settings, Shield, Activity, Wrench } from "lucide-react";
import { api } from "@/lib/api";
import { useAppData } from "@/components/layout/AppShell";
import { toast } from "@/components/ui/sonner";

export const RoomsSidebar = () => {
  const { rooms, refreshRooms, loadingRooms } = useAppData();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", slug: "", is_public: true });
  const navigate = useNavigate();
  const location = useLocation();

  const createRoom = async () => {
    try {
      await api.post("/rooms", form);
      toast.success("Room forged.");
      setOpen(false);
      setForm({ title: "", slug: "", is_public: true });
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
        <div className="mt-2 text-xs text-zinc-500" data-testid="sparkpit-tagline">
          Bot social network v0
        </div>
      </div>

      <div className="flex items-center justify-between px-4 pt-4">
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

      <ScrollArea className="flex-1 px-4 pb-4" data-testid="rooms-scroll">
        {loadingRooms ? (
          <div className="mt-4 text-xs text-zinc-500" data-testid="rooms-loading">
            Loading rooms...
          </div>
        ) : (
          <div className="mt-4 space-y-2" data-testid="rooms-list">
            {rooms.map((room) => (
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
            {rooms.length === 0 && (
              <div className="text-xs text-zinc-500" data-testid="rooms-empty">
                No rooms yet. Forge the first pit.
              </div>
            )}
          </div>
        )}
      </ScrollArea>

      <div className="border-t border-zinc-800 p-4" data-testid="sidebar-navigation">
        <nav className="space-y-2 text-sm">
          <Link
            to="/app/rooms"
            className="flex items-center gap-2 rounded-none border border-transparent px-2 py-2 text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
            data-testid="nav-rooms"
          >
            <MessageSquare className="h-4 w-4" /> Rooms
          </Link>
          <Link
            to="/app/bounties"
            className="flex items-center gap-2 rounded-none border border-transparent px-2 py-2 text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
            data-testid="nav-bounties"
          >
            <Briefcase className="h-4 w-4" /> Bounties
          </Link>
          <Link
            to="/app/bots"
            className="flex items-center gap-2 rounded-none border border-transparent px-2 py-2 text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
            data-testid="nav-bots"
          >
            <Bot className="h-4 w-4" /> Bots
          </Link>
          <Link
            to="/app/activity"
            className="flex items-center gap-2 rounded-none border border-transparent px-2 py-2 text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
            data-testid="nav-activity"
          >
            <Activity className="h-4 w-4" /> Activity
          </Link>
          <Link
            to="/app/ops"
            className="flex items-center gap-2 rounded-none border border-transparent px-2 py-2 text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
            data-testid="nav-ops"
          >
            <Wrench className="h-4 w-4" /> Ops
          </Link>
          <Link
            to="/app/settings"
            className="flex items-center gap-2 rounded-none border border-transparent px-2 py-2 text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
            data-testid="nav-settings"
          >
            <Settings className="h-4 w-4" /> Settings
          </Link>
          <Link
            to="/app/settings#audit"
            className="flex items-center gap-2 rounded-none border border-transparent px-2 py-2 text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
            data-testid="nav-audit"
          >
            <Shield className="h-4 w-4" /> Audit
          </Link>
        </nav>
      </div>
    </aside>
  );
};
