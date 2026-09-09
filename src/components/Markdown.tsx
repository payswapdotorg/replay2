"use client";

/**
 * Markdown renderer for agent messages — chat-grade:
 * GFM (tables, task lists, strikethrough), syntax-highlighted code blocks
 * with language label + copy button, safe links (new tab), inline images
 * (agent-generated content displays inline).
 */
import { memo, useState, isValidElement, cloneElement, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

function extractLang(children: ReactNode): string {
  const arr = Array.isArray(children) ? children : [children];
  for (const c of arr) {
    if (isValidElement(c)) {
      const cls = (c.props as { className?: string })?.className || "";
      const m = /language-([\w+#-]+)/.exec(cls);
      if (m) return m[1];
      const inner = extractLang((c.props as { children?: ReactNode })?.children);
      if (inner) return inner;
    }
  }
  return "";
}

function extractText(children: ReactNode): string {
  if (typeof children === "string") return children;
  if (typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(extractText).join("");
  if (isValidElement(children)) return extractText((children.props as { children?: ReactNode })?.children);
  return "";
}

function CodeBlock({ children }: { children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const lang = extractLang(children);
  const text = extractText(children);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <div className="my-3 rounded-lg border border-neutral-200 bg-neutral-900 overflow-hidden group">
      <div className="flex items-center justify-between px-3 py-1.5 bg-neutral-800 border-b border-neutral-700">
        <span className="text-[10px] font-mono uppercase tracking-wide text-neutral-400">{lang || "code"}</span>
        <button
          onClick={copy}
          className="text-[10px] px-2 py-0.5 rounded text-neutral-300 hover:text-white hover:bg-neutral-700 border border-neutral-600 transition-colors"
          aria-label="copy code"
        >
          {copied ? "copied ✓" : "copy"}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto text-[12.5px] leading-relaxed text-neutral-100">{children}</pre>
    </div>
  );
}

export const Markdown = memo(function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown-body text-[13.5px] leading-relaxed break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          code: ({ className, children, ...props }) => {
            const isBlock = /language-/.test(className || "");
            if (isBlock) {
              return (
                <code className={className} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code className="px-1 py-0.5 rounded bg-neutral-100 border border-neutral-200 font-mono text-[12px] text-pink-700">
                {children}
              </code>
            );
          },
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 underline decoration-blue-300 hover:text-blue-700"
            >
              {children}
            </a>
          ),
          img: ({ src, alt }) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={typeof src === "string" ? src : ""} alt={alt || ""} className="my-2 max-w-full rounded-lg border border-neutral-200" loading="lazy" />
          ),
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto">
              <table className="text-[12.5px] border-collapse border border-neutral-300">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-neutral-300 bg-neutral-100 px-2 py-1 text-left font-semibold">{children}</th>
          ),
          td: ({ children }) => <td className="border border-neutral-300 px-2 py-1">{children}</td>,
          ul: ({ children }) => <ul className="my-2 ml-5 list-disc space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 ml-5 list-decimal space-y-1">{children}</ol>,
          li: ({ children }) => {
            const raw = extractText(children);
            const task = /^\[( |x|X)\]\s+/.exec(raw);
            if (task) {
              const done = task[1].toLowerCase() === "x";
              const rest = raw.slice(task[0].length);
              return (
                <li className={`list-none -ml-5 flex items-start gap-1.5 ${done ? "text-neutral-400" : ""}`}>
                  <span className={`mt-0.5 text-[12px] ${done ? "text-emerald-600" : "text-neutral-400"}`}>{done ? "☑" : "☐"}</span>
                  <span className={done ? "line-through" : ""}>{rest}</span>
                </li>
              );
            }
            return <li>{children}</li>;
          },
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-3 border-neutral-300 pl-3 text-neutral-600">{children}</blockquote>
          ),
          h1: ({ children }) => <h1 className="my-3 text-lg font-bold first:mt-0">{children}</h1>,
          h2: ({ children }) => <h2 className="my-3 text-base font-bold first:mt-0">{children}</h2>,
          h3: ({ children }) => <h3 className="my-2 text-[14px] font-semibold first:mt-0">{children}</h3>,
          hr: () => <hr className="my-3 border-neutral-200" />,
          p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
});
