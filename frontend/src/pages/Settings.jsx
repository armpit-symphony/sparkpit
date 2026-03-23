import React, { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useLayout } from "@/components/layout/AppShell";
import { QuickPanel } from "@/components/layout/QuickPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "@/components/ui/sonner";

export default function Settings() {
  const { user, refresh, logout } = useAuth();
  const { setSecondaryPanel } = useLayout();
  const [handle, setHandle] = useState(user?.handle || "");
  const [inviteCode, setInviteCode] = useState(null);
  const [maxUses, setMaxUses] = useState(1);
  const [auditEvents, setAuditEvents] = useState([]);
  const isAdmin = user?.role === "admin";

  useEffect(() => {
    setSecondaryPanel(<QuickPanel />);
  }, [setSecondaryPanel]);

  useEffect(() => {
    setHandle(user?.handle || "");
  }, [user]);

  const updateProfile = async () => {
    try {
      await api.patch("/me", { handle });
      await refresh();
      toast.success("Profile updated.");
    } catch (error) {
      toast.error("Unable to update profile.");
    }
  };

  const generateInvite = async () => {
    try {
      const response = await api.post("/admin/invite-codes", {
        max_uses: Number(maxUses),
      });
      setInviteCode(response.data.invite_code.code);
      toast.success("Invite generated.");
    } catch (error) {
      toast.error("Unable to generate invite.");
    }
  };

  const loadAudit = async () => {
    try {
      const response = await api.get("/admin/audit");
      setAuditEvents(response.data.items || []);
    } catch (error) {
      toast.error("Unable to load audit feed.");
    }
  };

  useEffect(() => {
    if (isAdmin) {
      loadAudit();
    }
  }, [isAdmin]);

  return (
    <div className="flex h-full flex-col" data-testid="settings-page">
      <div className="border-b border-zinc-800 bg-zinc-950/70 px-6 py-4">
        <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">Settings</div>
        <div className="text-lg font-semibold" data-testid="settings-title">
          Profile control
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
          <div className="space-y-6">
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5" data-testid="profile-card">
              <div className="text-sm font-semibold">Profile</div>
              <div className="mt-4 space-y-3">
                <div className="text-xs text-zinc-500" data-testid="profile-email">
                  Email: {user?.email}
                </div>
                <div className="text-xs text-zinc-500" data-testid="profile-membership">
                  Membership: {user?.membership_status}
                </div>
                <Input
                  value={handle}
                  onChange={(event) => setHandle(event.target.value)}
                  className="rounded-none border-zinc-800 bg-zinc-950 font-mono"
                  data-testid="profile-handle-input"
                />
                <Button
                  onClick={updateProfile}
                  className="rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
                  data-testid="profile-update-submit"
                >
                  Update handle
                </Button>
              </div>
            </div>

            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5" data-testid="logout-card">
              <div className="text-sm font-semibold">Session</div>
              <Button
                onClick={logout}
                className="mt-4 w-full rounded-none border border-pink-500 text-pink-300 hover:bg-pink-500/10"
                variant="outline"
                data-testid="logout-button"
              >
                Sign out
              </Button>
            </div>
          </div>

          <div className="space-y-6" id="audit">
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5" data-testid="invite-card">
              <div className="text-sm font-semibold">Admin: Invite codes</div>
              <div className="mt-3 text-xs text-zinc-500">
                Only admins can generate codes.
              </div>
              <div className="mt-4 flex gap-2">
                <Input
                  value={maxUses}
                  onChange={(event) => setMaxUses(event.target.value)}
                  className="w-24 rounded-none border-zinc-800 bg-zinc-950 font-mono"
                  disabled={!isAdmin}
                  data-testid="invite-max-uses-input"
                />
                <Button
                  onClick={generateInvite}
                  className="rounded-none bg-cyan-500 text-black hover:bg-cyan-400"
                  disabled={!isAdmin}
                  data-testid="invite-generate-button"
                >
                  Generate
                </Button>
              </div>
              {inviteCode && (
                <div
                  className="mt-3 rounded-none border border-amber-500/30 bg-amber-500/10 p-2 font-mono text-xs text-amber-300"
                  data-testid="invite-code-display"
                >
                  {inviteCode}
                </div>
              )}
            </div>

            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5" data-testid="audit-card">
              <div className="text-sm font-semibold">Audit feed</div>
              {!isAdmin ? (
                <div className="mt-3 text-xs text-zinc-500" data-testid="audit-restricted">
                  Admin role required.
                </div>
              ) : (
                <div className="mt-4 space-y-3" data-testid="audit-list">
                  {auditEvents.map((event) => (
                    <div
                      key={event.id}
                      className="rounded-none border border-zinc-800 bg-zinc-950/60 p-3"
                      data-testid={`audit-event-${event.id}`}
                    >
                      <div className="text-xs text-zinc-500">{event.event_type}</div>
                      <div className="mt-1 text-xs text-zinc-400">
                        {new Date(event.created_at).toLocaleString()}
                      </div>
                    </div>
                  ))}
                  {auditEvents.length === 0 && (
                    <div className="text-xs text-zinc-500" data-testid="audit-empty">
                      No audit events yet.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
