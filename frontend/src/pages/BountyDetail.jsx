import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/sonner";
import { useLayout } from "@/components/layout/AppShell";
import { QuickPanel } from "@/components/layout/QuickPanel";

export default function BountyDetail() {
  const { id } = useParams();
  const [bounty, setBounty] = useState(null);
  const [updates, setUpdates] = useState([]);
  const [comment, setComment] = useState("");
  const [status, setStatus] = useState("");
  const navigate = useNavigate();
  const { setSecondaryPanel } = useLayout();

  const loadBounty = async () => {
    try {
      const response = await api.get(`/bounties/${id}`);
      setBounty(response.data.bounty);
      setUpdates(response.data.updates || []);
      setStatus(response.data.bounty.status);
    } catch (error) {
      toast.error("Unable to load bounty.");
    }
  };

  useEffect(() => {
    setSecondaryPanel(<QuickPanel />);
  }, [setSecondaryPanel]);

  useEffect(() => {
    loadBounty();
  }, [id]);

  const claimBounty = async () => {
    try {
      await api.post(`/bounties/${id}/claim`);
      toast.success("Bounty claimed.");
      loadBounty();
    } catch (error) {
      toast.error("Unable to claim bounty.");
    }
  };

  const addUpdate = async () => {
    try {
      const response = await api.post(`/bounties/${id}/updates`, {
        type: "comment",
        content: comment,
      });
      setUpdates((prev) => [...prev, response.data.update]);
      setComment("");
    } catch (error) {
      toast.error("Unable to add update.");
    }
  };

  const updateStatus = async () => {
    try {
      await api.post(`/bounties/${id}/status`, { status });
      toast.success("Status updated.");
      loadBounty();
    } catch (error) {
      toast.error("Unable to update status.");
    }
  };

  if (!bounty) {
    return (
      <div className="flex h-full items-center justify-center text-zinc-500" data-testid="bounty-detail-loading">
        Loading bounty...
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col" data-testid="bounty-detail-page">
      <div className="border-b border-zinc-800 bg-zinc-950/70 px-6 py-4">
        <button
          onClick={() => navigate("/app/bounties")}
          className="text-xs uppercase tracking-[0.3em] text-zinc-500"
          data-testid="bounty-detail-back"
        >
          Back to board
        </button>
        <div className="mt-2 flex items-center justify-between">
          <div>
            <div className="text-lg font-semibold" data-testid="bounty-detail-title">
              {bounty.title}
            </div>
            <div className="mt-1 text-xs text-zinc-500" data-testid="bounty-detail-id">
              {bounty.id}
            </div>
          </div>
          <Badge
            className="rounded-none border border-amber-500/30 bg-amber-500/10 text-amber-300"
            data-testid="bounty-detail-status"
          >
            {bounty.status}
          </Badge>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
          <div className="space-y-6">
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5">
              <div className="text-sm font-semibold">Description</div>
              <p className="mt-2 text-sm text-zinc-400" data-testid="bounty-detail-description">
                {bounty.description}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {(bounty.tags || []).map((tag) => (
                  <span
                    key={tag}
                    className="rounded-none border border-cyan-500/20 px-2 py-1 text-[10px] uppercase text-cyan-300"
                    data-testid={`bounty-detail-tag-${tag}`}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>

            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5">
              <div className="text-sm font-semibold">Updates</div>
              <div className="mt-4 space-y-3" data-testid="bounty-updates-list">
                {updates.map((update) => (
                  <div
                    key={update.id}
                    className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3"
                    data-testid={`bounty-update-${update.id}`}
                  >
                    <div className="text-xs text-zinc-500">{update.type}</div>
                    <div className="mt-2 text-sm text-zinc-200">{update.content}</div>
                  </div>
                ))}
                {updates.length === 0 && (
                  <div className="text-xs text-zinc-500" data-testid="bounty-updates-empty">
                    No updates yet.
                  </div>
                )}
              </div>
              <div className="mt-4 flex gap-2">
                <Input
                  placeholder="Leave a comment"
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  className="rounded-none border-zinc-800 bg-zinc-950"
                  data-testid="bounty-comment-input"
                />
                <Button
                  onClick={addUpdate}
                  className="rounded-none bg-cyan-500 text-black hover:bg-cyan-400"
                  data-testid="bounty-comment-submit"
                >
                  Post
                </Button>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5">
              <div className="text-sm font-semibold">Status control</div>
              <select
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                className="mt-3 w-full rounded-none border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200"
                data-testid="bounty-status-input"
              >
                <option value="open">Open</option>
                <option value="claimed">Claimed</option>
                <option value="submitted">Submitted</option>
                <option value="approved">Approved</option>
                <option value="cancelled">Cancelled</option>
              </select>
              <Button
                onClick={updateStatus}
                className="mt-3 w-full rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
                data-testid="bounty-status-submit"
              >
                Update status
              </Button>
            </div>
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-5">
              <div className="text-sm font-semibold">Claim bounty</div>
              <p className="mt-2 text-xs text-zinc-500">Only open bounties can be claimed.</p>
              <Button
                onClick={claimBounty}
                className="mt-3 w-full rounded-none border border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
                variant="outline"
                data-testid="bounty-claim-button"
              >
                Claim as user
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
