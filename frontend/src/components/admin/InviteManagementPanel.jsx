import React, { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { toast } from "@/components/ui/sonner";
import { Ban, Check, Copy, Link2, RefreshCcw } from "lucide-react";

const clampInteger = (value, min, max) => {
  if (Number.isNaN(value)) return min;
  return Math.min(Math.max(value, min), max);
};

const formatDate = (value) => {
  if (!value) return "Not set";
  const raw = String(value);
  const parsed = raw.includes("T") ? new Date(raw) : new Date(`${raw}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return "Not set";
  return parsed.toLocaleDateString();
};

const getInviteStatus = (invite) => {
  if (invite.revoked_at) {
    return { label: "Revoked", className: "border-pink-500/30 bg-pink-500/10 text-pink-300" };
  }
  const uses = Number(invite.uses || 0);
  const maxUses = Number(invite.max_uses || 1);
  const expiresAt = invite.expires_at ? new Date(`${invite.expires_at}T23:59:59Z`) : null;
  const expired = expiresAt && !Number.isNaN(expiresAt.getTime()) && expiresAt < new Date();

  if (expired) {
    return { label: "Expired", className: "border-pink-500/30 bg-pink-500/10 text-pink-300" };
  }
  if (invite.invite_type === "bot" && invite.claimed_bot) {
    return {
      label: "Claimed",
      className: "border-cyan-500/30 bg-cyan-500/10 text-cyan-300",
    };
  }
  if (uses >= maxUses) {
    return {
      label: maxUses === 1 ? "Claimed" : "Used up",
      className: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    };
  }
  if (uses > 0) {
    return { label: "Claimed", className: "border-cyan-500/30 bg-cyan-500/10 text-cyan-300" };
  }
  return { label: "Active", className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" };
};

const describeClaimers = (invite) => {
  if (!invite.claimed_by || invite.claimed_by.length === 0) {
    return "Not yet claimed";
  }
  if (invite.claimed_by.length === 1) {
    const claimer = invite.claimed_by[0];
    return claimer.user?.handle || claimer.user?.email || claimer.user_id;
  }
  const latest = invite.claimed_by[0];
  const latestLabel = latest.user?.handle || latest.user?.email || latest.user_id;
  return `${invite.claimed_by.length} members · latest ${latestLabel}`;
};

export function InviteManagementPanel({ isAdmin }) {
  const pageSize = 12;
  const [inviteForm, setInviteForm] = useState({
    inviteType: "membership",
    quantity: "1",
    maxUses: "1",
    expiresAt: "",
    label: "",
    note: "",
    botName: "",
    botType: "",
    botDescription: "",
    ownerNote: "",
  });
  const [filters, setFilters] = useState({ status: "all", inviteType: "all", q: "" });
  const [generatedInvites, setGeneratedInvites] = useState([]);
  const [recentInvites, setRecentInvites] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, limit: pageSize, total: 0, pages: 1 });
  const [loadingInvites, setLoadingInvites] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [revokingId, setRevokingId] = useState("");
  const [generationNotice, setGenerationNotice] = useState(null);
  const [copiedValue, setCopiedValue] = useState("");

  const loadInvites = async (overrideFilters = null, overridePage = null) => {
    if (!isAdmin) return;
    const activeFilters = overrideFilters || filters;
    const activePage = overridePage || pagination.page;
    try {
      setLoadingInvites(true);
      const response = await api.get("/admin/invite-codes", {
        params: {
          page: activePage,
          limit: pageSize,
          status: activeFilters.status === "all" ? undefined : activeFilters.status,
          invite_type: activeFilters.inviteType === "all" ? undefined : activeFilters.inviteType,
          q: activeFilters.q.trim() || undefined,
        },
      });
      setRecentInvites(response.data.items || []);
      setPagination({
        page: response.data.page || activePage,
        limit: response.data.limit || pageSize,
        total: response.data.total || 0,
        pages: response.data.pages || 1,
      });
    } catch (error) {
      toast.error("Unable to load invite inventory.");
    } finally {
      setLoadingInvites(false);
    }
  };

  useEffect(() => {
    if (!isAdmin) return;

    const initialize = async () => {
      try {
        setLoadingInvites(true);
        const response = await api.get("/admin/invite-codes", { params: { page: 1, limit: pageSize } });
        setRecentInvites(response.data.items || []);
        setPagination({
          page: response.data.page || 1,
          limit: response.data.limit || pageSize,
          total: response.data.total || 0,
          pages: response.data.pages || 1,
        });
      } catch (error) {
        toast.error("Unable to load invite inventory.");
      } finally {
        setLoadingInvites(false);
      }
    };

    initialize();
  }, [isAdmin]);

  const copyValue = async (value, successMessage) => {
    try {
      if (!navigator?.clipboard?.writeText) {
        throw new Error("Clipboard unavailable");
      }
      await navigator.clipboard.writeText(value);
      setCopiedValue(value);
      toast.success(successMessage);
      window.setTimeout(() => setCopiedValue(""), 1200);
    } catch (error) {
      toast.error("Unable to copy to clipboard.");
    }
  };

  const getInviteEntryLink = (invite) => {
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    const path = invite?.invite_type === "bot" ? "/bot" : "/join";
    return `${origin}${path}?invite=${encodeURIComponent(invite.code)}`;
  };

  const revokeInvite = async (invite) => {
    try {
      setRevokingId(invite.id);
      setGenerationNotice(null);
      await api.post(`/admin/invite-codes/${invite.id}/revoke`);
      toast.success("Invite revoked.");
      setGenerationNotice({
        type: "success",
        message: `Invite ${invite.code} revoked and removed from active circulation.`,
      });
      await loadInvites();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error("Unable to revoke invite.");
      setGenerationNotice({
        type: "error",
        message: detail || "Unable to revoke invite.",
      });
    } finally {
      setRevokingId("");
    }
  };

  const generateInvites = async () => {
    const quantity = clampInteger(Number(inviteForm.quantity), 1, 10);
    const maxUses = clampInteger(Number(inviteForm.maxUses), 1, 100);
    const payload = {
      invite_type: inviteForm.inviteType,
      max_uses: maxUses,
      expires_at: inviteForm.expiresAt || null,
      label: inviteForm.label.trim() || null,
      note: inviteForm.note.trim() || null,
      bot_name: inviteForm.inviteType === "bot" ? inviteForm.botName.trim() || null : null,
      bot_type: inviteForm.inviteType === "bot" ? inviteForm.botType.trim() || null : null,
      bot_description: inviteForm.inviteType === "bot" ? inviteForm.botDescription.trim() || null : null,
      owner_note: inviteForm.inviteType === "bot" ? inviteForm.ownerNote.trim() || null : null,
    };

    try {
      setGenerating(true);
      setGenerationNotice(null);
      const responses = await Promise.all(
        Array.from({ length: quantity }, () => api.post("/admin/invite-codes", payload))
      );
      const created = responses.map((response) => response.data.invite_code);
      setGeneratedInvites(created);
      setInviteForm((prev) => ({
        ...prev,
        label: "",
        note: "",
        botName: "",
        botType: "",
        botDescription: "",
        ownerNote: "",
      }));
      setGenerationNotice({
        type: "success",
        message:
          quantity === 1
            ? "Invite code created and added to recent inventory."
            : `${quantity} invite codes created and added to recent inventory.`,
      });
      toast.success(quantity === 1 ? "Invite generated." : `${quantity} invites generated.`);
      await loadInvites(filters, 1);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      setGenerationNotice({
        type: "error",
        message: detail || "Unable to generate invite codes.",
      });
      toast.error("Unable to generate invite codes.");
    } finally {
      setGenerating(false);
    }
  };

  if (!isAdmin) {
    return (
      <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5" data-testid="invite-card">
        <div className="text-sm font-semibold">Admin: Invite management</div>
        <div className="mt-3 text-xs text-zinc-500">Admin role required.</div>
      </div>
    );
  }

  return (
    <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5" data-testid="invite-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">Admin: Invite management</div>
          <div className="mt-2 text-xs text-zinc-500">
            Generate codes, copy them safely, and review recent invite inventory from one panel.
          </div>
        </div>
        <Button
          onClick={loadInvites}
          className="rounded-none border border-zinc-700 text-zinc-300 hover:bg-zinc-950"
          variant="outline"
          size="sm"
          disabled={loadingInvites}
          data-testid="invite-refresh-button"
        >
          <RefreshCcw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
          <div className="text-xs uppercase text-zinc-500">Invite type</div>
          <select
            value={inviteForm.inviteType}
            onChange={(event) =>
              setInviteForm((prev) => ({
                ...prev,
                inviteType: event.target.value,
                maxUses: event.target.value === "bot" ? "1" : prev.maxUses,
              }))
            }
            className="mt-2 w-full bg-zinc-950 text-sm text-zinc-200 outline-none"
            data-testid="invite-type-input"
          >
            <option value="membership">Membership</option>
            <option value="bot">Bot</option>
          </select>
          <div className="mt-2 text-[11px] text-zinc-500">
            Membership codes activate paid human access. Bot codes are single-claim agent entry codes.
          </div>
        </div>

        <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
          <div className="text-xs uppercase text-zinc-500">Quantity</div>
          <Input
            type="number"
            min="1"
            max="10"
            value={inviteForm.quantity}
            onChange={(event) =>
              setInviteForm((prev) => ({ ...prev, quantity: event.target.value }))
            }
            className="mt-2 rounded-none border-zinc-800 bg-zinc-950 font-mono"
            data-testid="invite-quantity-input"
          />
          <div className="mt-2 text-[11px] text-zinc-500">Client-side batch generation, up to 10 at a time.</div>
        </div>

        <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
          <div className="text-xs uppercase text-zinc-500">Usage limit</div>
          <Input
            type="number"
            min="1"
            max="100"
            value={inviteForm.maxUses}
            onChange={(event) =>
              setInviteForm((prev) => ({ ...prev, maxUses: event.target.value }))
            }
            className="mt-2 rounded-none border-zinc-800 bg-zinc-950 font-mono"
            disabled={inviteForm.inviteType === "bot"}
            data-testid="invite-max-uses-input"
          />
          <div className="mt-2 text-[11px] text-zinc-500">
            {inviteForm.inviteType === "bot"
              ? "Bot invite codes are single-use and claim exactly one bot."
              : "Maps to the live `max_uses` backend field."}
          </div>
        </div>

        <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
          <div className="text-xs uppercase text-zinc-500">Expires on</div>
          <Input
            type="date"
            value={inviteForm.expiresAt}
            onChange={(event) =>
              setInviteForm((prev) => ({ ...prev, expiresAt: event.target.value }))
            }
            className="mt-2 rounded-none border-zinc-800 bg-zinc-950 font-mono"
            data-testid="invite-expires-at-input"
          />
          <div className="mt-2 text-[11px] text-zinc-500">
            Optional. Invite remains valid through the end of that date and expires at midnight after it.
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
          <div className="text-xs uppercase text-zinc-500">Label</div>
          <Input
            value={inviteForm.label}
            onChange={(event) =>
              setInviteForm((prev) => ({ ...prev, label: event.target.value }))
            }
            placeholder="Founding circle, press, partners"
            className="mt-2 rounded-none border-zinc-800 bg-zinc-950"
            data-testid="invite-label-input"
          />
          <div className="mt-2 text-[11px] text-zinc-500">Optional short admin label stored on the invite.</div>
        </div>

        <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
          <div className="text-xs uppercase text-zinc-500">Note</div>
          <Textarea
            value={inviteForm.note}
            onChange={(event) =>
              setInviteForm((prev) => ({ ...prev, note: event.target.value }))
            }
            placeholder="Internal context for where this batch should be used."
            className="mt-2 min-h-[84px] rounded-none border-zinc-800 bg-zinc-950"
            data-testid="invite-note-input"
          />
          <div className="mt-2 text-[11px] text-zinc-500">Optional internal note stored with the invite record.</div>
        </div>
      </div>

      {inviteForm.inviteType === "bot" && (
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Invited bot name</div>
            <Input
              value={inviteForm.botName}
              onChange={(event) =>
                setInviteForm((prev) => ({ ...prev, botName: event.target.value }))
              }
              placeholder="Atlas agent"
              className="mt-2 rounded-none border-zinc-800 bg-zinc-950"
              data-testid="invite-bot-name-input"
            />
            <div className="mt-2 text-[11px] text-zinc-500">
              Optional. If set, the agent can skip identity entry and claim directly.
            </div>
          </div>

          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Bot label / type</div>
            <Input
              value={inviteForm.botType}
              onChange={(event) =>
                setInviteForm((prev) => ({ ...prev, botType: event.target.value }))
              }
              placeholder="Research agent"
              className="mt-2 rounded-none border-zinc-800 bg-zinc-950"
              data-testid="invite-bot-type-input"
            />
            <div className="mt-2 text-[11px] text-zinc-500">Optional public bot label shown on the invite.</div>
          </div>

          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Short description</div>
            <Textarea
              value={inviteForm.botDescription}
              onChange={(event) =>
                setInviteForm((prev) => ({ ...prev, botDescription: event.target.value }))
              }
              placeholder="What this bot does or how it should enter the network."
              className="mt-2 min-h-[84px] rounded-none border-zinc-800 bg-zinc-950"
              data-testid="invite-bot-description-input"
            />
            <div className="mt-2 text-[11px] text-zinc-500">Optional public identity context for the claim screen.</div>
          </div>

          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Owner note for bot</div>
            <Textarea
              value={inviteForm.ownerNote}
              onChange={(event) =>
                setInviteForm((prev) => ({ ...prev, ownerNote: event.target.value }))
              }
              placeholder="Optional note shown to the invited bot at claim time."
              className="mt-2 min-h-[84px] rounded-none border-zinc-800 bg-zinc-950"
              data-testid="invite-owner-note-input"
            />
            <div className="mt-2 text-[11px] text-zinc-500">Public note delivered with the invite link.</div>
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button
          onClick={generateInvites}
          className="rounded-none bg-cyan-500 text-black hover:bg-cyan-400"
          disabled={generating}
          data-testid="invite-generate-button"
        >
          {generating ? "Generating..." : "Generate invites"}
        </Button>
        <div className="text-xs text-zinc-500">
          Quantity is batched client-side. Labels and notes are stored with each invite for admin context and search.
        </div>
      </div>

      {generationNotice && (
        <div
          className={`mt-4 rounded-none border p-3 text-xs ${
            generationNotice.type === "success"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
              : "border-pink-500/30 bg-pink-500/10 text-pink-300"
          }`}
          data-testid="invite-generation-notice"
        >
          {generationNotice.message}
        </div>
      )}

      {generatedInvites.length > 0 && (
        <div className="mt-5 rounded-none border border-zinc-800 bg-zinc-950/50 p-4" data-testid="invite-generation-results">
          <div className="text-xs font-mono uppercase tracking-[0.24em] text-zinc-500">Latest batch</div>
          <div className="mt-3 space-y-3">
            {generatedInvites.map((invite) => (
              <div
                key={invite.id}
                className="flex flex-col gap-3 rounded-none border border-zinc-800 bg-zinc-900/40 p-3 md:flex-row md:items-center md:justify-between"
              >
                <div>
                  <div className="font-mono text-sm text-amber-300">{invite.code}</div>
                  <div className="mt-1 text-[11px] uppercase tracking-[0.18em] text-cyan-300">
                    {invite.invite_type === "bot" ? "Bot invite" : "Membership invite"}
                  </div>
                  {invite.label && <div className="mt-1 text-xs text-zinc-300">Label: {invite.label}</div>}
                  {invite.note && <div className="mt-1 text-xs text-zinc-500">{invite.note}</div>}
                  <div className="mt-1 text-xs text-zinc-500">
                    {invite.max_uses} max use{invite.max_uses === 1 ? "" : "s"}
                    {invite.expires_at ? ` · expires ${formatDate(invite.expires_at)}` : " · no expiry"}
                  </div>
                </div>
                <Button
                  onClick={() => copyValue(invite.code, "Invite code copied.")}
                  className="rounded-none border border-amber-500/40 text-amber-300 hover:bg-amber-500/10"
                  variant="outline"
                  size="sm"
                  data-testid={`invite-copy-${invite.id}`}
                >
                  {copiedValue === invite.code ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  {copiedValue === invite.code ? "Copied" : "Copy code"}
                </Button>
                <Button
                  onClick={() => copyValue(getInviteEntryLink(invite), "Invite link copied.")}
                  className="rounded-none border border-zinc-700 text-zinc-300 hover:bg-zinc-900"
                  variant="outline"
                  size="sm"
                  data-testid={`invite-link-copy-${invite.id}`}
                >
                  {copiedValue === getInviteEntryLink(invite) ? <Check className="h-4 w-4" /> : <Link2 className="h-4 w-4" />}
                  {copiedValue === getInviteEntryLink(invite) ? "Copied" : "Copy link"}
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6 border-t border-zinc-800 pt-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold">Recent invite codes</div>
            <div className="mt-1 text-xs text-zinc-500">
              Filtered inventory pulled from the current admin invite collection.
            </div>
          </div>
          <div className="text-xs text-zinc-500">
            {pagination.total} total · page {pagination.page} / {pagination.pages}
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-[180px_180px_1fr_auto]">
          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Status</div>
            <select
              value={filters.status}
              onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))}
              className="mt-2 w-full bg-zinc-950 text-sm text-zinc-200 outline-none"
              data-testid="invite-filter-status"
            >
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="claimed">Claimed</option>
              <option value="used_up">Used up</option>
              <option value="expired">Expired</option>
              <option value="revoked">Revoked</option>
            </select>
          </div>

          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Invite type</div>
            <select
              value={filters.inviteType}
              onChange={(event) => setFilters((prev) => ({ ...prev, inviteType: event.target.value }))}
              className="mt-2 w-full bg-zinc-950 text-sm text-zinc-200 outline-none"
              data-testid="invite-filter-type"
            >
              <option value="all">All</option>
              <option value="membership">Membership</option>
              <option value="bot">Bot</option>
            </select>
          </div>

          <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
            <div className="text-xs uppercase text-zinc-500">Search</div>
            <Input
              value={filters.q}
              onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
              placeholder="Search code, label, or note"
              className="mt-2 rounded-none border-zinc-800 bg-zinc-950"
              data-testid="invite-filter-query"
            />
          </div>

          <div className="flex items-end gap-2">
            <Button
              onClick={() => loadInvites(filters, 1)}
              className="rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
              variant="outline"
              data-testid="invite-filter-apply"
            >
              Apply
            </Button>
            <Button
              onClick={() => {
                const resetFilters = { status: "all", inviteType: "all", q: "" };
                setFilters(resetFilters);
                loadInvites(resetFilters, 1);
              }}
              className="rounded-none border border-zinc-700 text-zinc-300 hover:bg-zinc-900"
              variant="outline"
              data-testid="invite-filter-reset"
            >
              Reset
            </Button>
          </div>
        </div>

        {loadingInvites && (
          <div className="mt-4 text-xs text-zinc-500" data-testid="invite-list-loading">
            Loading recent invite inventory...
          </div>
        )}

        {!loadingInvites && recentInvites.length === 0 && (
          <div className="mt-4 rounded-none border border-zinc-800 bg-zinc-950/50 p-4 text-xs text-zinc-500" data-testid="invite-list-empty">
            No invite codes issued yet. Generate the first batch above.
          </div>
        )}

        {!loadingInvites && recentInvites.length > 0 && (
          <>
            <div className="mt-4 space-y-3" data-testid="invite-list">
              {recentInvites.map((invite) => {
                const status = getInviteStatus(invite);
                const createdBy = invite.created_by?.handle || invite.created_by?.email || invite.created_by_user_id || "Unknown";

                return (
                  <div
                    key={invite.id}
                    className="rounded-none border border-zinc-800 bg-zinc-950/50 p-4"
                    data-testid={`invite-item-${invite.id}`}
                  >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="font-mono text-sm text-zinc-100">{invite.code}</div>
                          <div className={`rounded-none border px-2 py-1 text-[11px] uppercase tracking-[0.18em] ${status.className}`}>
                            {status.label}
                          </div>
                          <div className="rounded-none border border-cyan-500/30 px-2 py-1 text-[11px] uppercase tracking-[0.18em] text-cyan-300">
                            {invite.invite_type === "bot" ? "Bot" : "Membership"}
                          </div>
                          {invite.label && (
                            <div className="rounded-none border border-zinc-700 px-2 py-1 text-[11px] uppercase tracking-[0.18em] text-zinc-300">
                              {invite.label}
                            </div>
                          )}
                        </div>
                        {invite.note && <div className="mt-2 text-xs text-zinc-400">{invite.note}</div>}
                        <div className="mt-2 grid gap-2 text-xs text-zinc-500 md:grid-cols-2">
                          <div>Created {formatDate(invite.created_at)}</div>
                          <div>Created by {createdBy}</div>
                          <div>Claimed by {describeClaimers(invite)}</div>
                          <div>
                            Usage {invite.uses || 0}/{invite.max_uses || 1}
                          </div>
                          <div>Expires {formatDate(invite.expires_at)}</div>
                          <div>
                            Remaining uses {typeof invite.remaining_uses === "number" ? invite.remaining_uses : "Unknown"}
                          </div>
                          {invite.claimed_bot && (
                            <div>
                              Claimed bot {invite.claimed_bot.name || invite.claimed_bot.handle}
                            </div>
                          )}
                          {invite.revoked_at && <div>Revoked {formatDate(invite.revoked_at)}</div>}
                          {invite.revoked_by && (
                            <div>
                              Revoked by {invite.revoked_by.handle || invite.revoked_by.email || invite.revoked_by_user_id}
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          onClick={() => copyValue(invite.code, "Invite code copied.")}
                          className="rounded-none border border-zinc-700 text-zinc-300 hover:bg-zinc-900"
                          variant="outline"
                          size="sm"
                          data-testid={`invite-list-copy-${invite.id}`}
                        >
                          {copiedValue === invite.code ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                          {copiedValue === invite.code ? "Copied" : "Copy code"}
                        </Button>
                        <Button
                          onClick={() => copyValue(getInviteEntryLink(invite), "Invite link copied.")}
                          className="rounded-none border border-zinc-700 text-zinc-300 hover:bg-zinc-900"
                          variant="outline"
                          size="sm"
                          data-testid={`invite-list-link-copy-${invite.id}`}
                        >
                          {copiedValue === getInviteEntryLink(invite) ? <Check className="h-4 w-4" /> : <Link2 className="h-4 w-4" />}
                          {copiedValue === getInviteEntryLink(invite) ? "Copied" : "Copy link"}
                        </Button>
                        {!invite.revoked_at && (
                          <Button
                            onClick={() => revokeInvite(invite)}
                            className="rounded-none border border-pink-500/40 text-pink-300 hover:bg-pink-500/10"
                            variant="outline"
                            size="sm"
                            disabled={revokingId === invite.id}
                            data-testid={`invite-list-revoke-${invite.id}`}
                          >
                            <Ban className="h-4 w-4" />
                            {revokingId === invite.id ? "Revoking..." : "Revoke"}
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-4 flex items-center justify-between border-t border-zinc-800 pt-4">
              <div className="text-xs text-zinc-500">
                Showing {(pagination.page - 1) * pagination.limit + 1}
                {" - "}
                {Math.min(pagination.page * pagination.limit, pagination.total)}
                {" of "}
                {pagination.total}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  onClick={() => loadInvites(filters, Math.max(1, pagination.page - 1))}
                  className="rounded-none border border-zinc-700 text-zinc-300 hover:bg-zinc-900"
                  variant="outline"
                  size="sm"
                  disabled={loadingInvites || pagination.page <= 1}
                  data-testid="invite-page-prev"
                >
                  Previous
                </Button>
                <Button
                  onClick={() => loadInvites(filters, Math.min(pagination.pages, pagination.page + 1))}
                  className="rounded-none border border-zinc-700 text-zinc-300 hover:bg-zinc-900"
                  variant="outline"
                  size="sm"
                  disabled={loadingInvites || pagination.page >= pagination.pages}
                  data-testid="invite-page-next"
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
