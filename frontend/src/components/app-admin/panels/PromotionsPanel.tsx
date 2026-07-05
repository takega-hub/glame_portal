'use client';

import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { AppPromotion, AppPublicationStatus } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';

const STATUSES: AppPublicationStatus[] = ['draft', 'published', 'archived'];

export default function PromotionsPanel() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<AppPromotion[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('');

  const selected = useMemo(() => items.find((x) => x.id === selectedId) || null, [items, selectedId]);

  const [title, setTitle] = useState('');
  const [bannerImageUrl, setBannerImageUrl] = useState('');
  const [body, setBody] = useState('');
  const [startsAt, setStartsAt] = useState('');
  const [endsAt, setEndsAt] = useState('');
  const [status, setStatus] = useState<AppPublicationStatus>('draft');

  const resetForm = () => {
    setSelectedId(null);
    setTitle('');
    setBannerImageUrl('');
    setBody('');
    setStartsAt('');
    setEndsAt('');
    setStatus('draft');
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listAppPromotions(filterStatus || undefined);
      setItems(res);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки акций');
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
    setBannerImageUrl(selected.banner_image_url || '');
    setBody(selected.body || '');
    setStartsAt(selected.starts_at || '');
    setEndsAt(selected.ends_at || '');
    setStatus((selected.status as AppPublicationStatus) || 'draft');
  }, [selectedId]);

  const onUpload = async (file: File) => {
    setSaving(true);
    setError(null);
    try {
      const { url } = await api.uploadAppAdminMedia('promotion', file);
      setBannerImageUrl(url);
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
        banner_image_url: bannerImageUrl.trim() ? bannerImageUrl.trim() : null,
        body,
        starts_at: startsAt.trim() ? startsAt.trim() : null,
        ends_at: endsAt.trim() ? endsAt.trim() : null,
        status,
      };
      if (selectedId) {
        await api.updateAppPromotion(selectedId, payload);
      } else {
        await api.createAppPromotion(payload);
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
    if (!confirm('Удалить акцию?')) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteAppPromotion(id);
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
          <CardTitle>Список акций</CardTitle>
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
            {!loading && items.length === 0 ? <div className="text-sm text-gray-600">Пока нет акций</div> : null}
            {items.map((p) => (
              <div
                key={p.id}
                className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
                  p.id === selectedId
                    ? 'border-blue-400 bg-blue-50'
                    : 'border-gray-300 bg-white'
                }`}
              >
                <button onClick={() => setSelectedId(p.id)} className="flex-1 text-left">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-gray-900">{p.title}</div>
                    <div className="rounded border border-gray-300 bg-white px-2 py-0.5 text-xs text-black">
                      {p.status}
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-gray-600 line-clamp-1">{p.body}</div>
                </button>
                <Button variant="destructive" onClick={() => onDelete(p.id)} disabled={saving}>
                  Удалить
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{selectedId ? 'Редактирование акции' : 'Новая акция'}</CardTitle>
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

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <div className="text-xs text-gray-700">Начало (ISO)</div>
                <Input value={startsAt} onChange={(e) => setStartsAt(e.target.value)} placeholder="2026-03-25T00:00:00+03:00" />
              </div>
              <div>
                <div className="text-xs text-gray-700">Окончание (ISO)</div>
                <Input value={endsAt} onChange={(e) => setEndsAt(e.target.value)} placeholder="2026-04-01T23:59:59+03:00" />
              </div>
            </div>

            <div>
              <div className="text-xs text-gray-700">Баннер (опционально)</div>
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
                <Input value={bannerImageUrl} onChange={(e) => setBannerImageUrl(e.target.value)} placeholder="/static/..." />
              </div>
              {bannerImageUrl ? (
                <div className="mt-3 overflow-hidden rounded-md border border-gray-300">
                  <img src={bannerImageUrl} alt="promo" className="h-40 w-full object-cover" />
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