import { ArrowRight, Boxes, ShieldCheck, Waypoints } from "lucide-react";
import { Button } from "@/components/ui/button";

const capabilities = [
  {
    icon: Waypoints,
    title: "One gateway",
    text: "A single place for team access to MCP servers.",
  },
  {
    icon: ShieldCheck,
    title: "Clear boundaries",
    text: "Credentials stay server-side, away from the browser.",
  },
  {
    icon: Boxes,
    title: "Built to grow",
    text: "WooCommerce, inventory, and shipping services have dedicated homes.",
  },
];

export function App() {
  return (
    <main className="min-h-screen px-6 py-8 sm:px-10">
      <div className="mx-auto max-w-6xl">
        <header className="flex items-center justify-between border-b border-border pb-6">
          <div className="flex items-center gap-3 font-semibold tracking-tight">
            <span className="grid size-10 place-items-center rounded-xl bg-primary text-white">
              B
            </span>{" "}
            BridgeCart
          </div>
          <span className="rounded-full border border-border px-3 py-1 text-xs font-medium text-primary">
            Foundation · milestone 1
          </span>
        </header>
        <section className="grid gap-10 py-20 lg:grid-cols-[1.25fr_1fr] lg:items-center lg:py-28">
          <div>
            <p className="mb-5 text-sm font-semibold uppercase tracking-[0.2em] text-primary">
              Team MCP gateway for commerce
            </p>
            <h1 className="max-w-3xl text-5xl font-semibold leading-tight tracking-tight sm:text-6xl">
              Connect your commerce tools with confidence.
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-slate-600">
              BridgeCart is the foundation for managed team access to
              WooCommerce and related MCP services. The gateway and product
              workflows arrive in the next milestone.
            </p>
            <div className="mt-9">
              <Button asChild size="lg">
                <a
                  href="https://github.com/modelcontextprotocol/python-sdk"
                  target="_blank"
                  rel="noreferrer"
                >
                  Explore MCP <ArrowRight className="size-4" />
                </a>
              </Button>
            </div>
          </div>
          <div className="rounded-3xl border border-border bg-white p-7 shadow-xl shadow-emerald-950/5">
            <div className="mb-8 flex items-center justify-between">
              <span className="text-sm font-semibold">
                Architecture preview
              </span>
              <span className="size-2 rounded-full bg-emerald-500" />
            </div>
            {capabilities.map(({ icon: Icon, title, text }) => (
              <div
                key={title}
                className="flex gap-4 border-t border-border py-5"
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-emerald-50 text-primary">
                  <Icon className="size-5" />
                </span>
                <div>
                  <h2 className="font-semibold">{title}</h2>
                  <p className="mt-1 text-sm leading-6 text-slate-600">
                    {text}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
        <footer className="border-t border-border pt-5 text-sm text-slate-500">
          BridgeCart · Project foundation
        </footer>
      </div>
    </main>
  );
}
