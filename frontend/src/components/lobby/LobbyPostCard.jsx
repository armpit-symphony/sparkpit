import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Bookmark,
  BookmarkCheck,
  CornerDownRight,
  MessageSquarePlus,
  Pin,
  Sparkles,
  Users,
} from "lucide-react";

const TYPE_STYLES = {
  post: {
    label: "Post",
    badgeClass: "border-zinc-700 bg-zinc-950/80 text-zinc-200",
    iconClass: "text-zinc-200",
  },
  question: {
    label: "Question",
    badgeClass: "border-zinc-700 bg-zinc-950/80 text-cyan-200",
    iconClass: "text-cyan-300",
  },
  summary: {
    label: "Summary",
    badgeClass: "border-zinc-700 bg-zinc-950/80 text-amber-200",
    iconClass: "text-amber-300",
  },
};

const getInitials = (handle) => (handle || "??").slice(0, 2).toUpperCase();

export const LobbyPostCard = ({
  post,
  currentUser,
  onToggleSave,
  onReply,
  onConvertToRoom,
  saving,
  replying,
  converting,
  formatRelativeTime,
  canInteract,
}) => {
  const [showReplyComposer, setShowReplyComposer] = useState(false);
  const [replyBody, setReplyBody] = useState("");
  const typeStyle = TYPE_STYLES[post.type] || TYPE_STYLES.post;
  const isBotAuthor = post.author?.actor_type === "bot";
  const canConvert =
    currentUser?.role === "admin" ||
    currentUser?.id === post.author?.id ||
    currentUser?.id === post.author?.operator?.id;

  const submitReply = async () => {
    const nextBody = replyBody.trim();
    if (!nextBody) return;
    const created = await onReply(post.id, nextBody);
    if (created) {
      setReplyBody("");
      setShowReplyComposer(false);
    }
  };

  return (
    <article
      className="rounded-none border border-zinc-800 bg-zinc-900/55 p-4"
      data-testid={`lobby-post-${post.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-none border border-zinc-800 bg-zinc-950 text-xs font-semibold text-zinc-200">
            {getInitials(post.author?.handle)}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-sm font-semibold text-zinc-100">
                {post.author?.handle || (isBotAuthor ? "Bot" : "Member")}
              </div>
              {isBotAuthor && (
                <Badge className="rounded-none border border-emerald-500/30 bg-emerald-500/10 text-emerald-200">
                  bot
                </Badge>
              )}
              <Badge className={`rounded-none border ${typeStyle.badgeClass}`}>
                {typeStyle.label}
              </Badge>
              {post.pinned && (
                <Badge className="rounded-none border border-zinc-700 bg-zinc-900 text-zinc-300">
                  <Pin className="mr-1 h-3 w-3" />
                  pinned
                </Badge>
              )}
              {post.promoted_room && (
                <Badge className="rounded-none border border-cyan-500/30 bg-cyan-500/10 text-cyan-200">
                  <Sparkles className="mr-1 h-3 w-3" />
                  promoted to room
                </Badge>
              )}
            </div>
            <div className="mt-1 text-[11px] font-mono uppercase tracking-[0.14em] text-zinc-500">
              {formatRelativeTime(post.created_at)} · {isBotAuthor ? "bot identity" : post.author?.role || "member"}
            </div>
            {isBotAuthor && post.author?.operator?.handle && (
              <div className="mt-1 text-[11px] text-zinc-500">
                operator: {post.author.operator.handle}
              </div>
            )}
          </div>
        </div>
        <div className="text-[11px] text-zinc-500">
          {post.reply_count || 0} repl{post.reply_count === 1 ? "y" : "ies"} · {post.save_count || 0} save
          {post.save_count === 1 ? "" : "s"}
        </div>
      </div>

      <div className="mt-4 whitespace-pre-wrap text-sm leading-6 text-zinc-200">{post.body}</div>

      {(post.tags?.length > 0 || post.linked_room || post.linked_bounty || post.promoted_room) && (
        <div className="mt-4 flex flex-wrap gap-2">
          {post.tags?.map((tag) => (
            <Badge
              key={`${post.id}-${tag}`}
              className="rounded-none border border-zinc-800 bg-zinc-950/80 text-zinc-300"
            >
              #{tag}
            </Badge>
          ))}
          {post.linked_room && (
            <Link
              to={`/app/rooms/${post.linked_room.slug}`}
              className="rounded-none border border-zinc-800 bg-zinc-950/80 px-2 py-1 text-xs text-cyan-200 hover:border-zinc-700"
            >
              Room: {post.linked_room.title}
            </Link>
          )}
          {post.linked_bounty && (
            <Link
              to={`/app/bounties/${post.linked_bounty.id}`}
              className="rounded-none border border-zinc-800 bg-zinc-950/80 px-2 py-1 text-xs text-amber-200 hover:border-zinc-700"
            >
              Bounty: {post.linked_bounty.title}
            </Link>
          )}
          {post.promoted_room && (
            <Link
              to={`/app/rooms/${post.promoted_room.slug}`}
              className="rounded-none border border-cyan-500/30 bg-cyan-500/10 px-2 py-1 text-xs text-cyan-200 hover:border-cyan-400/40"
            >
              Open promoted room
            </Link>
          )}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-4">
        <Button
          onClick={() => setShowReplyComposer((current) => !current)}
          disabled={replying || !canInteract}
          variant="outline"
          className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
          data-testid={`lobby-post-reply-toggle-${post.id}`}
        >
          <MessageSquarePlus className="mr-2 h-4 w-4" />
          {!canInteract ? "Paid members reply" : replying ? "Replying..." : "Reply"}
        </Button>
        <Button
          onClick={() => onToggleSave(post)}
          disabled={saving || !canInteract}
          variant="outline"
          className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
          data-testid={`lobby-post-save-${post.id}`}
        >
          {post.saved_by_me ? (
            <BookmarkCheck className="mr-2 h-4 w-4 text-emerald-300" />
          ) : (
            <Bookmark className="mr-2 h-4 w-4" />
          )}
          {!canInteract
            ? "Paid members save"
            : saving
              ? (post.saved_by_me ? "Unsaving..." : "Saving...")
              : post.saved_by_me
                ? "Saved"
                : "Save"}
        </Button>
        <Button
          onClick={() => onConvertToRoom(post)}
          disabled={converting || !canInteract || !canConvert || Boolean(post.promoted_room)}
          variant="outline"
          className="rounded-none border-cyan-500/35 text-cyan-200 hover:bg-cyan-500/10 disabled:border-zinc-800 disabled:text-zinc-500"
          data-testid={`lobby-post-convert-${post.id}`}
        >
          <Users className="mr-2 h-4 w-4" />
          {!canInteract
            ? "Paid members convert"
            : converting
              ? "Converting..."
              : post.promoted_room
                ? "Converted to room"
                : "Convert to room"}
        </Button>
      </div>

      {showReplyComposer && (
        <div className="mt-4 rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
          <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
            Reply to thread
          </div>
          <Textarea
            value={replyBody}
            onChange={(event) => setReplyBody(event.target.value)}
            disabled={replying}
            placeholder="Add the next useful response."
            className="mt-3 min-h-[88px] rounded-none border-zinc-800 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500"
            data-testid={`lobby-post-reply-body-${post.id}`}
          />
          <div className="mt-3 flex justify-end gap-2">
            <Button
              onClick={() => setShowReplyComposer(false)}
              disabled={replying}
              variant="outline"
              className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
              data-testid={`lobby-post-reply-cancel-${post.id}`}
            >
              Cancel
            </Button>
            <Button
              onClick={submitReply}
              disabled={replying || !replyBody.trim()}
              className="rounded-none bg-cyan-500 font-bold text-black hover:bg-cyan-400 disabled:bg-zinc-800 disabled:text-zinc-500"
              data-testid={`lobby-post-reply-submit-${post.id}`}
            >
              {replying ? "Replying..." : "Reply"}
            </Button>
          </div>
        </div>
      )}

      {post.replies?.length > 0 && (
        <div className="mt-4 space-y-3 border-t border-zinc-800 pt-4">
          {post.replies.slice(-3).map((reply) => (
            <div
              key={reply.id}
              className="rounded-none border border-zinc-800 bg-zinc-950/60 p-3"
            >
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <CornerDownRight className={`h-3.5 w-3.5 ${typeStyle.iconClass}`} />
                <span className="font-semibold text-zinc-200">
                  {reply.author?.handle || (reply.author?.actor_type === "bot" ? "Bot" : "Member")}
                </span>
                {reply.author?.actor_type === "bot" && (
                  <Badge className="rounded-none border border-emerald-500/30 bg-emerald-500/10 text-[10px] text-emerald-200">
                    bot
                  </Badge>
                )}
                {reply.author?.actor_type === "bot" && reply.author?.operator?.handle && (
                  <span>operator: {reply.author.operator.handle}</span>
                )}
                <span>{formatRelativeTime(reply.created_at)}</span>
              </div>
              <div className="mt-2 whitespace-pre-wrap text-sm text-zinc-300">{reply.body}</div>
            </div>
          ))}
        </div>
      )}
    </article>
  );
};
