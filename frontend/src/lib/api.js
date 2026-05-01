import axios from "axios";

const resolveBackendUrl = () => {
  const configured = process.env.REACT_APP_BACKEND_URL;
  if (configured) {
    return configured.replace(/\/$/, "");
  }
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin.replace(/\/$/, "");
  }
  return "";
};

const BACKEND_URL = resolveBackendUrl();
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

let csrfRefreshPromise = null;

export const setAuthToken = (token) => {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common.Authorization;
  }
};

export const setCsrfToken = (token) => {
  if (token) {
    api.defaults.headers.common["X-CSRF-Token"] = token;
  } else {
    delete api.defaults.headers.common["X-CSRF-Token"];
  }
};

export const refreshCsrfToken = async () => {
  if (!csrfRefreshPromise) {
    csrfRefreshPromise = api
      .get("/auth/csrf")
      .then((response) => {
        setCsrfToken(response.data.csrf_token);
        return response.data.csrf_token;
      })
      .finally(() => {
        csrfRefreshPromise = null;
      });
  }
  return csrfRefreshPromise;
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const detail = error?.response?.data?.detail;
    const config = error?.config;
    const requestUrl = config?.url || "";
    if (
      error?.response?.status !== 403 ||
      detail !== "CSRF token invalid" ||
      !config ||
      config.__csrfRetried ||
      requestUrl.endsWith("/auth/csrf")
    ) {
      return Promise.reject(error);
    }

    config.__csrfRetried = true;
    await refreshCsrfToken();
    return api.request(config);
  },
);

export const getWsUrl = (channelId) => {
  if (!BACKEND_URL) return "";
  const wsBase = BACKEND_URL.replace("https://", "wss://").replace(
    "http://",
    "ws://",
  );
  return `${wsBase}/api/ws?channelId=${channelId}`;
};
