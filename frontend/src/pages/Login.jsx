import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { toast } from "@/components/ui/sonner";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });

  useEffect(() => {
    if (user?.membership_status === "active") {
      navigate("/app");
    }
  }, [user, navigate]);

  const handleLogin = async () => {
    try {
      const loggedIn = await login(form.email, form.password);
      if (loggedIn.membership_status === "active") {
        navigate("/app");
      } else {
        navigate("/join");
      }
    } catch (error) {
      toast.error("Login failed.");
    }
  };

  return (
    <div className="min-h-screen bg-[#050505] px-6 py-20 text-zinc-100">
      <div className="mx-auto max-w-xl space-y-6">
        <div>
          <div className="text-xs font-mono uppercase tracking-[0.3em] text-amber-400">
            Access Portal
          </div>
          <h1 className="mt-3 text-3xl font-semibold uppercase" data-testid="login-title">
            Enter the Spark Pit
          </h1>
        </div>
        <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-6">
          <div className="space-y-3">
            <Input
              placeholder="Email"
              type="email"
              value={form.email}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, email: event.target.value }))
              }
              className="rounded-none border-zinc-800 bg-zinc-950"
              data-testid="login-email-input"
            />
            <Input
              placeholder="Password"
              type="password"
              value={form.password}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, password: event.target.value }))
              }
              className="rounded-none border-zinc-800 bg-zinc-950"
              data-testid="login-password-input"
            />
            <Button
              onClick={handleLogin}
              className="w-full rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
              data-testid="login-submit"
            >
              Enter
            </Button>
          </div>
        </div>
        <div className="text-sm text-zinc-500" data-testid="login-join-link">
          Need access?{" "}
          <Link
            to="/join"
            className="text-amber-400"
            data-testid="login-join-anchor"
          >
            Request invite
          </Link>
        </div>
      </div>
    </div>
  );
}
