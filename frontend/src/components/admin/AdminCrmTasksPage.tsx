'use client';

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { adminCrm, type CrmCampaignAnalyticsItem, type CrmCampaignAnalyticsPurchase, type CrmCampaignAnalyticsResponse, type CrmDashboardResponse, type CrmOptionItem, type CrmTaskDto } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import SellerCrmPage from '@/components/profile/SellerCrmPage';

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

const OUTCOME_LABELS: Record<string, string> = {
  no_answer: 'Не дозвонились',
  sent_no_reply: 'Отправлено, ответа нет',
  replied: 'Ответила',
  requested_photo_video: 'Попросила видео/фото',
  photo_video_sent: 'Видео/фото отправлено',
  service_requested: 'Нужен сервис',
  sale: 'Продажа',
  postpone: 'Перенести',
  not_relevant: 'Неактуально',
  do_not_disturb: 'Не беспокоить',
  quality_complaint: 'Жалоба на качество',
  create_cdek: 'Создать накладную СДЭК',
  in_dialogue: 'В диалоге',
  waiting_in_store: 'Ждём в магазине',
  purchased: 'Покупка',
  service: 'Сервис',
  interested: 'Заинтересовалась',
  not_interested: 'Не интересно',
  out_of_town: 'Не в городе',
  online_selection: 'Онлайн-подбор',
  asked_for_video: 'Попросила видео',
  asked_for_more_photos: 'Попросила ещё фото',
  plans_visit: 'Планирует визит',
  no_response: 'Нет ответа',
  follow_up_later: 'Связаться позже',
};

const ACTIVE_STATUS_FILTER = 'new,in_progress,postponed';
const COMPLETED_STATUS_FILTER = 'worked,closed,not_relevant,do_not_disturb,quality_complaint';
const DEFAULT_TASK_STATUS_FILTER = ACTIVE_STATUS_FILTER;

function today() {
  return new Date().toISOString().slice(0, 10);
}

function minusDays(days: number) {
  const value = new Date();
  value.setDate(value.getDate() - days);
  return value.toISOString().slice(0, 10);
}

function formatMoney(value?: number | null) {
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format((value || 0) / 100);
}

function formatDate(value?: string | null) {
  if (!value) return '—';
  return new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString('ru-RU');
}

function statusTone(status: string) {
  if (status === 'new') return 'bg-blue-50 text-blue-700 border-blue-100';
  if (status === 'in_progress') return 'bg-amber-50 text-amber-700 border-amber-100';
  if (status === 'overdue') return 'bg-red-50 text-red-700 border-red-100';
  if (status === 'worked' || status === 'closed') return 'bg-emerald-50 text-emerald-700 border-emerald-100';
  if (status === 'quality_complaint') return 'bg-rose-50 text-rose-700 border-rose-100';
  if (status === 'postponed') return 'bg-purple-50 text-purple-700 border-purple-100';
  return 'bg-gray-50 text-gray-700 border-gray-100';
}

function uniqSorted(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.map((value) => (value || '').trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'ru'));
}

function isLegacyMeganomStore(value?: string | null) {
  const normalized = String(value || '').trim().toLowerCase();
  return normalized.includes('меганом') || normalized.includes('meganom');
}

function mergeOptions(primary: CrmOptionItem[], fallbackValues: string[]) {
  const byValue = new Map<string, CrmOptionItem>();
  primary.forEach((option) => {
    if (isLegacyMeganomStore(option.value) || isLegacyMeganomStore(option.label)) return;
    if (option.value) byValue.set(option.value, option);
  });
  fallbackValues.forEach((value) => {
    if (isLegacyMeganomStore(value)) return;
    if (value && !byValue.has(value)) byValue.set(value, { value, label: value });
  });
  return Array.from(byValue.values()).sort((a, b) => a.label.localeCompare(b.label, 'ru'));
}

function taskSellerLabel(task: CrmTaskDto) {
  if (task.assigned_seller_user_id) return task.assigned_seller_name || 'Продавец платформы';
  if (task.assigned_seller_name) return `Не назначен на пользователя (${task.assigned_seller_name})`;
  return 'Не назначен';
}

function taskCampaignLabel(task: CrmTaskDto) {
  return task.campaign_name || task.campaign_id || 'Кампания не указана';
}

function taskDateBadge(task: CrmTaskDto) {
  if (task.completed_at || ['worked', 'closed', 'not_relevant', 'do_not_disturb', 'quality_complaint'].includes(task.status)) {
    return `Закрыта: ${formatDate(task.completed_at || task.updated_at || task.work_date)}`;
  }
  return `Дата задачи: ${formatDate(task.work_date)}`;
}

export default function AdminCrmTasksPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const isFullAdmin = user?.role === 'admin' && !user?.is_role_preview;
  const canDeleteTask = isFullAdmin;
  const [tasks, setTasks] = useState<CrmTaskDto[]>([]);
  const [dashboard, setDashboard] = useState<CrmDashboardResponse | null>(null);
  const [analytics, setAnalytics] = useState<CrmCampaignAnalyticsResponse | null>(null);
  const [activeTab, setActiveTab] = useState<'tasks' | 'sellers' | 'analytics'>('tasks');
  const [options, setOptions] = useState<{ stores: CrmOptionItem[]; sellers: CrmOptionItem[]; campaigns: CrmOptionItem[]; customerSegments: CrmOptionItem[] }>({
    stores: [],
    sellers: [],
    campaigns: [],
    customerSegments: [],
  });
  const [selected, setSelected] = useState<CrmTaskDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    start_date: minusDays(7),
    end_date: today(),
    store_name: '',
    seller_user_id: '',
    campaign_id: '',
    customer_query: '',
    customer_segment: '',
    min_total_spent: '',
    max_total_spent: '',
    status: DEFAULT_TASK_STATUS_FILTER,
    crm_group: '',
    only_overdue: false,
    only_without_comment: false,
    only_with_attribution: false,
  });
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [assignSellerUserId, setAssignSellerUserId] = useState('');
  const [assignStoreName, setAssignStoreName] = useState('');
  const [resultOutcome, setResultOutcome] = useState('');
  const [resultComment, setResultComment] = useState('');
  const [resultNextActionDate, setResultNextActionDate] = useState('');
  const [taskSaving, setTaskSaving] = useState(false);
  const [touchpointsGenerating, setTouchpointsGenerating] = useState(false);
  const [birthdaysGenerating, setBirthdaysGenerating] = useState(false);
  const [birthdayPreviewCreating, setBirthdayPreviewCreating] = useState(false);
  const [newArrivalsGenerating, setNewArrivalsGenerating] = useState(false);

  const params = useMemo(() => {
    const clean: Record<string, any> = { limit: 300 };
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== '' && value !== false && value !== null && value !== undefined) clean[key] = value;
    });
    return clean;
  }, [filters]);

  const summaryParams = useMemo(() => {
    const clean: Record<string, any> = {};
    Object.entries(filters).forEach(([key, value]) => {
      if (['status', 'only_overdue', 'only_without_comment', 'only_with_attribution'].includes(key)) return;
      if (value !== '' && value !== false && value !== null && value !== undefined) clean[key] = value;
    });
    return clean;
  }, [filters]);

  const filterOptions = useMemo(() => {
    const stores = mergeOptions(options.stores, uniqSorted(tasks.map((task) => task.store_name)));
    const sellers = mergeOptions(options.sellers, []);
    const campaigns = mergeOptions(options.campaigns, uniqSorted(tasks.map((task) => task.campaign_id)));
    const customerSegments = mergeOptions(options.customerSegments, uniqSorted(tasks.map((task) => task.customer?.customer_segment)));
    const groups = uniqSorted(tasks.map((task) => task.crm_group));
    if (filters.store_name && !stores.some((option) => option.value === filters.store_name)) stores.unshift({ value: filters.store_name, label: filters.store_name });
    if (filters.seller_user_id && !sellers.some((option) => option.value === filters.seller_user_id)) sellers.unshift({ value: filters.seller_user_id, label: filters.seller_user_id });
    if (filters.campaign_id && !campaigns.some((option) => option.value === filters.campaign_id)) campaigns.unshift({ value: filters.campaign_id, label: filters.campaign_id });
    if (filters.customer_segment && !customerSegments.some((option) => option.value === filters.customer_segment)) customerSegments.unshift({ value: filters.customer_segment, label: filters.customer_segment });
    if (filters.crm_group && !groups.includes(filters.crm_group)) groups.unshift(filters.crm_group);
    return { stores, sellers, campaigns, customerSegments, groups };
  }, [filters.campaign_id, filters.crm_group, filters.customer_segment, filters.seller_user_id, filters.store_name, options.campaigns, options.customerSegments, options.sellers, options.stores, tasks]);

  useEffect(() => {
    if (authLoading || !isFullAdmin) {
      setOptions({ stores: [], sellers: [], campaigns: [], customerSegments: [] });
      return;
    }
    let alive = true;
    adminCrm.options()
      .then((data) => {
        if (alive) setOptions({ stores: data.stores || [], sellers: data.sellers || [], campaigns: data.campaigns || [], customerSegments: data.customer_segments || [] });
      })
      .catch(() => {
        if (alive) setOptions({ stores: [], sellers: [], campaigns: [], customerSegments: [] });
      });
    return () => {
      alive = false;
    };
  }, [authLoading, isFullAdmin]);

  const load = useCallback(async () => {
    if (authLoading) return;
    if (!isFullAdmin) {
      setTasks([]);
      setDashboard(null);
      setAnalytics(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [list, stats, campaignStats] = await Promise.all([adminCrm.listTasks(params), adminCrm.dashboard(summaryParams), adminCrm.analytics({ ...summaryParams, window_days: 14 })]);
      setTasks(list.items);
      setDashboard(stats);
      setAnalytics(campaignStats);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось загрузить CRM-задачи');
    } finally {
      setLoading(false);
    }
  }, [authLoading, isFullAdmin, params, summaryParams]);

  useEffect(() => {
    load();
  }, [load]);

  async function openTask(task: CrmTaskDto) {
    try {
      const detailed = await adminCrm.getTask(task.id);
      setSelected(detailed);
      setAssignSellerUserId(detailed.assigned_seller_user_id || '');
      setAssignStoreName(detailed.store_name || '');
      setResultOutcome(detailed.seller_outcome || '');
      setResultComment(detailed.seller_comment || '');
      setResultNextActionDate(detailed.next_action_date || '');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось открыть задачу');
    }
  }

  async function assignTask() {
    if (!selected) return;
    const selectedStore = filterOptions.stores.find((store) => store.value === assignStoreName);
    try {
      const updated = await adminCrm.assignTask(selected.id, {
        assigned_seller_user_id: assignSellerUserId || null,
        store_id: selectedStore?.external_id || null,
        store_name: selectedStore?.store_name || assignStoreName || null,
      });
      setSelected(updated);
      setAssignSellerUserId(updated.assigned_seller_user_id || '');
      setAssignStoreName(updated.store_name || '');
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось переназначить задачу');
    }
  }

  async function saveTaskResult() {
    if (!selected) return;
    setTaskSaving(true);
    setError(null);
    try {
      const updated = await adminCrm.updateResult(selected.id, {
        seller_outcome: resultOutcome,
        seller_comment: resultComment,
        next_action_date: resultOutcome === 'postpone' ? resultNextActionDate || null : resultNextActionDate || null,
      });
      setSelected(updated);
      setResultOutcome(updated.seller_outcome || '');
      setResultComment(updated.seller_comment || '');
      setResultNextActionDate(updated.next_action_date || '');
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сохранить результат задачи');
    } finally {
      setTaskSaving(false);
    }
  }

  async function startSelectedTask() {
    if (!selected) return;
    setTaskSaving(true);
    setError(null);
    try {
      const updated = await adminCrm.startTask(selected.id);
      setSelected(updated);
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось взять задачу в работу');
    } finally {
      setTaskSaving(false);
    }
  }

  async function completeSelectedTask() {
    if (!selected) return;
    setTaskSaving(true);
    setError(null);
    try {
      const updated = await adminCrm.completeTask(selected.id);
      setSelected(updated);
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось закрыть задачу');
    } finally {
      setTaskSaving(false);
    }
  }

  async function deleteSelectedTask() {
    if (!selected) return;
    const customerName = selected.customer?.full_name || selected.customer?.phone || 'эту задачу';
    if (!window.confirm(`Удалить CRM-задачу «${customerName}»? Это действие удалит задачу и ее историю событий.`)) return;
    setTaskSaving(true);
    setError(null);
    try {
      await adminCrm.deleteTask(selected.id);
      setSelected(null);
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось удалить задачу');
    } finally {
      setTaskSaving(false);
    }
  }

  async function attributePurchases() {
    try {
      const result = await adminCrm.attributePurchases({ start_date: filters.start_date || null, end_date: filters.end_date || null, window_days: 14 });
      await load();
      setError(`Атрибуция обновлена: задач ${result.updated}, покупок ${result.purchase_count}, сумма ${formatMoney(result.revenue_kopecks)}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось обновить атрибуцию');
    }
  }

  async function generateTouchpoints() {
    setTouchpointsGenerating(true);
    setError(null);
    try {
      const result = await adminCrm.generateTouchpoints({
        work_date: filters.end_date || today(),
        warranty_days: 30,
        limit_documents_per_rule: 2000,
      });
      await load();
      setError(`Касания после покупки: создано ${result.created}, пропущено ${result.skipped}, ошибок ${result.errors?.length || 0}.`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сгенерировать касания после покупки');
    } finally {
      setTouchpointsGenerating(false);
    }
  }

  async function generateBirthdayTasks() {
    setBirthdaysGenerating(true);
    setError(null);
    try {
      const result = await adminCrm.generateBirthdayTasks({
        work_date: filters.end_date || today(),
        days_ahead: 3,
        limit: 500,
      });
      await load();
      setError(`Поздравления с ДР: создано ${result.created}, пропущено ${result.skipped}, ошибок ${result.errors?.length || 0}.`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сгенерировать задачи по дням рождения');
    } finally {
      setBirthdaysGenerating(false);
    }
  }

  async function createBirthdayVipPreview() {
    setBirthdayPreviewCreating(true);
    setError(null);
    try {
      const task = await adminCrm.createBirthdayVipPreview({
        work_date: filters.end_date || today(),
      });
      await load();
      setSelected(task);
      setAssignSellerUserId(task.assigned_seller_user_id || '');
      setAssignStoreName(task.store_name || '');
      setResultOutcome(task.seller_outcome || '');
      setResultComment(task.seller_comment || '');
      setResultNextActionDate(task.next_action_date || '');
      setError('Создана тестовая VIP-задача ДР с демо-сертификатом. Автоотправки нет, реальный сертификат не выпускается.');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось создать тестовую VIP-задачу ДР');
    } finally {
      setBirthdayPreviewCreating(false);
    }
  }

  async function generateNewArrivalTasks() {
    setNewArrivalsGenerating(true);
    setError(null);
    try {
      const result = await adminCrm.generateNewArrivalTasks({
        work_date: filters.end_date || today(),
        source: 'primary_receipt_only',
        create_seller_tasks: false,
        prepare_push: false,
        send_push: false,
        dry_run: true,
      });
      await load();
      const receiptSync = result.receipt_sync || {};
      const receiptPart = receiptSync.enabled === false
        ? ' Синхронизация приходов отключена.'
        : ` Приходы 1С: документов ${receiptSync.receipts ?? 0}, событий ${receiptSync.created ?? 0}.`;
      const transferSync = result.transfer_sync || {};
      const transferPart = transferSync.ignored_as_new_arrival_source
        ? ` Перемещения: ${transferSync.transfers ?? 0}, как источник новинок игнорируются.`
        : '';
      setError(`Проверка новых поступлений: к созданию задач ${result.tasks_previewed ?? 0}, без записей и отправок. Пропущено ${result.skipped}, ошибок ${result.errors?.length || 0}.${receiptPart}${transferPart}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось сгенерировать задачи по новому поступлению');
    } finally {
      setNewArrivalsGenerating(false);
    }
  }

  function applyKpiFilter(kind: 'all' | 'active' | 'completed' | 'overdue' | 'without_comment' | 'with_attribution') {
    setSelected(null);
    setFilters((old) => ({
      ...old,
      status: kind === 'all' || kind === 'active' ? DEFAULT_TASK_STATUS_FILTER : kind === 'completed' ? COMPLETED_STATUS_FILTER : '',
      only_overdue: kind === 'overdue',
      only_without_comment: kind === 'without_comment',
      only_with_attribution: kind === 'with_attribution',
    }));
  }

  function isKpiActive(kind: 'all' | 'active' | 'completed' | 'overdue' | 'without_comment' | 'with_attribution') {
    if (kind === 'active') return filters.status === ACTIVE_STATUS_FILTER && !filters.only_overdue && !filters.only_without_comment && !filters.only_with_attribution;
    if (kind === 'completed') return filters.status === COMPLETED_STATUS_FILTER && !filters.only_overdue && !filters.only_without_comment && !filters.only_with_attribution;
    if (kind === 'overdue') return filters.only_overdue;
    if (kind === 'without_comment') return filters.only_without_comment;
    if (kind === 'with_attribution') return filters.only_with_attribution;
    return false;
  }

  if (authLoading) {
    return (
      <main className="min-h-screen bg-[#f7f4ef] px-4 py-6 text-[#2f2924] md:px-8">
        <div className="mx-auto max-w-7xl rounded-3xl bg-white p-6 shadow-sm">
          <p className="text-sm text-[#6f6257]">Проверяю права доступа…</p>
        </div>
      </main>
    );
  }

  if (!isFullAdmin) {
    return <SellerCrmPage />;
  }

  return (
    <main className="min-h-screen bg-[#f7f4ef] px-4 py-6 text-[#2f2924] md:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="rounded-3xl bg-white p-6 shadow-sm">
          <p className="text-sm uppercase tracking-[0.2em] text-[#9b7f63]">Контроль CRM продавцов</p>
          <div className="mt-2 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="text-3xl font-semibold">CRM-задачи продавцов</h1>
              <p className="mt-2 max-w-3xl text-sm text-[#6f6257]">Контроль задач, результатов и продаж после клиентских касаний.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => router.push('/ai-marketer/boards/crm?new_campaign=1')} className="rounded-2xl bg-[#2f2924] px-4 py-2 text-sm font-medium text-white">Новая кампания</button>
              <button onClick={generateBirthdayTasks} disabled={birthdaysGenerating} className="rounded-2xl border border-[#8a6a4b] bg-white px-4 py-2 text-sm font-medium text-[#8a6a4b] disabled:opacity-50">
                {birthdaysGenerating ? 'Генерирую ДР...' : 'Сгенерировать ДР'}
              </button>
              <button onClick={createBirthdayVipPreview} disabled={birthdayPreviewCreating} className="rounded-2xl border border-[#8a6a4b] bg-white px-4 py-2 text-sm font-medium text-[#8a6a4b] disabled:opacity-50">
                {birthdayPreviewCreating ? 'Создаю демо...' : 'Демо VIP ДР'}
              </button>
              <button onClick={generateTouchpoints} disabled={touchpointsGenerating} className="rounded-2xl border border-[#8a6a4b] bg-white px-4 py-2 text-sm font-medium text-[#8a6a4b] disabled:opacity-50">
                {touchpointsGenerating ? 'Генерирую...' : 'Сгенерировать касания'}
              </button>
              <button onClick={generateNewArrivalTasks} disabled={newArrivalsGenerating} className="rounded-2xl border border-[#8a6a4b] bg-white px-4 py-2 text-sm font-medium text-[#8a6a4b] disabled:opacity-50">
                {newArrivalsGenerating ? 'Проверяю новинки...' : 'Проверить новинки (dry-run)'}
              </button>
              <button onClick={attributePurchases} className="rounded-2xl border border-[#8a6a4b] px-4 py-2 text-sm font-medium text-[#8a6a4b]">Обновить атрибуцию продаж</button>
            </div>
          </div>
        </header>

        {dashboard && (
          <section className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
            <Kpi label="Всего" value={dashboard.total} active={isKpiActive('all')} onClick={() => applyKpiFilter('all')} />
            <Kpi label="Активные" value={dashboard.active} active={isKpiActive('active')} onClick={() => applyKpiFilter('active')} />
            <Kpi label="Закрытые" value={dashboard.completed} active={isKpiActive('completed')} onClick={() => applyKpiFilter('completed')} />
            <Kpi label="Просрочены" value={dashboard.overdue} danger active={isKpiActive('overdue')} onClick={() => applyKpiFilter('overdue')} />
            <Kpi label="Без комментария" value={dashboard.without_comment} danger active={isKpiActive('without_comment')} onClick={() => applyKpiFilter('without_comment')} />
            <Kpi label="Продажи после касания" value={formatMoney(dashboard.attributed_revenue_kopecks)} active={isKpiActive('with_attribution')} onClick={() => applyKpiFilter('with_attribution')} />
          </section>
        )}

        <section className="relative rounded-3xl bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="flex flex-wrap items-end gap-3">
              <FilterDate inline label="С" value={filters.start_date} onChange={(value) => setFilters((old) => ({ ...old, start_date: value }))} />
              <FilterDate inline label="По" value={filters.end_date} onChange={(value) => setFilters((old) => ({ ...old, end_date: value }))} />
              <button
                type="button"
                onClick={() => load()}
                className="rounded-2xl bg-[#2f2924] px-4 py-2 text-sm font-medium text-white"
              >
                Применить
              </button>
            </div>
            <button
              type="button"
              onClick={() => setFiltersOpen((value) => !value)}
              className="rounded-2xl border border-[#8a6a4b] px-4 py-2 text-sm font-medium text-[#8a6a4b]"
            >
              Фильтры
            </button>
          </div>
          {filtersOpen && (
            <div className="absolute left-4 right-4 top-[calc(100%+8px)] z-20 rounded-3xl border border-[#eadfd4] bg-white p-4 shadow-xl">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                <FilterSelect label="Кампания" value={filters.campaign_id} options={filterOptions.campaigns} onChange={(value) => setFilters((old) => ({ ...old, campaign_id: value }))} />
                <FilterSelect label="Магазин" value={filters.store_name} options={filterOptions.stores} onChange={(value) => setFilters((old) => ({ ...old, store_name: value }))} />
                <FilterSelect label="Продавец" value={filters.seller_user_id} options={filterOptions.sellers} onChange={(value) => setFilters((old) => ({ ...old, seller_user_id: value }))} />
                <FilterSelect label="Группа" value={filters.crm_group} options={filterOptions.groups.map((value) => ({ value, label: CRM_GROUP_LABELS[value] || value }))} onChange={(value) => setFilters((old) => ({ ...old, crm_group: value }))} />
                <FilterSelect
                  label="Статус"
                  value={filters.status}
                  options={[
                    { value: ACTIVE_STATUS_FILTER, label: 'Активные' },
                    { value: COMPLETED_STATUS_FILTER, label: 'Закрытые' },
                    ...Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label })),
                  ]}
                  onChange={(value) => setFilters((old) => ({ ...old, status: value, only_overdue: false, only_without_comment: false, only_with_attribution: false }))}
                />
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                <label className="block text-xs text-[#6f6257] xl:col-span-2">
                  Клиент
                  <input
                    value={filters.customer_query}
                    onChange={(event) => setFilters((old) => ({ ...old, customer_query: event.target.value }))}
                    placeholder="Имя, телефон или email"
                    className="mt-1 w-full rounded-2xl border border-[#d9c8b8] px-3 py-2 text-sm text-[#1f1b17]"
                  />
                </label>
                <FilterSelect
                  label="Сегмент"
                  value={filters.customer_segment}
                  options={filterOptions.customerSegments}
                  onChange={(value) => setFilters((old) => ({ ...old, customer_segment: value }))}
                />
                <label className="block text-xs text-[#6f6257]">
                  Сумма покупок от, ₽
                  <input
                    type="number"
                    min="0"
                    value={filters.min_total_spent}
                    onChange={(event) => setFilters((old) => ({ ...old, min_total_spent: event.target.value }))}
                    placeholder="например 100000"
                    className="mt-1 w-full rounded-2xl border border-[#d9c8b8] px-3 py-2 text-sm text-[#1f1b17]"
                  />
                </label>
                <label className="block text-xs text-[#6f6257]">
                  Сумма покупок до, ₽
                  <input
                    type="number"
                    min="0"
                    value={filters.max_total_spent}
                    onChange={(event) => setFilters((old) => ({ ...old, max_total_spent: event.target.value }))}
                    placeholder="например 300000"
                    className="mt-1 w-full rounded-2xl border border-[#d9c8b8] px-3 py-2 text-sm text-[#1f1b17]"
                  />
                </label>
              </div>
              <p className="mt-3 text-xs text-[#8a7c6f]">
                Для ВИП-клиентов выберите сегмент VIP или задайте сумму покупок от нужного порога.
              </p>
              <div className="mt-4 flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setFilters((old) => ({ ...old, customer_query: '', customer_segment: '', min_total_spent: '', max_total_spent: '' }))}
                  className="rounded-2xl border border-[#d9c8b8] px-4 py-2 text-sm font-medium text-[#8a6a4b]"
                >
                  Очистить клиентов
                </button>
                <button type="button" onClick={() => { setFiltersOpen(false); void load(); }} className="rounded-2xl bg-[#2f2924] px-4 py-2 text-sm font-medium text-white">
                  Применить
                </button>
                <button type="button" onClick={() => setFiltersOpen(false)} className="rounded-2xl border border-[#8a6a4b] px-4 py-2 text-sm font-medium text-[#8a6a4b]">
                  Закрыть
                </button>
              </div>
            </div>
          )}
        </section>

        <section className="flex flex-wrap gap-2 rounded-3xl bg-white p-2 shadow-sm">
          <TabButton active={activeTab === 'tasks'} onClick={() => setActiveTab('tasks')}>Задачи</TabButton>
          <TabButton active={activeTab === 'sellers'} onClick={() => setActiveTab('sellers')}>Аналитика продавцов</TabButton>
          <TabButton active={activeTab === 'analytics'} onClick={() => setActiveTab('analytics')}>Аналитика кампаний</TabButton>
        </section>

        {error && <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">{error}</div>}

        {activeTab === 'sellers' && <SellerAnalyticsPanel dashboard={dashboard} loading={loading} />}

        {activeTab === 'analytics' && <CampaignAnalyticsPanel analytics={analytics} loading={loading} />}

        {activeTab === 'tasks' && <div>
          <section className="overflow-hidden rounded-3xl bg-white shadow-sm">
            <div className="border-b border-[#eee3d8] p-4 font-semibold">Задачи {loading ? '· загружаю…' : `· ${tasks.length}`}</div>
            <div className="divide-y divide-[#eee3d8]">
              {tasks.map((task) => (
                <button key={task.id} onClick={() => openTask(task)} className="block w-full p-4 text-left hover:bg-[#fbf6ef]">
                  <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                    <div>
                      <p className="font-semibold">{task.customer?.full_name || task.customer?.phone || 'Клиент'}</p>
                      <p className="text-sm text-[#6f6257]">
                        {taskCampaignLabel(task)} · {taskSellerLabel(task)} · {task.store_name || 'магазин не указан'} · {CRM_GROUP_LABELS[task.crm_group] || task.crm_group}
                      </p>
                      <p className="mt-1 line-clamp-2 text-sm text-[#5d5148]">{task.reason || task.seller_action || 'Повод не указан'}</p>
                    </div>
                    <div className="flex flex-wrap gap-2 md:justify-end">
                      <span className={`rounded-full border px-2.5 py-1 text-xs ${statusTone(task.status)}`}>{STATUS_LABELS[task.status] || task.status}</span>
                      <span className="rounded-full bg-[#f2eee8] px-2.5 py-1 text-xs">{taskDateBadge(task)}</span>
                      {task.attributed_revenue_kopecks > 0 && <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs text-emerald-700">{formatMoney(task.attributed_revenue_kopecks)}</span>}
                    </div>
                  </div>
                </button>
              ))}
              {!tasks.length && <p className="p-6 text-sm text-gray-500">По фильтрам задач нет.</p>}
            </div>
          </section>
        </div>}
        {selected && (
          <CrmTaskModal
            task={selected}
            sellers={filterOptions.sellers}
            stores={filterOptions.stores}
            assignSellerUserId={assignSellerUserId}
            assignStoreName={assignStoreName}
            resultOutcome={resultOutcome}
            resultComment={resultComment}
            resultNextActionDate={resultNextActionDate}
            saving={taskSaving}
            onAssignSellerChange={setAssignSellerUserId}
            onAssignStoreChange={setAssignStoreName}
            onOutcomeChange={setResultOutcome}
            onCommentChange={setResultComment}
            onNextActionDateChange={setResultNextActionDate}
            onClose={() => setSelected(null)}
            onAssign={assignTask}
            onSaveResult={saveTaskResult}
            onStart={startSelectedTask}
            onComplete={completeSelectedTask}
            onDelete={deleteSelectedTask}
            canDelete={canDeleteTask}
          />
        )}
      </div>
    </main>
  );
}

function CrmTaskModal({
  task,
  sellers,
  stores,
  assignSellerUserId,
  assignStoreName,
  resultOutcome,
  resultComment,
  resultNextActionDate,
  saving,
  onAssignSellerChange,
  onAssignStoreChange,
  onOutcomeChange,
  onCommentChange,
  onNextActionDateChange,
  onClose,
  onAssign,
  onSaveResult,
  onStart,
  onComplete,
  onDelete,
  canDelete,
}: {
  task: CrmTaskDto;
  sellers: CrmOptionItem[];
  stores: CrmOptionItem[];
  assignSellerUserId: string;
  assignStoreName: string;
  resultOutcome: string;
  resultComment: string;
  resultNextActionDate: string;
  saving: boolean;
  onAssignSellerChange: (value: string) => void;
  onAssignStoreChange: (value: string) => void;
  onOutcomeChange: (value: string) => void;
  onCommentChange: (value: string) => void;
  onNextActionDateChange: (value: string) => void;
  onClose: () => void;
  onAssign: () => void;
  onSaveResult: () => void;
  onStart: () => void;
  onComplete: () => void;
  onDelete: () => void;
  canDelete: boolean;
}) {
  const resultDisabled = saving || !resultOutcome || !resultComment.trim() || (resultOutcome === 'postpone' && !resultNextActionDate);
  const canComplete = !['closed', 'not_relevant', 'do_not_disturb', 'quality_complaint'].includes(task.status);
  const newArrivalPayload = task.source_payload?.task_type === 'NEW_ARRIVAL' ? task.source_payload : null;
  const arrivalMedia = Array.isArray(newArrivalPayload?.media) ? newArrivalPayload.media.filter(Boolean).slice(0, 6) : [];
  const arrivalItems = Array.isArray(newArrivalPayload?.items) ? newArrivalPayload.items.slice(0, 8) : [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-h-[92vh] w-full max-w-6xl overflow-hidden rounded-3xl bg-white shadow-2xl">
        <div className="flex flex-col gap-3 border-b border-[#eee3d8] p-5 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-[#9b7f63]">CRM-задача</p>
            <h2 className="mt-1 text-2xl font-semibold">{task.customer?.full_name || task.customer?.phone || 'Клиент'}</h2>
            <p className="mt-1 text-sm text-[#6f6257]">
              {task.customer?.phone || 'телефон не указан'} · {task.store_name || 'магазин не указан'} · {CRM_GROUP_LABELS[task.crm_group] || task.crm_group}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className={`rounded-full border px-3 py-2 text-xs ${statusTone(task.status)}`}>{STATUS_LABELS[task.status] || task.status}</span>
            <button type="button" onClick={onClose} className="rounded-2xl bg-[#2f2924] px-4 py-2 text-sm font-medium text-white">Закрыть окно</button>
          </div>
        </div>

        <div className="max-h-[calc(92vh-110px)] overflow-auto p-5">
          <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
            <section className="space-y-4">
              <div className="rounded-2xl bg-[#fbf6ef] p-4 text-sm leading-6">
                <p><b>Повод:</b> {task.reason || '—'}</p>
                <p className="mt-2"><b>Действие:</b> {task.seller_action || '—'}</p>
                <p className="mt-2 whitespace-pre-wrap"><b>Скрипт:</b> {task.script_text || '—'}</p>
              </div>

              {newArrivalPayload && (
                <div className="rounded-2xl border border-[#eee3d8] p-4">
                  <h3 className="font-semibold">Новое поступление</h3>
                  <p className="mt-2 text-sm text-[#6f6257]">
                    {newArrivalPayload.brand || 'Бренд не указан'} · {newArrivalPayload.physical_store || task.store_name || 'магазин не указан'} · канал: {newArrivalPayload.channel || '—'}
                  </p>
                  {arrivalMedia.length > 0 && (
                    <div className="mt-3 grid grid-cols-3 gap-2 md:grid-cols-6">
                      {arrivalMedia.map((src: string, index: number) => (
                        <a key={`${src}-${index}`} href={src} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-xl border border-[#eee3d8] bg-[#faf9f7]">
                          <img src={src} alt="Новинка GLAME" className="h-24 w-full object-cover" />
                        </a>
                      ))}
                    </div>
                  )}
                  {arrivalItems.length > 0 && (
                    <ul className="mt-3 max-h-44 space-y-2 overflow-auto text-sm text-[#5d5148]">
                      {arrivalItems.map((item: Record<string, any>, index: number) => (
                        <li key={item.product_id || item.sku || index} className="rounded-xl bg-[#fbf6ef] p-3">
                          <b>{item.name || item.sku || 'Товар'}</b>
                          <span className="text-[#6f6257]"> · {item.category || 'категория не указана'} · {formatMoney(Number(item.price || 0))}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <div className="rounded-2xl border border-[#eee3d8] p-4">
                <h3 className="font-semibold">Комментарий и результат</h3>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <FilterSelect
                    label="Итог продавца"
                    value={resultOutcome}
                    options={Object.entries(OUTCOME_LABELS).map(([value, label]) => ({ value, label }))}
                    onChange={onOutcomeChange}
                    emptyLabel="Выбрать итог"
                  />
                  <FilterDate label="Следующая дата" value={resultNextActionDate} onChange={onNextActionDateChange} />
                </div>
                <label className="mt-3 block text-sm font-medium">
                  Комментарий
                  <textarea
                    value={resultComment}
                    onChange={(event) => onCommentChange(event.target.value)}
                    rows={5}
                    className="mt-1 block w-full rounded-2xl border border-[#d8c8b8] px-3 py-2"
                    placeholder="Что произошло: дозвонились, отправили подборку, клиент ответил, договорились о следующем действии…"
                  />
                </label>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button type="button" onClick={onSaveResult} disabled={resultDisabled} className="rounded-2xl bg-[#2f2924] px-4 py-2 text-sm font-medium text-white disabled:opacity-40">Сохранить результат</button>
                  <button type="button" onClick={onStart} disabled={saving || task.status !== 'new'} className="rounded-2xl border border-[#8a6a4b] px-4 py-2 text-sm font-medium text-[#8a6a4b] disabled:opacity-40">Взять в работу</button>
                  <button type="button" onClick={onComplete} disabled={saving || !canComplete} className="rounded-2xl border border-emerald-200 px-4 py-2 text-sm font-medium text-emerald-700 disabled:opacity-40">Закрыть задачу</button>
                </div>
                {resultOutcome === 'postpone' && <p className="mt-2 text-xs text-[#9b7f63]">Для переноса обязательно укажи следующую дату.</p>}
              </div>

              <div className="rounded-2xl border border-[#eee3d8] p-4">
                <h3 className="font-semibold">Переназначить</h3>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <FilterSelect label="Продавец" value={assignSellerUserId} options={sellers} onChange={onAssignSellerChange} emptyLabel="Не назначен" />
                  <FilterSelect label="Магазин" value={assignStoreName} options={stores} onChange={onAssignStoreChange} emptyLabel="Не указан" />
                </div>
                <button type="button" onClick={onAssign} disabled={saving} className="mt-3 rounded-2xl bg-[#8a6a4b] px-4 py-2 text-sm font-medium text-white disabled:opacity-40">Сохранить назначение</button>
              </div>
            </section>

            <aside className="space-y-4">
              <div className="rounded-2xl border border-[#eee3d8] p-4 text-sm">
                <h3 className="font-semibold">Сводка</h3>
                <p className="mt-2"><b>Ответственный:</b> {taskSellerLabel(task)}</p>
                <p className="mt-2"><b>Дата работы:</b> {task.work_date}</p>
                <p className="mt-2"><b>Приоритет:</b> {task.priority}</p>
                <p className="mt-2"><b>Итог сейчас:</b> {task.seller_outcome ? OUTCOME_LABELS[task.seller_outcome] || task.seller_outcome : '—'}</p>
                <p className="mt-2"><b>Комментарий сейчас:</b> {task.seller_comment || '—'}</p>
                <p className="mt-2"><b>Следующая дата:</b> {task.next_action_date || '—'}</p>
                <p className="mt-2"><b>Атрибуция:</b> {task.attributed_purchase_count} покупок · {formatMoney(task.attributed_revenue_kopecks)}</p>
              </div>

              <div className="rounded-2xl bg-[#faf9f7] p-4">
                <h3 className="font-semibold">История задачи</h3>
                {task.events.length ? (
                  <ul className="mt-2 max-h-52 space-y-2 overflow-auto text-sm text-[#5d5148]">
                    {task.events.map((event) => (
                      <li key={event.id}>
                        {event.created_at ? new Date(event.created_at).toLocaleString('ru-RU') : ''} · {event.event_type} · {event.actor_name || 'system'}
                      </li>
                    ))}
                  </ul>
                ) : <p className="mt-2 text-sm text-gray-500">Нет событий</p>}
              </div>

              <div className="rounded-2xl bg-[#faf9f7] p-4">
                <h3 className="font-semibold">Коммуникации покупателя</h3>
                {task.recent_messages?.length ? (
                  <ul className="mt-2 max-h-60 space-y-2 overflow-auto text-sm text-[#5d5148]">
                    {task.recent_messages.map((message) => (
                      <li key={message.id} className="rounded-xl bg-white p-3">
                        <div className="text-xs text-[#9b7f63]">{message.sent_at ? new Date(message.sent_at).toLocaleString('ru-RU') : message.created_at ? new Date(message.created_at).toLocaleString('ru-RU') : ''} · {message.event_type || 'сообщение'}</div>
                        <div className="mt-1 line-clamp-4">{message.message || message.payload?.comment || '—'}</div>
                      </li>
                    ))}
                  </ul>
                ) : <p className="mt-2 text-sm text-gray-500">Коммуникаций пока нет.</p>}
              </div>

              {canDelete && (
                <button type="button" onClick={onDelete} disabled={saving} className="w-full rounded-2xl border border-red-200 px-4 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50 disabled:opacity-40">Удалить задачу</button>
              )}
            </aside>
          </div>
        </div>
      </div>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return <button type="button" onClick={onClick} className={`rounded-2xl px-4 py-2 text-sm font-medium ${active ? 'bg-[#2f2924] text-white' : 'text-[#6f6257] hover:bg-[#fbf6ef]'}`}>{children}</button>;
}

function SellerAnalyticsPanel({ dashboard, loading }: { dashboard: CrmDashboardResponse | null; loading: boolean }) {
  const sellers = (dashboard?.by_seller || []) as Array<Record<string, any>>;
  const rows = sellers.slice(0, 20);
  const maxTotal = Math.max(1, ...rows.map((seller) => Number(seller.total || 0)));
  const maxRevenue = Math.max(1, ...rows.map((seller) => Number(seller.revenue_kopecks || 0)));
  const maxPurchases = Math.max(1, ...rows.map((seller) => Number(seller.purchase_count || 0)));

  if (loading && !dashboard) return <section className="rounded-3xl bg-white p-6 shadow-sm text-sm text-gray-500">Загружаю аналитику продавцов…</section>;
  if (!dashboard || !rows.length) return <section className="rounded-3xl bg-white p-6 shadow-sm text-sm text-gray-500">По текущим фильтрам нет задач для аналитики продавцов.</section>;

  return (
    <section className="space-y-4">
      <div className="grid gap-3 md:grid-cols-5">
        <Kpi label="Ответственных" value={sellers.length} />
        <Kpi label="Открытых задач" value={dashboard.active} />
        <Kpi label="Закрытых задач" value={dashboard.completed} />
        <Kpi label="Просроченных" value={dashboard.overdue} danger />
        <Kpi label="Выручка после CRM" value={formatMoney(dashboard.attributed_revenue_kopecks)} />
      </div>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-[#9b7f63]">Работа ответственных</p>
            <h2 className="mt-1 text-xl font-semibold">Нагрузка, выполнение и продажи по продавцам</h2>
            <p className="mt-1 text-sm text-[#6f6257]">График учитывает выбранный период и фильтры. Видно, у кого много открытых/просроченных задач, а кто дает продажи после обработки.</p>
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-[#6f6257]">
            <LegendDot color="bg-[#8a6a4b]" label="Всего задач" />
            <LegendDot color="bg-[#2f2924]" label="Покупки" />
            <LegendDot color="bg-[#d7aa38]" label="Выручка" />
          </div>
        </div>

        <div className="mt-5 space-y-4">
          {rows.map((seller) => {
            const total = Number(seller.total || 0);
            const active = Number(seller.active || 0);
            const completed = Number(seller.completed || 0);
            const overdue = Number(seller.overdue || 0);
            const purchases = Number(seller.purchase_count || 0);
            const revenue = Number(seller.revenue_kopecks || 0);
            const totalWidth = Math.max(total ? 2 : 0, Math.round((total / maxTotal) * 100));
            const purchaseWidth = Math.max(purchases ? 2 : 0, Math.round((purchases / maxPurchases) * 100));
            const revenueWidth = Math.max(revenue ? 2 : 0, Math.round((revenue / maxRevenue) * 100));
            return (
              <div key={`seller-chart-${seller.seller_user_id || seller.seller_external_id || seller.seller}`} className="rounded-2xl border border-[#eee3d8] p-4">
                <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{seller.seller || 'Не назначено'}</p>
                    <p className="mt-1 text-xs text-[#6f6257]">Открыто: {active} · Закрыто: {completed} · Просрочено: {overdue} · Без комментария: {seller.without_comment || 0}</p>
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-[#5d5148] sm:grid-cols-4 lg:text-right">
                    <span>Выполнение {seller.completion_rate || 0}%</span>
                    <span>Конверсия {seller.conversion_rate || 0}%</span>
                    <span>{purchases} покупок</span>
                    <span>{formatMoney(revenue)}</span>
                  </div>
                </div>
                <div className="mt-3 grid gap-2 md:grid-cols-[110px_1fr_86px] md:items-center">
                  <span className="text-xs text-[#6f6257]">Всего задач</span>
                  <BarTrack width={totalWidth} className="bg-[#8a6a4b]" />
                  <span className="text-xs text-[#6f6257] md:text-right">{total}</span>

                  <span className="text-xs text-[#6f6257]">Покупки</span>
                  <BarTrack width={purchaseWidth} className="bg-[#2f2924]" />
                  <span className="text-xs text-[#6f6257] md:text-right">{purchases}</span>

                  <span className="text-xs text-[#6f6257]">Выручка</span>
                  <BarTrack width={revenueWidth} className="bg-[#d7aa38]" />
                  <span className="text-xs text-[#6f6257] md:text-right">{formatMoney(revenue)}</span>
                </div>
                <div className="mt-3 grid grid-cols-[1fr_auto] items-center gap-3">
                  <div className="h-2 overflow-hidden rounded-full bg-[#f2eee8]" title={`Доля закрытых задач ${seller.completion_rate || 0}%`}>
                    <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.min(100, Math.max(0, Number(seller.completion_rate || 0)))}%` }} />
                  </div>
                  <span className="text-xs text-[#6f6257]">закрыто {seller.completion_rate || 0}%</span>
                </div>
              </div>
            );
          })}
        </div>
        {sellers.length > rows.length && <p className="mt-3 text-xs text-[#9b7f63]">Показаны топ-{rows.length} ответственных по выручке, закрытым и общему числу задач.</p>}
      </section>

      <section className="overflow-hidden rounded-3xl bg-white shadow-sm">
        <div className="border-b border-[#eee3d8] p-4 font-semibold">Таблица эффективности продавцов</div>
        <div className="overflow-auto">
          <table className="w-full min-w-[980px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-[#eee3d8] text-left text-xs uppercase tracking-wide text-[#9b7f63]">
                <th className="p-3">Ответственный</th>
                <th className="p-3 text-right">Всего</th>
                <th className="p-3 text-right">Открыто</th>
                <th className="p-3 text-right">Закрыто</th>
                <th className="p-3 text-right">Просрочено</th>
                <th className="p-3 text-right">Без комм.</th>
                <th className="p-3 text-right">Покупателей</th>
                <th className="p-3 text-right">Покупок</th>
                <th className="p-3 text-right">Конверсия</th>
                <th className="p-3 text-right">Выручка</th>
                <th className="p-3 text-right">₽/закр.</th>
              </tr>
            </thead>
            <tbody>
              {sellers.map((seller) => (
                <tr key={`seller-table-${seller.seller_user_id || seller.seller_external_id || seller.seller}`} className="border-b border-[#f1e8df]">
                  <td className="p-3 font-medium">{seller.seller || 'Не назначено'}</td>
                  <td className="p-3 text-right">{seller.total || 0}</td>
                  <td className="p-3 text-right">{seller.active || 0}</td>
                  <td className="p-3 text-right">{seller.completed || 0}</td>
                  <td className={`p-3 text-right ${Number(seller.overdue || 0) > 0 ? 'font-semibold text-red-700' : ''}`}>{seller.overdue || 0}</td>
                  <td className={`p-3 text-right ${Number(seller.without_comment || 0) > 0 ? 'text-red-700' : ''}`}>{seller.without_comment || 0}</td>
                  <td className="p-3 text-right">{seller.buyers || 0}</td>
                  <td className="p-3 text-right">{seller.purchase_count || 0}</td>
                  <td className="p-3 text-right">{seller.conversion_rate || 0}%</td>
                  <td className="p-3 text-right font-semibold">{formatMoney(seller.revenue_kopecks || 0)}</td>
                  <td className="p-3 text-right">{formatMoney(seller.revenue_per_completed_task_kopecks || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

function CampaignAnalyticsPanel({ analytics, loading }: { analytics: CrmCampaignAnalyticsResponse | null; loading: boolean }) {
  const [details, setDetails] = useState<CrmCampaignAnalyticsItem | null>(null);

  if (loading && !analytics) return <section className="rounded-3xl bg-white p-6 shadow-sm text-sm text-gray-500">Загружаю аналитику кампаний…</section>;
  if (!analytics || !analytics.campaigns.length) return <section className="rounded-3xl bg-white p-6 shadow-sm text-sm text-gray-500">По фильтрам кампаний нет.</section>;
  return (
    <section className="space-y-4">
      <div className="grid gap-3 md:grid-cols-5">
        <Kpi label="Кампаний" value={analytics.total_campaigns} />
        <Kpi label="Получили / задач" value={analytics.total_recipients} />
        <Kpi label="Контактов" value={analytics.total_contacted} />
        <Kpi label="Покупок 14 дней" value={analytics.total_purchases} />
        <Kpi label="Выручка после CRM" value={formatMoney(analytics.total_revenue_kopecks)} />
      </div>
      <CampaignOverviewChart campaigns={analytics.campaigns} />
      <div className="space-y-4">
        {analytics.campaigns.map((campaign) => (
          <article key={`${campaign.campaign_id || campaign.campaign_name}-${campaign.source}`} className="rounded-3xl bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-[#9b7f63]">{campaign.source} · {campaign.campaign_id || 'без id'}</p>
                <h2 className="mt-1 text-xl font-semibold">{campaign.campaign_name}</h2>
                <p className="mt-2 text-sm text-[#6f6257]">Получили: {campaign.recipients} · Контактов: {campaign.contacted} · Закрыто: {campaign.completed}</p>
                <button
                  type="button"
                  onClick={() => setDetails(campaign)}
                  className="mt-3 rounded-2xl border border-[#8a6a4b] px-3 py-1.5 text-sm font-medium text-[#8a6a4b] transition hover:bg-[#fbf6ef]"
                >
                  Открыть результаты
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
                <Metric label="Покупателей" value={campaign.buyers} />
                <Metric label="Покупок" value={campaign.purchases} />
                <Metric label="Конверсия" value={`${campaign.conversion_rate}%`} />
                <Metric label="Выручка/контакт" value={formatMoney(campaign.revenue_per_contact_kopecks)} />
              </div>
            </div>
            <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_1.4fr]">
              <div className="rounded-2xl border border-[#eee3d8] p-4">
                <h3 className="font-semibold">Каналы</h3>
                <div className="mt-3 space-y-2 text-sm">
                  {campaign.by_channel.map((channel) => <div key={channel.channel} className="flex justify-between gap-3"><span>{channel.label}: {channel.contacted}/{channel.recipients}</span><span>{channel.purchases} пок. · {formatMoney(channel.revenue_kopecks)} · {channel.conversion_rate}%</span></div>)}
                </div>
              </div>
              <div className="rounded-2xl border border-[#eee3d8] p-4">
                <h3 className="font-semibold">Покупки после взаимодействия</h3>
                <div className="mt-3 space-y-3 text-sm">
                  {campaign.purchases_list.length ? campaign.purchases_list.slice(0, 8).map((purchase) => (
                    <div key={purchase.task_id} className="rounded-2xl bg-[#fbf6ef] p-3">
                      <div className="flex flex-col gap-1 md:flex-row md:items-start md:justify-between">
                        <span><b>{purchase.customer_name || purchase.customer_phone || 'Клиент'}</b> · {purchase.store_name || 'магазин не указан'} · {purchase.seller_name || 'продавец не указан'}</span>
                        <span className="font-semibold">{formatMoney(purchase.revenue_kopecks)}</span>
                      </div>
                      <p className="mt-1 text-xs text-[#6f6257]">{purchase.purchase_count} покупок · документы: {purchase.purchase_ids.length ? purchase.purchase_ids.join(', ') : '—'}</p>
                    </div>
                  )) : <p className="text-gray-500">Покупок в 14-дневном окне пока нет.</p>}
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>
      {details && <CampaignResultsModal campaign={details} onClose={() => setDetails(null)} />}
    </section>
  );
}

function CampaignResultsModal({ campaign, onClose }: { campaign: CrmCampaignAnalyticsItem; onClose: () => void }) {
  const purchases = campaign.purchases_list;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-h-[90vh] w-full max-w-6xl overflow-hidden rounded-3xl bg-white shadow-2xl">
        <div className="flex flex-col gap-3 border-b border-[#eee3d8] p-5 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-[#9b7f63]">Результаты кампании</p>
            <h2 className="mt-1 text-xl font-semibold">{campaign.campaign_name}</h2>
            <p className="mt-1 text-sm text-[#6f6257]">
              Контактов: {campaign.contacted} · Покупателей: {campaign.buyers} · Покупок: {campaign.purchases} · Выручка: {formatMoney(campaign.revenue_kopecks)}
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-2xl bg-[#2f2924] px-4 py-2 text-sm font-medium text-white">Закрыть</button>
        </div>
        <div className="max-h-[calc(90vh-110px)] overflow-auto p-5">
          {purchases.length ? (
            <table className="w-full min-w-[900px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-[#d8c8b8] text-left text-xs uppercase tracking-wide text-[#9b7f63]">
                  <th className="py-3 pr-4">Покупатель</th>
                  <th className="py-3 pr-4">Телефон</th>
                  <th className="py-3 pr-4">Дата касания</th>
                  <th className="py-3 pr-4">Магазин</th>
                  <th className="py-3 pr-4">Продавец</th>
                  <th className="py-3 pr-4 text-right">Чеков</th>
                  <th className="py-3 pr-4 text-right">Сумма</th>
                  <th className="py-3">Документы</th>
                </tr>
              </thead>
              <tbody>
                {purchases.map((purchase) => <CampaignPurchaseRow key={purchase.task_id} purchase={purchase} />)}
              </tbody>
            </table>
          ) : (
            <p className="rounded-2xl bg-[#fbf6ef] p-4 text-sm text-[#6f6257]">Покупок в выбранном окне пока нет.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function CampaignOverviewChart({ campaigns }: { campaigns: CrmCampaignAnalyticsItem[] }) {
  const rows = campaigns.slice(0, 12);
  const maxContacts = Math.max(1, ...rows.map((campaign) => campaign.contacted || campaign.recipients || 0));
  const maxPurchases = Math.max(1, ...rows.map((campaign) => campaign.purchases || 0));
  const maxRevenue = Math.max(1, ...rows.map((campaign) => campaign.revenue_kopecks || 0));

  return (
    <section className="rounded-3xl bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-[#9b7f63]">Общий график эффективности</p>
          <h2 className="mt-1 text-xl font-semibold">CRM-кампании за выбранный период</h2>
          <p className="mt-1 text-sm text-[#6f6257]">Сравнение кампаний с учетом текущих фильтров: охват, покупки, выручка и конверсия.</p>
        </div>
        <div className="flex flex-wrap gap-3 text-xs text-[#6f6257]">
          <LegendDot color="bg-[#8a6a4b]" label="Контакты" />
          <LegendDot color="bg-[#2f2924]" label="Покупки" />
          <LegendDot color="bg-[#d7aa38]" label="Выручка" />
        </div>
      </div>

      <div className="mt-5 space-y-4">
        {rows.map((campaign) => {
          const contactWidth = Math.max(2, Math.round(((campaign.contacted || campaign.recipients || 0) / maxContacts) * 100));
          const purchaseWidth = Math.max(campaign.purchases ? 2 : 0, Math.round(((campaign.purchases || 0) / maxPurchases) * 100));
          const revenueWidth = Math.max(campaign.revenue_kopecks ? 2 : 0, Math.round(((campaign.revenue_kopecks || 0) / maxRevenue) * 100));
          return (
            <div key={`chart-${campaign.source}-${campaign.campaign_id || campaign.campaign_name}`} className="rounded-2xl border border-[#eee3d8] p-4">
              <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{campaign.campaign_name}</p>
                  <p className="mt-1 truncate text-xs uppercase tracking-[0.14em] text-[#9b7f63]">{campaign.source} · {campaign.campaign_id || 'без id'}</p>
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-[#5d5148] sm:grid-cols-4 lg:text-right">
                  <span>{campaign.contacted}/{campaign.recipients} контактов</span>
                  <span>{campaign.buyers} покупателей</span>
                  <span>{campaign.purchases} покупок</span>
                  <span>{formatMoney(campaign.revenue_kopecks)}</span>
                </div>
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-[110px_1fr_72px] md:items-center">
                <span className="text-xs text-[#6f6257]">Контакты</span>
                <BarTrack width={contactWidth} className="bg-[#8a6a4b]" />
                <span className="text-xs text-[#6f6257] md:text-right">{campaign.contacted}</span>

                <span className="text-xs text-[#6f6257]">Покупки</span>
                <BarTrack width={purchaseWidth} className="bg-[#2f2924]" />
                <span className="text-xs text-[#6f6257] md:text-right">{campaign.purchases}</span>

                <span className="text-xs text-[#6f6257]">Выручка</span>
                <BarTrack width={revenueWidth} className="bg-[#d7aa38]" />
                <span className="text-xs text-[#6f6257] md:text-right">{formatMoney(campaign.revenue_kopecks)}</span>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#f2eee8]" title={`Конверсия ${campaign.conversion_rate}%`}>
                <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.min(100, Math.max(0, campaign.conversion_rate))}%` }} />
              </div>
              <p className="mt-1 text-right text-xs text-[#6f6257]">Конверсия: {campaign.conversion_rate}%</p>
            </div>
          );
        })}
      </div>
      {campaigns.length > rows.length && <p className="mt-3 text-xs text-[#9b7f63]">Показаны топ-{rows.length} кампаний по текущей сортировке аналитики.</p>}
    </section>
  );
}

function BarTrack({ width, className }: { width: number; className: string }) {
  return (
    <div className="h-3 overflow-hidden rounded-full bg-[#f2eee8]">
      <div className={`h-full rounded-full ${className}`} style={{ width: `${Math.min(100, Math.max(0, width))}%` }} />
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return <span className="inline-flex items-center gap-1.5"><span className={`h-2.5 w-2.5 rounded-full ${color}`} />{label}</span>;
}

function CampaignPurchaseRow({ purchase }: { purchase: CrmCampaignAnalyticsPurchase }) {
  return (
    <tr className="border-b border-[#eee3d8] align-top">
      <td className="py-3 pr-4 font-medium">{purchase.customer_name || 'Клиент'}</td>
      <td className="py-3 pr-4">{purchase.customer_phone || '—'}</td>
      <td className="py-3 pr-4">{purchase.contact_date ? new Date(purchase.contact_date).toLocaleDateString('ru-RU') : '—'}</td>
      <td className="py-3 pr-4">{purchase.store_name || '—'}</td>
      <td className="py-3 pr-4">{purchase.seller_name || '—'}</td>
      <td className="py-3 pr-4 text-right">{purchase.purchase_count}</td>
      <td className="py-3 pr-4 text-right font-semibold">{formatMoney(purchase.revenue_kopecks)}</td>
      <td className="max-w-sm py-3 text-xs text-[#6f6257]">{purchase.purchase_ids.length ? purchase.purchase_ids.join(', ') : '—'}</td>
    </tr>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded-2xl bg-[#fbf6ef] p-3"><p className="text-xs uppercase tracking-wide text-[#9b7f63]">{label}</p><p className="mt-1 font-semibold">{value}</p></div>;
}

function Kpi({ label, value, danger, active, onClick }: { label: string; value: string | number; danger?: boolean; active?: boolean; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-3xl p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-[#8a6a4b] ${
        danger ? 'bg-red-50 text-red-800' : 'bg-white'
      } ${active ? 'ring-2 ring-[#8a6a4b]' : ''}`}
    >
      <p className="text-xs uppercase tracking-wide opacity-70">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </button>
  );
}

function FilterSelect({ label, value, options, onChange, emptyLabel = 'Все' }: { label: string; value: string; options: Array<{ value: string; label: string }>; onChange: (value: string) => void; emptyLabel?: string }) {
  return (
    <label className="text-sm font-medium">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 block w-full rounded-2xl border border-[#d8c8b8] bg-white px-3 py-2">
        <option value="">{emptyLabel}</option>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

function FilterDate({ label, value, onChange, inline = false }: { label: string; value: string; onChange: (value: string) => void; inline?: boolean }) {
  if (inline) {
    return (
      <label className="inline-flex items-center gap-2 text-sm font-medium">
        <span>{label}</span>
        <input type="date" value={value} onChange={(event) => onChange(event.target.value)} className="rounded-2xl border border-[#d8c8b8] px-3 py-2" />
      </label>
    );
  }
  return <label className="text-sm font-medium">{label}<input type="date" value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 block w-full rounded-2xl border border-[#d8c8b8] px-3 py-2" /></label>;
}
