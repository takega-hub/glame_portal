'use client';

import { useState, useEffect, useCallback, useRef, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { apiClient, adminCustomers } from '@/lib/api';
import Link from 'next/link';

interface Customer {
  id: string;
  phone: string | null;
  email: string | null;
  full_name: string | null;
  city: string | null;
  birth_date: string | null;
  gender: string | null;
  customer_segment: string | null;
  loyalty_points: number;
  total_purchases: number;
  total_spent: number;
  last_purchase_date: string | null;
}

interface BirthdayCrmCard {
  customer_id: string;
  full_name: string | null;
  phone: string | null;
  birth_date: string | null;
  next_birthday: string | null;
  days_until_birthday: number | null;
  crm_segment: string;
  real_receipts_count: number;
  real_total_spent: number;
  average_receipt: number;
  high_quality_checks: number;
  excluded_accessory_amount: number;
  recommended_bonus: { title: string; description: string; requires_approval: boolean };
  draft_message: string;
  auto_send: boolean;
  status: string;
}

function AdminCustomersContent() {
  const { loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [search, setSearch] = useState('');
  const [segmentIdFilter, setSegmentIdFilter] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCustomers, setTotalCustomers] = useState(0);
  const [pageSize] = useState(50); // Количество записей на странице
  const [stats, setStats] = useState<any>(null);
  const [segments, setSegments] = useState<Array<{id: string, name: string}>>([]);
  const segmentsLoadedRef = useRef(false); // Флаг для предотвращения повторной загрузки
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [syncProgress, setSyncProgress] = useState(0);
  const [syncStep, setSyncStep] = useState<string>('');
  const [syncLogs, setSyncLogs] = useState<Array<{timestamp: string, message: string}>>([]);
  const [syncTaskId, setSyncTaskId] = useState<string | null>(null);
  const [showSyncModal, setShowSyncModal] = useState(false);
  const [backgroundSyncActive, setBackgroundSyncActive] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [birthdayCards, setBirthdayCards] = useState<BirthdayCrmCard[]>([]);
  const [birthdayLoading, setBirthdayLoading] = useState(false);

  // Определяем loadCustomers до использования в useEffect
  const loadCustomers = useCallback(async () => {
    try {
      setLoadingData(true);
      setErrorMsg(null);
      const offset = (currentPage - 1) * pageSize;
      const params: any = { 
        limit: pageSize,
        offset: offset
      };
      if (segmentIdFilter) params.segment_id = segmentIdFilter;
      if (search && search.trim()) params.search = search.trim();
      
      const response = await apiClient.get<{customers: Customer[], total: number, limit: number, offset: number}>('/api/admin/customers', { params });
      setCustomers(response.data.customers);
      setTotalCustomers(response.data.total);
    } catch (error) {
      console.error('Error loading customers:', error);
      setErrorMsg('Ошибка загрузки покупателей. Попробуйте позже.');
    } finally {
      setLoadingData(false);
    }
  }, [currentPage, pageSize, segmentIdFilter, search]);

  const loadStats = useCallback(async () => {
    try {
      const response = await apiClient.get('/api/admin/customers/analytics/overview');
      setStats(response.data);
    } catch (error) {
      console.error('Error loading stats:', error);
    }
  }, []);

  const loadBirthdayCrm = useCallback(async () => {
    try {
      setBirthdayLoading(true);
      const response = await apiClient.get<{cards: BirthdayCrmCard[]}>('/api/admin/customers/birthday-crm', {
        params: { days_ahead: 3, limit: 100 },
      });
      setBirthdayCards(response.data.cards || []);
    } catch (error) {
      console.error('Error loading birthday CRM:', error);
    } finally {
      setBirthdayLoading(false);
    }
  }, []);

  const loadSegments = useCallback(async () => {
    // Предотвращаем повторную загрузку, если уже загружены
    if (segmentsLoadedRef.current) {
      return;
    }
    
    try {
      const response = await apiClient.get<Array<{id: string, name: string, description?: string, customer_count?: number}>>('/api/admin/customers/segments/list');
      setSegments(response.data);
      segmentsLoadedRef.current = true;
    } catch (error) {
      console.error('Error loading segments:', error);
    }
  }, []);

  // Читаем параметр segment_id из URL при загрузке страницы
  useEffect(() => {
    const segmentIdFromUrl = searchParams?.get('segment_id');
    const segmentNameFromUrl = searchParams?.get('segment'); // legacy support
    
    if (segmentIdFromUrl) {
      setSegmentIdFilter(segmentIdFromUrl);
    } else if (segmentNameFromUrl && segments.length > 0) {
      // Try to find ID by name if segments are loaded
      const found = segments.find(s => s.name === segmentNameFromUrl);
      if (found) setSegmentIdFilter(found.id);
    }
  }, [searchParams, segments]);

  useEffect(() => {
    if (loading) return;
    loadStats();
    loadBirthdayCrm();
    if (!segmentsLoadedRef.current) {
      loadSegments();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  // Debounce для поиска и фильтра сегмента
  useEffect(() => {
    if (loading) return;
    setCurrentPage(1);
  }, [search, segmentIdFilter, loading]);

  // Загружаем данные при изменении страницы, фильтров или поиска
  useEffect(() => {
    if (loading) return;
    const timer = setTimeout(() => {
      loadCustomers();
    }, search || segmentIdFilter ? 500 : 0);
    return () => clearTimeout(timer);
  }, [currentPage, search, segmentIdFilter, loadCustomers, loading]);

  const pollTaskStatus = async (taskId: string) => {
    const maxAttempts = 3600; // Максимум 1 час (каждые 2 секунды)
    let attempts = 0;
    
    const poll = async () => {
      try {
        const response = await apiClient.get(`/api/admin/1c/sync/task/${taskId}`);
        const task = response.data;
        
        setSyncProgress(task.progress || 0);
        setSyncStep(task.current_step || '');
        setSyncLogs(task.logs || []);
        
        if (task.status === 'completed') {
          setSyncing(false);
          setBackgroundSyncActive(false);
          setSyncStatus('Синхронизация завершена успешно!');
          setSyncProgress(100);
          
          // Обновляем данные после синхронизации
          setTimeout(() => {
            loadCustomers();
            loadStats();
            setSyncStatus(null);
            setShowSyncModal(false);
            setSyncTaskId(null);
          }, 2000);
          return;
        }
        
        if (task.status === 'failed') {
          setSyncing(false);
          setBackgroundSyncActive(false);
          setSyncStatus(`Ошибка: ${task.error || 'Неизвестная ошибка'}`);
          return;
        }
        
        // Если модальное окно закрыто, но синхронизация идет - помечаем как фоновую
        if (!showSyncModal && task.status === 'running') {
          setBackgroundSyncActive(true);
        }
        
        // Продолжаем опрос
        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 2000); // Опрашиваем каждые 2 секунды
        } else {
          setSyncing(false);
          setBackgroundSyncActive(false);
          setSyncStatus('Синхронизация занимает слишком много времени. Проверьте статус позже.');
        }
      } catch (error: any) {
        console.error('Error polling task status:', error);
        setSyncing(false);
        setBackgroundSyncActive(false);
        setSyncStatus(`Ошибка при проверке статуса: ${error.message}`);
      }
    };
    
    poll();
  };

  const handleSync = async () => {
    if (syncing) return;
    
    setSyncing(true);
    setBackgroundSyncActive(true);
    setSyncStatus('Запуск синхронизации...');
    setSyncProgress(0);
    setSyncStep('Инициализация...');
    setSyncLogs([]);
    setShowSyncModal(true);
    
    try {
      const response = await apiClient.post('/api/admin/1c/sync/full', null, {
        params: {
          limit: 1000,
          days: 365
        }
      });
      
      const taskId = response.data.task_id;
      setSyncTaskId(taskId);
      setSyncStatus('Синхронизация запущена в фоне...');
      
      // Начинаем опрос статуса
      pollTaskStatus(taskId);
      
    } catch (error: any) {
      console.error('Error syncing:', error);
      setSyncing(false);
      setBackgroundSyncActive(false);
      setSyncStatus(`Ошибка: ${error.response?.data?.detail || error.message || 'Неизвестная ошибка'}`);
      setShowSyncModal(false);
    }
  };
  
  const openSyncModal = () => {
    if (syncTaskId) {
      setShowSyncModal(true);
      // Возобновляем опрос, если он еще не идет
      if (!syncing && backgroundSyncActive) {
        setSyncing(true);
        pollTaskStatus(syncTaskId);
      }
    }
  };

  const handleUpdateSegments = async () => {
    if (syncing) return;
    
    setSyncing(true);
    setBackgroundSyncActive(true);
    setSyncStatus('Запуск обновления сегментов...');
    setSyncProgress(0);
    setSyncStep('Инициализация...');
    setSyncLogs([]);
    setShowSyncModal(true);
    
    try {
      const response = await apiClient.post('/api/admin/1c/update-segments');
      
      const taskId = response.data.task_id;
      setSyncTaskId(taskId);
      setSyncStatus('Обновление сегментов запущено...');
      
      // Начинаем опрос статуса
      pollTaskStatus(taskId);
      
    } catch (error: any) {
      console.error('Error updating segments:', error);
      setSyncing(false);
      setBackgroundSyncActive(false);
      setSyncStatus(`Ошибка: ${error.response?.data?.detail || error.message || 'Неизвестная ошибка'}`);
      setShowSyncModal(false);
    }
  };
  
  const handleExportXlsx = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const query = new URLSearchParams();
      if (segmentIdFilter) query.set('segment_id', segmentIdFilter);
      if (search && search.trim()) query.set('search', search.trim());
      const qs = query.toString();
      const url = `/api/admin/customers/export${qs ? `?${qs}` : ''}`;
      window.open(url, '_blank');
    } catch (e) {
      console.error('Export XLSX error:', e);
      setErrorMsg('Не удалось выгрузить XLSX. Попробуйте позже.');
    } finally {
      setExporting(false);
    }
  };

  if (loading || loadingData) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Загрузка...</p>
        </div>
      </div>
    );
  }

 

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <Link href="/" className="text-pink-600 hover:text-pink-700 mb-4 inline-block">
            ← Назад
          </Link>
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold text-gray-900">Управление покупателями</h1>
            <div className="flex gap-3">
              <button
                onClick={handleExportXlsx}
                disabled={exporting || syncing}
                className={`px-4 py-2 rounded-md font-medium ${
                  exporting || syncing
                    ? 'bg-gray-400 text-white cursor-not-allowed'
                    : 'bg-indigo-600 text-white hover:bg-indigo-700'
                }`}
                title="Выгрузить список покупателей в XLSX (без истории покупок)"
              >
                {exporting ? 'Выгрузка...' : '📤 Выгрузить xlsx'}
              </button>
              <button
                onClick={handleUpdateSegments}
                disabled={syncing}
                className={`px-4 py-2 rounded-md font-medium ${
                  syncing
                    ? 'bg-gray-400 text-white cursor-not-allowed'
                    : 'bg-blue-600 text-white hover:bg-blue-700'
                }`}
                title="Обновить сегменты для всех покупателей"
              >
                {syncing ? 'Обновление...' : '🏷️ Обновить сегменты'}
              </button>
              <button
                onClick={handleSync}
                disabled={syncing}
                className={`px-4 py-2 rounded-md font-medium ${
                  syncing
                    ? 'bg-gray-400 text-white cursor-not-allowed'
                    : 'bg-pink-600 text-white hover:bg-pink-700'
                }`}
              >
                {syncing ? 'Синхронизация...' : '🔄 Синхронизация с 1С'}
              </button>
            </div>
          </div>
          {syncStatus && (
            <div className={`mt-2 p-3 rounded-md ${
              syncStatus.includes('Ошибка')
                ? 'bg-red-50 text-red-700 border border-red-200'
                : 'bg-green-50 text-green-700 border border-green-200'
            }`}>
              {syncStatus}
            </div>
          )}
          
          {/* Индикатор фоновой синхронизации */}
          {backgroundSyncActive && !showSyncModal && (
            <div className="mt-2 p-3 rounded-md bg-blue-50 text-blue-700 border border-blue-200 flex items-center justify-between">
              <div className="flex items-center">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                <span>Синхронизация выполняется в фоне ({syncProgress}%)</span>
              </div>
              <button
                onClick={openSyncModal}
                className="ml-4 px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Показать прогресс
              </button>
            </div>
          )}
        </div>

        {/* Статистика */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div className="bg-white rounded-lg shadow p-6">
              <p className="text-sm text-gray-500">Всего покупателей</p>
              <p className="text-3xl font-bold text-gray-900 mt-2">{stats.total_customers || 0}</p>
            </div>
            <div className="bg-white rounded-lg shadow p-6">
              <p className="text-sm text-gray-500">Общий доход</p>
              <p className="text-3xl font-bold text-gray-900 mt-2">
                {stats.total_revenue ? stats.total_revenue.toLocaleString('ru-RU') : 0} ₽
              </p>
            </div>
            <div className="bg-white rounded-lg shadow p-6">
              <p className="text-sm text-gray-500">Средний LTV</p>
              <p className="text-3xl font-bold text-gray-900 mt-2">
                {stats.ltv_metrics?.average_ltv ? stats.ltv_metrics.average_ltv.toLocaleString('ru-RU') : 0} ₽
              </p>
            </div>
            <div className="bg-white rounded-lg shadow p-6">
              <p className="text-sm text-gray-500">Активных сегментов</p>
              <p className="text-3xl font-bold text-gray-900 mt-2">
                {stats.segments_stats?.total_segments || 0}
              </p>
            </div>
          </div>
        )}

        {/* Birthday CRM */}
        <div className="bg-white rounded-lg shadow p-6 mb-8 border border-pink-100">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h2 className="text-xl font-semibold text-gray-900">Birthday CRM: ближайшие 3 дня</h2>
              <p className="text-sm text-gray-500 mt-1">
                Карточки формируются по реальным чекам: сопутствующие материалы исключены, чеки клиента в течение 1 часа объединяются. Отправка клиентам не выполняется — это черновики для менеджера.
              </p>
            </div>
            <button
              onClick={loadBirthdayCrm}
              disabled={birthdayLoading}
              className="px-3 py-2 text-sm rounded-md border border-pink-200 text-pink-700 hover:bg-pink-50 disabled:opacity-50"
            >
              {birthdayLoading ? 'Обновление...' : 'Обновить'}
            </button>
          </div>
          {birthdayCards.length === 0 ? (
            <div className="text-sm text-gray-500 bg-gray-50 rounded-md px-4 py-3">
              {birthdayLoading ? 'Загружаем карточки...' : 'Нет клиентов с днем рождения в ближайшие 3 дня.'}
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {birthdayCards.map((card) => (
                <div key={card.customer_id} className="rounded-lg border border-pink-100 bg-pink-50/40 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <Link href={`/admin/customers/${card.customer_id}`} className="font-semibold text-gray-900 hover:text-pink-700">
                        {card.full_name || card.phone || 'Клиент'}
                      </Link>
                      <div className="text-xs text-gray-500 mt-1">
                        ДР: {card.next_birthday ? new Date(card.next_birthday).toLocaleDateString('ru-RU') : '—'} · через {card.days_until_birthday} дн.
                      </div>
                    </div>
                    <span className="px-2 py-1 rounded-full text-xs font-semibold bg-white text-pink-700 border border-pink-200">
                      {card.crm_segment}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 mt-4 text-xs">
                    <div className="bg-white rounded p-2">
                      <div className="text-gray-500">Реальные чеки</div>
                      <div className="font-semibold text-gray-900">{card.real_receipts_count}</div>
                    </div>
                    <div className="bg-white rounded p-2">
                      <div className="text-gray-500">Сумма</div>
                      <div className="font-semibold text-gray-900">{(card.real_total_spent / 100).toLocaleString('ru-RU')} ₽</div>
                    </div>
                    <div className="bg-white rounded p-2">
                      <div className="text-gray-500">Средний чек</div>
                      <div className="font-semibold text-gray-900">{(card.average_receipt / 100).toLocaleString('ru-RU')} ₽</div>
                    </div>
                  </div>
                  <div className="mt-3 text-sm">
                    <div className="font-medium text-gray-900">{card.recommended_bonus.title}</div>
                    <div className="text-gray-600">{card.recommended_bonus.description}</div>
                  </div>
                  <div className="mt-3 rounded-md bg-white p-3 text-sm text-gray-700 whitespace-pre-wrap">
                    {card.draft_message}
                  </div>
                  <div className="mt-3 text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded px-2 py-1">
                    Статус: черновик, автоотправка выключена. Бонус требует ручного подтверждения.
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Фильтры */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Поиск
              </label>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Имя, телефон, email..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Сегмент
              </label>
              <select
                value={segmentIdFilter}
                onChange={(e) => setSegmentIdFilter(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
              >
                <option value="">Все сегменты</option>
                {segments.map((segment) => (
                  <option key={segment.id} value={segment.id}>
                    {segment.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <Link
                href="/admin/customers/segments"
                className="w-full px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 text-center"
              >
                Управление сегментами
              </Link>
            </div>
          </div>
        </div>

        {/* Таблица покупателей */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          {errorMsg && (
            <div className="px-6 py-3 bg-red-50 text-red-700 border-b border-red-200">
              {errorMsg}
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Имя / Телефон
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Город
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Дата рождения
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Пол
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Сегмент
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Баллы
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Покупок
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Потрачено
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Последняя покупка
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    Действия
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {loadingData && customers.length === 0 && (
                  <tr>
                    <td colSpan={10} className="px-6 py-8 text-center">
                      <div className="inline-flex items-center gap-2 text-gray-500">
                        <span className="animate-spin rounded-full h-5 w-5 border-b-2 border-pink-600"></span>
                        Загрузка списка покупателей...
                      </div>
                    </td>
                  </tr>
                )}
                {customers.map((customer) => (
                  <tr key={customer.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div>
                        <div className="text-sm font-medium text-gray-900">
                          {customer.full_name || 'Без имени'}
                        </div>
                        <div className="text-sm text-gray-500">
                          {customer.phone || customer.email || '—'}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-900">
                        {customer.city || '—'}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-900">
                        {customer.birth_date
                          ? customer.birth_date.split('-').reverse().join('.')
                          : '—'}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-900">
                        {customer.gender === 'male' ? 'Мужской' : 
                         customer.gender === 'female' ? 'Женский' : '—'}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
                        customer.customer_segment === 'VIP' ? 'bg-yellow-100 text-yellow-800' :
                        customer.customer_segment === 'Active' ? 'bg-green-100 text-green-800' :
                        customer.customer_segment === 'Sleeping' ? 'bg-gray-100 text-gray-800' :
                        'bg-blue-100 text-blue-800'
                      }`}>
                        {customer.customer_segment || '—'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {customer.loyalty_points}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {customer.total_purchases}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {customer.total_spent.toLocaleString('ru-RU')} ₽
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {customer.last_purchase_date
                        ? new Date(customer.last_purchase_date).toLocaleDateString('ru-RU')
                        : '—'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <Link
                        href={`/admin/customers/${customer.id}`}
                        className="text-pink-600 hover:text-pink-900"
                      >
                        Детали
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Пагинация */}
        {totalCustomers > 0 && (
          <div className="bg-white rounded-lg shadow px-4 py-3 mt-6 flex items-center justify-between border-t border-gray-200">
            <div className="flex-1 flex justify-between sm:hidden">
              <button
                onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                disabled={currentPage === 1}
                className="relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Предыдущая
              </button>
              <button
                onClick={() => setCurrentPage(prev => prev + 1)}
                disabled={currentPage * pageSize >= totalCustomers}
                className="ml-3 relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Следующая
              </button>
            </div>
            <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
              <div>
                <p className="text-sm text-gray-700">
                  Показано <span className="font-medium">{(currentPage - 1) * pageSize + 1}</span> -{' '}
                  <span className="font-medium">{Math.min(currentPage * pageSize, totalCustomers)}</span> из{' '}
                  <span className="font-medium">{totalCustomers}</span> покупателей
                </p>
              </div>
              <div>
                <nav className="relative z-0 inline-flex rounded-md shadow-sm -space-x-px" aria-label="Пагинация">
                  <button
                    onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                    disabled={currentPage === 1}
                    className="relative inline-flex items-center px-2 py-2 rounded-l-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span className="sr-only">Предыдущая</span>
                    ←
                  </button>
                  {Array.from({ length: Math.min(5, Math.ceil(totalCustomers / pageSize)) }, (_, i) => {
                    const totalPages = Math.ceil(totalCustomers / pageSize);
                    let pageNum;
                    if (totalPages <= 5) {
                      pageNum = i + 1;
                    } else if (currentPage <= 3) {
                      pageNum = i + 1;
                    } else if (currentPage >= totalPages - 2) {
                      pageNum = totalPages - 4 + i;
                    } else {
                      pageNum = currentPage - 2 + i;
                    }
                    
                    if (pageNum > totalPages) return null;
                    
                    return (
                      <button
                        key={pageNum}
                        onClick={() => setCurrentPage(pageNum)}
                        className={`relative inline-flex items-center px-4 py-2 border text-sm font-medium ${
                          currentPage === pageNum
                            ? 'z-10 bg-pink-50 border-pink-500 text-pink-600'
                            : 'bg-white border-gray-300 text-gray-500 hover:bg-gray-50'
                        }`}
                      >
                        {pageNum}
                      </button>
                    );
                  })}
                  <button
                    onClick={() => setCurrentPage(prev => prev + 1)}
                    disabled={currentPage * pageSize >= totalCustomers}
                    className="relative inline-flex items-center px-2 py-2 rounded-r-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span className="sr-only">Следующая</span>
                    →
                  </button>
                </nav>
              </div>
            </div>
          </div>
        )}

        {customers.length === 0 && !loadingData && (
          <div className="bg-white rounded-lg shadow p-12 text-center mt-6">
            <p className="text-gray-500">Покупатели не найдены</p>
          </div>
        )}
      </div>

      {/* Модальное окно синхронизации */}
      {showSyncModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-gray-900">Синхронизация данных</h2>
                {syncing && (
                  <p className="text-sm text-gray-500 mt-1">
                    Вы можете закрыть это окно - синхронизация продолжится в фоне
                  </p>
                )}
              </div>
              <button
                onClick={() => {
                  setShowSyncModal(false);
                  // Не сбрасываем taskId и статус - синхронизация продолжается в фоне
                }}
                className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
                title="Закрыть (синхронизация продолжится в фоне)"
              >
                ✕
              </button>
            </div>
            
            <div className="px-6 py-4 flex-1 overflow-y-auto">
              {/* Прогресс-бар */}
              <div className="mb-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-700">{syncStep || 'Инициализация...'}</span>
                  <span className="text-sm text-gray-500">{syncProgress}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2.5">
                  <div
                    className="bg-pink-600 h-2.5 rounded-full transition-all duration-300"
                    style={{ width: `${syncProgress}%` }}
                  ></div>
                </div>
              </div>

              {/* Логи */}
              {syncLogs.length > 0 && (
                <div className="mt-4">
                  <h3 className="text-sm font-medium text-gray-700 mb-2">Логи синхронизации:</h3>
                  <div className="bg-gray-50 rounded-md p-3 max-h-64 overflow-y-auto">
                    <div className="space-y-1">
                      {syncLogs.map((log, index) => {
                        // Поддержка разных форматов логов
                        const logEntry = typeof log === 'string' 
                          ? { timestamp: new Date().toISOString(), message: log }
                          : log;
                        const timestamp = logEntry.timestamp 
                          ? new Date(logEntry.timestamp).toLocaleTimeString('ru-RU')
                          : '';
                        const message = logEntry.message ?? (typeof logEntry === 'string' ? logEntry : '');
                        const messageStr = typeof message === 'string' ? message : (message && typeof message === 'object' && 'message' in message ? (message as { message: string }).message : String(message));
                        return (
                          <div key={index} className="text-xs text-gray-600 font-mono">
                            {timestamp && <span className="text-gray-400">{timestamp} </span>}
                            {messageStr}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* Статус */}
              {syncStatus && (
                <div className={`mt-4 p-3 rounded-md ${
                  syncStatus.includes('Ошибка')
                    ? 'bg-red-50 text-red-700 border border-red-200'
                    : syncStatus.includes('завершена')
                    ? 'bg-green-50 text-green-700 border border-green-200'
                    : 'bg-blue-50 text-blue-700 border border-blue-200'
                }`}>
                  {syncStatus}
                </div>
              )}
            </div>

            <div className="px-6 py-4 border-t border-gray-200 flex justify-end">
              {syncing ? (
                <button
                  onClick={() => {
                    setShowSyncModal(false);
                    // Синхронизация продолжается в фоне
                  }}
                  className="px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300"
                >
                  Свернуть (синхронизация продолжится)
                </button>
              ) : (
                <button
                  onClick={() => {
                    setShowSyncModal(false);
                    setSyncTaskId(null);
                    setSyncStatus(null);
                    loadCustomers();
                    loadStats();
                  }}
                  className="px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700"
                >
                  Закрыть
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AdminCustomersPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-gray-500">Загрузка...</div>}>
      <AdminCustomersContent />
    </Suspense>
  );
}
