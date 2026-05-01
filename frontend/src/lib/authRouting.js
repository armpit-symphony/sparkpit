import { getDefaultAppRouteForUser } from "@/lib/access";

export const getDefaultAppRoute = (user) => getDefaultAppRouteForUser(user);

export const normalizeNextPath = (value) => {
  if (!value || typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) {
    return null;
  }

  try {
    const baseOrigin =
      typeof window !== "undefined" && window.location?.origin
        ? window.location.origin
        : "https://thesparkpit.com";
    const url = new URL(trimmed, baseOrigin);
    if (url.origin !== baseOrigin) {
      return null;
    }
    return `${url.pathname}${url.search}${url.hash}`;
  } catch (error) {
    return null;
  }
};

export const buildLoginPath = (nextPath) => {
  const safeNextPath = normalizeNextPath(nextPath);
  if (!safeNextPath) {
    return "/login";
  }
  return `/login?next=${encodeURIComponent(safeNextPath)}`;
};

export const buildJoinPath = (nextPath) => {
  const safeNextPath = normalizeNextPath(nextPath);
  if (!safeNextPath) {
    return "/join";
  }
  return `/join?next=${encodeURIComponent(safeNextPath)}`;
};

export const getCurrentPathWithSearch = (location) => {
  if (!location) return "/";
  return `${location.pathname || "/"}${location.search || ""}${location.hash || ""}`;
};
