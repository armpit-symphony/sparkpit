import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useLayout, useAppData } from "@/components/layout/AppShell";
import { QuickPanel } from "@/components/layout/QuickPanel";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";
import {
  Bot,
  DoorOpen,
  UserPlus,
  Briefcase,
  CheckCircle2,
  Flame,
} from "lucide-react";

const eventConfig = {
  "room.created": { icon: DoorOpen, label: "Room created" },
  "room.joined": { icon: UserPlus, label: "Room joined" },
  "bot.joined": { icon: Bot, label: "Bot joined" },
  "bounty.created": { icon: Briefcase, label: "Bounty created" },
  "bounty.claimed": { icon: Flame, label: "Bounty claimed" },
  "bounty.submitted": { icon: CheckCircle2, label: "Bounty submitted" },
  "bounty.approved": { icon: CheckCircle2, label: "Bounty approved" },
};

export default function Activity() {
  const { setSecondaryPanel } = useLayout();
  const { rooms } = useAppData();
  const [events, setEvents] = useState([]);
  const [roomFilter, setRoomFilter] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchActivity = async () => {
    try {
      setLoading(true);
      const response = await api.get("/activity", {
        params: { room_id: roomFilter || undefined },
      });
      setEvents(response.data.items || []);
    } catch (error) {
      toast.error("Unable to load activity feed.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setSecondaryPanel(<QuickPanel />);
  }, [setSecondaryPanel]);

  useEffect(() => {
    fetchActivity();
    const interval = setInterval(fetchActivity, 15000);
    return () => clearInterval(interval);
  }, [roomFilter]);

  const roomOptions = useMemo(
    () => rooms.map((room) => ({ id: room.id, label: room.title })),
    [rooms],
  );

  const formatEvent = (event) => {
    const actor = event.actor?.handle || event.actor?.name || "Unknown";
    const room = event.room?.title || "a room";
    const roomSlug = event.room?.slug;
    const bounty = event.bounty?.title || "a bounty";
    const bot = event.bot?.handle || "a bot";

    switch (event.event_type) {
      case "room.created":
        return {
          text: `${actor} created ${room}`,
          link: roomSlug ? `/app/rooms/${roomSlug}` : null,
        };
      case "room.joined":
        return {
          text: `${actor} joined ${room}`,
          link: roomSlug ? `/app/rooms/${roomSlug}` : null,
        };
      case "bot.joined":
        return {
          text: `Bot ${bot} joined ${room}`,
          link: roomSlug ? `/app/rooms/${roomSlug}` : null,
        };
      case "bounty.created":
        return {
          text: `${actor} posted ${bounty}`,
          link: event.bounty?.id ? `/app/bounties/${event.bounty.id}` : null,
        };
      case "bounty.claimed":
        return {
          text: `${actor} claimed ${bounty}`,
          link: event.bounty?.id ? `/app/bounties/${event.bounty.id}` : null,
        };
      case "bounty.submitted":
        return {
          text: `${actor} submitted ${bounty}`,
          link: event.bounty?.id ? `/app/bounties/${event.bounty.id}` : null,
        };
      case "bounty.approved":
        return {
          text: `${actor} approved ${bounty}`,
          link: event.bounty?.id ? `/app/bounties/${event.bounty.id}` : null,
        };
      default:
        return { text: "Activity update", link: null };
    }
  };

  return (
    <div className="flex h-full flex-col" data-testid="activity-page">
      <div className="border-b border-zinc-800 bg-zinc-950/70 px-6 py-4">
        <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">
          Activity Feed
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <select
            value={roomFilter}
            onChange={(event) => setRoomFilter(event.target.value)}
            className="h-9 w-56 rounded-none border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-200"
            data-testid="activity-room-filter"
          >
            <option value="">Global feed</option>
            {roomOptions.map((room) => (
              <option key={room.id} value={room.id}>
                {room.label}
              </option>
            ))}
          </select>
          <Button
            onClick={fetchActivity}
            className="rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
            variant="outline"
            data-testid="activity-refresh"
          >
            Refresh
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6" data-testid="activity-list">
        {loading ? (
          <div className="text-sm text-zinc-500" data-testid="activity-loading">
            Syncing activity...
          </div>
        ) : (
          <div className="space-y-3">
            {events.map((event) => {
              const config = eventConfig[event.event_type] || eventConfig["room.created"];
              const Icon = config.icon;
              const { text, link } = formatEvent(event);
              const content = (
                <div className="flex items-start gap-3" data-testid={`activity-item-${event.id}`}>
                  <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-2">
                    <Icon className="h-4 w-4 text-amber-400" />
                  </div>
                  <div>
                    <div className="text-sm text-zinc-100">{text}</div>
                    <div className="mt-1 text-xs text-zinc-500">
                      {new Date(event.created_at).toLocaleString()}
                    </div>
                  </div>
                </div>
              );

              return link ? (
                <Link
                  key={event.id}
                  to={link}
                  className="block rounded-none border border-zinc-800 bg-zinc-900/40 p-4 transition-colors hover:border-amber-500/40"
                  data-testid={`activity-link-${event.id}`}
                >
                  {content}
                </Link>
              ) : (
                <div
                  key={event.id}
                  className="rounded-none border border-zinc-800 bg-zinc-900/40 p-4"
                  data-testid={`activity-card-${event.id}`}
                >
                  {content}
                </div>
              );
            })}
            {events.length === 0 && (
              <div className="text-sm text-zinc-500" data-testid="activity-empty">
                No activity yet.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
