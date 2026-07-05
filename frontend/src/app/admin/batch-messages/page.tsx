'use client';

import { Suspense } from 'react';
import BatchMessageGenerator from '@/components/customers/BatchMessageGenerator';
import GenerationHistoryPanel from '@/components/customers/GenerationHistoryPanel';
import Link from 'next/link';

function BatchMessagesContent() {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <Link href="/" className="text-pink-600 hover:text-pink-700 mb-4 inline-block">
            ← Назад
          </Link>
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold text-gray-900">Массовая генерация сообщений</h1>
          </div>
        </div>

        <div className="mb-6">
          <BatchMessageGenerator />
        </div>
        <div className="mb-6">
          <GenerationHistoryPanel />
        </div>
      </div>
    </div>
  );
}

export default function BatchMessagesPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-gray-500">Загрузка...</div>}>
      <BatchMessagesContent />
    </Suspense>
  );
}

