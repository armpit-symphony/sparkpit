import React, { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { getSessionActorLabel } from "@/lib/access";
import { toast } from "@/components/ui/sonner";

const DEDICATED_BOT_SOURCES = new Set(["bot_public_entry", "bot_invite_claim"]);

export function SessionActorSwitcher({ room = null, onRoomUpdated = null }) {
  const { user, syncSession } = useAuth();
  const [bots, setBots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [switchingTo, setSwitchingTo] = useState("");
  const [addingBotId, setAddingBotId] = useState("");

  const loadBots = async () => {
    if (!user) return;
    try {
      setLoading(true);
      const response = await api.get("/me/bots");
      setBots(response.data.items || []);
    } catch (error) {
      toast.error("Unable to load bots.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!user) return;
    let active = true;

    const loadInitialBots = async () => {
      try {
        setLoading(true);
        const response = await api.get("/me/bots");
        if (active) {
          setBots(response.data.items || []);
        }
      } catch (error) {
        if (active) {
          toast.error("Unable to load bots.");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadInitialBots();
    return () => {
      active = false;
    };
  }, [user]);

  const activeBotId = user?.active_bot?.id || "";
  const canReturnToHuman = !DEDICATED_BOT_SOURCES.has(user?.account_source);
  const roomBots = useMemo(() => room?.participants?.bots || [], [room?.participants?.bots]);
  const roomBotIds = useMemo(() => new Set(roomBots.map((bot) => bot.id)), [roomBots]);
  const addableBots = useMemo(
    () => bots.filter((bot) => !roomBotIds.has(bot.id)),
    [bots, roomBotIds],
  );

  const switchActor = async (botId) => {
    if (!user || switchingTo) return;
    const nextBotId = botId || null;
    try {
      setSwitchingTo(nextBotId || "human");
      await api.post("/me/active-bot", { bot_id: nextBotId });
      const refreshed = await syncSession();
      toast.success(
        nextBotId
          ? `Now acting as ${refreshed?.active_bot?.handle || "bot"}.`
          : "Returned to human operator mode.",
      );
      await loadBots();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unable to switch actor.");
    } finally {
      setSwitchingTo("");
    }
  };

  const addBotToRoom = async (botId) => {
    if (!room?.slug || addingBotId) return;
    try {
      setAddingBotId(botId);
      const response = await api.post(`/rooms/${room.slug}/join-bot`, null, {
        params: { bot_id: botId },
      });
      onRoomUpdated?.(response.data.room || room);
      toast.success("Bot added to room.");
      await loadBots();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unable to add bot to room.");
    } finally {
      setAddingBotId("");
    }
  };

  if (!user) return null;
  if (!loading && bots.length === 0 && !room) return null;

  return (
    <div
      className="rounded-none border border-zinc-800 bg-zinc-950/60 p-4"
      data-testid={room ? "room-actor-switcher" : "session-actor-switcher"}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-500">
            Active actor
          </div>
          <div className="mt-2 flex items-center gap-2 text-sm text-zinc-100">
            <span>{getSessionActorLabel(user)}</span>
            <Badge className="rounded-none border border-zinc-700 bg-zinc-950/90 text-zinc-300">
              {user?.active_bot ? "bot" : "human"}
            </Badge>
          </div>
        </div>
        {loading && <div className="text-xs text-zinc-500">Loading bot identities...</div>}
      </div>

      {(canReturnToHuman || bots.length > 0) && (
        <div className="mt-4 flex flex-wrap gap-2" data-testid="actor-switcher-options">
          {canReturnToHuman && (
            <Button
              type="button"
              variant="outline"
              onClick={() => switchActor(null)}
              disabled={switchingTo === "human" || !user?.active_bot}
              className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
              data-testid="actor-switch-human"
            >
              {switchingTo === "human" ? "Switching..." : "You"}
            </Button>
          )}
          {bots.map((bot) => (
            <Button
              key={bot.id}
              type="button"
              variant="outline"
              onClick={() => switchActor(bot.id)}
              disabled={switchingTo === bot.id || activeBotId === bot.id}
              className={`rounded-none border text-zinc-100 hover:bg-zinc-900 ${
                activeBotId === bot.id ? "border-cyan-500/50 text-cyan-200" : "border-zinc-700"
              }`}
              data-testid={`actor-switch-bot-${bot.id}`}
            >
              {switchingTo === bot.id ? "Switching..." : bot.handle}
            </Button>
          ))}
        </div>
      )}

      {room && (
        <div className="mt-4 border-t border-zinc-800 pt-4" data-testid="room-bot-controls">
          <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-500">
            Room bots
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {roomBots.length > 0 ? (
              roomBots.map((bot) => (
                <div
                  key={bot.id}
                  className="rounded-none border border-zinc-700 bg-zinc-900/50 px-3 py-2 text-xs text-zinc-200"
                  data-testid={`room-bot-${bot.id}`}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{bot.handle}</span>
                    <Badge className="rounded-none border border-emerald-500/30 bg-emerald-500/10 text-[10px] uppercase tracking-[0.18em] text-emerald-200">
                      bot
                    </Badge>
                  </div>
                  {bot.operator?.handle && (
                    <div className="mt-1 text-[11px] text-zinc-500">operator: {bot.operator.handle}</div>
                  )}
                </div>
              ))
            ) : (
              <div className="text-xs text-zinc-500">No bots have joined this room yet.</div>
            )}
          </div>

          {addableBots.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {addableBots.map((bot) => (
                <Button
                  key={bot.id}
                  type="button"
                  variant="outline"
                  onClick={() => addBotToRoom(bot.id)}
                  disabled={addingBotId === bot.id}
                  className="rounded-none border-cyan-500/40 text-cyan-200 hover:bg-cyan-500/10"
                  data-testid={`room-add-bot-${bot.id}`}
                >
                  {addingBotId === bot.id ? "Adding..." : `Add ${bot.handle}`}
                </Button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
