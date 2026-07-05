'use client';

import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { AppLookbook } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';

function safeParseItems(raw: string): { ok: true; items: any[] } | { ok: false; error: string } {
  const trimmed = (raw || '').trim();
  if (!trimmed) return { ok: true, items: [] };
  try {
    const parsed = JSON.parse(trimmed);
    if (!Array.isArray(parsed)) return { ok: false, error: 'items должен быть JSON-массивом' };
    return { ok: true, items: parsed };
  } catch (e: any) {
    return { ok: false, error: e?.message || 'Не удалось распарсить JSON' };
  }
}

export default function LookbooksPanel() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<AppLookbook[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = useMemo(() => items.find((x) => x.id === selectedId) || null, [items, selectedId]);

  const [title, setTitle] = useState('');
  const [coverImageUrl, setCoverImageUrl] = useState('');
  const [description, setDescription] = useState('');
  const [isPublished, setIsPublished] = useState(false);
  const [itemsJson, setItemsJson] = useState('[]');

  const resetForm = () => {
    setSelectedId(null);
    setTitle('');
    setCoverImageUrl('');
    setDescription('');
    setIsPublished(false);
    setItemsJson('[]');
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listAppLookbooks(true);
      setItems(res);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки лукбуков');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!selected) return;
    setTitle(selected.title || '');
    setCoverImageUrl(selected.cover_image_url || '');
    setDescription(selected.description || '');
    setIsPublished(!!selected.is_published);
    setItemsJson(JSON.stringify(selected.items || [], null, 2));
  }, [selectedId]);

  const onUpload = async (file: File) => {
    setSaving(true);
    setError(null);
    try {
      const { url } = await api.uploadAppAdminMedia('lookbook', file);
      setCoverImageUrl(url);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки обложки');
    } finally {
      setSaving(false);
    }
  };

  const onSave = async () => {
    const parsed = safeParseItems(itemsJson);
    if (!parsed.ok) {
      setError(parsed.error);
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const payload = {
        title,
        cover_image_url: coverImageUrl,
        description: description.trim() ? description.trim() : null,
        is_published: isPublished,
        items: parsed.items,
      };
      if (selectedId) {
        await api.updateAppLookbook(selectedId, payload);
      } else {
        await api.createAppLookbook(payload);
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
    if (!confirm('Удалить лукбук?')) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteAppLookbook(id);
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
          <CardTitle>Список лукбуков</CardTitle>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
          ) : null}
          <div className="flex gap-2">
            <Button onClick={load} disabled={loading || saving}>
              Обновить
            </Button>
            <Button variant="outline" onClick={resetForm} disabled={saving}>
              Новый
            </Button>
          </div>

          <div className="mt-4 space-y-2">
            {loading ? <div className="text-sm text-gray-600 dark:text-gray-300">Загрузка…</div> : null}
            {!loading && items.length === 0 ? <div className="text-sm text-gray-600 dark:text-gray-300">Пока нет лукбуков</div> : null}
            {items.map((b) => (
              <div
                key={b.id}
                className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
                  b.id === selectedId
                    ? 'border-blue-300 bg-blue-50 dark:border-blue-900 dark:bg-blue-950'
                    : 'border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950'
                }`}
              >
                <button onClick={() => setSelectedId(b.id)} className="flex-1 text-left">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-gray-900 dark:text-gray-100">{b.title}</div>
                    <div className="rounded border border-gray-200 bg-white px-2 py-0.5 text-xs text-black dark:border-gray-700 dark:bg-white dark:text-black">
                      {b.is_published ? 'Опубликован' : 'Черновик'}
                    </div>
                  </div>
                  {b.description ? <div className="mt-1 text-xs text-gray-500 dark:text-gray-400 line-clamp-1">{b.description}</div> : null}
                </button>
                <Button variant="destructive" onClick={() => onDelete(b.id)} disabled={saving}>
                  Удалить
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{selectedId ? 'Редактирование лукбука' : 'Новый лукбук'}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Название</div>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Например: Summer 2026" />
            </div>

            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Описание (опционально)</div>
              <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
            </div>

            <div className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={isPublished} onChange={(e) => setIsPublished(e.target.checked)} />
              <span className="rounded border border-gray-200 bg-white px-2 py-0.5 text-black dark:border-gray-700 dark:bg-white dark:text-black">
                Опубликован
              </span>
            </div>

            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Обложка</div>
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
                <Input value={coverImageUrl} onChange={(e) => setCoverImageUrl(e.target.value)} placeholder="/static/..." />
              </div>
              {coverImageUrl ? (
                <div className="mt-3 overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
                  <img src={coverImageUrl} alt="cover" className="h-40 w-full object-cover" />
                </div>
              ) : null}
            </div>

            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Элементы лукбука (JSON массив)</div>
              <Textarea value={itemsJson} onChange={(e) => setItemsJson(e.target.value)} rows={10} />
              <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Пример: {`[{"image_url":"/static/...","product_id":"<uuid>","caption":"..."}]`}
              </div>
            </div>

            <div className="flex gap-2">
              <Button onClick={onSave} disabled={saving || !title.trim() || !coverImageUrl.trim()}>
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
