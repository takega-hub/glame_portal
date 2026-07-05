'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface CertificateTexture {
  id: string;
  title?: string | null;
  image_url: string;
  sort_order?: number;
  is_active?: boolean;
}

export default function GiftCertificatesPanel() {
  const [items, setItems] = useState<CertificateTexture[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await api.listGiftCertificateTextures();
      setItems(rows as CertificateTexture[]);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки текстур сертификатов');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onUpload = async (file: File) => {
    setSaving(true);
    setError(null);
    try {
      await api.uploadAppAdminMedia('certificate_texture', file);
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки текстуры');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Текстуры сертификатов</CardTitle>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
          ) : null}
          <div className="flex gap-2">
            <Button onClick={load} disabled={loading || saving}>
              Обновить
            </Button>
          </div>
          <div className="mt-4 space-y-3">
            {loading ? <div className="text-sm text-gray-600 dark:text-gray-300">Загрузка...</div> : null}
            {!loading && items.length === 0 ? (
              <div className="text-sm text-gray-600 dark:text-gray-300">Пока нет загруженных текстур</div>
            ) : null}
            {items.map((item, index) => (
              <div key={item.id} className="flex items-center gap-3 rounded-md border border-gray-200 bg-white px-3 py-2 dark:border-gray-800 dark:bg-gray-950">
                <img src={item.image_url} alt={item.title || `Текстура ${index + 1}`} className="h-16 w-24 rounded object-cover" />
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-gray-900 dark:text-gray-100">{item.title || `Текстура ${index + 1}`}</div>
                  <div className="truncate text-xs text-gray-500 dark:text-gray-400">{item.image_url}</div>
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400">#{item.sort_order ?? index}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Новая текстура</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300">
              Загрузите PNG, JPG или WEBP. Новые текстуры появятся в первом шаге оформления подарочного сертификата.
            </div>
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Файл текстуры</div>
              <Input
                className="mt-1"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                disabled={saving}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) onUpload(file);
                  e.currentTarget.value = '';
                }}
              />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
