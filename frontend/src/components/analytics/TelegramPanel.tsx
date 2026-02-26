"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import { fetchJson } from '@/lib/utils';

export function TelegramPanel() {
  const [metrics, setMetrics] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchMetrics = async () => {
    try {
      setLoading(true);
      const { data } = await fetchJson<{ status?: string; metrics?: any[] }>('/api/analytics/telegram/metrics?days=30');
      if (data.status === 'success') setMetrics(data.metrics ?? []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const syncData = async () => {
    try {
      setLoading(true);
      await fetchJson('/api/analytics/telegram/sync', { method: 'POST' });
      await fetchMetrics();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchMetrics(); }, []);

  const channelMetrics = metrics.filter(m => m.metric_type === 'channel');

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Telegram</span>
          <Button onClick={syncData} disabled={loading} size="sm" variant="outline">
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Синхронизировать
          </Button>
        </CardTitle>
        <CardDescription>Статистика канала и бота</CardDescription>
      </CardHeader>
      <CardContent>
        {loading && !metrics.length ? <div>Загрузка...</div> : (
          <div className="space-y-4">
            {channelMetrics.length > 0 && (
              <div className="bg-gray-100 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Участники канала</p>
                <p className="text-2xl font-bold text-gray-900">{channelMetrics[0]?.value.toLocaleString()}</p>
                <p className="text-xs text-gray-600 mt-2">
                  Обновлено: {new Date(channelMetrics[0]?.date).toLocaleString()}
                </p>
              </div>
            )}
            {metrics.length === 0 && <div className="text-gray-600">Нет данных. Нажмите "Синхронизировать"</div>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
