'use client';

import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { AppBanner } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

function toInt(value: string) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.floor(n);
}

export default function BannersPanel() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<AppBanner[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = useMemo(() => items.find((x) => x.id === selectedId) || null, [items, selectedId]);

  const [title, setTitle] = useState('');
  const [placement, setPlacement] = useState('home_hero');
  const [mediaType, setMediaType] = useState<'image' | 'video'>('image');
  const [imageUrl, setImageUrl] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const [linkUrl, setLinkUrl] = useState('');
  const [sortOrder, setSortOrder] = useState('0');
  const [isActive, setIsActive] = useState(true);

  const placementOptions = useMemo(
    () => [
      { value: 'home_hero', label: 'Главная: hero' },
      { value: 'home_stories', label: 'Главная: stories' },
      { value: 'splash', label: 'Splash / заставка' },
      { value: 'catalog_top', label: 'Каталог: верх' },
      { value: 'fashion_top', label: 'Fashion: верх' },
      { value: 'product_bottom', label: 'Товар: низ' },
      { value: 'favorites_empty', label: 'Избранное: пусто' },
    ],
    []
  );

  const mediaTypeOptions = useMemo(
    () => [
      { value: 'image', label: 'Изображение' },
      { value: 'video', label: 'Видео' },
    ],
    []
  );

  const resetForm = () => {
    setSelectedId(null);
    setTitle('');
    setPlacement('home_hero');
    setMediaType('image');
    setImageUrl('');
    setVideoUrl('');
    setLinkUrl('');
    setSortOrder('0');
    setIsActive(true);
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listAppBanners(true);
      setItems(res);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки баннеров');
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
    setPlacement(selected.placement || 'home_hero');
    setMediaType(selected.media_type || 'image');
    setImageUrl(selected.image_url || '');
    setVideoUrl(selected.video_url || '');
    setLinkUrl(selected.link_url || '');
    setSortOrder(String(selected.sort_order ?? 0));
    setIsActive(!!selected.is_active);
  }, [selectedId]);

  const onUpload = async (file: File) => {
    setSaving(true);
    setError(null);
    try {
      const { url } = await api.uploadAppAdminMedia('banner', file);
      setImageUrl(url);
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
        placement,
        media_type: mediaType,
        image_url: imageUrl,
        video_url: mediaType === 'video' && videoUrl.trim() ? videoUrl.trim() : null,
        link_url: linkUrl.trim() ? linkUrl.trim() : null,
        sort_order: toInt(sortOrder),
        is_active: isActive,
      };
      if (selectedId) {
        await api.updateAppBanner(selectedId, payload);
      } else {
        await api.createAppBanner(payload);
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
    if (!confirm('Удалить баннер?')) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteAppBanner(id);
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
          <CardTitle>Список баннеров</CardTitle>
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
            {!loading && items.length === 0 ? <div className="text-sm text-gray-600 dark:text-gray-300">Пока нет баннеров</div> : null}
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
                    <div className="text-xs text-gray-500 dark:text-gray-400">#{b.sort_order}</div>
                  </div>
                  <div className="mt-1 inline-flex rounded border border-gray-200 bg-white px-2 py-0.5 text-xs text-black dark:border-gray-700 dark:bg-white dark:text-black">
                    {b.is_active ? 'Активен' : 'Выключен'}
                  </div>
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
          <CardTitle>{selectedId ? 'Редактирование баннера' : 'Новый баннер'}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Заголовок</div>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Например: Весенняя коллекция" />
            </div>

            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Плейсмент</div>
              <div className="mt-2">
                <Select value={placement} onValueChange={(v) => setPlacement(v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Выберите плейсмент" />
                  </SelectTrigger>
                  <SelectContent>
                    {placementOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Тип баннера</div>
              <div className="mt-2">
                <Select value={mediaType} onValueChange={(v) => setMediaType(v as any)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Выберите тип" />
                  </SelectTrigger>
                  <SelectContent>
                    {mediaTypeOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Ссылка (опционально)</div>
              <Input value={linkUrl} onChange={(e) => setLinkUrl(e.target.value)} placeholder="https://... или /route" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Порядок</div>
                <Input value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} />
              </div>
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Статус</div>
                <div className="mt-2 flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
                  <span className="rounded border border-gray-200 bg-white px-2 py-0.5 text-black dark:border-gray-700 dark:bg-white dark:text-black">
                    Активен
                  </span>
                </div>
              </div>
            </div>

            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Изображение</div>
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
                <Input value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} placeholder="/static/..." />
              </div>
              {imageUrl ? (
                <div className="mt-3 overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
                  <img src={imageUrl} alt="banner" className="h-40 w-full object-cover" />
                </div>
              ) : null}
            </div>

            {mediaType === 'video' ? (
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Видео URL</div>
                <Input value={videoUrl} onChange={(e) => setVideoUrl(e.target.value)} placeholder="https://...mp4" />
              </div>
            ) : null}

            <div className="flex gap-2">
              <Button
                onClick={onSave}
                disabled={saving || !title.trim() || !imageUrl.trim() || (mediaType === 'video' && !videoUrl.trim())}
              >
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
