import { useEffect, useState, type FormEvent } from "react";
import { Copy, Plus, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  ConfirmDialog,
  Empty,
  ErrorNotice,
  Field,
  inputClass,
  Loading,
  Panel,
  SectionTitle,
} from "@/components/Feedback";
import { endpoints, type Member } from "@/lib/api";
import { copyText } from "@/lib/clipboard";

export function MembersPage() {
  const [members, setMembers] = useState<Member[]>([]);
  const [email, setEmail] = useState("");
  const [copied, setCopied] = useState(false);
  const [invitation, setInvitation] = useState<{
    email: string;
    token: string;
    expires_at: string;
  } | null>(null);
  const [target, setTarget] = useState<Member | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  async function load() {
    setLoading(true);
    try {
      setMembers(await endpoints.members());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load members");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function invite(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setInvitation(null);
    setCopied(false);
    try {
      setInvitation(await endpoints.invite(email));
      setEmail("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invitation failed");
    } finally {
      setBusy(false);
    }
  }
  async function deactivate() {
    if (!target) return;
    setBusy(true);
    try {
      await endpoints.deactivate(target.id);
      setTarget(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deactivation failed");
    } finally {
      setBusy(false);
    }
  }
  const link = invitation
    ? `${location.origin}/accept-invitation?token=${encodeURIComponent(invitation.token)}`
    : "";
  return (
    <>
      <SectionTitle
        eyebrow="Team access"
        title="Members"
        description="Invite teammates privately and manage access to this workspace."
      />
      {error && <ErrorNotice message={error} retry={() => void load()} />}
      <div className="grid gap-5 xl:grid-cols-[1fr_1.65fr]">
        <Panel className="h-fit p-6">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Plus className="size-5 text-primary" /> Create invitation
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            The one-time link appears only here. Share it privately with the
            intended person.
          </p>
          <form className="mt-6 grid gap-4" onSubmit={invite}>
            <Field label="Member email">
              <input
                className={inputClass}
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <Button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create invitation"}
            </Button>
          </form>
          {invitation && (
            <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4">
              <p className="text-sm font-semibold text-amber-900">
                Private invitation for {invitation.email}
              </p>
              <p className="mt-1 text-xs text-amber-800">
                Expires {new Date(invitation.expires_at).toLocaleString()}. Copy
                now; it will not appear again.
              </p>
              <div className="mt-3 flex gap-2">
                <input
                  className={`${inputClass} min-w-0`}
                  readOnly
                  aria-label="Private invitation link"
                  value={link}
                />
                <Button
                  type="button"
                  variant="outline"
                  aria-label="Copy invitation link"
                  onClick={() =>
                    void copyText(link)
                      .then(() => setCopied(true))
                      .catch((err) => setError(err.message))
                  }
                >
                  <Copy className="size-4" />
                </Button>
                {copied && (
                  <span
                    role="status"
                    className="self-center text-xs text-emerald-800"
                  >
                    Copied
                  </span>
                )}
              </div>
            </div>
          )}
        </Panel>
        <Panel className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border p-6">
            <Users className="size-5 text-primary" />
            <h2 className="text-lg font-semibold">Team directory</h2>
            <span className="ml-auto text-sm text-slate-500">
              {members.length} members
            </span>
          </div>
          {loading ? (
            <div className="px-6">
              <Loading />
            </div>
          ) : members.length ? (
            <div className="divide-y divide-border">
              {members.map((member) => (
                <div
                  key={member.id}
                  className="flex flex-wrap items-center justify-between gap-3 px-6 py-4"
                >
                  <div className="min-w-0">
                    <p className="break-all text-sm font-semibold">
                      {member.email}
                    </p>
                    <p className="mt-1 text-xs capitalize text-slate-500">
                      {member.role} · {member.active ? "Active" : "Inactive"}
                    </p>
                  </div>
                  {member.role === "member" && member.active && (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setTarget(member)}
                    >
                      Deactivate
                    </Button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="No users found"
              text="Team members will appear here."
            />
          )}
        </Panel>
      </div>
      {target && (
        <ConfirmDialog
          title={`Deactivate ${target.email}?`}
          description="Their sessions and API keys will stop working on the next authenticated request. Existing audit records remain."
          confirmLabel="Deactivate member"
          busy={busy}
          onClose={() => setTarget(null)}
          onConfirm={() => void deactivate()}
        />
      )}
    </>
  );
}
