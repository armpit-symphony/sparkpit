import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { ChatPanel } from "@/components/ChatPanel";
import { ChannelsSidebar } from "@/components/layout/ChannelsSidebar";
import { useAppData, useLayout } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";

export default function Rooms() {
  const { slug, channelId } = useParams();
  const { rooms } = useAppData();
  const { setSecondaryPanel } = useLayout();
  const [room, setRoom] = useState(null);
  const [channels, setChannels] = useState([]);
  const [membership, setMembership] = useState(null);
  const navigate = useNavigate();

  const loadRoom = async () => {
    if (!slug) return;
    try {
      const response = await api.get(`/rooms/${slug}`);
      setRoom(response.data.room);
      setChannels(response.data.channels || []);
      setMembership(response.data.membership);
    } catch (error) {
      toast.error("Room unavailable.");
    }
  };

  useEffect(() => {
    loadRoom();
  }, [slug]);

  useEffect(() => {
    if (!slug && rooms.length > 0) {
      navigate(`/app/rooms/${rooms[0].slug}`);
    }
  }, [slug, rooms, navigate]);

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
    return (
      <div className="flex h-full items-center justify-center text-zinc-500" data-testid="rooms-empty-state">
        Select a room from the sidebar.
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
