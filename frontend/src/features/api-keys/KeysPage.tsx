import { useEffect, useState, type FormEvent } from "react";
import { Copy, KeyRound, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  ConfirmDialog,
  Empty,
  ErrorNotice,
  Field,
  inputClass,
  Panel,
  SectionTitle,
} from "@/components/Feedback";
import { endpoints, type ApiKey, type Member, type User } from "@/lib/api";
import { copyText } from "@/lib/clipboard";

export function KeysPage({ user }: { user: User }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [selected, setSelected] = useState<number | undefined>();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [name, setName] = useState("");
  const [created, setCreated] = useState("");
  const [copied, setCopied] = useState(false);
  const [target, setTarget] = useState<ApiKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (user.role === "admin")
      void endpoints
        .members()
        .then(setMembers)
        .catch((err) => setError(err.message));
  }, [user.role]);
  useEffect(() => {
    void endpoints
      .keys(selected)
      .then((rows) => {
        setKeys(rows);
        setError("");
      })
      .catch((err) => setError(err.message));
  }, [selected]);
  async function load() {
    try {
      setKeys(await endpoints.keys(selected));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load keys");
    }
  }
  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setCreated("");
    setCopied(false);
    try {
      const result = await endpoints.createKey(name, selected);
      setCreated(result.key);
      setName("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create key");
    } finally {
      setBusy(false);
    }
  }
  async function revoke() {
    if (!target) return;
    setBusy(true);
    try {
      await endpoints.revokeKey(target.id, selected);
      setTarget(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not revoke key");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <SectionTitle
        eyebrow="Gateway credentials"
        title="API keys"
        description="Issue keys for external MCP clients. Browser sessions and gateway keys are separate credentials."
      />
      {error && <ErrorNotice message={error} retry={() => void load()} />}
      {user.role === "admin" && (
        <div className="mb-5 max-w-sm">
          <Field label="Manage keys for">
            <select
              className={inputClass}
              value={selected ?? "self"}
              onChange={(e) => {
                setSelected(
                  e.target.value === "self"
                    ? undefined
                    : Number(e.target.value),
                );
                setCreated("");
              }}
            >
              <option value="self">My keys</option>
              {members
                .filter((m) => m.role === "member")
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.email}
                    {m.active ? "" : " (inactive)"}
                  </option>
                ))}
            </select>
          </Field>
        </div>
      )}
      <div className="grid gap-5 xl:grid-cols-[1fr_1.5fr]">
        <Panel className="h-fit p-6">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Plus className="size-5 text-primary" /> Create API key
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            Give the key a recognizable name for audit and revocation.
          </p>
          <form className="mt-6 grid gap-4" onSubmit={create}>
            <Field label="Key name">
              <input
                className={inputClass}
                required
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Desktop MCP client"
              />
            </Field>
            <Button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create key"}
            </Button>
          </form>
          {created && (
            <div
              className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4"
              role="status"
            >
              <p className="text-sm font-semibold text-amber-900">
                Copy this key now
              </p>
              <p className="mt-1 text-xs leading-5 text-amber-800">
                This is the only time the full key is shown. Store it in your
                MCP client's secure credential store. Do not share it in chat or
                a URL.
              </p>
              <div className="mt-3 flex gap-2">
                <input
                  className={`${inputClass} min-w-0 font-mono`}
                  type="text"
                  readOnly
                  aria-label="New API key, shown once"
                  value={created}
                />
                <Button
                  type="button"
                  variant="outline"
                  aria-label="Copy new API key"
                  onClick={() =>
                    void copyText(created)
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
              <Button
                className="mt-3"
                type="button"
                variant="outline"
                onClick={() => setCreated("")}
              >
                I saved the key
              </Button>
            </div>
          )}
        </Panel>
        <Panel className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border p-6">
            <KeyRound className="size-5 text-primary" />
            <h2 className="text-lg font-semibold">Issued keys</h2>
            <span className="ml-auto text-sm text-slate-500">
              {keys.length}
            </span>
          </div>
          {keys.length ? (
            <div className="divide-y divide-border">
              {keys.map((key) => (
                <div
                  key={key.id}
                  className="flex flex-wrap items-center justify-between gap-3 px-6 py-4"
                >
                  <div>
                    <p className="text-sm font-semibold">{key.name}</p>
                    <p className="mt-1 font-mono text-xs text-slate-500">
                      {key.prefix}… ·{" "}
                      {new Date(key.created_at).toLocaleDateString()}
                    </p>
                    <p
                      className={`mt-1 text-xs ${key.revoked_at ? "text-slate-500" : "text-emerald-700"}`}
                    >
                      {key.revoked_at ? "Revoked" : "Active"}
                    </p>
                  </div>
                  {!key.revoked_at && (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setTarget(key)}
                    >
                      Revoke
                    </Button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="No keys issued"
              text="Create a key to connect an external MCP client."
            />
          )}
        </Panel>
      </div>
      {target && (
        <ConfirmDialog
          title={`Revoke ${target.name}?`}
          description="This key will stop working on the next gateway request, including an existing client connection."
          confirmLabel="Revoke key"
          busy={busy}
          onClose={() => setTarget(null)}
          onConfirm={() => void revoke()}
        />
      )}
    </>
  );
}
