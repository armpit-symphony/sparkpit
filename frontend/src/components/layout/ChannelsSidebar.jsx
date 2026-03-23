import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

export const ChannelsSidebar = ({ room, channels, activeChannelId, onChannelCreated }) => {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", slug: "" });
  const navigate = useNavigate();

  const createChannel = async () => {
    try {
      const response = await api.post(`/rooms/${room.slug}/channels`, {
        title: form.title,
        slug: form.slug,
        type: "chat",
      });
      toast.success("Channel online.");
      setOpen(false);
      setForm({ title: "", slug: "" });
      onChannelCreated(response.data.channel);
    } catch (error) {
      toast.error("Channel creation failed.");
    }
  };

  return (
    <div className="flex h-full flex-col" data-testid="channels-sidebar">
      <div className="flex items-center justify-between border-b border-zinc-800 p-4">
        <div>
          <div className="text-xs font-mono uppercase tracking-[0.2em] text-zinc-500">
            Channels
          </div>
          <div className="text-sm font-semibold text-zinc-100" data-testid="channels-room-title">
            {room.title}
          </div>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button
              className="h-7 rounded-none bg-cyan-500/20 text-xs text-cyan-300 hover:bg-cyan-500/30"
              data-testid="create-channel-open"
            >
              New
            </Button>
          </DialogTrigger>
          <DialogContent className="rounded-none border border-zinc-800 bg-zinc-950 text-zinc-100">
            <DialogHeader>
              <DialogTitle data-testid="create-channel-title">Spawn channel</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <Input
                placeholder="Channel title"
                value={form.title}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, title: event.target.value }))
                }
                className="rounded-none border-zinc-800 bg-zinc-950"
                data-testid="create-channel-title-input"
              />
              <Input
                placeholder="channel-slug"
                value={form.slug}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, slug: event.target.value }))
                }
                className="rounded-none border-zinc-800 bg-zinc-950 font-mono"
                data-testid="create-channel-slug-input"
              />
              <Button
                onClick={createChannel}
                className="w-full rounded-none bg-cyan-500 text-black hover:bg-cyan-400"
                data-testid="create-channel-submit"
              >
                Spawn Channel
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
      <ScrollArea className="flex-1 p-4" data-testid="channels-scroll">
        <div className="space-y-2" data-testid="channels-list">
          {channels.map((channel) => (
            <button
              key={channel.id}
              onClick={() => navigate(`/app/rooms/${room.slug}/${channel.id}`)}
              className={`w-full rounded-none border border-zinc-800 px-3 py-2 text-left text-sm text-zinc-200 transition-colors hover:border-amber-500/40 ${
                activeChannelId === channel.id ? "border-amber-500/70" : ""
              }`}
              data-testid={`channel-select-${channel.slug}`}
            >
              # {channel.title}
            </button>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
};
