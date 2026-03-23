import React, { useEffect, useState } from "react";
import { useLayout } from "@/components/layout/AppShell";
import { QuickPanel } from "@/components/layout/QuickPanel";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

const statusLabel = (value) => (value ? "OK" : "Not set");

export default function OpsChecklist() {
  const { setSecondaryPanel } = useLayout();
  const { user } = useAuth();
  const [ops, setOps] = useState(null);
  const [error, setError] = useState("");

  const loadOps = async () => {
    try {
      setError("");
      const response = await api.get("/admin/ops");
      setOps(response.data);
    } catch (err) {
      setError("Admin access required or ops endpoint unavailable.");
    }
  };

  useEffect(() => {
    setSecondaryPanel(<QuickPanel />);
  }, [setSecondaryPanel]);

  useEffect(() => {
    loadOps();
  }, []);

  return (
    <div className="flex h-full flex-col" data-testid="ops-page">
      <div className="border-b border-zinc-800 bg-zinc-950/70 px-6 py-4">
        <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">Ops Checklist</div>
        <div className="text-lg font-semibold" data-testid="ops-title">
          Launch readiness
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="flex items-center justify-between">
          <div className="text-xs text-zinc-500" data-testid="ops-admin-note">
            Admin only · {user?.email}
          </div>
          <Button
            onClick={loadOps}
            className="rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
            variant="outline"
            data-testid="ops-refresh"
          >
            Refresh
          </Button>
        </div>

        {error && (
          <div className="mt-4 rounded-none border border-pink-500/40 bg-pink-500/10 p-3 text-xs text-pink-300" data-testid="ops-error">
            {error}
          </div>
        )}

        {ops && (
          <div className="mt-6 space-y-3" data-testid="ops-list">
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4" data-testid="ops-stripe-configured">
              <div className="text-sm font-semibold">Stripe configured</div>
              <div className="mt-2 text-xs text-zinc-400">{statusLabel(ops.stripe_configured)}</div>
            </div>
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4" data-testid="ops-stripe-webhook">
              <div className="text-sm font-semibold">Stripe webhook</div>
              <div className="mt-2 text-xs text-zinc-400">
                {ops.stripe_webhook_last_received
                  ? `Last received: ${new Date(ops.stripe_webhook_last_received).toLocaleString()}`
                  : "Awaiting first webhook"}
              </div>
            </div>
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4" data-testid="ops-redis">
              <div className="text-sm font-semibold">Redis connectivity</div>
              <div className="mt-2 text-xs text-zinc-400">{statusLabel(ops.redis_connected)}</div>
            </div>
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4" data-testid="ops-worker">
              <div className="text-sm font-semibold">Worker heartbeat</div>
              <div className="mt-2 text-xs text-zinc-400">
                {ops.worker_healthy
                  ? "Healthy (last 60s)"
                  : "Stale or missing"}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
