'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/components/auth/AuthProvider';
import { agentInteractions, type AgentInteractionTask } from '@/lib/api';
import SegmentSelector from '@/components/marketing/SegmentSelector';

type RiskLevel = 'low' | 'high';

type NewTaskForm = {
  title: string;
  description: string;
  is_recurring: boolean;
  target_agent: string;
  task_type: string;
  priority: number;
  risk_level: RiskLevel;
  deadline_at: string;
  campaign: string;
  city: '' | 'simferopol' | 'yalta' | 'both';
  dna: '' | 'classic' | 'dramatic' | 'romantic' | 'naturalistic';
  channel: string;
  platform: string;
  expected_result: string;
  assigned_human: string;
  attachments_text: string;
  city_context?: 'simferopol' | 'yalta'; // Для AI Brand Media
};

// Согласно иерархии AI-агентов из ТЗ
const TARGET_AGENTS = [
  { value: 'personal-media-agent', label: 'AI Personal Media' },
  { value: 'brand-media-agent', label: 'AI Brand Media' },
  { value: 'crm-agent', label: 'AI CRM' },
  { value: 'pr-partnerships-agent', label: 'AI PR & Partnerships' },
  { value: 'traffic-growth-agent', label: 'AI Traffic & Growth' },
  { value: 'analytics-agent', label: 'AI Analytics' },
  { value: 'assortment-agent', label: 'AI Assortment' },
];

const STATUS_LABEL: Record<string, string> = {
  pending: 'Планирование',
  validating: 'Планирование',
  validated: 'Планирование',
  queued: 'Выполнение',
  processing: 'Выполнение',
  completed: 'Завершено',
  failed: 'Ошибка',
  rejected: 'Отклонено',
  cancelled: 'Отменено',
};

function formatDate(iso?: string) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString('ru-RU');
}

export default function TasksPage() {
  const { loading } = useAuth();
  const router = useRouter();
  const [tasks, setTasks] = useState<AgentInteractionTask[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [creating, setCreating] = useState(false);
  const [showNewModal, setShowNewModal] = useState(false);
  const [showSegmentModal, setShowSegmentModal] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [form, setForm] = useState<NewTaskForm>({
    title: '',
    description: '',
    is_recurring: false,
    target_agent: 'personal-media-agent',
    task_type: 'custom',
    priority: 3,
    risk_level: 'low',
    deadline_at: '',
    campaign: '',
    city: '',
    dna: '',
    channel: '',
    platform: '',
    expected_result: '',
    assigned_human: '',
    attachments_text: '',
    city_context: undefined,
  });

  useEffect(() => {
    if (!loading) {
      loadTasks();
    }
  }, [loading]);

  async function loadTasks() {
    setLoadingData(true);
    try {
      const data = await agentInteractions.listTasks({ limit: 100 });
      setTasks(data);
    } finally {
      setLoadingData(false);
    }
  }

  const activeTasks = useMemo(
    () =>
      tasks.filter((t) =>
        ['pending', 'validating', 'validated', 'queued', 'processing'].includes(t.status)
      ),
    [tasks]
  );
  const completedTasks = useMemo(
    () => tasks.filter((t) => ['completed', 'failed', 'rejected', 'cancelled'].includes(t.status)),
    [tasks]
  );

  async function createTask() {
    setCreating(true);
    try {
      const attachments = form.attachments_text
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map((url) => ({ type: 'link', url }));
      const payload = {
        source_agent: 'ui',
        target_agent: form.target_agent,
        task_type: form.task_type || 'custom',
        input_data: { 
          description: form.description, 
          title: form.title,
          risk_level: form.risk_level,
          city_context: form.city_context,
          campaign: form.campaign || undefined,
          city: form.city || undefined,
          dna: form.dna || undefined,
          channel: form.channel || undefined,
          platform: form.platform || undefined,
          assigned_human: form.assigned_human || undefined,
          expected_result: form.expected_result || undefined,
          attachments,
        },
        task_context: {
          board_source: 'ai_marketer_tasks',
          is_recurring: form.is_recurring,
          schedule: form.is_recurring ? 'custom' : undefined,
          approval_status: 'needs_review',
        },
        priority: form.priority,
        deadline_at: form.deadline_at ? new Date(form.deadline_at).toISOString() : undefined,
      };
      const t = await agentInteractions.createTask(payload);
      setShowNewModal(false);
      setForm({ 
        title: '', 
        description: '', 
        is_recurring: false, 
        target_agent: 'personal-media-agent', 
        task_type: 'custom',
        priority: 3,
        risk_level: 'low',
        deadline_at: '',
        campaign: '',
        city: '',
        dna: '',
        channel: '',
        platform: '',
        expected_result: '',
        assigned_human: '',
        attachments_text: '',
        city_context: undefined
      });
      setTasks((prev) => [t, ...prev]);
      router.push(`/ai-marketer/tasks/${t.id}`);
    } finally {
      setCreating(false);
    }
  }

  async function approveTask(task: AgentInteractionTask) {
    try {
      await agentInteractions.approveTask(task.id, task.input_data?.risk_level === 'low' ? 'Low-risk approved from task board' : 'Approved from task board');
      await loadTasks();
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Не удалось согласовать задачу');
    }
  }

  async function deleteTask(id: string) {
    try {
      await agentInteractions.deleteTask(id, 'Удалено пользователем');
      await loadTasks();
    } catch (e: any) {
      const status = e?.response?.status;
      const message =
        status === 401
          ? 'Требуется авторизация для удаления задачи. Войдите в систему и попробуйте снова.'
          : e?.response?.data?.detail || 'Не удалось удалить задачу';
      alert(message);
    }
  }

  // Согласно ТЗ - регулярные задачи назначаются соответствующим агентам
  async function runRegularTask(kind: 'monthly_analytics' | 'weekly_content' | 'weekly_inventory') {
    const mapping: Record<typeof kind, { target: string; type: string; desc: string; risk_level: 'low' | 'high' }> = {
      monthly_analytics: {
        target: 'analytics',
        type: 'auto_segmentation',
        desc: 'Автосегментация и рекомендации',
        risk_level: 'low'
      },
      weekly_content: {
        target: 'content-agent',
        type: 'content_plan_refresh',
        desc: 'Обновление контент-плана для брендовых медиа',
        risk_level: 'low'
      },
      weekly_inventory: {
        target: 'inventory-control-agent',
        type: 'inventory_check',
        desc: 'Проверка остатков ключевых товаров',
        risk_level: 'low'
      },
    };
    const cfg = mapping[kind];
    const t = await agentInteractions.createTask({
      source_agent: 'scheduler',
      target_agent: cfg.target,
      task_type: cfg.type,
      input_data: { 
        title: cfg.desc,
        risk_level: cfg.risk_level
      },
      task_context: { is_recurring: true, kind },
        priority: 3,
      });
    router.push(`/ai-marketer/tasks/${t.id}`);
  }

  return (
    <div className="min-h-screen">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">AI Marketing Director - Задачи</h1>
          <p className="text-gray-600">Управление всеми задачами системы, согласование low-risk/high-risk действий</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowNewModal(true)}
            className="px-4 py-2 rounded-lg bg-pink-600 text-white hover:bg-pink-700"
          >
            Новая задача
          </button>
          <button
            onClick={() => setShowSegmentModal(true)}
            className="px-4 py-2 rounded-lg border border-gray-300 bg-white hover:bg-gray-50"
          >
            Определить сегмент
          </button>
          <Link
            href="/admin/prompts"
            className="px-4 py-2 rounded-lg border border-gray-300 bg-white hover:bg-gray-50"
          >
            Управление промптами
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div className="lg:col-span-2">
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-gray-900">Активные задачи</h2>
              <button onClick={loadTasks} className="text-sm text-pink-600 hover:text-pink-700">Обновить</button>
            </div>
            {loadingData ? (
              <div className="text-gray-500">Загрузка…</div>
            ) : activeTasks.length === 0 ? (
              <div className="text-gray-500">Нет активных задач</div>
            ) : (
              <div className="space-y-3">
                {activeTasks.map((t) => (
                  <div key={t.id} className="border border-gray-200 rounded-lg p-4 flex items-center justify-between">
                    <div className="min-w-0">
                      <div className="font-medium text-gray-900 truncate">{t.input_data?.title || t.task_type}</div>
                      <div className="text-sm text-gray-500">
                        Агент: {t.target_agent} • Создана: {formatDate(t.created_at)}
                        {t.input_data?.risk_level && (
                          <span className={`ml-2 px-1.5 py-0.5 text-xs rounded ${
                            t.input_data.risk_level === 'low' ? 'bg-green-50 text-green-700' : 'bg-orange-50 text-orange-700'
                          }`}>
                            {t.input_data.risk_level === 'low' ? 'low-risk' : 'high-risk'}
                          </span>
                        )}
                        {t.input_data?.city_context && (
                          <span className="ml-1 px-1.5 py-0.5 text-xs bg-blue-50 text-blue-700 rounded">
                            {t.input_data.city_context === 'simferopol' ? 'Симферополь' : 'Ялта'}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-1 text-xs rounded ${
                        ['pending','validating','validated'].includes(t.status) ? 'bg-yellow-100 text-yellow-800' :
                        ['queued','processing'].includes(t.status) ? 'bg-blue-100 text-blue-800' :
                        t.status === 'completed' ? 'bg-green-100 text-green-800' :
                        t.status === 'failed' ? 'bg-red-100 text-red-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>{STATUS_LABEL[t.status] || t.status}</span>
                      
                      {/* Кнопки согласования в зависимости от уровня риска */}
                      {['pending', 'validated', 'pending_approval'].includes(t.status) && t.input_data?.risk_level && (
                        <button
                          onClick={() => approveTask(t)}
                          className="px-3 py-1 text-sm rounded bg-green-600 text-white hover:bg-green-700"
                        >
                          {t.input_data.risk_level === 'low' ? 'Автозапустить' : 'Согласовать'}
                        </button>
                      )}
                      
                      <button
                        onClick={() => router.push(`/ai-marketer/tasks/${t.id}`)}
                        className="px-3 py-1 text-sm rounded bg-white border border-gray-300 hover:bg-gray-50"
                      >
                        Открыть
                      </button>
                      <button
                        onClick={() => setConfirmDeleteId(t.id)}
                        className="px-3 py-1 text-sm rounded bg-white border border-red-300 text-red-600 hover:bg-red-50"
                      >
                        Удалить
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <div>
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Регулярные задачи</h2>
            <div className="space-y-3">
              <div className="border border-gray-200 rounded-lg p-4">
                <div className="font-medium text-gray-900 mb-1">Месячная аналитика</div>
                <div className="text-sm text-gray-500 mb-3">1-е число месяца</div>
                <button
                  onClick={() => runRegularTask('monthly_analytics')}
                  className="px-3 py-1 text-sm rounded bg-pink-600 text-white hover:bg-pink-700"
                >
                  Запустить
                </button>
              </div>
              <div className="border border-gray-200 rounded-lg p-4">
                <div className="font-medium text-gray-900 mb-1">Обновление контент-плана</div>
                <div className="text-sm text-gray-500 mb-3">Каждую пятницу</div>
                <button
                  onClick={() => runRegularTask('weekly_content')}
                  className="px-3 py-1 text-sm rounded bg-pink-600 text-white hover:bg-pink-700"
                >
                  Запустить
                </button>
              </div>
              <div className="border border-gray-200 rounded-lg p-4">
                <div className="font-medium text-gray-900 mb-1">Проверка инвентаря</div>
                <div className="text-sm text-gray-500 mb-3">Еженедельно</div>
                <button
                  onClick={() => runRegularTask('weekly_inventory')}
                  className="px-3 py-1 text-sm rounded bg-pink-600 text-white hover:bg-pink-700"
                >
                  Запустить
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Завершенные</h2>
        {loadingData ? (
          <div className="text-gray-500">Загрузка…</div>
        ) : completedTasks.length === 0 ? (
          <div className="text-gray-500">Нет завершенных задач</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {completedTasks.map((t) => (
              <div key={t.id} className="border border-gray-200 rounded-lg p-4">
                <div className="flex items-center justify-between mb-1">
                  <div className="font-medium text-gray-900">{t.task_type}</div>
                  <span className={`px-2 py-1 text-xs rounded ${
                    t.status === 'completed' ? 'bg-green-100 text-green-800' :
                    t.status === 'failed' ? 'bg-red-100 text-red-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>{STATUS_LABEL[t.status] || t.status}</span>
                </div>
                <div className="text-sm text-gray-500 mb-3">Агент: {t.target_agent}</div>
                <div className="flex gap-2">
                  <button
                    onClick={() => router.push(`/ai-marketer/tasks/${t.id}`)}
                    className="px-3 py-1 text-sm rounded bg-white border border-gray-300 hover:bg-gray-50"
                  >
                    Открыть
                  </button>
                  <button
                    onClick={() => setConfirmDeleteId(t.id)}
                    className="px-3 py-1 text-sm rounded bg-white border border-red-300 text-red-600 hover:bg-red-50"
                  >
                    Удалить
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showNewModal && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-lg w-full p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Новая задача</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-700 mb-1">Название</label>
                <input
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2"
                  placeholder="Например: Контент-план на май"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-700 mb-1">Описание</label>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2"
                  rows={3}
                  placeholder="Краткое описание задачи"
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Агент</label>
                  <select
                    value={form.target_agent}
                    onChange={(e) => setForm((f) => ({ ...f, target_agent: e.target.value, city_context: undefined }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                  >
                    {TARGET_AGENTS.map((a) => (
                      <option key={a.value} value={a.value}>{a.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Тип задачи</label>
                  <input
                    value={form.task_type}
                    onChange={(e) => setForm((f) => ({ ...f, task_type: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                    placeholder="например"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Уровень риска (согласно ТЗ)</label>
                  <select
                    value={form.risk_level}
                    onChange={(e) => setForm((f) => ({ ...f, risk_level: e.target.value as RiskLevel }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                  >
                    <option value="low">Low-risk (автоматическое исполнение после согласования)</option>
                    <option value="high">High-risk (требует ручного подтверждения)</option>
                  </select>
                </div>

                {/* Городской контекст только для AI Brand Media */}
                {form.target_agent === 'content-agent' && (
                  <div>
                    <label className="block text-sm text-gray-700 mb-1">Городская среда (согласно ТЗ)</label>
                    <select
                      value={form.city_context || ''}
                      onChange={(e) => setForm((f) => ({ ...f, city_context: e.target.value as 'simferopol' | 'yalta' }))}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2"
                    >
                      <option value="simferopol">Симферополь - классика/драматизм</option>
                      <option value="yalta">Ялта - курорт/натурализм/романтика</option>
                    </select>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Приоритет</label>
                  <select
                    value={form.priority}
                    onChange={(e) => setForm((f) => ({ ...f, priority: Number(e.target.value) }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                  >
                    <option value={1}>P0 - критично</option>
                    <option value={2}>P1 - высокий</option>
                    <option value={3}>P2 - плановый</option>
                    <option value={4}>P3 - опционально</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Дедлайн</label>
                  <input
                    type="datetime-local"
                    value={form.deadline_at}
                    onChange={(e) => setForm((f) => ({ ...f, deadline_at: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Кампания</label>
                  <input
                    value={form.campaign}
                    onChange={(e) => setForm((f) => ({ ...f, campaign: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                    placeholder="Например: Summer Yalta"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Ответственный человек</label>
                  <input
                    value={form.assigned_human}
                    onChange={(e) => setForm((f) => ({ ...f, assigned_human: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                    placeholder="Елена / продюсер / PR"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Город</label>
                  <select
                    value={form.city}
                    onChange={(e) => setForm((f) => ({ ...f, city: e.target.value as NewTaskForm['city'] }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                  >
                    <option value="">Не задан</option>
                    <option value="simferopol">Симферополь</option>
                    <option value="yalta">Ялта</option>
                    <option value="both">Оба города</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-700 mb-1">DNA</label>
                  <select
                    value={form.dna}
                    onChange={(e) => setForm((f) => ({ ...f, dna: e.target.value as NewTaskForm['dna'] }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                  >
                    <option value="">Не задан</option>
                    <option value="classic">Classic</option>
                    <option value="dramatic">Dramatic</option>
                    <option value="romantic">Romantic</option>
                    <option value="naturalistic">Naturalistic</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Канал</label>
                  <input
                    value={form.channel}
                    onChange={(e) => setForm((f) => ({ ...f, channel: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                    placeholder="Instagram / SMS / App"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-700 mb-1">Ожидаемый результат</label>
                <input
                  value={form.expected_result}
                  onChange={(e) => setForm((f) => ({ ...f, expected_result: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2"
                  placeholder="Что должно быть готово или измерено"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-700 mb-1">Ссылки на материалы</label>
                <textarea
                  value={form.attachments_text}
                  onChange={(e) => setForm((f) => ({ ...f, attachments_text: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2"
                  rows={2}
                  placeholder="Каждая ссылка с новой строки"
                />
              </div>

              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.is_recurring}
                  onChange={(e) => setForm((f) => ({ ...f, is_recurring: e.target.checked }))}
                />
                <span className="text-sm text-gray-700">Регулярная задача</span>
              </label>
            </div>
            <div className="mt-6 flex items-center justify-end gap-2">
              <button
                onClick={() => setShowNewModal(false)}
                className="px-4 py-2 rounded-lg border border-gray-300 bg-white hover:bg-gray-50"
              >
                Отмена
              </button>
              <button
                onClick={createTask}
                disabled={creating || !form.title}
                className="px-4 py-2 rounded-lg bg-pink-600 text-white hover:bg-pink-700 disabled:opacity-50"
              >
                Создать
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmDeleteId && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Удалить задачу?</h3>
            <p className="text-sm text-gray-600 mb-6">Это действие удалит задачу (мягкое удаление) и скроет её из списков.</p>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setConfirmDeleteId(null)}
                className="px-4 py-2 rounded-lg border border-gray-300 bg-white hover:bg-gray-50"
              >
                Отмена
              </button>
              <button
                onClick={async () => {
                  const id = confirmDeleteId;
                  setConfirmDeleteId(null);
                  await deleteTask(id);
                }}
                className="px-4 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700"
              >
                Удалить
              </button>
            </div>
          </div>
        </div>
      )}

      {showSegmentModal && (
        <SegmentSelector
          open={showSegmentModal}
          onClose={() => setShowSegmentModal(false)}
          onSaved={() => setShowSegmentModal(false)}
        />
      )}
    </div>
  );
}
