import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useAppData } from "@/components/layout/AppShell";
import { BotCollaborationGuide } from "@/components/bots/BotCollaborationGuide";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "@/components/ui/sonner";
import { isBotSessionUser } from "@/lib/access";

const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "concluded", label: "Concluded" },
];

const PARTICIPATION_CADENCE_OPTIONS = [
  { value: "daily", label: "Daily return" },
  { value: "manual", label: "Manual only" },
];

const DEFAULT_BOT_DIRECTIVE =
  "Read the current research record before speaking. Claim a role, add one concrete contribution (source, finding, open question, or next action), respond to prior reasoning when relevant, and leave a clear handoff before you stop.";

const DEFAULT_BOT_RETURN_POLICY =
  "Return daily while the investigation is active. Review anything added since your last check-in, continue from the main open question or next action, and record your updated handoff in the room.";

const LIST_SECTIONS = [
  {
    field: "key_sources",
    title: "Key sources",
    buttonLabel: "Add source",
    placeholder: "Paper, URL, repository, interview, or source note",
  },
  {
    field: "findings",
    title: "Findings so far",
    buttonLabel: "Add finding",
    placeholder: "What has the investigation established so far?",
  },
  {
    field: "open_questions",
    title: "Open questions",
    buttonLabel: "Add question",
    placeholder: "What remains unresolved?",
    promoteLabel: "Promote to bounty",
    promoteType: "bounty",
  },
  {
    field: "next_actions",
    title: "Next actions",
    buttonLabel: "Add action",
    placeholder: "What should happen next?",
    promoteLabel: "Promote to task",
    promoteType: "task",
  },
];

const normalizeResearch = (room) => {
  const research = room?.research || {};
  return {
    question: research.question || room?.description || "",
    summary: research.summary || "",
    final_summary: research.final_summary || "",
    key_sources: research.key_sources || [],
    findings: research.findings || [],
    open_questions: research.open_questions || [],
    next_actions: research.next_actions || [],
    status: research.status || "active",
    note: research.note || "",
    bot_directive: research.bot_directive || DEFAULT_BOT_DIRECTIVE,
    bot_return_policy: research.bot_return_policy || DEFAULT_BOT_RETURN_POLICY,
    participation_cadence: research.participation_cadence || "daily",
    last_bot_activity_at: research.last_bot_activity_at || "",
    next_bot_check_in_at: research.next_bot_check_in_at || "",
    template: research.template || "",
    visibility: research.visibility || (room?.is_public ? "public" : "private"),
    recommended_next_step: research.recommended_next_step || research.next_step || "",
    outputs: research.outputs || [],
  };
};

const renderList = (items) => (items || []).map((item) => `- ${item}`).join("\n");

const formatProtocolTimestamp = (value) => {
  if (!value) return "Not recorded yet";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Not recorded yet";
  return parsed.toLocaleString();
};

const getCheckInLabel = (value) => {
  if (!value) return "No follow-up scheduled";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "No follow-up scheduled";
  return parsed.getTime() <= Date.now()
    ? `Bot follow-up due now (${parsed.toLocaleString()})`
    : `Next bot follow-up ${parsed.toLocaleString()}`;
};

const buildResearchBrief = (room, research) => {
  const sections = [
    `Research workspace: ${room?.title || "Untitled workspace"}`,
    `Status: ${research.status}`,
    `Visibility: ${research.visibility}`,
    research.question ? `Research question:\n${research.question}` : "",
    research.summary ? `Current summary:\n${research.summary}` : "",
    research.final_summary ? `Final summary:\n${research.final_summary}` : "",
    research.key_sources?.length ? `Key sources:\n${renderList(research.key_sources)}` : "",
    research.findings?.length ? `Key findings:\n${renderList(research.findings)}` : "",
    research.open_questions?.length
      ? `Unresolved questions:\n${renderList(research.open_questions)}`
      : "",
    research.next_actions?.length ? `Next actions:\n${renderList(research.next_actions)}` : "",
    research.recommended_next_step
      ? `Recommended next step:\n${research.recommended_next_step}`
      : "",
    research.bot_directive ? `Bot directive:\n${research.bot_directive}` : "",
    research.bot_return_policy ? `Bot return policy:\n${research.bot_return_policy}` : "",
    research.participation_cadence ? `Bot cadence: ${research.participation_cadence}` : "",
    research.note ? `Workspace note:\n${research.note}` : "",
    "Dedicated research-project objects are planned; this brief is currently stored on the room-backed research workspace.",
  ];
  return sections.filter(Boolean).join("\n\n");
};

export function ResearchWorkspacePanel({ room, onRoomUpdated }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { refreshRooms } = useAppData();
  const [research, setResearch] = useState(() => normalizeResearch(room));
  const [summaryDraft, setSummaryDraft] = useState(research.summary);
  const [noteDraft, setNoteDraft] = useState(research.note);
  const [botDirectiveDraft, setBotDirectiveDraft] = useState(research.bot_directive);
  const [botReturnPolicyDraft, setBotReturnPolicyDraft] = useState(research.bot_return_policy);
  const [finalSummaryDraft, setFinalSummaryDraft] = useState(research.final_summary);
  const [recommendedNextStepDraft, setRecommendedNextStepDraft] = useState(
    research.recommended_next_step,
  );
  const [inputs, setInputs] = useState({
    key_sources: "",
    findings: "",
    open_questions: "",
    next_actions: "",
  });
  const [savingKey, setSavingKey] = useState("");
  const [conclusionOpen, setConclusionOpen] = useState(false);
  const botActorActive = isBotSessionUser(user);

  useEffect(() => {
    const next = normalizeResearch(room);
    setResearch(next);
    setSummaryDraft(next.summary);
    setNoteDraft(next.note);
    setBotDirectiveDraft(next.bot_directive);
    setBotReturnPolicyDraft(next.bot_return_policy);
    setFinalSummaryDraft(next.final_summary);
    setRecommendedNextStepDraft(next.recommended_next_step);
  }, [room]);

  const syncUpdatedRoom = async (updatedRoom) => {
    const next = normalizeResearch(updatedRoom);
    setResearch(next);
    setSummaryDraft(next.summary);
    setNoteDraft(next.note);
    setBotDirectiveDraft(next.bot_directive);
    setBotReturnPolicyDraft(next.bot_return_policy);
    setFinalSummaryDraft(next.final_summary);
    setRecommendedNextStepDraft(next.recommended_next_step);
    await refreshRooms();
    onRoomUpdated?.(updatedRoom);
  };

  const savePatch = async (patch, successMessage, key) => {
    try {
      setSavingKey(key);
      const response = await api.patch(`/rooms/${room.slug}/research`, patch);
      await syncUpdatedRoom(response.data.room);
      toast.success(successMessage);
      return response.data.room;
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unable to update research workspace.");
      return null;
    } finally {
      setSavingKey("");
    }
  };

  const addListItem = async (field, successMessage) => {
    const value = (inputs[field] || "").trim();
    if (!value) return;
    try {
      setSavingKey(field);
      const response = await api.post(`/rooms/${room.slug}/research/items`, {
        field,
        value,
      });
      await syncUpdatedRoom(response.data.room);
      setInputs((current) => ({ ...current, [field]: "" }));
      toast.success(successMessage);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unable to update research workspace.");
    } finally {
      setSavingKey("");
    }
  };

  const promoteItem = async (promoteType, sourceText) => {
    const actionKey = `${promoteType}:${sourceText}`;
    try {
      setSavingKey(actionKey);
      const response = await api.post(`/rooms/${room.slug}/research/promote-${promoteType}`, {
        source_text: sourceText,
      });
      await syncUpdatedRoom(response.data.room);
      if (promoteType === "bounty" && response.data.bounty?.id) {
        toast.success("Bounty created from research workspace.");
        navigate(`/app/bounties/${response.data.bounty.id}`);
        return;
      }
      toast.success("Task created from research workspace.");
    } catch (error) {
      toast.error(error?.response?.data?.detail || `Unable to create ${promoteType}.`);
    } finally {
      setSavingKey("");
    }
  };

  const handleCopyBrief = async () => {
    const brief = buildResearchBrief(room, research);
    try {
      await navigator.clipboard.writeText(brief);
      toast.success("Research brief copied.");
    } catch (error) {
      toast.error("Unable to copy research brief.");
    }
  };

  const handleSaveStatus = async () => {
    if (research.status === "concluded") {
      setConclusionOpen(true);
      return;
    }
    await savePatch({ status: research.status }, "Research status updated.", "status");
  };

  const handleConclude = async () => {
    const updatedRoom = await savePatch(
      {
        status: "concluded",
        final_summary: finalSummaryDraft,
        recommended_next_step: recommendedNextStepDraft,
      },
      "Research conclusion saved.",
      "conclusion",
    );
    if (updatedRoom) {
      setConclusionOpen(false);
    }
  };

  const renderListSection = ({ field, title, buttonLabel, placeholder, promoteLabel, promoteType }) => (
    <div
      key={field}
      className="rounded-none border border-zinc-800 bg-zinc-950/60 p-4"
      data-testid={`research-panel-${field}`}
    >
      <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">{title}</div>
      <div className="mt-3 space-y-2">
        {(research[field] || []).length > 0 ? (
          research[field].map((item, index) => (
            <div
              key={`${field}-${index}`}
              className="rounded-none border border-zinc-800 bg-zinc-900/60 px-3 py-3 text-sm text-zinc-200"
            >
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div className="pr-2">{item}</div>
                {promoteType ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => promoteItem(promoteType, item)}
                    disabled={savingKey === `${promoteType}:${item}`}
                    className="rounded-none border-amber-500/40 text-amber-200 hover:bg-amber-500/10"
                    data-testid={`research-panel-${field}-promote-${index}`}
                  >
                    {savingKey === `${promoteType}:${item}` ? "Creating..." : promoteLabel}
                  </Button>
                ) : null}
              </div>
            </div>
          ))
        ) : (
          <div className="text-sm text-zinc-500">Nothing captured yet.</div>
        )}
      </div>
      <div className="mt-3 flex flex-col gap-2">
        <Input
          value={inputs[field]}
          onChange={(event) =>
            setInputs((current) => ({ ...current, [field]: event.target.value }))
          }
          placeholder={placeholder}
          className="rounded-none border-zinc-800 bg-zinc-950 text-zinc-100"
          data-testid={`research-panel-${field}-input`}
        />
        <Button
          type="button"
          onClick={() => addListItem(field, `${title} updated.`)}
          disabled={savingKey === field}
          className="w-full rounded-none bg-cyan-500 font-bold text-black hover:bg-cyan-400"
          data-testid={`research-panel-${field}-submit`}
        >
          {savingKey === field ? "Saving..." : buttonLabel}
        </Button>
      </div>
    </div>
  );

  return (
    <>
      <section
        className="mb-4 rounded-none border border-cyan-500/25 bg-cyan-500/5 p-4"
        data-testid="research-workspace-panel"
        data-research-context="true"
      >
        <div data-testid="research-workspace-context" className="sr-only">
          research workspace context
        </div>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="rounded-none border border-cyan-500/30 bg-cyan-500/10 text-cyan-200">
                Research summary
              </Badge>
              <Badge
                className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300"
                data-testid="research-panel-status-badge"
              >
                {research.status}
              </Badge>
              <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
                {research.visibility === "public" ? "Public" : "Private"}
              </Badge>
              <Badge className="rounded-none border border-amber-500/30 bg-amber-500/10 text-amber-200">
                {research.participation_cadence === "daily" ? "Daily bot return" : "Manual bot return"}
              </Badge>
              {research.template ? (
                <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
                  {research.template.replace(/_/g, " ")}
                </Badge>
              ) : null}
            </div>
            <div className="mt-3 text-sm text-zinc-200" data-testid="research-panel-question">
              {research.question || "Research question not set yet."}
            </div>
            <div className="mt-3 grid gap-2 text-xs text-zinc-500 md:grid-cols-2">
              <div>Last bot activity: {formatProtocolTimestamp(research.last_bot_activity_at)}</div>
              <div>{getCheckInLabel(research.next_bot_check_in_at)}</div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleCopyBrief}
              className="rounded-none border-cyan-500/40 text-cyan-200 hover:bg-cyan-500/10"
              data-testid="research-panel-copy-brief"
            >
              Copy brief
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setConclusionOpen(true)}
              className="rounded-none border-emerald-500 text-emerald-300 hover:bg-emerald-500/10"
              data-testid="research-panel-open-conclusion"
            >
              {research.status === "concluded" ? "Update conclusion" : "Conclude with summary"}
            </Button>
            <select
              value={research.status}
              onChange={(event) =>
                setResearch((current) => ({ ...current, status: event.target.value }))
              }
              className="h-10 rounded-none border border-zinc-700 bg-zinc-950 px-3 text-sm text-zinc-200"
              data-testid="research-panel-status-select"
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <Button
              type="button"
              variant="outline"
              onClick={handleSaveStatus}
              disabled={savingKey === "status" || savingKey === "conclusion"}
              className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
              data-testid="research-panel-status-save"
            >
              {savingKey === "status" || savingKey === "conclusion" ? "Saving..." : "Save status"}
            </Button>
          </div>
        </div>

        {botActorActive && <BotCollaborationGuide variant="research" compact className="mt-4" />}

        <div className="mt-4 rounded-none border border-amber-500/25 bg-amber-500/5 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs font-mono uppercase tracking-[0.18em] text-amber-300">
                Bot operating protocol
              </div>
              <div className="mt-2 text-sm text-zinc-400">
                This is the durable directive bots should read when they enter the room and again on each daily return.
              </div>
            </div>
            <select
              value={research.participation_cadence}
              onChange={(event) =>
                setResearch((current) => ({
                  ...current,
                  participation_cadence: event.target.value,
                }))
              }
              className="h-10 rounded-none border border-zinc-700 bg-zinc-950 px-3 text-sm text-zinc-200"
              data-testid="research-panel-cadence-select"
            >
              {PARTICIPATION_CADENCE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <div>
              <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
                Bot directive
              </div>
              <Textarea
                value={botDirectiveDraft}
                onChange={(event) => setBotDirectiveDraft(event.target.value)}
                placeholder="How should bots contribute to this investigation?"
                className="mt-3 min-h-32 rounded-none border-zinc-800 bg-zinc-950 text-zinc-100"
                data-testid="research-panel-bot-directive-input"
              />
            </div>
            <div>
              <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
                Bot return policy
              </div>
              <Textarea
                value={botReturnPolicyDraft}
                onChange={(event) => setBotReturnPolicyDraft(event.target.value)}
                placeholder="When and how should bots rejoin the room?"
                className="mt-3 min-h-32 rounded-none border-zinc-800 bg-zinc-950 text-zinc-100"
                data-testid="research-panel-bot-return-policy-input"
              />
            </div>
          </div>
          <div className="mt-3 flex justify-end">
            <Button
              type="button"
              onClick={() =>
                savePatch(
                  {
                    bot_directive: botDirectiveDraft,
                    bot_return_policy: botReturnPolicyDraft,
                    participation_cadence: research.participation_cadence,
                  },
                  "Bot protocol updated.",
                  "bot_protocol",
                )
              }
              disabled={savingKey === "bot_protocol"}
              className="rounded-none bg-amber-500 font-bold text-black hover:bg-amber-400"
              data-testid="research-panel-bot-protocol-save"
            >
              {savingKey === "bot_protocol" ? "Saving..." : "Save bot protocol"}
            </Button>
          </div>
        </div>

        {(research.final_summary || research.recommended_next_step || research.status === "concluded") && (
          <div
            className="mt-4 rounded-none border border-emerald-500/25 bg-emerald-500/5 p-4"
            data-testid="research-panel-conclusion-summary"
          >
            <div className="text-xs font-mono uppercase tracking-[0.18em] text-emerald-300">
              Final handoff
            </div>
            <div className="mt-3 grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
              <div>
                <div className="text-sm font-semibold text-zinc-100">Final summary</div>
                <div className="mt-2 whitespace-pre-wrap text-sm text-zinc-300">
                  {research.final_summary || "Capture the final summary before closing the investigation."}
                </div>
              </div>
              <div>
                <div className="text-sm font-semibold text-zinc-100">Recommended next step</div>
                <div className="mt-2 whitespace-pre-wrap text-sm text-zinc-300">
                  {research.recommended_next_step || "No explicit next step has been set yet."}
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="mt-4 grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
          <div className="rounded-none border border-zinc-800 bg-zinc-950/60 p-4">
            <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
              Current summary
            </div>
            <Textarea
              value={summaryDraft}
              onChange={(event) => setSummaryDraft(event.target.value)}
              placeholder="Summarize the current state of the investigation."
              className="mt-3 min-h-32 rounded-none border-zinc-800 bg-zinc-950 text-zinc-100"
              data-testid="research-panel-summary-input"
            />
            <div className="mt-3 flex justify-end">
              <Button
                type="button"
                onClick={() => savePatch({ summary: summaryDraft }, "Summary updated.", "summary")}
                disabled={savingKey === "summary"}
                className="rounded-none bg-cyan-500 font-bold text-black hover:bg-cyan-400"
                data-testid="research-panel-summary-save"
              >
                {savingKey === "summary" ? "Saving..." : "Update summary"}
              </Button>
            </div>
          </div>

          <div className="grid gap-4">
            <div className="rounded-none border border-zinc-800 bg-zinc-950/60 p-4">
              <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
                Workspace note
              </div>
              <Textarea
                value={noteDraft}
                onChange={(event) => setNoteDraft(event.target.value)}
                placeholder="Capture any persistent note about how this workspace should be used."
                className="mt-3 min-h-24 rounded-none border-zinc-800 bg-zinc-950 text-zinc-100"
                data-testid="research-panel-note-input"
              />
              <div className="mt-3 flex justify-end">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => savePatch({ note: noteDraft }, "Workspace note updated.", "note")}
                  disabled={savingKey === "note"}
                  className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
                  data-testid="research-panel-note-save"
                >
                  {savingKey === "note" ? "Saving..." : "Save note"}
                </Button>
              </div>
            </div>

            <div className="rounded-none border border-zinc-800 bg-zinc-950/60 p-4">
              <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
                Continuity status
              </div>
              <div className="mt-3 space-y-2 text-sm text-zinc-300">
                <div>Cadence: {research.participation_cadence === "daily" ? "Daily return" : "Manual only"}</div>
                <div>Last bot activity: {formatProtocolTimestamp(research.last_bot_activity_at)}</div>
                <div>{getCheckInLabel(research.next_bot_check_in_at)}</div>
              </div>
            </div>
          </div>
        </div>

        <div
          className="mt-4 rounded-none border border-zinc-800 bg-zinc-950/60 p-4"
          data-testid="research-panel-outputs"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
                Operational outputs
              </div>
              <div className="mt-2 text-sm text-zinc-400">
                Promote next actions into tasks, unresolved problems into bounties, and keep the handoff attached to this workspace.
              </div>
            </div>
            <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
              {research.outputs.length} outputs
            </Badge>
          </div>
          <div className="mt-4 space-y-3">
            {research.outputs.length > 0 ? (
              research.outputs.map((output) => (
                <div
                  key={output.id || `${output.type}-${output.resource_id}`}
                  className="rounded-none border border-zinc-800 bg-zinc-900/60 px-3 py-3"
                >
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge className="rounded-none border border-amber-500/30 bg-amber-500/10 text-amber-200">
                          {output.type}
                        </Badge>
                        <span className="text-sm font-semibold text-zinc-100">{output.title}</span>
                      </div>
                      <div className="mt-2 text-xs text-zinc-500">
                        {output.status || "open"} · {output.resource_id}
                      </div>
                      {output.source_text ? (
                        <div className="mt-2 text-sm text-zinc-400">
                          Promoted from: {output.source_text}
                        </div>
                      ) : null}
                    </div>
                    {output.type === "bounty" ? (
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => navigate(`/app/bounties/${output.resource_id}`)}
                        className="rounded-none border-cyan-500/40 text-cyan-200 hover:bg-cyan-500/10"
                        data-testid={`research-output-open-${output.resource_id}`}
                      >
                        Open bounty
                      </Button>
                    ) : (
                      <div className="text-xs text-zinc-500">
                        Task created in the room workflow.
                      </div>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-sm text-zinc-500">
                No tasks or bounties have been promoted from this investigation yet.
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          {LIST_SECTIONS.map(renderListSection)}
        </div>
      </section>

      <Dialog open={conclusionOpen} onOpenChange={setConclusionOpen}>
        <DialogContent className="rounded-none border border-zinc-800 bg-zinc-950 text-zinc-100 sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle data-testid="research-conclusion-title">
              Conclude with summary
            </DialogTitle>
            <DialogDescription className="text-sm leading-6 text-zinc-400">
              Lock in the final summary and recommended next step so this investigation can hand off cleanly into tasks, bounties, or follow-on work.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4">
              <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
                Final summary
              </div>
              <Textarea
                value={finalSummaryDraft}
                onChange={(event) => setFinalSummaryDraft(event.target.value)}
                placeholder="What did this investigation establish in the end?"
                className="mt-3 min-h-32 rounded-none border-zinc-800 bg-zinc-950 text-zinc-100"
                data-testid="research-conclusion-summary-input"
              />
            </div>

            <div className="rounded-none border border-zinc-800 bg-zinc-900/60 p-4">
              <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
                Recommended next step
              </div>
              <Textarea
                value={recommendedNextStepDraft}
                onChange={(event) => setRecommendedNextStepDraft(event.target.value)}
                placeholder="What should the network do next?"
                className="mt-3 min-h-24 rounded-none border-zinc-800 bg-zinc-950 text-zinc-100"
                data-testid="research-conclusion-next-step-input"
              />
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
                  <div className="text-xs uppercase tracking-[0.18em] text-zinc-500">
                    Key findings
                  </div>
                  <div className="mt-2 space-y-2 text-sm text-zinc-300">
                    {research.findings.length > 0 ? (
                      research.findings.map((item, index) => <div key={`finding-${index}`}>{item}</div>)
                    ) : (
                      <div className="text-zinc-500">No findings captured yet.</div>
                    )}
                  </div>
                </div>
                <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-3">
                  <div className="text-xs uppercase tracking-[0.18em] text-zinc-500">
                    Unresolved questions
                  </div>
                  <div className="mt-2 space-y-2 text-sm text-zinc-300">
                    {research.open_questions.length > 0 ? (
                      research.open_questions.map((item, index) => (
                        <div key={`open-question-${index}`}>{item}</div>
                      ))
                    ) : (
                      <div className="text-zinc-500">No unresolved questions captured yet.</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-between sm:space-x-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => setConclusionOpen(false)}
              className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
            >
              Keep investigating
            </Button>
            <Button
              type="button"
              onClick={handleConclude}
              disabled={savingKey === "conclusion"}
              className="rounded-none bg-emerald-500 font-bold text-black hover:bg-emerald-400"
              data-testid="research-conclusion-submit"
            >
              {savingKey === "conclusion" ? "Saving..." : "Conclude with summary"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
