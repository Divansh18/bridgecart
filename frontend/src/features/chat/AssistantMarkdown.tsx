import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { safeMarkdownUrl } from "./safeMarkdownUrl";

const allowedElements = [
  "a",
  "blockquote",
  "br",
  "code",
  "del",
  "em",
  "h1",
  "h2",
  "h3",
  "hr",
  "li",
  "ol",
  "p",
  "pre",
  "strong",
  "table",
  "tbody",
  "td",
  "th",
  "thead",
  "tr",
  "ul",
];

export function AssistantMarkdown({ content }: { content: string }) {
  return (
    <div className="min-w-0 break-words">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        allowedElements={allowedElements}
        urlTransform={safeMarkdownUrl}
        components={{
          a: ({ href, children }) =>
            href ? (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline underline-offset-2 hover:text-emerald-800 focus-visible:rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                {children}
              </a>
            ) : (
              <span>{children}</span>
            ),
          blockquote: ({ children }) => (
            <blockquote className="my-3 border-l-2 border-emerald-200 pl-3 text-slate-600">
              {children}
            </blockquote>
          ),
          code: ({ children }) => (
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">
              {children}
            </code>
          ),
          h1: ({ children }) => (
            <h1 className="mb-2 mt-4 text-lg font-semibold first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2 mt-4 text-base font-semibold first:mt-0">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-1 mt-3 font-semibold first:mt-0">{children}</h3>
          ),
          li: ({ children }) => <li className="pl-1">{children}</li>,
          ol: ({ children }) => (
            <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>
          ),
          p: ({ children }) => (
            <p className="my-2 first:mt-0 last:mb-0">{children}</p>
          ),
          pre: ({ children }) => (
            <pre className="my-3 max-w-full overflow-x-auto rounded-lg bg-slate-950 p-3 text-slate-50 [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-inherit">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div
              role="region"
              aria-label="Assistant table"
              tabIndex={0}
              className="my-3 max-w-full overflow-x-auto rounded-lg border border-border focus-visible:outline-2 focus-visible:outline-primary"
            >
              <table className="min-w-max border-collapse text-left text-xs">
                {children}
              </table>
            </div>
          ),
          td: ({ children }) => (
            <td className="border-t border-border px-3 py-2 align-top">
              {children}
            </td>
          ),
          th: ({ children }) => (
            <th className="bg-slate-50 px-3 py-2 font-semibold">{children}</th>
          ),
          ul: ({ children }) => (
            <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}
