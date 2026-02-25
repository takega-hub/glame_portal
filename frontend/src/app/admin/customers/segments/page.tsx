'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { apiClient } from '@/lib/api';
import Link from 'next/link';

interface Segment {
  id: string;
  name: string;
  description: string | null;
  customer_count: number;
  color: string | null;
  is_auto_generated: boolean;
}

export default function CustomerSegmentsPage() {
  const { user, isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const [segments, setSegments] = useState<Segment[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    if (!loading && (!isAuthenticated || user?.role !== 'admin')) {
      router.push('/login');
    } else if (isAuthenticated && user?.role === 'admin') {
      loadSegments();
    }
  }, [loading, isAuthenticated, user, router]);

  const loadSegments = async () => {
    try {
      const response = await apiClient.get<Segment[]>('/api/admin/customers/segments/list');
      setSegments(response.data);
    } catch (error) {
      console.error('Error loading segments:', error);
    } finally {
      setLoadingData(false);
    }
  };

  const handleAutoGenerate = async () => {
    if (!confirm('Запустить автоматическую сегментацию? Это может занять некоторое время.')) {
      return;
    }

    setGenerating(true);
    try {
      await apiClient.post('/api/ai-marketer/segments/auto-generate');
      alert('Сегментация запущена. Обновите страницу через несколько секунд.');
      setTimeout(() => loadSegments(), 3000);
    } catch (error) {
      console.error('Error generating segments:', error);
      alert('Ошибка при запуске сегментации');
    } finally {
      setGenerating(false);
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
        <div className="mb-6 flex items-center justify-between">
          <div>
            <Link href="/admin/customers" className="text-pink-600 hover:text-pink-700 mb-4 inline-block">
              ← Назад к покупателям
            </Link>
            <h1 className="text-3xl font-bold text-gray-900">Сегменты покупателей</h1>
          </div>
          <div className="flex gap-4">
            <button
              onClick={handleAutoGenerate}
              disabled={generating}
              className="px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 disabled:opacity-50"
            >
              {generating ? 'Генерация...' : 'Автосегментация AI'}
            </button>
            <button className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700">
              Создать сегмент
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {segments.map((segment) => (
            <div
              key={segment.id}
              className="bg-white rounded-lg shadow p-6"
              style={{
                borderTop: segment.color ? `4px solid ${segment.color}` : '4px solid #e5e7eb'
              }}
            >
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-xl font-bold text-gray-900">{segment.name}</h3>
                  {segment.is_auto_generated && (
                    <span className="inline-block mt-1 px-2 py-1 text-xs bg-purple-100 text-purple-800 rounded">
                      AI
                    </span>
                  )}
                </div>
              </div>
              
              {segment.description && (
                <p className="text-sm text-gray-600 mb-4">{segment.description}</p>
              )}
              
              <div className="flex items-center justify-between pt-4 border-t border-gray-200">
                <div>
                  <p className="text-sm text-gray-500">Покупателей</p>
                  <p className="text-2xl font-bold text-gray-900">{segment.customer_count}</p>
                </div>
                <div className="flex gap-2">
                  <Link
                    href={`/admin/customers?segment=${segment.name}`}
                    className="px-3 py-1 text-sm bg-pink-100 text-pink-700 rounded hover:bg-pink-200"
                  >
                    Просмотреть
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>

        {segments.length === 0 && (
          <div className="bg-white rounded-lg shadow p-12 text-center">
            <p className="text-gray-500 mb-4">Сегментов пока нет</p>
            <button
              onClick={handleAutoGenerate}
              disabled={generating}
              className="px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 disabled:opacity-50"
            >
              {generating ? 'Генерация...' : 'Создать сегменты автоматически'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
