'use client';

import { useEffect, useMemo, useState, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { agentInteractions, adminCustomers, apiClient, customerSegmentation, type AgentInteractionTask } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  ArrowLeft,
  BarChart3,
  Calendar,
  CheckCircle2,
  ChevronDown,
  FileText,
  ListTodo,
  Paperclip,
  Send,
  Sparkles,
  Target,
  Users,
  Wand2,
} from 'lucide-react';
import { Reply, Trash2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

type AgentMode = 'auto' | 'planning' | 'action' | 'consultation';
type TaskSegmentSelection = { id?: string; name?: string; customer_count?: number } | null;

const TASK_STATUS_LABELS: Record<string, string> = {
  pending: 'Новая',
  validating: 'Проверка',
  validated: 'Проверена',
  pending_approval: 'На согласовании',
  approved: 'Одобрена',
  queued: 'В очереди',
  processing: 'В работе',
  completed: 'Завершена',
  failed: 'Ошибка',
  cancelled: 'Отменена',
  rejected: 'Отклонена',
  deleted: 'Удалена',
};

type ParsedBlock =
  | { type: 'heading'; level: 1 | 2 | 3 | 4; text: string }
  | { type: 'divider' }
  | { type: 'paragraph'; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'callout'; tone: 'info' | 'warn' | 'danger' | 'success'; title?: string; lines: string[] };

type PlanItem = {
  id: string;
  title: string;
  description: string;
  expectedResult: string;
  timeframe: string;
  children: PlanItem[];
};

function safeId(seed: string) {
  const raw = seed || String(Date.now());
  let h = 0;
  for (let i = 0; i < raw.length; i += 1) {
    h = (h << 5) - h + raw.charCodeAt(i);
    h |= 0;
  }
  return `id_${Math.abs(h)}`;
}

function normalizeText(input: string) {
  let t = (input || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  t = t.replace(/\s(#{2,4}\s+)/g, '\n$1');
  t = t.replace(/\s(KPI\s*[:：])/gi, '\n$1');
  t = t.replace(/\s(Важно\s*[:：])/gi, '\n$1');
  t = t.replace(/\s(Ошибка\s*[:：])/gi, '\n$1');
  t = t.replace(/\s(Предупреждение\s*[:：])/gi, '\n$1');
  return t;
}

function parseBlocks(input: string): ParsedBlock[] {
  const text = normalizeText(input).trim();
  if (!text) return [];
  const lines = text.split('\n');

  const blocks: ParsedBlock[] = [];
  let i = 0;

  const pushParagraph = (buf: string[]) => {
    const t = buf.join('\n').trim();
    if (t) blocks.push({ type: 'paragraph', text: t });
  };

  while (i < lines.length) {
    const line = lines[i] ?? '';
    const trimmed = line.trim();

    if (!trimmed) {
      i += 1;
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,4})\s+(.*)$/);
    if (headingMatch) {
      const level = headingMatch[1].length as 1 | 2 | 3 | 4;
      blocks.push({ type: 'heading', level, text: headingMatch[2].trim() });
      i += 1;
      continue;
    }

    if (/^(-{3,}|\*{3,})$/.test(trimmed)) {
      blocks.push({ type: 'divider' });
      i += 1;
      continue;
    }

    const calloutMatch = trimmed.match(/^(Важно|KPI|Ошибка|Предупреждение)\s*[:：]\s*(.*)$/i);
    if (calloutMatch) {
      const key = calloutMatch[1].toLowerCase();
      const tone: 'info' | 'warn' | 'danger' | 'success' =
        key.includes('ошиб') ? 'danger' : key.includes('предуп') ? 'warn' : key.includes('kpi') ? 'info' : 'info';
      const title = calloutMatch[1];
      const collected: string[] = [calloutMatch[2]].filter(Boolean);
      i += 1;
      while (i < lines.length && lines[i] && !lines[i].trim().match(/^(#{1,4})\s+/) && !lines[i].trim().match(/^\d+[\.\)]\s+/)) {
        const t = lines[i].trim();
        if (t) collected.push(t);
        i += 1;
      }
      blocks.push({ type: 'callout', tone, title, lines: collected });
      continue;
    }

    const ordered = trimmed.match(/^(\d+)[\.\)]\s+(.*)$/);
    const unordered = trimmed.match(/^[-•]\s+(.*)$/);
    if (ordered || unordered) {
      const isOrdered = Boolean(ordered);
      const items: string[] = [];
      while (i < lines.length) {
        const l = (lines[i] ?? '').trim();
        const o = l.match(/^(\d+)[\.\)]\s+(.*)$/);
        const u = l.match(/^[-•]\s+(.*)$/);
        if (isOrdered && o) {
          items.push(o[2].trim());
          i += 1;
          continue;
        }
        if (!isOrdered && u) {
          items.push(u[1].trim());
          i += 1;
          continue;
        }
        break;
      }
      blocks.push({ type: 'list', ordered: isOrdered, items });
      continue;
    }

    const buf: string[] = [];
    while (i < lines.length) {
      const l = lines[i] ?? '';
      const t = l.trim();
      if (!t) break;
      if (/^(#{1,4})\s+/.test(t)) break;
      if (/^(-{3,}|\*{3,})$/.test(t)) break;
      if (/^(\d+)[\.\)]\s+/.test(t)) break;
      if (/^[-•]\s+/.test(t)) break;
      buf.push(l);
      i += 1;
    }
    pushParagraph(buf);
  }

  return blocks;
}

function sectionKey(title: string) {
  const t = (title || '').toLowerCase();
  if (t.includes('парамет')) return 'params';
  if (t.includes('сегмент')) return 'segment';
  if (t.includes('контент')) return 'content';
  if (t.includes('kpi') || t.includes('метрик')) return 'kpi';
  if (t.includes('план') || t.includes('шаг')) return 'plan';
  if (t.includes('риск') || t.includes('ошиб')) return 'risk';
  return 'default';
}

function sectionMeta(key: ReturnType<typeof sectionKey>) {
  switch (key) {
    case 'plan':
      return { icon: ListTodo, accent: 'border-pink-300', bg: 'bg-pink-50', text: 'text-pink-800' };
    case 'kpi':
      return { icon: BarChart3, accent: 'border-indigo-300', bg: 'bg-indigo-50', text: 'text-indigo-800' };
    case 'segment':
      return { icon: Users, accent: 'border-cyan-300', bg: 'bg-cyan-50', text: 'text-cyan-800' };
    case 'content':
      return { icon: FileText, accent: 'border-amber-300', bg: 'bg-amber-50', text: 'text-amber-800' };
    case 'params':
      return { icon: Target, accent: 'border-slate-300', bg: 'bg-slate-50', text: 'text-slate-800' };
    case 'risk':
      return { icon: Wand2, accent: 'border-red-300', bg: 'bg-red-50', text: 'text-red-800' };
    default:
      return { icon: Sparkles, accent: 'border-gray-200', bg: 'bg-white', text: 'text-gray-800' };
  }
}

function extractTimeframe(text: string) {
  const s = (text || '').toLowerCase();
  const m1 = s.match(/\b(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b/);
  if (m1) return `${m1[1]}–${m1[2]} ${m1[3]}`;
  const m2 = s.match(/\b(\d{1,2})\s*(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b/);
  if (m2) return `${m2[1]} ${m2[2]}`;
  const m3 = s.match(/\b(сегодня|завтра|на этой неделе|на следующей неделе|в течение \d+\s*(дн(я|ей)|недел(и|ь)))\b/);
  if (m3) return m3[1];
  return '';
}

function buildPlan(blocks: ParsedBlock[], seed: string): PlanItem[] {
  const items: PlanItem[] = [];
  const listBlocks = blocks.filter((b) => b.type === 'list' && b.ordered) as Extract<ParsedBlock, { type: 'list' }>[]; // ordered only
  const source = listBlocks.length ? listBlocks[0].items : [];
  source.forEach((raw, idx) => {
    const title = raw.replace(/\*\*/g, '').trim();
    const timeframe = extractTimeframe(raw) || '';
    items.push({
      id: safeId(`${seed}_${idx}_${raw}`),
      title: title || `Шаг ${idx + 1}`,
      description: '',
      expectedResult: '',
      timeframe,
      children: [],
    });
  });
  return items;
}

function clampPct(n: number) {
  if (Number.isNaN(n)) return 0;
  if (n < 0) return 0;
  if (n > 100) return 100;
  return n;
}

function ModeBadge({ mode }: { mode: AgentMode }) {
  const meta = (() => {
    switch (mode) {
      case 'planning':
        return { label: 'Планирование', cls: 'bg-pink-50 text-pink-800 border-pink-200' };
      case 'action':
        return { label: 'Действие', cls: 'bg-blue-50 text-blue-800 border-blue-200' };
      case 'consultation':
        return { label: 'Консультация', cls: 'bg-amber-50 text-amber-800 border-amber-200' };
      case 'auto':
      default:
        return { label: 'Авто', cls: 'bg-slate-50 text-slate-800 border-slate-200' };
    }
  })();
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full border text-xs font-medium ${meta.cls}`}>
      <span className="inline-block w-1.5 h-1.5 rounded-full bg-current opacity-70" />
      {meta.label}
    </span>
  );
}

function ModeSwitcher({ value, onChange }: { value: AgentMode; onChange: (v: AgentMode) => void }) {
  const options: { value: AgentMode; label: string }[] = [
    { value: 'auto', label: 'Авто' },
    { value: 'planning', label: 'Планирование' },
    { value: 'action', label: 'Действие' },
    { value: 'consultation', label: 'Консультация' },
  ];
  const order: AgentMode[] = ['auto', 'planning', 'action', 'consultation'];
  return (
    <div
      className="flex items-center gap-1 rounded-lg border bg-white p-1 transition-colors duration-200"
      role="radiogroup"
      aria-label="Режим работы агента"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
        e.preventDefault();
        const idx = order.indexOf(value);
        const nextIdx = e.key === 'ArrowRight' ? (idx + 1) % order.length : (idx - 1 + order.length) % order.length;
        onChange(order[nextIdx]);
      }}
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt.value)}
            className={`px-2.5 py-1.5 text-xs rounded-md transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-500 ${
              active ? 'bg-pink-600 text-white shadow-sm' : 'text-gray-700 hover:bg-gray-50'
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function ProgressBar({ value, labelId }: { value: number; labelId?: string }) {
  const pct = clampPct(value);
  return (
    <div aria-labelledby={labelId} className="w-full">
      <div className="h-2 w-full rounded-full bg-gray-200">
        <div className="h-2 rounded-full bg-pink-600 transition-all duration-200" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function blocksToText(blocks: ParsedBlock[]) {
  const out: string[] = [];
  blocks.forEach((b) => {
    if (b.type === 'paragraph') out.push(b.text);
    if (b.type === 'list') out.push(b.items.join('\n'));
    if (b.type === 'callout') out.push([b.title || '', ...b.lines].filter(Boolean).join('\n'));
  });
  return out.join('\n').trim();
}

function looksLikeMassMailingPlan(title: string, blocks: ParsedBlock[]) {
  const src = `${title || ''}\n${blocksToText(blocks)}`.toLowerCase();
  return src.includes('массов') || src.includes('рассыл') || src.includes('sms') || src.includes('смс');
}

function extractContentHint(blocks: ParsedBlock[]) {
  // Берём текст из раздела "контент" если такой заголовок встречался
  const lines: string[] = [];
  let currentHeading: string | null = null;
  blocks.forEach((b) => {
    if (b.type === 'heading') {
      currentHeading = b.text.toLowerCase();
      return;
    }
    if (!currentHeading) return;
    const isContent = /контент|сообщен|формулировк|тон|tone|style|hook|pos/i.test(currentHeading);
    if (isContent) {
      if (b.type === 'paragraph') lines.push(b.text);
      if (b.type === 'list') lines.push(...b.items);
      if (b.type === 'callout') lines.push(...b.lines);
    }
  });
  return lines.join('\n').trim();
}

function ActionPlan({
  taskId,
  storageKey,
  title,
  blocks,
  onMetric,
}: {
  taskId: string;
  storageKey: string;
  title: string;
  blocks: ParsedBlock[];
  onMetric: (name: string, data?: Record<string, any>) => void;
}) {
  const initial = useMemo(() => {
    const plan = buildPlan(blocks, storageKey);
    const savedRaw = typeof window !== 'undefined' ? localStorage.getItem(storageKey) : null;
    if (!savedRaw) return { plan, done: {} as Record<string, boolean> };
    try {
      const parsed = JSON.parse(savedRaw) as { done?: Record<string, boolean> };
      return { plan, done: parsed?.done ?? {} };
    } catch {
      return { plan, done: {} as Record<string, boolean> };
    }
  }, [blocks, storageKey]);

  const [done, setDone] = useState<Record<string, boolean>>(initial.done);
  const total = initial.plan.length || 0;
  const completed = initial.plan.reduce((acc, item) => acc + (done[item.id] ? 1 : 0), 0);
  const pct = total ? (completed / total) * 100 : 0;
  const labelId = `${storageKey}_progress_label`;
  const planText = useMemo(() => blocksToText(blocks), [blocks]);
  const isMassMailing = useMemo(() => looksLikeMassMailingPlan(title, blocks), [title, blocks]);

  const [massPreparing, setMassPreparing] = useState(false);
  const [massRunning, setMassRunning] = useState(false);
  const [massError, setMassError] = useState<string | null>(null);
  const [massPrepared, setMassPrepared] = useState<any | null>(null);
  const [massRun, setMassRun] = useState<any | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify({ done }));
    } catch {
      // ignore
    }
  }, [done, storageKey]);

  if (!initial.plan.length) return null;

  return (
    <div className="mt-3 rounded-lg border bg-white">
      <div className="px-3 py-2 border-b flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ListTodo className="w-4 h-4 text-pink-700" aria-hidden="true" />
          <div className="text-sm font-semibold text-gray-900">{title || 'План действий'}</div>
        </div>
        <div className="flex items-center gap-2">
          <div id={labelId} className="text-xs text-gray-600">
            Прогресс: {Math.round(pct)}% ({completed}/{total})
          </div>
          <div className="w-28">
            <ProgressBar value={pct} labelId={labelId} />
          </div>
        </div>
      </div>

      <ol className="divide-y">
        {initial.plan.map((item, idx) => {
          const checked = Boolean(done[item.id]);
          return (
            <li key={item.id} className="px-3 py-2">
              <details
                className="group"
                open
                onToggle={() => onMetric('plan_toggle', { item: item.title, open: true })}
              >
                <summary className="flex items-start justify-between gap-3 cursor-pointer list-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-500 rounded-md px-1 py-1">
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 text-xs text-gray-500 w-5">{idx + 1}.</span>
                    <label className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => {
                          const next = e.target.checked;
                          setDone((d) => ({ ...d, [item.id]: next }));
                          onMetric('plan_check', { item: item.title, checked: next });
                        }}
                        className="mt-1 h-4 w-4 rounded border-gray-300 text-pink-600 focus:ring-pink-500"
                      />
                      <span className={`text-sm font-medium ${checked ? 'line-through text-gray-500' : 'text-gray-900'}`}>
                        {item.title}
                      </span>
                    </label>
                  </div>
                  <ChevronDown className="w-4 h-4 text-gray-500 transition-transform duration-200 group-open:rotate-180" aria-hidden="true" />
                </summary>

                <div className="mt-2 ml-7 space-y-2 text-sm leading-[1.65] text-gray-800">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <div className="rounded-md bg-gray-50 border px-2 py-1">
                      <div className="text-[11px] font-medium text-gray-600">Описание</div>
                      <div className="text-sm text-gray-800">{item.description || '—'}</div>
                    </div>
                    <div className="rounded-md bg-gray-50 border px-2 py-1">
                      <div className="text-[11px] font-medium text-gray-600">Ожидаемый результат</div>
                      <div className="text-sm text-gray-800">{item.expectedResult || '—'}</div>
                    </div>
                    <div className="rounded-md bg-gray-50 border px-2 py-1">
                      <div className="text-[11px] font-medium text-gray-600">Временные рамки</div>
                      <div className="flex items-center gap-1 text-sm text-gray-800">
                        <Calendar className="w-4 h-4 text-gray-500" aria-hidden="true" />
                        {item.timeframe || '—'}
                      </div>
                    </div>
                  </div>
                </div>
              </details>
            </li>
          );
        })}
      </ol>

      {isMassMailing ? (
        <div className="px-3 py-3 border-t space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              onClick={async () => {
                if (!taskId) return;
                setMassError(null);
                setMassRun(null);
                setMassPrepared(null);
                setMassPreparing(true);
                try {
                  const res = await agentInteractions.prepareMassMailing(taskId, {
                    plan_text: planText,
                    plan_title: title,
                  });
                  setMassPrepared(res);
                onMetric('mass_prepare', {
                  segment_id: res?.segment?.id,
                  segment_name: res?.segment?.name,
                  customer_count: res?.segment?.customer_count,
                  event_type: res?.suggested_request?.event?.type,
                });
                } catch (e: any) {
                  const message = e?.response?.data?.detail || e?.message || 'Не удалось подготовить массовую генерацию';
                  setMassError(String(message));
                  onMetric('mass_prepare_error', { message: String(message) });
                } finally {
                  setMassPreparing(false);
                }
              }}
              disabled={massPreparing || massRunning}
              className="bg-pink-600 hover:bg-pink-700"
            >
              {massPreparing ? 'Подготовка…' : 'Выполнить действия по плану'}
            </Button>
            {massPrepared?.segment?.name ? (
              <div className="text-xs text-gray-600">
                Сегмент: <span className="font-medium text-gray-900">{massPrepared.segment.name}</span>
              </div>
            ) : null}
          </div>

          {massError ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 whitespace-pre-wrap">
              {massError}
            </div>
          ) : null}

          {massPrepared?.report ? (
            <div className="rounded-lg border bg-gray-50 px-3 py-2">
              <div className="text-xs font-semibold text-gray-700">Отчёт</div>
              <div className="mt-1 text-sm text-gray-900 whitespace-pre-wrap leading-[1.65]">{massPrepared.report}</div>
            </div>
          ) : null}

          {massPrepared?.segment?.id && massPrepared?.suggested_request?.event?.type ? (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={async () => {
                  setMassError(null);
                  setMassRun(null);
                  setMassRunning(true);
                  try {
                    const res = await agentInteractions.runMassMailing(taskId, {
                      segment_id: massPrepared.segment.id,
                      event_type: massPrepared.suggested_request.event.type,
                      brand: massPrepared.suggested_request.brand || 'GLAME',
                      message_count: massPrepared.suggested_request.limit,
                      auto_detect_store: Boolean(massPrepared.suggested_request.auto_detect_store),
                      metadata: massPrepared.suggested_request.event.metadata || {},
                    });
                    setMassRun(res);
                    onMetric('mass_run', { generation_id: res?.generation_id });
                  } catch (e: any) {
                    const message = e?.response?.data?.detail || e?.message || 'Не удалось запустить массовую генерацию';
                    setMassError(String(message));
                    onMetric('mass_run_error', { message: String(message) });
                  } finally {
                    setMassRunning(false);
                  }
                }}
                disabled={massPreparing || massRunning}
              >
                {massRunning ? 'Запуск…' : 'Запустить массовую генерацию'}
              </Button>
              {massRun?.generation_id ? (
                <div className="text-xs text-gray-600">
                  generation_id: <span className="font-mono text-gray-900">{massRun.generation_id}</span>
                </div>
              ) : null}
              {massRun?.generation_id ? (
                <a
                  href="/admin/batch-messages"
                  className="text-xs text-pink-700 hover:text-pink-800 underline underline-offset-2"
                  onClick={() => onMetric('mass_open_batch_messages')}
                >
                  Открыть массовую генерацию
                </a>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function AgentContent({
  taskId,
  content,
  storageSeed,
  onMetric,
}: {
  taskId: string;
  content: string;
  storageSeed: string;
  onMetric: (name: string, data?: Record<string, any>) => void;
}) {
  const blocks = useMemo(() => parseBlocks(content), [content]);
  const sections = useMemo(() => {
    const out: { title: string; key: string; blocks: ParsedBlock[] }[] = [];
    let currentTitle = '';
    let buf: ParsedBlock[] = [];
    const flush = () => {
      if (!buf.length) return;
      const title = currentTitle || 'Ответ';
      out.push({ title, key: sectionKey(title), blocks: buf });
      buf = [];
    };
    blocks.forEach((b) => {
      if (b.type === 'heading') {
        flush();
        currentTitle = b.text || 'Раздел';
        return;
      }
      buf.push(b);
    });
    flush();
    return out;
  }, [blocks]);

  const [segLoading, setSegLoading] = useState(false);
  const [segError, setSegError] = useState<string | null>(null);
  const [segPrepared, setSegPrepared] = useState<any | null>(null);
  const [totalCustomers, setTotalCustomers] = useState<number | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewUsers, setPreviewUsers] = useState<any[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [removingUserId, setRemovingUserId] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    async function loadTotal() {
      try {
        const o = await adminCustomers.getOverview();
        if (!ignore) setTotalCustomers(o.total_customers || 0);
      } catch {
        if (!ignore) setTotalCustomers(null);
      }
    }
    loadTotal();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    let ignore = false;
    async function loadBoundSegment() {
      try {
        const segment = await agentInteractions.getTaskSegment(taskId);
        if (ignore || !segment?.id) return;
        setSegPrepared((prev: any) => ({
          ...(prev || {}),
          segment: {
            id: segment.id,
            name: segment.name || 'Сегмент AI CRM',
            customer_count: Number(segment.customer_count || 0),
          },
        }));
      } catch {
        // Сегмент может быть еще не привязан к задаче.
      }
    }
    loadBoundSegment();
    return () => {
      ignore = true;
    };
  }, [taskId]);

  async function handleSegmentationRun(title: string, segBlocks: ParsedBlock[]) {
    setSegError(null);
    setSegPrepared(null);
    setSegLoading(true);
    try {
      const res = await agentInteractions.prepareMassMailing(taskId, {
        plan_text: blocksToText(segBlocks),
        plan_title: title,
      });
      setSegPrepared(res);
      onMetric('segmentation_prepare', {
        segment_id: res?.segment?.id,
        segment_name: res?.segment?.name,
        customer_count: res?.segment?.customer_count,
      });
    } catch (e: any) {
      const message = e?.response?.data?.detail || e?.message || 'Не удалось выполнить сегментацию';
      setSegError(String(message));
      onMetric('segmentation_prepare_error', { message: String(message) });
    } finally {
      setSegLoading(false);
    }
  }

  async function openPreview() {
    if (!segPrepared?.segment?.id) return;
    setPreviewLoading(true);
    setPreviewUsers([]);
    setPreviewOpen(true);
    try {
      const r = await apiClient.get(`/api/customer-segmentation/segments/${segPrepared.segment.id}/users`);
      setPreviewUsers(r.data?.users || []);
    } catch (e: any) {
      try {
        if (e?.response?.status === 404) {
          const r2 = await apiClient.get(`/api/admin/customers/segments/${segPrepared.segment.id}/users`);
          setPreviewUsers(r2.data?.users || []);
        } else {
          setPreviewUsers([]);
        }
      } catch {
        setPreviewUsers([]);
      }
    } finally {
      setPreviewLoading(false);
    }
  }

  async function removeUserFromSegment(userId: string) {
    if (!segPrepared?.segment?.id) return;
    setRemovingUserId(userId);
    try {
      await apiClient.delete(`/api/customer-segmentation/segments/${segPrepared.segment.id}/users/${userId}`);
      setPreviewUsers((prev) => prev.filter((u) => u.id !== userId));
      onMetric('segmentation_remove_user', { user_id: userId });
    } catch {
    } finally {
      setRemovingUserId(null);
    }
  }

  if (!content) return null;

  return (
    <div className="space-y-3">
      {sections.map((s, idx) => {
        const meta = sectionMeta(s.key as any);
        const Icon = meta.icon;
        const sectionId = `${storageSeed}_sec_${idx}`;
        return (
          <details
            key={sectionId}
            className={`group rounded-lg border ${meta.accent} ${meta.bg} overflow-hidden`}
            open={idx === 0}
            onToggle={(e) => onMetric('section_toggle', { title: s.title, open: (e.currentTarget as HTMLDetailsElement).open })}
          >
            <summary className="flex items-center justify-between gap-3 px-3 py-2 cursor-pointer list-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-500">
              <div className={`flex items-center gap-2 ${meta.text}`}>
                <Icon className="w-4 h-4" aria-hidden="true" />
                <div className="font-semibold text-sm">{s.title}</div>
              </div>
              <ChevronDown className="w-4 h-4 text-gray-600 transition-transform duration-200 group-open:rotate-180" aria-hidden="true" />
            </summary>
            <div className="px-3 pb-3 bg-white/70">
              <div className="pt-2 space-y-2 text-[15px] leading-[1.7] text-gray-900">
                {s.blocks.map((b, bi) => {
                  if (b.type === 'divider') return <div key={bi} className="border-t my-2" />;
                  if (b.type === 'paragraph') return <p key={bi} className="whitespace-pre-wrap">{b.text}</p>;
                  if (b.type === 'list') {
                    const Tag = b.ordered ? 'ol' : 'ul';
                    return (
                      <Tag key={bi} className={`${b.ordered ? 'list-decimal' : 'list-disc'} pl-5 space-y-1`}>
                        {b.items.map((it, ii) => (
                          <li key={ii} className="whitespace-pre-wrap">{it}</li>
                        ))}
                      </Tag>
                    );
                  }
                  if (b.type === 'callout') {
                    const toneCls =
                      b.tone === 'danger'
                        ? 'border-red-200 bg-red-50 text-red-900'
                        : b.tone === 'warn'
                          ? 'border-amber-200 bg-amber-50 text-amber-900'
                          : b.tone === 'success'
                            ? 'border-green-200 bg-green-50 text-green-900'
                            : 'border-blue-200 bg-blue-50 text-blue-900';
                    const ToneIcon = b.tone === 'danger' ? Wand2 : b.tone === 'warn' ? Wand2 : b.tone === 'success' ? CheckCircle2 : Sparkles;
                    return (
                      <div key={bi} className={`rounded-lg border px-3 py-2 ${toneCls}`}>
                        <div className="flex items-center gap-2 font-semibold text-sm">
                          <ToneIcon className="w-4 h-4" aria-hidden="true" />
                          {b.title || 'Информация'}
                        </div>
                        <div className="mt-1 text-sm leading-[1.65] space-y-1">
                          {b.lines.map((l, li) => (
                            <div key={li} className="whitespace-pre-wrap">{l}</div>
                          ))}
                        </div>
                      </div>
                    );
                  }
                  return null;
                })}
              </div>

              {s.key === 'plan' ? (
                <ActionPlan taskId={taskId} storageKey={`${storageSeed}_plan`} title={s.title} blocks={s.blocks} onMetric={onMetric} />
              ) : null}

              {s.key === 'segment' ? (
                <div className="mt-3 rounded-lg border bg-white">
                  <div className="px-3 py-2 border-b flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <Users className="w-4 h-4 text-cyan-700" aria-hidden="true" />
                      <div className="text-sm font-semibold text-gray-900">Сегментация аудитории</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleSegmentationRun(s.title, s.blocks)}
                        disabled={segLoading}
                        className="px-3 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                      >
                        {segLoading ? 'Сегментация…' : 'Сегментация'}
                      </button>
                      {segPrepared?.segment?.name ? (
                        <div className="text-xs text-gray-600">
                          Сегмент: <span className="font-medium text-gray-900">{segPrepared.segment.name}</span>
                        </div>
                      ) : null}
                    </div>
                  </div>
                  <div className="px-3 py-3 space-y-2">
                    {segError ? (
                      <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 whitespace-pre-wrap">
                        {segError}
                      </div>
                    ) : null}
                    {segPrepared?.segment ? (
                      <div className="flex flex-wrap items-center gap-3 text-sm">
                        <div className="rounded bg-cyan-50 text-cyan-900 border border-cyan-200 px-2 py-1">
                          Найдено: <span className="font-semibold">{segPrepared.segment.customer_count}</span>
                        </div>
                        {typeof totalCustomers === 'number' && totalCustomers > 0 ? (
                          <div className="rounded bg-gray-50 text-gray-900 border px-2 py-1">
                            {Math.round((segPrepared.segment.customer_count / totalCustomers) * 1000) / 10}% от базы
                          </div>
                        ) : null}
                        <button
                          type="button"
                          className="ml-auto px-3 py-1.5 rounded-md border text-gray-800 hover:bg-gray-50"
                          onClick={openPreview}
                        >
                          Предпросмотр
                        </button>
                      </div>
                    ) : (
                      <div className="text-sm text-gray-600">Нажмите «Сегментация», чтобы подобрать получателей.</div>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </details>
        );
      })}

      {previewOpen ? (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] flex flex-col">
            <div className="p-4 border-b flex items-center justify-between">
              <div className="text-lg font-semibold text-gray-900">Предпросмотр сегмента</div>
              <button
                type="button"
                onClick={() => setPreviewOpen(false)}
                className="px-3 py-1.5 rounded-md border hover:bg-gray-50"
              >
                Закрыть
              </button>
            </div>
            <div className="p-4 overflow-auto">
              {previewLoading ? (
                <div className="text-center py-8 text-sm text-gray-600">Загрузка…</div>
              ) : previewUsers.length ? (
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-sm font-semibold text-gray-900">Имя</th>
                      <th className="px-3 py-2 text-left text-sm font-semibold text-gray-900">Предпочитаемый магазин</th>
                      <th className="px-3 py-2 text-left text-sm font-semibold text-gray-900">Телефон</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white">
                    {previewUsers.map((u) => (
                      <tr key={u.id}>
                        <td className="px-3 py-2 text-sm text-gray-900">{u.full_name}</td>
                        <td className="px-3 py-2 text-sm text-gray-700">{u.preferred_store_name || u.preferred_store || '—'}</td>
                        <td className="px-3 py-2 text-sm text-gray-700">{u.phone}</td>
                        <td className="px-3 py-2 text-right">
                          <button
                            type="button"
                            onClick={() => removeUserFromSegment(u.id)}
                            disabled={removingUserId === u.id}
                            className="text-red-600 hover:text-red-800 disabled:opacity-50 text-sm"
                          >
                            {removingUserId === u.id ? 'Удаление…' : 'Удалить'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="text-center py-8 text-sm text-gray-600">Пользователи не найдены.</div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function humanizeRules(rules: any): string[] {
  try {
    const out: string[] = [];
    const walk = (node: any) => {
      if (!node) return;
      if (Array.isArray(node.filters)) {
        node.filters.forEach((f: any) => walk(f));
        return;
      }
      if (node.field && node.operator) {
        const field = String(node.field);
        const op = String(node.operator);
        const value = node.value;
        const v = Array.isArray(value) ? value.join(', ') : String(value);
        out.push(`${field} ${op} ${v}`);
      }
    };
    walk(rules);
    return out.length ? out : ['Правила сегментации отсутствуют'];
  } catch {
    return ['Правила сегментации отсутствуют'];
  }
}

function toLocalInputValue(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (v: number) => String(v).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function TaskPassport({
  task,
  onSaved,
  onAction,
}: {
  task: AgentInteractionTask;
  onSaved: (task: AgentInteractionTask) => void | Promise<void>;
  onAction: (action: 'approve' | 'reject' | 'revise' | 'queue' | 'process' | 'cancel' | 'complete') => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(() => ({
    title: task.input_data?.title || '',
    description: task.input_data?.description || '',
    expected_result: task.input_data?.expected_result || '',
    result: task.input_data?.result || task.output_data?.result || '',
    next_step: task.input_data?.next_step || '',
    campaign: task.input_data?.campaign || '',
    city: task.input_data?.city || task.input_data?.city_context || '',
    dna: task.input_data?.dna || '',
    channel: task.input_data?.channel || '',
    platform: task.input_data?.platform || '',
    assigned_human: task.input_data?.assigned_human || '',
    priority: String(task.priority || 3),
    deadline_at: toLocalInputValue(task.deadline_at),
    attachments_text: Array.isArray(task.input_data?.attachments)
      ? task.input_data.attachments.map((a: any) => a?.url || a?.href || '').filter(Boolean).join('\n')
      : '',
  }));

  useEffect(() => {
    setForm({
      title: task.input_data?.title || '',
      description: task.input_data?.description || '',
      expected_result: task.input_data?.expected_result || '',
      result: task.input_data?.result || task.output_data?.result || '',
      next_step: task.input_data?.next_step || '',
      campaign: task.input_data?.campaign || '',
      city: task.input_data?.city || task.input_data?.city_context || '',
      dna: task.input_data?.dna || '',
      channel: task.input_data?.channel || '',
      platform: task.input_data?.platform || '',
      assigned_human: task.input_data?.assigned_human || '',
      priority: String(task.priority || 3),
      deadline_at: toLocalInputValue(task.deadline_at),
      attachments_text: Array.isArray(task.input_data?.attachments)
        ? task.input_data.attachments.map((a: any) => a?.url || a?.href || '').filter(Boolean).join('\n')
        : '',
    });
  }, [task]);

  const attachments = Array.isArray(task.input_data?.attachments) ? task.input_data.attachments : [];
  const canApproval = ['pending', 'validated', 'pending_approval'].includes(task.status);
  const canQueue = task.status === 'approved';
  const canProcess = ['queued', 'approved'].includes(task.status);
  const canComplete = !['completed', 'failed', 'cancelled', 'rejected', 'deleted'].includes(task.status);

  async function save() {
    setSaving(true);
    try {
      const links = form.attachments_text
        .split('\n')
        .map((x) => x.trim())
        .filter(Boolean)
        .map((url) => ({ type: 'link', url }));
      const updated = await agentInteractions.updateTask(task.id, {
        priority: Number(form.priority || 3),
        deadline_at: form.deadline_at ? new Date(form.deadline_at).toISOString() : undefined,
        input_data: {
          ...(task.input_data || {}),
          title: form.title,
          description: form.description,
          expected_result: form.expected_result,
          result: form.result,
          next_step: form.next_step,
          campaign: form.campaign || undefined,
          city: form.city || undefined,
          dna: form.dna || undefined,
          channel: form.channel || undefined,
          platform: form.platform || undefined,
          assigned_human: form.assigned_human || undefined,
          attachments: links,
        },
        task_context: {
          ...(task.task_context || {}),
          edited_from_task_detail: true,
        },
      });
      await onSaved(updated);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle>Паспорт задачи</CardTitle>
          <Button size="sm" variant="outline" onClick={() => setEditing((v) => !v)}>
            {editing ? 'Закрыть' : 'Редактировать'}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <span className="px-2 py-1 rounded bg-gray-100 text-xs text-gray-700">{TASK_STATUS_LABELS[task.status] || task.status}</span>
          <span className="px-2 py-1 rounded bg-gray-100 text-xs text-gray-700">P{Math.max(0, Number(task.priority || 3) - 1)}</span>
          {task.input_data?.risk_level && <span className="px-2 py-1 rounded bg-orange-50 text-xs text-orange-700">{task.input_data.risk_level}-risk</span>}
          {task.input_data?.campaign && <span className="px-2 py-1 rounded bg-pink-50 text-xs text-pink-700">{task.input_data.campaign}</span>}
          {task.input_data?.city && <span className="px-2 py-1 rounded bg-blue-50 text-xs text-blue-700">{task.input_data.city}</span>}
          {task.input_data?.dna && <span className="px-2 py-1 rounded bg-purple-50 text-xs text-purple-700">{task.input_data.dna}</span>}
        </div>

        {!editing ? (
          <div className="space-y-3 text-sm">
            <InfoRow label="Описание" value={task.input_data?.description || '—'} />
            <InfoRow label="Ответственный" value={task.input_data?.assigned_human || '—'} />
            <InfoRow label="Дедлайн" value={task.deadline_at ? new Date(task.deadline_at).toLocaleString('ru-RU') : '—'} />
            <InfoRow label="Ожидаемый результат" value={task.input_data?.expected_result || '—'} />
            <InfoRow label="Результат" value={task.input_data?.result || task.output_data?.result || '—'} />
            <InfoRow label="Следующий шаг" value={task.input_data?.next_step || '—'} />
            <InfoRow label="Канал / платформа" value={[task.input_data?.channel, task.input_data?.platform].filter(Boolean).join(' / ') || '—'} />
            {attachments.length > 0 ? (
              <div>
                <div className="text-xs font-medium text-gray-500 mb-1">Материалы</div>
                <div className="space-y-1">
                  {attachments.map((a: any, idx: number) => (
                    <a key={idx} href={a.url || a.href} target="_blank" rel="noreferrer" className="block text-pink-700 hover:text-pink-800 truncate">
                      {a.url || a.href}
                    </a>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="space-y-3">
            <input className="w-full border rounded-lg px-3 py-2" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="Название" />
            <textarea className="w-full border rounded-lg px-3 py-2" rows={3} value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} placeholder="Описание" />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <select className="border rounded-lg px-3 py-2" value={form.priority} onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}>
                <option value="1">P0 - критично</option>
                <option value="2">P1 - высокий</option>
                <option value="3">P2 - плановый</option>
                <option value="4">P3 - опционально</option>
              </select>
              <input type="datetime-local" className="border rounded-lg px-3 py-2" value={form.deadline_at} onChange={(e) => setForm((f) => ({ ...f, deadline_at: e.target.value }))} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <input className="border rounded-lg px-3 py-2" value={form.campaign} onChange={(e) => setForm((f) => ({ ...f, campaign: e.target.value }))} placeholder="Кампания" />
              <input className="border rounded-lg px-3 py-2" value={form.assigned_human} onChange={(e) => setForm((f) => ({ ...f, assigned_human: e.target.value }))} placeholder="Ответственный" />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <select className="border rounded-lg px-3 py-2" value={form.city} onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))}>
                <option value="">Город</option>
                <option value="simferopol">Симферополь</option>
                <option value="yalta">Ялта</option>
                <option value="both">Оба</option>
              </select>
              <select className="border rounded-lg px-3 py-2" value={form.dna} onChange={(e) => setForm((f) => ({ ...f, dna: e.target.value }))}>
                <option value="">DNA</option>
                <option value="classic">Classic</option>
                <option value="dramatic">Dramatic</option>
                <option value="romantic">Romantic</option>
                <option value="naturalistic">Naturalistic</option>
              </select>
              <input className="border rounded-lg px-3 py-2" value={form.channel} onChange={(e) => setForm((f) => ({ ...f, channel: e.target.value }))} placeholder="Канал" />
            </div>
            <input className="w-full border rounded-lg px-3 py-2" value={form.platform} onChange={(e) => setForm((f) => ({ ...f, platform: e.target.value }))} placeholder="Платформа" />
            <input className="w-full border rounded-lg px-3 py-2" value={form.expected_result} onChange={(e) => setForm((f) => ({ ...f, expected_result: e.target.value }))} placeholder="Ожидаемый результат" />
            <input className="w-full border rounded-lg px-3 py-2" value={form.result} onChange={(e) => setForm((f) => ({ ...f, result: e.target.value }))} placeholder="Факт / результат" />
            <input className="w-full border rounded-lg px-3 py-2" value={form.next_step} onChange={(e) => setForm((f) => ({ ...f, next_step: e.target.value }))} placeholder="Следующий шаг" />
            <textarea className="w-full border rounded-lg px-3 py-2" rows={2} value={form.attachments_text} onChange={(e) => setForm((f) => ({ ...f, attachments_text: e.target.value }))} placeholder="Ссылки, каждая с новой строки" />
            <Button onClick={save} disabled={saving} className="w-full">{saving ? 'Сохранение…' : 'Сохранить паспорт'}</Button>
          </div>
        )}

        <div className="grid grid-cols-2 gap-2 pt-2 border-t">
          {canApproval && <Button size="sm" className="bg-green-600 hover:bg-green-700" onClick={() => onAction('approve')}>Approve</Button>}
          {canApproval && <Button size="sm" variant="destructive" onClick={() => onAction('reject')}>Reject</Button>}
          {canApproval && <Button size="sm" variant="outline" onClick={() => onAction('revise')}>Revise</Button>}
          {canQueue && <Button size="sm" variant="outline" onClick={() => onAction('queue')}>Queue</Button>}
          {canProcess && <Button size="sm" onClick={() => onAction('process')}>Process</Button>}
          {canComplete && <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" onClick={() => onAction('complete')}>Завершить</Button>}
          {canComplete && <Button size="sm" variant="outline" onClick={() => onAction('cancel')}>Cancel</Button>}
        </div>
      </CardContent>
    </Card>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium text-gray-500">{label}</div>
      <div className="text-gray-900 whitespace-pre-wrap">{value}</div>
    </div>
  );
}

function PlanSidebar({
  taskId,
  taskTitle,
  latestAssistantText,
  refreshToken,
  onMetric,
  onSegmentSelected,
}: {
  taskId: string;
  taskTitle: string;
  latestAssistantText: string | null;
  refreshToken: string | number | null;
  onMetric: (name: string, data?: Record<string, any>) => void;
  onSegmentSelected?: (segment: TaskSegmentSelection) => void;
}) {
  const blocks = useMemo(() => parseBlocks(latestAssistantText || ''), [latestAssistantText]);
  const planText = useMemo(() => blocksToText(blocks), [blocks]);
  const isMassMailing = useMemo(() => looksLikeMassMailingPlan(taskTitle, blocks), [taskTitle, blocks]);
  const [promptHint, setPromptHint] = useState<string>(() => extractContentHint(blocks));
  useEffect(() => {
    setPromptHint(extractContentHint(blocks));
  }, [latestAssistantText]);

  const [segLoading, setSegLoading] = useState(false);
  const [segError, setSegError] = useState<string | null>(null);
  const [prepared, setPrepared] = useState<any | null>(null);
  const [running, setRunning] = useState(false);
  const [segmentDetail, setSegmentDetail] = useState<any | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewUsers, setPreviewUsers] = useState<any[]>([]);
  const [currentSeg, setCurrentSeg] = useState<{ id?: string; name?: string; customer_count?: number } | null>(null);
  const [allSegments, setAllSegments] = useState<any[]>([]);

  useEffect(() => {
    let ignore = false;
    async function loadData() {
      try {
        const [res, list] = await Promise.all([
          agentInteractions.getTaskSegment(taskId).catch(() => null),
          customerSegmentation.getSegments().catch(() => [])
        ]);
        
        if (!ignore) {
          if (res && !(res as any).message) {
            const selected = { id: res.id, name: res.name, customer_count: res.customer_count };
            setCurrentSeg(selected);
            onSegmentSelected?.(selected);
          } else {
            setCurrentSeg(null);
            onSegmentSelected?.(null);
          }
          if (list) setAllSegments(list);
        }
      } catch {
        if (!ignore) setCurrentSeg(null);
      }
    }
    loadData();
    return () => {
      ignore = true;
    };
  }, [taskId, refreshToken, onSegmentSelected]);

  async function handleSegmentChange(segId: string) {
    if (!segId) return;
    try {
      const res = await agentInteractions.bindTaskSegment(taskId, segId);
      const selected = { id: res.id, name: res.name, customer_count: res.customer_count };
      setCurrentSeg(selected);
      onSegmentSelected?.(selected);
      onMetric('segment_bind', { segment_id: res.id, segment_name: res.name, customer_count: res.customer_count });
    } catch (e) {
      alert('Не удалось привязать сегмент');
    }
  }

  async function prepare() {
    if (!isMassMailing || !planText.trim()) return;
    setSegError(null);
    setPrepared(null);
    setSegmentDetail(null);
    setSegLoading(true);
    try {
      const res = await agentInteractions.prepareMassMailing(taskId, {
        plan_text: planText,
        plan_title: taskTitle,
      });
      setPrepared(res);
      onMetric('sidebar_mass_prepare', {
        segment_id: res?.segment?.id,
        segment_name: res?.segment?.name,
        customer_count: res?.segment?.customer_count,
      });
      // Подгружаем правила сегмента
      try {
        const r = await apiClient.get(`/api/customer-segmentation/segments/${res.segment.id}`);
        setSegmentDetail(r.data);
      } catch {
        setSegmentDetail(null);
      }
    } catch (e: any) {
      const message = e?.response?.data?.detail || e?.message || 'Не удалось подготовить массовую генерацию';
      setSegError(String(message));
      onMetric('sidebar_mass_prepare_error', { message: String(message) });
    } finally {
      setSegLoading(false);
    }
  }

  async function run() {
    if (!prepared?.segment?.id || !prepared?.suggested_request?.event?.type) return;
    setSegError(null);
    setRunning(true);
    try {
      const meta = {
        ...(prepared.suggested_request?.event?.metadata || {}),
        prompt_hint: promptHint || undefined,
        source: 'ai-marketer:sidebar',
      };
      const res = await agentInteractions.runMassMailing(taskId, {
        segment_id: prepared.segment.id,
        event_type: prepared.suggested_request.event.type,
        brand: prepared.suggested_request.brand || 'GLAME',
        message_count: prepared.suggested_request.limit,
        auto_detect_store: Boolean(prepared.suggested_request.auto_detect_store),
        metadata: meta,
      });
      onMetric('sidebar_mass_run', { generation_id: res?.generation_id });
      alert(`Массовая генерация запущена.\ngeneration_id: ${res.generation_id}`);
    } catch (e: any) {
      const message = e?.response?.data?.detail || e?.message || 'Не удалось запустить массовую генерацию';
      setSegError(String(message));
      onMetric('sidebar_mass_run_error', { message: String(message) });
    } finally {
      setRunning(false);
    }
  }

  async function openPreview(segId?: string) {
    const targetId = segId || prepared?.segment?.id || currentSeg?.id;
    if (!targetId) return;
    setPreviewLoading(true);
    setPreviewOpen(true);
    setPreviewUsers([]);
    try {
      const r = await apiClient.get(`/api/customer-segmentation/segments/${targetId}/users`);
      setPreviewUsers(r.data?.users || []);
    } catch (e: any) {
      try {
        const r2 = await apiClient.get(`/api/admin/customers/segments/${targetId}/users`);
        setPreviewUsers(r2.data?.users || []);
      } catch {
        setPreviewUsers([]);
      }
    } finally {
      setPreviewLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>План</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {!latestAssistantText ? (
          <p className="text-sm text-gray-500">План появится здесь после ответа агента.</p>
        ) : (
          <>
            <div className="rounded-lg border bg-white">
              <div className="px-3 py-2 border-b text-sm font-semibold text-gray-900">Актуальная сегментация</div>
              <div className="px-3 py-2 space-y-3">
                <div className="flex items-center gap-2">
                  <div className="flex-grow">
                    <Select value={currentSeg?.id || ''} onValueChange={handleSegmentChange}>
                      <SelectTrigger className="h-8 text-sm">
                        <SelectValue placeholder="Выберите сегмент..." />
                      </SelectTrigger>
                      <SelectContent>
                        {allSegments.map((s) => (
                          <SelectItem key={s.id} value={s.id}>
                            {s.name} ({s.customer_count})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  {currentSeg?.id ? (
                    <button
                      type="button"
                      className="px-3 py-1.5 rounded-md border text-gray-800 hover:bg-gray-50 text-sm"
                      onClick={() => openPreview(currentSeg?.id)}
                    >
                      Предпросмотр
                    </button>
                  ) : null}
                </div>
                {currentSeg?.id ? (
                  <div className="text-xs text-gray-500">
                    ID: <span className="font-mono">{currentSeg.id.slice(0, 8)}...</span>
                  </div>
                ) : (
                  <div className="text-sm text-gray-500">Сегмент не привязан. Выберите из списка или нажмите «Подготовить».</div>
                )}
              </div>
            </div>

            <div className="rounded-lg border bg-white">
              <div className="px-3 py-2 border-b text-sm font-semibold text-gray-900">Документ</div>
              <div className="px-3 py-2 text-sm text-gray-900 whitespace-pre-wrap leading-[1.65]">
                {planText || '—'}
              </div>
            </div>

            {isMassMailing ? (
              <div className="rounded-lg border bg-white">
                <div className="px-3 py-2 border-b flex items-center justify-between">
                  <div className="text-sm font-semibold text-gray-900">Массовая рассылка</div>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      onClick={prepare}
                      disabled={segLoading || running}
                      className="bg-pink-600 hover:bg-pink-700"
                    >
                      {segLoading ? 'Подготовка…' : (prepared ? 'Обновить' : 'Подготовить')}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={run}
                      disabled={!prepared || segLoading || running}
                    >
                      {running ? 'Запуск…' : 'Выполнить'}
                    </Button>
                  </div>
                </div>

                {segError ? (
                  <div className="px-3 py-2 text-sm text-red-900 bg-red-50 border-t border-red-200 whitespace-pre-wrap">
                    {segError}
                  </div>
                ) : null}

                {prepared?.segment ? (
                  <div className="px-3 py-3 space-y-2">
                    <div className="text-sm text-gray-900">
                      Сегмент: <span className="font-medium">{prepared.segment.name}</span>{' '}
                      <span className="text-gray-600">({prepared.segment.customer_count})</span>
                    </div>
                    <div className="text-xs text-gray-600">
                      Тип события: <span className="font-medium">{prepared?.suggested_request?.event?.type}</span>{' '}
                      • Сообщений: <span className="font-medium">{prepared?.suggested_request?.limit}</span>
                    </div>
                    {segmentDetail?.rules ? (
                      <div className="rounded-md bg-gray-50 border px-2 py-2">
                        <div className="text-[11px] font-semibold text-gray-600 mb-1">Критерии выбора</div>
                        <ul className="list-disc pl-5 text-sm text-gray-800 space-y-1">
                          {humanizeRules(segmentDetail.rules).map((l, i) => (
                            <li key={i}>{l}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    <div className="flex items-center gap-2">
                      <button type="button" className="px-3 py-1.5 rounded-md border text-gray-800 hover:bg-gray-50" onClick={() => openPreview()}>
                        Предпросмотр сегмента
                      </button>
                      <a href="/admin/batch-messages" className="text-xs text-pink-700 hover:text-pink-800 underline underline-offset-2">
                        Открыть массовую генерацию
                      </a>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="rounded-lg border bg-white">
              <div className="px-3 py-2 border-b text-sm font-semibold text-gray-900">Основа промпта для сообщений</div>
              <div className="p-3">
                <Textarea
                  value={promptHint}
                  onChange={(e) => setPromptHint(e.target.value)}
                  placeholder="Опишите тон, ключевые акценты и цель сообщений. Этот текст будет передан как hint в событии."
                />
                <div className="mt-1 text-[11px] text-gray-600">
                  Будет передано в metadata как prompt_hint при запуске «Выполнить».
                </div>
              </div>
            </div>
          </>
        )}
      </CardContent>
      {previewOpen ? (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] flex flex-col">
            <div className="p-4 border-b flex items-center justify-between">
              <div className="text-lg font-semibold text-gray-900">Предпросмотр сегмента</div>
              <button type="button" onClick={() => setPreviewOpen(false)} className="px-3 py-1.5 rounded-md border hover:bg-gray-50">
                Закрыть
              </button>
            </div>
            <div className="p-4 overflow-auto">
              {previewLoading ? (
                <div className="text-center py-8 text-sm text-gray-600">Загрузка…</div>
              ) : previewUsers.length ? (
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-sm font-semibold text-gray-900">Имя</th>
                      <th className="px-3 py-2 text-left text-sm font-semibold text-gray-900">Предпочитаемый магазин</th>
                      <th className="px-3 py-2 text-left text-sm font-semibold text-gray-900">Телефон</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white">
                    {previewUsers.map((u) => (
                      <tr key={u.id}>
                        <td className="px-3 py-2 text-sm text-gray-900">{u.full_name}</td>
                        <td className="px-3 py-2 text-sm text-gray-700">{u.preferred_store_name || u.preferred_store || '—'}</td>
                        <td className="px-3 py-2 text-sm text-gray-700">{u.phone}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="text-center py-8 text-sm text-gray-600">Пользователи не найдены.</div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

export default function TaskPage() {
  const { id } = useParams();
  const router = useRouter();
  const [task, setTask] = useState<AgentInteractionTask | null>(null);
  const [loadingTask, setLoadingTask] = useState(false);
  const [loadingChatHistory, setLoadingChatHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [agentMode, setAgentMode] = useState<AgentMode>('auto');
  const [sessionId] = useState(() => {
    const v = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : safeId(String(Date.now()));
    return String(v);
  });

  type Attachment = { id: string; url: string; name: string; size: number; kind: 'image' | 'file'; file: File };
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  type ChatMsg = {
    id?: string;
    role: 'user' | 'assistant';
    content: string;
    attachments?: Attachment[];
    usedBrand?: any[];
    usedHistory?: any[];
    ctxOpen?: boolean;
    createdAt: string;
  };
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [thinking, setThinking] = useState(false);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const lastAssistantReplyAtRef = useRef<number | null>(null);
  const [replyTo, setReplyTo] = useState<{ id: string; snippet: string } | null>(null);
  const [selectedTaskSegment, setSelectedTaskSegment] = useState<TaskSegmentSelection>(null);

  const stepType = useMemo<'planning' | 'segmentation' | 'content' | 'analytics' | 'distribution' | 'other'>(() => {
    if (agentMode === 'planning') return 'planning';
    if (agentMode === 'action') return 'distribution';
    if (agentMode === 'consultation') return 'other';
    return 'other';
  }, [agentMode]);

  useEffect(() => {
    if (id) {
      loadTask();
      loadChatHistory();
    }
  }, [id]);

  async function loadTask() {
    setLoadingTask(true);
    setError(null);
    try {
      const taskData = await agentInteractions.getTask(id as string);
      setTask(taskData);
    } catch (e) {
      console.error('Failed to load task', { taskId: id, error: e });
      setError('Не удалось загрузить задачу');
    } finally {
      setLoadingTask(false);
    }
  }

  async function loadChatHistory() {
    setLoadingChatHistory(true);
    setError(null);
    try {
      const chatHistory = await agentInteractions.getChatHistory(id as string, 200);
      setChat(
        chatHistory.map((item: any) => ({
          id: item.id,
          role: item.role,
          content: item.content,
          createdAt: item.created_at || new Date().toISOString(),
        }))
      );
    } catch (e) {
      console.error('Failed to load chat history', { taskId: id, error: e });
      setError('Не удалось загрузить историю сообщений');
    } finally {
      setLoadingChatHistory(false);
    }
  }

  const handleTextareaInput = (e: React.FormEvent<HTMLTextAreaElement>) => {
    const el = e.currentTarget;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 240) + 'px';
  }

  function extractErrorMessage(e: any, fallback: string) {
    const detail = e?.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    const message = e?.message;
    if (typeof message === 'string' && message.trim()) return message;
    return fallback;
  }

  async function sendChat() {
    if (!chatInput.trim() || thinking) return;
    const text = chatInput;
    setChatInput('');
    const outgoing = attachments;
    setAttachments([]);
    const now = new Date().toISOString();
    setError(null);
    trackMetric('send', { mode: agentMode, step_type: stepType, attachments: outgoing.length });
    setChat((c) => {
      const next = [...c, { role: 'user' as const, content: text, attachments: outgoing, createdAt: now }];
      return next.length > 200 ? next.slice(next.length - 200) : next;
    });
    setThinking(true);
    setChat((c) => {
      const next = [...c, { role: 'assistant' as const, content: 'typing', createdAt: now }];
      return next.length > 200 ? next.slice(next.length - 200) : next;
    });
    try {
      const metadata = {
        step_type: stepType,
        task_type: task?.task_type,
        attachments: outgoing.map((a) => ({ name: a.name, kind: a.kind, size: a.size })),
        extra: {
          agent_mode: agentMode,
          ui: 'agent_answer_v2',
          reply_to_log_id: replyTo?.id || undefined,
          selected_segment_id: selectedTaskSegment?.id || undefined,
          selected_segment_name: selectedTaskSegment?.name || undefined,
          selected_segment_customer_count: selectedTaskSegment?.customer_count,
        },
      };
      const res = await agentInteractions.chat(id as string, { message: text, metadata });
      const reply = res.reply;
      const usedBrand = (res as any).used_brand_context || [];
      const usedHistory = (res as any).used_history_fragments || [];
      trackMetric('reply', { mode: agentMode, used_brand: usedBrand.length, used_history: usedHistory.length });
      lastAssistantReplyAtRef.current = Date.now();
      trackMetric('reply_rendered', { mode: agentMode, reply_len: String(reply || '').length });
      setChat((c) => {
        const withoutTyping = c.filter((m) => !(m.role === 'assistant' && m.content === 'typing'));
        const withUserId = withoutTyping.map((m) => {
          if (m.role === 'user' && !('id' in (m as any)) && m.createdAt === now) {
            return { ...m, id: res.user_log_id || undefined };
          }
          return m;
        });
        const next = [
          ...withUserId,
          {
            id: res.assistant_log_id || undefined,
            role: 'assistant' as const,
            content: reply,
            usedBrand,
            usedHistory,
            ctxOpen: false,
            createdAt: new Date().toISOString(),
          },
        ];
        return next.length > 200 ? next.slice(next.length - 200) : next;
      });
    } catch (e) {
      const message = extractErrorMessage(e, 'Не удалось получить ответ агента');
      console.error('Chat with agent failed', { taskId: id, error: e, message });
      setError(message);
      trackMetric('reply_error', { mode: agentMode, message });
      setChat((c) => {
        const withoutTyping = c.filter((m) => !(m.role === 'assistant' && m.content === 'typing'));
        const next = [
          ...withoutTyping,
          { role: 'assistant' as const, content: `Ошибка: ${message}`, createdAt: new Date().toISOString() },
        ];
        return next.length > 200 ? next.slice(next.length - 200) : next;
      });
    } finally {
      setThinking(false);
      setReplyTo(null);
    }
  }

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const active = document.activeElement as HTMLElement | null;
      const isTyping =
        active?.tagName === 'TEXTAREA' || active?.tagName === 'INPUT' || (active?.getAttribute('contenteditable') === 'true');

      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        sendChat();
        return;
      }
      if (e.altKey && ['1', '2', '3', '4'].includes(e.key)) {
        e.preventDefault();
        const next: AgentMode = e.key === '1' ? 'auto' : e.key === '2' ? 'planning' : e.key === '3' ? 'action' : 'consultation';
        setAgentMode(next);
        trackMetric('mode_hotkey', { mode: next });
        return;
      }
      if (e.key === '/' && !isTyping) {
        e.preventDefault();
        textareaRef.current?.focus();
        return;
      }
      if (e.key === 'Escape' && isTyping) {
        (document.activeElement as HTMLElement | null)?.blur?.();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [id, sessionId, agentMode, thinking, chatInput, attachments]);

  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [chat]);

  const trackMetric = (name: string, data?: Record<string, any>) => {
    try {
        if (name === 'segmentation_prepare' || name === 'mass_prepare' || name === 'sidebar_mass_prepare' || name === 'segment_bind') {
        const segId = String(data?.segment_id || '').trim();
        if (segId) {
          const seg = { id: segId, name: data?.segment_name as string | undefined, customer_count: data?.customer_count as number | undefined };
          setSelectedTaskSegment(seg);
          // @ts-ignore set state if available in page scope
          (setLatestSegment as any)?.(seg);
        }
      }
    } catch {}
  };

  if (!task) {
    if (loadingTask) return <div>Загрузка…</div>;
    return <div className="p-4 text-red-600">{error || 'Задача не найдена'}</div>;
  }

  async function deleteCurrentTask() {
    if (!id) return;
    if (!confirm('Удалить эту задачу? Это мягкое удаление, задача исчезнет из списков.')) return;
    setDeleting(true);
    setError(null);
    try {
      await agentInteractions.deleteTask(String(id), 'Удалено пользователем');
      router.push('/ai-marketer/tasks');
    } catch (e: any) {
      const msg = extractErrorMessage(e, 'Не удалось удалить задачу');
      console.error('Delete task failed', { taskId: id, error: e, msg });
      setError(msg);
    } finally {
      setDeleting(false);
    }
  }

  function goBack() {
    if (typeof window !== 'undefined' && window.history.length > 1) {
      router.back();
      return;
    }
    router.push('/ai-marketer/tasks');
  }

  async function handleTaskAction(action: 'approve' | 'reject' | 'revise' | 'queue' | 'process' | 'cancel' | 'complete') {
    if (!id || !task) return;
    setError(null);
    try {
      if (action === 'approve') {
        await agentInteractions.approveTask(String(id), 'Approved from task detail');
      } else if (action === 'reject') {
        const comment = window.prompt('Комментарий отклонения', 'Отклонено из карточки задачи') || 'Отклонено';
        await agentInteractions.rejectTask(String(id), comment);
      } else if (action === 'revise') {
        const comment = window.prompt('Что нужно доработать?', 'Нужна доработка') || 'Нужна доработка';
        await agentInteractions.reviseTask(String(id), comment);
      } else if (action === 'queue') {
        await agentInteractions.queueTask(String(id));
      } else if (action === 'process') {
        await agentInteractions.processTask(String(id));
      } else if (action === 'cancel') {
        const reason = window.prompt('Причина отмены', 'Отменено из карточки задачи') || 'Отменено';
        await agentInteractions.cancelTask(String(id), reason);
      } else if (action === 'complete') {
        const updated = await agentInteractions.updateTask(String(id), {
          status: 'completed',
          input_data: {
            ...(task.input_data || {}),
            completed_at: new Date().toISOString(),
            completion_source: 'task_detail',
          },
        });
        setTask(updated);
      }
      await loadTask();
    } catch (e: any) {
      setError(extractErrorMessage(e, 'Не удалось выполнить действие'));
    }
  }

  async function handlePassportSaved(updated: AgentInteractionTask) {
    setTask(updated);
    await Promise.all([loadTask(), loadChatHistory()]);
  }

  return (
    <div className="flex flex-col min-h-screen p-3 sm:p-4 space-y-4 bg-gray-50">
      {error && (
        <div className="p-3 rounded-lg border border-red-200 bg-red-50 text-red-700 text-sm">
          {error}
        </div>
      )}
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pb-3 border-b">
        <div className="flex items-start gap-3 min-w-0">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-9 w-9 shrink-0 p-0"
            onClick={goBack}
            aria-label="Вернуться назад"
            title="Назад"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </Button>
          <div className="min-w-0">
          <h1 className="text-2xl font-bold truncate">{task.input_data?.title || task.task_type || 'Задача'}</h1>
          <p className="text-sm text-gray-500">
            Агент: {task.target_agent} • Создана: {new Date(task.created_at).toLocaleString()}
          </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 justify-between sm:justify-end">
          <div className="flex items-center gap-2">
            <ModeBadge mode={agentMode} />
            <ModeSwitcher
              value={agentMode}
              onChange={(v) => {
                setAgentMode(v);
                trackMetric('mode_switch', { mode: v });
              }}
            />
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              className="transition-colors duration-200"
              onClick={deleteCurrentTask}
              disabled={deleting}
            >
              {deleting ? 'Удаление…' : 'Удалить задачу'}
            </Button>
            <Button className="transition-colors duration-200">Управление промптами</Button>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 flex flex-col space-y-4">
          <Card className="flex-grow flex flex-col">
            <CardHeader>
              <CardTitle>Диалог</CardTitle>
            </CardHeader>
            <CardContent className="flex-grow flex flex-col space-y-4">
              <div
                ref={chatScrollRef}
                className="flex-grow p-3 sm:p-4 space-y-4 overflow-y-auto bg-gray-50 rounded-lg border"
                role="log"
                aria-live="polite"
                aria-relevant="additions"
              >
                {loadingChatHistory && chat.length === 0 && (
                  <div className="text-sm text-gray-500">Загрузка истории…</div>
                )}
                {!loadingChatHistory && chat.length === 0 && (
                  <div className="text-sm text-gray-500">История сообщений пуста</div>
                )}
                {chat.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : ''}`}>
                    <div
                      className={`rounded-xl max-w-[780px] w-full sm:w-auto ${
                        msg.role === 'user'
                          ? 'bg-blue-600 text-white'
                          : msg.content?.startsWith('Ошибка:') ? 'bg-red-50 border border-red-200' : 'bg-white border'
                      }`}
                    >
                      <div className="px-3 py-2 sm:px-4 sm:py-3">
                        {msg.content === 'typing' ? (
                          <div className="flex items-center space-x-1" aria-label="Агент печатает">
                            <span className="w-2 h-2 bg-gray-500 rounded-full animate-pulse"></span>
                            <span className="w-2 h-2 bg-gray-500 rounded-full animate-pulse"></span>
                            <span className="w-2 h-2 bg-gray-500 rounded-full animate-pulse"></span>
                          </div>
                        ) : msg.role === 'assistant' ? (
                          <div className="space-y-3">
                            <AgentContent
                              taskId={String(id)}
                              content={msg.content}
                              storageSeed={`${id}_${msg.createdAt}_${i}`}
                              onMetric={(n, d) => trackMetric(n, { ...(d || {}), message_index: i })}
                            />

                            {(msg.usedBrand?.length || msg.usedHistory?.length) ? (
                              <details
                                className="group rounded-lg border bg-gray-50"
                                onToggle={(e) =>
                                  trackMetric('context_toggle', {
                                    open: (e.currentTarget as HTMLDetailsElement).open,
                                    message_index: i,
                                  })
                                }
                              >
                                <summary className="px-3 py-2 cursor-pointer list-none flex items-center justify-between gap-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-500 rounded-lg">
                                  <div className="text-sm font-semibold text-gray-900">Контекст ответа</div>
                                  <ChevronDown className="w-4 h-4 text-gray-600 transition-transform duration-200 group-open:rotate-180" aria-hidden="true" />
                                </summary>
                                <div className="px-3 pb-3 space-y-3 text-sm leading-[1.65] text-gray-800">
                                  {msg.usedBrand?.length ? (
                                    <div className="rounded-lg border bg-white p-3">
                                      <div className="flex items-center gap-2 font-semibold text-sm">
                                        <Target className="w-4 h-4 text-slate-700" aria-hidden="true" />
                                        Бренд-контекст ({msg.usedBrand.length})
                                      </div>
                                      <div className="mt-2 space-y-2">
                                        {msg.usedBrand.map((x, xi) => (
                                          <div key={xi} className="text-xs text-gray-700 whitespace-pre-wrap">
                                            {x?.payload?.text || x?.payload?.content || JSON.stringify(x?.payload || x)}
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  ) : null}
                                  {msg.usedHistory?.length ? (
                                    <div className="rounded-lg border bg-white p-3">
                                      <div className="flex items-center gap-2 font-semibold text-sm">
                                        <FileText className="w-4 h-4 text-slate-700" aria-hidden="true" />
                                        История задачи ({msg.usedHistory.length})
                                      </div>
                                      <div className="mt-2 space-y-2">
                                        {msg.usedHistory.map((x, xi) => (
                                          <div key={xi} className="text-xs text-gray-700 whitespace-pre-wrap">
                                            {x?.payload?.text || x?.payload?.content || JSON.stringify(x?.payload || x)}
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  ) : null}
                                </div>
                              </details>
                            ) : null}
                          </div>
                        ) : (
                          <p className="text-sm leading-[1.7] whitespace-pre-wrap">{msg.content}</p>
                        )}
                        <div className={`text-xs mt-2 ${msg.role === 'user' ? 'opacity-80' : 'text-gray-500'}`}>
                          {new Date(msg.createdAt).toLocaleTimeString()}
                        </div>
                        <div className="mt-2 flex gap-1">
                          <button
                            type="button"
                            className="h-8 w-8 grid place-items-center rounded border hover:bg-gray-50"
                            onClick={() => setReplyTo({ id: String((msg as any).id || ''), snippet: msg.content.slice(0, 64) })}
                            disabled={!('id' in (msg as any))}
                            title="Ответить"
                            aria-label="Ответить"
                          >
                            <Reply className="w-4 h-4 text-gray-700" aria-hidden="true" />
                          </button>
                          <button
                            type="button"
                            className="h-8 w-8 grid place-items-center rounded border hover:bg-gray-50"
                            onClick={async () => {
                              const logId = (msg as any).id;
                              if (!logId) return;
                              if (!confirm('Удалить это сообщение из истории?')) return;
                              try {
                                await agentInteractions.deleteChatMessage(String(id), String(logId));
                                setChat((c) => c.filter((m) => (m as any).id !== logId));
                              } catch {
                                alert('Не удалось удалить сообщение');
                              }
                            }}
                            disabled={!('id' in (msg as any))}
                            title="Удалить"
                            aria-label="Удалить"
                          >
                            <Trash2 className="w-4 h-4 text-red-600" aria-hidden="true" />
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="relative">
                <Textarea
                  ref={textareaRef}
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onInput={handleTextareaInput}
                  placeholder="Напишите сообщение... Поддерживается разметка Markdown"
                  className="pr-28 sm:pr-40 leading-[1.7]"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      sendChat();
                    }
                  }}
                />
                {replyTo ? (
                  <div className="absolute -top-7 left-0 text-xs text-gray-700 flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded bg-gray-100 border" title={replyTo.snippet}>
                      Ответ на: {replyTo.snippet}
                    </span>
                    <button type="button" className="text-gray-500 hover:text-gray-800" onClick={() => setReplyTo(null)}>Отменить</button>
                  </div>
                ) : null}
                <div className="absolute bottom-2 right-2 flex items-center gap-2">
                  <div className="flex items-center rounded-md border bg-white overflow-hidden shadow-sm">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="h-9 w-9 grid place-items-center hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-500"
                      aria-label="Прикрепить файлы"
                    >
                      <Paperclip className="w-5 h-5 text-gray-700" aria-hidden="true" />
                    </button>
                    <div className="w-[150px] sm:w-[190px] border-l">
                      <Select
                        value={agentMode}
                        onValueChange={(v) => {
                          const next = v as AgentMode;
                          setAgentMode(next);
                          trackMetric('mode_select', { mode: next });
                        }}
                      >
                        <SelectTrigger className="h-9 border-0 rounded-none bg-white focus:ring-0">
                          <SelectValue placeholder="Тип действия" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="auto">Авто</SelectItem>
                          <SelectItem value="planning">Планирование</SelectItem>
                          <SelectItem value="action">Действие</SelectItem>
                          <SelectItem value="consultation">Консультация</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <Button size="icon" onClick={sendChat} disabled={thinking} aria-label="Отправить сообщение">
                    <Send className="w-5 h-5" aria-hidden="true" />
                  </Button>
                  <input
                    type="file"
                    ref={fileInputRef}
                    className="hidden"
                    multiple
                    onChange={(e) => {
                      const files = Array.from(e.target.files || []);
                      if (!files.length) return;
                      setAttachments((prev) => {
                        const next = [...prev];
                        files.forEach((file) => {
                          const kind = file.type.startsWith('image/') ? 'image' : 'file';
                          next.push({
                            id: safeId(`${file.name}_${file.size}_${file.lastModified}`),
                            url: '',
                            name: file.name,
                            size: file.size,
                            kind,
                            file,
                          });
                        });
                        return next.slice(-10);
                      });
                      trackMetric('attach_files', { count: files.length });
                      e.target.value = '';
                    }}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-1 flex flex-col space-y-4">
          <TaskPassport task={task} onSaved={handlePassportSaved} onAction={handleTaskAction} />
          <PlanSidebar
            taskId={String(id)}
            taskTitle={task.input_data?.title || task.task_type || 'Задача'}
            latestAssistantText={
              [...chat].reverse().find((m) => m.role === 'assistant' && m.content && m.content !== 'typing')?.content || null
            }
            refreshToken={`${chat.length}-${lastAssistantReplyAtRef.current || 0}`}
            onMetric={trackMetric}
            onSegmentSelected={setSelectedTaskSegment}
          />
          <Card>
            <CardHeader>
              <CardTitle>Результаты</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-500">Результаты появятся после выполнения.</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Файлы</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-500">Экспорт в Excel/PDF будет доступен после выполнения.</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
