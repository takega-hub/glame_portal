'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { adminCrm, sellerCrm, type CrmTaskDto } from '@/lib/api';

const STATUS_LABELS: Record<string, string> = {
  new: 'Новая',
  in_progress: 'В работе',
  overdue: 'Просрочено',
  worked: 'Отработано',
  postponed: 'Перенесено',
  not_relevant: 'Неактуально',
  do_not_disturb: 'Не беспокоить',
  quality_complaint: 'Жалоба на качество',
  closed: 'Закрыто',
};

const OUTCOMES = [
  { value: 'no_answer', label: 'Не дозвонились' },
  { value: 'sent_no_reply', label: 'Отправлено, ответа нет' },
  { value: 'replied', label: 'Ответила' },
  { value: 'requested_photo_video', label: 'Попросила видео/фото' },
  { value: 'photo_video_sent', label: 'Видео/фото отправлено' },
  { value: 'service_requested', label: 'Нужен сервис' },
  { value: 'sale', label: 'Продажа' },
  { value: 'postpone', label: 'Перенести' },
  { value: 'not_relevant', label: 'Неактуально' },
  { value: 'do_not_disturb', label: 'Не беспокоить' },
  { value: 'quality_complaint', label: 'Жалоба на качество' },
  { value: 'create_cdek', label: 'Создать накладную СДЭК' },
  { value: 'in_dialogue', label: 'В диалоге' },
  { value: 'waiting_in_store', label: 'Ждём в магазине' },
  { value: 'purchased', label: 'Покупка' },
  { value: 'service', label: 'Сервис' },
  { value: 'interested', label: 'Заинтересовалась' },
  { value: 'not_interested', label: 'Не интересно' },
  { value: 'out_of_town', label: 'Не в городе' },
  { value: 'online_selection', label: 'Онлайн-подбор' },
  { value: 'asked_for_video', label: 'Попросила видео' },
  { value: 'asked_for_more_photos', label: 'Попросила ещё фото' },
  { value: 'plans_visit', label: 'Планирует визит' },
  { value: 'no_response', label: 'Нет ответа' },
  { value: 'follow_up_later', label: 'Связаться позже' },
];
const OPEN_STATUS_FILTER = 'new,in_progress,postponed,overdue';
const COMPLETED_STATUS_FILTER = 'worked,closed,not_relevant,do_not_disturb,quality_complaint';

const CRM_GROUP_LABELS: Record<string, string> = {
  personal_call: 'Личный звонок',
  personal_message: 'Личное сообщение',
  segmented_message: 'Сегментированное сообщение',
  do_not_touch_review: 'Не трогать / проверить',
  post_purchase_care: 'Уход после покупки',
  warranty_check: 'Гарантийное касание',
  cleaning_reminder: 'Напоминание о чистке',
  birthday_greeting: 'Поздравление с ДР',
  new_arrival: 'Новое поступление',
};

const SELLER_MAIN_CRM_GROUPS = [
  'birthday_greeting',
  'post_purchase_care',
  'warranty_check',
  'cleaning_reminder',
  'new_arrival',
] as const;

const SELLER_MAIN_CRM_GROUP_SET = new Set<string>(SELLER_MAIN_CRM_GROUPS);

function formatMoney(value?: number | null) {
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format((value || 0) / 100);
}

function formatDate(value?: string | null) {
  if (!value) return '—';
  return new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString('ru-RU');
}

function statusClass(status: string) {
  if (status === 'new') return 'bg-blue-100 text-blue-800';
  if (status === 'in_progress') return 'bg-amber-100 text-amber-800';
  if (status === 'overdue') return 'bg-red-100 text-red-800';
  if (status === 'worked' || status === 'closed') return 'bg-emerald-100 text-emerald-800';
  if (status === 'quality_complaint') return 'bg-rose-100 text-rose-800';
  if (status === 'postponed') return 'bg-purple-100 text-purple-800';
  return 'bg-gray-100 text-gray-700';
}

function dateMinusDays(value: string, days: number) {
  const date = new Date(`${value}T00:00:00`);
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

function taskCampaignLabel(task: CrmTaskDto) {
  return task.campaign_name || task.campaign_id || 'Кампания не указана';
}

function ArrivalBlock({ task }: { task: CrmTaskDto }) {
  const payload = task.source_payload?.task_type === 'NEW_ARRIVAL' ? task.source_payload : null;
  if (!payload) return null;
  const media = Array.isArray(payload.media) ? payload.media.filter(Boolean).slice(0, 6) : [];
  const items = Array.isArray(payload.items) ? payload.items.slice(0, 8) : [];
  return (
    <div className="rounded-2xl border border-[#eee3d8] p-4">
      <h3 className="font-semibold">Новое поступление</h3>
      <p className="mt-2 text-sm text-[#6f6257]">
        {payload.brand || 'Бренд не указан'} · {payload.physical_store || task.store_name || 'магазин не указан'} · канал: {payload.channel || '—'}
      </p>
      {media.length > 0 && (
        <div className="mt-3 grid grid-cols-3 gap-2 md:grid-cols-6">
          {media.map((src: string, index: number) => (
            <a key={`${src}-${index}`} href={src} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-xl border border-[#eee3d8] bg-[#faf9f7]">
              <img src={src} alt="Новинка GLAME" className="h-24 w-full object-cover" />
            </a>
          ))}
        </div>
      )}
      {items.length > 0 && (
        <ul className="mt-3 max-h-44 space-y-2 overflow-auto text-sm text-[#5d5148]">
          {items.map((item: Record<string, any>, index: number) => (
            <li key={item.product_id || item.sku || index} className="rounded-xl bg-[#fbf6ef] p-3">
              <b>{item.name || item.sku || 'Товар'}</b>
              <span className="text-[#6f6257]"> · {item.category || 'категория не указана'} · {formatMoney(Number(item.price || 0))}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function SellerCrmPage() {
  const { user, accountPreview } = useAuth();
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [tasks, setTasks] = useState<CrmTaskDto[]>([]);
  const [availableGroups, setAvailableGroups] = useState<string[]>([]);
  const [completedCount, setCompletedCount] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<CrmTaskDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sellerOutcome, setSellerOutcome] = useState('sent_no_reply');
  const [sellerComment, setSellerComment] = useState('');
  const [nextActionDate, setNextActionDate] = useState('');
  const [taskFilter, setTaskFilter] = useState<'all' | 'new' | 'in_progress' | 'overdue'>('all');
  const [groupFilter, setGroupFilter] = useState('');
  const previewSellerUserId = user?.is_role_preview && accountPreview?.id ? accountPreview.id : '';
  const isPreviewMode = Boolean(previewSellerUserId);

  const fetchOpenTasks = useCallback(async (crmGroup?: string) => {
    if (isPreviewMode) {
      const activeWindowStart = dateMinusDays(date, 2);
      const [dayTasks, overdueTasks] = await Promise.all([
        adminCrm.listTasks({ start_date: activeWindowStart, end_date: date, seller_user_id: previewSellerUserId, status: OPEN_STATUS_FILTER, crm_group: crmGroup || undefined, limit: 300 }),
        adminCrm.listTasks({ seller_user_id: previewSellerUserId, status: 'overdue', only_overdue: true, crm_group: crmGroup || undefined, limit: 300 }),
      ]);
      const byId = new Map<string, CrmTaskDto>();
      [...overdueTasks.items, ...dayTasks.items].forEach((task) => byId.set(task.id, task));
      return Array.from(byId.values());
    }
    const data = await sellerCrm.listTasks({ date, crm_group: crmGroup || undefined, include_overdue: true, limit: 300 });
    return data.items;
  }, [date, isPreviewMode, previewSellerUserId]);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const collectGroups = (items: CrmTaskDto[]) => {
        const present = new Set(items.map((task) => task.crm_group).filter(Boolean));
        return SELLER_MAIN_CRM_GROUPS.filter((group) => present.has(group));
      };
      if (isPreviewMode) {
        const [items, allOpenItems, completedTasks] = await Promise.all([
          fetchOpenTasks(groupFilter || undefined),
          groupFilter ? fetchOpenTasks(undefined) : Promise.resolve(null),
          adminCrm.listTasks({ start_date: date, end_date: date, seller_user_id: previewSellerUserId, status: COMPLETED_STATUS_FILTER, crm_group: groupFilter || undefined, limit: 1 }),
        ]);
        setAvailableGroups(collectGroups(allOpenItems || items));
        setTasks(items);
        setCompletedCount(completedTasks.total || 0);
        if (!selectedId && items[0]) setSelectedId(items[0].id);
      } else {
        const [items, allOpenItems, completedTasks] = await Promise.all([
          fetchOpenTasks(groupFilter || undefined),
          groupFilter ? fetchOpenTasks(undefined) : Promise.resolve(null),
          sellerCrm.listTasks({ date, crm_group: groupFilter || undefined, status: COMPLETED_STATUS_FILTER, include_overdue: false, limit: 1 }),
        ]);
        setAvailableGroups(collectGroups(allOpenItems || items));
        setTasks(items);
        setCompletedCount(completedTasks.total || 0);
        if (!selectedId && items[0]) setSelectedId(items[0].id);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось загрузить CRM-задачи');
    } finally {
      setLoading(false);
    }
  }, [date, fetchOpenTasks, groupFilter, isPreviewMode, previewSellerUserId, selectedId]);

  async function loadSelected(id: string) {
    try {
      const data = isPreviewMode ? await adminCrm.getTask(id) : await sellerCrm.getTask(id);
      setSelected(data);
      setSellerOutcome(data.seller_outcome || 'sent_no_reply');
      setSellerComment(data.seller_comment || '');
      setNextActionDate(data.next_action_date || '');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось открыть CRM-задачу');
    }
  }

  useEffect(() => {
    setSelectedId(null);
    setSelected(null);
  }, [date, groupFilter, previewSellerUserId]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  useEffect(() => {
    if (selectedId) loadSelected(selectedId);
  }, [isPreviewMode, selectedId]);

  const counters = useMemo(() => ({
    total: tasks.length,
    new: tasks.filter((task) => task.status === 'new').length,
    inProgress: tasks.filter((task) => task.status === 'in_progress').length,
    overdue: tasks.filter((task) => task.status === 'overdue').length,
    completed: completedCount,
  }), [tasks, date, completedCount]);

  const visibleTasks = useMemo(() => {
    let items = tasks;
    if (groupFilter) items = items.filter((task) => task.crm_group === groupFilter);
    if (taskFilter === 'new') return items.filter((task) => task.status === 'new');
    if (taskFilter === 'in_progress') return items.filter((task) => task.status === 'in_progress');
    if (taskFilter === 'overdue') return items.filter((task) => task.status === 'overdue');
    return items;
  }, [date, groupFilter, taskFilter, tasks]);

  const groupOptions = useMemo(() => {
    const values = availableGroups.filter((group) => SELLER_MAIN_CRM_GROUP_SET.has(group));
    if (groupFilter && SELLER_MAIN_CRM_GROUP_SET.has(groupFilter) && !values.includes(groupFilter)) {
      return [...values, groupFilter];
    }
    return values;
  }, [availableGroups, groupFilter]);

  useEffect(() => {
    if (selectedId && !visibleTasks.some((task) => task.id === selectedId)) {
      setSelectedId(visibleTasks[0]?.id || null);
      setSelected(null);
    }
  }, [selectedId, visibleTasks]);

  async function startTask() {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      const data = isPreviewMode ? await adminCrm.startTask(selected.id) : await sellerCrm.startTask(selected.id);
      setSelected(data);
      await loadTasks();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось взять задачу в работу');
    } finally {
      setSaving(false);
    }
  }

  async function saveResult() {
    if (!selected) return;
    if (!sellerComment.trim()) {
      setError('Для сохранения результата нужен комментарий продавца.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = {
        seller_outcome: sellerOutcome,
        seller_comment: sellerComment,
        next_action_date: nextActionDate || null,
      };
      const data = isPreviewMode ? await adminCrm.updateResult(selected.id, payload) : await sellerCrm.updateResult(selected.id, payload);
      setSelected(data);
      await loadTasks();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить результат');
    } finally {
      setSaving(false);
    }
  }

  async function completeTask() {
    if (!selected) return;
    if (!(sellerComment || selected.seller_comment || '').trim()) {
      setError('Чтобы закрыть задачу, сначала добавьте комментарий продавца.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      let data = selected;
      if (sellerOutcome && sellerComment.trim()) {
        const payload = {
          seller_outcome: sellerOutcome,
          seller_comment: sellerComment,
          next_action_date: nextActionDate || null,
        };
        data = isPreviewMode ? await adminCrm.updateResult(selected.id, payload) : await sellerCrm.updateResult(selected.id, payload);
      }
      data = isPreviewMode ? await adminCrm.completeTask(data.id) : await sellerCrm.completeTask(data.id);
      setSelected(data);
      await loadTasks();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось закрыть задачу');
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f7f4ef] px-4 py-6 text-[#2f2924] md:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="rounded-3xl bg-white p-6 shadow-sm">
          <p className="text-sm uppercase tracking-[0.2em] text-[#9b7f63]">CRM</p>
          <div className="mt-2 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-3xl font-semibold">Ежедневные клиентские задачи</h1>
            </div>
            <label className="text-sm font-medium">
              Дата работы
              <input type="date" value={date} onChange={(event) => setDate(event.target.value)} className="mt-1 block rounded-2xl border border-[#d8c8b8] bg-white px-4 py-2" />
            </label>
          </div>
          <div className="mt-5 grid gap-3 md:grid-cols-5">
            <Counter label="Всего" value={counters.total} active={taskFilter === 'all'} onClick={() => setTaskFilter('all')} />
            <Counter label="Новые" value={counters.new} active={taskFilter === 'new'} onClick={() => setTaskFilter('new')} />
            <Counter label="В работе" value={counters.inProgress} active={taskFilter === 'in_progress'} onClick={() => setTaskFilter('in_progress')} />
            <Counter label="Просрочено" value={counters.overdue} danger active={taskFilter === 'overdue'} onClick={() => setTaskFilter('overdue')} />
            <StaticCounter label="Выполнено" value={counters.completed} />
          </div>
        </header>

        {error && <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}

        <div className="grid gap-5 lg:grid-cols-[420px_1fr]">
          <section className="rounded-3xl bg-white p-4 shadow-sm lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-hidden">
            <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <h2 className="text-lg font-semibold">Список задач</h2>
              <select
                value={groupFilter}
                onChange={(event) => setGroupFilter(event.target.value)}
                className="rounded-2xl border border-[#d8c8b8] bg-white px-3 py-2 text-sm"
                aria-label="Фильтр по типу CRM-задачи"
              >
                <option value="">Все типы</option>
                {groupOptions.map((value) => (
                  <option key={value} value={value}>{CRM_GROUP_LABELS[value] || value}</option>
                ))}
              </select>
            </div>
            {loading ? <p className="text-sm text-gray-500">Загружаю...</p> : null}
            {!loading && visibleTasks.length === 0 ? <p className="rounded-2xl bg-gray-50 p-4 text-sm text-gray-500">По выбранному фильтру задач нет.</p> : null}
            <div className="space-y-3 lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto lg:pr-2">
              {visibleTasks.map((task) => (
                <button
                  key={task.id}
                  onClick={() => setSelectedId(task.id)}
                  className={`w-full rounded-2xl border p-4 text-left transition ${selectedId === task.id ? 'border-[#8a6a4b] bg-[#fbf6ef]' : 'border-[#eee3d8] bg-white hover:bg-[#fbf6ef]'}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold">{task.customer?.full_name || task.customer?.phone || 'Клиент'}</p>
                      <p className="mt-1 text-xs text-[#7b6a5b]">{taskCampaignLabel(task)} · {task.store_name || 'Магазин не указан'} · {CRM_GROUP_LABELS[task.crm_group] || task.crm_group}</p>
                    </div>
                    <span className={`rounded-full px-2.5 py-1 text-xs ${statusClass(task.status)}`}>{STATUS_LABELS[task.status] || task.status}</span>
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm text-[#5d5148]">{task.reason || task.seller_action || 'Повод не указан'}</p>
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-3xl bg-white p-5 shadow-sm">
            {!selected ? (
              <p className="text-sm text-gray-500">Выберите задачу из списка.</p>
            ) : (
              <div className="space-y-5">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-sm text-[#9b7f63]">Карточка клиента</p>
                    <h2 className="text-2xl font-semibold">{selected.customer?.full_name || selected.customer?.phone || 'Клиент'}</h2>
                    <p className="mt-1 text-sm text-[#6f6257]">Телефон: <span className="font-medium">{selected.customer?.phone || '—'}</span></p>
                  </div>
                  <button onClick={startTask} disabled={saving || selected.status !== 'new'} className="rounded-2xl bg-[#2f2924] px-4 py-2 text-sm font-medium text-white disabled:opacity-40">Взять в работу</button>
                </div>

                <div className="grid gap-3 md:grid-cols-4">
                  <Info label="Город/магазин" value={`${selected.customer?.city || '—'} / ${selected.store_name || selected.customer?.preferred_store_name || '—'}`} />
                  <Info label="Покупок" value={String(selected.customer?.total_purchases || 0)} />
                  <Info label="Сумма" value={formatMoney(selected.customer?.total_spent)} />
                  <Info label="Средний чек" value={formatMoney(selected.customer?.average_check)} />
                </div>

                <div className={`rounded-2xl p-4 ${selected.customer?.questionnaire?.do_not_contact ? 'bg-rose-50 text-rose-900' : 'bg-[#edf5ef] text-[#254b33]'}`}>
                  <h3 className="font-semibold">Канал контакта из анкеты</h3>
                  <p className="mt-2 text-sm">{selected.customer?.contact_instruction || 'Канал связи не указан: уточните его у клиента.'}</p>
                  {selected.customer?.questionnaire?.purchase_for?.length ? <p className="mt-2 text-sm">Покупает: {selected.customer.questionnaire.purchase_for.join(', ')}.</p> : null}
                  {selected.customer?.questionnaire?.glame_values?.length ? <p className="mt-1 text-sm">Важно: {selected.customer.questionnaire.glame_values.join(', ')}.</p> : null}
                </div>

                <div className="space-y-4">
                  <div className="rounded-2xl bg-[#fbf6ef] p-4">
                    <h3 className="font-semibold">Что сделать</h3>
                    <p className="mt-2 whitespace-pre-wrap text-sm text-[#5d5148]">{selected.seller_action || selected.reason || 'Действие не задано'}</p>
                  </div>
                  <div className="rounded-2xl bg-[#f2eee8] p-4">
                    <h3 className="font-semibold">Скрипт / текст</h3>
                    <p className="mt-2 whitespace-pre-wrap text-sm text-[#5d5148]">{selected.script_text || 'Скрипт не задан'}</p>
                  </div>
                </div>

                <ArrivalBlock task={selected} />

                <div className="rounded-2xl border border-[#eee3d8] p-4">
                  <h3 className="font-semibold">Зафиксировать результат</h3>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <label className="text-sm font-medium">Итог
                      <select value={sellerOutcome} onChange={(event) => setSellerOutcome(event.target.value)} className="mt-1 block w-full rounded-2xl border border-[#d8c8b8] px-4 py-2">
                        {OUTCOMES.map((outcome) => <option key={outcome.value} value={outcome.value}>{outcome.label}</option>)}
                      </select>
                    </label>
                    <label className="text-sm font-medium">Следующая дата
                      <input type="date" value={nextActionDate} onChange={(event) => setNextActionDate(event.target.value)} className="mt-1 block w-full rounded-2xl border border-[#d8c8b8] px-4 py-2" />
                    </label>
                  </div>
                  <label className="mt-3 block text-sm font-medium">Комментарий продавца
                    <textarea value={sellerComment} onChange={(event) => setSellerComment(event.target.value)} rows={4} className="mt-1 block w-full rounded-2xl border border-[#d8c8b8] px-4 py-3" placeholder="Что реально произошло: дозвонились/ответила/что попросила/что отправили" />
                  </label>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <button onClick={saveResult} disabled={saving || !sellerComment.trim()} className="rounded-2xl bg-[#8a6a4b] px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50">Сохранить результат</button>
                    <button onClick={completeTask} disabled={saving || !(sellerComment || selected.seller_comment || '').trim()} className="rounded-2xl border border-[#8a6a4b] px-5 py-2.5 text-sm font-medium text-[#8a6a4b] disabled:opacity-50">Закрыть задачу</button>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <History title="История задачи" rows={selected.events.map((event) => `${event.created_at ? new Date(event.created_at).toLocaleString('ru-RU') : ''} · ${event.event_type} · ${event.actor_name || 'system'}`)} />
                  <History title="Последние коммуникации" rows={selected.recent_messages.map((msg) => `${msg.created_at ? new Date(msg.created_at).toLocaleDateString('ru-RU') : ''} · ${msg.message || msg.event_type || 'сообщение'}`)} />
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}

function Counter({ label, value, danger, active, onClick }: { label: string; value: number; danger?: boolean; active?: boolean; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-2xl p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-[#8a6a4b] ${
        danger ? 'bg-red-50 text-red-800' : 'bg-[#fbf6ef]'
      } ${active ? 'ring-2 ring-[#8a6a4b]' : ''}`}
    >
      <p className="text-xs uppercase tracking-wide opacity-70">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </button>
  );
}

function StaticCounter({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl bg-[#f4efe8] p-4 text-left text-[#2f2924]">
      <p className="text-xs uppercase tracking-wide opacity-70">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div className="rounded-2xl bg-[#faf9f7] p-4"><p className="text-xs text-[#8a7a6b]">{label}</p><p className="mt-1 font-semibold">{value}</p></div>;
}

function History({ title, rows }: { title: string; rows: string[] }) {
  return <div className="rounded-2xl bg-[#faf9f7] p-4"><h3 className="font-semibold">{title}</h3>{rows.length ? <ul className="mt-2 space-y-2 text-sm text-[#5d5148]">{rows.map((row, index) => <li key={`${row}-${index}`}>{row}</li>)}</ul> : <p className="mt-2 text-sm text-gray-500">Пока пусто</p>}</div>;
}
