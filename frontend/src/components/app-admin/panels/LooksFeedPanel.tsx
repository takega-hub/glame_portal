'use client';

import { useEffect, useMemo, useState } from 'react';
import { Download, Eye, RefreshCw, Search } from 'lucide-react';
import { api } from '@/lib/api';
import type { InstagramPreviewItem, LookFeedPost, Product } from '@/types';

function getErrorMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail ?? error?.message;
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === 'string' ? item : item?.msg || item?.detail || JSON.stringify(item)))
      .join('; ');
  }
  if (typeof detail === 'object') {
    return detail.msg || detail.detail || JSON.stringify(detail);
  }
  return String(detail);
}

export default function LooksFeedPanel() {
  const [instagramItems, setInstagramItems] = useState<InstagramPreviewItem[]>([]);
  const [posts, setPosts] = useState<LookFeedPost[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProducts, setSelectedProducts] = useState<Record<string, string[]>>({});
  const [search, setSearch] = useState('');
  const [loadingInstagram, setLoadingInstagram] = useState(false);
  const [loadingPosts, setLoadingPosts] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyNewPosts, setOnlyNewPosts] = useState(false);
  const newPostsCount = posts.filter((post) => post.is_new).length;

  const filteredProducts = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return products.slice(0, 20);
    return products
      .filter((product) => {
        return [product.name, product.article, product.external_code, product.category]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(q));
      })
      .slice(0, 20);
  }, [products, search]);

  const visiblePosts = useMemo(
    () => (onlyNewPosts ? posts.filter((post) => post.is_new) : posts),
    [onlyNewPosts, posts]
  );

  const loadPosts = async () => {
    setLoadingPosts(true);
    setError(null);
    try {
      const data = await api.getLooksFeed({ include_drafts: true, limit: 50 });
      setPosts(data);
    } catch (e: any) {
      setError(getErrorMessage(e, 'Не удалось загрузить образы'));
    } finally {
      setLoadingPosts(false);
    }
  };

  const loadInstagram = async () => {
    setLoadingInstagram(true);
    setError(null);
    setMessage(null);
    try {
      const data = await api.previewInstagramLooks(12);
      setInstagramItems(data);
    } catch (e: any) {
      setError(getErrorMessage(e, 'Не удалось получить Instagram-посты'));
    } finally {
      setLoadingInstagram(false);
    }
  };

  const loadProducts = async () => {
    try {
      const data = await api.getProductsPaged({ limit: 100, in_stock: true });
      setProducts(Array.isArray(data.items) ? data.items : []);
    } catch {
      const data = await api.getProducts({ limit: 100 });
      setProducts(Array.isArray(data) ? data : []);
    }
  };

  useEffect(() => {
    void loadPosts();
    void loadProducts();
  }, []);

  const toggleProduct = (mediaId: string, productId: string) => {
    setSelectedProducts((current) => {
      const selected = current[mediaId] || [];
      const next = selected.includes(productId)
        ? selected.filter((id) => id !== productId)
        : [...selected, productId];
      return { ...current, [mediaId]: next };
    });
  };

  const importItem = async (item: InstagramPreviewItem, publish: boolean) => {
    setBusyId(item.instagram_media_id);
    setError(null);
    setMessage(null);
    try {
      await api.importInstagramLook({
        instagram_media_id: item.instagram_media_id,
        product_ids: selectedProducts[item.instagram_media_id] || [],
        publish,
      });
      setMessage(publish ? 'Пост импортирован и опубликован' : 'Пост импортирован как черновик');
      await loadPosts();
    } catch (e: any) {
      setError(getErrorMessage(e, 'Не удалось импортировать пост'));
    } finally {
      setBusyId(null);
    }
  };

  const publishPost = async (post: LookFeedPost, isPublished: boolean) => {
    setBusyId(post.id);
    setError(null);
    try {
      await api.publishLookFeedPost(post.id, isPublished);
      await loadPosts();
    } catch (e: any) {
      setError(getErrorMessage(e, 'Не удалось изменить статус публикации'));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-950">Instagram импорт</h2>
            <p className="mt-1 text-sm text-gray-500">Перенос постов в ленту образов с ручной привязкой товаров.</p>
          </div>
          <button
            type="button"
            onClick={() => void loadInstagram()}
            disabled={loadingInstagram}
            className="inline-flex items-center gap-2 rounded-md bg-gray-950 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            <RefreshCw className="h-4 w-4" />
            {loadingInstagram ? 'Загрузка...' : 'Получить посты'}
          </button>
        </div>

        <div className="mt-4 flex max-w-md items-center gap-2 rounded-md border border-gray-300 px-3 py-2">
          <Search className="h-4 w-4 text-gray-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full text-sm outline-none"
            placeholder="Поиск товара для привязки"
          />
        </div>

        {message ? <div className="mt-3 rounded-md bg-green-50 p-3 text-sm text-green-800">{message}</div> : null}
        {error ? <div className="mt-3 rounded-md bg-red-50 p-3 text-sm text-red-800">{error}</div> : null}

        {instagramItems.length ? (
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {instagramItems.map((item) => {
              const media = item.media_items[0];
              const selected = selectedProducts[item.instagram_media_id] || [];
              return (
                <div key={item.instagram_media_id} className="rounded-lg border border-gray-200 p-3">
                  <div className="grid gap-3 sm:grid-cols-[180px_1fr]">
                    <div className="aspect-square overflow-hidden rounded-md bg-gray-100">
                      {media?.type === 'video' ? (
                        <video src={media.url} poster={media.thumbnail_url || undefined} className="h-full w-full object-cover" />
                      ) : media?.url ? (
                        <img src={media.url} alt="" className="h-full w-full object-cover" />
                      ) : null}
                    </div>
                    <div className="min-w-0">
                      <div className="line-clamp-4 text-sm text-gray-800">{item.caption || 'Без подписи'}</div>
                      <div className="mt-2 text-xs text-gray-500">{item.media_type}</div>
                      <div className="mt-3 text-xs font-semibold text-gray-950">Товары: {selected.length}</div>
                      <div className="mt-2 flex max-h-32 flex-wrap gap-2 overflow-y-auto">
                        {filteredProducts.map((product) => (
                          <button
                            key={product.id}
                            type="button"
                            onClick={() => toggleProduct(item.instagram_media_id, product.id)}
                            className={`rounded-md border px-2 py-1 text-xs ${
                              selected.includes(product.id)
                                ? 'border-gray-950 bg-gray-950 text-white'
                                : 'border-gray-200 bg-white text-gray-700'
                            }`}
                          >
                            {product.name}
                          </button>
                        ))}
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => void importItem(item, false)}
                          disabled={busyId === item.instagram_media_id}
                          className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium"
                        >
                          <Download className="h-4 w-4" />
                          В черновик
                        </button>
                        <button
                          type="button"
                          onClick={() => void importItem(item, true)}
                          disabled={busyId === item.instagram_media_id}
                          className="inline-flex items-center gap-2 rounded-md bg-gray-950 px-3 py-2 text-sm font-medium text-white"
                        >
                          <Eye className="h-4 w-4" />
                          Опубликовать
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h2 className="text-base font-semibold text-gray-950">Публикации ленты</h2>
            <button
              type="button"
              onClick={() => setOnlyNewPosts((current) => !current)}
              className={`border px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.12em] ${
                onlyNewPosts
                  ? 'border-gray-950 bg-gray-950 text-white'
                  : 'border-gray-300 bg-white text-gray-700'
              }`}
            >
              {onlyNewPosts
                ? `Показать все (${posts.length})`
                : `Только новинки (${newPostsCount})`}
            </button>
          </div>
          <button type="button" onClick={() => void loadPosts()} className="text-sm font-medium text-gray-600">
            {loadingPosts ? 'Обновление...' : 'Обновить'}
          </button>
        </div>
        <div className="mt-4 divide-y divide-gray-100">
          {visiblePosts.map((post) => (
            <div key={post.id} className="flex items-center gap-3 py-3">
              <div className="h-16 w-16 shrink-0 overflow-hidden rounded-md bg-gray-100">
                {post.media_items?.[0]?.url ? (
                  <img src={post.media_items[0].thumbnail_url || post.media_items[0].url} alt="" className="h-full w-full object-cover" />
                ) : null}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <div className="truncate text-sm font-semibold text-gray-950">{post.name}</div>
                  {post.is_new ? (
                    <span className="shrink-0 border border-gray-950 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-gray-950">
                      Новинка
                    </span>
                  ) : null}
                </div>
                <div className="truncate text-xs text-gray-500">{post.caption || 'Без подписи'}</div>
                <div className="mt-1 text-xs text-gray-500">
                  {post.is_published ? 'Опубликован' : 'Черновик'} · {post.products.length} товаров · {post.like_count} лайков
                </div>
              </div>
              <button
                type="button"
                onClick={() => void publishPost(post, !post.is_published)}
                disabled={busyId === post.id}
                className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium"
              >
                {post.is_published ? 'Снять' : 'Опубликовать'}
              </button>
            </div>
          ))}
          {!visiblePosts.length ? (
            <div className="py-8 text-center text-sm text-gray-500">
              {onlyNewPosts ? 'Пока нет образов с пометкой «Новинка»' : 'Пока нет импортированных образов'}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
