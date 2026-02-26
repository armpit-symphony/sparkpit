import React, { useEffect, useState } from "react";
import { useLayout } from "@/components/layout/AppShell";
import { QuickPanel } from "@/components/layout/QuickPanel";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

const statusLabel = (value) => (value ? "OK" : "Not set");

export default function OpsChecklist() {
  const { setSecondaryPanel } = useLayout();
  const { user } = useAuth();
  const [ops, setOps] = useState(null);
  const [error, setError] = useState("");
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
  const [rateLimitEvents, setRateLimitEvents] = useState([]);
  const [rateLimitAvailable, setRateLimitAvailable] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [alertsError, setAlertsError] = useState("");

  const loadOps = async () => {
    try {
      setError("");
      const response = await api.get("/admin/ops");
      setOps(response.data);
    } catch (err) {
      setError("Admin access required or ops endpoint unavailable.");
    }
  };

  const loadLookups = async () => {
    try {
      setLookupError("");
      const response = await api.get("/admin/lookups", { params: { limit: 50 } });
      setRooms(response.data.rooms_recent || []);
      setChannels(response.data.channels_recent || []);
      setBounties(response.data.bounties_recent || []);
    } catch (err) {
      setLookupError("Unable to load room/channel/bounty lookups.");
    }
  };

  const loadRateLimits = async () => {
    try {
      const response = await api.get("/admin/rate-limits");
      setRateLimitEvents(response.data.events || []);
      setRateLimitAvailable(!!response.data.available);
    } catch (err) {
      setRateLimitEvents([]);
      setRateLimitAvailable(false);
    }
  };

  const loadAlerts = async () => {
    try {
      setAlertsError("");
      const response = await api.get("/admin/alerts");
      setAlerts(response.data.items || []);
    } catch (err) {
      setAlerts([]);
      setAlertsError("Unable to load alerts.");
    }
  };

  const loadChannelsForRoom = async (roomId) => {
    if (!roomId) {
      setChannels([]);
      return;
    }
    setChannels((prev) => prev.filter((channel) => channel.room_id === roomId));
  };

  const loadModeration = async (status = moderationStatus) => {
    try {
      setModerationError("");
      setModerationLoading(true);
      const response = await api.get("/admin/moderation", {
        params: {
          status,
          actor_type: moderationActorType || undefined,
          content_type: moderationContentType || undefined,
          actor_id: moderationActorId || undefined,
          room_id: moderationRoomId || undefined,
          channel_id: moderationChannelId || undefined,
          bounty_id: moderationBountyId || undefined,
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

  useEffect(() => {
    setSecondaryPanel(<QuickPanel />);
  }, [setSecondaryPanel]);

  useEffect(() => {
    loadOps();
    loadModeration();
    loadLookups();
    loadRateLimits();
    loadAlerts();
  }, []);

  return (
    <div className="flex h-full flex-col" data-testid="ops-page">
      <div className="border-b border-zinc-800 bg-zinc-950/70 px-6 py-4">
        <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">Ops Checklist</div>
        <div className="text-lg font-semibold" data-testid="ops-title">
          Launch readiness
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="flex items-center justify-between">
          <div className="text-xs text-zinc-500" data-testid="ops-admin-note">
            Admin only · {user?.email}
          </div>
          <Button
            onClick={loadOps}
            className="rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
            variant="outline"
            data-testid="ops-refresh"
          >
            Refresh
          </Button>
        </div>

        {error && (
          <div className="mt-4 rounded-none border border-pink-500/40 bg-pink-500/10 p-3 text-xs text-pink-300" data-testid="ops-error">
            {error}
          </div>
        )}

        {ops && (
          <div className="mt-6 space-y-3" data-testid="ops-list">
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4" data-testid="ops-stripe-configured">
              <div className="text-sm font-semibold">Stripe configured</div>
              <div className="mt-2 text-xs text-zinc-400">{statusLabel(ops.stripe_configured)}</div>
            </div>
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4" data-testid="ops-stripe-webhook">
              <div className="text-sm font-semibold">Stripe webhook</div>
              <div className="mt-2 text-xs text-zinc-400">
                {ops.stripe_webhook_last_received
                  ? `Last received: ${new Date(ops.stripe_webhook_last_received).toLocaleString()}`
                  : "Awaiting first webhook"}
              </div>
            </div>
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4" data-testid="ops-redis">
              <div className="text-sm font-semibold">Redis connectivity</div>
              <div className="mt-2 text-xs text-zinc-400">{statusLabel(ops.redis_connected)}</div>
            </div>
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4" data-testid="ops-worker">
              <div className="text-sm font-semibold">Worker heartbeat</div>
              <div className="mt-2 text-xs text-zinc-400">
                {ops.worker_healthy
                  ? "Healthy (last 60s)"
                  : "Stale or missing"}
              </div>
            </div>
          </div>
        )}

        <div className="mt-10 border-t border-zinc-800 pt-6" data-testid="ops-moderation">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">Moderation</div>
              <div className="text-lg font-semibold">Queue</div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                onClick={() => {
                  setModerationStatus("queued");
                  loadModeration("queued");
                }}
                className={`rounded-none border ${moderationStatus === "queued" ? "border-cyan-500 text-cyan-300" : "border-zinc-700 text-zinc-300"} hover:bg-cyan-500/10`}
                variant="outline"
              >
                Queued
              </Button>
              <Button
                onClick={() => {
                  setModerationStatus("resolved");
                  loadModeration("resolved");
                }}
                className={`rounded-none border ${moderationStatus === "resolved" ? "border-cyan-500 text-cyan-300" : "border-zinc-700 text-zinc-300"} hover:bg-cyan-500/10`}
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

          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-3">
              <div className="text-xs uppercase text-zinc-500">Actor Type</div>
              <input
                value={moderationActorType}
                onChange={(event) => setModerationActorType(event.target.value)}
                placeholder="user or bot"
                className="mt-2 w-full bg-transparent text-sm text-zinc-200 outline-none"
              />
            </div>
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-3">
              <div className="text-xs uppercase text-zinc-500">Content Type</div>
              <input
                value={moderationContentType}
                onChange={(event) => setModerationContentType(event.target.value)}
                placeholder="message, bounty, bounty_update"
                className="mt-2 w-full bg-transparent text-sm text-zinc-200 outline-none"
              />
            </div>
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-3">
              <div className="text-xs uppercase text-zinc-500">Actor Id</div>
              <input
                value={moderationActorId}
                onChange={(event) => setModerationActorId(event.target.value)}
                placeholder="actor id"
                className="mt-2 w-full bg-transparent text-sm text-zinc-200 outline-none"
              />
            </div>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-3">
              <div className="text-xs uppercase text-zinc-500">Room Id</div>
              <input
                value={moderationRoomId}
                onChange={(event) => {
                  setModerationRoomId(event.target.value);
                  loadChannelsForRoom(event.target.value);
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
                    loadChannelsForRoom(event.target.value);
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
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-3">
              <div className="text-xs uppercase text-zinc-500">Channel Id</div>
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
              {channels.length > 0 && (
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
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-3">
              <div className="text-xs uppercase text-zinc-500">Bounty Id</div>
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
          <div className="mt-3">
            <Button
              onClick={() => loadModeration()}
              className="rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
              variant="outline"
            >
              Apply Filters
            </Button>
          </div>
          {lookupError && (
            <div className="mt-3 text-xs text-pink-300">
              {lookupError}
            </div>
          )}

          {moderationError && (
            <div className="mt-4 rounded-none border border-pink-500/40 bg-pink-500/10 p-3 text-xs text-pink-300">
              {moderationError}
            </div>
          )}

          {moderationLoading && (
            <div className="mt-4 text-xs text-zinc-500">Loading moderation queue...</div>
          )}

          {!moderationLoading && moderationItems.length === 0 && (
            <div className="mt-4 text-xs text-zinc-500">No moderation items.</div>
          )}

          {moderationItems.length > 0 && (
            <div className="mt-4 space-y-3">
              {moderationItems.map((item) => (
                <div
                  key={item.id}
                  className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-sm font-semibold">
                        {item.content_type} · {item.actor_type}:{item.actor_id}
                      </div>
                      <div className="mt-1 text-xs text-zinc-400">
                        {item.reason}
                      </div>
                    </div>
                    <div className="text-xs text-zinc-500">
                      {item.created_at ? new Date(item.created_at).toLocaleString() : ""}
                    </div>
                  </div>
                  {item.content && (
                    <div className="mt-3 text-xs text-zinc-300 whitespace-pre-wrap">
                      {item.content}
                    </div>
                  )}
                  {moderationStatus === "queued" && (
                    <div className="mt-4 flex items-center gap-2">
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
                        onClick={async () => {
                          await api.post(`/admin/moderation/${item.id}/shadow-ban`);
                          await loadModeration();
                        }}
                        className="rounded-none border border-amber-500 text-amber-300 hover:bg-amber-500/10"
                        variant="outline"
                      >
                        Shadow Ban
                      </Button>
                      <Button
                        onClick={async () => {
                          await api.post(`/admin/moderation/${item.id}/ban`);
                          await loadModeration();
                        }}
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

        <div className="mt-10 border-t border-zinc-800 pt-6" data-testid="ops-rate-limits">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">Abuse</div>
              <div className="text-lg font-semibold">Rate Limits</div>
            </div>
            <Button
              onClick={() => loadRateLimits()}
              className="rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
              variant="outline"
            >
              Refresh
            </Button>
          </div>
          {!rateLimitAvailable && (
            <div className="mt-3 text-xs text-zinc-500">
              Rate limit telemetry unavailable (Redis not connected).
            </div>
          )}
          {rateLimitAvailable && rateLimitEvents.length === 0 && (
            <div className="mt-3 text-xs text-zinc-500">
              No rate limit events.
            </div>
          )}
          {rateLimitEvents.length > 0 && (
            <div className="mt-4 space-y-3">
              {rateLimitEvents.map((event, index) => (
                <div key={`${event.actor_id}-${index}`} className="rounded-none border border-zinc-800 bg-zinc-900/60 p-3">
                  <div className="text-sm font-semibold">
                    {event.actor_type}:{event.actor_id}
                  </div>
                  <div className="mt-1 text-xs text-zinc-400">
                    {event.endpoint} · {event.detail}
                  </div>
                  <div className="mt-1 text-xs text-zinc-500">
                    {event.created_at ? new Date(event.created_at).toLocaleString() : ""}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="mt-10 border-t border-zinc-800 pt-6" data-testid="ops-alerts">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">Alerts</div>
              <div className="text-lg font-semibold">Security Events</div>
            </div>
            <Button
              onClick={() => loadAlerts()}
              className="rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
              variant="outline"
            >
              Refresh
            </Button>
          </div>
          {alertsError && (
            <div className="mt-3 text-xs text-pink-300">
              {alertsError}
            </div>
          )}
          {!alertsError && alerts.length === 0 && (
            <div className="mt-3 text-xs text-zinc-500">No alerts yet.</div>
          )}
          {alerts.length > 0 && (
            <div className="mt-4 space-y-3">
              {alerts.map((alert) => (
                <div key={alert.id} className="rounded-none border border-zinc-800 bg-zinc-900/60 p-3">
                  <div className="text-sm font-semibold">{alert.event_type}</div>
                  <div className="mt-1 text-xs text-zinc-400">
                    {alert.payload ? JSON.stringify(alert.payload) : ""}
                  </div>
                  <div className="mt-1 text-xs text-zinc-500">
                    {alert.created_at ? new Date(alert.created_at).toLocaleString() : ""}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
  const filteredRooms = rooms.filter((room) => {
    const term = roomSearch.trim().toLowerCase();
    if (!term) return true;
    return (
      (room.title || "").toLowerCase().includes(term) ||
      (room.slug || "").toLowerCase().includes(term) ||
      (room.id || "").toLowerCase().includes(term)
    );
  });

  const filteredChannels = channels.filter((channel) => {
    const term = channelSearch.trim().toLowerCase();
    if (!term) return true;
    return (
      (channel.title || "").toLowerCase().includes(term) ||
      (channel.slug || "").toLowerCase().includes(term) ||
      (channel.id || "").toLowerCase().includes(term)
    );
  });

  const filteredBounties = bounties.filter((bounty) => {
    const term = bountySearch.trim().toLowerCase();
    if (!term) return true;
    return (
      (bounty.title || "").toLowerCase().includes(term) ||
      (bounty.id || "").toLowerCase().includes(term)
    );
  });
