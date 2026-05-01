import React, { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useLayout } from "@/components/layout/AppShell";
import { QuickPanel } from "@/components/layout/QuickPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "@/components/ui/sonner";
import { AdminStatusCards } from "@/components/admin/AdminStatusCards";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { InviteManagementPanel } from "@/components/admin/InviteManagementPanel";

export default function Settings() {
  const { user, refresh, logout } = useAuth();
  const { setSecondaryPanel } = useLayout();
  const [handle, setHandle] = useState(user?.handle || "");
  const [auditEvents, setAuditEvents] = useState([]);
  const isAdmin = user?.role === "admin";
  const adminSummaryItems = [
    {
      id: "role",
      label: "Admin access",
      detail: isAdmin ? "Enabled for invites, moderation, ops, and audit." : "Standard member access only.",
      ok: isAdmin,
      eyebrow: "Role",
    },
    {
      id: "invites",
      label: "Invite console",
      detail: isAdmin ? "Inventory, generation, and copy controls are available." : "Invite management restricted to admins.",
      ok: isAdmin,
      eyebrow: "Access",
    },
    {
      id: "audit",
      label: "Audit visibility",
      detail: isAdmin ? `${auditEvents.length} recent admin-visible events loaded.` : "Audit feed restricted to admins.",
      ok: isAdmin && auditEvents.length > 0,
      eyebrow: "Audit",
    },
  ];

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
      <div className="flex-1 overflow-y-auto p-6">
        <AdminPageHeader
          eyebrow="Settings"
          title="Profile control"
          titleTestId="settings-title"
          description="Manage account settings and, when permitted, the admin surfaces tied to invites and audit visibility."
          adminNote={user?.email}
          meta="Profile edits • session control • admin access surfaces"
        />

        <div className="mt-6 grid gap-6 lg:grid-cols-[1.2fr_1fr]">
          <div className="space-y-6">
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5" data-testid="profile-card">
              <div className="text-sm font-semibold">Profile</div>
              <div className="mt-4 space-y-3">
                <div className="text-xs text-zinc-500" data-testid="profile-email">
                  Email: {user?.email}
                </div>
                <div className="text-xs text-zinc-500" data-testid="profile-membership">
                  Access: open
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
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5">
              <div className="text-sm font-semibold">Admin surface</div>
              <div className="mt-2 text-xs text-zinc-500">
                Invite controls and audit visibility share the same admin access boundary.
              </div>
              <div className="mt-4">
                <AdminStatusCards items={adminSummaryItems} testId="settings-admin-summary" />
              </div>
            </div>

            <InviteManagementPanel isAdmin={isAdmin} />

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
