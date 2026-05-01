import React, { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/sonner";
import { AdminStatusCards } from "@/components/admin/AdminStatusCards";

const INITIAL_FORM = {
  publishable_key: "",
  secret_key: "",
  webhook_secret: "",
  membership_yearly_price_id: "",
  bot_invite_price_id: "",
};

export function StripeSettingsPanel({ onUpdated }) {
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState(INITIAL_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const loadStatus = async () => {
    try {
      setLoading(true);
      const response = await api.get("/admin/payments/stripe/config/status");
      setStatus(response.data);
    } catch (error) {
      toast.error("Unable to load Stripe config status.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  useEffect(() => {
    if (!status) return;
    setForm((current) => ({
      ...current,
      publishable_key: status.publishable_key || "",
      membership_yearly_price_id: status.membership_yearly_price_id || "",
      bot_invite_price_id: status.bot_invite_price_id || "",
      secret_key: "",
      webhook_secret: "",
    }));
  }, [status]);

  const cards = useMemo(
    () => [
      {
        id: "credentials",
        label: "Credentials",
        detail: status?.credentials_configured
          ? "Publishable, secret, and webhook secrets are configured."
          : "Stripe credentials are incomplete.",
        ok: !!status?.credentials_configured,
        eyebrow: "Config",
      },
      {
        id: "membership",
        label: "Membership price",
        detail: status?.membership_yearly_price_id || "Not configured. Checkout falls back to the server amount.",
        ok: !!status?.membership_price_configured,
        eyebrow: "Price",
      },
      {
        id: "bot-invite",
        label: "Bot invite price",
        detail: status?.bot_invite_price_id || "Not configured yet.",
        ok: !!status?.bot_invite_price_configured,
        eyebrow: "Price",
      },
      {
        id: "webhook",
        label: "Webhook receipt",
        detail: status?.stripe_webhook_last_received
          ? `Last received ${new Date(status.stripe_webhook_last_received).toLocaleString()}`
          : "No webhook received yet.",
        ok: !!status?.stripe_webhook_last_received,
        eyebrow: "Health",
      },
    ],
    [status],
  );

  const saveConfig = async () => {
    try {
      setSaving(true);
      const payload = {
        publishable_key: form.publishable_key,
        membership_yearly_price_id: form.membership_yearly_price_id,
        bot_invite_price_id: form.bot_invite_price_id,
      };
      if (form.secret_key.trim()) {
        payload.secret_key = form.secret_key.trim();
      }
      if (form.webhook_secret.trim()) {
        payload.webhook_secret = form.webhook_secret.trim();
      }
      const response = await api.post("/admin/payments/stripe/config", payload);
      setStatus(response.data.status);
      setForm((current) => ({ ...current, secret_key: "", webhook_secret: "" }));
      onUpdated?.();
      toast.success("Stripe config saved.");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unable to save Stripe config.");
    } finally {
      setSaving(false);
    }
  };

  const testConfig = async () => {
    try {
      setTesting(true);
      const response = await api.post("/admin/payments/stripe/test");
      setStatus(response.data.status);
      onUpdated?.();
      toast.success(response.data.result?.message || "Stripe connection successful.");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unable to test Stripe config.");
      await loadStatus();
      onUpdated?.();
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="mt-10 border-t border-zinc-800 pt-6" data-testid="stripe-settings-panel">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">
            Payments
          </div>
          <div className="text-lg font-semibold">Stripe configuration</div>
          <div className="mt-1 text-sm text-zinc-400">
            Save Stripe credentials and price IDs server-side. Secret fields stay masked after save.
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={loadStatus}
            variant="outline"
            className="rounded-none border-zinc-700 text-zinc-300 hover:bg-zinc-900"
            disabled={loading}
          >
            Refresh
          </Button>
          <Button
            onClick={testConfig}
            variant="outline"
            className="rounded-none border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
            disabled={testing || loading}
            data-testid="stripe-config-test"
          >
            {testing ? "Testing..." : "Test connection"}
          </Button>
          <Button
            onClick={saveConfig}
            className="rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
            disabled={saving || loading}
            data-testid="stripe-config-save"
          >
            {saving ? "Saving..." : "Save config"}
          </Button>
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5">
          <div className="grid gap-3">
            <Input
              value={form.publishable_key}
              onChange={(event) =>
                setForm((current) => ({ ...current, publishable_key: event.target.value }))
              }
              placeholder="pk_live_..."
              className="rounded-none border-zinc-800 bg-zinc-950"
              data-testid="stripe-publishable-key-input"
            />
            <Input
              value={form.secret_key}
              onChange={(event) =>
                setForm((current) => ({ ...current, secret_key: event.target.value }))
              }
              placeholder="Leave blank to keep current secret key"
              className="rounded-none border-zinc-800 bg-zinc-950"
              type="password"
              data-testid="stripe-secret-key-input"
            />
            <Input
              value={form.webhook_secret}
              onChange={(event) =>
                setForm((current) => ({ ...current, webhook_secret: event.target.value }))
              }
              placeholder="Leave blank to keep current webhook secret"
              className="rounded-none border-zinc-800 bg-zinc-950"
              type="password"
              data-testid="stripe-webhook-secret-input"
            />
            <Input
              value={form.membership_yearly_price_id}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  membership_yearly_price_id: event.target.value,
                }))
              }
              placeholder="price_... membership yearly"
              className="rounded-none border-zinc-800 bg-zinc-950 font-mono"
              data-testid="stripe-membership-price-input"
            />
            <Input
              value={form.bot_invite_price_id}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  bot_invite_price_id: event.target.value,
                }))
              }
              placeholder="price_... bot invite one-time"
              className="rounded-none border-zinc-800 bg-zinc-950 font-mono"
              data-testid="stripe-bot-invite-price-input"
            />
          </div>

          <div className="mt-4 rounded-none border border-zinc-800 bg-zinc-950/60 p-3 text-xs text-zinc-400">
            Leave secret fields blank to keep the currently stored server-side values. Saving does
            not send stored secrets back to the browser.
          </div>
        </div>

        <div className="space-y-4">
          <AdminStatusCards items={cards} testId="stripe-config-status-cards" />

          <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5 text-sm text-zinc-300">
            <div className="text-xs font-mono uppercase tracking-[0.24em] text-zinc-500">
              Stored status
            </div>
            <div className="mt-3 space-y-2">
              <div>
                Publishable key:{" "}
                <span className="font-mono text-zinc-100">{status?.publishable_key || "Not set"}</span>
              </div>
              <div>
                Secret key:{" "}
                <span className="font-mono text-zinc-100">{status?.secret_key_masked || "Not set"}</span>
              </div>
              <div>
                Webhook secret:{" "}
                <span className="font-mono text-zinc-100">{status?.webhook_secret_masked || "Not set"}</span>
              </div>
              <div>
                Updated:{" "}
                <span className="text-zinc-100">
                  {status?.updated_at ? new Date(status.updated_at).toLocaleString() : "Never"}
                </span>
              </div>
              <div>
                Updated by:{" "}
                <span className="text-zinc-100">
                  {status?.updated_by?.email || status?.updated_by?.handle || "Unknown"}
                </span>
              </div>
            </div>
          </div>

          <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5 text-sm text-zinc-300">
            <div className="text-xs font-mono uppercase tracking-[0.24em] text-zinc-500">
              Last test
            </div>
            <div className="mt-3 space-y-2">
              <div>
                Result:{" "}
                <span className="text-zinc-100">
                  {status?.last_tested_at
                    ? status?.last_test_ok
                      ? "OK"
                      : "Failed"
                    : "Not tested"}
                </span>
              </div>
              <div>
                Message:{" "}
                <span className="text-zinc-100">{status?.last_test_message || "No test run yet."}</span>
              </div>
              <div>
                Account:{" "}
                <span className="font-mono text-zinc-100">{status?.last_test_account_id || "N/A"}</span>
              </div>
              <div>
                Mode:{" "}
                <span className="text-zinc-100">
                  {status?.last_test_livemode === true
                    ? "Live"
                    : status?.last_test_livemode === false
                      ? "Test"
                      : "Unknown"}
                </span>
              </div>
              <div>
                Tested at:{" "}
                <span className="text-zinc-100">
                  {status?.last_tested_at ? new Date(status.last_tested_at).toLocaleString() : "Never"}
                </span>
              </div>
              <div>
                Tested by:{" "}
                <span className="text-zinc-100">
                  {status?.last_tested_by?.email || status?.last_tested_by?.handle || "N/A"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
