"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

export function VKPanel() {
  const [metrics, setMetrics] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchMetrics = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/analytics/vk/metrics?days=30');
      const data = await response.json();
      if (data.status === 'success') setMetrics(data.metrics);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const syncData = async () => {
    try {
      setLoading(true);
      await fetch('/api/analytics/vk/sync', { method: 'POST' });
      await fetchMetrics();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchMetrics(); }, []);

  const groupMetrics = metrics.filter(m => m.metric_type === 'group');
  const postMetrics = metrics.filter(m => m.metric_type === 'post');

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>ВКонтакте</span>
          <Button onClick={syncData} disabled={loading} size="sm" variant="outline">
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Синхронизировать
          </Button>
        </CardTitle>
        <CardDescription>Статистика сообщества и постов</CardDescription>
      </CardHeader>
      <CardContent>
        {loading && !metrics.length ? <div>Загрузка...</div> : (
          <div className="space-y-4">
            {groupMetrics.length > 0 && (
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-gray-100 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Участники</p>
                  <p className="text-2xl font-bold text-gray-900">{groupMetrics[0]?.value.toLocaleString()}</p>
                </div>
                <div className="bg-gray-100 p-4 rounded-lg">
                  <p className="text-sm text-gray-600">Охват</p>
                  <p className="text-2xl font-bold text-gray-900">{groupMetrics[0]?.reach?.toLocaleString() || 'N/A'}</p>
                </div>
              </div>
            )}
            <div>
              <h3 className="text-lg font-semibold mb-2 text-gray-900">Посты ({postMetrics.length})</h3>
              <div className="space-y-2">
                {postMetrics.slice(0, 5).map((post) => (
                  <div key={post.id} className="p-3 bg-gray-100 rounded-lg flex justify-between">
                    <span className="text-sm text-gray-900">{new Date(post.date).toLocaleDateString()}</span>
                    <span className="text-xs text-gray-900">❤️ {post.likes} 💬 {post.comments} 🔄 {post.shares}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
