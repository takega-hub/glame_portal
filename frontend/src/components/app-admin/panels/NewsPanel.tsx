'use client';

import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { AppNews, AppPublicationStatus } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';

const STATUSES: AppPublicationStatus[] = ['draft', 'published', 'archived'];

export default function NewsPanel() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<AppNews[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('');

  const selected = useMemo(() => items.find((x) => x.id === selectedId) || null, [items, selectedId]);

  const [title, setTitle] = useState('');
  const [previewImageUrl, setPreviewImageUrl] = useState('');
  const [body, setBody] = useState('');
  const [publishedAt, setPublishedAt] = useState('');
  const [status, setStatus] = useState<AppPublicationStatus>('draft');

  const resetForm = () => {
    setSelectedId(null);
    setTitle('');
    setPreviewImageUrl('');
    setBody('');
    setPublishedAt('');
    setStatus('draft');
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listAppNews(filterStatus || undefined);
      setItems(res);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки новостей');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [filterStatus]);

  useEffect(() => {
    if (!selected) return;
    setTitle(selected.title || '');
    setPreviewImageUrl(selected.preview_image_url || '');
    setBody(selected.body || '');
    setPublishedAt(selected.published_at || '');
    setStatus((selected.status as AppPublicationStatus) || 'draft');
  }, [selectedId]);

  const onUpload = async (file: File) => {
    setSaving(true);
    setError(null);
    try {
      const { url } = await api.uploadAppAdminMedia('news', file);
      setPreviewImageUrl(url);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки изображения');
    } finally {
      setSaving(false);
    }
  };

  const onSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        title,
        preview_image_url: previewImageUrl.trim() ? previewImageUrl.trim() : null,
        body,
        published_at: publishedAt.trim() ? publishedAt.trim() : null,
        status,
      };
      if (selectedId) {
        await api.updateAppNews(selectedId, payload);
      } else {
        await api.createAppNews(payload);
      }
      await load();
      resetForm();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (id: string) => {
    if (!confirm('Удалить новость?')) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteAppNews(id);
      if (selectedId === id) resetForm();
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка удаления');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Список новостей</CardTitle>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
          ) : null}

          <div className="flex flex-wrap items-end gap-2">
            <div>
              <div className="text-xs text-gray-700">Статус</div>
              <select
                className="mt-1 h-10 rounded-md border border-gray-300 bg-white px-3 text-sm text-black"
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
              >
                <option value="">Все</option>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <Button onClick={load} disabled={loading || saving}>
              Обновить
            </Button>
            <Button variant="outline" onClick={resetForm} disabled={saving}>
              Новая
            </Button>
          </div>

          <div className="mt-4 space-y-2">
            {loading ? <div className="text-sm text-gray-600">Загрузка…</div> : null}
            {!loading && items.length === 0 ? <div className="text-sm text-gray-600">Пока нет новостей</div> : null}
            {items.map((n) => (
              <div
                key={n.id}
                className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
                  n.id === selectedId
                    ? 'border-blue-400 bg-blue-50'
                    : 'border-gray-300 bg-white'
                }`}
              >
                <button onClick={() => setSelectedId(n.id)} className="flex-1 text-left">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-gray-900">{n.title}</div>
                    <div className="rounded border border-gray-300 bg-white px-2 py-0.5 text-xs text-black">
                      {n.status}
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-gray-600 line-clamp-1">{n.body}</div>
                </button>
                <Button variant="destructive" onClick={() => onDelete(n.id)} disabled={saving}>
                  Удалить
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{selectedId ? 'Редактирование новости' : 'Новая новость'}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div>
              <div className="text-xs text-gray-700">Заголовок</div>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>

            <div>
              <div className="text-xs text-gray-700">Статус</div>
              <select
                className="mt-1 h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-black"
                value={status}
                onChange={(e) => setStatus(e.target.value as AppPublicationStatus)}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <div className="text-xs text-gray-700">Дата публикации (ISO, опционально)</div>
              <Input value={publishedAt} onChange={(e) => setPublishedAt(e.target.value)} placeholder="2026-03-25T12:00:00+03:00" />
            </div>

            <div>
              <div className="text-xs text-gray-700">Превью-изображение (опционально)</div>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) onUpload(f);
                  }}
                  disabled={saving}
                />
                <Input value={previewImageUrl} onChange={(e) => setPreviewImageUrl(e.target.value)} placeholder="/static/..." />
              </div>
              {previewImageUrl ? (
                <div className="mt-3 overflow-hidden rounded-md border border-gray-300">
                  <img src={previewImageUrl} alt="news" className="h-40 w-full object-cover" />
                </div>
              ) : null}
            </div>

            <div>
              <div className="text-xs text-gray-700">Текст</div>
              <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={10} />
            </div>

            <div className="flex gap-2">
              <Button onClick={onSave} disabled={saving || !title.trim() || !body.trim()}>
                Сохранить
              </Button>
              <Button variant="outline" onClick={resetForm} disabled={saving}>
                Отменить
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}