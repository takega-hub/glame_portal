'use client';

import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '@/lib/api';

type CronJob = {
  id: string;
  title: string;
  description?: string;
  category: string;
  target_agent: string;
  task_type: string;
  schedule_type: 'hourly' | 'daily' | 'weekly' | 'monthly';
  time_of_day?: string | null;
  weekday?: number | null;
  day_of_month?: number | null;
  enabled: boolean;
  parameters?: Record<string, any>;
  next_run_at?: string | null;
  last_run_at?: string | null;
};

type CronRun = {
  id: string;
  job_id: string;
  job_title?: string;
  status: string;
  manual: boolean;
  task_id?: string;
  message?: string;
  started_at: string;
};

const categoryLabels: Record<string, string> = {
  analytics: 'Аналитика',
  assortment: 'Ассортимент',
  crm: 'CRM',
  data: 'Данные',
  director: 'Директор',
  inventory: 'Запасы',
  system: 'Система',
};

const agentLabels: Record<string, string> = {
  'director-agent': 'AI Marketing Director',
  'crm-agent': 'AI CRM',
  'assortment-agent': 'AI Assortment',
  'analytics-agent': 'AI Analytics',
  'brand-media-agent': 'AI Brand Media',
  'traffic-growth-agent': 'AI Traffic & Growth',
};

const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const categories = Object.keys(categoryLabels);

function defaultJobDraft(): CronJob {
  return {
    id: '',
    title: 'Новый регламент',
    description: '',
    category: 'director',
    target_agent: 'director-agent',
    task_type: 'scheduled_admin_task',
    schedule_type: 'daily',
    time_of_day: '09:00',
    weekday: null,
    day_of_month: null,
    enabled: false,
    parameters: { approval_required: true },
  };
}

function formatDate(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function scheduleText(job: CronJob) {
  if (job.schedule_type === 'hourly') {
    const interval = job.parameters?.interval_minutes || 60;
    return `каждые ${interval} мин.`;
  }
  if (job.schedule_type === 'weekly') return `${weekdays[job.weekday ?? 0]}, ${job.time_of_day || '09:00'}`;
  if (job.schedule_type === 'monthly') return `${job.day_of_month || 1} число, ${job.time_of_day || '09:00'}`;
  return `каждый день, ${job.time_of_day || '09:00'}`;
}

export default function AdminCronPage() {
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [runs, setRuns] = useState<CronRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingJob, setEditingJob] = useState<CronJob | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [parametersText, setParametersText] = useState('{}');

  const enabledCount = useMemo(() => jobs.filter((job) => job.enabled).length, [jobs]);
  const nextJob = useMemo(
    () =>
      jobs
        .filter((job) => job.enabled && job.next_run_at)
        .sort((a, b) => String(a.next_run_at).localeCompare(String(b.next_run_at)))[0],
    [jobs]
  );

  async function loadData() {
    setError(null);
    try {
      const [jobsResp, runsResp] = await Promise.all([
        apiClient.get<{ jobs: CronJob[] }>('/api/admin/cron/jobs'),
        apiClient.get<{ runs: CronRun[] }>('/api/admin/cron/runs', { params: { limit: 30 } }),
      ]);
      setJobs(jobsResp.data.jobs || []);
      setRuns(runsResp.data.runs || []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось загрузить CRON регламенты');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  function patchLocal(id: string, patch: Partial<CronJob>) {
    setJobs((current) => current.map((job) => (job.id === id ? { ...job, ...patch } : job)));
  }

  function openEditor(job?: CronJob) {
    const next = job || defaultJobDraft();
    setEditingJob(next);
    setIsCreating(!job);
    setParametersText(JSON.stringify(next.parameters || {}, null, 2));
    setEditorOpen(true);
    setError(null);
  }

  function closeEditor() {
    setEditorOpen(false);
    setEditingJob(null);
    setIsCreating(false);
    setParametersText('{}');
  }

  function updateEditingJob(patch: Partial<CronJob>) {
    setEditingJob((current) => (current ? { ...current, ...patch } : current));
  }

  function parseParameters() {
    try {
      const parsed = JSON.parse(parametersText || '{}');
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
        throw new Error('parameters must be object');
      }
      return parsed;
    } catch {
      throw new Error('Параметры должны быть валидным JSON-объектом');
    }
  }

  function jobPayload(job: CronJob, parameters: Record<string, any>) {
    return {
      title: job.title,
      description: job.description || '',
      category: job.category,
      enabled: Boolean(job.enabled),
      schedule_type: job.schedule_type,
      time_of_day: job.schedule_type === 'hourly' ? null : job.time_of_day || '09:00',
      weekday: job.schedule_type === 'weekly' ? job.weekday ?? 0 : null,
      day_of_month: job.schedule_type === 'monthly' ? job.day_of_month || 1 : null,
      target_agent: job.target_agent,
      task_type: job.task_type,
      parameters,
    };
  }

  async function saveJob(job: CronJob, patch: Partial<CronJob> = {}) {
    const next = { ...job, ...patch };
    setSavingId(job.id);
    setError(null);
    try {
      const resp = await apiClient.put<{ job: CronJob }>(`/api/admin/cron/jobs/${job.id}`, {
        enabled: next.enabled,
        schedule_type: next.schedule_type,
        time_of_day: next.time_of_day,
        weekday: next.weekday,
        day_of_month: next.day_of_month,
        target_agent: next.target_agent,
        task_type: next.task_type,
        parameters: next.parameters || {},
      });
      patchLocal(job.id, resp.data.job);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось сохранить регламент');
    } finally {
      setSavingId(null);
    }
  }

  async function runNow(job: CronJob) {
    setSavingId(job.id);
    setError(null);
    try {
      await apiClient.post(`/api/admin/cron/jobs/${job.id}/run`);
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось запустить регламент');
    } finally {
      setSavingId(null);
    }
  }

  async function saveEditor() {
    if (!editingJob) return;
    setSavingId(editingJob.id || 'new');
    setError(null);
    try {
      const parameters = parseParameters();
      const payload = jobPayload(editingJob, parameters);
      if (isCreating) {
        const resp = await apiClient.post<{ job: CronJob }>('/api/admin/cron/jobs', payload);
        setJobs((current) => [...current, resp.data.job].sort((a, b) => `${a.category}-${a.title}`.localeCompare(`${b.category}-${b.title}`)));
      } else {
        const resp = await apiClient.put<{ job: CronJob }>(`/api/admin/cron/jobs/${editingJob.id}`, payload);
        patchLocal(editingJob.id, resp.data.job);
      }
      closeEditor();
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Не удалось сохранить регламент');
    } finally {
      setSavingId(null);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-950">CRON регламенты</h1>
          <p className="mt-2 max-w-3xl text-sm text-gray-600">
            Периодические проверки и операционные задачи для директора, AI CRM, AI Analytics и AI Assortment.
            Запуски создают задачи агентам и не отправляют рассылки без согласования администратора.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => openEditor()}
            className="rounded-md bg-pink-600 px-4 py-2 text-sm font-medium text-white hover:bg-pink-700"
          >
            Создать регламент
          </button>
          <button
            type="button"
            onClick={loadData}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-900 hover:bg-gray-50"
          >
            Обновить
          </button>
        </div>
      </div>

      <div className="mb-6 grid gap-3 md:grid-cols-3">
        <div className="rounded-md border border-gray-200 bg-white p-4 shadow-sm">
          <div className="text-sm text-gray-500">Всего регламентов</div>
          <div className="mt-1 text-2xl font-bold text-gray-950">{jobs.length}</div>
        </div>
        <div className="rounded-md border border-gray-200 bg-white p-4 shadow-sm">
          <div className="text-sm text-gray-500">Включено</div>
          <div className="mt-1 text-2xl font-bold text-green-700">{enabledCount}</div>
        </div>
        <div className="rounded-md border border-gray-200 bg-white p-4 shadow-sm">
          <div className="text-sm text-gray-500">Следующий запуск</div>
          <div className="mt-1 text-sm font-semibold text-gray-950">{nextJob ? nextJob.title : 'Не запланирован'}</div>
          <div className="mt-1 text-xs text-gray-500">{nextJob ? formatDate(nextJob.next_run_at) : '—'}</div>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <section className="rounded-md border border-gray-200 bg-white shadow-sm">
        <div className="grid grid-cols-[1.3fr_0.9fr_0.9fr_0.9fr_0.9fr] gap-3 border-b border-gray-200 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
          <div>Регламент</div>
          <div>Расписание</div>
          <div>Агент</div>
          <div>Запуски</div>
          <div className="text-right">Действия</div>
        </div>
        {loading ? (
          <div className="p-8 text-center text-sm text-gray-500">Загрузка...</div>
        ) : (
          jobs.map((job) => (
            <div
              key={job.id}
              className="grid grid-cols-[1.3fr_0.9fr_0.9fr_0.9fr_0.9fr] gap-3 border-b border-gray-100 px-4 py-4 last:border-b-0"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                      job.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {job.enabled ? 'Включен' : 'Выключен'}
                  </span>
                  <span className="rounded-full bg-pink-50 px-2 py-0.5 text-xs text-pink-700">
                    {categoryLabels[job.category] || job.category}
                  </span>
                </div>
                <h2 className="mt-2 text-base font-bold text-gray-950">{job.title}</h2>
                <p className="mt-1 text-sm text-gray-600">{job.description}</p>
                <div className="mt-2 text-xs text-gray-500">{job.task_type}</div>
              </div>

              <div className="space-y-2">
                <select
                  value={job.schedule_type}
                  onChange={(e) => patchLocal(job.id, { schedule_type: e.target.value as CronJob['schedule_type'] })}
                  className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                >
                  <option value="hourly">Каждый N минут</option>
                  <option value="daily">Ежедневно</option>
                  <option value="weekly">Еженедельно</option>
                  <option value="monthly">Ежемесячно</option>
                </select>
                {job.schedule_type === 'hourly' ? (
                  <input
                    type="number"
                    min={5}
                    value={job.parameters?.interval_minutes || 60}
                    onChange={(e) =>
                      patchLocal(job.id, {
                        parameters: { ...(job.parameters || {}), interval_minutes: Number(e.target.value || 60) },
                      })
                    }
                    className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                  />
                ) : (
                  <input
                    type="time"
                    value={job.time_of_day || '09:00'}
                    onChange={(e) => patchLocal(job.id, { time_of_day: e.target.value })}
                    className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                  />
                )}
                {job.schedule_type === 'weekly' && (
                  <select
                    value={job.weekday ?? 0}
                    onChange={(e) => patchLocal(job.id, { weekday: Number(e.target.value) })}
                    className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                  >
                    {weekdays.map((label, index) => (
                      <option key={label} value={index}>
                        {label}
                      </option>
                    ))}
                  </select>
                )}
                {job.schedule_type === 'monthly' && (
                  <input
                    type="number"
                    min={1}
                    max={28}
                    value={job.day_of_month || 1}
                    onChange={(e) => patchLocal(job.id, { day_of_month: Number(e.target.value || 1) })}
                    className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                  />
                )}
                <div className="text-xs text-gray-500">{scheduleText(job)}</div>
              </div>

              <div>
                <select
                  value={job.target_agent}
                  onChange={(e) => patchLocal(job.id, { target_agent: e.target.value })}
                  className="w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
                >
                  {Object.entries(agentLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <div className="mt-2 text-xs text-gray-500">{job.target_agent}</div>
              </div>

              <div className="text-sm">
                <div className="text-gray-500">Следующий</div>
                <div className="font-medium text-gray-950">{formatDate(job.next_run_at)}</div>
                <div className="mt-3 text-gray-500">Последний</div>
                <div className="font-medium text-gray-950">{formatDate(job.last_run_at)}</div>
              </div>

              <div className="flex flex-col items-end gap-2">
                <button
                  type="button"
                  onClick={() => saveJob(job, { enabled: !job.enabled })}
                  disabled={savingId === job.id}
                  className={`w-full rounded-md px-3 py-2 text-sm font-medium ${
                    job.enabled
                      ? 'border border-gray-300 bg-white text-gray-900 hover:bg-gray-50'
                      : 'bg-pink-600 text-white hover:bg-pink-700'
                  } disabled:opacity-60`}
                >
                  {job.enabled ? 'Выключить' : 'Включить'}
                </button>
                <button
                  type="button"
                  onClick={() => openEditor(job)}
                  disabled={savingId === job.id}
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-50 disabled:opacity-60"
                >
                  Настроить
                </button>
                <button
                  type="button"
                  onClick={() => saveJob(job)}
                  disabled={savingId === job.id}
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-900 hover:bg-gray-50 disabled:opacity-60"
                >
                  Сохранить
                </button>
                <button
                  type="button"
                  onClick={() => runNow(job)}
                  disabled={savingId === job.id}
                  className="w-full rounded-md bg-gray-950 px-3 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-60"
                >
                  Запустить сейчас
                </button>
              </div>
            </div>
          ))
        )}
      </section>

      <section className="mt-6 rounded-md border border-gray-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-bold text-gray-950">Последние запуски</h2>
          <span className="text-xs text-gray-500">Время сервера: UTC</span>
        </div>
        {runs.length === 0 ? (
          <div className="py-6 text-sm text-gray-500">Запусков пока нет.</div>
        ) : (
          <div className="divide-y divide-gray-100">
            {runs.map((run) => (
              <div key={run.id} className="grid grid-cols-[1fr_160px_120px_1fr] gap-3 py-3 text-sm">
                <div>
                  <div className="font-medium text-gray-950">{run.job_title || run.job_id}</div>
                  <div className="text-xs text-gray-500">{run.message || '—'}</div>
                </div>
                <div className="text-gray-600">{formatDate(run.started_at)}</div>
                <div>
                  <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
                    {run.manual ? 'ручной' : 'авто'}
                  </span>
                </div>
                <div className="truncate text-right text-xs text-gray-500">
                  {run.task_id ? (
                    <a href={`/ai-marketer/tasks/${run.task_id}`} className="text-pink-700 underline underline-offset-2 hover:text-pink-800">
                      Открыть задачу
                    </a>
                  ) : (
                    run.status
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {editorOpen && editingJob ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
          <div className="max-h-[92vh] w-full max-w-3xl overflow-auto rounded-md bg-white shadow-xl">
            <div className="flex items-center justify-between border-b px-5 py-4">
              <div>
                <h2 className="text-xl font-bold text-gray-950">{isCreating ? 'Новый регламент' : 'Настройка регламента'}</h2>
                <p className="mt-1 text-sm text-gray-500">Здесь задается, какую задачу CRON создаст агенту при запуске.</p>
              </div>
              <button type="button" onClick={closeEditor} className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50">
                Закрыть
              </button>
            </div>

            <div className="grid gap-4 px-5 py-4 md:grid-cols-2">
              <label className="md:col-span-2">
                <span className="text-sm font-medium text-gray-800">Название регламента</span>
                <input
                  value={editingJob.title}
                  onChange={(e) => updateEditingJob({ title: e.target.value })}
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
              </label>

              <label className="md:col-span-2">
                <span className="text-sm font-medium text-gray-800">Описание задачи для агента</span>
                <textarea
                  value={editingJob.description || ''}
                  onChange={(e) => updateEditingJob({ description: e.target.value })}
                  rows={4}
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
              </label>

              <label>
                <span className="text-sm font-medium text-gray-800">Категория</span>
                <select
                  value={editingJob.category}
                  onChange={(e) => updateEditingJob({ category: e.target.value })}
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  {categories.map((category) => (
                    <option key={category} value={category}>
                      {categoryLabels[category] || category}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span className="text-sm font-medium text-gray-800">Агент-исполнитель</span>
                <select
                  value={editingJob.target_agent}
                  onChange={(e) => updateEditingJob({ target_agent: e.target.value })}
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  {Object.entries(agentLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span className="text-sm font-medium text-gray-800">Тип задачи</span>
                <input
                  value={editingJob.task_type}
                  onChange={(e) => updateEditingJob({ task_type: e.target.value })}
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                />
              </label>

              <label>
                <span className="text-sm font-medium text-gray-800">Расписание</span>
                <select
                  value={editingJob.schedule_type}
                  onChange={(e) => updateEditingJob({ schedule_type: e.target.value as CronJob['schedule_type'] })}
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="hourly">Каждый N минут</option>
                  <option value="daily">Ежедневно</option>
                  <option value="weekly">Еженедельно</option>
                  <option value="monthly">Ежемесячно</option>
                </select>
              </label>

              {editingJob.schedule_type === 'hourly' ? (
                <label>
                  <span className="text-sm font-medium text-gray-800">Интервал, минут</span>
                  <input
                    type="number"
                    min={5}
                    value={editingJob.parameters?.interval_minutes || 60}
                    onChange={(e) => {
                      const parameters = { ...(editingJob.parameters || {}), interval_minutes: Number(e.target.value || 60) };
                      updateEditingJob({
                        parameters,
                      });
                      setParametersText(JSON.stringify(parameters, null, 2));
                    }}
                    className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  />
                </label>
              ) : (
                <label>
                  <span className="text-sm font-medium text-gray-800">Время UTC</span>
                  <input
                    type="time"
                    value={editingJob.time_of_day || '09:00'}
                    onChange={(e) => updateEditingJob({ time_of_day: e.target.value })}
                    className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  />
                </label>
              )}

              {editingJob.schedule_type === 'weekly' ? (
                <label>
                  <span className="text-sm font-medium text-gray-800">День недели</span>
                  <select
                    value={editingJob.weekday ?? 0}
                    onChange={(e) => updateEditingJob({ weekday: Number(e.target.value) })}
                    className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  >
                    {weekdays.map((label, index) => (
                      <option key={label} value={index}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}

              {editingJob.schedule_type === 'monthly' ? (
                <label>
                  <span className="text-sm font-medium text-gray-800">День месяца</span>
                  <input
                    type="number"
                    min={1}
                    max={28}
                    value={editingJob.day_of_month || 1}
                    onChange={(e) => updateEditingJob({ day_of_month: Number(e.target.value || 1) })}
                    className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  />
                </label>
              ) : null}

              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={editingJob.enabled}
                  onChange={(e) => updateEditingJob({ enabled: e.target.checked })}
                  className="h-4 w-4 rounded border-gray-300"
                />
                <span className="text-sm font-medium text-gray-800">Включить регламент после сохранения</span>
              </label>

              <label className="md:col-span-2">
                <span className="text-sm font-medium text-gray-800">Параметры задачи JSON</span>
                <textarea
                  value={parametersText}
                  onChange={(e) => setParametersText(e.target.value)}
                  rows={8}
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-xs"
                  spellCheck={false}
                />
              </label>
            </div>

            <div className="flex justify-end gap-2 border-t px-5 py-4">
              <button type="button" onClick={closeEditor} className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-gray-50">
                Отмена
              </button>
              <button
                type="button"
                onClick={saveEditor}
                disabled={savingId !== null}
                className="rounded-md bg-gray-950 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-60"
              >
                {savingId ? 'Сохранение...' : 'Сохранить регламент'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
