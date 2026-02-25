"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

interface YandexMetrikaMetrics {
  visits: {
    visits: number;
    users: number;
    pageviews: number;
    bounce_rate: number;
    avg_visit_duration: number;
  };
  traffic_sources: Array<{
    source: string;
    visits: number;
    users: number;
  }>;
  behavior: {
    depth: number;
    time_on_site: number;
    bounce_rate: number;
    new_users_rate: number;
  };
  ecommerce: {
    transactions: number;
    revenue: number;
    avg_order_value: number;
    ecommerce_conversion_rate: number;
  };
}

export function YandexMetrikaPanel() {
  const [metrics, setMetrics] = useState<YandexMetrikaMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch('/api/analytics/yandex-metrika/metrics?days=30');
      const data = await response.json();
      if (data.status === 'success') {
        setMetrics(data.data);
      } else {
        setError('Ошибка загрузки данных');
      }
    } catch (err) {
      setError('Ошибка подключения к API');
    } finally {
      setLoading(false);
    }
  };

  const syncData = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch('/api/analytics/yandex-metrika/sync', { method: 'POST' });
      const data = await response.json();
      if (data.status === 'success') {
        setMetrics(data.metrics);
      }
    } catch (err) {
      setError('Ошибка синхронизации');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
  }, []);

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Яндекс.Метрика</CardTitle>
          <CardDescription className="text-red-500">{error}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Яндекс.Метрика</span>
          <Button onClick={syncData} disabled={loading} size="sm" variant="outline">
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Синхронизировать
          </Button>
        </CardTitle>
        <CardDescription>Статистика посещаемости сайта за последние 30 дней</CardDescription>
      </CardHeader>
      <CardContent>
        {loading && !metrics ? (
          <div>Загрузка...</div>
        ) : metrics ? (
          <div className="space-y-4">
            {/* Посещения */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-gray-100 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Визиты</p>
                <p className="text-2xl font-bold text-gray-900">{metrics.visits.visits.toLocaleString()}</p>
              </div>
              <div className="bg-gray-100 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Пользователи</p>
                <p className="text-2xl font-bold text-gray-900">{metrics.visits.users.toLocaleString()}</p>
              </div>
              <div className="bg-gray-100 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Просмотры</p>
                <p className="text-2xl font-bold text-gray-900">{metrics.visits.pageviews.toLocaleString()}</p>
              </div>
              <div className="bg-gray-100 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Отказы</p>
                <p className="text-2xl font-bold text-gray-900">{metrics.visits.bounce_rate.toFixed(1)}%</p>
              </div>
            </div>

            {/* E-commerce */}
            <div>
              <h3 className="text-lg font-semibold mb-2 text-gray-900">E-commerce</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-gray-100 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Транзакции</p>
                  <p className="text-2xl font-bold text-gray-900">{metrics.ecommerce.transactions}</p>
                </div>
                <div className="bg-gray-100 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Выручка</p>
                  <p className="text-2xl font-bold text-gray-900">₽{metrics.ecommerce.revenue.toLocaleString()}</p>
                </div>
                <div className="bg-gray-100 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Средний чек</p>
                  <p className="text-2xl font-bold text-gray-900">₽{metrics.ecommerce.avg_order_value.toFixed(0)}</p>
                </div>
                <div className="bg-gray-100 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Конверсия</p>
                  <p className="text-2xl font-bold text-gray-900">{metrics.ecommerce.ecommerce_conversion_rate.toFixed(2)}%</p>
                </div>
              </div>
            </div>

            {/* Источники трафика */}
            <div>
              <h3 className="text-lg font-semibold mb-2 text-gray-900">Источники трафика</h3>
              <div className="space-y-2">
                {metrics.traffic_sources.map((source, idx) => (
                  <div key={idx} className="flex items-center justify-between p-2 bg-gray-100 rounded">
                    <span className="text-gray-900">{source.source}</span>
                    <span className="font-semibold text-gray-900">{source.visits} визитов</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div>Нет данных</div>
        )}
      </CardContent>
    </Card>
  );
}
