import { useState, type FormEvent } from "react";
import {
  ChevronDown,
  ChevronRight,
  Plus,
  RefreshCw,
  ServerCog,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  ConfirmDialog,
  Empty,
  ErrorNotice,
  Field,
  inputClass,
  Panel,
  SectionTitle,
  StatusBadge,
} from "@/components/Feedback";
import { endpoints, type Server, type ServerInput } from "@/lib/api";

type CredentialChoice = "keep" | "replace" | "remove";
export function ServersPage({
  servers,
  admin,
  loading,
  error,
  refresh,
}: {
  servers: Server[];
  admin: boolean;
  loading: boolean;
  error: string;
  refresh: () => Promise<void>;
}) {
  const [editing, setEditing] = useState<Server | "new" | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<Server | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  async function toggle(server: Server) {
    setBusy(true);
    setActionError("");
    try {
      await endpoints.updateServer(server.id, { enabled: !server.enabled });
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!confirm) return;
    setBusy(true);
    setActionError("");
    try {
      await endpoints.removeServer(confirm.id);
      setConfirm(null);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Removal failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <SectionTitle
        eyebrow="Upstream registry"
        title="Servers"
        description="Live connection state and the tools exposed by each enabled upstream."
        action={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => void refresh()}>
              <RefreshCw className="size-4" /> Refresh
            </Button>
            {admin && (
              <Button onClick={() => setEditing("new")}>
                <Plus className="size-4" /> Add server
              </Button>
            )}
          </div>
        }
      />
      {error && <ErrorNotice message={error} retry={() => void refresh()} />}
      {actionError && (
        <div className="mt-3">
          <ErrorNotice message={actionError} />
        </div>
      )}
      {loading && !servers.length ? (
        <p role="status" className="text-sm text-slate-500">
          Discovering servers…
        </p>
      ) : !servers.length ? (
        <Panel>
          <Empty
            title="No servers registered"
            text="An administrator can add an approved MCP destination."
          />
        </Panel>
      ) : (
        <div className="grid gap-4">
          {servers.map((server) => (
            <Panel key={server.id} className="overflow-hidden">
              <div className="flex flex-wrap items-start justify-between gap-4 p-5 sm:p-6">
                <div className="flex min-w-0 items-start gap-4">
                  <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-emerald-50 text-primary">
                    <ServerCog className="size-5" />
                  </span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-3">
                      <h2 className="text-lg font-semibold text-slate-900">
                        {server.name}
                      </h2>
                      <StatusBadge status={server.status} />
                    </div>
                    <p className="mt-1 text-sm text-slate-500">
                      {server.tools.length}{" "}
                      {server.tools.length === 1 ? "tool" : "tools"} available
                      {server.reason
                        ? ` · ${server.reason.replaceAll("_", " ")}`
                        : ""}
                    </p>
                    {admin && (
                      <p className="mt-1 break-all text-xs text-slate-400">
                        {server.url}
                      </p>
                    )}
                  </div>
                </div>
                {admin && (
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      onClick={() => setEditing(server)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="outline"
                      disabled={busy}
                      onClick={() => void toggle(server)}
                    >
                      {server.enabled ? "Disable" : "Enable"}
                    </Button>
                    <Button
                      variant="outline"
                      aria-label={`Remove ${server.name}`}
                      onClick={() => setConfirm(server)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                )}
              </div>
              <div className="border-t border-border px-5 py-4 sm:px-6">
                <button
                  type="button"
                  aria-expanded={expanded === server.id}
                  className="flex w-full items-center justify-between text-left text-sm font-semibold text-slate-700 focus-visible:outline-2 focus-visible:outline-primary"
                  onClick={() =>
                    setExpanded(expanded === server.id ? null : server.id)
                  }
                >
                  <span>Exposed tools</span>
                  {expanded === server.id ? (
                    <ChevronDown className="size-4" />
                  ) : (
                    <ChevronRight className="size-4" />
                  )}
                </button>
                {expanded === server.id && (
                  <div className="mt-4 space-y-3">
                    {server.tools.length ? (
                      server.tools.map((tool) => (
                        <details
                          key={tool.name}
                          className="rounded-xl border border-border bg-slate-50 p-4"
                        >
                          <summary className="cursor-pointer break-all text-sm font-medium text-slate-800 focus-visible:outline-2 focus-visible:outline-primary">
                            {tool.original_name}
                            <span className="ml-2 text-xs font-normal text-slate-500">
                              {tool.name}
                            </span>
                          </summary>
                          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-600">
                            {tool.description || "No description provided."}
                          </p>
                          <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Input schema
                          </p>
                          <pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
                            {JSON.stringify(tool.input_schema, null, 2)}
                          </pre>
                        </details>
                      ))
                    ) : (
                      <p className="text-sm text-slate-500">
                        No tools currently available.
                      </p>
                    )}
                  </div>
                )}
              </div>
            </Panel>
          ))}
        </div>
      )}
      {editing && (
        <ServerEditor
          server={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await refresh();
          }}
        />
      )}
      {confirm && (
        <ConfirmDialog
          title={`Remove ${confirm.name}?`}
          description="This removes the registration and its stored credential. Existing audit history remains. This action cannot be undone."
          confirmLabel="Remove server"
          busy={busy}
          onClose={() => setConfirm(null)}
          onConfirm={() => void remove()}
        />
      )}
    </>
  );
}

function ServerEditor({
  server,
  onClose,
  onSaved,
}: {
  server: Server | "new";
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const fresh = server === "new";
  const current = fresh ? null : server;
  const [name, setName] = useState(current?.name ?? "");
  const [url, setUrl] = useState(current?.url ?? "");
  const [enabled, setEnabled] = useState(current?.enabled ?? true);
  const [authType, setAuthType] = useState<ServerInput["auth_type"]>(
    current?.auth_type ?? "none",
  );
  const [headerName, setHeaderName] = useState(current?.header_name ?? "");
  const [choice, setChoice] = useState<CredentialChoice>("keep");
  const [credential, setCredential] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (
      authType !== "none" &&
      (fresh || choice === "replace" || !current?.has_credential) &&
      !credential.trim()
    ) {
      setError("Enter a credential for the selected authentication type.");
      return;
    }
    setBusy(true);
    try {
      const body: ServerInput = {
        name: name.trim(),
        url: url.trim(),
        enabled,
        auth_type: authType,
        ...(authType === "header"
          ? { header_name: headerName.trim() }
          : { header_name: null }),
      };
      if (
        authType !== "none" &&
        (fresh || choice === "replace" || !current?.has_credential)
      )
        body.credential = credential;
      if (fresh) await endpoints.createServer(body);
      else if (current) await endpoints.updateServer(current.id, body);
      setCredential("");
      await onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }
  function removeCredential() {
    setAuthType("none");
    setChoice("remove");
    setCredential("");
  }
  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/50 px-4 py-8"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="server-editor-title"
        className="mx-auto w-full max-w-xl rounded-2xl bg-white p-6 shadow-2xl sm:p-8"
      >
        <h2 id="server-editor-title" className="text-xl font-semibold">
          {fresh ? "Add approved server" : `Edit ${current?.name}`}
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          Upstream URLs must be preapproved in gateway configuration. Stored
          credentials are never displayed.
        </p>
        {error && (
          <div className="mt-5">
            <ErrorNotice message={error} />
          </div>
        )}
        <form className="mt-6 grid gap-5" onSubmit={submit}>
          <Field label="Server name">
            <input
              className={inputClass}
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <Field
            label="Internal MCP URL"
            hint="Use an approved cluster Service URL ending in /mcp."
          >
            <input
              className={inputClass}
              type="url"
              required
              maxLength={500}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </Field>
          <Field label="Authentication">
            <select
              className={inputClass}
              value={authType}
              onChange={(e) => {
                const next = e.target.value as ServerInput["auth_type"];
                setAuthType(next);
                setChoice(
                  next === "none"
                    ? "remove"
                    : current?.has_credential
                      ? "replace"
                      : "keep",
                );
              }}
            >
              {["none", "bearer", "header"].map((value) => (
                <option key={value} value={value}>
                  {value === "none"
                    ? "None"
                    : value === "bearer"
                      ? "Bearer token"
                      : "Custom header"}
                </option>
              ))}
            </select>
          </Field>
          {authType === "header" && (
            <Field
              label="Header name"
              hint="Only approved X- headers are accepted."
            >
              <input
                className={inputClass}
                required
                pattern="X-[A-Za-z0-9-]+"
                value={headerName}
                onChange={(e) => setHeaderName(e.target.value)}
              />
            </Field>
          )}
          {current?.has_credential && authType !== "none" && (
            <Field label="Stored credential">
              <select
                className={inputClass}
                value={choice}
                onChange={(e) => {
                  const next = e.target.value as CredentialChoice;
                  if (next === "remove") removeCredential();
                  else setChoice(next);
                }}
              >
                <option value="keep">Keep existing credential</option>
                <option value="replace">Replace credential</option>
                <option value="remove">
                  Remove credential and authentication
                </option>
              </select>
            </Field>
          )}
          {authType !== "none" &&
            (fresh || choice === "replace" || !current?.has_credential) && (
              <Field
                label="New credential"
                hint="Write-only. It will not be retrievable after saving."
              >
                <input
                  className={inputClass}
                  type="password"
                  autoComplete="off"
                  required
                  value={credential}
                  onChange={(e) => setCredential(e.target.value)}
                />
              </Field>
            )}
          <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />{" "}
            Enabled
          </label>
          <div className="flex justify-end gap-2 border-t border-border pt-5">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save server"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
