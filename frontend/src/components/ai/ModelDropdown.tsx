'use client';

import { useEffect, useMemo, useState } from 'react';

type Category = 'dialog' | 'segmentation';

export type TaskType =
  | 'dialog'
  | 'segmentation'
  | 'content_plan'
  | 'customer_segmentation'
  | 'churn_prediction'
  | 'campaign_generation';

type OpenRouterModel = {
  id: string;
  name?: string | null;
  context_length?: number | null;
  pricing?: { prompt?: string | null; completion?: string | null } | null;
  type?: string | null;
};

type Props = {
  category: Category;
  taskType?: TaskType;
  label?: string;
  value?: string | null;
  onChange?: (model: string) => void;
  requireSelection?: boolean;
  storageKey?: string; // for local persistence override
};

const DIALOG_MODELS = [
  {
    id: 'openrouter/auto',
    label: 'openrouter-auto',
    hint:
      'Автоматический роутер OpenRouter: выбирает доступную подходящую модель и снижает риск ошибки “No endpoints found”.',
  },
  {
    id: 'openai/gpt-5.4',
    label: 'gpt-5.4',
    hint:
      'Сильная модель для стратегического диалога, сложного планирования и проверки решений директора.',
  },
  {
    id: 'deepseek/deepseek-v4-flash',
    label: 'deepseek-v4-flash',
    hint:
      'Быстрая модель для рабочих диалогов, уточнений, коротких планов и оперативных ответов агентов.',
  },
  {
    id: 'google/gemini-3.5-flash',
    label: 'gemini-3.5-flash',
    hint:
      'Быстрые ответы и хорошая обработка больших контекстов для ежедневной работы директора.',
  },
  {
    id: 'qwen/qwen3.5-flash-02-23',
    label: 'qwen3.5-flash',
    hint:
      'Экономичная быстрая модель для черновиков, рабочих сообщений и первичного анализа.',
  },
  {
    id: 'google/gemma-4-26b-a4b-it',
    label: 'gemma-4-26b-a4b-it',
    hint:
      'Инструкционная модель для объяснимых ответов, аккуратных резюме и рабочих рекомендаций.',
  },
  {
    id: 'meta-llama/llama-3.1-70b-instruct',
    label: 'llama-3.1‑70b',
    hint:
      'Высокое качество для диалогов и креатива. Оптимально для планирования задач и совместного обсуждения.',
  },
];

const SEGMENTATION_MODELS = [
  {
    id: 'openrouter/auto',
    label: 'openrouter-auto',
    hint:
      'Автоматический роутер OpenRouter для случаев, когда конкретная модель временно недоступна.',
  },
  {
    id: 'deepseek/deepseek-v4-flash',
    label: 'deepseek-v4-flash',
    hint:
      'Быстрая модель для первичного разбиения покупателей на сегменты и проверки гипотез.',
  },
  {
    id: 'google/gemini-3.5-flash',
    label: 'gemini-3.5-flash',
    hint:
      'Быстрая аналитика сегментов, сводки по большим наборам правил и объяснение критериев.',
  },
  {
    id: 'qwen/qwen3.5-flash-02-23',
    label: 'qwen3.5-flash',
    hint:
      'Экономичный вариант для массовых сегментационных черновиков и RFM-гипотез.',
  },
  {
    id: 'google/gemma-4-26b-a4b-it',
    label: 'gemma-4-26b-a4b-it',
    hint:
      'Объяснимые сегменты и понятные критерии отбора покупателей.',
  },
  {
    id: 'mistralai/mixtral-8x22b',
    label: 'mixtral‑large',
    hint:
      'Кластеризация и аналитика. Подходит для сегментации, RFM и ABC анализов на текстовых данных.',
  },
  {
    id: 'google/gemma-2-27b-it',
    label: 'gemma‑2‑27b',
    hint:
      'Быстрое моделирование гипотез сегментации и объяснимые инсайты. Хороший баланс цена/качество.',
  },
];

function recommendedFor(task?: TaskType, category?: Category): string {
  if (!category) return '';
  if (category === 'dialog') {
    // По умолчанию для диалогов
    switch (task) {
      case 'dialog':
      case 'campaign_generation':
      case 'content_plan':
        return DIALOG_MODELS[0].id; // llama
      default:
        return DIALOG_MODELS[0].id;
    }
  }
  // segmentation
  switch (task) {
    case 'segmentation':
    case 'customer_segmentation':
    case 'churn_prediction':
      return SEGMENTATION_MODELS[0].id; // mixtral
    default:
      return SEGMENTATION_MODELS[0].id;
  }
}

async function fetchOpenRouterModels(): Promise<OpenRouterModel[]> {
  const res = await fetch('/api/settings/openrouter/models', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || `OpenRouter models request failed with ${res.status}`);
  }
  const data = await res.json();
  return (data?.models ?? []) as OpenRouterModel[];
}

export default function ModelDropdown({
  category,
  taskType,
  label,
  value,
  onChange,
  requireSelection = true,
  storageKey,
}: Props) {
  const storage = storageKey ?? (category === 'dialog' ? 'ai_marketer_model_dialog' : 'ai_marketer_model_segmentation');
  const [models, setModels] = useState<OpenRouterModel[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  // Initial load/persist
  useEffect(() => {
    // Load persisted
    const saved = (typeof window !== 'undefined' && localStorage.getItem(storage)) || null;
    if (!value && saved) {
      setSelected(saved);
    } else if (value) {
      setSelected(value);
    }
  }, [value, storage]);

  // Fetch models (with graceful fallback)
  useEffect(() => {
    let mounted = true;
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const list = await fetchOpenRouterModels();
        if (!mounted) return;
        setModels(list);
        // If nothing selected, try to apply recommendation
        if (!selected) {
          const rec = recommendedFor(taskType, category);
          setSelected(rec);
        }
      } catch (e: any) {
        if (!mounted) return;
        // Fallback to static subset
        setError('Не удалось загрузить список моделей OpenRouter. Используется локальный список.');
        setModels(
          category === 'dialog'
            ? DIALOG_MODELS.map((m) => ({ id: m.id, name: m.label }))
            : SEGMENTATION_MODELS.map((m) => ({ id: m.id, name: m.label }))
        );
        if (!selected) {
          const rec = recommendedFor(taskType, category);
          setSelected(rec);
        }
      } finally {
        if (mounted) setLoading(false);
      }
    };
    run();
    return () => {
      mounted = false;
    };
  }, [category, taskType]);

  const options = useMemo(() => {
    const staticList = category === 'dialog' ? DIALOG_MODELS : SEGMENTATION_MODELS;
    const ids = new Set(staticList.map((m) => m.id));
    const enriched = (models ?? []).filter((m) => m?.id && ids.has(m.id));
    // Ensure both static models appear even if OpenRouter didn't return them (fallback from error path handles this too)
    staticList.forEach((s) => {
      if (!enriched.find((m) => m.id === s.id)) {
        enriched.push({ id: s.id, name: s.label });
      }
    });
    // Preserve order from static list
    return staticList.map((s) => ({
      id: s.id,
      label: s.label,
      hint: s.hint,
      info: enriched.find((m) => m.id === s.id) || { id: s.id },
    }));
  }, [models, category]);

  const recommendedId = useMemo(() => recommendedFor(taskType, category), [taskType, category]);
  const hasError = requireSelection && touched && !selected;

  function handleChange(next: string) {
    setSelected(next);
    setTouched(true);
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem(storage, next);
      }
    } catch {
      // ignore persistence errors
    }
    onChange?.(next);
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-gray-700">
          {label ?? (category === 'dialog' ? 'Модель для диалога' : 'Модель для сегментации')}
        </label>
        <div className="text-xs text-gray-500">
          {recommendedId ? (
            <span>
              Рекомендуется: <span className="font-semibold">{options.find((o) => o.id === recommendedId)?.label}</span>
            </span>
          ) : null}
        </div>
      </div>

      <div className="relative">
        <select
          value={selected ?? ''}
          onChange={(e) => handleChange(e.target.value)}
          onBlur={() => setTouched(true)}
          className={`w-full border rounded-lg px-3 py-2 bg-white ${
            hasError ? 'border-red-400' : 'border-gray-300'
          }`}
          disabled={loading}
        >
          <option value="" disabled>
            {loading ? 'Загрузка моделей…' : 'Выберите модель'}
          </option>
          {options.map((opt) => (
            <option key={opt.id} value={opt.id}>
              {opt.label} {opt.id === recommendedId ? '· Рекомендуется' : ''}
            </option>
          ))}
        </select>
        {loading ? (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 animate-pulse">…</div>
        ) : null}
      </div>

      {error ? <div className="text-xs text-amber-600">{error}</div> : null}
      {hasError ? <div className="text-xs text-red-600">Пожалуйста, выберите модель.</div> : null}

      <div className="space-y-2">
        {options.map((opt) => (
          <div
            key={opt.id}
            className="text-xs text-gray-600 bg-gray-50 border border-gray-200 rounded-lg p-2"
          >
            <div className="font-medium">
              {opt.label} {opt.id === recommendedId ? '· Рекомендуется для этой задачи' : ''}
            </div>
            <div className="mt-1">{category === 'dialog' ? DIALOG_MODELS.find(m => m.id === opt.id)?.hint : SEGMENTATION_MODELS.find(m => m.id === opt.id)?.hint}</div>
            {opt.info?.context_length ? (
              <div className="mt-1 text-gray-500">
                Контекст: {opt.info.context_length} токенов
              </div>
            ) : null}
            {opt.info?.pricing ? (
              <div className="mt-1 text-gray-500">
                Стоимость: prompt {opt.info.pricing?.prompt ?? '—'} · completion {opt.info.pricing?.completion ?? '—'}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
