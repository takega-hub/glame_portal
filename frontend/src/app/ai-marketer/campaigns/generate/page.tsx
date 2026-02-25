'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { apiClient } from '@/lib/api';
import Link from 'next/link';

interface Segment {
  id: string;
  name: string;
  customer_count: number;
}

export default function CampaignGeneratePage() {
  const { user, isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const [segments, setSegments] = useState<Segment[]>([]);
  const [selectedSegment, setSelectedSegment] = useState('');
  const [campaignType, setCampaignType] = useState('discount');
  const [campaignGoal, setCampaignGoal] = useState('');
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    if (!loading && (!isAuthenticated || (user?.role !== 'admin' && user?.role !== 'ai_marketer'))) {
      router.push('/login');
    } else if (isAuthenticated && (user?.role === 'admin' || user?.role === 'ai_marketer')) {
      loadSegments();
    }
  }, [loading, isAuthenticated, user, router]);

  const loadSegments = async () => {
    try {
      const response = await apiClient.get<Segment[]>('/api/admin/customers/segments/list');
      setSegments(response.data);
    } catch (error) {
      console.error('Error loading segments:', error);
    }
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    setGenerating(true);
    setResult(null);

    try {
      const response = await apiClient.post('/api/ai-marketer/campaigns/generate', {
        segment_id: selectedSegment || null,
        campaign_type: campaignType,
        campaign_goal: campaignGoal,
      });
      setResult(response.data);
    } catch (error) {
      console.error('Error generating campaign:', error);
      alert('Ошибка при генерации кампании');
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
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
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <Link href="/ai-marketer" className="text-pink-600 hover:text-pink-700 mb-4 inline-block">
            ← Назад к дашборду
          </Link>
          <h1 className="text-3xl font-bold text-gray-900">Генератор кампаний</h1>
          <p className="mt-2 text-gray-600">
            Создание персонализированных маркетинговых кампаний с помощью AI
          </p>
        </div>

        <form onSubmit={handleGenerate} className="bg-white rounded-lg shadow p-6 space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Сегмент покупателей
            </label>
            <select
              value={selectedSegment}
              onChange={(e) => setSelectedSegment(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
            >
              <option value="">Все покупатели</option>
              {segments.map((segment) => (
                <option key={segment.id} value={segment.id}>
                  {segment.name} ({segment.customer_count} покупателей)
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Тип кампании
            </label>
            <select
              value={campaignType}
              onChange={(e) => setCampaignType(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
            >
              <option value="discount">Скидка</option>
              <option value="new_product">Новый товар</option>
              <option value="re-engagement">Реактивация</option>
              <option value="birthday">День рождения</option>
              <option value="loyalty">Программа лояльности</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Цель кампании
            </label>
            <textarea
              value={campaignGoal}
              onChange={(e) => setCampaignGoal(e.target.value)}
              rows={4}
              placeholder="Опишите цель кампании, например: 'Реактивировать покупателей, которые не покупали более 90 дней'"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500"
            />
          </div>

          <div className="flex gap-4">
            <button
              type="submit"
              disabled={generating}
              className="flex-1 px-4 py-2 bg-pink-600 text-white rounded-md hover:bg-pink-700 disabled:opacity-50"
            >
              {generating ? 'Генерация...' : 'Сгенерировать кампанию'}
            </button>
            <Link
              href="/ai-marketer"
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200"
            >
              Отмена
            </Link>
          </div>
        </form>

        {result && (
          <div className="mt-6 bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-bold text-gray-900 mb-4">Результат генерации</h2>
            <div className="bg-gray-50 rounded-lg p-4">
              <pre className="whitespace-pre-wrap text-sm text-gray-700">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
            <p className="mt-4 text-sm text-gray-500">
              Генерация кампаний будет полностью реализована в следующей версии
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
