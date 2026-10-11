import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Boxes,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  PlugZap,
  RefreshCw,
  ServerCog,
  Users,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Empty,
  ErrorNotice,
  Loading,
  Panel,
  SectionTitle,
  StatusBadge,
} from "@/components/Feedback";
import { AuditPage } from "@/features/audit/AuditPage";
import { AuthScreens } from "@/features/auth/AuthScreens";
import { KeysPage } from "@/features/api-keys/KeysPage";
import { MembersPage } from "@/features/members/MembersPage";
import { ServersPage } from "@/features/servers/ServersPage";
import { ConnectPage } from "@/features/connect/ConnectPage";
import {
  ApiError,
  endpoints,
  type AuditRow,
  type Server,
  type User,
} from "@/lib/api";

type Page =
  "overview" | "servers" | "members" | "api-keys" | "audit" | "connect";
const pageNames: Page[] = [
  "overview",
  "servers",
  "members",
  "api-keys",
  "audit",
  "connect",
];
function pathPage(): Page {
  const segment = location.pathname.slice(1) as Page;
  return pageNames.includes(segment) ? segment : "overview";
}
const nav = [
  { id: "overview", name: "Overview", icon: LayoutDashboard },
  { id: "servers", name: "Servers", icon: ServerCog },
  { id: "members", name: "Members", icon: Users },
  { id: "api-keys", name: "API keys", icon: KeyRound },
  { id: "audit", name: "Audit log", icon: Activity },
  { id: "connect", name: "Connect", icon: PlugZap },
] as const;

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [initialError, setInitialError] = useState("");
  const [expired, setExpired] = useState(false);
  const [page, setPage] = useState<Page>(pathPage);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [servers, setServers] = useState<Server[]>([]);
  const [serversLoading, setServersLoading] = useState(false);
  const [serversError, setServersError] = useState("");
  const [recent, setRecent] = useState<AuditRow[]>([]);
  const [recentError, setRecentError] = useState("");
  const loadServers = useCallback(async (admin: boolean) => {
    setServersLoading(true);
    try {
      setServers(await endpoints.servers(admin));
      setServersError("");
    } catch (err) {
      setServersError(
        err instanceof Error ? err.message : "Could not load servers",
      );
    } finally {
      setServersLoading(false);
    }
  }, []);
  const loadRecent = useCallback(async () => {
    try {
      setRecent(await endpoints.audit(1, 6));
      setRecentError("");
    } catch (err) {
      setRecentError(
        err instanceof Error ? err.message : "Could not load activity",
      );
    }
  }, []);
  const checkSession = useCallback(async () => {
    setChecking(true);
    setInitialError("");
    await endpoints
      .me()
      .then(setUser)
      .catch((err: unknown) => {
        if (!(err instanceof ApiError && err.status === 401))
          setInitialError(
            "Could not check your session. Retry when the API is available.",
          );
      })
      .finally(() => setChecking(false));
  }, []);
  useEffect(() => {
    void checkSession();
  }, [checkSession]);
  useEffect(() => {
    const onExpired = () => {
      setUser(null);
      setExpired(true);
      setServers([]);
      setRecent([]);
    };
    const pop = () => setPage(pathPage());
    window.addEventListener("bridgecart:session-expired", onExpired);
    window.addEventListener("popstate", pop);
    return () => {
      window.removeEventListener("bridgecart:session-expired", onExpired);
      window.removeEventListener("popstate", pop);
    };
  }, []);
  useEffect(() => {
    if (!user) return;
    void loadServers(user.role === "admin");
    void loadRecent();
    const timer = window.setInterval(() => {
      void loadServers(user.role === "admin");
      void loadRecent();
    }, 30000);
    return () => clearInterval(timer);
  }, [user, loadServers, loadRecent]);
  function navigate(next: Page) {
    history.pushState(null, "", `/${next}`);
    setPage(next);
    setMobileMenu(false);
    window.scrollTo(0, 0);
  }
  async function logout() {
    try {
      await endpoints.logout();
    } catch {
      /* Clear local display even if the session expired. */
    }
    setUser(null);
    setServers([]);
    setRecent([]);
    history.replaceState(null, "", "/login");
  }
  if (checking)
    return (
      <div className="grid min-h-screen place-items-center">
        <Loading />
      </div>
    );
  if (initialError && !user)
    return (
      <div className="mx-auto grid min-h-screen max-w-lg place-items-center px-5">
        <ErrorNotice message={initialError} retry={() => void checkSession()} />
      </div>
    );
  if (!user)
    return (
      <>
        {expired && (
          <div
            role="alert"
            className="fixed left-1/2 top-4 z-20 -translate-x-1/2 rounded-lg bg-amber-100 px-4 py-2 text-sm text-amber-900 shadow"
          >
            Your session expired. Sign in again.
          </div>
        )}
        <AuthScreens
          onLogin={(signedIn) => {
            setUser(signedIn);
            setExpired(false);
            history.replaceState(null, "", "/overview");
            setPage("overview");
          }}
        />
      </>
    );
  return (
    <div className="min-h-screen bg-[#f7f8f6] lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside
        className={`${mobileMenu ? "fixed inset-0 z-40 bg-white" : "hidden"} border-r border-border bg-white lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col`}
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-6">
          <div className="flex items-center gap-3 text-lg font-bold tracking-tight">
            <span className="grid size-10 place-items-center rounded-xl bg-primary text-white">
              B
            </span>{" "}
            BridgeCart
          </div>
          <button
            type="button"
            className="lg:hidden"
            aria-label="Close navigation"
            onClick={() => setMobileMenu(false)}
          >
            <X />
          </button>
        </div>
        <p className="px-6 pb-2 pt-7 text-[11px] font-bold uppercase tracking-[0.19em] text-slate-400">
          Workspace
        </p>
        <nav aria-label="Main navigation" className="space-y-1 px-3">
          {nav
            .filter((item) => item.id !== "members" || user.role === "admin")
            .map(({ id, name, icon: Icon }) => (
              <button
                key={id}
                type="button"
                aria-current={page === id ? "page" : undefined}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-primary ${page === id ? "bg-emerald-50 text-primary" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}
                onClick={() => navigate(id)}
              >
                <Icon className="size-[18px]" />
                {name}
              </button>
            ))}
        </nav>
        <div className="mt-auto border-t border-border p-4">
          <p className="truncate px-2 text-sm font-semibold" title={user.email}>
            {user.email}
          </p>
          <p className="px-2 pt-1 text-xs capitalize text-slate-500">
            {user.role} · Active
          </p>
          <Button
            className="mt-4 w-full justify-start"
            variant="outline"
            onClick={() => void logout()}
          >
            <LogOut className="size-4" /> Sign out
          </Button>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-border bg-white/95 px-5 backdrop-blur sm:px-8 lg:px-10">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded-lg p-2 focus-visible:outline-2 focus-visible:outline-primary lg:hidden"
              aria-label="Open navigation"
              onClick={() => setMobileMenu(true)}
            >
              <Menu />
            </button>
            <span className="text-sm font-medium capitalize text-slate-600">
              {page.replace("-", " ")}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-primary sm:inline">
              Operations workspace
            </span>
            <span
              className="grid size-8 place-items-center rounded-full bg-slate-100 text-xs font-bold text-slate-700"
              aria-label={`Signed in as ${user.email}`}
            >
              {user.email[0].toUpperCase()}
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-[1450px] px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
          {page === "overview" && (
            <>
              <SectionTitle
                eyebrow="Operations overview"
                title="Your workspace at a glance"
                description="Live server availability, discovered tools, and recent gateway activity."
                action={
                  <Button
                    variant="outline"
                    onClick={() => {
                      void loadServers(user.role === "admin");
                      void loadRecent();
                    }}
                  >
                    <RefreshCw className="size-4" /> Refresh
                  </Button>
                }
              />
              {serversError && (
                <ErrorNotice
                  message={serversError}
                  retry={() => void loadServers(user.role === "admin")}
                />
              )}
              {recentError && (
                <div className="mt-3">
                  <ErrorNotice
                    message={recentError}
                    retry={() => void loadRecent()}
                  />
                </div>
              )}
              <div className="grid gap-4 sm:grid-cols-3">
                <Metric
                  label="Connected servers"
                  value={servers.filter((s) => s.status === "Connected").length}
                  icon={<ServerCog className="size-5" />}
                />
                <Metric
                  label="Available tools"
                  value={servers.reduce((sum, s) => sum + s.tools.length, 0)}
                  icon={<Boxes className="size-5" />}
                />
                <Metric
                  label="Recent tool attempts"
                  value={recent.length}
                  icon={<Activity className="size-5" />}
                />
              </div>
              <div className="mt-7 grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
                <Panel className="overflow-hidden">
                  <div className="flex items-center justify-between border-b border-border p-5 sm:p-6">
                    <div>
                      <h2 className="text-lg font-semibold">Server health</h2>
                      <p className="mt-1 text-sm text-slate-500">
                        Updated every 30 seconds
                      </p>
                    </div>
                    <button
                      className="text-sm font-semibold text-primary hover:underline"
                      onClick={() => navigate("servers")}
                    >
                      View all <ArrowUpRight className="inline size-4" />
                    </button>
                  </div>
                  {serversLoading && !servers.length ? (
                    <div className="p-5">
                      <Loading />
                    </div>
                  ) : servers.length ? (
                    <div className="divide-y divide-border">
                      {servers.map((s) => (
                        <div
                          key={s.id}
                          className="flex items-center justify-between gap-3 px-5 py-4 sm:px-6"
                        >
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold">
                              {s.name}
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                              {s.tools.length} tools
                              {s.reason
                                ? ` · ${s.reason.replaceAll("_", " ")}`
                                : ""}
                            </p>
                          </div>
                          <StatusBadge status={s.status} />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <Empty
                      title="No registered servers"
                      text="Server status will appear here once configured."
                    />
                  )}
                </Panel>
                <Panel className="overflow-hidden">
                  <div className="flex items-center justify-between border-b border-border p-5 sm:p-6">
                    <div>
                      <h2 className="text-lg font-semibold">Recent activity</h2>
                      <p className="mt-1 text-sm text-slate-500">
                        Latest gateway attempts
                      </p>
                    </div>
                    <button
                      className="text-sm font-semibold text-primary hover:underline"
                      onClick={() => navigate("audit")}
                    >
                      View log <ArrowUpRight className="inline size-4" />
                    </button>
                  </div>
                  {recent.length ? (
                    <div className="divide-y divide-border">
                      {recent.map((row) => (
                        <div
                          key={row.id}
                          className="flex items-center justify-between gap-3 px-5 py-4 sm:px-6"
                        >
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold">
                              {row.original_tool_name ||
                                row.exposed_tool_name ||
                                "Unknown tool"}
                            </p>
                            <p className="mt-1 truncate text-xs text-slate-500">
                              {row.user_email} ·{" "}
                              {new Date(row.started_at).toLocaleString()}
                            </p>
                          </div>
                          <StatusBadge status={row.outcome} />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <Empty
                      title="No recent activity"
                      text="Gateway calls will appear here."
                    />
                  )}
                </Panel>
              </div>
            </>
          )}
          {page === "servers" && (
            <ServersPage
              servers={servers}
              admin={user.role === "admin"}
              loading={serversLoading}
              error={serversError}
              refresh={() => loadServers(user.role === "admin")}
            />
          )}
          {page === "members" && user.role === "admin" && <MembersPage />}
          {page === "members" && user.role !== "admin" && (
            <ErrorNotice
              message="Admin access required."
              retry={() => navigate("overview")}
            />
          )}
          {page === "api-keys" && <KeysPage user={user} />}
          {page === "audit" && <AuditPage user={user} />}
          {page === "connect" && <ConnectPage />}
        </main>
      </div>
    </div>
  );
}
function Metric({
  label,
  value,
  icon,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
}) {
  return (
    <Panel className="flex items-center justify-between p-5 sm:p-6">
      <div>
        <p className="text-sm text-slate-500">{label}</p>
        <p className="mt-3 text-3xl font-semibold tracking-tight">{value}</p>
      </div>
      <span className="grid size-12 place-items-center rounded-2xl bg-emerald-50 text-primary">
        {icon}
      </span>
    </Panel>
  );
}
