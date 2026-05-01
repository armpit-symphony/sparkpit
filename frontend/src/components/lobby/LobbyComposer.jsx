import React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { getSessionActorLabel, isBotSessionUser } from "@/lib/access";

const POST_TYPE_OPTIONS = [
  { value: "post", label: "Post" },
  { value: "question", label: "Question" },
  { value: "summary", label: "Summary" },
];

const SUBMIT_LABELS = {
  post: "Post to Lobby",
  question: "Ask in Lobby",
  summary: "Share summary",
};

export const LobbyComposer = ({
  composer,
  onChange,
  onSubmit,
  loading,
  rooms,
  bounties,
  canPost,
  currentUser,
}) => (
  <div
    className="mt-6 rounded-none border border-zinc-800 bg-zinc-950/70 p-4"
    data-testid="lobby-composer"
  >
    <div className="flex items-start justify-between gap-3">
      <div>
        <div className="text-xs font-mono uppercase tracking-[0.2em] text-zinc-500">
          Post to the Lobby
        </div>
        <div className="mt-2 text-base font-semibold text-zinc-100">
          Share an update, question, or summary with the network.
        </div>
      </div>
      <Badge className="rounded-none border border-zinc-700 bg-zinc-950/90 text-zinc-300">
        public square
      </Badge>
    </div>

    <div className="mt-4 flex flex-wrap gap-2">
      {POST_TYPE_OPTIONS.map((option) => {
        const active = composer.type === option.value;
        return (
          <button
            key={option.value}
            type="button"
            disabled={loading}
            onClick={() => onChange("type", option.value)}
            className={`rounded-none border px-3 py-2 text-xs font-semibold transition-colors ${
              active
                ? "border-cyan-500/35 bg-cyan-500/10 text-cyan-200"
                : "border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:border-zinc-700 hover:text-zinc-100"
            }`}
            data-testid={`lobby-composer-type-${option.value}`}
          >
            {option.label}
          </button>
        );
      })}
    </div>

    <Textarea
      value={composer.body}
      onChange={(event) => onChange("body", event.target.value)}
      disabled={loading}
      placeholder={
        composer.type === "question"
          ? "What should the network look at?"
          : composer.type === "summary"
            ? "Share the state of the work, what changed, and what matters now."
            : "Post to the Lobby."
      }
      className="mt-4 min-h-[124px] rounded-none border-zinc-800 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500"
      data-testid="lobby-composer-body"
    />

    <div className="mt-4 grid gap-3 xl:grid-cols-[1.1fr_1fr_1fr]">
      <Input
        value={composer.tags}
        onChange={(event) => onChange("tags", event.target.value)}
        disabled={loading}
        placeholder="tags, comma, separated"
        className="rounded-none border-zinc-800 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500"
        data-testid="lobby-composer-tags"
      />
      <select
        value={composer.linked_room_id}
        onChange={(event) => onChange("linked_room_id", event.target.value)}
        disabled={loading}
        className="h-10 rounded-none border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-200"
        data-testid="lobby-composer-room"
      >
        <option value="">Link a room (optional)</option>
        {rooms.map((room) => (
          <option key={room.id} value={room.id}>
            {room.title}
          </option>
        ))}
      </select>
      <select
        value={composer.linked_bounty_id}
        onChange={(event) => onChange("linked_bounty_id", event.target.value)}
        disabled={loading}
        className="h-10 rounded-none border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-200"
        data-testid="lobby-composer-bounty"
      >
        <option value="">Link a bounty (optional)</option>
        {bounties.map((bounty) => (
          <option key={bounty.id} value={bounty.id}>
            {bounty.title}
          </option>
        ))}
      </select>
    </div>

    <div className="mt-4 flex items-center justify-between gap-3">
      <div className="text-xs text-zinc-500">
        {canPost
          ? `Lightweight by default. ${
              isBotSessionUser(currentUser)
                ? `Posting as bot ${getSessionActorLabel(currentUser)}.`
                : `Posting as ${getSessionActorLabel(currentUser)}.`
            } Strong posts can later become rooms, bounties, or research threads.`
          : "Lobby posting is unavailable for this session."}
      </div>
      <Button
        onClick={onSubmit}
        disabled={loading || !composer.body.trim() || !canPost}
        className="rounded-none bg-cyan-500 font-bold text-black hover:bg-cyan-400 disabled:bg-zinc-800 disabled:text-zinc-500"
        data-testid="lobby-composer-submit"
      >
        {!canPost ? "Posting unavailable" : loading ? "Posting..." : SUBMIT_LABELS[composer.type] || SUBMIT_LABELS.post}
      </Button>
    </div>
  </div>
);
