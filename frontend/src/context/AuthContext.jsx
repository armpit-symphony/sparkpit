import React, { createContext, useContext, useEffect, useState } from "react";
import { api, setAuthToken } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const bootstrap = async () => {
    const token = localStorage.getItem("spark_token");
    if (token) {
      setAuthToken(token);
      try {
        const response = await api.get("/me");
        setUser(response.data.user);
      } catch (error) {
        localStorage.removeItem("spark_token");
        setAuthToken(null);
      }
    }
    setLoading(false);
  };

  useEffect(() => {
    bootstrap();
  }, []);

  const login = async (email, password) => {
    const response = await api.post("/auth/login", { email, password });
    localStorage.setItem("spark_token", response.data.token);
    setAuthToken(response.data.token);
    setUser(response.data.user);
    toast.success("Welcome back to the Pit.");
    return response.data.user;
  };

  const register = async (email, handle, password) => {
    const response = await api.post("/auth/register", { email, handle, password });
    localStorage.setItem("spark_token", response.data.token);
    setAuthToken(response.data.token);
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
    localStorage.removeItem("spark_token");
    setAuthToken(null);
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
