import type { ApiKeys, AppConfig, DocumentItem, KnowledgeBase, ProviderId, SearchType, StreamEvent } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

// Keys typed into Settings travel with each request; the backend never stores them.
function keyHeaders(keys?: ApiKeys): Record<string, string> {
  const headers: Record<string, string> = {};
  if (keys?.openai.trim()) headers["X-OpenAI-Key"] = keys.openai.trim();
  if (keys?.anthropic.trim()) headers["X-Anthropic-Key"] = keys.anthropic.trim();
  if (keys?.google.trim()) headers["X-Google-Key"] = keys.google.trim();
  return headers;
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(`Can't reach the API at ${API_URL}. Is the backend running?`, 0);
  }
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  return response;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    // not JSON
  }
  return `Request failed (${response.status}).`;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await send(path, init)).json() as Promise<T>;
}

function jsonBody(method: string, body: unknown, keys?: ApiKeys): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json", ...keyHeaders(keys) },
    body: JSON.stringify(body),
  };
}

export const api = {
  config: () => json<AppConfig>("/api/config"),

  listKnowledgeBases: () => json<KnowledgeBase[]>("/api/knowledge-bases"),

  createKnowledgeBase: (body: {
    name: string;
    description: string;
    embedding_provider: ProviderId;
    embedding_model: string;
  }) => json<KnowledgeBase>("/api/knowledge-bases", jsonBody("POST", body)),

  deleteKnowledgeBase: async (id: string) => {
    await send(`/api/knowledge-bases/${id}`, { method: "DELETE" });
  },

  listDocuments: (kbId: string) => json<DocumentItem[]>(`/api/knowledge-bases/${kbId}/documents`),

  uploadDocument: (kbId: string, file: File, keys: ApiKeys) => {
    const form = new FormData();
    form.append("file", file);
    return json<DocumentItem>(`/api/knowledge-bases/${kbId}/documents`, {
      method: "POST",
      headers: keyHeaders(keys),
      body: form,
    });
  },

  deleteDocument: async (kbId: string, documentId: string) => {
    await send(`/api/knowledge-bases/${kbId}/documents/${documentId}`, { method: "DELETE" });
  },
};

export interface ChatRequestBody {
  knowledge_base_id: string;
  messages: { role: "user" | "assistant"; content: string }[];
  provider: ProviderId;
  model: string;
  temperature: number | null;
  top_k: number;
  search_type: SearchType;
}

/** POST /api/chat and hand each server-sent event to `onEvent` as it arrives. */
export async function streamChat(
  body: ChatRequestBody,
  keys: ApiKeys,
  signal: AbortSignal,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await send("/api/chat", { ...jsonBody("POST", body, keys), signal });
  if (!response.body) throw new ApiError("The server sent an empty response.", 502);

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = parseEvent(block);
      if (event) onEvent(event);
    }
  }
}

function parseEvent(block: string): StreamEvent | null {
  let name = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!data.length) return null;
  const payload = JSON.parse(data.join("\n"));
  switch (name) {
    case "sources":
      return { type: "sources", query: payload.query, sources: payload.sources };
    case "token":
      return { type: "token", text: payload.text };
    case "done":
      return { type: "done" };
    case "error":
      return { type: "error", message: payload.message };
    default:
      return null;
  }
}
