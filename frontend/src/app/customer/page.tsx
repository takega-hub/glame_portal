'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { apiClient } from '@/lib/api';
import Link from 'next/link';

interface CustomerProfile {
  id: string;
  phone: string | null;
  email: string | null;
  full_name: string | null;
  discount_card_number: string | null;
  loyalty_points: number;
  customer_segment: string | null;
  total_purchases: number;
  total_spent: number;
  average_check: number | null;
  last_purchase_date: string | null;
}

interface PurchaseStats {
  total_purchases: number;
  total_spent: number;
  average_check: number;
  favorite_categories: string[];
  favorite_brands: string[];
}

export default function CustomerCabinetPage() {
  const { user, isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [stats, setStats] = useState<PurchaseStats | null>(null);
  const [loadingData, setLoadingData] = useState(true);

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.push('/login');
    } else if (isAuthenticated && user?.is_customer) {
      loadData();
    }
  }, [loading, isAuthenticated, user, router]);

  const loadData = async () => {
    try {
      const [profileRes, statsRes] = await Promise.all([
        apiClient.get<CustomerProfile>('/api/customer/profile'),
        apiClient.get<PurchaseStats>('/api/customer/purchase-stats'),
      ]);
      setProfile(profileRes.data);
      setStats(statsRes.data);
    } catch (error) {
      console.error('Error loading customer data:', error);
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

  if (!user?.is_customer) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600">Доступно только для покупателей</p>
          <Link href="/" className="text-pink-600 hover:text-pink-700 mt-4 inline-block">
            Вернуться на главную
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">
                Добро пожаловать{profile?.full_name ? `, ${profile.full_name}` : ''}!
              </h1>
              <p className="mt-1 text-sm text-gray-500">
                Ваш личный кабинет GLAME
              </p>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-pink-600">
                {profile?.loyalty_points || 0} баллов
              </div>
              <p className="text-sm text-gray-500">Баланс лояльности</p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Карточки быстрого доступа */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <Link
            href="/customer/purchases"
            className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
          >
            <div className="flex items-center">
              <div className="flex-shrink-0 bg-pink-100 rounded-lg p-3">
                <svg className="h-6 w-6 text-pink-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
                </svg>
              </div>
              <div className="ml-4">
                <h3 className="text-lg font-medium text-gray-900">История покупок</h3>
                <p className="text-sm text-gray-500">{stats?.total_purchases || 0} покупок</p>
              </div>
            </div>
          </Link>

          <Link
            href="/customer/loyalty"
            className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
          >
            <div className="flex items-center">
              <div className="flex-shrink-0 bg-yellow-100 rounded-lg p-3">
                <svg className="h-6 w-6 text-yellow-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="ml-4">
                <h3 className="text-lg font-medium text-gray-900">Программа лояльности</h3>
                <p className="text-sm text-gray-500">{profile?.loyalty_points || 0} баллов</p>
              </div>
            </div>
          </Link>

          <Link
            href="/customer/saved-looks"
            className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
          >
            <div className="flex items-center">
              <div className="flex-shrink-0 bg-purple-100 rounded-lg p-3">
                <svg className="h-6 w-6 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                </svg>
              </div>
              <div className="ml-4">
                <h3 className="text-lg font-medium text-gray-900">Сохраненные образы</h3>
                <p className="text-sm text-gray-500">Мои образы</p>
              </div>
            </div>
          </Link>

          <Link
            href="/customer/stylist"
            className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow"
          >
            <div className="flex items-center">
              <div className="flex-shrink-0 bg-blue-100 rounded-lg p-3">
                <svg className="h-6 w-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <div className="ml-4">
                <h3 className="text-lg font-medium text-gray-900">AI Стилист</h3>
                <p className="text-sm text-gray-500">Консультация</p>
              </div>
            </div>
          </Link>
        </div>

        {/* Статистика */}
        {stats && (
          <div className="bg-white rounded-lg shadow p-6 mb-8">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Ваша статистика</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <p className="text-sm text-gray-500">Всего потрачено</p>
                <p className="text-2xl font-bold text-gray-900">{stats.total_spent.toLocaleString('ru-RU')} ₽</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Средний чек</p>
                <p className="text-2xl font-bold text-gray-900">{stats.average_check.toLocaleString('ru-RU')} ₽</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Всего покупок</p>
                <p className="text-2xl font-bold text-gray-900">{stats.total_purchases}</p>
              </div>
            </div>
            {(stats.favorite_categories.length > 0 || stats.favorite_brands.length > 0) && (
              <div className="mt-6 pt-6 border-t border-gray-200">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {stats.favorite_categories.length > 0 && (
                    <div>
                      <p className="text-sm text-gray-500 mb-2">Любимые категории</p>
                      <div className="flex flex-wrap gap-2">
                        {stats.favorite_categories.map((cat, idx) => (
                          <span key={idx} className="px-3 py-1 bg-pink-100 text-pink-800 rounded-full text-sm">
                            {cat}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {stats.favorite_brands.length > 0 && (
                    <div>
                      <p className="text-sm text-gray-500 mb-2">Любимые бренды</p>
                      <div className="flex flex-wrap gap-2">
                        {stats.favorite_brands.map((brand, idx) => (
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

        {/* Информация о сегменте */}
        {profile?.customer_segment && (
          <div className="bg-gradient-to-r from-pink-500 to-purple-600 rounded-lg shadow p-6 text-white mb-8">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm opacity-90">Ваш статус</p>
                <h3 className="text-2xl font-bold mt-1">{profile.customer_segment}</h3>
              </div>
              <div className="text-right">
                <p className="text-sm opacity-90">Дисконтная карта</p>
                <p className="text-xl font-bold mt-1">{profile.discount_card_number || profile.phone}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
