'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams, useSearchParams } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { apiClient } from '@/lib/api';
import Link from 'next/link';
import { communication, type CustomerMessageItem } from '@/lib/api';
import { RefreshCw } from 'lucide-react';

interface CustomerDetail {
  id: string;
  phone: string | null;
  email: string | null;
  full_name: string | null;
  city: string | null;
  birth_date: string | null;
  gender: string | null;
  discount_card_number: string | null;
  customer_segment: string | null;
  loyalty_points: number;
  total_purchases: number;
  total_spent: number;
  average_check: number | null;
  last_purchase_date: string | null;
  rfm_score: any;
  purchase_preferences: any;
  segments: Array<{ id: string; name: string }>;
  created_at: string;
  preferred_store_name?: string | null;
  preferred_store_share?: number | null;
  store_distribution?: Array<{ store_name: string; count: number; share_pct: number }>;
}

interface PurchaseHistoryItem {
  id: string;
  purchase_date: string;
  product_name: string | null;
  product_article: string | null;
  quantity: number;
  price: number;
  total_amount: number;
  category: string | null;
  brand: string | null;
  document_id_1c: string | null;
  store_id_1c: string | null;
  store_name: string | null;
}

interface PurchaseHistoryResponse {
  items: PurchaseHistoryItem[];
  total_count: number;
  total_amount: number;
}

interface ForceSyncResponse {
  success: boolean;
  message: string;
  stats?: {
    fetched?: number;
    created?: number;
    updated?: number;
    skipped?: number;
    linked_products?: Record<string, number>;
    loyalty_balance?: number;
    loyalty_updated?: boolean;
  };
}

interface StylistDialogMessageItem {
  id: string;
  role: string;
  sender_name?: string | null;
  text?: string | null;
  attachments?: Array<Record<string, any>>;
  created_at?: string | null;
}

interface StylistDialogItem {
  id: string;
  topic: string;
  source?: string | null;
  scenario?: string | null;
  status: string;
  status_label: string;
  assigned_stylist_name?: string | null;
  created_at?: string | null;
  last_message_at?: string | null;
  messages: StylistDialogMessageItem[];
}

interface StylistDialogsResponse {
  items: StylistDialogItem[];
  total: number;
}

interface LoyaltyInfo {
  balance: number;
  transactions: Array<{
    id: string;
    type: string;
    points: number;
    balance_after: number;
    reason?: string | null;
    description?: string | null;
    source?: string | null;
    expires_at?: string | null;
    created_at: string;
  }>;
  program_info: {
    name: string;
    description: string;
    levels: Array<{
      name: string;
      bonus_percent: number;
      min_total: number;
      max_total?: number | null;
      condition: string;
      benefits: string[];
    }>;
  };
  level_progress: {
    current_total: number;
    current_level: { name: string; bonus_percent: number; min_total: number; max_total?: number | null };
    next_level?: { name: string; bonus_percent: number; min_total: number; max_total?: number | null } | null;
    remaining_total: number;
    progress: number;
  };
  summary: {
    total_spent: number;
    total_purchases: number;
    average_check: number;
    discount_card_number?: string | null;
    earned_points_loaded: number;
    spent_points_loaded: number;
    expiring_points_loaded: number;
  };
}

interface SavedItemsInfo {
  saved_looks: Array<{
    id: string;
    look_id: string;
    look_name: string;
    save_type: string;
    notes?: string | null;
    is_purchased: boolean;
    look_style?: string | null;
    look_mood?: string | null;
    look_description?: string | null;
    look_image_url?: string | null;
    look_image_urls: string[];
    product_ids: string[];
    created_at?: string | null;
  }>;
  favorite_products: Array<{
    id: string;
    name?: string | null;
    brand?: string | null;
    category?: string | null;
    article?: string | null;
    external_code?: string | null;
    price?: number | null;
    image_url?: string | null;
    source: string;
  }>;
  source_notes: string[];
}

function formatRub(value?: number | null) {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

export default function CustomerDetailPage() {
  const { loading } = useAuth();
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const customerId = params.id as string;
  const [customer, setCustomer] = useState<CustomerDetail | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [forceSyncing, setForceSyncing] = useState(false);
  const [forceSyncMessage, setForceSyncMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'purchases' | 'loyalty' | 'looks' | 'messages'>('overview');
  const [isEditingGender, setIsEditingGender] = useState(false);
  const [editGender, setEditGender] = useState<string | null>(null);
  const [savingGender, setSavingGender] = useState(false);
  
  // История покупок
  const [purchaseHistory, setPurchaseHistory] = useState<PurchaseHistoryResponse | null>(null);
  const [loadingPurchases, setLoadingPurchases] = useState(false);
  const [loyaltyInfo, setLoyaltyInfo] = useState<LoyaltyInfo | null>(null);
  const [loadingLoyalty, setLoadingLoyalty] = useState(false);
  const [savedItems, setSavedItems] = useState<SavedItemsInfo | null>(null);
  const [loadingSavedItems, setLoadingSavedItems] = useState(false);

  // История сообщений
  const [messages, setMessages] = useState<CustomerMessageItem[]>([]);
  const [messagesTotal, setMessagesTotal] = useState(0);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messagesOffset, setMessagesOffset] = useState(0);
  const [messagesActionId, setMessagesActionId] = useState<string | null>(null);
  const [stylistDialogs, setStylistDialogs] = useState<StylistDialogItem[]>([]);
  const [stylistDialogsTotal, setStylistDialogsTotal] = useState(0);
  const [stylistDialogsLoading, setStylistDialogsLoading] = useState(false);
  const MESSAGES_LIMIT = 50;

  useEffect(() => {
    const requestedTab = searchParams.get('tab');
    if (requestedTab === 'overview' || requestedTab === 'purchases' || requestedTab === 'loyalty' || requestedTab === 'looks' || requestedTab === 'messages') {
      setActiveTab(requestedTab);
    }
  }, [searchParams]);

  useEffect(() => {
    if (!loading) {
      loadCustomer();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, router, customerId]);

  // Загружаем историю покупок при переключении на вкладку
  useEffect(() => {
    if (activeTab === 'purchases' && !purchaseHistory && !loadingPurchases) {
      loadPurchaseHistory();
    }
    if (activeTab === 'loyalty' && !loyaltyInfo && !loadingLoyalty) {
      loadLoyaltyInfo();
    }
    if (activeTab === 'looks' && !savedItems && !loadingSavedItems) {
      loadSavedItems();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // Загружаем историю сообщений при переключении на вкладку
  useEffect(() => {
    if (activeTab === 'messages' && customer && !messagesLoading) {
      loadMessages(true);
      loadStylistDialogs();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, customer?.id]);

  const loadCustomer = async (sync: boolean = true) => {
    try {
      setSyncing(sync);
      const response = await apiClient.get<CustomerDetail>(
        `/api/admin/customers/${customerId}?sync=${sync}`
      );
      setCustomer(response.data);
      setEditGender(response.data.gender);
    } catch (error) {
      console.error('Error loading customer:', error);
    } finally {
      setLoadingData(false);
      setSyncing(false);
    }
  };

  const loadMessages = async (initial: boolean = false) => {
    if (!customer) return;
    setMessagesLoading(true);
    try {
      const offset = initial ? 0 : messagesOffset;
      const data = await communication.getCustomerMessages(
        customer.id,
        MESSAGES_LIMIT,
        offset,
        { kind: 'all', sort_by: 'created_at', desc: true }
      );
      setMessagesTotal(data.total || 0);
      if (initial) {
        setMessages(data.items || []);
        setMessagesOffset((data.items || []).length);
      } else {
        setMessages(prev => [...prev, ...(data.items || [])]);
        setMessagesOffset(prev => prev + (data.items?.length || 0));
      }
    } finally {
      setMessagesLoading(false);
    }
  };

  const loadMoreMessages = async () => {
    if (messagesLoading) return;
    if (messages.length >= messagesTotal) return;
    await loadMessages(false);
  };

  const loadStylistDialogs = async () => {
    if (!customer) return;
    setStylistDialogsLoading(true);
    try {
      const response = await apiClient.get<StylistDialogsResponse>(
        `/api/admin/customers/${customer.id}/stylist-dialogs`
      );
      setStylistDialogs(response.data.items || []);
      setStylistDialogsTotal(response.data.total || 0);
    } finally {
      setStylistDialogsLoading(false);
    }
  };

  const handleDeleteMessage = async (msg: CustomerMessageItem) => {
    setMessagesActionId(msg.id);
    try {
      await communication.deleteCustomerMessage(msg.id);
      setMessagesOffset(0);
      await loadMessages(true);
    } finally {
      setMessagesActionId(null);
    }
  };

  const handleMarkSentMessage = async (msg: CustomerMessageItem) => {
    setMessagesActionId(msg.id);
    try {
      await communication.markMessageSent(msg.id);
      setMessagesOffset(0);
      await loadMessages(true);
    } finally {
      setMessagesActionId(null);
    }
  };

  const handleSaveGender = async () => {
    if (!customer) return;
    
    setSavingGender(true);
    try {
      const response = await apiClient.put(`/api/admin/customers/${customerId}`, {
        gender: editGender || null
      });
      
      console.log('Save gender response:', response.data);
      
      // Обновляем данные клиента
      await loadCustomer(false);
      
      // Обновляем editGender на основе сохраненного значения из ответа
      const savedGender = response.data?.gender ?? editGender ?? null;
      setEditGender(savedGender);
      
      // Обновляем customer напрямую
      if (customer) {
        setCustomer({
          ...customer,
          gender: savedGender
        });
      }
      
      setIsEditingGender(false);
    } catch (error) {
      console.error('Error saving gender:', error);
      alert('Ошибка при сохранении пола');
    } finally {
      setSavingGender(false);
    }
  };

  const loadPurchaseHistory = async () => {
    setLoadingPurchases(true);
    try {
      const response = await apiClient.get<PurchaseHistoryResponse>(
        `/api/admin/customers/${customerId}/purchases?limit=100`
      );
      setPurchaseHistory(response.data);
    } catch (error) {
      console.error('Error loading purchase history:', error);
    } finally {
      setLoadingPurchases(false);
    }
  };

  const loadLoyaltyInfo = async () => {
    setLoadingLoyalty(true);
    try {
      const response = await apiClient.get<LoyaltyInfo>(`/api/admin/customers/${customerId}/loyalty`);
      setLoyaltyInfo(response.data);
    } catch (error) {
      console.error('Error loading loyalty info:', error);
    } finally {
      setLoadingLoyalty(false);
    }
  };

  const loadSavedItems = async () => {
    setLoadingSavedItems(true);
    try {
      const response = await apiClient.get<SavedItemsInfo>(`/api/admin/customers/${customerId}/saved-items`);
      setSavedItems(response.data);
    } catch (error) {
      console.error('Error loading saved items:', error);
    } finally {
      setLoadingSavedItems(false);
    }
  };

  const handleForceSync = async () => {
    if (!customer || forceSyncing) return;

    setForceSyncing(true);
    setForceSyncMessage(null);
    try {
      const response = await apiClient.post<ForceSyncResponse>(
        `/api/admin/customers/${customerId}/force-sync?days=3650&replace_history=true`
      );
      await loadCustomer(false);
      await loadPurchaseHistory();
      if (loyaltyInfo) await loadLoyaltyInfo();
      if (savedItems) await loadSavedItems();

      const stats = response.data.stats || {};
      const linkedTotal = stats.linked_products
        ? Object.values(stats.linked_products).reduce((sum, value) => sum + Number(value || 0), 0)
        : 0;
      setForceSyncMessage(
        `Синхронизация завершена: получено ${stats.fetched ?? 0}, создано ${stats.created ?? 0}, обновлено ${stats.updated ?? 0}, привязано товаров ${linkedTotal}. Баллы: ${stats.loyalty_balance ?? '—'}`
      );
    } catch (error: any) {
      console.error('Force sync error:', error);
      const detail = error.response?.data?.detail || error.message || 'Неизвестная ошибка';
      setForceSyncMessage(`Ошибка синхронизации: ${detail}`);
    } finally {
      setForceSyncing(false);
    }
  };

  if (loading || loadingData) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">
            {syncing ? 'Синхронизация данных из 1С...' : 'Загрузка...'}
          </p>
          {syncing && (
            <p className="mt-2 text-sm text-gray-500">
              Обновление истории покупок, бонусных баллов и метрик
            </p>
          )}
        </div>
      </div>
    );
  }

  if (!customer) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600">Покупатель не найден</p>
          <Link href="/admin/customers" className="text-pink-600 hover:text-pink-700 mt-4 inline-block">
            Вернуться к списку
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <Link href="/admin/customers" className="text-pink-600 hover:text-pink-700 mb-4 inline-block">
            ← Назад к списку покупателей
          </Link>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h1 className="text-3xl font-bold text-gray-900">
              {customer.full_name || customer.phone || 'Покупатель'}
            </h1>
            <button
              type="button"
              onClick={handleForceSync}
              disabled={forceSyncing}
              title="Принудительно обновить покупки, бонусные баллы и связи товаров из 1С"
              className="inline-flex items-center justify-center gap-2 rounded-md bg-pink-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-pink-700 disabled:cursor-not-allowed disabled:bg-gray-300 disabled:text-gray-600"
            >
              <RefreshCw className={`h-4 w-4 ${forceSyncing ? 'animate-spin' : ''}`} />
              {forceSyncing ? 'Синхронизация...' : 'Обновить из 1С'}
            </button>
          </div>
          {forceSyncMessage && (
            <div className={`mt-3 rounded-md border px-4 py-3 text-sm ${
              forceSyncMessage.startsWith('Ошибка')
                ? 'border-red-200 bg-red-50 text-red-700'
                : 'border-green-200 bg-green-50 text-green-700'
            }`}>
              {forceSyncMessage}
            </div>
          )}
        </div>

        {/* Вкладки */}
        <div className="bg-white rounded-lg shadow mb-6">
          <div className="border-b border-gray-200">
            <nav className="flex -mb-px">
              {[
                { id: 'overview', label: 'Обзор' },
                { id: 'purchases', label: 'История покупок' },
                { id: 'loyalty', label: 'Программа лояльности' },
                { id: 'looks', label: 'Сохраненные образы' },
                { id: 'messages', label: 'Сообщения' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`py-4 px-6 text-sm font-medium border-b-2 ${
                    activeTab === tab.id
                      ? 'border-pink-500 text-pink-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>
        </div>

        {/* Контент вкладок */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Профиль */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-bold text-gray-900 mb-4">Профиль</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <p className="text-sm text-gray-500">Имя</p>
                  <p className="text-lg font-medium text-gray-900">{customer.full_name || '—'}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Телефон</p>
                  <p className="text-lg font-medium text-gray-900">{customer.phone || '—'}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Email</p>
                  <p className="text-lg font-medium text-gray-900">{customer.email || '—'}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Город</p>
                  <p className="text-lg font-medium text-gray-900">{customer.city || '—'}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Дата рождения</p>
                  <p className="text-lg font-medium text-gray-900">
                    {customer.birth_date
                      ? customer.birth_date.split('-').reverse().join('.')
                      : '—'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Предпочтительный магазин</p>
                  <p className="text-lg font-medium text-gray-900">
                    {customer.preferred_store_name
                      ? `${customer.preferred_store_name} (${(customer.preferred_store_share ?? 0).toFixed(0)}%)`
                      : '—'}
                  </p>
                  {customer.store_distribution && customer.store_distribution.length > 1 && (
                    <p className="text-xs text-gray-500 mt-1">
                      {customer.store_distribution.map(d => `${d.store_name}: ${d.share_pct.toFixed(0)}%`).join(' · ')}
                    </p>
                  )}
                </div>
                <div>
                  <p className="text-sm text-gray-500">Пол</p>
                  {isEditingGender ? (
                    <div className="flex items-center gap-2">
                      <select
                        value={editGender || ''}
                        onChange={(e) => setEditGender(e.target.value || null)}
                        className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
                      >
                        <option value="">Не указан</option>
                        <option value="male">Мужской</option>
                        <option value="female">Женский</option>
                      </select>
                      <button
                        onClick={handleSaveGender}
                        disabled={savingGender}
                        className="px-3 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 disabled:bg-gray-400 text-sm"
                      >
                        {savingGender ? 'Сохранение...' : 'Сохранить'}
                      </button>
                      <button
                        onClick={() => {
                          setIsEditingGender(false);
                          setEditGender(customer.gender);
                        }}
                        className="px-3 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300 text-sm"
                      >
                        Отмена
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <p className="text-lg font-medium text-gray-900">
                        {customer.gender === 'male' ? 'Мужской' : 
                         customer.gender === 'female' ? 'Женский' : '—'}
                      </p>
                      <button
                        onClick={() => setIsEditingGender(true)}
                        className="text-sm text-pink-600 hover:text-pink-700 underline"
                      >
                        Изменить
                      </button>
                    </div>
                  )}
                </div>
                <div>
                  <p className="text-sm text-gray-500">Дисконтная карта</p>
                  <p className="text-lg font-medium text-gray-900">
                    {customer.discount_card_number || customer.phone || '—'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Дата регистрации</p>
                  <p className="text-lg font-medium text-gray-900">
                    {new Date(customer.created_at).toLocaleDateString('ru-RU')}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Сегмент</p>
                  <span className={`inline-block px-3 py-1 text-sm font-semibold rounded-full ${
                    customer.customer_segment === 'VIP' ? 'bg-yellow-100 text-yellow-800' :
                    customer.customer_segment === 'Active' ? 'bg-green-100 text-green-800' :
                    customer.customer_segment === 'Sleeping' ? 'bg-gray-100 text-gray-800' :
                    'bg-blue-100 text-blue-800'
                  }`}>
                    {customer.customer_segment || '—'}
                  </span>
                </div>
              </div>
            </div>

            {/* Метрики */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-bold text-gray-900 mb-4">Метрики</h2>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <div>
                  <p className="text-sm text-gray-500">Всего покупок</p>
                  <p className="text-3xl font-bold text-gray-900">{customer.total_purchases}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Общая сумма</p>
                  <p className="text-3xl font-bold text-gray-900">
                    {customer.total_spent.toLocaleString('ru-RU')} ₽
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Средний чек</p>
                  <p className="text-3xl font-bold text-gray-900">
                    {customer.average_check ? customer.average_check.toLocaleString('ru-RU') : 0} ₽
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Баллы лояльности</p>
                  <p className="text-3xl font-bold text-gray-900">{customer.loyalty_points}</p>
                </div>
              </div>
            </div>

            {/* RFM Score */}
            {customer.rfm_score && (
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-xl font-bold text-gray-900 mb-4">RFM Анализ</h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div>
                    <p className="text-sm text-gray-500">Recency (R)</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {customer.rfm_score.r_score || 0}/5
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      {customer.rfm_score.recency !== null ? `${customer.rfm_score.recency} дней назад` : '—'}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Frequency (F)</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {customer.rfm_score.f_score || 0}/5
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      {customer.rfm_score.frequency || 0} покупок
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Monetary (M)</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {customer.rfm_score.m_score || 0}/5
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      {customer.rfm_score.monetary ? (customer.rfm_score.monetary / 100).toLocaleString('ru-RU') + ' ₽' : '—'}
                    </p>
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <p className="text-sm text-gray-500">Общий RFM Score</p>
                  <p className="text-3xl font-bold text-pink-600">
                    {customer.rfm_score.total_score || 0}/15
                  </p>
                </div>
              </div>
            )}

            {/* Предпочтения */}
            {customer.purchase_preferences && (
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-xl font-bold text-gray-900 mb-4">Предпочтения</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {customer.purchase_preferences.favorite_categories && (
                    <div>
                      <p className="text-sm text-gray-500 mb-2">Любимые категории</p>
                      <div className="flex flex-wrap gap-2">
                        {customer.purchase_preferences.favorite_categories.map((cat: string, idx: number) => (
                          <span key={idx} className="px-3 py-1 bg-pink-100 text-pink-800 rounded-full text-sm">
                            {cat}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {customer.purchase_preferences.favorite_brands && (
                    <div>
                      <p className="text-sm text-gray-500 mb-2">Любимые бренды</p>
                      <div className="flex flex-wrap gap-2">
                        {customer.purchase_preferences.favorite_brands.map((brand: string, idx: number) => (
                          <span key={idx} className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm">
                            {brand}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'purchases' && (
          <div className="bg-white rounded-lg shadow p-6">
            {loadingPurchases ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-pink-600 mx-auto"></div>
                <p className="mt-4 text-gray-600">Загрузка истории покупок...</p>
              </div>
            ) : purchaseHistory && purchaseHistory.items.length > 0 ? (
              <>
                <div className="mb-4 flex justify-between items-center">
                  <h2 className="text-xl font-bold text-gray-900">История покупок</h2>
                  <div className="text-sm text-gray-500">
                    Всего: <span className="font-semibold">{purchaseHistory.total_count}</span> покупок на сумму{' '}
                    <span className="font-semibold text-pink-600">
                      {purchaseHistory.total_amount.toLocaleString('ru-RU')} ₽
                    </span>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Дата
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Товар
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Артикул
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Категория
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Бренд
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Магазин
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Кол-во
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Сумма
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {purchaseHistory.items.map((purchase) => (
                        <tr key={purchase.id} className="hover:bg-gray-50">
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                            {new Date(purchase.purchase_date).toLocaleDateString('ru-RU', {
                              day: '2-digit',
                              month: '2-digit',
                              year: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit'
                            })}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-900 max-w-xs truncate" title={purchase.product_name || ''}>
                            {purchase.product_name || '—'}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                            {purchase.product_article || '—'}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                            {purchase.category ? (
                              <span className="px-2 py-1 bg-pink-100 text-pink-800 rounded text-xs">
                                {purchase.category}
                              </span>
                            ) : '—'}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                            {purchase.brand ? (
                              <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs">
                                {purchase.brand}
                              </span>
                            ) : '—'}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                            {purchase.store_name || '—'}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900 text-right">
                            {purchase.quantity}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 text-right">
                            {purchase.total_amount.toLocaleString('ru-RU')} ₽
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-500">История покупок пуста</p>
                <p className="text-sm text-gray-400 mt-2">
                  Данные появятся после синхронизации с 1С
                </p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'loyalty' && (
          <div className="space-y-6">
            {loadingLoyalty ? (
              <div className="bg-white rounded-lg shadow p-8 text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-pink-600 mx-auto"></div>
                <p className="mt-4 text-gray-600">Загрузка программы лояльности...</p>
              </div>
            ) : loyaltyInfo ? (
              <>
                <div className="grid gap-4 md:grid-cols-4">
                  <div className="rounded-lg bg-gray-900 p-5 text-white shadow">
                    <div className="text-sm text-gray-300">Баланс</div>
                    <div className="mt-2 text-3xl font-bold">{loyaltyInfo.balance}</div>
                    <div className="mt-1 text-xs text-gray-300">1 балл = 1 ₽ скидки</div>
                  </div>
                  <div className="rounded-lg bg-white p-5 shadow">
                    <div className="text-sm text-gray-500">Текущий уровень</div>
                    <div className="mt-2 text-2xl font-bold text-gray-900">{loyaltyInfo.level_progress.current_level.name}</div>
                    <div className="mt-1 text-sm text-gray-500">{loyaltyInfo.level_progress.current_level.bonus_percent}% начисления</div>
                  </div>
                  <div className="rounded-lg bg-white p-5 shadow">
                    <div className="text-sm text-gray-500">Сумма покупок</div>
                    <div className="mt-2 text-2xl font-bold text-gray-900">{formatRub(loyaltyInfo.summary.total_spent)}</div>
                    <div className="mt-1 text-sm text-gray-500">{loyaltyInfo.summary.total_purchases} покупок</div>
                  </div>
                  <div className="rounded-lg bg-white p-5 shadow">
                    <div className="text-sm text-gray-500">Средний чек</div>
                    <div className="mt-2 text-2xl font-bold text-gray-900">{formatRub(loyaltyInfo.summary.average_check)}</div>
                    <div className="mt-1 text-sm text-gray-500">{loyaltyInfo.summary.discount_card_number || 'Карта не указана'}</div>
                  </div>
                </div>

                <div className="rounded-lg bg-white p-6 shadow">
                  <div className="mb-3 flex items-center justify-between gap-4">
                    <div>
                      <h2 className="text-xl font-bold text-gray-900">Прогресс уровня</h2>
                      <p className="mt-1 text-sm text-gray-500">
                        {loyaltyInfo.level_progress.next_level
                          ? `До уровня "${loyaltyInfo.level_progress.next_level.name}" осталось купить на ${formatRub(loyaltyInfo.level_progress.remaining_total)}`
                          : 'Максимальный уровень программы достигнут'}
                      </p>
                    </div>
                    <div className="text-sm font-medium text-gray-700">
                      {Math.round((loyaltyInfo.level_progress.progress || 0) * 100)}%
                    </div>
                  </div>
                  <div className="h-3 overflow-hidden rounded-full bg-gray-100">
                    <div
                      className="h-full rounded-full bg-pink-600"
                      style={{ width: `${Math.min(100, Math.max(0, (loyaltyInfo.level_progress.progress || 0) * 100))}%` }}
                    />
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {loyaltyInfo.program_info.levels.map((level) => (
                      <span
                        key={level.name}
                        className={`rounded-full border px-3 py-1.5 text-xs ${
                          loyaltyInfo.level_progress.current_level.name === level.name
                            ? 'border-pink-200 bg-pink-50 text-pink-700'
                            : 'border-gray-200 bg-gray-50 text-gray-600'
                        }`}
                      >
                        {level.name}: {level.condition}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="rounded-lg bg-white p-6 shadow">
                  <div className="mb-4 flex items-center justify-between">
                    <h2 className="text-xl font-bold text-gray-900">История бонусов</h2>
                    <div className="text-sm text-gray-500">
                      Начислено: +{loyaltyInfo.summary.earned_points_loaded} · Списано: -{loyaltyInfo.summary.spent_points_loaded}
                    </div>
                  </div>
                  {loyaltyInfo.transactions.length === 0 ? (
                    <p className="py-8 text-center text-gray-500">Транзакций пока нет.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Дата</th>
                            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Тип</th>
                            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Причина</th>
                            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Источник</th>
                            <th className="px-4 py-3 text-right text-xs font-medium uppercase text-gray-500">Баллы</th>
                            <th className="px-4 py-3 text-right text-xs font-medium uppercase text-gray-500">Баланс</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200 bg-white">
                          {loyaltyInfo.transactions.map((transaction) => (
                            <tr key={transaction.id} className="hover:bg-gray-50">
                              <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-700">
                                {new Date(transaction.created_at).toLocaleString('ru-RU')}
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-700">
                                {transaction.type === 'earn' ? 'Начисление' : transaction.type === 'spend' ? 'Списание' : transaction.type}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-700">
                                {transaction.reason || transaction.description || '—'}
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
                                {transaction.source || '—'}
                              </td>
                              <td className={`whitespace-nowrap px-4 py-3 text-right text-sm font-semibold ${transaction.points >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                {transaction.points > 0 ? '+' : ''}{transaction.points}
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 text-right text-sm font-medium text-gray-900">
                                {transaction.balance_after}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="bg-white rounded-lg shadow p-6">
                <p className="text-gray-500">Не удалось загрузить программу лояльности.</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'looks' && (
          <div className="space-y-6">
            {loadingSavedItems ? (
              <div className="bg-white rounded-lg shadow p-8 text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-pink-600 mx-auto"></div>
                <p className="mt-4 text-gray-600">Загрузка сохраненного...</p>
              </div>
            ) : savedItems ? (
              <>
                <div className="rounded-lg bg-white p-6 shadow">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <h2 className="text-xl font-bold text-gray-900">Избранные товары</h2>
                      <p className="mt-1 text-sm text-gray-500">
                        Серверное избранное из приложения и товары из обращений к стилисту.
                      </p>
                    </div>
                    <div className="text-sm text-gray-500">{savedItems.favorite_products.length} товаров</div>
                  </div>
                  {savedItems.favorite_products.length === 0 ? (
                    <p className="py-6 text-gray-500">Избранных товаров пока нет.</p>
                  ) : (
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {savedItems.favorite_products.map((product) => (
                        <div key={`${product.source}-${product.id}`} className="rounded-lg border border-gray-200 p-3">
                          <div className="flex gap-3">
                            <div className="h-20 w-20 shrink-0 overflow-hidden rounded-md border border-gray-200 bg-gray-50">
                              {product.image_url ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img src={product.image_url} alt={product.name || product.id} className="h-full w-full object-cover" />
                              ) : (
                                <div className="flex h-full items-center justify-center text-xs text-gray-400">Нет фото</div>
                              )}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="line-clamp-2 font-medium text-gray-900">{product.name || product.id}</div>
                              <div className="mt-1 text-xs text-gray-500">
                                {[product.brand, product.category, product.article || product.external_code].filter(Boolean).join(' · ') || 'Без деталей'}
                              </div>
                              <div className="mt-2 flex flex-wrap items-center gap-2">
                                <span className="text-sm font-semibold text-gray-900">{product.price ? formatRub(product.price) : 'Цена не указана'}</span>
                                <span className="rounded-full bg-gray-100 px-2 py-1 text-[11px] text-gray-600">{product.source}</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-lg bg-white p-6 shadow">
                  <div className="mb-4 flex items-center justify-between">
                    <h2 className="text-xl font-bold text-gray-900">Сохраненные образы</h2>
                    <div className="text-sm text-gray-500">{savedItems.saved_looks.length} образов</div>
                  </div>
                  {savedItems.saved_looks.length === 0 ? (
                    <p className="py-6 text-gray-500">Сохраненных образов пока нет.</p>
                  ) : (
                    <div className="grid gap-4 lg:grid-cols-2">
                      {savedItems.saved_looks.map((look) => (
                        <div key={look.id} className="rounded-lg border border-gray-200 p-4">
                          <div className="flex gap-4">
                            <div className="h-28 w-28 shrink-0 overflow-hidden rounded-md border border-gray-200 bg-gray-50">
                              {look.look_image_url ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img src={look.look_image_url} alt={look.look_name} className="h-full w-full object-cover" />
                              ) : (
                                <div className="flex h-full items-center justify-center text-xs text-gray-400">Нет фото</div>
                              )}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="font-semibold text-gray-900">{look.look_name}</div>
                              <div className="mt-1 text-sm text-gray-500">
                                {[look.look_style, look.look_mood, look.save_type].filter(Boolean).join(' · ') || 'Без тегов'}
                              </div>
                              {look.look_description && (
                                <p className="mt-2 line-clamp-3 text-sm text-gray-700">{look.look_description}</p>
                              )}
                              <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-500">
                                <span>{look.created_at ? new Date(look.created_at).toLocaleDateString('ru-RU') : 'Дата не указана'}</span>
                                <span>{look.product_ids.length} товаров в образе</span>
                                {look.is_purchased && <span className="text-green-700">Куплен</span>}
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {!!savedItems.source_notes.length && (
                    <div className="mt-5 rounded-md bg-gray-50 p-3 text-xs text-gray-500">
                      {savedItems.source_notes.join(' ')}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="bg-white rounded-lg shadow p-6">
                <p className="text-gray-500">Не удалось загрузить сохраненные образы и товары.</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'messages' && (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="space-y-8">
              <div>
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">Рассылки и сообщения платформы</h2>
                    <p className="mt-1 text-sm text-gray-500">
                      История сгенерированных и отправленных сообщений покупателю.
                    </p>
                  </div>
                  <div className="text-sm text-gray-500">
                    {messagesTotal > 0 ? `Показано ${messages.length} из ${messagesTotal}` : '—'}
                  </div>
                </div>
                {messagesLoading && messages.length === 0 ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-pink-600 mx-auto"></div>
                    <p className="mt-4 text-gray-600">Загрузка истории сообщений…</p>
                  </div>
                ) : messages.length === 0 ? (
                  <p className="text-gray-500">Сообщений платформы пока нет.</p>
                ) : (
                  <>
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Дата</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Событие / бренд</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Текст</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Статус</th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Действия</th>
                          </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                          {messages.map((msg) => (
                            <tr key={msg.id} className="hover:bg-gray-50">
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">
                                {new Date(msg.created_at).toLocaleString('ru-RU', {
                                  day: '2-digit',
                                  month: '2-digit',
                                  year: 'numeric',
                                  hour: '2-digit',
                                  minute: '2-digit',
                                })}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-700">
                                <span className="font-medium">{msg.event_type || '—'}</span>
                                {(msg.event_brand || msg.event_store) && (
                                  <span className="block text-gray-500 text-xs">
                                    {[msg.event_brand, msg.event_store].filter(Boolean).join(' · ')}
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-900 max-w-md">
                                <p className="line-clamp-2" title={msg.message}>
                                  {msg.message}
                                </p>
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap">
                                {msg.status === 'sent' ? (
                                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                    Отправлено{' '}
                                    {msg.sent_at && new Date(msg.sent_at).toLocaleDateString('ru-RU', {
                                      day: '2-digit',
                                      month: '2-digit',
                                      year: 'numeric',
                                      hour: '2-digit',
                                      minute: '2-digit',
                                    })}
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                    Сгенерировано
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap text-right text-sm">
                                {messagesActionId === msg.id ? (
                                  <span className="text-gray-400">…</span>
                                ) : (
                                  <>
                                    {msg.status === 'new' && (
                                      <button
                                        type="button"
                                        onClick={() => handleMarkSentMessage(msg)}
                                        className="text-pink-600 hover:text-pink-800 font-medium mr-3"
                                      >
                                        Отправить
                                      </button>
                                    )}
                                    <button
                                      type="button"
                                      onClick={() => handleDeleteMessage(msg)}
                                      className="text-red-600 hover:text-red-800 font-medium"
                                    >
                                      Удалить
                                    </button>
                                  </>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {messages.length < messagesTotal && (
                      <div className="mt-4 flex justify-center">
                        <button
                          type="button"
                          onClick={loadMoreMessages}
                          disabled={messagesLoading}
                          className="px-4 py-2 bg-white text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 border border-gray-200 disabled:opacity-50"
                        >
                          {messagesLoading ? 'Загрузка…' : 'Загрузить еще'}
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>

              <div className="border-t border-gray-200 pt-8">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">Диалоги со стилистом</h2>
                    <p className="mt-1 text-sm text-gray-500">
                      История обращений покупателя к AI и живому стилисту с темами диалогов.
                    </p>
                  </div>
                  <div className="text-sm text-gray-500">
                    {stylistDialogsTotal > 0 ? `${stylistDialogsTotal} диалогов` : '—'}
                  </div>
                </div>
                {stylistDialogsLoading ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-pink-600 mx-auto"></div>
                    <p className="mt-4 text-gray-600">Загрузка диалогов со стилистом…</p>
                  </div>
                ) : stylistDialogs.length === 0 ? (
                  <p className="text-gray-500">Диалогов со стилистом пока нет.</p>
                ) : (
                  <div className="space-y-4">
                    {stylistDialogs.map((dialog) => (
                      <div key={dialog.id} className="rounded-lg border border-gray-200">
                        <div className="border-b border-gray-200 bg-gray-50 px-4 py-3">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <div className="font-medium text-gray-900">{dialog.topic}</div>
                              <div className="mt-1 text-xs text-gray-500">
                                {[dialog.source, dialog.scenario].filter(Boolean).join(' · ') || 'Источник не указан'}
                              </div>
                            </div>
                            <div className="text-right text-xs text-gray-500">
                              <div>{dialog.status_label}</div>
                              <div>{dialog.assigned_stylist_name || 'Стилист не назначен'}</div>
                              <div>{dialog.last_message_at ? new Date(dialog.last_message_at).toLocaleString('ru-RU') : 'Без сообщений'}</div>
                            </div>
                          </div>
                        </div>
                        <div className="max-h-96 space-y-3 overflow-y-auto p-4">
                          {dialog.messages.map((message) => {
                            const outgoing = message.role === 'stylist' || message.role === 'assistant';
                            const productAttachments = (message.attachments || []).filter((item) => item?.type === 'product');
                            const imageAttachments = (message.attachments || []).filter((item) => item?.type === 'image' && item?.url);
                            return (
                              <div
                                key={message.id}
                                className={`max-w-[85%] rounded-md border px-3 py-2 text-sm ${
                                  outgoing
                                    ? 'ml-auto border-gray-900 bg-gray-900 text-white'
                                    : 'border-gray-200 bg-white text-gray-900'
                                }`}
                              >
                                <div className={`mb-1 text-xs ${outgoing ? 'text-gray-300' : 'text-gray-500'}`}>
                                  {message.sender_name || (message.role === 'user' ? 'Покупатель' : 'Стилист')}
                                  {' · '}
                                  {message.created_at ? new Date(message.created_at).toLocaleString('ru-RU') : '—'}
                                </div>
                                {!!message.text && <div className="whitespace-pre-wrap">{message.text}</div>}
                                {!message.text && !message.attachments?.length && (
                                  <div className="whitespace-pre-wrap">Сообщение без текста</div>
                                )}
                                {!!productAttachments.length && (
                                  <div className="mt-2 space-y-2">
                                    {productAttachments.map((attachment, index) => (
                                      <div
                                        key={`${message.id}-product-${attachment.product_id || index}`}
                                        className={`rounded-md border p-2 ${
                                          outgoing ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-gray-50'
                                        }`}
                                      >
                                        <div className={`font-medium ${outgoing ? 'text-white' : 'text-gray-900'}`}>
                                          {attachment.name || attachment.product_id || 'Карточка товара'}
                                        </div>
                                        <div className={`mt-1 text-xs ${outgoing ? 'text-gray-300' : 'text-gray-500'}`}>
                                          {[attachment.brand, attachment.category, attachment.article].filter(Boolean).join(' · ')}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                )}
                                {!!imageAttachments.length && (
                                  <div className="mt-2 flex flex-wrap gap-2">
                                    {imageAttachments.map((attachment, index) => (
                                      <a
                                        key={`${message.id}-image-${index}`}
                                        href={attachment.url}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="block"
                                      >
                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                        <img
                                          src={attachment.url}
                                          alt={attachment.name || 'Фото'}
                                          className="h-24 w-24 rounded border border-gray-200 object-cover"
                                        />
                                      </a>
                                    ))}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                          {!dialog.messages.length && (
                            <div className="text-sm text-gray-500">В этом диалоге пока нет сообщений.</div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
