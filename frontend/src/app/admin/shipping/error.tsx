'use client';

import { useEffect } from 'react';

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="p-6">
      <div className="rounded-lg border border-red-200 bg-red-50 p-4">
        <div className="font-medium text-red-800">Ошибка страницы доставки</div>
        <div className="mt-1 text-sm text-red-700">{error.message || 'Неизвестная ошибка'}</div>
        <div className="mt-3 flex gap-2">
          <button
            className="rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white"
            onClick={() => reset()}
          >
            Повторить
          </button>
          <a className="rounded-md border border-red-200 bg-white px-3 py-2 text-sm" href="/admin/app">
            В админку
          </a>
        </div>
      </div>
    </div>
  );
}

