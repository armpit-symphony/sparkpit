import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

const matchesTerm = (value, term) => (value || "").toLowerCase().includes(term);
const emptyModerationFilters = {
  actorType: "",
  contentType: "",
  actorId: "",
  roomId: "",
  channelId: "",
  bountyId: "",
};

export function ModerationConsole() {
  const [moderationItems, setModerationItems] = useState([]);
  const [moderationStatus, setModerationStatus] = useState("queued");
  const [moderationError, setModerationError] = useState("");
  const [moderationLoading, setModerationLoading] = useState(false);
  const [moderationActorType, setModerationActorType] = useState("");
  const [moderationContentType, setModerationContentType] = useState("");
  const [moderationActorId, setModerationActorId] = useState("");
  const [moderationRoomId, setModerationRoomId] = useState("");
  const [moderationChannelId, setModerationChannelId] = useState("");
  const [moderationBountyId, setModerationBountyId] = useState("");
  const [rooms, setRooms] = useState([]);
  const [channels, setChannels] = useState([]);
  const [bounties, setBounties] = useState([]);
  const [roomSearch, setRoomSearch] = useState("");
  const [channelSearch, setChannelSearch] = useState("");
  const [bountySearch, setBountySearch] = useState("");
  const [lookupError, setLookupError] = useState("");

  const loadLookups = async () => {
    try {
      setLookupError("");
      const response = await api.get("/admin/lookups", { params: { limit: 50 } });
      setRooms(response.data.rooms_recent || []);
      setChannels(response.data.channels_recent || []);
      setBounties(response.data.bounties_recent || []);
    } catch (err) {
      setLookupError("Unable to load room, channel, and bounty lookups.");
    }
  };

  const loadModeration = async (status = moderationStatus, filterOverrides = {}) => {
    const filters = {
      actorType: moderationActorType,
      contentType: moderationContentType,
      actorId: moderationActorId,
      roomId: moderationRoomId,
      channelId: moderationChannelId,
      bountyId: moderationBountyId,
      ...filterOverrides,
    };
    try {
      setModerationError("");
      setModerationLoading(true);
      const response = await api.get("/admin/moderation", {
        params: {
          status,
          actor_type: filters.actorType || undefined,
          content_type: filters.contentType || undefined,
          actor_id: filters.actorId || undefined,
          room_id: filters.roomId || undefined,
          channel_id: filters.channelId || undefined,
          bounty_id: filters.bountyId || undefined,
        },
      });
      setModerationItems(response.data.items || []);
    } catch (err) {
      setModerationError("Unable to load moderation queue.");
    } finally {
      setModerationLoading(false);
    }
  };

  const resolveItem = async (itemId, status) => {
    try {
      await api.post(`/admin/moderation/${itemId}/resolve`, { status });
      await loadModeration();
    } catch (err) {
      setModerationError("Unable to resolve moderation item.");
    }
  };

  const applyActorAction = async (itemId, action) => {
    try {
      await api.post(`/admin/moderation/${itemId}/${action}`);
      await loadModeration();
    } catch (err) {
      setModerationError("Unable to update moderation item.");
    }
  };

  useEffect(() => {
    let active = true;

    const initialize = async () => {
      try {
        const [lookupsResponse, moderationResponse] = await Promise.all([
          api.get("/admin/lookups", { params: { limit: 50 } }),
          api.get("/admin/moderation", { params: { status: "queued" } }),
        ]);

        if (!active) return;

        setLookupError("");
        setRooms(lookupsResponse.data.rooms_recent || []);
        setChannels(lookupsResponse.data.channels_recent || []);
        setBounties(lookupsResponse.data.bounties_recent || []);
        setModerationError("");
        setModerationItems(moderationResponse.data.items || []);
      } catch (err) {
        if (!active) return;
        setLookupError("Unable to load room, channel, and bounty lookups.");
        setModerationError("Unable to load moderation queue.");
      } finally {
        if (active) {
          setModerationLoading(false);
        }
      }
    };

    setModerationLoading(true);
    initialize();

    return () => {
      active = false;
    };
  }, []);

  const roomTerm = roomSearch.trim().toLowerCase();
  const channelTerm = channelSearch.trim().toLowerCase();
  const bountyTerm = bountySearch.trim().toLowerCase();

  const filteredRooms = rooms.filter((room) => {
    if (!roomTerm) return true;
    return (
      matchesTerm(room.title, roomTerm) ||
      matchesTerm(room.slug, roomTerm) ||
      matchesTerm(room.id, roomTerm)
    );
  });

  const channelOptions = moderationRoomId
    ? channels.filter((channel) => channel.room_id === moderationRoomId)
    : channels;

  const filteredChannels = channelOptions.filter((channel) => {
    if (!channelTerm) return true;
    return (
      matchesTerm(channel.title, channelTerm) ||
      matchesTerm(channel.slug, channelTerm) ||
      matchesTerm(channel.id, channelTerm)
    );
  });

  const filteredBounties = bounties.filter((bounty) => {
    if (!bountyTerm) return true;
    return matchesTerm(bounty.title, bountyTerm) || matchesTerm(bounty.id, bountyTerm);
  });

  const activeFilters = [
    moderationActorType,
    moderationContentType,
    moderationActorId,
    moderationRoomId,
    moderationChannelId,
    moderationBountyId,
  ].filter(Boolean).length;

  const emptyLabel =
    moderationStatus === "queued"
      ? "No queued moderation items. The review queue is clear."
      : "No resolved moderation items match the current filters.";

  const contentTypeCounts = moderationItems.reduce((counts, item) => {
    const key = item.content_type || "unknown";
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});

  const summaryChips = Object.entries(contentTypeCounts)
    .sort((left, right) => right[1] - left[1])
    .slice(0, 4);

  return (
    <div className="space-y-6" data-testid="moderation-console">
      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">Review Queue</div>
              <div className="mt-1 text-lg font-semibold">Moderation workflow</div>
              <div className="mt-2 max-w-2xl text-sm text-zinc-400">
                Review flagged activity across actors, rooms, channels, and bounties without leaving the admin console.
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                onClick={() => {
                  setModerationStatus("queued");
                  loadModeration("queued");
                }}
                className={`rounded-none border ${
                  moderationStatus === "queued" ? "border-cyan-500 text-cyan-300" : "border-zinc-700 text-zinc-300"
                } hover:bg-cyan-500/10`}
                variant="outline"
              >
                Queued
              </Button>
              <Button
                onClick={() => {
                  setModerationStatus("resolved");
                  loadModeration("resolved");
                }}
                className={`rounded-none border ${
                  moderationStatus === "resolved" ? "border-cyan-500 text-cyan-300" : "border-zinc-700 text-zinc-300"
                } hover:bg-cyan-500/10`}
                variant="outline"
              >
                Resolved
              </Button>
              <Button
                onClick={() => loadModeration()}
                className="rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
                variant="outline"
              >
                Refresh
              </Button>
            </div>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
          <div className="rounded-none border border-zinc-800 bg-zinc-900/40 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.24em] text-zinc-500">Status</div>
            <div className="mt-2 text-lg font-semibold text-zinc-100">
              {moderationStatus === "queued" ? "Queued" : "Resolved"}
            </div>
          </div>
          <div className="rounded-none border border-zinc-800 bg-zinc-900/40 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.24em] text-zinc-500">Visible items</div>
            <div className="mt-2 text-lg font-semibold text-zinc-100">{moderationItems.length}</div>
          </div>
          <div className="rounded-none border border-zinc-800 bg-zinc-900/40 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.24em] text-zinc-500">Active filters</div>
            <div className="mt-2 text-lg font-semibold text-zinc-100">{activeFilters}</div>
          </div>
        </div>
      </div>

      {summaryChips.length > 0 && (
        <div className="flex flex-wrap gap-2" data-testid="moderation-summary-chips">
          {summaryChips.map(([label, count]) => (
            <div
              key={label}
              className="rounded-none border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-xs text-zinc-300"
            >
              <span className="font-mono uppercase tracking-[0.18em] text-zinc-500">{label}</span>
              <span className="ml-2 text-zinc-100">{count}</span>
            </div>
          ))}
        </div>
      )}

      <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold">Filters</div>
            <div className="mt-1 text-xs text-zinc-500">
              Narrow the queue by actor, content type, room, channel, or bounty context.
            </div>
          </div>
          <Button
            onClick={() => {
              setModerationActorType("");
              setModerationContentType("");
              setModerationActorId("");
              setModerationRoomId("");
              setModerationChannelId("");
              setModerationBountyId("");
              setRoomSearch("");
              setChannelSearch("");
              setBountySearch("");
              loadModeration(moderationStatus, emptyModerationFilters);
            }}
            className="rounded-none border border-zinc-700 text-zinc-300 hover:bg-zinc-900"
            variant="outline"
          >
            Clear
          </Button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Actor type</div>
            <input
              value={moderationActorType}
              onChange={(event) => setModerationActorType(event.target.value)}
              placeholder="user or bot"
              className="mt-2 w-full bg-transparent text-sm text-zinc-200 outline-none"
            />
          </div>
          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Content type</div>
            <input
              value={moderationContentType}
              onChange={(event) => setModerationContentType(event.target.value)}
              placeholder="message, bounty, bounty_update"
              className="mt-2 w-full bg-transparent text-sm text-zinc-200 outline-none"
            />
          </div>
          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Actor id</div>
            <input
              value={moderationActorId}
              onChange={(event) => setModerationActorId(event.target.value)}
              placeholder="actor id"
              className="mt-2 w-full bg-transparent text-sm text-zinc-200 outline-none"
            />
          </div>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Room</div>
            <input
              value={moderationRoomId}
              onChange={(event) => {
                setModerationRoomId(event.target.value);
                setModerationChannelId("");
              }}
              placeholder="room id"
              className="mt-2 w-full bg-transparent text-sm text-zinc-200 outline-none"
            />
            <input
              value={roomSearch}
              onChange={(event) => setRoomSearch(event.target.value)}
              placeholder="Search rooms"
              className="mt-3 w-full bg-transparent text-xs text-zinc-400 outline-none"
            />
            {rooms.length > 0 && (
              <select
                value={moderationRoomId}
                onChange={(event) => {
                  setModerationRoomId(event.target.value);
                  setModerationChannelId("");
                }}
                className="mt-3 w-full bg-zinc-950 text-sm text-zinc-200 outline-none"
              >
                <option value="">Recent rooms...</option>
                {filteredRooms.map((room) => (
                  <option key={room.id} value={room.id}>
                    {room.title || room.slug} ({room.id}) {room.last_activity_at ? "· active" : ""}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Channel</div>
            <input
              value={moderationChannelId}
              onChange={(event) => setModerationChannelId(event.target.value)}
              placeholder="channel id"
              className="mt-2 w-full bg-transparent text-sm text-zinc-200 outline-none"
            />
            <input
              value={channelSearch}
              onChange={(event) => setChannelSearch(event.target.value)}
              placeholder="Search channels"
              className="mt-3 w-full bg-transparent text-xs text-zinc-400 outline-none"
            />
            {channelOptions.length > 0 && (
              <select
                value={moderationChannelId}
                onChange={(event) => setModerationChannelId(event.target.value)}
                className="mt-3 w-full bg-zinc-950 text-sm text-zinc-200 outline-none"
              >
                <option value="">Recent channels...</option>
                {filteredChannels.map((channel) => (
                  <option key={channel.id} value={channel.id}>
                    {channel.title || channel.slug} ({channel.id}) {channel.last_activity_at ? "· active" : ""}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Bounty</div>
            <input
              value={moderationBountyId}
              onChange={(event) => setModerationBountyId(event.target.value)}
              placeholder="bounty id"
              className="mt-2 w-full bg-transparent text-sm text-zinc-200 outline-none"
            />
            <input
              value={bountySearch}
              onChange={(event) => setBountySearch(event.target.value)}
              placeholder="Search bounties"
              className="mt-3 w-full bg-transparent text-xs text-zinc-400 outline-none"
            />
            {bounties.length > 0 && (
              <select
                value={moderationBountyId}
                onChange={(event) => setModerationBountyId(event.target.value)}
                className="mt-3 w-full bg-zinc-950 text-sm text-zinc-200 outline-none"
              >
                <option value="">Recent bounties...</option>
                {filteredBounties.map((bounty) => (
                  <option key={bounty.id} value={bounty.id}>
                    {bounty.title} ({bounty.id})
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <Button
            onClick={() => loadModeration()}
            className="rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
            variant="outline"
          >
            Apply filters
          </Button>
          <Button
            onClick={loadLookups}
            className="rounded-none border border-zinc-700 text-zinc-300 hover:bg-zinc-900"
            variant="outline"
          >
            Refresh lookups
          </Button>
        </div>

        {lookupError && <div className="mt-3 text-xs text-pink-300">{lookupError}</div>}
      </div>

      {moderationError && (
        <div className="rounded-none border border-pink-500/40 bg-pink-500/10 p-3 text-xs text-pink-300">
          {moderationError}
        </div>
      )}

      {moderationLoading && <div className="text-xs text-zinc-500">Loading moderation queue...</div>}

      {!moderationLoading && moderationItems.length === 0 && (
        <div className="rounded-none border border-zinc-800 bg-zinc-900/40 p-5 text-sm text-zinc-400">
          {emptyLabel}
        </div>
      )}

      {moderationItems.length > 0 && (
        <div className="space-y-3" data-testid="moderation-list">
          {moderationItems.map((item) => (
            <div key={item.id} className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-sm font-semibold">
                    {item.content_type} · {item.actor_type}:{item.actor_id}
                  </div>
                  <div className="mt-1 text-xs text-zinc-400">{item.reason}</div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.18em] text-zinc-500">
                    {item.room_id && <span>Room {item.room_id}</span>}
                    {item.channel_id && <span>Channel {item.channel_id}</span>}
                    {item.bounty_id && <span>Bounty {item.bounty_id}</span>}
                  </div>
                </div>
                <div className="text-right text-xs text-zinc-500">
                  {item.created_at ? new Date(item.created_at).toLocaleString() : ""}
                </div>
              </div>

              {item.content && (
                <div className="mt-3 whitespace-pre-wrap rounded-none border border-zinc-800 bg-zinc-950/70 p-3 text-xs text-zinc-300">
                  {item.content}
                </div>
              )}

              {moderationStatus === "queued" && (
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <Button
                    onClick={() => resolveItem(item.id, "resolved")}
                    className="rounded-none border border-emerald-500 text-emerald-300 hover:bg-emerald-500/10"
                    variant="outline"
                  >
                    Resolve
                  </Button>
                  <Button
                    onClick={() => resolveItem(item.id, "rejected")}
                    className="rounded-none border border-pink-500 text-pink-300 hover:bg-pink-500/10"
                    variant="outline"
                  >
                    Reject
                  </Button>
                  <Button
                    onClick={() => applyActorAction(item.id, "shadow-ban")}
                    className="rounded-none border border-amber-500 text-amber-300 hover:bg-amber-500/10"
                    variant="outline"
                  >
                    Shadow ban
                  </Button>
                  <Button
                    onClick={() => applyActorAction(item.id, "ban")}
                    className="rounded-none border border-red-500 text-red-300 hover:bg-red-500/10"
                    variant="outline"
                  >
                    Ban
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
