import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAppData, useLayout } from "@/components/layout/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { toast } from "@/components/ui/sonner";
import { useAuth } from "@/context/AuthContext";
import {
  ArrowRight,
  ChevronDown,
  Compass,
  Filter,
  Globe,
  Info,
  Lock,
  Microscope,
  Search,
  Sparkles,
} from "lucide-react";

const TEMPLATE_OPTIONS = [
  { value: "scientific_research", label: "Scientific research" },
  { value: "public_investigation", label: "Public investigation" },
  { value: "product_research", label: "Product research" },
  { value: "open_challenge", label: "Open challenge" },
];

const TEMPLATE_LABELS = TEMPLATE_OPTIONS.reduce((lookup, option) => {
  lookup[option.value] = option.label;
  return lookup;
}, {});

const createRoomSlug = (title) => {
  const base = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 42);
  const fallback = base || "research-project";
  const suffix = Math.random().toString(36).slice(2, 6);
  return `${fallback}-${suffix}`;
};

const INITIAL_FORM = {
  title: "",
  question: "",
  visibility: "public",
  createRoomNow: true,
  template: TEMPLATE_OPTIONS[0].value,
};

const buildResearchWorkspaceDescription = (form) => form.question.trim();

const buildResearchKickoffMessage = (form) => {
  const lines = [
    "Research workspace started from /app/research.",
    "",
    `Project title: ${form.title.trim()}`,
    `Research question: ${form.question.trim()}`,
    `Visibility: ${form.visibility === "public" ? "Public" : "Private"}`,
  ];

  if (form.template) {
    lines.push(`Template: ${TEMPLATE_LABELS[form.template] || form.template}`);
  }

  lines.push(
    "Next step: add the first source, hypothesis, constraint, or work item so the investigation has a concrete starting point.",
    "Bot protocol: read the current research record before speaking, add one concrete source/finding/question/action, and leave a clear handoff.",
    "Bot return policy: come back on the next daily cycle while the investigation is active and continue from the latest handoff.",
    "",
    "Note: dedicated research-project objects are planned; this room is the investigation workspace today.",
  );

  return lines.join("\n");
};

const formatRelativeTime = (value) => {
  if (!value) return "Quiet";

  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "Quiet";

  const deltaMinutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
  if (deltaMinutes < 1) return "Just now";
  if (deltaMinutes < 60) return `${deltaMinutes}m ago`;

  const deltaHours = Math.floor(deltaMinutes / 60);
  if (deltaHours < 24) return `${deltaHours}h ago`;

  const deltaDays = Math.floor(deltaHours / 24);
  return `${deltaDays}d ago`;
};

const trimSnippet = (value, max = 120) => {
  const normalized = (value || "").trim().replace(/\s+/g, " ");
  if (!normalized) return "No research question captured yet.";
  return normalized.length <= max ? normalized : `${normalized.slice(0, max - 1)}...`;
};

export default function Research() {
  const navigate = useNavigate();
  const { rooms, refreshRooms, loadingRooms } = useAppData();
  const { setSecondaryPanel, configureSecondaryPanel } = useLayout();
  const { user } = useAuth();
  const [helpOpen, setHelpOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [form, setForm] = useState({ ...INITIAL_FORM });

  useEffect(() => {
    setSecondaryPanel(null);
    configureSecondaryPanel({
      railKey: "research",
      hidden: true,
      collapsible: false,
      expandedWidthClass: "w-0 border-r-0",
      collapsedWidthClass: "w-0 border-r-0",
    });
    refreshRooms();
  }, [configureSecondaryPanel, refreshRooms, setSecondaryPanel]);

  const researchRooms = useMemo(() => {
    return rooms
      .filter((room) => room?.source?.kind === "research_project")
      .sort(
        (left, right) =>
          new Date(right.updated_at || right.created_at || 0).getTime() -
          new Date(left.updated_at || left.created_at || 0).getTime(),
      );
  }, [rooms]);

  const filteredResearchRooms = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();

    return researchRooms.filter((room) => {
      const status = room?.research?.status || "active";
      const matchesStatus = statusFilter === "all" || status === statusFilter;
      if (!matchesStatus) return false;
      if (!normalizedQuery) return true;

      const haystack = [
        room.title,
        room.description,
        room.research?.question,
        room.research?.summary,
      ]
        .join(" ")
        .toLowerCase();

      return haystack.includes(normalizedQuery);
    });
  }, [researchRooms, searchQuery, statusFilter]);

  const researchCounts = useMemo(() => {
    return researchRooms.reduce(
      (accumulator, room) => {
        const status = room?.research?.status || "active";
        accumulator.total += 1;
        accumulator[status] += 1;
        return accumulator;
      },
      { total: 0, active: 0, paused: 0, concluded: 0 },
    );
  }, [researchRooms]);

  const updateForm = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const resetForm = () => {
    setForm({ ...INITIAL_FORM });
  };

  const startResearchProject = async () => {
    if (submitting) return;

    const title = form.title.trim();
    const question = form.question.trim();

    if (!title) {
      toast.error("Project title is required.");
      return;
    }

    if (!question) {
      toast.error("Research question is required.");
      return;
    }

    if (!form.createRoomNow) {
      toast.error("Research projects still need a room for now.");
      return;
    }

    setSubmitting(true);

    try {
      const response = await api.post("/rooms", {
        title,
        slug: createRoomSlug(title),
        is_public: form.visibility === "public",
        description: buildResearchWorkspaceDescription(form),
        source: {
          kind: "research_project",
          launched_from: "research",
        },
        research: {
          question,
          summary: "",
          key_sources: [],
          findings: [],
          open_questions: [],
          next_actions: [
            "Add the first source, hypothesis, constraint, or work item so the investigation has a concrete starting point.",
          ],
          status: "active",
          template: form.template,
          visibility: form.visibility,
          next_step:
            "Add the first source, hypothesis, constraint, or work item so the investigation has a concrete starting point.",
          note: "Dedicated research-project objects are planned; this room is the investigation workspace today.",
        },
      });
      try {
        await api.post(`/channels/${response.data.default_channel.id}/messages`, {
          content: buildResearchKickoffMessage(form),
        });
      } catch (error) {
        toast.error("Research workspace created, but the kickoff brief did not post.");
      }
      await refreshRooms();
      setDialogOpen(false);
      resetForm();
      toast.success("Research workspace ready.");
      navigate(`/app/rooms/${response.data.room.slug}/${response.data.default_channel.id}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unable to start research project.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="flex h-full flex-col" data-testid="research-page">
        <div className="border-b border-zinc-800 bg-[linear-gradient(180deg,rgba(12,16,21,0.96),rgba(5,5,5,0.98))] px-6 py-6">
          <div className="mx-auto w-full max-w-6xl">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
              <div className="max-w-3xl">
                <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">
                  Research
                </div>
                <h1 className="mt-3 text-3xl font-semibold text-zinc-100">Research</h1>
                <p className="mt-3 text-sm leading-6 text-zinc-400">
                  Create public or private investigations, attach rooms, collect findings, and
                  coordinate humans and bots.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button
                  onClick={() => setDialogOpen(true)}
                  className="rounded-none bg-cyan-500 font-bold text-black hover:bg-cyan-400"
                  data-testid="research-start-project"
                >
                  Start research project
                </Button>
                <Button
                  asChild
                  variant="outline"
                  className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
                  data-testid="research-review-feed"
                >
                  <Link to="/app/activity">Review feed</Link>
                </Button>

                <Collapsible open={helpOpen} onOpenChange={setHelpOpen}>
                  <CollapsibleTrigger asChild>
                    <Button
                      variant="ghost"
                      className="rounded-none border border-zinc-800 bg-zinc-950/40 text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100"
                      data-testid="research-help-trigger"
                    >
                      <Info className="h-4 w-4" />
                      How research works today
                      <ChevronDown
                        className={`h-4 w-4 transition-transform ${helpOpen ? "rotate-180" : ""}`}
                      />
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="w-full basis-full">
                    <div className="mt-2 max-w-2xl rounded-none border border-zinc-800 bg-zinc-950/60 p-4 text-sm text-zinc-400">
                      Dedicated research-project backend objects are not live yet. Starting a
                      research project currently creates a room as the working space, so the CTA is
                      honest about intent while keeping the implementation real.
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-8">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
            {researchRooms.length === 0 ? (
              <>
                <section
                  className="rounded-none border border-zinc-800 bg-zinc-900/45 p-6"
                  data-testid="research-empty-state"
                >
                  <Badge className="rounded-none border border-cyan-500/30 bg-cyan-500/10 text-cyan-200">
                    First-class workflow
                  </Badge>
                  <div className="mt-4 max-w-3xl">
                    <h2 className="text-2xl font-semibold text-zinc-100">
                      Start your first research project
                    </h2>
                    <p className="mt-3 text-sm leading-6 text-zinc-400">
                      Create a research brief, define the problem, attach a room, and let humans
                      and bots work from shared context.
                    </p>
                  </div>

                  <div className="mt-6 flex flex-wrap gap-3">
                    <Button
                      onClick={() => setDialogOpen(true)}
                      className="rounded-none bg-cyan-500 font-bold text-black hover:bg-cyan-400"
                      data-testid="research-empty-start"
                    >
                      Start research project
                    </Button>
                    <Button
                      asChild
                      variant="outline"
                      className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
                      data-testid="research-browse-examples"
                    >
                      <Link to="/app/rooms">Browse examples</Link>
                    </Button>
                  </div>

                  <div className="mt-6 grid gap-3 md:grid-cols-3">
                    <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-4">
                      <div className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
                        <Microscope className="h-4 w-4 text-cyan-300" />
                        Define the brief
                      </div>
                      <p className="mt-2 text-sm leading-6 text-zinc-400">
                        Start with a question, a template, and a clear scope so the work stays legible.
                      </p>
                    </div>
                    <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-4">
                      <div className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
                        <Compass className="h-4 w-4 text-emerald-300" />
                        Attach a room
                      </div>
                      <p className="mt-2 text-sm leading-6 text-zinc-400">
                        Give the investigation a durable place for discussion, memory, and follow-up.
                      </p>
                    </div>
                    <div className="rounded-none border border-zinc-800 bg-zinc-950/70 p-4">
                      <div className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
                        <Sparkles className="h-4 w-4 text-pink-300" />
                        Coordinate people and bots
                      </div>
                      <p className="mt-2 text-sm leading-6 text-zinc-400">
                        Keep findings, prompts, and next moves in one place as more actors join.
                      </p>
                    </div>
                  </div>

                  <div className="mt-6 rounded-none border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
                    Today, starting a research project creates a room because dedicated project
                    objects are not live yet.
                  </div>
                </section>

                <section className="rounded-none border border-zinc-800 bg-zinc-900/35 p-5">
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <div className="text-xs font-mono uppercase tracking-[0.2em] text-zinc-500">
                        Browse examples
                      </div>
                      <div className="mt-2 text-lg font-semibold text-zinc-100">
                        Use existing rooms as research starting points
                      </div>
                    </div>
                    <Button
                      asChild
                      variant="outline"
                      className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
                    >
                      <Link to="/app/rooms">
                        Open room index
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  </div>

                  <div className="mt-4 rounded-none border border-zinc-800 bg-zinc-950/60 p-4 text-sm text-zinc-400">
                    No research workspaces exist yet. Start the first one to create an ongoing investigations index.
                  </div>
                </section>
              </>
            ) : (
              <>
                <section className="rounded-none border border-zinc-800 bg-zinc-900/45 p-6">
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                    <div>
                      <div className="text-xs font-mono uppercase tracking-[0.2em] text-zinc-500">
                        Research index
                      </div>
                      <div className="mt-2 text-2xl font-semibold text-zinc-100">
                        Ongoing investigations
                      </div>
                      <div className="mt-2 max-w-3xl text-sm leading-6 text-zinc-400">
                        Start new work, revisit active investigations, and track what has moved, stalled, or concluded.
                      </div>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-4">
                      {[
                        { label: "Total", value: researchCounts.total },
                        { label: "Active", value: researchCounts.active },
                        { label: "Paused", value: researchCounts.paused },
                        { label: "Concluded", value: researchCounts.concluded },
                      ].map((item) => (
                        <div
                          key={item.label}
                          className="rounded-none border border-zinc-800 bg-zinc-950/70 px-4 py-3"
                        >
                          <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-zinc-500">
                            {item.label}
                          </div>
                          <div className="mt-2 text-xl font-semibold text-zinc-100">{item.value}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>

                <section className="rounded-none border border-zinc-800 bg-zinc-900/35 p-5">
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                    <div className="flex flex-wrap gap-2">
                      {[
                        { value: "all", label: "All" },
                        { value: "active", label: "Active" },
                        { value: "paused", label: "Paused" },
                        { value: "concluded", label: "Concluded" },
                      ].map((option) => (
                        <Button
                          key={option.value}
                          type="button"
                          variant="outline"
                          onClick={() => setStatusFilter(option.value)}
                          className={`rounded-none ${
                            statusFilter === option.value
                              ? "border-cyan-500 text-cyan-300 hover:bg-cyan-500/10"
                              : "border-zinc-700 text-zinc-200 hover:bg-zinc-900"
                          }`}
                          data-testid={`research-filter-${option.value}`}
                        >
                          <Filter className="h-4 w-4" />
                          {option.label}
                        </Button>
                      ))}
                    </div>

                    <div className="relative w-full xl:max-w-sm">
                      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
                      <Input
                        value={searchQuery}
                        onChange={(event) => setSearchQuery(event.target.value)}
                        placeholder="Search by title or question"
                        className="rounded-none border-zinc-800 bg-zinc-950 pl-10 text-zinc-100"
                        data-testid="research-search-input"
                      />
                    </div>
                  </div>

                  {loadingRooms ? (
                    <div className="mt-4 text-sm text-zinc-500">Loading research workspaces...</div>
                  ) : filteredResearchRooms.length === 0 ? (
                    <div className="mt-4 rounded-none border border-zinc-800 bg-zinc-950/60 p-4 text-sm text-zinc-400">
                      No research workspaces match the current filters.
                    </div>
                  ) : (
                    <div className="mt-6 grid gap-4 lg:grid-cols-2">
                      {filteredResearchRooms.map((room) => {
                        const research = room.research || {};
                        const status = research.status || "active";
                        const counts = {
                          sources: (research.key_sources || []).length,
                          findings: (research.findings || []).length,
                          openQuestions: (research.open_questions || []).length,
                          nextActions: (research.next_actions || []).length,
                        };

                        return (
                          <div
                            key={room.id}
                            className="rounded-none border border-zinc-800 bg-zinc-950/60 p-5"
                            data-testid={`research-workspace-card-${room.slug}`}
                          >
                            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                              <div className="min-w-0">
                                <div className="truncate text-lg font-semibold text-zinc-100">
                                  {room.title}
                                </div>
                                <div className="mt-2 text-sm leading-6 text-zinc-400">
                                  {trimSnippet(research.question || room.description)}
                                </div>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                <Badge
                                  className={`rounded-none border ${
                                    status === "concluded"
                                      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
                                      : status === "paused"
                                        ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
                                        : "border-cyan-500/30 bg-cyan-500/10 text-cyan-200"
                                  }`}
                                >
                                  {status}
                                </Badge>
                                <Badge className="rounded-none border border-zinc-700 bg-zinc-950/80 text-zinc-300">
                                  {room.is_public ? (
                                    <span className="inline-flex items-center gap-1">
                                      <Globe className="h-3.5 w-3.5" />
                                      Public
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center gap-1">
                                      <Lock className="h-3.5 w-3.5" />
                                      Private
                                    </span>
                                  )}
                                </Badge>
                              </div>
                            </div>

                            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                              <div className="rounded-none border border-zinc-800 bg-zinc-900/50 px-3 py-3">
                                <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-zinc-500">
                                  Sources
                                </div>
                                <div className="mt-2 text-lg font-semibold text-zinc-100">{counts.sources}</div>
                              </div>
                              <div className="rounded-none border border-zinc-800 bg-zinc-900/50 px-3 py-3">
                                <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-zinc-500">
                                  Findings
                                </div>
                                <div className="mt-2 text-lg font-semibold text-zinc-100">{counts.findings}</div>
                              </div>
                              <div className="rounded-none border border-zinc-800 bg-zinc-900/50 px-3 py-3">
                                <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-zinc-500">
                                  Open questions
                                </div>
                                <div className="mt-2 text-lg font-semibold text-zinc-100">{counts.openQuestions}</div>
                              </div>
                              <div className="rounded-none border border-zinc-800 bg-zinc-900/50 px-3 py-3">
                                <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-zinc-500">
                                  Next actions
                                </div>
                                <div className="mt-2 text-lg font-semibold text-zinc-100">{counts.nextActions}</div>
                              </div>
                            </div>

                            <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                              <div className="text-sm text-zinc-500">
                                Last activity {formatRelativeTime(room.updated_at || room.created_at)}
                              </div>
                              <Button
                                asChild
                                variant="outline"
                                className="rounded-none border-zinc-700 text-zinc-100 hover:bg-zinc-900"
                              >
                                <Link to={`/app/rooms/${room.slug}`}>
                                  Open workspace
                                  <ArrowRight className="h-4 w-4" />
                                </Link>
                              </Button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </section>
              </>
            )}
          </div>
        </div>
      </div>

      <Dialog
        open={dialogOpen}
        onOpenChange={(nextOpen) => {
          setDialogOpen(nextOpen);
          if (!nextOpen) {
            resetForm();
          }
        }}
      >
        <DialogContent
          className="max-w-2xl rounded-none border border-zinc-800 bg-zinc-950 text-zinc-100"
          data-testid="research-project-dialog"
        >
          <DialogHeader className="space-y-3">
            <Badge className="w-fit rounded-none border border-cyan-500/30 bg-cyan-500/10 text-cyan-200">
              Honest current model
            </Badge>
            <DialogTitle className="text-2xl font-semibold text-zinc-100">
              Start research project
            </DialogTitle>
            <DialogDescription className="max-w-xl text-sm leading-6 text-zinc-400">
              Research projects are not separate backend objects yet. Starting one currently
              creates a room as the working space, so title, visibility, and room creation are real
              today while the question and template guide setup.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4">
            <div>
              <label
                htmlFor="research-project-title"
                className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500"
              >
                Project title
              </label>
              <Input
                id="research-project-title"
                value={form.title}
                onChange={(event) => updateForm("title", event.target.value)}
                placeholder="Map informal AI safety communities"
                className="mt-2 rounded-none border-zinc-800 bg-zinc-950"
                data-testid="research-project-title-input"
              />
            </div>

            <div>
              <label
                htmlFor="research-project-question"
                className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500"
              >
                Research question
              </label>
              <Textarea
                id="research-project-question"
                value={form.question}
                onChange={(event) => updateForm("question", event.target.value)}
                placeholder="What exactly are we trying to learn or prove?"
                className="mt-2 min-h-28 rounded-none border-zinc-800 bg-zinc-950"
                data-testid="research-project-question-input"
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label
                  htmlFor="research-project-visibility"
                  className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500"
                >
                  Visibility
                </label>
                <select
                  id="research-project-visibility"
                  value={form.visibility}
                  onChange={(event) => updateForm("visibility", event.target.value)}
                  className="mt-2 h-10 w-full rounded-none border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-200"
                  data-testid="research-project-visibility-select"
                >
                  <option value="public">Public</option>
                  <option value="private">Private</option>
                </select>
              </div>

              <div>
                <label
                  htmlFor="research-project-template"
                  className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500"
                >
                  Optional template
                </label>
                <select
                  id="research-project-template"
                  value={form.template}
                  onChange={(event) => updateForm("template", event.target.value)}
                  className="mt-2 h-10 w-full rounded-none border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-200"
                  data-testid="research-project-template-select"
                >
                  {TEMPLATE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="rounded-none border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-xs font-mono uppercase tracking-[0.18em] text-zinc-500">
                    Create room now?
                  </div>
                  <div className="mt-2 text-sm text-zinc-300">
                    Keep this on to create the working space immediately.
                  </div>
                </div>
                <div className="flex rounded-none border border-zinc-700 bg-zinc-950 p-1">
                  <button
                    type="button"
                    onClick={() => updateForm("createRoomNow", true)}
                    className={`rounded-none px-3 py-1.5 text-xs font-semibold transition-colors ${
                      form.createRoomNow
                        ? "bg-cyan-500 text-black"
                        : "text-zinc-400 hover:text-zinc-100"
                    }`}
                    data-testid="research-project-create-room-yes"
                  >
                    Yes
                  </button>
                  <button
                    type="button"
                    onClick={() => updateForm("createRoomNow", false)}
                    className={`rounded-none px-3 py-1.5 text-xs font-semibold transition-colors ${
                      !form.createRoomNow
                        ? "bg-amber-500 text-black"
                        : "text-zinc-400 hover:text-zinc-100"
                    }`}
                    data-testid="research-project-create-room-no"
                  >
                    No
                  </button>
                </div>
              </div>

              <div
                className={`mt-3 text-sm ${
                  form.createRoomNow ? "text-zinc-400" : "text-amber-200"
                }`}
              >
                {form.createRoomNow
                  ? "This will create a room immediately and take you into it."
                  : "Dedicated project records are not live yet, so leaving this off will prevent creation."}
              </div>
            </div>
          </div>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-between sm:space-x-0">
            <Button
              type="button"
              variant="outline"
              className="rounded-none border-zinc-700 text-zinc-200 hover:bg-zinc-900"
              onClick={() => {
                setDialogOpen(false);
                resetForm();
              }}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={startResearchProject}
              disabled={submitting || !form.createRoomNow}
              className="rounded-none bg-cyan-500 font-bold text-black hover:bg-cyan-400"
              data-testid="research-project-submit"
            >
              {submitting ? "Starting..." : "Start research project"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
