import React, { useEffect } from "react";
import { useLayout } from "@/components/layout/AppShell";
import { QuickPanel } from "@/components/layout/QuickPanel";
import { ModerationConsole } from "@/components/admin/ModerationConsole";
import { useAuth } from "@/context/AuthContext";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";

export default function Moderation() {
  const { setSecondaryPanel } = useLayout();
  const { user } = useAuth();

  useEffect(() => {
    setSecondaryPanel(<QuickPanel />);
  }, [setSecondaryPanel]);

  return (
    <div className="flex h-full flex-col" data-testid="moderation-page">
      <div className="flex-1 overflow-y-auto p-6">
        <AdminPageHeader
          eyebrow="Moderation"
          title="Trust and safety review"
          description="Review flagged content, resolve queue items, and apply actor actions without mixing that work into system ops."
          adminNote={`Admin only · ${user?.email}`}
          meta="Queue triage • review workflow • actor actions"
        />
        <div className="mt-6">
          <ModerationConsole />
        </div>
      </div>
    </div>
  );
}
