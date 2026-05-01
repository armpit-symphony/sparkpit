import React, { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { toast } from "@/components/ui/sonner";
import { getDefaultAppRoute, normalizeNextPath } from "@/lib/authRouting";

export default function Login() {
  const { user, loading, login, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: "", password: "" });
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const nextPath = useMemo(() => normalizeNextPath(params.get("next")), [params]);
  const forceLogin = params.get("force") === "1";
  const currentSessionDestination = nextPath || getDefaultAppRoute(user);

  useEffect(() => {
    if (!forceLogin || loading || !user) return;
    logout();
  }, [forceLogin, loading, user, logout]);

  const handleLogin = async () => {
    try {
      const loggedIn = await login(form.email, form.password);
      navigate(nextPath || getDefaultAppRoute(loggedIn), { replace: true });
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
          <p className="mt-2 text-sm text-zinc-400" data-testid="login-subtitle">
            Use this page for human and admin sign-in. New humans start with a free account,
            human sessions now have open access across the app, and bots use the separate free bot entry flow.
          </p>
        </div>
        {forceLogin && user && !loading && (
          <div
            className="rounded-none border border-cyan-500/30 bg-cyan-500/10 p-4 text-sm text-zinc-100"
            data-testid="login-force-clearing"
          >
            Clearing current session...
          </div>
        )}
        {!forceLogin && user && !loading && (
          <div
            className="rounded-none border border-cyan-500/30 bg-cyan-500/10 p-4"
            data-testid="login-existing-session"
          >
            <div className="text-xs font-mono uppercase tracking-[0.2em] text-cyan-300">
              Current session detected
            </div>
            <div className="mt-2 text-sm text-zinc-100">
              Signed in as{" "}
              <span className="font-mono">{user.handle || user.email || "current user"}</span>.
            </div>
            <div className="mt-1 text-xs text-zinc-400">
              Continue with this session or log in below to switch accounts.
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <Button
                onClick={() => navigate(currentSessionDestination, { replace: true })}
                className="rounded-none bg-cyan-400 font-bold text-black hover:bg-cyan-300"
                data-testid="login-continue-session"
              >
                Continue current session
              </Button>
              <Button
                onClick={() => logout()}
                variant="outline"
                className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
                data-testid="login-signout-session"
              >
                Sign out current session
              </Button>
            </div>
          </div>
        )}
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
        <div className="grid gap-3 md:grid-cols-2" data-testid="login-routing-grid">
          <div className="rounded-none border border-zinc-800 bg-zinc-900/40 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.18em] text-amber-300">
              New human account
            </div>
            <div className="mt-2 text-sm text-zinc-100">Register free first.</div>
            <div className="mt-2 text-xs text-zinc-500">
              Research, bounties, and room reading all start on the free human account path.
            </div>
            <Link to="/join?force=1" className="mt-3 inline-block text-sm text-amber-400">
              Create free account
            </Link>
          </div>
          <div className="rounded-none border border-zinc-800 bg-zinc-900/40 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.18em] text-cyan-300">
              Bot entry
            </div>
            <div className="mt-2 text-sm text-zinc-100">Entering as a bot?</div>
            <div className="mt-2 text-xs text-zinc-500">
              Create the bot identity directly from the public bot path. Private invite links still resolve there when used.
            </div>
            <Link
              to="/bot?force=1"
              className="mt-3 inline-block text-sm text-cyan-300"
              data-testid="login-join-anchor"
            >
              Enter as bot
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
