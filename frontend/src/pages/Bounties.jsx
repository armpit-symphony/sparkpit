import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLayout } from "@/components/layout/AppShell";
import { QuickPanel } from "@/components/layout/QuickPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { toast } from "@/components/ui/sonner";
import { useAppData } from "@/components/layout/AppShell";

export default function Bounties() {
  const { setSecondaryPanel } = useLayout();
  const { rooms } = useAppData();
  const [bounties, setBounties] = useState([]);
  const [filters, setFilters] = useState({ status: "", tag: "", sort: "newest" });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    title: "",
    description: "",
    tags: "",
    reward_amount: "",
    reward_currency: "USD",
    room_id: "",
  });
  const navigate = useNavigate();

  const loadBounties = async () => {
    try {
      const response = await api.get("/bounties", {
        params: {
          status: filters.status || undefined,
          tag: filters.tag || undefined,
          sort: filters.sort || undefined,
        },
      });
      setBounties(response.data.items || []);
    } catch (error) {
      toast.error("Unable to load bounties.");
    }
  };

  useEffect(() => {
    setSecondaryPanel(<QuickPanel />);
  }, [setSecondaryPanel]);

  useEffect(() => {
    loadBounties();
  }, [filters]);

  const createBounty = async () => {
    try {
      const payload = {
        ...form,
        tags: form.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        reward_amount: form.reward_amount ? Number(form.reward_amount) : null,
        room_id: form.room_id || null,
      };
      await api.post("/bounties", payload);
      toast.success("Bounty posted.");
      setOpen(false);
      setForm({
        title: "",
        description: "",
        tags: "",
        reward_amount: "",
        reward_currency: "USD",
        room_id: "",
      });
      loadBounties();
    } catch (error) {
      toast.error("Unable to create bounty.");
    }
  };

  return (
    <div className="flex h-full flex-col" data-testid="bounties-page">
      <div className="border-b border-zinc-800 bg-zinc-950/70 px-6 py-4">
        <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">Bounties</div>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <select
            value={filters.status}
            onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))}
            className="h-9 w-40 rounded-none border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-200"
            data-testid="bounty-filter-status"
          >
            <option value="">All status</option>
            <option value="open">Open</option>
            <option value="claimed">Claimed</option>
            <option value="submitted">Submitted</option>
            <option value="approved">Approved</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <Input
            placeholder="Filter by tag"
            value={filters.tag}
            onChange={(event) => setFilters((prev) => ({ ...prev, tag: event.target.value }))}
            className="h-9 w-48 rounded-none border-zinc-800 bg-zinc-950"
            data-testid="bounty-filter-tag"
          />
          <select
            value={filters.sort}
            onChange={(event) => setFilters((prev) => ({ ...prev, sort: event.target.value }))}
            className="h-9 w-40 rounded-none border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-200"
            data-testid="bounty-filter-sort"
          >
            <option value="newest">Newest</option>
            <option value="reward">Highest reward</option>
          </select>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button
                className="rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
                data-testid="bounty-create-open"
              >
                New bounty
              </Button>
            </DialogTrigger>
            <DialogContent className="rounded-none border border-zinc-800 bg-zinc-950 text-zinc-100">
              <DialogHeader>
                <DialogTitle data-testid="bounty-create-title">Post a bounty</DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <Input
                  placeholder="Title"
                  value={form.title}
                  onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
                  className="rounded-none border-zinc-800 bg-zinc-950"
                  data-testid="bounty-title-input"
                />
                <Input
                  placeholder="Description"
                  value={form.description}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, description: event.target.value }))
                  }
                  className="rounded-none border-zinc-800 bg-zinc-950"
                  data-testid="bounty-description-input"
                />
                <Input
                  placeholder="Tags (comma separated)"
                  value={form.tags}
                  onChange={(event) => setForm((prev) => ({ ...prev, tags: event.target.value }))}
                  className="rounded-none border-zinc-800 bg-zinc-950 font-mono"
                  data-testid="bounty-tags-input"
                />
                <div className="flex gap-2">
                  <Input
                    placeholder="Reward amount"
                    value={form.reward_amount}
                    onChange={(event) =>
                      setForm((prev) => ({ ...prev, reward_amount: event.target.value }))
                    }
                    className="rounded-none border-zinc-800 bg-zinc-950"
                    data-testid="bounty-reward-input"
                  />
                  <Input
                    placeholder="Currency"
                    value={form.reward_currency}
                    onChange={(event) =>
                      setForm((prev) => ({ ...prev, reward_currency: event.target.value }))
                    }
                    className="w-24 rounded-none border-zinc-800 bg-zinc-950 font-mono"
                    data-testid="bounty-currency-input"
                  />
                </div>
                <Input
                  placeholder="Room ID (optional)"
                  value={form.room_id}
                  onChange={(event) => setForm((prev) => ({ ...prev, room_id: event.target.value }))}
                  className="rounded-none border-zinc-800 bg-zinc-950 font-mono"
                  data-testid="bounty-room-input"
                />
                {rooms.length > 0 && (
                  <div className="text-xs text-zinc-500" data-testid="bounty-room-hint">
                    Tip: use a room id from your room list.
                  </div>
                )}
                <Button
                  onClick={createBounty}
                  className="w-full rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
                  data-testid="bounty-create-submit"
                >
                  Publish bounty
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6" data-testid="bounties-list">
        <div className="grid gap-4 md:grid-cols-2">
          {bounties.map((bounty) => (
            <button
              key={bounty.id}
              onClick={() => navigate(`/app/bounties/${bounty.id}`)}
              className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5 text-left transition-colors hover:border-amber-500/40"
              data-testid={`bounty-card-${bounty.id}`}
            >
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-zinc-100">{bounty.title}</div>
                <Badge
                  className="rounded-none border border-amber-500/30 bg-amber-500/10 text-amber-300"
                  data-testid={`bounty-status-${bounty.id}`}
                >
                  {bounty.status}
                </Badge>
              </div>
              <p className="mt-2 text-xs text-zinc-400" data-testid={`bounty-description-${bounty.id}`}>
                {bounty.description}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {(bounty.tags || []).map((tag) => (
                  <span
                    key={tag}
                    className="rounded-none border border-cyan-500/20 px-2 py-1 text-[10px] uppercase text-cyan-300"
                    data-testid={`bounty-tag-${bounty.id}-${tag}`}
                  >
                    {tag}
                  </span>
                ))}
              </div>
              {bounty.reward_amount && (
                <div className="mt-3 text-xs font-mono text-zinc-400" data-testid={`bounty-reward-${bounty.id}`}>
                  Reward: {bounty.reward_amount} {bounty.reward_currency}
                </div>
              )}
            </button>
          ))}
        </div>
        {bounties.length === 0 && (
          <div className="text-sm text-zinc-500" data-testid="bounties-empty">
            No bounties match the current filters.
          </div>
        )}
      </div>
    </div>
  );
}
