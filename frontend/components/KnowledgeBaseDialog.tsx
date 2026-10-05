"use client";

import { LoaderCircle } from "lucide-react";
import { useState, type FormEvent } from "react";

import { hasKey } from "@/lib/models";
import type { ApiKeys, AppConfig, ProviderId } from "@/lib/types";
import { Button, Field, inputClass, Modal } from "./ui";

export interface NewKnowledgeBase {
  name: string;
  description: string;
  embedding_provider: ProviderId;
  embedding_model: string;
}

export function KnowledgeBaseDialog({
  open,
  config,
  keys,
  onClose,
  onCreate,
}: {
  open: boolean;
  config: AppConfig;
  keys: ApiKeys;
  onClose: () => void;
  onCreate: (body: NewKnowledgeBase) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [embedding, setEmbedding] = useState(
    `${config.defaults.embedding_provider}::${config.defaults.embedding_model}`,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [providerId, modelId] = embedding.split("::") as [ProviderId, string];
  const provider = config.providers.find((p) => p.id === providerId);
  const missingKey = !hasKey(provider, keys);

  const close = () => {
    setError(null);
    onClose();
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await onCreate({
        name: name.trim(),
        description: description.trim(),
        embedding_provider: providerId,
        embedding_model: modelId,
      });
      setName("");
      setDescription("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't create the knowledge base.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      title="New knowledge base"
      onClose={close}
      footer={
        <>
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="kb-form" disabled={busy || !name.trim()}>
            {busy && <LoaderCircle className="size-4 animate-spin" />}
            Create
          </Button>
        </>
      }
    >
      <form id="kb-form" onSubmit={submit} className="space-y-4">
        <Field label="Name" htmlFor="kb-name">
          <input
            id="kb-name"
            className={inputClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Product handbook"
            maxLength={80}
            autoFocus
            required
          />
        </Field>
        <Field label="Description" htmlFor="kb-description" hint="Optional. Shown under the title.">
          <input
            id="kb-description"
            className={inputClass}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What's in it?"
            maxLength={500}
          />
        </Field>
        <Field
          label="Embedding model"
          htmlFor="kb-embedding"
          hint={
            missingKey ? (
              <span className="text-amber-700 dark:text-amber-400">
                Uploading needs a {provider?.label} API key. Add one in Settings, or set it on the server.
              </span>
            ) : (
              "Fixed per knowledge base: every document in it is embedded with the same model."
            )
          }
        >
          <select
            id="kb-embedding"
            className={inputClass}
            value={embedding}
            onChange={(e) => setEmbedding(e.target.value)}
          >
            {config.providers
              .filter((p) => p.embedding_models.length)
              .map((p) => (
                <optgroup key={p.id} label={p.label}>
                  {p.embedding_models.map((m) => (
                    <option key={m.id} value={`${p.id}::${m.id}`}>
                      {m.label}
                    </option>
                  ))}
                </optgroup>
              ))}
          </select>
        </Field>
        {error && (
          <p
            role="alert"
            className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300"
          >
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
