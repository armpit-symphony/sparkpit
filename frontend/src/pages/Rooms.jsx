import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { ChatPanel } from "@/components/ChatPanel";
import { ChannelsSidebar } from "@/components/layout/ChannelsSidebar";
import { useAppData, useLayout } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";

export default function Rooms() {
  const { slug, channelId } = useParams();
  const { rooms, loadingRooms } = useAppData();
  const { setSecondaryPanel, configureSecondaryPanel } = useLayout();
  const [room, setRoom] = useState(null);
  const [channels, setChannels] = useState([]);
  const [membership, setMembership] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!slug) {
      setSecondaryPanel(null);
      configureSecondaryPanel({
        railKey: "rooms-index",
        hidden: true,
        collapsible: false,
        expandedWidthClass: "w-0 border-r-0",
        collapsedWidthClass: "w-0 border-r-0",
      });
      return;
    }

    configureSecondaryPanel({
      railKey: "room-context",
      expandedWidthClass: "w-64",
      collapsedWidthClass: "w-16",
      collapsible: true,
      defaultCollapsed: false,
      hidden: false,
    });
  }, [configureSecondaryPanel, setSecondaryPanel, slug]);

  const loadRoom = async () => {
    if (!slug) return;
    try {
      const response = await api.get(`/rooms/${slug}`);
      setRoom(response.data.room);
      setChannels(response.data.channels || []);
      setMembership(response.data.membership || response.data.bot_membership || null);
    } catch (error) {
      toast.error("Room unavailable.");
    }
  };

  useEffect(() => {
    if (!slug) return;
    let active = true;

    const loadSelectedRoom = async () => {
      try {
        const response = await api.get(`/rooms/${slug}`);
        if (!active) return;
        setRoom(response.data.room);
        setChannels(response.data.channels || []);
        setMembership(response.data.membership || response.data.bot_membership || null);
      } catch (error) {
        if (active) {
          toast.error("Room unavailable.");
        }
      }
    };

    loadSelectedRoom();
    return () => {
      active = false;
    };
  }, [slug]);

  useEffect(() => {
    if (room) {
      setSecondaryPanel(
        <ChannelsSidebar
          room={room}
          channels={channels}
          activeChannelId={channelId}
          onChannelCreated={(channel) => setChannels((prev) => [...prev, channel])}
        />,
      );
    }
  }, [room, channels, channelId, setSecondaryPanel]);

  useEffect(() => {
    if (channels.length > 0 && !channelId) {
      navigate(`/app/rooms/${slug}/${channels[0].id}`);
    }
  }, [channels, channelId, navigate, slug]);

  const activeChannel = useMemo(
    () => channels.find((channel) => channel.id === channelId),
    [channels, channelId],
  );

  const joinRoom = async () => {
    try {
      await api.post(`/rooms/${slug}/join`);
      toast.success("Joined room.");
      loadRoom();
    } catch (error) {
      toast.error("Unable to join room.");
    }
  };

  if (!slug) {
    const joinedRooms = (rooms || []).filter((item) => item?.joined);
    const visibleRooms = joinedRooms.length > 0 ? joinedRooms : rooms || [];
    return (
      <div className="flex h-full flex-col" data-testid="rooms-index-page">
        <div className="border-b border-zinc-800 bg-zinc-950/70 px-6 py-5">
          <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">
            Rooms
          </div>
          <div className="mt-2 text-2xl font-semibold text-zinc-100">Room index</div>
          <div className="mt-2 max-w-3xl text-sm text-zinc-400">
            Open an existing collaboration space or join a public room from the network index.
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {loadingRooms ? (
            <div className="text-sm text-zinc-500" data-testid="rooms-index-loading">
              Loading rooms...
            </div>
          ) : visibleRooms.length === 0 ? (
            <div
              className="rounded-none border border-zinc-800 bg-zinc-900/40 p-6 text-sm text-zinc-400"
              data-testid="rooms-empty-state"
            >
              No rooms are available yet. Use the sidebar to forge the first room.
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="rooms-index-grid">
              {visibleRooms.map((item) => (
                <div
                  key={item.id}
                  className="rounded-none border border-zinc-800 bg-zinc-900/50 p-5"
                  data-testid={`rooms-index-card-${item.slug}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-lg font-semibold text-zinc-100">
                        {item.title}
                      </div>
                      <div className="mt-1 text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
                        #{item.slug}
                      </div>
                    </div>
                    <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
                      {item.is_public ? "Public" : "Private"}
                    </Badge>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button
                      onClick={() => navigate(`/app/rooms/${item.slug}`)}
                      className="rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
                      data-testid={`rooms-index-open-${item.slug}`}
                    >
                      Open room
                    </Button>
                    {!item.joined && (
                      <Button
                        onClick={() => navigate(`/app/rooms/${item.slug}`)}
                        variant="outline"
                        className="rounded-none border-cyan-500/40 text-cyan-200 hover:bg-cyan-500/10"
                        data-testid={`rooms-index-join-${item.slug}`}
                      >
                        Join / review
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (!room) {
    return (
      <div className="flex h-full items-center justify-center text-zinc-500" data-testid="rooms-loading">
        Loading room...
      </div>
    );
  }

  if (!membership) {
    return (
      <div className="flex h-full items-center justify-center p-6" data-testid="rooms-join-gate">
        <div className="max-w-md rounded-none border border-zinc-800 bg-zinc-900/60 p-6 text-center">
          <div className="text-sm font-semibold">Join #{room.slug}</div>
          <p className="mt-2 text-xs text-zinc-500">
            You need to join this room before participating in chat.
          </p>
          <Button
            onClick={joinRoom}
            className="mt-4 w-full rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
            data-testid="room-join-button"
          >
            Join Room
          </Button>
        </div>
      </div>
    );
  }

  if (!activeChannel) {
    return (
      <div className="flex h-full items-center justify-center text-zinc-500" data-testid="channel-empty">
        Select a channel to start chatting.
      </div>
    );
  }

  return <ChatPanel channel={activeChannel} room={room} />;
}
