'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { apiClient } from '@/lib/api';
import Link from 'next/link';

interface SegmentAnalysis {
  segment_id: string;
  name: string;
  description: string;
  size: number;
  average_ltv: number;
  average_purchases: number;
  insights: string;
}

export default function SegmentsAnalysisPage() {
  const { user, isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const [segments, setSegments] = useState<SegmentAnalysis[]>([]);
  const [loadingData, setLoadingData] = useState(true);

  useEffect(() => {
    if (!loading && (!isAuthenticated || (user?.role !== 'admin' && user?.role !== 'ai_marketer'))) {
      router.push('/login');
    } else if (isAuthenticated && (user?.role === 'admin' || user?.role === 'ai_marketer')) {
      loadSegments();
    }
  }, [loading, isAuthenticated, user, router]);

  const loadSegments = async () => {
    try {
      const response = await apiClient.get<{ segments: SegmentAnalysis[] }>('/api/ai-marketer/segments/analysis');
      setSegments(response.data.segments || []);
    } catch (error) {
      console.error('Error loading segments analysis:', error);
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
          <Link href="/ai-marketer" className="text-pink-600 hover:text-pink-700 mb-4 inline-block">
            ← Назад к дашборду
          </Link>
          <h1 className="text-3xl font-bold text-gray-900">Анализ сегментов</h1>
        </div>

        <div className="space-y-6">
          {segments.map((segment) => (
            <div key={segment.segment_id} className="bg-white rounded-lg shadow p-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 className="text-2xl font-bold text-gray-900">{segment.name}</h2>
                  {segment.description && (
                    <p className="text-gray-600 mt-1">{segment.description}</p>
                  )}
                </div>
                <button className="px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700">
                  Создать кампанию
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
                <div>
                  <p className="text-sm text-gray-500">Размер сегмента</p>
                  <p className="text-2xl font-bold text-gray-900">{segment.size} покупателей</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Средний LTV</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {segment.average_ltv.toLocaleString('ru-RU')} ₽
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Среднее количество покупок</p>
                  <p className="text-2xl font-bold text-gray-900">{segment.average_purchases.toFixed(1)}</p>
                </div>
              </div>

              {segment.insights && (
                <div className="border-t border-gray-200 pt-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">AI Инсайты и рекомендации</h3>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <p className="text-gray-700 whitespace-pre-wrap">{segment.insights}</p>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {segments.length === 0 && (
          <div className="bg-white rounded-lg shadow p-12 text-center">
            <p className="text-gray-500 mb-4">Сегментов пока нет</p>
            <Link
              href="/admin/customers/segments"
              className="text-pink-600 hover:text-pink-700 font-medium"
            >
              Создать сегменты →
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
