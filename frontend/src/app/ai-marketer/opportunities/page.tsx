'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { apiClient } from '@/lib/api';
import Link from 'next/link';

interface Opportunity {
  type: string;
  description: string;
  customer_count: number;
  potential_revenue?: number;
  recommended_actions: string[];
}

export default function OpportunitiesPage() {
  const { user, isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [loadingData, setLoadingData] = useState(true);

  useEffect(() => {
    if (!loading && (!isAuthenticated || (user?.role !== 'admin' && user?.role !== 'ai_marketer'))) {
      router.push('/login');
    } else if (isAuthenticated && (user?.role === 'admin' || user?.role === 'ai_marketer')) {
      loadOpportunities();
    }
  }, [loading, isAuthenticated, user, router]);

  const loadOpportunities = async () => {
    try {
      const response = await apiClient.get<{ opportunities: Opportunity[]; total: number }>('/api/ai-marketer/opportunities');
      setOpportunities(response.data.opportunities || []);
    } catch (error) {
      console.error('Error loading opportunities:', error);
    } finally {
      setLoadingData(false);
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

  const getTypeColor = (type: string) => {
    switch (type) {
      case 're-engagement':
        return 'bg-red-100 text-red-800';
      case 'upsell':
        return 'bg-blue-100 text-blue-800';
      case 'cross-sell':
        return 'bg-green-100 text-green-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getTypeLabel = (type: string) => {
    switch (type) {
      case 're-engagement':
        return 'Реактивация';
      case 'upsell':
        return 'Увеличение чека';
      case 'cross-sell':
        return 'Допродажа';
      default:
        return type;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <Link href="/ai-marketer" className="text-pink-600 hover:text-pink-700 mb-4 inline-block">
            ← Назад к дашборду
          </Link>
          <h1 className="text-3xl font-bold text-gray-900">Инсайты и возможности</h1>
          <p className="mt-2 text-gray-600">
            AI-обнаруженные возможности для маркетинговых кампаний
          </p>
        </div>

        {opportunities.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-12 text-center">
            <p className="text-gray-500 mb-4">Возможности не найдены</p>
            <p className="text-sm text-gray-400">
              AI анализирует данные покупателей и найдет возможности для кампаний
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {opportunities.map((opp, idx) => (
              <div key={idx} className="bg-white rounded-lg shadow p-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <span className={`px-3 py-1 text-sm font-semibold rounded ${getTypeColor(opp.type)}`}>
                      {getTypeLabel(opp.type)}
                    </span>
                    <h3 className="text-lg font-semibold text-gray-900">{opp.description}</h3>
                  </div>
                  <div className="flex gap-2">
                    <button className="px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 text-sm">
                      Создать кампанию
                    </button>
                    <button className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 text-sm">
                      Отклонить
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-4">
                  <div>
                    <p className="text-sm text-gray-500">Покупателей</p>
                    <p className="text-2xl font-bold text-gray-900">{opp.customer_count}</p>
                  </div>
                  {opp.potential_revenue && (
                    <div>
                      <p className="text-sm text-gray-500">Потенциальный доход</p>
                      <p className="text-2xl font-bold text-green-600">
                        {opp.potential_revenue.toLocaleString('ru-RU')} ₽
                      </p>
                    </div>
                  )}
                  <div>
                    <p className="text-sm text-gray-500">Приоритет</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {opp.potential_revenue && opp.potential_revenue > 100000 ? 'Высокий' : 'Средний'}
                    </p>
                  </div>
                </div>

                {opp.recommended_actions && opp.recommended_actions.length > 0 && (
                  <div className="border-t border-gray-200 pt-4">
                    <p className="text-sm font-medium text-gray-700 mb-2">Рекомендуемые действия:</p>
                    <ul className="list-disc list-inside space-y-1">
                      {opp.recommended_actions.map((action, aidx) => (
                        <li key={aidx} className="text-sm text-gray-600">{action}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
