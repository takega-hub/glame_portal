'use client';

import { useEffect, useMemo, useState } from 'react';
import { api, type OpenRouterModelInfo } from '@/lib/api';

type Mode = 'llm' | 'image';

type Option = {
  id: string;
  name: string;
  label: string;
  pricingLabel: string;
  contextLabel: string;
  provider: string;
};

type Props = {
  value?: string;
  onChange: (value: string) => void;
  mode?: Mode;
  label?: string;
  allowCustom?: boolean;
  disabled?: boolean;
  searchPlaceholder?: string;
  className?: string;
};

const TTL = 5 * 60 * 1000;
let llmCache: { ts: number; options: Option[] } | null = null;
let imageCache: { ts: number; options: Option[] } | null = null;

function pricePerM(v?: string | null) {
  if (v == null) return '—';
  const n = Number(v);
  if (Number.isFinite(n)) return `$${n}/M`;
  return `$${v}/M`;
}

function toOption(m: OpenRouterModelInfo): Option {
  const id = String(m.id || '');
  const name = String(m.name || id || 'Unknown');
  const provider = id.includes('/') ? id.split('/')[0] : 'unknown';
  const prompt = pricePerM(m.pricing?.prompt ?? null);
  const completion = pricePerM(m.pricing?.completion ?? null);
  const pricingLabel = `${prompt} in, ${completion} out`;
  const ctx = m.context_length ? `${m.context_length} ctx` : 'ctx —';
  const contextLabel = ctx;
  const label = `${name} (${id}) — ${pricingLabel} • ${contextLabel}`;
  return { id, name, label, pricingLabel, contextLabel, provider };
}

async function loadOptions(mode: Mode): Promise<Option[]> {
  if (mode === 'image') {
    const res = await api.getOpenRouterImageModels();
    return (res.models || [])
      .map(toOption)
      .filter((x) => x.id && x.id.includes('/'))
      .sort((a, b) => a.name.localeCompare(b.name));
  }
  const res = await api.getOpenRouterModels();
  return (res.models || [])
    .map(toOption)
    .filter((x) => x.id && x.id.includes('/'))
    .sort((a, b) => a.name.localeCompare(b.name));
}

export default function UnifiedModelSelect(props: Props) {
  const {
    value,
    onChange,
    mode = 'llm',
    label,
    allowCustom = true,
    disabled = false,
    searchPlaceholder = 'Поиск по названию или id',
    className,
  } = props;

  const [options, setOptions] = useState<Option[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [val, setVal] = useState(value || '');

  useEffect(() => setVal(value || ''), [value]);

  useEffect(() => {
    let stop = false;
    async function run() {
      setLoading(true);
      setError(null);
      try {
        const now = Date.now();
        if (mode === 'image' && imageCache && now - imageCache.ts < TTL) {
          if (!stop) setOptions(imageCache.options);
          return;
        }
        if (mode === 'llm' && llmCache && now - llmCache.ts < TTL) {
          if (!stop) setOptions(llmCache.options);
          return;
        }
        const opts = await loadOptions(mode);
        if (stop) return;
        setOptions(opts);
        const entry = { ts: now, options: opts };
        if (mode === 'image') imageCache = entry;
        else llmCache = entry;
      } catch (e: any) {
        if (stop) return;
        const msg = e?.response?.data?.detail || e?.message || 'Не удалось загрузить список моделей';
        setError(msg);
      } finally {
        if (!stop) setLoading(false);
      }
    }
    run();
    return () => {
      stop = true;
    };
  }, [mode]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => o.id.toLowerCase().includes(q) || o.name.toLowerCase().includes(q));
  }, [options, search]);

  const selected = useMemo(() => options.find((o) => o.id === val), [options, val]);

  const handle = (v: string) => {
    setVal(v);
    onChange(v);
  };

  return (
    <div className={className}>
      {label && <div className="block text-sm font-medium text-gray-700 mb-2">{label}</div>}
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
        value={val}
        onChange={(e) => handle(e.target.value)}
        disabled={disabled || (loading && options.length === 0)}
        className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
      >
        {(!val || options.length === 0) && (
          <option value="">
            {loading ? 'Загрузка моделей…' : 'Выберите модель'}
          </option>
        )}
        {filtered.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
        {allowCustom && <option value="__custom__">Другая модель (ввести вручную)</option>}
      </select>
      {selected && (
        <div className="mt-2 text-xs text-gray-500 space-y-1">
          <div>Название: <span className="font-medium">{selected.name}</span></div>
          <div>ID: <span className="font-mono break-all">{selected.id}</span></div>
          <div>Провайдер: {selected.provider}</div>
          <div>Контекст: {selected.contextLabel}</div>
          <div>Стоимость: {selected.pricingLabel}</div>
        </div>
      )}
    </div>
  );
}

