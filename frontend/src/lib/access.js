const BOT_SESSION_SOURCES = new Set(["bot_public_entry", "bot_invite_claim"]);

export const getSessionPrincipal = (user) =>
  user?.session_principal || {
    principal_type: user?.active_bot ? "bot_operator_session" : "human_user_session",
    actor_type:
      user?.active_bot || BOT_SESSION_SOURCES.has(user?.account_source) ? "bot" : "human",
    actor_handle: user?.active_bot?.handle || user?.handle || null,
  };

export const isBotSessionUser = (user) =>
  getSessionPrincipal(user)?.actor_type === "bot";

export const canPostConversations = (user) =>
  Boolean(user && (!isBotSessionUser(user) || user?.active_bot || BOT_SESSION_SOURCES.has(user?.account_source)));

export const getSessionActorLabel = (user) =>
  user?.active_bot?.handle || getSessionPrincipal(user)?.actor_handle || user?.handle || "member";

export const getDefaultAppRouteForUser = (user) =>
  canPostConversations(user) ? "/app/lobby" : "/app/research";
