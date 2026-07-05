'use client';

import { useEffect, useState } from 'react';
import { RefreshCw, Sparkles } from 'lucide-react';
import LookFeedPostCard from '@/components/looks/LookFeedPostCard';
import LooksStudioPage from '@/components/looks/LooksStudioPage';
import type { LookFeedPost } from '@/types';
import { api } from '@/lib/api';

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

export default function LooksPage() {
  const [mode, setMode] = useState<'feed' | 'studio'>('feed');
  const [posts, setPosts] = useState<LookFeedPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [onlyNew, setOnlyNew] = useState(false);
  const newPostsCount = posts.filter((post) => post.is_new).length;

  const loadFeed = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getLooksFeed({ limit: 30 });
      setPosts(Array.isArray(data) ? data : []);
    } catch (e: any) {
      setError(getErrorMessage(e, 'Не удалось загрузить ленту образов'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadFeed();
  }, []);

  const visiblePosts = onlyNew ? posts.filter((post) => post.is_new) : posts;

  if (mode === 'studio') {
    return (
      <div>
        <div className="sticky top-0 z-30 border-b border-gray-200 bg-white/95 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
            <div className="text-sm font-semibold text-gray-950">Студия образов</div>
            <button
              type="button"
              onClick={() => setMode('feed')}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-800 hover:bg-gray-50"
            >
              Вернуться в ленту
            </button>
          </div>
        </div>
        <LooksStudioPage />
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-white">
      <div className="sticky top-0 z-30 border-b border-gray-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[520px] items-center justify-between px-3">
          <div className="text-xl font-semibold tracking-normal text-gray-950">Образы</div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void loadFeed()}
              className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-gray-100"
              aria-label="Обновить ленту"
            >
              <RefreshCw className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={() => setMode('studio')}
              className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-gray-100"
              aria-label="Студия образов"
            >
              <Sparkles className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>

      <section className="mx-auto max-w-[520px] border-x border-gray-100">
        <div className="border-b border-gray-100 px-3 py-3">
          <button
            type="button"
            onClick={() => setOnlyNew((current) => !current)}
            className={`border px-3 py-1.5 text-xs font-medium uppercase tracking-[0.12em] ${
              onlyNew
                ? 'border-gray-950 bg-gray-950 text-white'
                : 'border-gray-300 bg-white text-gray-700'
            }`}
          >
            {onlyNew
              ? `Показать все (${posts.length})`
              : `Только новинки (${newPostsCount})`}
          </button>
        </div>
        {loading ? (
          <div className="flex min-h-[420px] items-center justify-center text-sm text-gray-500">Загрузка ленты...</div>
        ) : error ? (
          <div className="p-5 text-sm text-red-700">{error}</div>
        ) : visiblePosts.length === 0 ? (
          <div className="flex min-h-[420px] flex-col items-center justify-center px-6 text-center">
            <div className="text-base font-semibold text-gray-950">
              {onlyNew ? 'Пока нет опубликованных новинок' : 'Пока нет опубликованных образов'}
            </div>
            <div className="mt-2 text-sm leading-6 text-gray-500">
              {onlyNew
                ? 'Отметьте образ как «Новинка», чтобы он появился в этом списке.'
                : 'Импортируйте посты из Instagram или опубликуйте готовые образы в админке.'}
            </div>
            <button
              type="button"
              onClick={() => setMode('studio')}
              className="mt-5 rounded-md bg-gray-950 px-4 py-2 text-sm font-medium text-white"
            >
              Открыть студию
            </button>
          </div>
        ) : (
          visiblePosts.map((post) => <LookFeedPostCard key={post.id} post={post} />)
        )}
      </section>
    </main>
  );
}
