'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { apiClient } from '@/lib/api';
import Link from 'next/link';

interface LoyaltyInfo {
  balance: number;
  transactions: Array<{
    id: string;
    type: string;
    points: number;
    balance_after: number;
    reason: string | null;
    description: string | null;
    created_at: string;
  }>;
  program_info: {
    name: string;
    description: string;
    rules: any;
    levels: Array<{
      name: string;
      min_purchases: number;
      benefits: string[];
    }>;
  };
}

export default function LoyaltyPage() {
  const { user, isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const [loyaltyInfo, setLoyaltyInfo] = useState<LoyaltyInfo | null>(null);
  const [loadingData, setLoadingData] = useState(true);

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.push('/login');
    } else if (isAuthenticated && user?.is_customer) {
      loadLoyaltyInfo();
    }
  }, [loading, isAuthenticated, user, router]);

  const loadLoyaltyInfo = async () => {
    try {
      const response = await apiClient.get<LoyaltyInfo>('/api/customer/loyalty');
      setLoyaltyInfo(response.data);
    } catch (error) {
      console.error('Error loading loyalty info:', error);
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

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <Link href="/customer" className="text-pink-600 hover:text-pink-700 mb-4 inline-block">
            ← Назад в личный кабинет
          </Link>
          <h1 className="text-3xl font-bold text-gray-900">Программа лояльности</h1>
        </div>

        {/* Баланс */}
        <div className="bg-gradient-to-r from-pink-500 to-purple-600 rounded-lg shadow-lg p-8 mb-8 text-white">
          <div className="text-center">
            <p className="text-lg opacity-90 mb-2">Ваш баланс баллов</p>
            <p className="text-6xl font-bold mb-4">{loyaltyInfo?.balance || 0}</p>
            <p className="text-sm opacity-90">1 балл = 1 рубль скидки</p>
          </div>
        </div>

        {/* Уровни программы */}
        {loyaltyInfo?.program_info.levels && (
          <div className="bg-white rounded-lg shadow p-6 mb-8">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Уровни программы</h2>
            <div className="space-y-4">
              {loyaltyInfo.program_info.levels.map((level, idx) => (
                <div key={idx} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold text-gray-900">{level.name}</h3>
                      <p className="text-sm text-gray-500 mt-1">
                        От {level.min_purchases} покупок
                      </p>
                    </div>
                    <div className="text-right">
                      <ul className="text-sm text-gray-600 space-y-1">
                        {level.benefits.map((benefit, bidx) => (
                          <li key={bidx}>• {benefit}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* История транзакций */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-bold text-gray-900 mb-4">История транзакций</h2>
          {loyaltyInfo?.transactions.length === 0 ? (
            <p className="text-gray-500 text-center py-8">Транзакций пока нет</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Дата
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Тип
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Причина
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      Баллы
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                      Баланс после
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {loyaltyInfo?.transactions.map((transaction) => (
                    <tr key={transaction.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {new Date(transaction.created_at).toLocaleDateString('ru-RU')}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {transaction.type === 'earn' ? 'Начисление' : 'Списание'}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">
                        {transaction.reason || transaction.description || '—'}
                      </td>
                      <td className={`px-6 py-4 whitespace-nowrap text-sm font-medium text-right ${
                        transaction.points > 0 ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {transaction.points > 0 ? '+' : ''}{transaction.points}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                        {transaction.balance_after}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
