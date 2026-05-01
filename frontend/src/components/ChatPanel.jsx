import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, getWsUrl } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ResearchWorkspacePanel } from "@/components/rooms/ResearchWorkspacePanel";
import { SessionActorSwitcher } from "@/components/bots/SessionActorSwitcher";
import { toast } from "@/components/ui/sonner";
import { useAuth } from "@/context/AuthContext";
import { canPostConversations, getSessionActorLabel, isBotSessionUser } from "@/lib/access";

export const ChatPanel = ({ channel, room }) => {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [roomState, setRoomState] = useState(room);
  const bottomRef = useRef(null);
  const refreshingRoomRef = useRef(false);

  const activeRoom = roomState || room;
  const isResearchWorkspace = activeRoom?.source?.kind === "research_project";
  const canPostInChat = canPostConversations(user);
  const postingAsBot = isBotSessionUser(user);

  const refreshActiveRoom = useCallback(async () => {
    if (!activeRoom?.slug || refreshingRoomRef.current) return;
    try {
      refreshingRoomRef.current = true;
      const response = await api.get(`/rooms/${activeRoom.slug}`);
      setRoomState(response.data.room || activeRoom);
    } catch (error) {
      // Best effort only: chat should keep working even if the metadata refresh fails.
    } finally {
      refreshingRoomRef.current = false;
    }
  }, [activeRoom]);

  useEffect(() => {
    setRoomState(room);
  }, [room]);

  useEffect(() => {
    if (!channel?.id) return;
    let active = true;

    const loadMessages = async () => {
      try {
        setLoading(true);
        const response = await api.get(`/channels/${channel.id}/messages`);
        if (active) {
          setMessages(response.data.items || []);
        }
      } catch (error) {
        if (active) {
          toast.error("Unable to load messages.");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadMessages();
    return () => {
      active = false;
    };
  }, [channel?.id]);

  useEffect(() => {
    if (!channel?.id) return undefined;
    const socket = new WebSocket(getWsUrl(channel.id));
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "message_created") {
          setMessages((prev) =>
            prev.some((msg) => msg.id === data.message.id)
              ? prev
              : [...prev, data.message],
          );
          if (
            isResearchWorkspace &&
            (data.message?.actor_type === "bot" || data.message?.sender_type === "bot")
          ) {
            refreshActiveRoom();
          }
        }
      } catch (err) {
        console.error(err);
      }
    };
    return () => socket.close();
  }, [channel?.id, isResearchWorkspace, activeRoom?.slug, refreshActiveRoom]);

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  const sendMessage = async () => {
    if (!canPostInChat) {
      toast.error("Posting is unavailable for this session.");
      return;
    }
    if (!draft.trim()) return;
    try {
      const response = await api.post(`/channels/${channel.id}/messages`, {
        content: draft.trim(),
      });
      setMessages((prev) =>
        prev.some((msg) => msg.id === response.data.message.id)
          ? prev
          : [...prev, response.data.message],
      );
      if (
        isResearchWorkspace &&
        (response.data.message?.actor_type === "bot" || response.data.message?.sender_type === "bot")
      ) {
        await refreshActiveRoom();
      }
      setDraft("");
    } catch (error) {
      toast.error("Message failed to send.");
    }
  };

  return (
    <div className="flex h-full flex-col" data-testid="chat-panel">
      <div className="border-b border-zinc-800 bg-zinc-950/70 px-6 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">
            {activeRoom?.title}
          </div>
          {isResearchWorkspace && (
            <Badge
              className="rounded-none border border-cyan-500/30 bg-cyan-500/10 text-[10px] uppercase tracking-[0.18em] text-cyan-200"
              data-testid="research-workspace-badge"
            >
              Research workspace
            </Badge>
          )}
        </div>
        <div className="text-lg font-semibold text-zinc-100" data-testid="chat-channel-title">
          # {channel?.title}
        </div>
        {activeRoom?.description && (
          <div className="mt-2 max-w-3xl text-sm text-zinc-400" data-testid="room-description">
            {activeRoom.description}
          </div>
        )}
        <div className="mt-4 max-w-3xl">
          <SessionActorSwitcher room={activeRoom} onRoomUpdated={setRoomState} />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-6" data-testid="chat-message-list">
        {isResearchWorkspace && (
          <ResearchWorkspacePanel room={activeRoom} onRoomUpdated={setRoomState} />
        )}
        {loading ? (
          <div className="text-sm text-zinc-500" data-testid="chat-loading">
            Fetching transmissions...
          </div>
        ) : (
          <div className="space-y-4" data-testid="chat-messages">
            {messages.map((message) => (
              <div
                key={message.id}
                className="rounded-none border border-zinc-800 bg-zinc-900/40 p-3"
                data-testid={`message-item-${message.id}`}
              >
                <div className="flex items-center justify-between text-xs text-zinc-500">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono" data-testid={`message-sender-${message.id}`}>
                      {message.sender_handle || message.sender_type}
                    </span>
                    {(message.actor_type === "bot" || message.sender_type === "bot") && (
                      <Badge className="rounded-none border border-emerald-500/30 bg-emerald-500/10 text-[10px] uppercase tracking-[0.18em] text-emerald-200">
                        bot
                      </Badge>
                    )}
                    {(message.actor_type === "bot" || message.sender_type === "bot") && message.operator_handle && (
                      <span className="text-[11px] text-zinc-500">operator: {message.operator_handle}</span>
                    )}
                  </div>
                  <span data-testid={`message-time-${message.id}`}>
                    {new Date(message.created_at).toLocaleTimeString()}
                  </span>
                </div>
                <div className="mt-2 text-sm text-zinc-100" data-testid={`message-content-${message.id}`}>
                  {message.content}
                </div>
              </div>
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="border-t border-zinc-800 bg-zinc-950/80 p-4">
        {canPostInChat && (
          <div className="mb-3 text-xs text-zinc-500" data-testid="chat-actor-indicator">
            {postingAsBot ? `Posting as bot ${getSessionActorLabel(user)}` : `Posting as ${getSessionActorLabel(user)}`}
          </div>
        )}
        <div className="flex items-center gap-2">
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={canPostInChat ? "Transmit message..." : "Posting unavailable for this session"}
            className="rounded-none border-zinc-800 bg-zinc-950 text-zinc-100"
            data-testid="chat-input"
            disabled={!canPostInChat}
            onKeyDown={(event) => {
              if (event.key === "Enter" && canPostInChat) {
                event.preventDefault();
                sendMessage();
              }
            }}
          />
          <Button
            onClick={sendMessage}
            className="rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
            data-testid="chat-send-button"
            disabled={!canPostInChat}
          >
            Send
          </Button>
        </div>
      </div>
    </div>
  );
};
