'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { LookWithProducts } from '@/types';
import LookCard from './LookCard';

interface LookGeneratorProps {
  onLookGenerated?: (look: LookWithProducts) => void;
  selectedDigitalModel?: string;
}

export default function LookGenerator({ onLookGenerated, selectedDigitalModel }: LookGeneratorProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generatedLook, setGeneratedLook] = useState<LookWithProducts | null>(null);
  const [formData, setFormData] = useState({
    style: '',
    mood: '',
    persona: '',
    user_request: '',
    generate_image: true,
    use_default_model: false,
  });

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setGeneratedLook(null);

    try {
      const result = await api.generateLook({
        style: formData.style || undefined,
        mood: formData.mood || undefined,
        persona: formData.persona || undefined,
        user_request: formData.user_request || undefined,
        generate_image: formData.generate_image,
        use_default_model: formData.use_default_model,
        digital_model: selectedDigitalModel,
      });

      setGeneratedLook(result as LookWithProducts);
      if (onLookGenerated) {
        onLookGenerated(result as LookWithProducts);
      }
    } catch (e: any) {
      let errorMessage = 'Ошибка при генерации образа';
      
      // Обработка таймаутов
      if (e?.code === 'ECONNABORTED' || e?.message?.includes('timeout') || e?.message?.includes('время')) {
        errorMessage = 'Генерация образа занимает больше времени, чем ожидалось. Пожалуйста, подождите - образ может быть создан в фоновом режиме. Проверьте список образов через несколько минут.';
      } else if (e?.response?.status === 500) {
        // Ошибка сервера - может быть таймаут на сервере
        const detail = e?.response?.data?.detail || '';
        if (detail.includes('timeout') || detail.includes('Timeout') || detail.includes('время')) {
          errorMessage = 'Генерация образа занимает больше времени, чем ожидалось. Пожалуйста, подождите - образ может быть создан в фоновом режиме. Проверьте список образов через несколько минут.';
        } else if (e?.response?.data?.detail) {
          errorMessage = typeof e.response.data.detail === 'string' 
            ? e.response.data.detail 
            : JSON.stringify(e.response.data.detail);
        }
      } else if (e?.response?.data?.detail) {
        errorMessage = typeof e.response.data.detail === 'string' 
          ? e.response.data.detail 
          : JSON.stringify(e.response.data.detail);
      } else if (e?.message) {
        errorMessage = typeof e.message === 'string' ? e.message : String(e.message);
      }
      
      setError(errorMessage);
      console.error('Ошибка при генерации образа:', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-4">Генерация образа AI</h2>
      
      <div className="space-y-4">
        {selectedDigitalModel && (
          <div className="rounded-md border border-gold-200 bg-gold-50 px-3 py-2 text-sm text-gold-900">
            Генерация выполняется на цифровой модели: <span className="font-semibold">{selectedDigitalModel}</span>
          </div>
        )}
        <div>
          <label className="block text-sm font-medium text-gray-900 mb-1">
            Описание запроса
          </label>
          <textarea
            value={formData.user_request}
            onChange={(e) => setFormData({ ...formData, user_request: e.target.value })}
            placeholder="Например: образ для романтического ужина, деловой стиль для офиса..."
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
            rows={3}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-1">
              Стиль
            </label>
            <select
              value={formData.style}
              onChange={(e) => setFormData({ ...formData, style: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
            >
              <option value="">Любой</option>
              <option value="романтичный">Романтичный</option>
              <option value="деловой">Деловой</option>
              <option value="повседневный">Повседневный</option>
              <option value="вечерний">Вечерний</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-900 mb-1">
              Настроение
            </label>
            <select
              value={formData.mood}
              onChange={(e) => setFormData({ ...formData, mood: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
            >
              <option value="">Любое</option>
              <option value="романтичный вечер">Романтичный вечер</option>
              <option value="уверенный день">Уверенный день</option>
              <option value="праздничный">Праздничный</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-900 mb-1">
              Персона
            </label>
            <select
              value={formData.persona}
              onChange={(e) => setFormData({ ...formData, persona: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
            >
              <option value="">Автоопределение</option>
              <option value="fashion_girl">Fashion Girl</option>
              <option value="status_woman">Status Woman</option>
              <option value="romantic">Romantic</option>
              <option value="minimalist">Minimalist</option>
            </select>
          </div>
        </div>

        <button
          onClick={handleGenerate}
          disabled={loading}
          className="w-full px-4 py-2 bg-gold-500 text-white rounded-lg hover:bg-gold-600 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <div className="animate-spin rounded-full h-5 w-5 border-2 border-white border-t-transparent"></div>
              <span>Генерация образа...</span>
            </>
          ) : (
            'Сгенерировать образ'
          )}
        </button>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-md p-3">
            <p className="text-red-700 text-sm">{error}</p>
          </div>
        )}

        {loading && (
          <div className="mt-6 bg-white rounded-lg shadow p-8">
            <div className="flex flex-col items-center justify-center">
              <div className="animate-spin rounded-full h-16 w-16 border-4 border-gold-500 border-t-transparent mb-4"></div>
              <p className="text-gray-700 text-lg font-medium">Генерация образа...</p>
              <p className="text-gray-500 text-sm mt-2">Создание образа и изображения может занять несколько минут</p>
              <div className="mt-4 w-full max-w-md h-2 bg-gray-200 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-gold-500 to-gold-600 rounded-full animate-pulse" style={{ width: '70%' }}></div>
              </div>
              <div className="mt-4 flex gap-2 text-xs text-gray-500">
                <span className="animate-pulse">●</span>
                <span>Анализ запроса</span>
                <span className="animate-pulse delay-75">●</span>
                <span>Подбор товаров</span>
                <span className="animate-pulse delay-150">●</span>
                <span>Генерация изображения</span>
              </div>
            </div>
          </div>
        )}

        {generatedLook && !loading && (
          <div className="mt-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Сгенерированный образ:</h3>
            <LookCard look={generatedLook} />
          </div>
        )}
      </div>
    </div>
  );
}
