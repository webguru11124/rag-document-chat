export type ProviderId = "openai" | "anthropic" | "google" | "mock";
export type SearchType = "similarity" | "mmr";

export interface ChatModel {
  id: string;
  label: string;
  provider: ProviderId;
  temperature: boolean;
  reasoning: boolean;
  effort: boolean;
  fallbacks: boolean;
}

export interface EmbeddingModel {
  id: string;
  label: string;
  provider: ProviderId;
  dimensions: number;
}

export interface Provider {
  id: ProviderId;
  label: string;
  requires_key: boolean;
  server_key: boolean;
  chat_models: ChatModel[];
  embedding_models: EmbeddingModel[];
}

export interface AppConfig {
  providers: Provider[];
  defaults: {
    chat_provider: ProviderId;
    chat_model: string;
    embedding_provider: ProviderId;
    embedding_model: string;
    top_k: number;
    search_type: SearchType;
  };
  limits: { max_upload_mb: number; max_top_k: number; extensions: string[] };
  mock_enabled: boolean;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  embedding_provider: ProviderId;
  embedding_model: string;
  created_at: string;
  document_count: number;
  chunk_count: number;
}

export interface DocumentItem {
  id: string;
  knowledge_base_id: string;
  filename: string;
  size_bytes: number;
  pages: number | null;
  chunk_count: number;
  characters: number;
  created_at: string;
}

export interface Source {
  number: number;
  document_id: string;
  filename: string;
  page: number | null;
  chunk_index: number;
  text: string;
  score: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "streaming" | "done" | "stopped" | "error";
  error?: string;
  sources?: Source[];
  query?: string;
  modelLabel?: string;
}

export interface ApiKeys {
  openai: string;
  anthropic: string;
  google: string;
}

export interface Preferences {
  keys: ApiKeys;
  provider: ProviderId | "";
  model: string;
  useCustomModel: boolean;
  customModel: string;
  temperature: number;
  topK: number;
  searchType: SearchType;
}

export type StreamEvent =
  | { type: "sources"; query: string; sources: Source[] }
  | { type: "token"; text: string }
  | { type: "done" }
  | { type: "error"; message: string };
