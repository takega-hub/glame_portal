"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function UnifiedAnalyticsPanel() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
    try {
      setLoading(true);
      const response = await fetch('http://localhost:8000/api/analytics/unified?days=30');
      const result = await response.json();
      if (result.status === 'success') setData(result);
    } catch (err) {
      console.error('Error fetching unified analytics:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  if (loading || !data) return <div>Загрузка объединенной аналитики...</div>;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Объединенная аналитика</CardTitle>
        <CardDescription>Сводка по всем источникам данных</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Сайт (Яндекс.Метрика) */}
          <div className="bg-gradient-to-br from-orange-50 to-orange-100 p-6 rounded-lg">
            <h3 className="text-sm font-semibold text-orange-900 mb-2">Сайт</h3>
            <p className="text-2xl font-bold text-orange-900">
              {data.website?.visits?.toLocaleString() || 0}
            </p>
            <p className="text-xs text-orange-700 mt-1">
              {data.website?.visitors?.toLocaleString() || 0} посетителей
            </p>
            {data.website?.bounce_rate !== undefined && (
              <p className="text-xs text-orange-700">
                Отказы: {data.website.bounce_rate}%
              </p>
            )}
          </div>
          
          <div className="bg-gradient-to-br from-blue-50 to-blue-100 p-6 rounded-lg">
            <h3 className="text-sm font-semibold text-blue-900 mb-2">Социальные сети</h3>
            <p className="text-2xl font-bold text-blue-900">{data.social_media.total_metrics}</p>
            <p className="text-xs text-blue-700 mt-1">
              Платформы: {data.social_media.platforms.length > 0 ? data.social_media.platforms.join(', ') : 'нет данных'}
            </p>
          </div>
          
          <div className="bg-gradient-to-br from-green-50 to-green-100 p-6 rounded-lg">
            <h3 className="text-sm font-semibold text-green-900 mb-2">Продажи</h3>
            <p className="text-2xl font-bold text-green-900">
              ₽{data.sales.total_revenue.toLocaleString()}
            </p>
            <p className="text-xs text-green-700 mt-1">{data.sales.total_orders} заказов</p>
          </div>
          
          <div className="bg-gradient-to-br from-purple-50 to-purple-100 p-6 rounded-lg">
            <h3 className="text-sm font-semibold text-purple-900 mb-2">Офлайн магазины</h3>
            <p className="text-2xl font-bold text-purple-900">
              {data.stores.total_visitors.toLocaleString()}
            </p>
            <p className="text-xs text-purple-700 mt-1">посетителей</p>
            <p className="text-xs text-purple-700">{data.stores.total_sales} продаж</p>
          </div>
        </div>
        
        <div className="mt-4 p-4 bg-gray-100 rounded-lg">
          <p className="text-sm text-gray-700">
            Период: {new Date(data.period.start).toLocaleDateString()} - {new Date(data.period.end).toLocaleDateString()}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
