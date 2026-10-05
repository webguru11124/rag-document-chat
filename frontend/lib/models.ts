import type { ApiKeys, AppConfig, ChatModel, Preferences, Provider } from "./types";

export interface Selection {
  provider: Provider;
  model: ChatModel;
  custom: boolean;
}

/** The provider and model to chat with: the saved choice if it's still valid, else the server default. */
export function resolveSelection(config: AppConfig, prefs: Preferences): Selection {
  const saved = config.providers.find((p) => p.id === prefs.provider);
  const provider = saved ?? config.providers.find((p) => p.id === config.defaults.chat_provider) ?? config.providers[0];
  const wanted = saved ? prefs.model : config.defaults.chat_model;

  if (saved && prefs.useCustomModel && prefs.customModel.trim()) {
    return { provider, model: customModel(provider, prefs.customModel.trim()), custom: true };
  }
  const known = provider.chat_models.find((m) => m.id === wanted);
  return { provider, model: known ?? provider.chat_models[0], custom: false };
}

/** Mirrors the backend's rules for model IDs that aren't in the catalog. */
export function customModel(provider: Provider, id: string): ChatModel {
  const reasoning = provider.id === "openai" && /^(gpt-5|o1|o3|o4)/.test(id);
  return {
    id,
    label: id,
    provider: provider.id,
    temperature: provider.id === "google" || (provider.id === "openai" && !reasoning),
    reasoning,
    effort: false,
    fallbacks: false,
  };
}

export function hasKey(provider: Provider | undefined, keys: ApiKeys): boolean {
  if (!provider) return false;
  if (!provider.requires_key || provider.server_key) return true;
  return Boolean(keys[provider.id as keyof ApiKeys]?.trim());
}

export function modelNote(model: ChatModel): string | null {
  if (model.reasoning) return "Reasoning model: runs at low reasoning effort and ignores temperature.";
  if (model.effort) {
    return "Thinks at low effort and ignores temperature. If a safety check declines a request, the API retries it on a fallback model.";
  }
  if (model.provider === "anthropic") return "Uses the model's default sampling.";
  if (model.provider === "mock") return "Offline: quotes the best-matching sentences instead of generating an answer.";
  return null;
}
