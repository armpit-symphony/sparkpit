import React, { useEffect, useRef, useState } from "react";
import { api, getWsUrl } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";

export const ChatPanel = ({ channel, room }) => {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const bottomRef = useRef(null);

  const loadMessages = async () => {
    if (!channel?.id) return;
    try {
      setLoading(true);
      const response = await api.get(`/channels/${channel.id}/messages`);
      setMessages(response.data.items || []);
    } catch (error) {
      toast.error("Unable to load messages.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMessages();
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
        }
      } catch (err) {
        console.error(err);
      }
    };
    return () => socket.close();
  }, [channel?.id]);

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  const sendMessage = async () => {
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
      setDraft("");
    } catch (error) {
      toast.error("Message failed to send.");
    }
  };

  return (
    <div className="flex h-full flex-col" data-testid="chat-panel">
      <div className="border-b border-zinc-800 bg-zinc-950/70 px-6 py-4">
        <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">
          {room?.title}
        </div>
        <div className="text-lg font-semibold text-zinc-100" data-testid="chat-channel-title">
          # {channel?.title}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-6" data-testid="chat-message-list">
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
                  <span className="font-mono" data-testid={`message-sender-${message.id}`}>
                    {message.sender_handle || message.sender_type}
                  </span>
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
        <div className="flex items-center gap-2">
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Transmit message..."
            className="rounded-none border-zinc-800 bg-zinc-950 text-zinc-100"
            data-testid="chat-input"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                sendMessage();
              }
            }}
          />
          <Button
            onClick={sendMessage}
            className="rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
            data-testid="chat-send-button"
          >
            Send
          </Button>
        </div>
      </div>
    </div>
  );
};
