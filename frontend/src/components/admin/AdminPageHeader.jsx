import React from "react";

export function AdminPageHeader({
  eyebrow,
  title,
  description,
  adminNote,
  meta,
  actions = null,
  titleTestId,
}) {
  return (
    <>
      <div className="border-b border-zinc-800 bg-zinc-950/70 px-6 py-5">
        <div className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-500">{eyebrow}</div>
        <div className="mt-1 text-lg font-semibold" data-testid={titleTestId}>
          {title}
        </div>
        {description && <div className="mt-2 max-w-2xl text-sm text-zinc-400">{description}</div>}
      </div>

      <div className="flex flex-col gap-3 border-b border-zinc-900 pb-6 md:flex-row md:items-center md:justify-between">
        <div>
          {adminNote && <div className="text-xs text-zinc-500">{adminNote}</div>}
          {meta && <div className="mt-1 text-xs uppercase tracking-[0.24em] text-zinc-600">{meta}</div>}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
    </>
  );
}
