'use client';

import { useEffect, useMemo, useState } from 'react';
import { api, type OpenRouterModelInfo } from '@/lib/api';

type ModelSelectMode = 'llm' | 'image';

type ModelOption = {
  id: string;
  name: string;
  label: string;
  pricingLabel: string;
  contextLabel: string;
};

type ModelSelectProps = {
  value?: string;
  onChange: (value: string) => void;
  mode?: ModelSelectMode;
  label?: string;
  allowCustom?: boolean;
  disabled?: boolean;
  searchPlaceholder?: string;
};

const CACHE_TTL_MS = 5 * 60 * 1000;

let cachedLlmModels: { ts: number; models: ModelOption[] } | null = null;
let cachedImageModels: { ts: number; models: ModelOption[] } | null = null;

function formatPricePerM(value?: string | null) {
  if (value == null) return '—';
  const n = Number(value);
  if (Number.isFinite(n)) return `$${n}/M`;
  return `$${value}/M`;
}

function buildModelOption(model: OpenRouterModelInfo): ModelOption {
  const id = String(model.id || '');
  const name = String(model.name || id || 'Unknown');
  const prompt = formatPricePerM(model.pricing?.prompt ?? null);
  const completion = formatPricePerM(model.pricing?.completion ?? null);
  const pricingLabel = `${prompt} in, ${completion} out`;
  const ctx = model.context_length ? `${model.context_length} ctx` : 'ctx —';
  const contextLabel = ctx;
  const label = `${name} (${id}) — ${pricingLabel} • ${contextLabel}`;
  return { id, name, label, pricingLabel, contextLabel };
}

async function fetchModels(mode: ModelSelectMode): Promise<ModelOption[]> {
  if (mode === 'image') {
    const res = await api.getOpenRouterImageModels();
    const models = res.models || [];
    return models
      .map(buildModelOption)
      .filter((m) => m.id && m.id.includes('/'))
      .sort((a, b) => a.name.localeCompare(b.name));
  }
  const res = await api.getOpenRouterModels();
  const models = res.models || [];
  return models
    .map(buildModelOption)
    .filter((m) => m.id && m.id.includes('/'))
    .sort((a, b) => a.name.localeCompare(b.name));
}

export default function ModelSelect(props: ModelSelectProps) {
  const {
    value,
    onChange,
    mode = 'llm',
    label,
    allowCustom = false,
    disabled = false,
    searchPlaceholder = 'Поиск по названию или id (например: claude, gpt-4o, gemini...)',
  } = props;

  const [models, setModels] = useState<ModelOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [innerValue, setInnerValue] = useState<string>(value || '');

  useEffect(() => {
    setInnerValue(value || '');
  }, [value]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const now = Date.now();
        if (mode === 'image' && cachedImageModels && now - cachedImageModels.ts < CACHE_TTL_MS) {
          if (!cancelled) setModels(cachedImageModels.models);
          return;
        }
        if (mode === 'llm' && cachedLlmModels && now - cachedLlmModels.ts < CACHE_TTL_MS) {
          if (!cancelled) setModels(cachedLlmModels.models);
          return;
        }
        const opts = await fetchModels(mode);
        if (cancelled) return;
        setModels(opts);
        const entry = { ts: now, models: opts };
        if (mode === 'image') cachedImageModels = entry;
        else cachedLlmModels = entry;
      } catch (e: any) {
        if (cancelled) return;
        const detail = e?.response?.data?.detail || e?.message || 'Не удалось загрузить список моделей';
        setError(detail);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [mode]);

  const filteredModels = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return models;
    return models.filter((m) => m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q));
  }, [models, search]);

  const selectedOption = useMemo(
    () => models.find((m) => m.id === innerValue),
    [models, innerValue]
  );

  const handleChange = (next: string) => {
    setInnerValue(next);
    onChange(next);
  };

  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-gray-700 mb-2">
          {label}
        </label>
      )}
      {error && (
        <div className="mb-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-3">
          {error}
        </div>
      )}
      <div className="mb-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={searchPlaceholder}
          className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
          disabled={disabled}
        />
      </div>
      <select
        value={innerValue}
        onChange={(e) => handleChange(e.target.value)}
        disabled={disabled || (loading && models.length === 0)}
        className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
      >
        {(!innerValue || models.length === 0) && (
          <option value="">
            {loading ? 'Загрузка моделей…' : 'Выберите модель'}
          </option>
        )}
        {filteredModels.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label}
          </option>
        ))}
        {allowCustom && <option value="__custom__">Другая модель (ввести вручную)</option>}
      </select>
      {selectedOption && (
        <div className="mt-2 text-xs text-gray-500 space-y-1">
          <div>
            Название: <span className="font-medium">{selectedOption.name}</span>
          </div>
          <div>
            ID: <span className="font-mono break-all">{selectedOption.id}</span>
          </div>
          <div>Контекст: {selectedOption.contextLabel}</div>
          <div>Стоимость: {selectedOption.pricingLabel}</div>
        </div>
      )}
    </div>
  );
}

