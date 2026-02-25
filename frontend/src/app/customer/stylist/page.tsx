'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import Link from 'next/link';
import ChatInterface from '@/components/chat/ChatInterface';

export default function CustomerStylistPage() {
  const { user, isAuthenticated, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.push('/login');
    }
  }, [loading, isAuthenticated, router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Загрузка...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <Link href="/customer" className="text-pink-600 hover:text-pink-700 mb-4 inline-block">
            ← Назад в личный кабинет
          </Link>
          <h1 className="text-3xl font-bold text-gray-900">AI Стилист</h1>
          <p className="mt-2 text-gray-600">
            Персональная консультация с учетом ваших предпочтений и истории покупок
          </p>
        </div>

        {/* Быстрые действия */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <button className="bg-white rounded-lg shadow p-4 text-left hover:shadow-lg transition-shadow">
            <h3 className="font-semibold text-gray-900 mb-1">Подобрать образ</h3>
            <p className="text-sm text-gray-500">Для особого случая</p>
          </button>
          <button className="bg-white rounded-lg shadow p-4 text-left hover:shadow-lg transition-shadow">
            <h3 className="font-semibold text-gray-900 mb-1">Рекомендации по истории</h3>
            <p className="text-sm text-gray-500">На основе ваших покупок</p>
          </button>
          <button className="bg-white rounded-lg shadow p-4 text-left hover:shadow-lg transition-shadow">
            <h3 className="font-semibold text-gray-900 mb-1">Что подарить</h3>
            <p className="text-sm text-gray-500">Идеи для подарков</p>
          </button>
        </div>

        {/* Чат */}
        <div className="bg-white rounded-lg shadow">
          <ChatInterface userId={user?.id} />
        </div>
      </div>
    </div>
  );
}
