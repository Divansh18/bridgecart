import { useState, type FormEvent } from "react";
import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorNotice, Field, inputClass } from "@/components/Feedback";
import { endpoints, type User } from "@/lib/api";

export function AuthScreens({ onLogin }: { onLogin: (user: User) => void }) {
  const invite = location.pathname === "/accept-invitation";
  const token = new URLSearchParams(location.search).get("token") ?? "";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [accepted, setAccepted] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (invite && password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      if (invite) {
        await endpoints.accept(token, password);
        history.replaceState(null, "", "/login");
        setAccepted(true);
        setPassword("");
      } else onLogin((await endpoints.login(email, password)).user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(420px,0.85fr)]">
      <section className="relative hidden overflow-hidden bg-[#103b32] p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="relative z-10 flex items-center gap-3 text-lg font-semibold">
          <span className="grid size-10 place-items-center rounded-xl bg-white/15">
            B
          </span>{" "}
          BridgeCart
        </div>
        <div className="relative z-10 max-w-xl">
          <p className="text-sm font-semibold uppercase tracking-[0.22em] text-emerald-300">
            Commerce operations, connected
          </p>
          <h1 className="mt-6 text-5xl font-semibold leading-tight">
            One clear view across every commerce tool.
          </h1>
          <p className="mt-6 text-lg leading-8 text-emerald-100/80">
            Manage MCP servers, team access, and tool activity from a secure
            workspace.
          </p>
          <div className="mt-12 flex gap-7 text-sm text-emerald-100">
            <span className="flex items-center gap-2">
              <ShieldCheck className="size-5" /> Team access
            </span>
            <span className="flex items-center gap-2">
              <LockKeyhole className="size-5" /> Private credentials
            </span>
          </div>
        </div>
        <p className="relative z-10 text-xs text-emerald-100/60">
          BridgeCart operations console
        </p>
        <div className="absolute -bottom-36 -right-28 size-[550px] rounded-full border border-white/10 bg-emerald-400/10" />
        <div className="absolute -bottom-52 -right-10 size-[430px] rounded-full border border-white/10" />
      </section>
      <section className="flex min-h-screen items-center justify-center px-5 py-12 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-12 flex items-center gap-3 text-lg font-semibold lg:hidden">
            <span className="grid size-10 place-items-center rounded-xl bg-primary text-white">
              B
            </span>{" "}
            BridgeCart
          </div>
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary">
            Team workspace
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight">
            {invite ? "Accept your invitation" : "Welcome back"}
          </h2>
          <p className="mt-3 text-sm leading-6 text-slate-500">
            {invite
              ? "Set a password to join your BridgeCart team."
              : "Sign in to monitor servers, manage access, and review activity."}
          </p>
          {accepted && (
            <div
              role="status"
              className="mt-6 rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800"
            >
              Invitation accepted. Sign in with your new password.
            </div>
          )}
          {error && (
            <div className="mt-6">
              <ErrorNotice message={error} />
            </div>
          )}
          <form className="mt-8 space-y-5" onSubmit={submit}>
            {!invite && (
              <Field label="Email address">
                <input
                  className={inputClass}
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
            )}
            <Field label={invite ? "New password" : "Password"}>
              <input
                className={inputClass}
                type="password"
                autoComplete={invite ? "new-password" : "current-password"}
                minLength={invite ? 12 : 1}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            {invite && (
              <Field label="Confirm password">
                <input
                  className={inputClass}
                  type="password"
                  autoComplete="new-password"
                  minLength={12}
                  required
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              </Field>
            )}
            <Button
              type="submit"
              className="w-full"
              size="lg"
              disabled={busy || (invite && !token)}
            >
              {busy ? "Please wait…" : invite ? "Create account" : "Sign in"}
              <ArrowRight className="size-4" />
            </Button>
          </form>
          {invite && !token && (
            <p className="mt-4 text-sm text-red-700">
              Invitation token missing. Request a new private invitation link
              from your administrator.
            </p>
          )}
          {invite && (
            <a
              className="mt-6 inline-block text-sm font-medium text-primary underline-offset-4 hover:underline"
              href="/login"
            >
              Back to sign in
            </a>
          )}
          <p className="mt-12 border-t border-border pt-5 text-xs leading-5 text-slate-500">
            Private team access. Contact your administrator for an invitation.
            No public signup is available.
          </p>
        </div>
      </section>
    </main>
  );
}
