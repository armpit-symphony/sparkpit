import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { api, setCsrfToken } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const csrfReady = useRef(false);

  const ensureCsrf = async () => {
    if (csrfReady.current) return;
    const response = await api.get("/auth/csrf");
    setCsrfToken(response.data.csrf_token);
    csrfReady.current = true;
  };

  const bootstrap = async () => {
    await ensureCsrf();
    try {
      const response = await api.get("/me");
      setUser(response.data.user);
    } catch (error) {
      setUser(null);
    }
    setLoading(false);
  };

  useEffect(() => {
    bootstrap();
  }, []);

  const login = async (email, password) => {
    await ensureCsrf();
    const response = await api.post("/auth/login", { email, password });
    setUser(response.data.user);
    toast.success("Welcome back to the Pit.");
    return response.data.user;
  };

  const register = async (email, handle, password) => {
    await ensureCsrf();
    const response = await api.post("/auth/register", { email, handle, password });
    setUser(response.data.user);
    toast.success("Account forged. Activate with your invite code.");
    return response.data.user;
  };

  const refresh = async () => {
    const response = await api.get("/me");
    setUser(response.data.user);
    return response.data.user;
  };

  const logout = () => {
    api.post("/auth/logout").catch(() => {});
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, logout, refresh }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
