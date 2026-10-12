import { FormEvent, useRef, useState } from "react";
import {
  ArrowUp,
  MessageSquareText,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Panel, SectionTitle, inputClass } from "@/components/Feedback";
import { endpoints, type ChatHistory, type ChatTrace } from "@/lib/api";

type Entry = {
  role: "user" | "assistant";
  content: string;
  traces?: ChatTrace[];
  correlationId?: string;
};

export function ChatPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || inFlight.current || message.length > 2000) return;
    inFlight.current = true;
    setSending(true);
    setError("");
    setDraft("");
    const history: ChatHistory[] = entries.slice(-10).map((entry) => ({
      role: entry.role,
      content: entry.content.slice(0, 2000),
    }));
    setEntries((current) => [...current, { role: "user", content: message }]);
    try {
      const response = await endpoints.chat(message, history);
      setEntries((current) => [
        ...current,
        {
          role: "assistant",
          content: response.reply,
          traces: response.traces,
          correlationId: response.correlation_id,
        },
      ]);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Chat failed. Try again.",
      );
    } finally {
      inFlight.current = false;
      setSending(false);
    }
  }

  return (
    <>
      <SectionTitle
        eyebrow="Team assistant"
        title="Chat with your store"
        description="Ask Claude about your store or request a change. Tool calls run as your signed-in account through the gateway."
        action={
          <Button
            type="button"
            variant="outline"
            disabled={sending || entries.length === 0}
            onClick={() => {
              setEntries([]);
              setError("");
            }}
          >
            <RotateCcw className="size-4" /> New conversation
          </Button>
        }
      />
      <div className="mx-auto max-w-4xl space-y-5">
        <Panel className="flex min-h-[440px] flex-col overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border bg-white px-5 py-4 text-sm text-slate-600">
            <ShieldCheck className="size-4 text-primary" />
            Session authenticated · gateway audited
          </div>
          <div
            className="flex-1 space-y-5 bg-[#fafbf9] p-4 sm:p-7"
            aria-live="polite"
          >
            {entries.length === 0 && (
              <div className="mx-auto grid max-w-md justify-items-center gap-3 py-16 text-center">
                <span className="grid size-14 place-items-center rounded-2xl bg-emerald-50 text-primary">
                  <MessageSquareText className="size-7" />
                </span>
                <h2 className="text-lg font-semibold">
                  Start with a store question
                </h2>
                <p className="text-sm leading-6 text-slate-500">
                  Ask about products or today&apos;s orders. Inventory and
                  shipping tools use seeded demo data.
                </p>
              </div>
            )}
            {entries.map((entry, index) => (
              <div
                key={index}
                className={`flex ${entry.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[92%] rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm sm:max-w-[82%] ${entry.role === "user" ? "bg-primary text-white" : "border border-border bg-white text-foreground"}`}
                >
                  <p className="whitespace-pre-wrap break-words">
                    {entry.content}
                  </p>
                  {entry.traces && entry.traces.length > 0 && (
                    <div className="mt-4 space-y-2 border-t border-border pt-3 text-xs">
                      <p className="font-semibold uppercase tracking-wide text-slate-500">
                        Gateway tool trace
                      </p>
                      {entry.traces.map((trace, traceIndex) => (
                        <div
                          key={traceIndex}
                          className="rounded-lg bg-slate-50 px-3 py-2 text-slate-700"
                        >
                          <div className="flex flex-wrap justify-between gap-2 font-medium">
                            <span className="break-all">
                              {trace.server} · {trace.tool}
                            </span>
                            <span
                              className={
                                trace.status === "success"
                                  ? "text-emerald-700"
                                  : "text-amber-700"
                              }
                            >
                              {trace.status} · {trace.duration_ms} ms
                            </span>
                          </div>
                          <p className="mt-1 break-words text-slate-500">
                            {trace.detail}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                  {entry.correlationId && (
                    <p className="mt-3 text-[11px] text-slate-400">
                      Audit reference: {entry.correlationId}
                    </p>
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <p role="status" className="text-sm text-slate-500">
                Claude is working through the gateway…
              </p>
            )}
          </div>
          <form
            onSubmit={(event) => void send(event)}
            className="border-t border-border bg-white p-4 sm:p-5"
          >
            {error && (
              <p
                role="alert"
                className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700"
              >
                {error}
              </p>
            )}
            <label htmlFor="chat-message" className="sr-only">
              Message
            </label>
            <div className="flex items-end gap-3">
              <textarea
                id="chat-message"
                className={`${inputClass} min-h-20 flex-1 resize-y`}
                maxLength={2000}
                value={draft}
                disabled={sending}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Ask about your store…"
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <Button
                type="submit"
                disabled={sending || !draft.trim()}
                aria-label="Send message"
              >
                <ArrowUp className="size-4" />
              </Button>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              Up to 2,000 characters. Review tool results before retrying a
              timed-out write.
            </p>
          </form>
        </Panel>
      </div>
    </>
  );
}
