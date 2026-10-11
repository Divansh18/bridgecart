import type { ReactNode } from "react";
import { useDialogKeyboard } from "@/lib/useDialogKeyboard";
import { AlertCircle, LoaderCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-2xl border border-border bg-white shadow-sm ${className}`}
    >
      {children}
    </section>
  );
}
export function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="py-14 text-center">
      <p className="font-semibold">{title}</p>
      <p className="mt-2 text-sm text-slate-500">{text}</p>
    </div>
  );
}
export function Loading() {
  return (
    <div
      className="flex items-center gap-2 py-12 text-sm text-slate-500"
      role="status"
    >
      <LoaderCircle className="size-4 animate-spin" /> Loading live data…
    </div>
  );
}
export function ErrorNotice({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
    >
      <span className="flex items-center gap-2">
        <AlertCircle className="size-4" />
        {message}
      </span>
      {retry && (
        <Button type="button" variant="outline" onClick={retry}>
          <RefreshCw className="size-4" /> Retry
        </Button>
      )}
    </div>
  );
}

export function ConfirmDialog({
  title,
  description,
  confirmLabel,
  danger = true,
  busy,
  onClose,
  onConfirm,
}: {
  title: string;
  description: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const dialogRef = useDialogKeyboard(onClose, busy);
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-description"
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl"
      >
        <h2 id="confirm-title" className="text-xl font-semibold">
          {title}
        </h2>
        <p
          id="confirm-description"
          className="mt-3 text-sm leading-6 text-slate-600"
        >
          {description}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button
            autoFocus
            type="button"
            className={danger ? "bg-red-700 hover:bg-red-800" : ""}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "Working…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
export function StatusBadge({ status }: { status: string }) {
  const color =
    status === "Connected" || status === "success"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : status === "Disabled"
        ? "bg-slate-100 text-slate-600 ring-slate-200"
        : "bg-amber-50 text-amber-800 ring-amber-200";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${color}`}
    >
      <span className="size-1.5 rounded-full bg-current" />
      {status}
    </span>
  );
}
export function SectionTitle({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-primary">
          {eyebrow}
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">
          {title}
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-500">{description}</p>
      </div>
      {action}
    </div>
  );
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="block text-sm font-medium text-slate-700">
      {label}
      <span className="mt-2 block">{children}</span>
      {hint && (
        <span className="mt-1 block text-xs font-normal text-slate-500">
          {hint}
        </span>
      )}
    </label>
  );
}
export const inputClass =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:bg-slate-100";
