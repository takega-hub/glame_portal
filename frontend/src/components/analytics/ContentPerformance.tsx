'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

interface ContentPerformanceProps {
  days?: number;
}

export default function ContentPerformance({ days = 30 }: ContentPerformanceProps) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [days]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getContentPerformance(days);
      setData(result);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки данных');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
        <p className="text-gray-600">Загрузка...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  if (!data || !data.performance_by_item || data.performance_by_item.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Анализ контента</h3>
        <p className="text-gray-600">Нет данных о производительности контента за выбранный период</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Анализ контента</h3>
      <div className="space-y-4">
        <div className="text-sm text-gray-600 mb-4">
          Всего событий: <strong>{data.total_content_events}</strong>
        </div>
        {data.performance_by_item.map((item: any, index: number) => (
          <div key={index} className="border border-gray-200 rounded-lg p-4">
            <div className="font-medium text-gray-900 mb-2">
              Контент ID: {item.content_item_id.substring(0, 8)}...
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-600">Всего событий: </span>
                <span className="font-medium text-gray-900">{item.total_events}</span>
              </div>
              <div>
                <span className="text-gray-600">Каналы: </span>
                <span className="font-medium text-gray-900">{item.channels.join(', ') || 'N/A'}</span>
              </div>
            </div>
            <div className="mt-2">
              <span className="text-gray-600 text-sm">Типы событий: </span>
              <div className="flex flex-wrap gap-2 mt-1">
                {Object.entries(item.event_counts).map(([type, count]: [string, any]) => (
                  <span key={type} className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs">
                    {type}: {count}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
