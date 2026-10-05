"use client";

import { Check, KeyRound } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";

import { modelNote, resolveSelection } from "@/lib/models";
import type { ApiKeys, AppConfig, Preferences, ProviderId, SearchType } from "@/lib/types";
import { Button, Field, inputClass, Modal } from "./ui";

const CUSTOM = "__custom__";

export function SettingsDialog({
  open,
  config,
  prefs,
  setPrefs,
  onClose,
}: {
  open: boolean;
  config: AppConfig;
  prefs: Preferences;
  setPrefs: Dispatch<SetStateAction<Preferences>>;
  onClose: () => void;
}) {
  const { provider, model } = resolveSelection(config, prefs);
  const note = modelNote(model);

  const update = (patch: Partial<Preferences>) => setPrefs((p) => ({ ...p, ...patch }));
  const setKey = (id: keyof ApiKeys, value: string) => setPrefs((p) => ({ ...p, keys: { ...p.keys, [id]: value } }));

  return (
    <Modal
      open={open}
      title="Settings"
      onClose={onClose}
      footer={
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      }
    >
      <div className="space-y-8">
        <section className="space-y-4">
          <h3 className="text-sm font-semibold">Answer model</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Provider" htmlFor="set-provider">
              <select
                id="set-provider"
                className={inputClass}
                value={provider.id}
                onChange={(e) => {
                  const next = config.providers.find((p) => p.id === e.target.value);
                  update({
                    provider: e.target.value as ProviderId,
                    model: next?.chat_models[0]?.id ?? "",
                    useCustomModel: false,
                  });
                }}
              >
                {config.providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Model" htmlFor="set-model">
              <select
                id="set-model"
                className={inputClass}
                value={prefs.useCustomModel && provider.id === prefs.provider ? CUSTOM : model.id}
                onChange={(e) =>
                  e.target.value === CUSTOM
                    ? update({ provider: provider.id, useCustomModel: true })
                    : update({ provider: provider.id, model: e.target.value, useCustomModel: false })
                }
              >
                {provider.chat_models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
                {provider.id !== "mock" && <option value={CUSTOM}>Custom model ID…</option>}
              </select>
            </Field>
          </div>
          {prefs.useCustomModel && provider.id === prefs.provider && (
            <Field
              label="Custom model ID"
              htmlFor="set-custom"
              hint="Any model ID the provider accepts, for example a newer release."
            >
              <input
                id="set-custom"
                className={inputClass}
                value={prefs.customModel}
                onChange={(e) => update({ customModel: e.target.value })}
                placeholder="model-id"
                autoFocus
              />
            </Field>
          )}
          {note && <p className="text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">{note}</p>}
          <Field
            label={`Temperature · ${prefs.temperature.toFixed(1)}`}
            htmlFor="set-temperature"
            hint={
              model.temperature
                ? "Lower is more literal; higher is more varied."
                : "This model doesn't take a temperature."
            }
          >
            <input
              id="set-temperature"
              type="range"
              min={0}
              max={1}
              step={0.1}
              value={prefs.temperature}
              disabled={!model.temperature}
              onChange={(e) => update({ temperature: Number(e.target.value) })}
              className="w-full accent-indigo-600"
            />
          </Field>
        </section>

        <section className="space-y-4">
          <h3 className="text-sm font-semibold">Retrieval</h3>
          <Field
            label={`Passages per answer · ${prefs.topK}`}
            htmlFor="set-topk"
            hint="How many chunks are retrieved and sent to the model with each question."
          >
            <input
              id="set-topk"
              type="range"
              min={1}
              max={config.limits.max_top_k}
              value={prefs.topK}
              onChange={(e) => update({ topK: Number(e.target.value) })}
              className="w-full accent-indigo-600"
            />
          </Field>
          <Field
            label="Search"
            hint={
              prefs.searchType === "mmr"
                ? "Maximal marginal relevance: relevant passages that don't repeat each other."
                : "The most similar passages, even if they overlap."
            }
          >
            <div className="inline-flex rounded-lg bg-zinc-100 p-1 dark:bg-zinc-800" role="radiogroup">
              {(
                [
                  ["mmr", "Diverse (MMR)"],
                  ["similarity", "Most similar"],
                ] as [SearchType, string][]
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={prefs.searchType === value}
                  onClick={() => update({ searchType: value })}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                    prefs.searchType === value
                      ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-950 dark:text-zinc-100"
                      : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </Field>
        </section>

        <section className="space-y-4">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <KeyRound className="size-4 text-zinc-400" />
              API keys
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
              Kept in this browser only and sent with each request. The server never stores them. A key set on the
              server is used when the field is empty.
            </p>
          </div>
          {config.providers
            .filter((p) => p.requires_key)
            .map((p) => (
              <Field key={p.id} label={p.label} htmlFor={`key-${p.id}`}>
                <div className="relative">
                  <input
                    id={`key-${p.id}`}
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    className={`${inputClass} pr-28 font-mono`}
                    value={prefs.keys[p.id as keyof ApiKeys]}
                    onChange={(e) => setKey(p.id as keyof ApiKeys, e.target.value)}
                    placeholder={p.server_key ? "Using the server's key" : "Paste a key"}
                  />
                  {p.server_key && (
                    <span className="absolute top-1/2 right-2 inline-flex -translate-y-1/2 items-center gap-1 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
                      <Check className="size-3" />
                      Server key
                    </span>
                  )}
                </div>
              </Field>
            ))}
        </section>
      </div>
    </Modal>
  );
}
