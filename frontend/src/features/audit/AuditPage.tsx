import { useEffect, useState } from "react";
import { Activity, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Empty,
  ErrorNotice,
  Panel,
  SectionTitle,
  StatusBadge,
  inputClass,
} from "@/components/Feedback";
import { endpoints, type AuditRow, type Member, type User } from "@/lib/api";

export function AuditPage({ user }: { user: User }) {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [page, setPage] = useState(1);
  const [member, setMember] = useState<number | undefined>();
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (user.role === "admin")
      void endpoints
        .members()
        .then(setMembers)
        .catch(() => {});
  }, [user.role]);
  useEffect(() => {
    let active = true;
    void endpoints
      .audit(page, 20, member)
      .then((data) => {
        if (active) {
          setRows(data);
          setError("");
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err.message);
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [page, member, revision]);
  return (
    <>
      <SectionTitle
        eyebrow="Tool activity"
        title="Audit log"
        description="User-attributed attempts and safe outcomes. Arguments, results, and credentials are not stored."
        action={
          <Button variant="outline" onClick={() => setRevision(revision + 1)}>
            <Activity className="size-4" /> Refresh
          </Button>
        }
      />
      {user.role === "admin" && (
        <div className="mb-5 max-w-xs">
          <label className="text-sm font-medium text-slate-700">
            Filter by user
            <select
              className={`${inputClass} mt-2`}
              value={member ?? "all"}
              onChange={(e) => {
                setPage(1);
                setMember(
                  e.target.value === "all" ? undefined : Number(e.target.value),
                );
              }}
            >
              <option value="all">All users</option>
              {members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.email}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      {error && (
        <ErrorNotice message={error} retry={() => setRevision(revision + 1)} />
      )}
      <Panel className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-5 py-4">When</th>
                <th className="px-5 py-4">User</th>
                <th className="px-5 py-4">Server / tool</th>
                <th className="px-5 py-4">Duration</th>
                <th className="px-5 py-4">Outcome</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((row) => (
                <tr key={row.id} className="align-top">
                  <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                    {new Date(row.started_at).toLocaleString()}
                  </td>
                  <td className="px-5 py-4">
                    <span className="break-all font-medium">
                      {row.user_email}
                    </span>
                    <span className="mt-1 block text-xs text-slate-400">
                      {row.credential_type === "session_delegation"
                        ? `Chat session #${row.session_id}`
                        : `Key #${row.api_key_id}`}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <span className="font-medium">
                      {row.server_name || "Unknown server"}
                    </span>
                    <span className="mt-1 block break-all text-xs text-slate-500">
                      {row.original_tool_name ||
                        row.exposed_tool_name ||
                        "Unknown tool"}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                    {row.duration_ms == null ? "—" : `${row.duration_ms} ms`}
                  </td>
                  <td className="px-5 py-4">
                    <StatusBadge status={row.outcome} />
                    {row.error_category && (
                      <span className="mt-1 block text-xs text-slate-500">
                        {row.error_category.replaceAll("_", " ")}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && !rows.length && (
          <Empty
            title="No activity on this page"
            text="Tool calls appear here when external clients use the gateway."
          />
        )}
        {loading && (
          <p role="status" className="p-5 text-sm text-slate-500">
            Loading activity…
          </p>
        )}
        <div className="flex items-center justify-between border-t border-border px-5 py-4 text-sm text-slate-500">
          <span>Page {page} · up to 20 records</span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              disabled={page === 1 || loading}
              onClick={() => setPage(page - 1)}
              aria-label="Previous page"
            >
              <ChevronLeft className="size-4" />
            </Button>
            <Button
              variant="outline"
              disabled={rows.length < 20 || loading}
              onClick={() => setPage(page + 1)}
              aria-label="Next page"
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      </Panel>
    </>
  );
}
