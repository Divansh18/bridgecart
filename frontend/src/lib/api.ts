export type User = {
  id: number;
  email: string;
  role: "admin" | "member";
  active: boolean;
};
export type Tool = {
  name: string;
  original_name: string;
  description: string | null;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown> | null;
  annotations: Record<string, unknown> | null;
};
export type Server = {
  id: string;
  name: string;
  status: "Connected" | "Unreachable" | "Disabled";
  reason: string | null;
  tools: Tool[];
  url?: string;
  enabled?: boolean;
  auth_type?: "none" | "bearer" | "header";
  header_name?: string | null;
  has_credential?: boolean;
};
export type Member = User;
export type ApiKey = {
  id: number;
  user_id: number;
  name: string;
  prefix: string;
  created_at: string;
  revoked_at: string | null;
};
export type AuditRow = {
  id: number;
  user_id: number;
  user_email: string;
  api_key_id: number | null;
  session_id: number | null;
  credential_type: "api_key" | "session_delegation";
  correlation_id: string | null;
  server_id: string | null;
  server_name: string | null;
  original_tool_name: string | null;
  exposed_tool_name: string | null;
  started_at: string;
  duration_ms: number | null;
  outcome: string;
  error_category: string | null;
};
export type ServerInput = {
  name: string;
  url: string;
  enabled: boolean;
  auth_type: "none" | "bearer" | "header";
  header_name?: string | null;
  credential?: string;
};

export type ChatTrace = {
  server: string;
  tool: string;
  status: "success" | "error" | "uncertain";
  duration_ms: number;
  detail: string;
};
export type ChatResponse = {
  reply: string;
  traces: ChatTrace[];
  correlation_id: string;
};
export type ChatHistory = { role: "user" | "assistant"; content: string };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function csrfToken(): string | undefined {
  const found = document.cookie
    .split("; ")
    .find((part) => part.startsWith("bridgecart_csrf="));
  return found
    ? decodeURIComponent(found.slice("bridgecart_csrf=".length))
    : undefined;
}

function detailText(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value))
    return value
      .map((item) =>
        typeof item?.msg === "string" ? item.msg : "Invalid input",
      )
      .join("; ");
  return "Request failed";
}

export async function api<T>(
  path: string,
  options: {
    method?: "GET" | "POST" | "PATCH" | "DELETE";
    body?: unknown;
  } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (
    method !== "GET" &&
    path !== "/auth/login" &&
    path !== "/auth/invitations/accept"
  ) {
    const token = csrfToken();
    if (token) headers["X-CSRF-Token"] = token;
  }
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      credentials: "same-origin",
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      "The server could not be reached. Check your connection and retry.",
    );
  }
  if (!response.ok) {
    if (
      response.status === 401 &&
      path !== "/auth/me" &&
      path !== "/auth/login"
    )
      window.dispatchEvent(new Event("bridgecart:session-expired"));
    let message = `Request failed (${response.status})`;
    try {
      message = detailText((await response.json()).detail);
    } catch {
      /* Non-JSON error response. */
    }
    throw new ApiError(response.status, message);
  }
  return response.status === 204
    ? (undefined as T)
    : ((await response.json()) as T);
}

export const endpoints = {
  me: () => api<User>("/auth/me"),
  login: (email: string, password: string) =>
    api<{ user: User }>("/auth/login", {
      method: "POST",
      body: { email, password },
    }),
  logout: () => api<void>("/auth/logout", { method: "POST" }),
  accept: (token: string, password: string) =>
    api<User>("/auth/invitations/accept", {
      method: "POST",
      body: { token, password },
    }),
  servers: (admin: boolean) =>
    api<Server[]>(admin ? "/servers" : "/servers/catalog"),
  createServer: (body: ServerInput) =>
    api<Server>("/servers", { method: "POST", body }),
  updateServer: (id: string, body: Partial<ServerInput>) =>
    api<Server>(`/servers/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body,
    }),
  removeServer: (id: string) =>
    api<void>(`/servers/${encodeURIComponent(id)}`, { method: "DELETE" }),
  members: () => api<Member[]>("/members"),
  invite: (email: string) =>
    api<{ id: number; email: string; token: string; expires_at: string }>(
      "/invitations",
      { method: "POST", body: { email } },
    ),
  deactivate: (id: number) =>
    api<Member>(`/members/${id}/deactivate`, { method: "POST" }),
  keys: (memberId?: number) =>
    api<ApiKey[]>(memberId ? `/members/${memberId}/api-keys` : "/api-keys"),
  createKey: (name: string, memberId?: number) =>
    api<ApiKey & { key: string }>(
      memberId ? `/members/${memberId}/api-keys` : "/api-keys",
      { method: "POST", body: { name } },
    ),
  revokeKey: (id: number, memberId?: number) =>
    api<void>(
      memberId ? `/members/${memberId}/api-keys/${id}` : `/api-keys/${id}`,
      { method: "DELETE" },
    ),
  audit: (page: number, perPage: number, userId?: number) =>
    api<AuditRow[]>(
      `/audit?${new URLSearchParams({ page: String(page), per_page: String(perPage), ...(userId ? { user_id: String(userId) } : {}) })}`,
    ),
  chat: (message: string, history: ChatHistory[]) =>
    api<ChatResponse>("/chat", { method: "POST", body: { message, history } }),
};
