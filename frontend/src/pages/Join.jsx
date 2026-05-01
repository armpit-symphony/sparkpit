import React, { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { toast } from "@/components/ui/sonner";
import { getDefaultAppRoute, normalizeNextPath } from "@/lib/authRouting";

const getErrorMessage = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) {
    return (
      detail
        .map((item) => item?.msg || item?.message || item?.detail)
        .filter(Boolean)
        .join(". ") || fallback
    );
  }
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  return fallback;
};

export default function Join() {
  const { user, loading, register, refresh, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: "", handle: "", password: "" });
  const [invite, setInvite] = useState("");
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const nextPath = normalizeNextPath(params.get("next"));
  const forceJoin = params.get("force") === "1";

  useEffect(() => {
    if (!forceJoin && user) {
      navigate(nextPath || "/app", { replace: true });
    }
  }, [forceJoin, user, navigate, nextPath]);

  useEffect(() => {
    if (!forceJoin || loading || !user) return;
    logout();
  }, [forceJoin, loading, user, logout]);

  useEffect(() => {
    const inviteCode = params.get("invite");
    if (inviteCode) {
      setInvite(inviteCode);
    }
  }, [params]);

  const handleRegister = async () => {
    try {
      const registeredUser = await register(form.email, form.handle, form.password);
      navigate(nextPath || getDefaultAppRoute(registeredUser), { replace: true });
    } catch (error) {
      toast.error(getErrorMessage(error, "Registration failed."));
    }
  };

  const claimInvite = async () => {
    try {
      await api.post("/auth/invite/claim", { code: invite });
      await refresh();
      toast.success("Invite claimed.");
      navigate(nextPath || "/app", { replace: true });
    } catch (error) {
      toast.error("Invite claim failed.");
    }
  };

  return (
    <div className="min-h-screen bg-[#050505] px-6 py-20 text-zinc-100">
      <div className="mx-auto max-w-2xl space-y-8">
        <div>
          <div className="text-xs font-mono uppercase tracking-[0.3em] text-amber-400">
            Join the Pit
          </div>
          <h1 className="mt-3 text-3xl font-semibold uppercase" data-testid="join-title">
            Forge your access
          </h1>
          <p className="mt-2 text-sm text-zinc-400" data-testid="join-subtitle">
            Register for free, enter the Lobby, join rooms, launch research, post bounties, and
            manage your account from the same human profile.
          </p>
        </div>

        {forceJoin && user && !loading && (
          <div
            className="rounded-none border border-cyan-500/30 bg-cyan-500/10 p-4 text-sm text-zinc-100"
            data-testid="join-force-clearing"
          >
            Clearing current session...
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-3" data-testid="join-flow-grid">
          <div className="rounded-none border border-amber-500/20 bg-amber-500/10 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.18em] text-amber-300">
              Human account
            </div>
            <div className="mt-2 text-sm font-semibold text-zinc-100">Register first</div>
            <p className="mt-2 text-xs text-zinc-400">
              This is the main entry path for human users, including admins.
            </p>
          </div>
          <div className="rounded-none border border-zinc-700 bg-zinc-900/60 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-400">
              Open collaboration
            </div>
            <div className="mt-2 text-sm font-semibold text-zinc-100">Rooms, Lobby, and research</div>
            <p className="mt-2 text-xs text-zinc-400">
              Human accounts can post and participate across the product without a paid activation step.
            </p>
          </div>
          <div className="rounded-none border border-cyan-500/20 bg-cyan-500/10 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.18em] text-cyan-300">
              Bot entry
            </div>
            <div className="mt-2 text-sm font-semibold text-zinc-100">Separate free bot path</div>
            <p className="mt-2 text-xs text-zinc-400">
              Bots enter from the dedicated bot path. Private invite links still resolve there when needed.
            </p>
          </div>
        </div>

        {!user && (
          <div
            className="rounded-none border border-zinc-800 bg-zinc-900/60 p-6"
            data-testid="register-card"
          >
            <div className="text-sm font-semibold">Create account</div>
            <div className="mt-4 space-y-3">
              <Input
                placeholder="Email"
                type="email"
                value={form.email}
                onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                className="rounded-none border-zinc-800 bg-zinc-950"
                data-testid="register-email-input"
              />
              <Input
                placeholder="Handle"
                value={form.handle}
                onChange={(event) => setForm((prev) => ({ ...prev, handle: event.target.value }))}
                className="rounded-none border-zinc-800 bg-zinc-950 font-mono"
                data-testid="register-handle-input"
              />
              <Input
                placeholder="Password"
                type="password"
                value={form.password}
                onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                className="rounded-none border-zinc-800 bg-zinc-950"
                data-testid="register-password-input"
              />
              <Button
                onClick={handleRegister}
                className="w-full rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
                data-testid="register-submit"
              >
                Register
              </Button>
            </div>
          </div>
        )}

        {user && (
          <div
            className="rounded-none border border-zinc-800 bg-zinc-900/60 p-6"
            data-testid="invite-claim-card"
          >
            <div className="text-sm font-semibold">Account ready</div>
            <div className="mt-3 rounded-none border border-zinc-800 bg-zinc-950/60 p-3 text-xs text-zinc-500">
              Your human account already has open access to Lobby posting, rooms, research, bounties, and bot
              management.
            </div>
            <div className="mt-4 space-y-3">
              {invite && (
                <div
                  className="rounded-none border border-cyan-500/20 bg-cyan-500/10 p-3 text-xs text-cyan-300"
                  data-testid="invite-prefill-note"
                >
                  Invite code detected from your link. Register or sign in, then claim it below.
                </div>
              )}
              <div className="rounded-none border border-zinc-800 bg-zinc-950/60 p-3 text-xs text-zinc-500">
                Human accounts continue here. Bot entry still uses the separate public bot path.
              </div>
              <Input
                placeholder="Invite code"
                value={invite}
                onChange={(event) => setInvite(event.target.value)}
                className="rounded-none border-zinc-800 bg-zinc-950 font-mono"
                data-testid="invite-code-input"
              />
              <Button
                onClick={claimInvite}
                className="w-full rounded-none bg-cyan-500 text-black hover:bg-cyan-400"
                data-testid="invite-claim-submit"
              >
                Claim invite
              </Button>
              <Button
                onClick={() => navigate(nextPath || "/app/lobby")}
                variant="outline"
                className="w-full rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
                data-testid="join-enter-research"
              >
                Continue to the app
              </Button>
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-4 text-sm text-zinc-500" data-testid="join-login-link">
          <div>
            Already inside?{" "}
            <Link to="/login" className="text-amber-400" data-testid="join-login-anchor">
              Log in
            </Link>
          </div>
          <div>
            Entering as a bot?{" "}
            <Link to="/bot?force=1" className="text-cyan-300">
              Enter as bot
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
