'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { apiClient } from '@/lib/api';
import Link from 'next/link';

interface DashboardData {
  segments_overview: {
    segments: Array<{
      segment_id: string;
      name: string;
      customer_count: number;
      average_ltv: number;
    }>;
  };
  churn_risk: {
    total_customers: number;
    high_risk: number;
    medium_risk: number;
    low_risk: number;
  };
  top_customers: Array<{
    user_id: string;
    phone: string | null;
    full_name: string | null;
    total_spent: number;
    total_purchases: number;
  }>;
}

export default function AIMarketerPage() {
  const { user, isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [opportunities, setOpportunities] = useState<any[]>([]);

  useEffect(() => {
    if (!loading && (!isAuthenticated || (user?.role !== 'admin' && user?.role !== 'ai_marketer'))) {
      router.push('/login');
    } else if (isAuthenticated && (user?.role === 'admin' || user?.role === 'ai_marketer')) {
      loadDashboard();
      loadOpportunities();
    }
  }, [loading, isAuthenticated, user, router]);

  const loadDashboard = async () => {
    try {
      const response = await apiClient.get<DashboardData>('/api/ai-marketer/dashboard');
      setDashboard(response.data);
    } catch (error) {
      console.error('Error loading dashboard:', error);
    } finally {
      setLoadingData(false);
    }
  };

  const loadOpportunities = async () => {
    try {
      const response = await apiClient.get('/api/ai-marketer/opportunities');
      setOpportunities(response.data.opportunities || []);
    } catch (error) {
      console.error('Error loading opportunities:', error);
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
          <h1 className="text-3xl font-bold text-gray-900">AI Маркетолог</h1>
          <p className="mt-2 text-gray-600">
            Интеллектуальная аналитика и возможности для маркетинга
          </p>
        </div>

        {/* KPI карточки */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow p-6">
            <p className="text-sm text-gray-500">Всего покупателей</p>
            <p className="text-3xl font-bold text-gray-900 mt-2">
              {dashboard?.churn_risk.total_customers || 0}
            </p>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <p className="text-sm text-gray-500">Высокий риск оттока</p>
            <p className="text-3xl font-bold text-red-600 mt-2">
              {dashboard?.churn_risk.high_risk || 0}
            </p>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <p className="text-sm text-gray-500">Средний риск</p>
            <p className="text-3xl font-bold text-yellow-600 mt-2">
              {dashboard?.churn_risk.medium_risk || 0}
            </p>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <p className="text-sm text-gray-500">Возможности</p>
            <p className="text-3xl font-bold text-green-600 mt-2">
              {opportunities.length}
            </p>
          </div>
        </div>

        {/* Сегменты */}
        {dashboard?.segments_overview.segments && dashboard.segments_overview.segments.length > 0 && (
          <div className="bg-white rounded-lg shadow p-6 mb-8">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Обзор сегментов</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {dashboard.segments_overview.segments.map((segment) => (
                <div key={segment.segment_id} className="border border-gray-200 rounded-lg p-4">
                  <h3 className="font-semibold text-gray-900">{segment.name}</h3>
                  <div className="mt-2 space-y-1">
                    <p className="text-sm text-gray-600">
                      Покупателей: <span className="font-medium">{segment.customer_count}</span>
                    </p>
                    <p className="text-sm text-gray-600">
                      Средний LTV: <span className="font-medium">
                        {segment.average_ltv.toLocaleString('ru-RU')} ₽
                      </span>
                    </p>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4">
              <Link
                href="/ai-marketer/segments"
                className="text-pink-600 hover:text-pink-700 font-medium"
              >
                Детальный анализ сегментов →
              </Link>
            </div>
          </div>
        )}

        {/* Возможности */}
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-xl font-bold text-gray-900 mb-4">AI Инсайты и возможности</h2>
          {opportunities.length === 0 ? (
            <p className="text-gray-500 text-center py-8">
              Возможности не найдены. Запустите анализ для поиска возможностей.
            </p>
          ) : (
            <div className="space-y-4">
              {opportunities.map((opp, idx) => (
                <div key={idx} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`px-2 py-1 text-xs font-semibold rounded ${
                          opp.type === 're-engagement' ? 'bg-red-100 text-red-800' :
                          opp.type === 'upsell' ? 'bg-blue-100 text-blue-800' :
                          'bg-green-100 text-green-800'
                        }`}>
                          {opp.type}
                        </span>
                      </div>
                      <p className="text-gray-900 font-medium mb-2">{opp.description}</p>
                      <div className="flex items-center gap-4 text-sm text-gray-600">
                        <span>Покупателей: {opp.customer_count}</span>
                        {opp.potential_revenue && (
                          <span>Потенциальный доход: {opp.potential_revenue.toLocaleString('ru-RU')} ₽</span>
                        )}
                      </div>
                      {opp.recommended_actions && (
                        <div className="mt-2">
                          <p className="text-xs text-gray-500 mb-1">Рекомендуемые действия:</p>
                          <ul className="text-sm text-gray-700 list-disc list-inside">
                            {opp.recommended_actions.map((action: string, aidx: number) => (
                              <li key={aidx}>{action}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                    <div className="ml-4 flex gap-2">
                      <button className="px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 text-sm">
                        Создать кампанию
                      </button>
                      <button className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 text-sm">
                        Подробнее
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Топ покупатели */}
        {dashboard?.top_customers && dashboard.top_customers.length > 0 && (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Топ покупатели</h2>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Имя
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Покупок
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      Потрачено
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      Действия
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {dashboard.top_customers.map((customer) => (
                    <tr key={customer.user_id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {customer.full_name || customer.phone || '—'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {customer.total_purchases}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 text-right">
                        {customer.total_spent.toLocaleString('ru-RU')} ₽
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <Link
                          href={`/admin/customers/${customer.user_id}`}
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
        )}

        {/* Быстрые действия */}
        <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-6">
          <Link
            href="/ai-marketer/segments"
            className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
          >
            <h3 className="font-semibold text-gray-900 mb-2">Анализ сегментов</h3>
            <p className="text-sm text-gray-600">Детальный анализ всех сегментов покупателей</p>
          </Link>
          <Link
            href="/ai-marketer/campaigns/generate"
            className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
          >
            <h3 className="font-semibold text-gray-900 mb-2">Генератор кампаний</h3>
            <p className="text-sm text-gray-600">Создание персонализированных кампаний</p>
          </Link>
          <Link
            href="/ai-marketer/opportunities"
            className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
          >
            <h3 className="font-semibold text-gray-900 mb-2">Инсайты и возможности</h3>
            <p className="text-sm text-gray-600">Все обнаруженные возможности</p>
          </Link>
        </div>
      </div>
    </div>
  );
}
