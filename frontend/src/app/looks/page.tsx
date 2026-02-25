'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Look, LookWithProducts } from '@/types';
import LookCard from '@/components/looks/LookCard';
import LookGenerator from '@/components/looks/LookGenerator';
import PhotoTryOn from '@/components/looks/PhotoTryOn';

export default function LooksPage() {
  const [looks, setLooks] = useState<Look[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'list' | 'generate' | 'tryon'>('list');
  const [selectedLookId, setSelectedLookId] = useState<string | undefined>();

  const loadLooks = () => {
    setLoading(true);
    setError(null);

    api
      .getLooks({ limit: 100 })
      .then((data) => {
        setLooks(Array.isArray(data) ? data : []);
      })
      .catch((e: any) => {
        const status = e?.response?.status;
        const detail = e?.response?.data?.detail;
        setError(detail || (status ? `Ошибка загрузки (HTTP ${status})` : 'Не удалось загрузить образы'));
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    loadLooks();
  }, []);

  const handleLookGenerated = (look: LookWithProducts) => {
    loadLooks();
    setActiveTab('list');
  };

  const handleTryOnClick = (lookId: string) => {
    setSelectedLookId(lookId);
    setActiveTab('tryon');
  };

  const handleTryOnComplete = () => {
    loadLooks();
  };

  return (
    <main className="min-h-screen bg-concrete-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-concrete-900">Образы</h1>
          <p className="mt-2 text-concrete-600">
            Готовые образы и стилистические решения от GLAME
          </p>
        </div>

        {/* Табы */}
        <div className="mb-6 border-b border-concrete-200">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('list')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'list'
                  ? 'border-gold-500 text-gold-600'
                  : 'border-transparent text-concrete-700 hover:text-concrete-900 hover:border-concrete-300'
              }`}
            >
              Все образы
            </button>
            <button
              onClick={() => setActiveTab('generate')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'generate'
                  ? 'border-gold-500 text-gold-600'
                  : 'border-transparent text-concrete-700 hover:text-concrete-900 hover:border-concrete-300'
              }`}
            >
              Генерация образа
            </button>
            <button
              onClick={() => setActiveTab('tryon')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'tryon'
                  ? 'border-gold-500 text-gold-600'
                  : 'border-transparent text-concrete-700 hover:text-concrete-900 hover:border-concrete-300'
              }`}
            >
              Примерка на фото
            </button>
          </nav>
        </div>

        {/* Контент табов */}
        {activeTab === 'list' && (
          <>
            {loading ? (
              <div className="bg-white rounded-lg shadow-concrete p-8 text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gold-500 mx-auto"></div>
                <p className="text-concrete-500 mt-4">Загрузка образов...</p>
              </div>
            ) : error ? (
              <div className="bg-white rounded-lg shadow-concrete p-8">
                <p className="text-red-700 font-medium">Ошибка</p>
                <p className="text-red-600 text-sm mt-1">{error}</p>
              </div>
            ) : looks.length === 0 ? (
              <div className="bg-white rounded-lg shadow-concrete p-8 text-center">
                <p className="text-concrete-500 text-lg">
                  Образы будут доступны после создания через AI Stylist или генерацию
                </p>
                <p className="text-concrete-400 text-sm mt-2">
                  Используйте вкладку "Генерация образа" для создания персонализированных образов
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {looks.map((look) => (
                  <LookCard
                    key={look.id}
                    look={look}
                    showTryOn={true}
                    onTryOnClick={handleTryOnClick}
                  />
                ))}
              </div>
            )}
          </>
        )}

        {activeTab === 'generate' && (
          <LookGenerator onLookGenerated={handleLookGenerated} />
        )}

        {activeTab === 'tryon' && (
          <PhotoTryOn lookId={selectedLookId} onTryOnComplete={handleTryOnComplete} />
        )}
      </div>
    </main>
  );
}
