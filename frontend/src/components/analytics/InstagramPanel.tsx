"use client";

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

interface InstagramMetric {
  id: string;
  metric_type: string;
  post_id?: string;
  date: string;
  value: number;
  likes?: number;
  comments?: number;
  views?: number;
  reach?: number;
  engagement?: number;
  metadata?: any;
}

export function InstagramPanel() {
  const [metrics, setMetrics] = useState<InstagramMetric[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch('/api/analytics/instagram/metrics?days=30');
      const data = await response.json();
      if (data.status === 'success') {
        setMetrics(data.metrics);
      }
    } catch (err) {
      setError('Ошибка загрузки данных Instagram');
    } finally {
      setLoading(false);
    }
  };

  const syncData = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch('/api/analytics/instagram/sync', { method: 'POST' });
      const data = await response.json();
      if (data.status === 'success') {
        await fetchMetrics();
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

  const accountMetrics = metrics.filter(m => m.metric_type === 'account');
  const postMetrics = metrics.filter(m => m.metric_type === 'post');

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Instagram</span>
          <Button onClick={syncData} disabled={loading} size="sm" variant="outline">
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Синхронизировать
          </Button>
        </CardTitle>
        <CardDescription>Статистика аккаунта и постов</CardDescription>
      </CardHeader>
      <CardContent>
        {error && <div className="text-red-500 mb-4">{error}</div>}
        {loading && !metrics.length ? (
          <div>Загрузка...</div>
        ) : (
          <div className="space-y-4">
            {/* Account metrics */}
            {accountMetrics.length > 0 && (
              <div>
                <h3 className="text-lg font-semibold mb-2 text-gray-900">Аккаунт</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-gray-100 p-4 rounded-lg">
                    <p className="text-sm text-gray-600">Подписчики</p>
                    <p className="text-2xl font-bold text-gray-900">{accountMetrics[0]?.value.toLocaleString()}</p>
                  </div>
                  <div className="bg-gray-100 p-4 rounded-lg">
                    <p className="text-sm text-gray-600">Охват</p>
                    <p className="text-2xl font-bold text-gray-900">{accountMetrics[0]?.reach?.toLocaleString() || 'N/A'}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Post metrics */}
            <div>
              <h3 className="text-lg font-semibold mb-2 text-gray-900">Последние посты ({postMetrics.length})</h3>
              <div className="space-y-2">
                {postMetrics.slice(0, 5).map((post) => (
                  <div key={post.id} className="p-3 bg-gray-100 rounded-lg">
                    <div className="flex justify-between items-start">
                      <div className="text-sm text-gray-600">
                        {new Date(post.date).toLocaleDateString()}
                      </div>
                      <div className="text-right">
                        <div className="text-xs text-gray-900">❤️ {post.likes} 💬 {post.comments} 👁️ {post.views}</div>
                      </div>
                    </div>
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
