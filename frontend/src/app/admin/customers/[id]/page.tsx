'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { apiClient } from '@/lib/api';
import Link from 'next/link';
import MessageGenerator from '@/components/customers/MessageGenerator';

interface CustomerDetail {
  id: string;
  phone: string | null;
  email: string | null;
  full_name: string | null;
  city: string | null;
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

export default function CustomerDetailPage() {
  const { user, isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const params = useParams();
  const customerId = params.id as string;
  const [customer, setCustomer] = useState<CustomerDetail | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'purchases' | 'loyalty' | 'looks' | 'messages'>('overview');
  const [isEditingGender, setIsEditingGender] = useState(false);
  const [editGender, setEditGender] = useState<string | null>(null);
  const [savingGender, setSavingGender] = useState(false);
  
  // История покупок
  const [purchaseHistory, setPurchaseHistory] = useState<PurchaseHistoryResponse | null>(null);
  const [loadingPurchases, setLoadingPurchases] = useState(false);

  useEffect(() => {
    if (!loading && (!isAuthenticated || user?.role !== 'admin')) {
      router.push('/login');
    } else if (isAuthenticated && user?.role === 'admin') {
      loadCustomer();
    }
  }, [loading, isAuthenticated, user, router, customerId]);

  // Загружаем историю покупок при переключении на вкладку
  useEffect(() => {
    if (activeTab === 'purchases' && !purchaseHistory && !loadingPurchases) {
      loadPurchaseHistory();
    }
  }, [activeTab]);

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
          <h1 className="text-3xl font-bold text-gray-900">
            {customer.full_name || customer.phone || 'Покупатель'}
          </h1>
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
          <div className="bg-white rounded-lg shadow p-6">
            <p className="text-gray-500">Информация о программе лояльности будет загружена здесь</p>
          </div>
        )}

        {activeTab === 'looks' && (
          <div className="bg-white rounded-lg shadow p-6">
            <p className="text-gray-500">Сохраненные образы будут загружены здесь</p>
          </div>
        )}

        {activeTab === 'messages' && (
          <div>
            <MessageGenerator
              clientId={customer.id}
              clientName={customer.full_name || undefined}
              purchaseHistory={purchaseHistory?.items.map(p => ({
                brand: p.brand || '',
                date: p.purchase_date,
                store: undefined
              })) || []}
            />
          </div>
        )}
      </div>
    </div>
  );
}
