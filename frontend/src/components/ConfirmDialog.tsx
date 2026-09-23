"use client";

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  pendingLabel?: string;
  isPending?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

// Modal for destructive actions. Styled like the "Create New Project" modal on the dashboard.
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Delete",
  pendingLabel = "Deleting...",
  isPending = false,
  error,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isPending) onCancel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, isPending, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4"
      onClick={() => !isPending && onCancel()}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        onClick={(e) => e.stopPropagation()}
        className="bg-white dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 max-w-md w-full p-6 rounded-2xl shadow-2xl space-y-4"
      >
        <div className="flex items-start gap-3">
          <span className="p-2.5 bg-red-100 dark:bg-red-950/60 text-red-600 dark:text-red-400 rounded-xl border border-red-200 dark:border-red-900/50 shrink-0">
            <AlertTriangle className="w-5 h-5" />
          </span>
          <div>
            <h3 id="confirm-dialog-title" className="text-lg font-bold text-slate-900 dark:text-white">
              {title}
            </h3>
            <div className="text-slate-500 dark:text-zinc-400 text-sm mt-1">{message}</div>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800/50 p-3 rounded-xl text-xs text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        <div className="flex items-center justify-end space-x-3 pt-4 border-t border-stone-200 dark:border-zinc-800">
          <button
            type="button"
            onClick={onCancel}
            disabled={isPending}
            autoFocus
            className="px-4 py-2 text-slate-500 dark:text-zinc-400 hover:text-slate-800 dark:hover:text-zinc-200 text-sm font-medium transition disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isPending}
            className="px-5 py-2 bg-red-600 hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600 text-white text-sm font-semibold rounded-xl transition disabled:opacity-50 shadow-xs"
          >
            {isPending ? pendingLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
