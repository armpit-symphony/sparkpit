import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { api, refreshCsrfToken, setCsrfToken } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const csrfReady = useRef(false);

  const resetCsrf = () => {
    csrfReady.current = false;
    setCsrfToken(null);
  };

  const ensureCsrf = async (force = false) => {
    if (csrfReady.current && !force) return;
    const response = await api.get("/auth/csrf");
    setCsrfToken(response.data.csrf_token);
    csrfReady.current = true;
  };

  const withFreshCsrf = async (requestFn) => {
    await ensureCsrf();
    try {
      return await requestFn();
    } catch (error) {
      if (error?.response?.status !== 403) {
        throw error;
      }
      resetCsrf();
      await ensureCsrf(true);
      return requestFn();
    }
  };

  const alignCsrf = async () => {
    try {
      await refreshCsrfToken();
      csrfReady.current = true;
    } catch (error) {
      resetCsrf();
    }
  };

  useEffect(() => {
    let active = true;

    const bootstrap = async () => {
      try {
        try {
          const response = await api.get("/auth/csrf");
          if (active) {
            setCsrfToken(response.data.csrf_token);
            csrfReady.current = true;
          }
        } catch (error) {
          csrfReady.current = false;
          setCsrfToken(null);
        }

        try {
          const response = await api.get("/me");
          if (active) {
            setUser(response.data.user);
          }
        } catch (error) {
          if (active) {
            setUser(null);
          }
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    bootstrap();
    return () => {
      active = false;
    };
  }, []);

  const login = async (email, password) => {
    const response = await withFreshCsrf(() => api.post("/auth/login", { email, password }));
    setUser(response.data.user);
    await alignCsrf();
    toast.success("Welcome back to the Pit.");
    return response.data.user;
  };

  const register = async (email, handle, password) => {
    const response = await withFreshCsrf(() => api.post("/auth/register", { email, handle, password }));
    setUser(response.data.user);
    await alignCsrf();
    toast.success("Account forged. Research and bounties are open; paid access unlocks chat.");
    return response.data.user;
  };

  const refresh = async () => {
    const response = await api.get("/me");
    setUser(response.data.user);
    return response.data.user;
  };

  const syncSession = async () => {
    try {
      await ensureCsrf();
    } catch (error) {
      resetCsrf();
    }

    try {
      const response = await api.get("/me");
      setUser(response.data.user);
      return response.data.user;
    } catch (error) {
      setUser(null);
      return null;
    }
  };

  const logout = () => {
    api.post("/auth/logout").catch(() => {});
    resetCsrf();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, logout, refresh, syncSession }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
