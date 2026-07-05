'use client';

import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { AppStore } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

function toInt(value: string) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.floor(n);
}

function block5ImageRoleLabel(index: number) {
  switch (index) {
    case 0:
      return 'Карточка Home';
    case 1:
      return 'Hero пространства';
    case 2:
      return 'Галерея main';
    case 3:
      return 'Галерея 01';
    case 4:
      return 'Галерея 02';
    default:
      return `Доп. фото #${index + 1}`;
  }
}

function isBlock5Space(city: string, title: string) {
  const normalized = `${city} ${title}`.trim().toLowerCase();
  return normalized.includes('ялт') || normalized.includes('симфер');
}

export default function StoresPanel() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<AppStore[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = useMemo(() => items.find((x) => x.id === selectedId) || null, [items, selectedId]);

  const [city, setCity] = useState('');
  const [title, setTitle] = useState('');
  const [address, setAddress] = useState('');
  const [workingHours, setWorkingHours] = useState('');
  const [phone, setPhone] = useState('');
  const [comment, setComment] = useState('');
  const [imageUrl, setImageUrl] = useState('');
  const [imageUrls, setImageUrls] = useState('');
  const [draggedImageUrl, setDraggedImageUrl] = useState<string | null>(null);
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [sortOrder, setSortOrder] = useState('0');
  const [isActive, setIsActive] = useState(true);

  const resetForm = () => {
    setSelectedId(null);
    setCity('');
    setTitle('');
    setAddress('');
    setWorkingHours('');
    setPhone('');
    setComment('');
    setImageUrl('');
    setImageUrls('');
    setLatitude('');
    setLongitude('');
    setSortOrder('0');
    setIsActive(true);
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listAppStores(true);
      setItems(res);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки магазинов');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!selected) return;
    setCity(selected.city || '');
    setTitle(selected.title || '');
    setAddress(selected.address || '');
    setWorkingHours(selected.working_hours || '');
    setPhone(selected.phone || '');
    setComment(selected.comment || '');
    setImageUrl(selected.image_url || selected.image_urls?.[0] || '');
    setImageUrls((selected.image_urls || []).join('\n'));
    setLatitude(selected.latitude == null ? '' : String(selected.latitude));
    setLongitude(selected.longitude == null ? '' : String(selected.longitude));
    setSortOrder(String(selected.sort_order ?? 0));
    setIsActive(!!selected.is_active);
  }, [selected]);

  const parseImageUrls = (value: string) =>
    Array.from(
      new Set(
        value
          .split('\n')
          .map((item) => item.trim())
          .filter(Boolean)
      )
    );

  const setGalleryUrls = (urls: string[]) => {
    const normalized = Array.from(new Set(urls.map((item) => item.trim()).filter(Boolean)));
    setImageUrls(normalized.join('\n'));
    setImageUrl(normalized[0] || '');
  };

  const galleryUrls = parseImageUrls(imageUrls);
  const requiresBlock5Photos = isBlock5Space(city, title);
  const missingBlock5Photos = requiresBlock5Photos ? Math.max(0, 5 - galleryUrls.length) : 0;
  const block5ValidationMessage =
    missingBlock5Photos > 0
      ? `Для пространства GLAME нужно еще ${missingBlock5Photos} фото из 5 обязательных: карточка Home, Hero, Галерея main, Галерея 01, Галерея 02.`
      : null;

  const handleSetPrimaryImage = (url: string) => {
    const next = [url, ...galleryUrls.filter((item) => item !== url)];
    setGalleryUrls(next);
  };

  const handleRemoveGalleryImage = (url: string) => {
    const next = galleryUrls.filter((item) => item !== url);
    setGalleryUrls(next);
    if (imageUrl.trim() === url) {
      setImageUrl(next[0] || '');
    }
  };

  const handleMoveGalleryImage = (fromUrl: string, toUrl: string) => {
    if (!fromUrl || !toUrl || fromUrl === toUrl) return;
    const next = [...galleryUrls];
    const fromIndex = next.indexOf(fromUrl);
    const toIndex = next.indexOf(toUrl);
    if (fromIndex === -1 || toIndex === -1) return;
    const [moved] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, moved);
    setGalleryUrls(next);
  };

  const onUpload = async (files: FileList | File[]) => {
    setSaving(true);
    setError(null);
    try {
      const uploadedUrls: string[] = [];
      for (const file of Array.from(files)) {
        const { url } = await api.uploadAppAdminMedia('store', file);
        uploadedUrls.push(url);
      }
      if (uploadedUrls.length) {
        const next = [...galleryUrls, ...uploadedUrls];
        setGalleryUrls(next);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки фото');
    } finally {
      setSaving(false);
    }
  };

  const onSave = async () => {
    if (block5ValidationMessage) {
      setError(block5ValidationMessage);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const normalizedImageUrls = galleryUrls;
      const payload = {
        city,
        title,
        address,
        working_hours: workingHours.trim() ? workingHours.trim() : null,
        phone: phone.trim() ? phone.trim() : null,
        comment: comment.trim() ? comment.trim() : null,
        image_url: imageUrl.trim() ? imageUrl.trim() : normalizedImageUrls[0] || null,
        image_urls: normalizedImageUrls,
        latitude: latitude.trim() ? Number(latitude) : null,
        longitude: longitude.trim() ? Number(longitude) : null,
        sort_order: toInt(sortOrder),
        is_active: isActive,
      };
      if (selectedId) {
        await api.updateAppStore(selectedId, payload);
      } else {
        await api.createAppStore(payload);
      }
      await load();
      resetForm();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка сохранения магазина');
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (id: string) => {
    if (!confirm('Удалить магазин?')) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteAppStore(id);
      if (selectedId === id) resetForm();
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка удаления магазина');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Магазины в приложении</CardTitle>
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
            {!loading && items.length === 0 ? <div className="text-sm text-gray-600 dark:text-gray-300">Пока нет магазинов</div> : null}
            {items.map((store) => (
              <div
                key={store.id}
                className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
                  store.id === selectedId
                    ? 'border-blue-300 bg-blue-50 dark:border-blue-900 dark:bg-blue-950'
                    : 'border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950'
                }`}
              >
                {(store.image_urls?.[0] || store.image_url) ? (
                  <img src={store.image_urls?.[0] || store.image_url || ''} alt={store.title} className="h-16 w-20 rounded object-cover" />
                ) : (
                  <div className="flex h-16 w-20 items-center justify-center rounded bg-gray-100 text-xs text-gray-500 dark:bg-gray-900">
                    GLAME
                  </div>
                )}
                <button onClick={() => setSelectedId(store.id)} className="flex-1 text-left">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-gray-900 dark:text-gray-100">{store.title}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">#{store.sort_order}</div>
                  </div>
                  <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">{store.city}</div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{store.address}</div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    Фото: {store.image_urls?.length || (store.image_url ? 1 : 0)}
                  </div>
                  <div className="mt-2 inline-flex rounded border border-gray-200 bg-white px-2 py-0.5 text-xs text-black dark:border-gray-700 dark:bg-white dark:text-black">
                    {store.is_active ? 'Активен' : 'Выключен'}
                  </div>
                </button>
                <Button variant="destructive" onClick={() => onDelete(store.id)} disabled={saving}>
                  Удалить
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{selectedId ? 'Редактирование магазина' : 'Новый магазин'}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Город</div>
                <Input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Ялта" />
              </div>
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Название</div>
                <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="GLAME Yalta" />
              </div>
            </div>

            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Адрес</div>
              <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Набережная имени Ленина, 18" />
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Время работы</div>
                <Input value={workingHours} onChange={(e) => setWorkingHours(e.target.value)} placeholder="Ежедневно 10:00–22:00" />
              </div>
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Телефон</div>
                <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+7 ..." />
              </div>
            </div>

            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Комментарий</div>
              <Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={4} placeholder="Короткое описание магазина или ориентир" />
            </div>

            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-xs leading-5 text-gray-600 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300">
              Для блока «Пространства GLAME» порядок фото в галерее важен:
              <br />
              1. фото карточки на главной
              <br />
              2. hero-фото страницы пространства
              <br />
              3. главное фото галереи
              <br />
              4. галерея 01
              <br />
              5. галерея 02
            </div>

            {galleryUrls.length ? (
              <div className="rounded-md border border-gray-200 bg-white p-3 text-xs leading-5 text-gray-600 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300">
                <div className="mb-2 font-medium text-gray-900 dark:text-gray-100">Структура, которая уйдет в API</div>
                <div>`card_image_url`: {galleryUrls[0] || '—'}</div>
                <div>`hero_image_url`: {galleryUrls[1] || galleryUrls[0] || '—'}</div>
                <div>`gallery_image_urls`: [{[galleryUrls[2], galleryUrls[3], galleryUrls[4]].filter(Boolean).join(', ') || '—'}]</div>
              </div>
            ) : null}

            {block5ValidationMessage ? (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
                {block5ValidationMessage}
              </div>
            ) : null}

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Широта</div>
                <Input value={latitude} onChange={(e) => setLatitude(e.target.value)} placeholder="44.4952" />
              </div>
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Долгота</div>
                <Input value={longitude} onChange={(e) => setLongitude(e.target.value)} placeholder="34.1663" />
              </div>
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
              <div className="text-xs text-gray-500 dark:text-gray-400">Фото магазина</div>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <input
                  type="file"
                  multiple
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(e) => {
                    const files = e.target.files;
                    if (files?.length) onUpload(files);
                  }}
                  disabled={saving}
                />
                <Input value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} placeholder="/static/..." />
              </div>
              <div className="mt-3">
                <div className="text-xs text-gray-500 dark:text-gray-400">Галерея магазина, по одному URL на строку</div>
                <Textarea
                  value={imageUrls}
                  onChange={(e) => setGalleryUrls(parseImageUrls(e.target.value))}
                  rows={5}
                  placeholder={"/static/app_admin_media/store/first.jpg\n/static/app_admin_media/store/second.jpg"}
                />
              </div>
              {galleryUrls.length ? (
                <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3">
                  {galleryUrls.map((url, index) => (
                    <div
                      key={url}
                      draggable
                      onDragStart={() => setDraggedImageUrl(url)}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        if (draggedImageUrl) {
                          handleMoveGalleryImage(draggedImageUrl, url);
                        }
                        setDraggedImageUrl(null);
                      }}
                      onDragEnd={() => setDraggedImageUrl(null)}
                      className={`overflow-hidden rounded-md border ${
                        draggedImageUrl === url
                          ? 'border-blue-400 opacity-70'
                          : 'border-gray-200 dark:border-gray-800'
                      }`}
                    >
                      <img src={url} alt="store" className="h-36 w-full object-cover" />
                      <div className="border-t border-gray-200 bg-white p-2 dark:border-gray-800 dark:bg-gray-950">
                        <div className="mb-2 inline-flex rounded border border-gray-200 bg-gray-50 px-2 py-1 text-[11px] text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200">
                          {block5ImageRoleLabel(index)}
                        </div>
                        <div className="mb-2 flex items-center justify-between gap-2 text-xs text-gray-500 dark:text-gray-400">
                          <span>{index === 0 ? 'Главное фото' : `Фото #${index + 1}`}</span>
                          <span>Перетащите для сортировки</span>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            className="h-8 text-xs"
                            onClick={() => handleSetPrimaryImage(url)}
                            disabled={index === 0}
                          >
                            Сделать главным
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            className="h-8 text-xs text-red-600"
                            onClick={() => handleRemoveGalleryImage(url)}
                          >
                            Удалить
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : imageUrl ? (
                <div className="mt-3 overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
                  <img src={imageUrl} alt="store" className="h-56 w-full object-cover" />
                </div>
              ) : null}
            </div>

            <div className="flex gap-2">
              <Button onClick={onSave} disabled={saving || !city.trim() || !title.trim() || !address.trim() || !!block5ValidationMessage}>
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
