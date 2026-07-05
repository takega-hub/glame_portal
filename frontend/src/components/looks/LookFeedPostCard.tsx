'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { Bookmark, ChevronLeft, ChevronRight, Heart, Send, ShoppingBag } from 'lucide-react';
import type { LookFeedPost } from '@/types';
import { api } from '@/lib/api';

interface LookFeedPostCardProps {
  post: LookFeedPost;
}

function formatPrice(value: number) {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value || 0);
}

export default function LookFeedPostCard({ post }: LookFeedPostCardProps) {
  const [slide, setSlide] = useState(0);
  const [liked, setLiked] = useState(Boolean(post.liked_by_me));
  const [favorited, setFavorited] = useState(Boolean(post.favorited_by_me));
  const [likeCount, setLikeCount] = useState(post.like_count || 0);
  const [favoriteCount, setFavoriteCount] = useState(post.favorite_count || 0);
  const [busyAction, setBusyAction] = useState<'like' | 'favorite' | null>(null);

  const mediaItems = useMemo(() => {
    if (post.media_items?.length) return post.media_items.filter((item) => item.url);
    if (post.image_url) return [{ type: 'image', url: post.image_url }];
    return [];
  }, [post]);

  const currentMedia = mediaItems[slide] || mediaItems[0];

  const changeSlide = (direction: -1 | 1) => {
    if (mediaItems.length < 2) return;
    setSlide((current) => (current + direction + mediaItems.length) % mediaItems.length);
  };

  const toggleLike = async () => {
    if (busyAction) return;
    setBusyAction('like');
    try {
      const result = await api.toggleLookLike(post.id);
      setLiked(result.liked);
      setLikeCount(result.like_count);
    } finally {
      setBusyAction(null);
    }
  };

  const toggleFavorite = async () => {
    if (busyAction) return;
    setBusyAction('favorite');
    try {
      const result = await api.toggleLookFavorite(post.id);
      setFavorited(result.favorited);
      setFavoriteCount(result.favorite_count);
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <article className="border-b border-gray-200 bg-white">
      <header className="flex h-14 items-center justify-between px-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black text-xs font-semibold text-white">
            GL
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <div className="truncate text-sm font-semibold text-gray-950">glame_official</div>
              {post.is_new ? (
                <span className="shrink-0 border border-gray-950 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-gray-950">
                  Новинка
                </span>
              ) : null}
            </div>
            <div className="truncate text-xs text-gray-500">{post.style || post.mood || 'Образ GLAME'}</div>
          </div>
        </div>
        {post.source_permalink ? (
          <a
            href={post.source_permalink}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-gray-500 hover:text-gray-950"
          >
            Instagram
          </a>
        ) : null}
      </header>

      <div className="relative aspect-square bg-gray-100">
        {currentMedia?.type === 'video' ? (
          <video
            className="h-full w-full object-cover"
            src={currentMedia.url}
            poster={currentMedia.thumbnail_url || undefined}
            controls
            playsInline
          />
        ) : currentMedia?.url ? (
          <img src={currentMedia.url} alt={post.name} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-sm text-gray-500">Нет медиа</div>
        )}

        {mediaItems.length > 1 ? (
          <>
            <button
              type="button"
              onClick={() => changeSlide(-1)}
              className="absolute left-3 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-black/40 text-white"
              aria-label="Предыдущее медиа"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={() => changeSlide(1)}
              className="absolute right-3 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-black/40 text-white"
              aria-label="Следующее медиа"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
            <div className="absolute right-3 top-3 rounded-full bg-black/55 px-2 py-1 text-xs font-medium text-white">
              {slide + 1}/{mediaItems.length}
            </div>
          </>
        ) : null}
      </div>

      <div className="px-3 pb-5 pt-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={toggleLike}
              disabled={busyAction === 'like'}
              className={liked ? 'text-red-600' : 'text-gray-950'}
              aria-label="Лайк"
            >
              <Heart className="h-6 w-6" fill={liked ? 'currentColor' : 'none'} />
            </button>
            <button type="button" className="text-gray-950" aria-label="Поделиться">
              <Send className="h-6 w-6" />
            </button>
          </div>
          <button
            type="button"
            onClick={toggleFavorite}
            disabled={busyAction === 'favorite'}
            className={favorited ? 'text-gray-950' : 'text-gray-950'}
            aria-label="Сохранить образ"
          >
            <Bookmark className="h-6 w-6" fill={favorited ? 'currentColor' : 'none'} />
          </button>
        </div>

        <div className="mt-3 text-sm font-semibold text-gray-950">{likeCount} отметок “нравится”</div>
        <div className="mt-1 text-sm leading-5 text-gray-950">
          <span className="font-semibold">glame_official</span>{' '}
          <span>{post.caption || post.name}</span>
        </div>

        {post.products.length ? (
          <div className="mt-4 border-t border-gray-100 pt-3">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-semibold text-gray-950">
                <ShoppingBag className="h-4 w-4" />
                Товары в образе
              </div>
              <div className="text-xs text-gray-500">{favoriteCount} сохранений</div>
            </div>
            <div className="flex gap-3 overflow-x-auto pb-1">
              {post.products.map((product) => {
                const image = product.images?.[0];
                return (
                  <Link
                    key={product.id}
                    href={`/products/${product.id}`}
                    className="w-36 shrink-0 rounded-lg border border-gray-200 bg-white p-2 transition hover:border-gray-400"
                  >
                    <div className="aspect-square overflow-hidden rounded-md bg-gray-100">
                      {image ? (
                        <img src={image} alt={product.name} className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full items-center justify-center text-xs text-gray-400">Нет фото</div>
                      )}
                    </div>
                    <div className="mt-2 line-clamp-2 min-h-9 text-xs font-medium text-gray-950">{product.name}</div>
                    <div className="mt-1 text-xs font-semibold text-gray-950">{formatPrice(product.price)}</div>
                  </Link>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </article>
  );
}
