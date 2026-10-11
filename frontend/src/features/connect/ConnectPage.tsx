import { ExternalLink, PlugZap } from "lucide-react";
import { Panel, SectionTitle } from "@/components/Feedback";

export function ConnectPage() {
  const url =
    window.bridgecartConfig?.gatewayUrl ||
    "http://api.bridgecart.local:8088/mcp";
  return (
    <>
      <SectionTitle
        eyebrow="External clients"
        title="Connect to BridgeCart"
        description="Use a personal API key with an MCP client that supports Streamable HTTP."
      />
      <div className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
        <Panel className="p-6">
          <div className="flex items-center gap-2">
            <PlugZap className="size-5 text-primary" />
            <h2 className="text-lg font-semibold">Gateway endpoint</h2>
          </div>
          <p className="mt-4 break-all rounded-xl bg-slate-950 p-4 font-mono text-sm text-emerald-200">
            {url}
          </p>
          <p className="mt-4 text-sm leading-6 text-slate-600">
            Configure your client with transport{" "}
            <strong>Streamable HTTP</strong> and an Authorization header in the
            form{" "}
            <code className="rounded bg-slate-100 px-1">
              Bearer &lt;YOUR_API_KEY&gt;
            </code>
            . Create the key on the API keys page. The client must refresh its
            tool list after registry changes.
          </p>
          <pre className="mt-5 overflow-x-auto rounded-xl bg-slate-100 p-4 text-xs leading-6 text-slate-700">
            {JSON.stringify(
              {
                mcpServers: {
                  bridgecart: {
                    url,
                    headers: { Authorization: "Bearer <YOUR_API_KEY>" },
                  },
                },
              },
              null,
              2,
            )}
          </pre>
          <p className="mt-3 text-xs text-slate-500">
            This is a generic configuration example. Client configuration shapes
            vary.
          </p>
        </Panel>
        <Panel className="p-6">
          <h2 className="text-lg font-semibold">Connection boundaries</h2>
          <ul className="mt-5 space-y-4 text-sm leading-6 text-slate-600">
            <li>
              Use your personal gateway key; do not use the browser session
              cookie.
            </li>
            <li>
              Only the gateway endpoint is public. The three upstream MCP
              services remain inside Kubernetes.
            </li>
            <li>Revoking a key blocks the next authenticated request.</li>
            <li>
              Tool names include immutable server identity, so names stay stable
              through display-name edits.
            </li>
          </ul>
          <a
            className="mt-6 inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
            href="/api/docs"
            target="_blank"
            rel="noreferrer"
          >
            Team API reference <ExternalLink className="size-4" />
          </a>
        </Panel>
      </div>
    </>
  );
}
