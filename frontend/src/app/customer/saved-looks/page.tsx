'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { apiClient } from '@/lib/api';
import Link from 'next/link';

interface SavedLook {
  id: string;
  look_id: string;
  look_name: string;
  save_type: string;
  notes: string | null;
  is_purchased: boolean;
  created_at: string;
}

export default function SavedLooksPage() {
  const { user, isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const [savedLooks, setSavedLooks] = useState<SavedLook[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [activeTab, setActiveTab] = useState<'favorite' | 'generated'>('favorite');

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.push('/login');
    } else if (isAuthenticated && user?.is_customer) {
      loadSavedLooks();
    }
  }, [loading, isAuthenticated, user, router, activeTab]);

  const loadSavedLooks = async () => {
    try {
      const response = await apiClient.get<SavedLook[]>('/api/customer/saved-looks', {
        params: { save_type: activeTab }
      });
      setSavedLooks(response.data);
    } catch (error) {
      console.error('Error loading saved looks:', error);
    } finally {
      setLoadingData(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Удалить сохраненный образ?')) return;
    
    try {
      await apiClient.delete(`/api/customer/saved-looks/${id}`);
      loadSavedLooks();
    } catch (error) {
      console.error('Error deleting saved look:', error);
      alert('Ошибка при удалении');
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
          <h1 className="text-3xl font-bold text-gray-900">Сохраненные образы</h1>
        </div>

        {/* Вкладки */}
        <div className="bg-white rounded-lg shadow mb-6">
          <div className="border-b border-gray-200">
            <nav className="flex -mb-px">
              <button
                onClick={() => setActiveTab('favorite')}
                className={`py-4 px-6 text-sm font-medium border-b-2 ${
                  activeTab === 'favorite'
                    ? 'border-pink-500 text-pink-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Избранные
              </button>
              <button
                onClick={() => setActiveTab('generated')}
                className={`py-4 px-6 text-sm font-medium border-b-2 ${
                  activeTab === 'generated'
                    ? 'border-pink-500 text-pink-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Персональные
              </button>
            </nav>
          </div>
        </div>

        {/* Список образов */}
        {savedLooks.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-12 text-center">
            <p className="text-gray-500 mb-4">Сохраненных образов пока нет</p>
            <Link
              href="/customer/stylist"
              className="text-pink-600 hover:text-pink-700 font-medium"
            >
              Получить консультацию AI стилиста →
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {savedLooks.map((savedLook) => (
              <div key={savedLook.id} className="bg-white rounded-lg shadow overflow-hidden">
                <div className="p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">
                    {savedLook.look_name}
                  </h3>
                  {savedLook.notes && (
                    <p className="text-sm text-gray-600 mb-4">{savedLook.notes}</p>
                  )}
                  <div className="flex items-center justify-between">
                    <div className="flex gap-2">
                      <Link
                        href={`/looks/${savedLook.look_id}`}
                        className="px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 text-sm"
                      >
                        Посмотреть
                      </Link>
                      {savedLook.is_purchased && (
                        <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-xs">
                          Куплено
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => handleDelete(savedLook.id)}
                      className="text-red-600 hover:text-red-700 text-sm"
                    >
                      Удалить
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
