"use client";

import { Sparkles, TriangleAlert } from "lucide-react";
import { useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ChatMessage, Source } from "@/lib/types";

const CITATION = /\[(\d{1,2})\](?!\()/g;

/** Turn "[2]" into a link the markdown renderer hands to `CitationLink`. */
function linkCitations(text: string): string {
  return text.replace(CITATION, (_, n) => `[${n}](#cite-${n})`);
}

function citedNumbers(text: string): Set<number> {
  return new Set(Array.from(text.matchAll(CITATION), (m) => Number(m[1])));
}

export function MessageView({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end" data-role="user">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-indigo-600 px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap text-white">
          {message.content}
        </div>
      </div>
    );
  }
  return <AssistantMessage message={message} />;
}

function AssistantMessage({ message }: { message: ChatMessage }) {
  const [openSource, setOpenSource] = useState<number | null>(null);
  const sources = message.sources ?? [];
  const cited = citedNumbers(message.content);
  const waiting = message.status === "streaming" && !message.content;

  const components: Components = {
    a: ({ href, children }) => {
      const match = href?.match(/^#cite-(\d+)$/);
      if (match) {
        const number = Number(match[1]);
        const known = sources.some((s) => s.number === number);
        return (
          <button
            type="button"
            onClick={() => known && setOpenSource(openSource === number ? null : number)}
            className="mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded bg-indigo-100 px-1 align-middle text-[11px] font-semibold text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-500/20 dark:text-indigo-200"
            aria-label={`Show source ${number}`}
          >
            {number}
          </button>
        );
      }
      return (
        <a href={href} target="_blank" rel="noreferrer">
          {children}
        </a>
      );
    },
  };

  return (
    <div className="flex gap-3" data-role="assistant" data-status={message.status ?? "done"}>
      <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900">
        <Sparkles className="size-3.5" />
      </div>
      <div className="min-w-0 flex-1">
        {waiting ? (
          <div className="flex items-center gap-1.5 py-2" aria-label="Searching the documents">
            <span className="text-sm text-zinc-500 dark:text-zinc-400">
              {sources.length ? "Writing an answer" : "Searching the documents"}
            </span>
            <span className="flex gap-1">
              {[0, 150, 300].map((delay) => (
                <span
                  key={delay}
                  className="size-1.5 animate-bounce rounded-full bg-zinc-400"
                  style={{ animationDelay: `${delay}ms` }}
                />
              ))}
            </span>
          </div>
        ) : (
          <div className={`markdown ${message.status === "streaming" ? "streaming" : ""}`}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
              {linkCitations(message.content)}
            </ReactMarkdown>
          </div>
        )}

        {message.status === "stopped" && <p className="mt-1 text-xs text-zinc-500">Stopped.</p>}
        {message.status === "error" && (
          <div className="mt-2 flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" />
            <span>{message.error}</span>
          </div>
        )}

        {sources.length > 0 && (
          <Sources
            sources={sources}
            cited={cited}
            open={openSource}
            onToggle={(n) => setOpenSource(openSource === n ? null : n)}
            query={message.query}
            model={message.modelLabel}
          />
        )}
      </div>
    </div>
  );
}

function Sources({
  sources,
  cited,
  open,
  onToggle,
  query,
  model,
}: {
  sources: Source[];
  cited: Set<number>;
  open: number | null;
  onToggle: (n: number) => void;
  query?: string;
  model?: string;
}) {
  const current = sources.find((s) => s.number === open);
  return (
    <div className="mt-3 space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {sources.map((source) => {
          const isCited = cited.has(source.number);
          const isOpen = source.number === open;
          return (
            <button
              key={source.number}
              type="button"
              onClick={() => onToggle(source.number)}
              aria-expanded={isOpen}
              title={`Similarity ${source.score.toFixed(2)}`}
              className={`inline-flex max-w-64 items-center gap-1.5 rounded-md px-2 py-1 text-xs ring-1 transition-colors ${
                isOpen
                  ? "bg-indigo-600 text-white ring-indigo-600"
                  : isCited
                    ? "bg-indigo-50 text-indigo-800 ring-indigo-200 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-200 dark:ring-indigo-500/30"
                    : "bg-white text-zinc-500 ring-zinc-200 hover:bg-zinc-50 dark:bg-zinc-900 dark:text-zinc-400 dark:ring-zinc-700"
              }`}
            >
              <span className="font-semibold">{source.number}</span>
              <span className="truncate">{source.filename}</span>
              {source.page && <span className="shrink-0 opacity-75">p.{source.page}</span>}
            </button>
          );
        })}
      </div>
      {current && (
        <blockquote className="rounded-lg border-l-2 border-indigo-400 bg-zinc-50 px-3 py-2 text-sm leading-relaxed text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
          <div className="mb-1 text-xs text-zinc-500 dark:text-zinc-400">
            {current.filename}
            {current.page ? `, page ${current.page}` : ""} · similarity {current.score.toFixed(2)}
          </div>
          <p className="whitespace-pre-wrap">{current.text}</p>
        </blockquote>
      )}
      {(query || model) && (
        <p className="text-[11px] text-zinc-400 dark:text-zinc-500">
          {model && <>Answered by {model}</>}
          {model && query && " · "}
          {query && <>searched for “{query}”</>}
        </p>
      )}
    </div>
  );
}
