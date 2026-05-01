import React from "react";

export function AdminStatusCards({ items, testId = "admin-status-cards" }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2" data-testid={testId}>
      {items.map((item) => (
        <div
          key={item.id}
          className={`rounded-none border p-4 ${
            item.ok
              ? "border-emerald-500/20 bg-emerald-500/5"
              : "border-amber-500/20 bg-amber-500/5"
          }`}
          data-testid={`${testId}-${item.id}`}
        >
          <div className="text-xs font-mono uppercase tracking-[0.24em] text-zinc-500">
            {item.eyebrow || "Status"}
          </div>
          <div className="mt-2 text-sm font-semibold text-zinc-100">{item.label}</div>
          <div className="mt-2 text-xs text-zinc-400">{item.detail}</div>
        </div>
      ))}
    </div>
  );
}
