"use client";

import { BookOpen, Library, Plus, Settings, Trash2, X } from "lucide-react";

import { API_URL } from "@/lib/api";
import { pluralize } from "@/lib/format";
import type { AppConfig, KnowledgeBase } from "@/lib/types";

export function Sidebar({
  config,
  knowledgeBases,
  activeId,
  open,
  onClose,
  onSelect,
  onCreate,
  onDelete,
  onSettings,
}: {
  config: AppConfig | null;
  knowledgeBases: KnowledgeBase[] | null;
  activeId: string | null;
  open: boolean;
  onClose: () => void;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (kb: KnowledgeBase) => void;
  onSettings: () => void;
}) {
  const embeddingLabel = (kb: KnowledgeBase) =>
    config?.providers
      .find((p) => p.id === kb.embedding_provider)
      ?.embedding_models.find((m) => m.id === kb.embedding_model)?.label ?? kb.embedding_model;

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-zinc-950/40 md:hidden" onClick={onClose} aria-hidden />}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-zinc-200 bg-white transition-transform md:static md:translate-x-0 dark:border-zinc-800 dark:bg-zinc-900 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 pt-4 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
              <BookOpen className="size-4" />
            </div>
            <div>
              <div className="text-sm leading-tight font-semibold">DocChat</div>
              <div className="text-xs text-zinc-500 dark:text-zinc-400">Chat with your documents</div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-zinc-500 hover:bg-zinc-100 md:hidden dark:hover:bg-zinc-800"
            aria-label="Close sidebar"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="px-3">
          <button
            type="button"
            onClick={onCreate}
            className="flex w-full items-center gap-2 rounded-lg border border-dashed border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-700 hover:border-indigo-400 hover:bg-indigo-50 hover:text-indigo-700 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-indigo-500 dark:hover:bg-indigo-500/10 dark:hover:text-indigo-300"
          >
            <Plus className="size-4" />
            New knowledge base
          </button>
        </div>

        <nav className="mt-4 min-h-0 flex-1 overflow-y-auto px-3 pb-3" aria-label="Knowledge bases">
          <div className="px-2 pb-2 text-xs font-medium tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
            Knowledge bases
          </div>
          {knowledgeBases === null ? (
            <div className="space-y-2 px-2">
              {[0, 1].map((i) => (
                <div key={i} className="h-10 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
              ))}
            </div>
          ) : knowledgeBases.length === 0 ? (
            <p className="px-2 text-sm text-zinc-500 dark:text-zinc-400">None yet.</p>
          ) : (
            <ul className="space-y-1">
              {knowledgeBases.map((kb) => {
                const active = kb.id === activeId;
                return (
                  <li key={kb.id} className="group relative">
                    <button
                      type="button"
                      onClick={() => onSelect(kb.id)}
                      aria-current={active ? "page" : undefined}
                      className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 pr-9 text-left transition-colors ${
                        active
                          ? "bg-indigo-50 text-indigo-900 dark:bg-indigo-500/15 dark:text-indigo-100"
                          : "text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
                      }`}
                    >
                      <Library
                        className={`mt-0.5 size-4 shrink-0 ${active ? "text-indigo-600 dark:text-indigo-300" : "text-zinc-400"}`}
                      />
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">{kb.name}</span>
                        <span className="block truncate text-xs text-zinc-500 dark:text-zinc-400">
                          {pluralize(kb.document_count, "doc")} · {embeddingLabel(kb)}
                        </span>
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(kb)}
                      aria-label={`Delete ${kb.name}`}
                      className="absolute top-2 right-1.5 rounded-md p-1 text-zinc-400 opacity-0 group-hover:opacity-100 hover:bg-red-50 hover:text-red-600 focus:opacity-100 dark:hover:bg-red-500/10"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </nav>

        <div className="space-y-1 border-t border-zinc-200 p-3 dark:border-zinc-800">
          <button
            type="button"
            onClick={onSettings}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            <Settings className="size-4 text-zinc-400" />
            Settings &amp; API keys
          </button>
          <a
            href={`${API_URL}/docs`}
            target="_blank"
            rel="noreferrer"
            className="block px-2.5 text-xs text-zinc-500 hover:text-indigo-600 dark:text-zinc-400 dark:hover:text-indigo-300"
          >
            API reference ↗
          </a>
        </div>
      </aside>
    </>
  );
}
