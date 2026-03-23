import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
});

export const setAuthToken = (token) => {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common.Authorization;
  }
};

export const getWsUrl = (channelId) => {
  if (!BACKEND_URL) return "";
  const wsBase = BACKEND_URL.replace("https://", "wss://").replace(
    "http://",
    "ws://",
  );
  return `${wsBase}/api/ws?channelId=${channelId}`;
};
