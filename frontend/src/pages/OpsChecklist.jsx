import React, { useEffect, useState } from "react";
import { useLayout } from "@/components/layout/AppShell";
import { QuickPanel } from "@/components/layout/QuickPanel";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { AdminStatusCards } from "@/components/admin/AdminStatusCards";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { StripeSettingsPanel } from "@/components/admin/StripeSettingsPanel";

const statusLabel = (value) => (value ? "OK" : "Attention needed");

export default function OpsChecklist() {
  const { setSecondaryPanel } = useLayout();
  const { user } = useAuth();
  const [ops, setOps] = useState(null);
  const [error, setError] = useState("");
  const [rateLimitEvents, setRateLimitEvents] = useState([]);
  const [rateLimitAvailable, setRateLimitAvailable] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [alertsError, setAlertsError] = useState("");

  const loadOps = async () => {
    try {
      setError("");
      const response = await api.get("/admin/ops");
      setOps(response.data);
    } catch (err) {
      setError("Admin access required or ops endpoint unavailable.");
    }
  };

  const loadRateLimits = async () => {
    try {
      const response = await api.get("/admin/rate-limits");
      setRateLimitEvents(response.data.events || []);
      setRateLimitAvailable(!!response.data.available);
    } catch (err) {
      setRateLimitEvents([]);
      setRateLimitAvailable(false);
    }
  };

  const loadAlerts = async () => {
    try {
      setAlertsError("");
      const response = await api.get("/admin/alerts");
      setAlerts(response.data.items || []);
    } catch (err) {
      setAlerts([]);
      setAlertsError("Unable to load alerts.");
    }
  };

  useEffect(() => {
    setSecondaryPanel(<QuickPanel />);
  }, [setSecondaryPanel]);

  useEffect(() => {
    loadOps();
    loadRateLimits();
    loadAlerts();
  }, []);

  const checks = [
    {
      id: "stripe",
      label: "Stripe configured",
      detail: statusLabel(ops?.stripe_configured),
      ok: !!ops?.stripe_configured,
    },
    {
      id: "webhook",
      label: "Stripe webhook",
      detail: ops?.stripe_webhook_last_received
        ? `Last received ${new Date(ops.stripe_webhook_last_received).toLocaleString()}`
        : "Awaiting first webhook",
      ok: !!ops?.stripe_webhook_last_received,
    },
    {
      id: "membership-price",
      label: "Membership price ID",
      detail: statusLabel(ops?.stripe_membership_price_configured),
      ok: !!ops?.stripe_membership_price_configured,
    },
    {
      id: "bot-invite-price",
      label: "Bot invite price ID",
      detail: statusLabel(ops?.stripe_bot_invite_price_configured),
      ok: !!ops?.stripe_bot_invite_price_configured,
    },
    {
      id: "redis",
      label: "Redis connectivity",
      detail: statusLabel(ops?.redis_connected),
      ok: !!ops?.redis_connected,
    },
    {
      id: "worker",
      label: "Worker heartbeat",
      detail: ops?.worker_healthy ? "Healthy in the last minute" : "Stale or missing heartbeat",
      ok: !!ops?.worker_healthy,
    },
  ];

  return (
    <div className="flex h-full flex-col" data-testid="ops-page">
      <div className="flex-1 overflow-y-auto p-6">
        <AdminPageHeader
          eyebrow="Ops Console"
          title="System readiness and launch health"
          titleTestId="ops-title"
          description="Track platform dependencies, worker health, and abuse telemetry before you push work live."
          adminNote={`Admin only · ${user?.email}`}
          meta="Launch readiness • platform health • incident telemetry"
          actions={
            <>
              <Button
                onClick={loadRateLimits}
                className="rounded-none border border-zinc-700 text-zinc-300 hover:bg-zinc-900"
                variant="outline"
              >
                Refresh telemetry
              </Button>
              <Button
                onClick={() => {
                  loadOps();
                  loadAlerts();
                }}
                className="rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
                variant="outline"
                data-testid="ops-refresh"
              >
                Refresh checks
              </Button>
            </>
          }
        />

        {error && (
          <div className="mt-4 rounded-none border border-pink-500/40 bg-pink-500/10 p-3 text-xs text-pink-300" data-testid="ops-error">
            {error}
          </div>
        )}

        <div className="mt-6 grid gap-4 xl:grid-cols-[1.3fr_0.7fr]">
          <AdminStatusCards items={checks} testId="ops-list" />

          <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5">
            <div className="text-xs font-mono uppercase tracking-[0.24em] text-zinc-500">Console scope</div>
            <div className="mt-3 space-y-3 text-sm text-zinc-300">
              <div>Use Ops for launch readiness, service health, and platform-level abuse signals.</div>
              <div className="rounded-none border border-zinc-800 bg-zinc-950/60 p-3 text-xs text-zinc-400">
                Moderation review now lives in its own console so trust and safety triage does not compete with system checks.
              </div>
            </div>
          </div>
        </div>

        <StripeSettingsPanel
          onUpdated={() => {
            loadOps();
          }}
        />

        <div className="mt-10 border-t border-zinc-800 pt-6" data-testid="ops-rate-limits">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">Abuse</div>
              <div className="text-lg font-semibold">Rate limit telemetry</div>
              <div className="mt-1 text-sm text-zinc-400">
                Review throttled actors and endpoints without leaving the ops surface.
              </div>
            </div>
            <Button
              onClick={loadRateLimits}
              className="rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
              variant="outline"
            >
              Refresh
            </Button>
          </div>
          {!rateLimitAvailable && (
            <div className="mt-3 text-xs text-zinc-500">
              Rate limit telemetry unavailable. Confirm Redis connectivity first.
            </div>
          )}
          {rateLimitAvailable && rateLimitEvents.length === 0 && (
            <div className="mt-3 rounded-none border border-zinc-800 bg-zinc-900/40 p-3 text-xs text-zinc-500">
              No recent throttling events.
            </div>
          )}
          {rateLimitEvents.length > 0 && (
            <div className="mt-4 space-y-3">
              {rateLimitEvents.map((event, index) => (
                <div key={`${event.actor_id}-${index}`} className="rounded-none border border-zinc-800 bg-zinc-900/60 p-3">
                  <div className="text-sm font-semibold">
                    {event.actor_type}:{event.actor_id}
                  </div>
                  <div className="mt-1 text-xs text-zinc-400">
                    {event.endpoint} · {event.detail}
                  </div>
                  <div className="mt-1 text-xs text-zinc-500">
                    {event.created_at ? new Date(event.created_at).toLocaleString() : ""}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="mt-10 border-t border-zinc-800 pt-6" data-testid="ops-alerts">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">Alerts</div>
              <div className="text-lg font-semibold">Security events</div>
              <div className="mt-1 text-sm text-zinc-400">
                Keep an eye on platform-level anomalies and admin-visible security signals.
              </div>
            </div>
            <Button
              onClick={loadAlerts}
              className="rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
              variant="outline"
            >
              Refresh
            </Button>
          </div>
          {alertsError && (
            <div className="mt-3 text-xs text-pink-300">
              {alertsError}
            </div>
          )}
          {!alertsError && alerts.length === 0 && (
            <div className="mt-3 rounded-none border border-zinc-800 bg-zinc-900/40 p-3 text-xs text-zinc-500">
              No alerts in the current window.
            </div>
          )}
          {alerts.length > 0 && (
            <div className="mt-4 space-y-3">
              {alerts.map((alert) => (
                <div key={alert.id} className="rounded-none border border-zinc-800 bg-zinc-900/60 p-3">
                  <div className="text-sm font-semibold">{alert.event_type}</div>
                  <div className="mt-1 text-xs text-zinc-400">
                    {alert.payload ? JSON.stringify(alert.payload) : ""}
                  </div>
                  <div className="mt-1 text-xs text-zinc-500">
                    {alert.created_at ? new Date(alert.created_at).toLocaleString() : ""}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
