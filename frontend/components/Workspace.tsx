"use client";

import { BookOpen, Eraser, KeyRound, LoaderCircle, Menu, Plus, Settings, TriangleAlert, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";

import { api, streamChat } from "@/lib/api";
import { extensionOf, uid } from "@/lib/format";
import { hasKey, resolveSelection, type Selection } from "@/lib/models";
import { usePersistentState } from "@/lib/storage";
import type { AppConfig, ChatMessage, DocumentItem, KnowledgeBase, Preferences, ProviderId } from "@/lib/types";
import { Composer } from "./Composer";
import { DocumentsBar, FilePicker, type UploadItem } from "./DocumentsBar";
import { KnowledgeBaseDialog, type NewKnowledgeBase } from "./KnowledgeBaseDialog";
import { MessageView } from "./Message";
import { SettingsDialog } from "./SettingsDialog";
import { Sidebar } from "./Sidebar";
import { Button } from "./ui";

const DEFAULT_PREFS: Preferences = {
  keys: { openai: "", anthropic: "", google: "" },
  provider: "",
  model: "",
  useCustomModel: false,
  customModel: "",
  temperature: 0.2,
  topK: 5,
  searchType: "mmr",
};

const MAX_THREAD_MESSAGES = 100;

const SUGGESTIONS = [
  "Summarize the key points",
  "What are the main topics covered?",
  "List any dates, numbers or deadlines mentioned",
];

function withoutKey<T>(record: Record<string, T>, key: string): Record<string, T> {
  const copy = { ...record };
  delete copy[key];
  return copy;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}

export default function Workspace() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<Record<string, DocumentItem[]>>({});
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [dialog, setDialog] = useState<"create" | "settings" | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [streamingKb, setStreamingKb] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [activeId, setActiveId] = usePersistentState<string | null>("docchat:active", null);
  const [prefs, setPrefs] = usePersistentState<Preferences>("docchat:prefs", DEFAULT_PREFS);
  const [threads, setThreads] = usePersistentState<Record<string, ChatMessage[]>>("docchat:threads", {});

  const load = useCallback(async () => {
    try {
      const [nextConfig, list] = await Promise.all([api.config(), api.listKnowledgeBases()]);
      setConfig(nextConfig);
      setKnowledgeBases(list);
      setLoadError(null);
    } catch (error) {
      setLoadError(errorText(error));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refreshKnowledgeBases = useCallback(async () => {
    try {
      setKnowledgeBases(await api.listKnowledgeBases());
    } catch {
      // keep the list we have
    }
  }, []);

  const active = knowledgeBases?.find((kb) => kb.id === activeId) ?? knowledgeBases?.[0] ?? null;
  const activeKbId = active?.id ?? null;

  useEffect(() => {
    if (!activeKbId) return;
    let cancelled = false;
    api
      .listDocuments(activeKbId)
      .then((docs) => !cancelled && setDocuments((d) => ({ ...d, [activeKbId]: docs })))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [activeKbId]);

  const selection = useMemo(() => (config ? resolveSelection(config, prefs) : null), [config, prefs]);
  const messages = useMemo(() => (activeKbId ? (threads[activeKbId] ?? []) : []), [threads, activeKbId]);
  const activeDocs = activeKbId ? documents[activeKbId] : undefined;
  const hasDocuments = (active?.document_count ?? 0) > 0 || (activeDocs?.length ?? 0) > 0;

  async function createKnowledgeBase(body: NewKnowledgeBase) {
    const kb = await api.createKnowledgeBase(body);
    setKnowledgeBases((list) => [kb, ...(list ?? [])]);
    setActiveId(kb.id);
    setDialog(null);
  }

  async function deleteKnowledgeBase(kb: KnowledgeBase) {
    if (!window.confirm(`Delete "${kb.name}" and all of its documents? This can't be undone.`)) return;
    try {
      await api.deleteKnowledgeBase(kb.id);
      setKnowledgeBases((list) => (list ?? []).filter((k) => k.id !== kb.id));
      setThreads((t) => withoutKey(t, kb.id));
    } catch (error) {
      window.alert(errorText(error));
    }
  }

  async function uploadFiles(files: File[]) {
    if (!active || !config) return;
    const kbId = active.id;
    const patchUpload = (id: string, patch: Partial<UploadItem>) =>
      setUploads((list) => list.map((u) => (u.id === id ? { ...u, ...patch } : u)));

    for (const file of files) {
      const id = uid();
      const ext = extensionOf(file.name);
      let problem: string | null = null;
      if (!config.limits.extensions.includes(ext)) problem = `${ext || "This type"} isn't supported`;
      else if (file.size > config.limits.max_upload_mb * 1024 * 1024)
        problem = `Larger than ${config.limits.max_upload_mb} MB`;
      if (problem) {
        setUploads((list) => [...list, { id, name: file.name, status: "error", error: problem }]);
        continue;
      }

      setUploads((list) => [...list, { id, name: file.name, status: "uploading" }]);
      try {
        const doc = await api.uploadDocument(kbId, file, prefs.keys);
        setDocuments((d) => ({ ...d, [kbId]: [doc, ...(d[kbId] ?? [])] }));
        setUploads((list) => list.filter((u) => u.id !== id));
      } catch (error) {
        patchUpload(id, { status: "error", error: errorText(error) });
      }
    }
    await refreshKnowledgeBases();
  }

  async function deleteDocument(doc: DocumentItem) {
    try {
      await api.deleteDocument(doc.knowledge_base_id, doc.id);
      setDocuments((d) => ({
        ...d,
        [doc.knowledge_base_id]: (d[doc.knowledge_base_id] ?? []).filter((x) => x.id !== doc.id),
      }));
      await refreshKnowledgeBases();
    } catch (error) {
      window.alert(errorText(error));
    }
  }

  async function ask(question: string) {
    if (!active || !selection || streamingKb) return;
    const kbId = active.id;
    const history = (threads[kbId] ?? [])
      .filter((m) => m.status !== "error" && m.content.trim())
      .map(({ role, content }) => ({ role, content }));
    const reply: ChatMessage = {
      id: uid(),
      role: "assistant",
      content: "",
      status: "streaming",
      modelLabel: selection.model.label,
    };
    setThreads((t) => ({
      ...t,
      [kbId]: [...(t[kbId] ?? []), { id: uid(), role: "user" as const, content: question }, reply].slice(
        -MAX_THREAD_MESSAGES,
      ),
    }));
    const patch = (update: (m: ChatMessage) => ChatMessage) =>
      setThreads((t) => ({ ...t, [kbId]: (t[kbId] ?? []).map((m) => (m.id === reply.id ? update(m) : m)) }));

    const controller = new AbortController();
    abortRef.current = controller;
    setStreamingKb(kbId);
    try {
      await streamChat(
        {
          knowledge_base_id: kbId,
          messages: [...history, { role: "user", content: question }],
          provider: selection.provider.id,
          model: selection.model.id,
          temperature: selection.model.temperature ? prefs.temperature : null,
          top_k: prefs.topK,
          search_type: prefs.searchType,
        },
        prefs.keys,
        controller.signal,
        (event) => {
          if (event.type === "sources") patch((m) => ({ ...m, sources: event.sources, query: event.query }));
          else if (event.type === "token") patch((m) => ({ ...m, content: m.content + event.text }));
          else if (event.type === "done") patch((m) => ({ ...m, status: "done" }));
          else patch((m) => ({ ...m, status: "error", error: event.message }));
        },
      );
      patch((m) => (m.status === "streaming" ? { ...m, status: "done" } : m));
    } catch (error) {
      if (controller.signal.aborted) patch((m) => ({ ...m, status: "stopped" }));
      else patch((m) => ({ ...m, status: "error", error: errorText(error) }));
    } finally {
      abortRef.current = null;
      setStreamingKb(null);
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.length) void uploadFiles(files);
  }

  const embeddingProvider = config?.providers.find((p) => p.id === active?.embedding_provider);
  const missingKeys = [
    selection && !hasKey(selection.provider, prefs.keys) ? selection.provider : null,
    active && embeddingProvider && !hasKey(embeddingProvider, prefs.keys) ? embeddingProvider : null,
  ].filter((p, i, all): p is NonNullable<typeof p> => p !== null && all.findIndex((q) => q?.id === p.id) === i);

  return (
    <div className="flex h-dvh overflow-hidden bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <Sidebar
        config={config}
        knowledgeBases={knowledgeBases}
        activeId={activeKbId}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onSelect={(id) => {
          setActiveId(id);
          setSidebarOpen(false);
        }}
        onCreate={() => setDialog("create")}
        onDelete={deleteKnowledgeBase}
        onSettings={() => setDialog("settings")}
      />

      <main
        className="relative flex min-w-0 flex-1 flex-col"
        onDragOver={(event) => {
          if (!active || !event.dataTransfer.types.includes("Files")) return;
          event.preventDefault();
          setDragging(true);
        }}
      >
        <header className="flex items-center gap-3 border-b border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
          <button
            type="button"
            className="rounded-md p-1.5 text-zinc-600 hover:bg-zinc-100 md:hidden dark:text-zinc-300 dark:hover:bg-zinc-800"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
          >
            <Menu className="size-5" />
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-[15px] font-semibold">{active?.name ?? "DocChat"}</h1>
            {active?.description && (
              <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">{active.description}</p>
            )}
          </div>
          {config && selection && (
            <ModelPicker
              config={config}
              selection={selection}
              onChange={(provider, model) => setPrefs((p) => ({ ...p, provider, model, useCustomModel: false }))}
            />
          )}
          {messages.length > 0 && (
            <Button
              variant="ghost"
              className="px-2"
              onClick={() => activeKbId && setThreads((t) => withoutKey(t, activeKbId))}
              disabled={streamingKb !== null}
              aria-label="Clear conversation"
              title="Clear conversation"
            >
              <Eraser className="size-4" />
            </Button>
          )}
          <Button
            variant="ghost"
            className="px-2"
            onClick={() => setDialog("settings")}
            aria-label="Settings"
            title="Settings"
          >
            <Settings className="size-4" />
          </Button>
        </header>

        {missingKeys.length > 0 && (
          <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200">
            <KeyRound className="size-4 shrink-0" />
            <span className="flex-1">
              Add {missingKeys.map((p) => `${/^[aeiou]/i.test(p.label) ? "an" : "a"} ${p.label}`).join(" and ")} API{" "}
              {missingKeys.length > 1 ? "keys" : "key"} to{" "}
              {missingKeys.some((p) => p.id === active?.embedding_provider) ? "index documents and " : ""}get answers.
            </span>
            <button
              type="button"
              className="font-medium underline underline-offset-2"
              onClick={() => setDialog("settings")}
            >
              Open settings
            </button>
          </div>
        )}

        {loadError ? (
          <CenteredNotice
            icon={<TriangleAlert className="size-5 text-amber-500" />}
            title="Can't load the workspace"
            body={loadError}
            action={<Button onClick={() => void load()}>Try again</Button>}
          />
        ) : !config || !knowledgeBases ? (
          <div className="flex flex-1 items-center justify-center text-zinc-400">
            <LoaderCircle className="size-6 animate-spin" />
          </div>
        ) : !active ? (
          <Welcome config={config} onCreate={() => setDialog("create")} />
        ) : (
          <>
            <DocumentsBar
              documents={activeDocs}
              uploads={uploads}
              extensions={config.limits.extensions}
              onUpload={(files) => void uploadFiles(files)}
              onDelete={(doc) => void deleteDocument(doc)}
              onDismissUpload={(id) => setUploads((list) => list.filter((u) => u.id !== id))}
            />
            <Thread messages={messages} streaming={streamingKb === active.id}>
              {!hasDocuments ? (
                <EmptyDocuments config={config} onFiles={(files) => void uploadFiles(files)} />
              ) : (
                <EmptyChat onAsk={(q) => void ask(q)} disabled={streamingKb !== null} />
              )}
            </Thread>
            <Composer
              disabled={!hasDocuments}
              streaming={streamingKb === active.id}
              placeholder={hasDocuments ? `Ask about ${active.name}…` : "Upload a document to start asking questions"}
              onSend={(q) => void ask(q)}
              onStop={() => abortRef.current?.abort()}
            />
          </>
        )}

        {dragging && (
          <div
            className="absolute inset-0 z-20 m-3 flex items-center justify-center rounded-2xl border-2 border-dashed border-indigo-400 bg-indigo-50/90 text-indigo-700 dark:bg-indigo-950/90 dark:text-indigo-200"
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <div className="pointer-events-none flex flex-col items-center gap-2">
              <Upload className="size-8" />
              <p className="font-medium">Drop files to add them to {active?.name}</p>
            </div>
          </div>
        )}
      </main>

      {config && (
        <>
          <KnowledgeBaseDialog
            key={dialog === "create" ? "open" : "closed"}
            open={dialog === "create"}
            config={config}
            keys={prefs.keys}
            onClose={() => setDialog(null)}
            onCreate={createKnowledgeBase}
          />
          <SettingsDialog
            open={dialog === "settings"}
            config={config}
            prefs={prefs}
            setPrefs={setPrefs}
            onClose={() => setDialog(null)}
          />
        </>
      )}
    </div>
  );
}

function ModelPicker({
  config,
  selection,
  onChange,
}: {
  config: AppConfig;
  selection: Selection;
  onChange: (provider: ProviderId, model: string) => void;
}) {
  const value = `${selection.provider.id}::${selection.model.id}`;
  return (
    <select
      aria-label="Answer model"
      value={value}
      onChange={(event) => {
        const [provider, model] = event.target.value.split("::");
        onChange(provider as ProviderId, model);
      }}
      className="hidden max-w-56 rounded-lg border sm:block border-zinc-200 bg-white py-1.5 pr-7 pl-2.5 text-sm text-zinc-700 hover:border-zinc-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 focus:outline-none sm:max-w-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
    >
      {config.providers.map((p) => (
        <optgroup key={p.id} label={p.label}>
          {p.chat_models.map((m) => (
            <option key={m.id} value={`${p.id}::${m.id}`}>
              {m.label}
            </option>
          ))}
          {selection.custom && selection.provider.id === p.id && <option value={value}>{selection.model.id}</option>}
        </optgroup>
      ))}
    </select>
  );
}

function Thread({
  messages,
  streaming,
  children,
}: {
  messages: ChatMessage[];
  streaming: boolean;
  children: React.ReactNode;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  // Follow the answer as it streams, unless the reader has scrolled up.
  useEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (streaming) stick.current = true;
  }, [streaming]);

  return (
    <div
      ref={scroller}
      className="min-h-0 flex-1 overflow-y-auto"
      onScroll={(event) => {
        const el = event.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      }}
    >
      {messages.length === 0 ? (
        children
      ) : (
        <div className="mx-auto max-w-3xl space-y-6 px-4 py-6" aria-live="polite">
          {messages.map((message) => (
            <MessageView key={message.id} message={message} />
          ))}
        </div>
      )}
    </div>
  );
}

function CenteredNotice({
  icon,
  title,
  body,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  body: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="max-w-md text-center">
        <div className="mx-auto mb-3 flex size-11 items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-zinc-200 dark:bg-zinc-900 dark:ring-zinc-800">
          {icon}
        </div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <div className="mt-1.5 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{body}</div>
        {action && <div className="mt-5">{action}</div>}
      </div>
    </div>
  );
}

function Welcome({ config, onCreate }: { config: AppConfig; onCreate: () => void }) {
  const anyKey = config.providers.some((p) => p.requires_key && p.server_key);
  return (
    <CenteredNotice
      icon={<BookOpen className="size-5 text-indigo-600" />}
      title="Chat with your documents"
      body={
        <>
          <p>
            Create a knowledge base, upload PDFs, Word files, spreadsheets or notes, and ask questions. Answers are
            grounded in your files and cite the passages they come from.
          </p>
          {!anyKey && config.mock_enabled && (
            <p className="mt-3 rounded-lg bg-zinc-100 px-3 py-2 text-xs dark:bg-zinc-900">
              No API keys on the server: pick the Mock embedding model to try it offline, or add a key in Settings.
            </p>
          )}
        </>
      }
      action={
        <Button variant="primary" onClick={onCreate}>
          <Plus className="size-4" />
          Create a knowledge base
        </Button>
      }
    />
  );
}

function EmptyDocuments({ config, onFiles }: { config: AppConfig; onFiles: (files: File[]) => void }) {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <FilePicker
        extensions={config.limits.extensions}
        onFiles={onFiles}
        className="group flex w-full max-w-xl flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-zinc-300 bg-white px-6 py-12 text-center transition-colors hover:border-indigo-400 hover:bg-indigo-50/50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-indigo-500 dark:hover:bg-indigo-500/5"
      >
        <span className="flex size-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 group-hover:bg-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-300">
          <Upload className="size-5" />
        </span>
        <span className="text-base font-semibold text-zinc-900 dark:text-zinc-100">Add your first documents</span>
        <span className="text-sm text-zinc-500 dark:text-zinc-400">
          Drop files here or click to browse · {config.limits.extensions.join(" ")} · up to{" "}
          {config.limits.max_upload_mb} MB each
        </span>
      </FilePicker>
    </div>
  );
}

function EmptyChat({ onAsk, disabled }: { onAsk: (question: string) => void; disabled: boolean }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-5 p-6 text-center">
      <div>
        <h2 className="text-lg font-semibold">Ask anything about these documents</h2>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Every answer links back to the passages it used.
        </p>
      </div>
      <div className="flex max-w-xl flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((q) => (
          <button
            key={q}
            type="button"
            disabled={disabled}
            onClick={() => onAsk(q)}
            className="rounded-full bg-white px-3.5 py-1.5 text-sm text-zinc-700 ring-1 ring-zinc-200 hover:bg-indigo-50 hover:text-indigo-700 hover:ring-indigo-200 dark:bg-zinc-900 dark:text-zinc-300 dark:ring-zinc-700 dark:hover:bg-indigo-500/10 dark:hover:text-indigo-200"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
