import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useAppData, useLayout } from "@/components/layout/AppShell";
import { LobbyComposer } from "@/components/lobby/LobbyComposer";
import { LobbyPostCard } from "@/components/lobby/LobbyPostCard";
import { LobbyRail } from "@/components/lobby/LobbyRail";
import { BotCollaborationGuide } from "@/components/bots/BotCollaborationGuide";
import { SessionActorSwitcher } from "@/components/bots/SessionActorSwitcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { canPostConversations, isBotSessionUser } from "@/lib/access";
import { toast } from "@/components/ui/sonner";
import {
  Activity,
  Bot,
  Briefcase,
  FolderKanban,
  MessageSquareQuote,
  Sparkles,
  Users,
} from "lucide-react";

const ACTIVE_BOUNTY_STATES = new Set(["open", "claimed", "submitted"]);
const OPEN_TASK_STATES = new Set(["open", "claimed", "in_progress"]);
const COMPLETED_TASK_STATES = new Set(["done", "completed", "approved", "closed"]);

const FEED_TYPE_STYLES = {
  question: {
    label: "Question",
    badgeClass: "border-zinc-700 bg-zinc-950/80 text-cyan-200",
    cardClass: "border-zinc-800 bg-zinc-900/50",
    iconClass: "text-cyan-300",
  },
  "bot-update": {
    label: "Bot update",
    badgeClass: "border-zinc-700 bg-zinc-950/80 text-emerald-200",
    cardClass: "border-zinc-800 bg-zinc-900/50",
    iconClass: "text-emerald-300",
  },
  "room-update": {
    label: "Room update",
    badgeClass: "border-zinc-700 bg-zinc-950/80 text-sky-200",
    cardClass: "border-zinc-800 bg-zinc-900/50",
    iconClass: "text-sky-300",
  },
  "open-call": {
    label: "Open call",
    badgeClass: "border-zinc-700 bg-zinc-950/80 text-amber-200",
    cardClass: "border-zinc-800 bg-zinc-900/50",
    iconClass: "text-amber-300",
  },
  bounty: {
    label: "Bounty",
    badgeClass: "border-zinc-700 bg-zinc-950/80 text-pink-200",
    cardClass: "border-zinc-800 bg-zinc-900/50",
    iconClass: "text-pink-300",
  },
  summary: {
    label: "Summary",
    badgeClass: "border-zinc-700 bg-zinc-900 text-zinc-200",
    cardClass: "border-zinc-800 bg-zinc-900/60",
    iconClass: "text-zinc-200",
  },
};

const FEED_TYPE_PRIORITY = {
  question: 0,
  "bot-update": 1,
  "room-update": 2,
  "open-call": 3,
  bounty: 4,
  summary: 5,
};

const formatRelativeTime = (value) => {
  if (!value) return "Quiet";

  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "Quiet";

  const deltaMinutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
  if (deltaMinutes < 1) return "Just now";
  if (deltaMinutes < 60) return `${deltaMinutes}m ago`;

  const deltaHours = Math.floor(deltaMinutes / 60);
  if (deltaHours < 24) return `${deltaHours}h ago`;

  const deltaDays = Math.floor(deltaHours / 24);
  return `${deltaDays}d ago`;
};

const getTimestamp = (value) => {
  const timestamp = new Date(value || 0).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
};

const trimSnippet = (value, max = 92) => {
  const normalized = (value || "").trim().replace(/\s+/g, " ");
  if (!normalized) return "Fresh signal";
  return normalized.length <= max ? normalized : `${normalized.slice(0, max - 1)}…`;
};

const uniqueById = (items) =>
  items.filter((item, index, list) => list.findIndex((entry) => entry.id === item.id) === index);

const buildFeedItem = (item) => ({
  generated: false,
  ...item,
});

const humanizeEventType = (value) => {
  if (!value) return "Signal pulse";
  return value
    .split(".")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
};

const activityEventToFeedItem = (event) => {
  const actor = event.actor?.handle || event.actor?.name || "Someone";
  const roomTitle = event.room?.title || "a room";
  const roomSlug = event.room?.slug;
  const bountyTitle = event.bounty?.title || "a bounty";
  const botHandle = event.bot?.handle || "a bot";

  switch (event.event_type) {
    case "room.created":
      return buildFeedItem({
        id: `activity-${event.id}`,
        type: "room-update",
        title: `${roomTitle} just opened`,
        detail: `${actor} opened a fresh working thread, so there is a new place to gather context and move a question forward.`,
        meta: `${formatRelativeTime(event.created_at)} · New room`,
        link: roomSlug ? `/app/rooms/${roomSlug}` : "/app/rooms",
        icon: Users,
        timestamp: event.created_at,
      });
    case "room.joined":
      return buildFeedItem({
        id: `activity-${event.id}`,
        title: `${actor} joined ${roomTitle}`,
        type: "room-update",
        detail: "The room picked up another participant, which usually means more context, faster replies, and better momentum.",
        meta: `${formatRelativeTime(event.created_at)} · Room activity`,
        link: roomSlug ? `/app/rooms/${roomSlug}` : "/app/rooms",
        icon: Users,
        timestamp: event.created_at,
      });
    case "bot.joined":
      return buildFeedItem({
        id: `activity-${event.id}`,
        type: "bot-update",
        title: `${botHandle} is now live in ${roomTitle}`,
        detail: "That room now has an active agent available for summaries, digging through context, or tightening the next move.",
        meta: `${formatRelativeTime(event.created_at)} · Agent entered room`,
        link: roomSlug ? `/app/rooms/${roomSlug}` : "/app/bots",
        icon: Bot,
        timestamp: event.created_at,
      });
    case "bounty.created":
      return buildFeedItem({
        id: `activity-${event.id}`,
        type: "open-call",
        title: `${bountyTitle} needs help`,
        detail: `${actor} opened a concrete call for help${roomTitle !== "a room" ? ` in ${roomTitle}` : ""}, so there is new work the network can actually pick up right now.`,
        meta: `${formatRelativeTime(event.created_at)} · New open call`,
        link: event.bounty?.id ? `/app/bounties/${event.bounty.id}` : "/app/bounties",
        icon: Briefcase,
        timestamp: event.created_at,
      });
    case "bounty.claimed":
      return buildFeedItem({
        id: `activity-${event.id}`,
        type: "bounty",
        title: `${bountyTitle} moved into execution`,
        detail: `${actor} picked it up, which means the ask is no longer idle and delivery is actively underway.`,
        meta: `${formatRelativeTime(event.created_at)} · Bounty claimed`,
        link: event.bounty?.id ? `/app/bounties/${event.bounty.id}` : "/app/bounties",
        icon: Briefcase,
        timestamp: event.created_at,
      });
    case "bounty.submitted":
    case "bounty.approved":
      return buildFeedItem({
        id: `activity-${event.id}`,
        type: "summary",
        title: `${bountyTitle} advanced`,
        detail: `${actor} pushed the work forward, which gives the network a fresh delivery milestone to review or build on.`,
        meta: `${formatRelativeTime(event.created_at)} · Delivery milestone`,
        link: event.bounty?.id ? `/app/bounties/${event.bounty.id}` : "/app/bounties",
        icon: Briefcase,
        timestamp: event.created_at,
      });
    default:
      return null;
  }
};

const taskToFeedItem = (task, roomsById) => {
  const roomTitle = roomsById.get(task.room_id)?.title || "Unassigned room";
  const state = task.state || task.status || "open";
  if (!COMPLETED_TASK_STATES.has(state)) return null;

  return buildFeedItem({
    id: `task-${task.id}`,
    type: "summary",
    title: `${task.title} wrapped in ${roomTitle}`,
    detail: "A concrete piece of room work closed out, which frees the thread to move to the next decision or delivery.",
    meta: `${formatRelativeTime(task.updated_at || task.created_at)} · Task completion`,
    link: "/app/rooms",
    icon: FolderKanban,
    timestamp: task.updated_at || task.created_at,
  });
};

const bountyToFeedItem = (bounty, roomsById) => {
  const roomTitle = roomsById.get(bounty.room_id)?.title || "Network board";
  const type = bounty.status === "open" ? "open-call" : "bounty";

  return buildFeedItem({
    id: `bounty-${bounty.id}`,
    type,
    title:
      bounty.status === "open"
        ? `${bounty.title} is open`
        : bounty.status === "claimed"
          ? `${bounty.title} is in progress`
          : bounty.title,
    detail:
      bounty.status === "claimed"
        ? `Claimed from ${roomTitle}, so that open call has moved into real execution.`
        : bounty.status === "submitted"
          ? `Submitted from ${roomTitle} and ready for review or approval.`
          : `Still open${roomTitle ? ` in ${roomTitle}` : ""}, waiting for someone to pick it up.`,
    meta: `${formatRelativeTime(bounty.updated_at || bounty.created_at)} · ${type === "open-call" ? "Open call" : "Bounty update"}`,
    link: `/app/bounties/${bounty.id}`,
    icon: Briefcase,
    timestamp: bounty.updated_at || bounty.created_at,
  });
};

const botToFeedItem = (bot) => {
  const status = bot.presence?.status || bot.status || "offline";
  if (status !== "online") return null;

  return buildFeedItem({
    id: `bot-${bot.id}`,
    type: "bot-update",
    title: `${bot.name || bot.handle} is standing by`,
    detail:
      bot.bio ||
      `${bot.handle || "This bot"} is online and ready to summarize context, answer questions, or tighten a room brief.`,
    meta: `${formatRelativeTime(bot.presence?.last_seen_at || bot.last_seen_at)} · Agent available`,
    link: "/app/bots",
    icon: Bot,
    timestamp: bot.presence?.last_seen_at || bot.last_seen_at || bot.created_at,
  });
};

const auditToSignalItem = (event) => ({
  id: `audit-${event.id}`,
  label: humanizeEventType(event.event_type),
  meta: `${formatRelativeTime(event.created_at)} · Admin signal`,
  link: "/app/settings#audit",
});

const postToSignalItem = (post) => ({
  id: `post-${post.id}`,
  label:
    post.type === "question"
      ? `${post.author?.handle || "Someone"} asked: ${trimSnippet(post.body, 68)}`
      : post.type === "summary"
        ? `${post.author?.handle || "Someone"} shared a summary`
        : `${post.author?.handle || "Someone"} posted to the Lobby`,
  meta: `${formatRelativeTime(post.created_at)} · ${post.type}`,
  link: "/app/lobby",
});

const postToMilestone = (post) => ({
  id: `milestone-${post.id}`,
  title:
    post.type === "question"
      ? trimSnippet(post.body, 80)
      : post.promoted_room
        ? `${post.author?.handle || "Member"} turned a post into a room`
        : `${post.author?.handle || "Member"} posted to the square`,
  detail: post.promoted_room
    ? `Now live as ${post.promoted_room.title}.`
    : trimSnippet(post.body, 120),
});

const buildPromptFeedItems = ({ rooms, openBounties, openTasks, onlineBots }) => {
  const firstRoom = rooms[0];
  const prompts = [];

  if (rooms.length === 0) {
    prompts.push({
      id: "prompt-first-room",
      type: "question",
      title: "What should the first room investigate?",
      detail: "A clear question gives people and bots one shared thread to gather around instead of scattering context across the network.",
      meta: "Suggested next move",
      link: "/app/rooms",
      icon: MessageSquareQuote,
      generated: true,
    });
  }

  if (rooms.length > 0 && openBounties.length === 0 && openTasks.length === 0) {
    prompts.push({
      id: "prompt-first-call",
      type: "question",
      title: `What should ${firstRoom?.title || "the network"} work on next?`,
      detail: "Turn the next concrete need into a bounty or task so the network has a real ask to rally around.",
      meta: "Suggested next move",
      link: "/app/bounties",
      icon: MessageSquareQuote,
      generated: true,
    });
  }

  if (rooms.length > 0 && onlineBots.length > 0) {
    prompts.push({
      id: "prompt-bot-brief",
      type: "question",
      title: "Which room needs a bot brief right now?",
      detail: "Point an online agent at the room with the loosest brief or the thickest context so the next handoff gets easier.",
      meta: "Suggested next move",
      link: "/app/bots",
      icon: MessageSquareQuote,
      generated: true,
    });
  }

  return prompts;
};

const buildSummaryFeedItems = ({ rooms, openBounties, openTasks, onlineBots, feedCount }) => {
  const totalOpenWork = openBounties.length + openTasks.length;
  const items = [];

  if (rooms.length > 0 || totalOpenWork > 0 || onlineBots.length > 0) {
    items.push({
      id: "summary-network-state",
      type: "summary",
      title: "Network summary",
      detail: `${rooms.length} active room${rooms.length === 1 ? "" : "s"}, ${totalOpenWork} open work item${totalOpenWork === 1 ? "" : "s"}, and ${onlineBots.length} agent${onlineBots.length === 1 ? "" : "s"} ready to help right now.`,
      meta: feedCount > 0 ? "At-a-glance state" : "Starter overview",
      link: "/app/activity",
      icon: Sparkles,
      generated: true,
    });
  }

  return items;
};

const sortFeedItems = (items) =>
  [...items].sort((left, right) => {
    const priorityDelta =
      (FEED_TYPE_PRIORITY[left.type] ?? FEED_TYPE_PRIORITY.summary) -
      (FEED_TYPE_PRIORITY[right.type] ?? FEED_TYPE_PRIORITY.summary);

    if (priorityDelta !== 0) {
      return priorityDelta;
    }

    return getTimestamp(right.timestamp) - getTimestamp(left.timestamp);
  });

const composeDerivedFeed = ({ realItems, promptItems, summaryItems, limit }) => {
  const rankedRealItems = sortFeedItems(realItems);
  const promptLimit = rankedRealItems.length >= 5 ? 0 : rankedRealItems.length >= 2 ? 1 : 2;
  const prompts = promptItems.slice(0, promptLimit);
  const feed = [];

  if (rankedRealItems.length === 0) {
    return uniqueById([...prompts, ...summaryItems]).slice(0, limit);
  }

  if (prompts[0]) {
    feed.push(prompts[0]);
  }

  feed.push(...rankedRealItems);

  if (prompts[1]) {
    const insertAt = Math.min(3, feed.length);
    feed.splice(insertAt, 0, prompts[1]);
  }

  return uniqueById([...feed, ...summaryItems]).slice(0, limit);
};

const replaceLobbyPost = (posts, nextPost) => {
  const existing = posts.some((post) => post.id === nextPost.id);
  if (!existing) {
    return [nextPost, ...posts];
  }
  return posts.map((post) => (post.id === nextPost.id ? nextPost : post));
};

const parseTagInput = (raw) =>
  raw
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);

const createEmptySnapshot = () => ({
  lobbyPosts: [],
  bounties: [],
  tasks: [],
  bots: [],
  activity: [],
  auditEvents: [],
});

const addPendingId = (pendingIds, id) => (pendingIds.includes(id) ? pendingIds : [...pendingIds, id]);

const removePendingId = (pendingIds, id) => pendingIds.filter((pendingId) => pendingId !== id);

const fetchLobbySnapshot = async (isAdmin) => {
  const requests = [
    api.get("/lobby/posts", { params: { limit: 24 } }),
    api.get("/bounties", { params: { sort: "newest", limit: 24 } }),
    api.get("/tasks"),
    api.get("/bots"),
    api.get("/activity"),
  ];

  if (isAdmin) {
    requests.push(api.get("/admin/audit"));
  }

  const [
    lobbyPostsResponse,
    bountiesResponse,
    tasksResponse,
    botsResponse,
    activityResponse,
    auditResponse,
  ] = await Promise.allSettled(requests);

  return {
    lobbyPosts:
      lobbyPostsResponse.status === "fulfilled"
        ? lobbyPostsResponse.value.data.items || []
        : [],
    bounties:
      bountiesResponse.status === "fulfilled"
        ? bountiesResponse.value.data.items || []
        : [],
    tasks:
      tasksResponse.status === "fulfilled"
        ? tasksResponse.value.data.items || []
        : [],
    bots: botsResponse.status === "fulfilled" ? botsResponse.value.data.items || [] : [],
    activity:
      activityResponse.status === "fulfilled"
        ? activityResponse.value.data.items || []
        : [],
    auditEvents:
      auditResponse?.status === "fulfilled"
        ? auditResponse.value.data.items || []
        : [],
  };
};

export default function Lobby() {
  const { user } = useAuth();
  const { rooms, loadingRooms, refreshRooms } = useAppData();
  const { setSecondaryPanel, configureSecondaryPanel } = useLayout();
  const [snapshot, setSnapshot] = useState(createEmptySnapshot);
  const [loading, setLoading] = useState(true);
  const [composer, setComposer] = useState({
    type: "post",
    body: "",
    tags: "",
    linked_room_id: "",
    linked_bounty_id: "",
  });
  const [creatingPost, setCreatingPost] = useState(false);
  const [savingPostIds, setSavingPostIds] = useState([]);
  const [replyingPostIds, setReplyingPostIds] = useState([]);
  const [convertingPostIds, setConvertingPostIds] = useState([]);
  const snapshotRequestRef = useRef(0);
  const canPostInLobby = canPostConversations(user);
  const botActorActive = isBotSessionUser(user);

  useEffect(() => {
    configureSecondaryPanel({
      railKey: "lobby-utility",
      expandedWidthClass: "w-72",
      collapsedWidthClass: "w-16",
      collapsible: true,
      defaultCollapsed: true,
      hidden: false,
    });
  }, [configureSecondaryPanel]);

  useEffect(() => {
    let active = true;

    const loadSnapshot = async () => {
      const requestId = snapshotRequestRef.current + 1;
      snapshotRequestRef.current = requestId;

      try {
        const nextSnapshot = await fetchLobbySnapshot(user?.role === "admin");

        if (!active || requestId !== snapshotRequestRef.current) return;

        setSnapshot(nextSnapshot);
      } catch (error) {
        if (active && requestId === snapshotRequestRef.current) {
          toast.error("Unable to sync lobby state.");
        }
      } finally {
        if (active && requestId === snapshotRequestRef.current) {
          setLoading(false);
        }
      }
    };

    loadSnapshot();
    const interval = setInterval(loadSnapshot, 25000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [user?.role]);

  const updateComposer = (field, value) => {
    if (creatingPost) return;
    setComposer((current) => ({ ...current, [field]: value }));
  };

  const createPost = async () => {
    if (creatingPost) return;
    if (!canPostInLobby) {
      toast.error("Posting is unavailable for this session.");
      return;
    }

    const nextBody = composer.body.trim();
    if (!nextBody) return;

    try {
      setCreatingPost(true);
      const postType = composer.type;
      const response = await api.post("/lobby/posts", {
        type: postType,
        body: nextBody,
        tags: parseTagInput(composer.tags),
        linked_room_id: composer.linked_room_id || null,
        linked_bounty_id: composer.linked_bounty_id || null,
      });
      setSnapshot((current) => ({
        ...current,
        lobbyPosts: replaceLobbyPost(current.lobbyPosts, response.data.post),
      }));
      setComposer({
        type: "post",
        body: "",
        tags: "",
        linked_room_id: "",
        linked_bounty_id: "",
      });
      toast.success(
        postType === "question"
          ? "Question posted to Lobby."
          : postType === "summary"
            ? "Summary posted to Lobby."
            : "Lobby post published.",
      );
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unable to post to the Lobby.");
    } finally {
      setCreatingPost(false);
    }
  };

  const toggleSave = async (post) => {
    if (savingPostIds.includes(post.id)) return;
    if (!canPostInLobby) {
      toast.error("Posting is unavailable for this session.");
      return;
    }

    try {
      setSavingPostIds((current) => addPendingId(current, post.id));
      const response = post.saved_by_me
        ? await api.delete(`/lobby/posts/${post.id}/save`)
        : await api.post(`/lobby/posts/${post.id}/save`);
      setSnapshot((current) => ({
        ...current,
        lobbyPosts: replaceLobbyPost(current.lobbyPosts, response.data.post),
      }));
    } catch (error) {
      toast.error("Unable to update saved state.");
    } finally {
      setSavingPostIds((current) => removePendingId(current, post.id));
    }
  };

  const replyToPost = async (postId, body) => {
    if (replyingPostIds.includes(postId)) return false;
    if (!canPostInLobby) {
      toast.error("Posting is unavailable for this session.");
      return false;
    }

    try {
      setReplyingPostIds((current) => addPendingId(current, postId));
      const response = await api.post(`/lobby/posts/${postId}/replies`, { body });
      setSnapshot((current) => ({
        ...current,
        lobbyPosts: replaceLobbyPost(current.lobbyPosts, response.data.post),
      }));
      toast.success("Reply posted.");
      return true;
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unable to reply.");
      return false;
    } finally {
      setReplyingPostIds((current) => removePendingId(current, postId));
    }
  };

  const convertPostToRoom = async (post) => {
    if (convertingPostIds.includes(post.id)) return;
    if (!canPostInLobby) {
      toast.error("Posting is unavailable for this session.");
      return;
    }

    try {
      setConvertingPostIds((current) => addPendingId(current, post.id));
      const response = await api.post(`/lobby/posts/${post.id}/convert-room`);
      setSnapshot((current) => ({
        ...current,
        lobbyPosts: replaceLobbyPost(current.lobbyPosts, response.data.post),
      }));
      await refreshRooms();
      toast.success(response.data.room ? "Room created from Lobby post." : "Lobby post already has a room.");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unable to convert post into a room.");
    } finally {
      setConvertingPostIds((current) => removePendingId(current, post.id));
    }
  };

  const viewModel = useMemo(() => {
    const roomsById = new Map(rooms.map((room) => [room.id, room]));
    const openBounties = snapshot.bounties.filter((bounty) =>
      ACTIVE_BOUNTY_STATES.has(bounty.status),
    );
    const openTasks = snapshot.tasks.filter((task) =>
      OPEN_TASK_STATES.has(task.state || task.status || "open"),
    );
    const onlineBots = snapshot.bots.filter(
      (bot) => (bot.presence?.status || bot.status) === "online",
    );
    const latestAudit = snapshot.auditEvents[0] || null;
    const latestActivity = snapshot.activity[0] || null;

    const nativePosts = [...snapshot.lobbyPosts].sort((left, right) => {
      const pinDelta = Number(Boolean(right.pinned)) - Number(Boolean(left.pinned));
      if (pinDelta !== 0) return pinDelta;
      return getTimestamp(right.created_at) - getTimestamp(left.created_at);
    });

    const realFeedItems = uniqueById(
      [
        ...snapshot.activity.map(activityEventToFeedItem).filter(Boolean),
        ...snapshot.tasks.map((task) => taskToFeedItem(task, roomsById)).filter(Boolean),
        ...snapshot.bots.map(botToFeedItem).filter(Boolean),
        ...snapshot.bounties
          .filter((bounty) => ACTIVE_BOUNTY_STATES.has(bounty.status))
          .map((bounty) => bountyToFeedItem(bounty, roomsById)),
        ...openTasks.slice(0, 2).map((task) =>
          buildFeedItem({
            id: `task-open-${task.id}`,
            type: "open-call",
            title: `${task.title} needs an owner`,
            detail: `There is open room work waiting in ${roomsById.get(task.room_id)?.title || "a room"}, and it still needs someone to pick it up.`,
            meta: `${formatRelativeTime(task.updated_at || task.created_at)} · Task open`,
            link: "/app/rooms",
            icon: FolderKanban,
            timestamp: task.updated_at || task.created_at,
          }),
        ),
      ].sort((left, right) => getTimestamp(right.timestamp) - getTimestamp(left.timestamp)),
    );

    const promptFeedItems = uniqueById(
      buildPromptFeedItems({ rooms, openBounties, openTasks, onlineBots }),
    );
    const summaryFeedItems = uniqueById(
      buildSummaryFeedItems({
        rooms,
        openBounties,
        openTasks,
        onlineBots,
        feedCount: realFeedItems.length + nativePosts.length,
      }),
    );
    const derivedFeedItems = composeDerivedFeed({
      realItems: realFeedItems,
      promptItems: promptFeedItems,
      summaryItems: summaryFeedItems,
      limit: nativePosts.length >= 4 ? 3 : 5,
    });

    const hybridFeedItems = [
      ...nativePosts.slice(0, 6).map((post) => ({
        id: `native-${post.id}`,
        kind: "native-post",
        timestamp: post.created_at,
        post,
      })),
      ...derivedFeedItems.map((item) => ({
        ...item,
        kind: "derived-update",
      })),
    ].slice(0, 9);

    let signalItems = [
      ...nativePosts.slice(0, 3).map(postToSignalItem),
      ...snapshot.activity
        .map(activityEventToFeedItem)
        .filter(Boolean)
        .slice(0, 4)
        .map((item) => ({
          id: item.id,
          label: item.title,
          meta: item.meta,
          link: item.link,
        })),
      ...snapshot.auditEvents.slice(0, 2).map(auditToSignalItem),
    ].slice(0, 8);

    if (signalItems.length < 4) {
      signalItems.push(
        {
          id: "rooms-count",
          label: `${rooms.length} active rooms visible`,
          meta: "Room network",
          link: "/app/rooms",
        },
        {
          id: "bounties-count",
          label: `${openBounties.length} open bounties in play`,
          meta: "Open calls",
          link: "/app/bounties",
        },
        {
          id: "bots-count",
          label: `${onlineBots.length}/${snapshot.bots.length} agents online`,
          meta: "Bot presence",
          link: "/app/bots",
        },
        {
          id: "access-status",
          label: "Access open",
          meta: "Network access",
          link: "/app/lobby",
        },
      );
    }

    const latestPulse =
      nativePosts[0]?.created_at ||
      latestAudit?.created_at ||
      latestActivity?.created_at ||
      snapshot.bots[0]?.last_seen_at;

    const openWork = [
      ...openBounties.slice(0, 3).map((bounty) => ({
        id: `open-bounty-${bounty.id}`,
        kind: "Bounty",
        title: bounty.title,
        meta: `${bounty.status} · ${bounty.reward_amount ? `${bounty.reward_amount} ${bounty.reward_currency || ""}`.trim() : "No reward set"}`,
        link: `/app/bounties/${bounty.id}`,
      })),
      ...openTasks.slice(0, 3).map((task) => ({
        id: `open-task-${task.id}`,
        kind: "Task",
        title: task.title,
        meta: `${task.state || task.status || "open"} · ${roomsById.get(task.room_id)?.title || "Room work"}`,
        link: "/app/rooms",
      })),
    ];

    return {
      starterMode:
        nativePosts.length === 0 &&
        rooms.length === 0 &&
        snapshot.bounties.length === 0 &&
        snapshot.tasks.length === 0 &&
        snapshot.bots.length === 0 &&
        snapshot.activity.length === 0 &&
        snapshot.auditEvents.length === 0,
      nativePosts,
      onlineBots,
      latestPulse,
      signalItems: signalItems.slice(0, 8),
      hybridFeedItems,
      derivedFeedItems,
      openWork,
      railMilestones: nativePosts.slice(0, 2).map(postToMilestone).concat(derivedFeedItems.slice(0, 2)),
      openBounties,
    };
  }, [rooms, snapshot]);

  const tickerItems = useMemo(() => {
    if (viewModel.signalItems.length === 0) return [];
    return [...viewModel.signalItems, ...viewModel.signalItems].slice(
      0,
      Math.max(viewModel.signalItems.length * 2, 8),
    );
  }, [viewModel.signalItems]);

  useEffect(() => {
    setSecondaryPanel(
      <LobbyRail
        loading={loading || loadingRooms}
        rooms={rooms}
        openWork={viewModel.openWork}
        onlineBots={viewModel.onlineBots}
        milestones={viewModel.railMilestones}
        recentPulse={formatRelativeTime(viewModel.latestPulse)}
      />,
    );
  }, [
    loading,
    loadingRooms,
    rooms,
    setSecondaryPanel,
    viewModel.latestPulse,
    viewModel.onlineBots,
    viewModel.openWork,
    viewModel.railMilestones,
  ]);

  return (
    <div className="flex h-full flex-col" data-testid="lobby-page">
      <div className="border-b border-zinc-800 bg-zinc-950/70 px-6 py-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex items-center gap-2 text-[11px] font-mono uppercase tracking-[0.2em] text-zinc-500">
              <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-400" />
              Live signal
            </div>
            <div
              className="lobby-signal-ticker max-w-full overflow-hidden rounded-none border border-zinc-800 bg-zinc-900/35"
              data-testid="lobby-signal-ribbon"
            >
              <div className="lobby-signal-track">
                {tickerItems.map((item, index) => {
                  const content = (
                    <>
                      <div className="truncate text-sm font-semibold text-zinc-100">{item.label}</div>
                      <div className="mt-1 text-[11px] text-zinc-500">{item.meta}</div>
                    </>
                  );

                  const classes =
                    "lobby-signal-chip block w-[240px] shrink-0 rounded-none border border-zinc-800 bg-zinc-950/75 px-3 py-2 transition-colors hover:border-cyan-500/30 hover:bg-zinc-900";

                  if (item.link) {
                    return (
                      <Link
                        key={`${item.id}-${index}`}
                        to={item.link}
                        className={classes}
                        data-testid={index === 0 ? "lobby-signal-active" : undefined}
                      >
                        {content}
                      </Link>
                    );
                  }

                  return (
                    <div
                      key={`${item.id}-${index}`}
                      className={classes}
                      data-testid={index === 0 ? "lobby-signal-active" : undefined}
                    >
                      {content}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          <div className="xl:w-auto xl:min-w-[360px]">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-3xl font-semibold text-zinc-100">Pit Lobby</div>
              <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
                {viewModel.hybridFeedItems.length} recent
              </Badge>
            </div>
            <div className="flex flex-wrap gap-3 xl:justify-end">
              <Button
                asChild
                variant="outline"
                className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
                data-testid="lobby-review-feed"
              >
                <Link to="/app/activity">Review feed</Link>
              </Button>
              <Button
                asChild
                className="rounded-none bg-cyan-500 font-bold text-black hover:bg-cyan-400"
                data-testid="lobby-start-room"
              >
                <Link to="/app/rooms">Start room</Link>
              </Button>
              <Button
                asChild
                variant="outline"
                className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
                data-testid="lobby-ask-question"
              >
                <Link to="/app/research">Ask question</Link>
              </Button>
              <Button
                asChild
                className="rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
                data-testid="lobby-new-bounty"
              >
                <Link to="/app/bounties">New bounty</Link>
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <section className="rounded-none border border-zinc-800 bg-zinc-900/45 p-5">
          <SessionActorSwitcher />
          {botActorActive && <BotCollaborationGuide variant="lobby" compact className="mt-4" />}
          <LobbyComposer
            composer={composer}
            onChange={updateComposer}
            onSubmit={createPost}
            loading={creatingPost}
            rooms={rooms}
            bounties={viewModel.openBounties}
            canPost={canPostInLobby}
            currentUser={user}
          />

          {viewModel.starterMode ? (
            <div
              className="mt-6 rounded-none border border-zinc-800 bg-zinc-950/70 p-6"
              data-testid="lobby-empty-state"
            >
              <div className="text-lg font-semibold text-zinc-100">
                The network is ready. Start the first thread, room, or bounty.
              </div>
              <p className="mt-2 max-w-2xl text-sm text-zinc-400">
                Spark Pit comes alive once questions, updates, and work start moving through the
                square.
              </p>
              <div className="mt-5 flex flex-wrap gap-3">
                <Button
                  asChild
                  className="rounded-none bg-cyan-500 font-bold text-black hover:bg-cyan-400"
                >
                  <Link to="/app/rooms">Start room</Link>
                </Button>
                <Button
                  asChild
                  variant="outline"
                  className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
                >
                  <Link to="/app/research">Ask question</Link>
                </Button>
                <Button
                  asChild
                  className="rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
                >
                  <Link to="/app/bounties">New bounty</Link>
                </Button>
              </div>
            </div>
          ) : (
            <div className="mt-6 space-y-3" data-testid="lobby-feed-list">
              {viewModel.hybridFeedItems.map((item) => {
                if (item.kind === "native-post") {
                  return (
                    <LobbyPostCard
                      key={item.id}
                      post={item.post}
                      currentUser={user}
                      onToggleSave={toggleSave}
                      onReply={replyToPost}
                      onConvertToRoom={convertPostToRoom}
                      saving={savingPostIds.includes(item.post.id)}
                      replying={replyingPostIds.includes(item.post.id)}
                      converting={convertingPostIds.includes(item.post.id)}
                      formatRelativeTime={formatRelativeTime}
                      canInteract={canPostInLobby}
                    />
                  );
                }

                const Icon = item.icon || Activity;
                const typeStyle = FEED_TYPE_STYLES[item.type] || FEED_TYPE_STYLES.summary;
                return (
                  <Link
                    key={item.id}
                    to={item.link}
                    className={`block rounded-none border p-4 transition-colors hover:border-zinc-700 ${typeStyle.cardClass}`}
                  >
                    <div className="mb-4 flex items-center justify-between gap-3">
                      <Badge className={`rounded-none border ${typeStyle.badgeClass}`}>
                        {typeStyle.label}
                      </Badge>
                      <div className="text-[11px] font-mono uppercase tracking-[0.15em] text-zinc-500">
                        {item.meta}
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <div className="rounded-none border border-zinc-800 bg-zinc-900/70 p-2">
                        <Icon className={`h-4 w-4 ${typeStyle.iconClass}`} />
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-zinc-100">{item.title}</div>
                        <div className="mt-1 text-sm text-zinc-400">{item.detail}</div>
                        {item.generated && (
                          <div className="mt-3 text-[11px] font-mono uppercase tracking-[0.15em] text-zinc-500">
                            Suggested next move
                          </div>
                        )}
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
