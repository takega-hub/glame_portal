'use client';

import { useState, useRef } from 'react';
import { api } from '@/lib/api';

interface PhotoTryOnProps {
  lookId?: string;
  onTryOnComplete?: (result: any) => void;
}

export default function PhotoTryOn({ lookId, onTryOnComplete }: PhotoTryOnProps) {
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<any>(null);
  const [tryOnResult, setTryOnResult] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setPhoto(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreview(reader.result as string);
      };
      reader.readAsDataURL(file);
      setError(null);
      setAnalysis(null);
      setTryOnResult(null);
    }
  };

  const handleAnalyze = async () => {
    if (!photo) return;

    setAnalyzing(true);
    setError(null);

    try {
      const result = await api.analyzeUserPhoto(photo);
      setAnalysis(result);
    } catch (e: any) {
      let errorMessage = 'Ошибка при анализе фото';
      if (e?.response?.data?.detail) {
        errorMessage = typeof e.response.data.detail === 'string' 
          ? e.response.data.detail 
          : JSON.stringify(e.response.data.detail);
      } else if (e?.message) {
        errorMessage = typeof e.message === 'string' ? e.message : String(e.message);
      }
      setError(errorMessage);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleTryOn = async () => {
    if (!photo || !lookId) return;

    setLoading(true);
    setError(null);

    try {
      const result = await api.tryOnLook(lookId, photo);
      setTryOnResult(result);
      if (onTryOnComplete) {
        onTryOnComplete(result);
      }
    } catch (e: any) {
      let errorMessage = 'Ошибка при примерке образа';
      if (e?.response?.data?.detail) {
        errorMessage = typeof e.response.data.detail === 'string' 
          ? e.response.data.detail 
          : JSON.stringify(e.response.data.detail);
      } else if (e?.message) {
        errorMessage = typeof e.message === 'string' ? e.message : String(e.message);
      }
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateWithTryOn = async () => {
    if (!photo) return;

    setLoading(true);
    setError(null);

    try {
      const result = await api.generateLookWithTryOn(
        {
          look_id: lookId,
          user_request: analysis ? `Стиль: ${analysis.style}, Цветотип: ${analysis.color_type}` : undefined,
        },
        photo
      );
      setTryOnResult(result);
      if (onTryOnComplete) {
        onTryOnComplete(result);
      }
    } catch (e: any) {
      let errorMessage = 'Ошибка при генерации образа с примеркой';
      if (e?.response?.data?.detail) {
        errorMessage = typeof e.response.data.detail === 'string' 
          ? e.response.data.detail 
          : JSON.stringify(e.response.data.detail);
      } else if (e?.message) {
        errorMessage = typeof e.message === 'string' ? e.message : String(e.message);
      }
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-4">Примерка образа на фото</h2>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-900 mb-2">
            Загрузите ваше фото
          </label>
          <div className="flex items-center gap-4">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handlePhotoSelect}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="px-4 py-2 border border-gray-300 rounded-md text-gray-900 bg-white hover:bg-gray-50 transition"
            >
              Выбрать фото
            </button>
            {photo && (
              <span className="text-sm text-gray-900 font-medium">{photo.name}</span>
            )}
          </div>
        </div>

        {preview && (
          <div className="mt-4">
            <img
              src={preview}
              alt="Preview"
              className="max-w-xs rounded-lg border border-gray-200"
            />
          </div>
        )}

        {photo && (
          <div className="flex gap-2">
            <button
              onClick={handleAnalyze}
              disabled={analyzing}
              className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition disabled:opacity-50"
            >
              {analyzing ? 'Анализ...' : 'Проанализировать фото'}
            </button>
            {lookId && (
              <button
                onClick={handleTryOn}
                disabled={loading}
                className="px-4 py-2 bg-gold-500 text-white rounded-lg hover:bg-gold-600 transition disabled:opacity-50"
              >
                {loading ? 'Примерка...' : 'Примерка образа'}
              </button>
            )}
            {!lookId && (
              <button
                onClick={handleGenerateWithTryOn}
                disabled={loading}
                className="px-4 py-2 bg-gold-500 text-white rounded-lg hover:bg-gold-600 transition disabled:opacity-50"
              >
                {loading ? 'Генерация...' : 'Сгенерировать и примерить'}
              </button>
            )}
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-md p-3">
            <p className="text-red-700 text-sm">{error}</p>
          </div>
        )}

        {analysis && (
          <div className="bg-blue-50 border border-blue-200 rounded-md p-4">
            <h3 className="font-semibold text-gray-900 mb-2">Результаты анализа:</h3>
            <div className="space-y-1 text-sm text-gray-900">
              <p><strong className="text-gray-900">Цветотип:</strong> <span className="text-gray-900">{analysis.color_type}</span></p>
              <p><strong className="text-gray-900">Стиль:</strong> <span className="text-gray-900">{analysis.style}</span></p>
              {analysis.features && (
                <div className="mt-2">
                  <p className="font-medium text-gray-900">Особенности:</p>
                  <ul className="list-disc list-inside ml-2 text-gray-900">
                    {Object.entries(analysis.features).map(([key, value]) => (
                      <li key={key} className="text-gray-900">{key}: {String(value)}</li>
                    ))}
                  </ul>
                </div>
              )}
              {analysis.recommendations && (
                <div className="mt-2">
                  <p className="font-medium text-gray-900">Рекомендации:</p>
                  <ul className="list-disc list-inside ml-2 text-gray-900">
                    {analysis.recommendations.metal_colors && (
                      <li className="text-gray-900">Металлы: {analysis.recommendations.metal_colors.join(', ')}</li>
                    )}
                    {analysis.recommendations.stone_colors && (
                      <li className="text-gray-900">Камни: {analysis.recommendations.stone_colors.join(', ')}</li>
                    )}
                    {analysis.recommendations.styles && (
                      <li className="text-gray-900">Стили: {analysis.recommendations.styles.join(', ')}</li>
                    )}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}

        {tryOnResult && (
          <div className="mt-4">
            <h3 className="font-semibold text-gray-900 mb-2">Результат примерки:</h3>
            {tryOnResult.try_on_result?.try_on_image_url && (
              <div>
                <img
                  src={tryOnResult.try_on_result.try_on_image_url}
                  alt="Try-on result"
                  className="max-w-full rounded-lg border border-gray-200"
                />
              </div>
            )}
            {tryOnResult.generated_look && (
              <div className="mt-4">
                <p className="text-sm text-gray-900">
                  Образ сгенерирован и примерен на ваше фото
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
