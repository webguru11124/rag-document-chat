"use client";

import { FileSpreadsheet, FileText, LoaderCircle, TriangleAlert, Upload, X } from "lucide-react";
import { useRef } from "react";

import { extensionOf, formatBytes, pluralize } from "@/lib/format";
import type { DocumentItem } from "@/lib/types";

export interface UploadItem {
  id: string;
  name: string;
  status: "uploading" | "error";
  error?: string;
}

export function FilePicker({
  extensions,
  onFiles,
  children,
  className,
}: {
  extensions: string[];
  onFiles: (files: File[]) => void;
  children: React.ReactNode;
  className: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className={className} onClick={() => input.current?.click()}>
        {children}
      </button>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        accept={extensions.join(",")}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          event.target.value = "";
          if (files.length) onFiles(files);
        }}
      />
    </>
  );
}

function DocIcon({ filename }: { filename: string }) {
  const Icon = extensionOf(filename) === ".csv" ? FileSpreadsheet : FileText;
  return <Icon className="size-3.5 shrink-0 text-zinc-400" />;
}

export function DocumentsBar({
  documents,
  uploads,
  extensions,
  onUpload,
  onDelete,
  onDismissUpload,
}: {
  documents: DocumentItem[] | undefined;
  uploads: UploadItem[];
  extensions: string[];
  onUpload: (files: File[]) => void;
  onDelete: (doc: DocumentItem) => void;
  onDismissUpload: (id: string) => void;
}) {
  return (
    <section
      className="border-b border-zinc-200 bg-white/60 px-4 py-2.5 dark:border-zinc-800 dark:bg-zinc-900/40"
      aria-label="Documents"
    >
      <div className="flex items-center gap-3">
        <span className="shrink-0 text-xs font-medium text-zinc-500 dark:text-zinc-400">
          {documents ? pluralize(documents.length, "document") : "Documents"}
        </span>
        <ul className="flex min-w-0 flex-1 gap-1.5 overflow-x-auto py-0.5 [scrollbar-width:thin]">
          {uploads.map((upload) => (
            <li
              key={upload.id}
              title={upload.error}
              className={`flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-xs ring-1 ${
                upload.status === "error"
                  ? "bg-red-50 text-red-700 ring-red-200 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/30"
                  : "bg-indigo-50 text-indigo-700 ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-500/30"
              }`}
            >
              {upload.status === "uploading" ? (
                <LoaderCircle className="size-3.5 animate-spin" />
              ) : (
                <TriangleAlert className="size-3.5" />
              )}
              <span className="max-w-48 truncate">{upload.name}</span>
              {upload.status === "uploading" ? (
                <span className="text-indigo-500 dark:text-indigo-400">indexing…</span>
              ) : (
                <>
                  <span className="max-w-72 truncate">{upload.error}</span>
                  <button type="button" onClick={() => onDismissUpload(upload.id)} aria-label="Dismiss">
                    <X className="size-3.5" />
                  </button>
                </>
              )}
            </li>
          ))}
          {documents?.map((doc) => (
            <li
              key={doc.id}
              className="group flex shrink-0 items-center gap-1.5 rounded-md bg-white px-2 py-1 text-xs text-zinc-700 ring-1 ring-zinc-200 dark:bg-zinc-900 dark:text-zinc-300 dark:ring-zinc-700"
              title={`${formatBytes(doc.size_bytes)} · ${doc.pages ? `${pluralize(doc.pages, "page")} · ` : ""}${pluralize(doc.chunk_count, "chunk")}`}
            >
              <DocIcon filename={doc.filename} />
              <span className="max-w-48 truncate">{doc.filename}</span>
              <span className="text-zinc-400">{pluralize(doc.chunk_count, "chunk")}</span>
              <button
                type="button"
                onClick={() => onDelete(doc)}
                aria-label={`Remove ${doc.filename}`}
                className="rounded text-zinc-400 hover:text-red-600"
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
        <FilePicker
          extensions={extensions}
          onFiles={onUpload}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50 dark:text-indigo-300 dark:hover:bg-indigo-500/10"
        >
          <Upload className="size-3.5" />
          Add files
        </FilePicker>
      </div>
    </section>
  );
}
