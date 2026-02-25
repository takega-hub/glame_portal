'use client';

import { useState, useEffect } from 'react';
import { api, ContentResponse } from '@/lib/api';

const CJM_STAGES = [
  { value: 'awareness', label: 'Осведомленность' },
  { value: 'consideration', label: 'Рассмотрение' },
  { value: 'purchase', label: 'Покупка' },
  { value: 'retention', label: 'Удержание' },
];

const CHANNELS = [
  { value: 'website_main', label: 'Главная страница сайта' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'email', label: 'Email рассылка' },
  { value: 'facebook', label: 'Facebook' },
  { value: 'vk', label: 'ВКонтакте' },
  { value: 'telegram', label: 'Telegram' },
];

const QUICK_PERSONAS = [
  'Молодая женщина 25-35 лет, любит стильные украшения',
  'Женщина 30-40 лет, ценит качество и уникальность',
  'Активная женщина 20-30 лет, следит за трендами',
  'Деловая женщина 35-45 лет, предпочитает классику',
];

const QUICK_GOALS = [
  'Познакомить с брендом GLAME',
  'Вдохновить на покупку',
  'Мотивировать к покупке',
  'Предложить новые коллекции',
  'Рассказать о преимуществах',
];

export default function ContentGenerator() {
  const [persona, setPersona] = useState('');
  const [cjmStage, setCjmStage] = useState('');
  const [channel, setChannel] = useState('website_main');
  const [goal, setGoal] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ContentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<ContentResponse[]>([]);

  // Загрузка истории из localStorage
  useEffect(() => {
    try {
      const savedHistory = localStorage.getItem('content_generator_history');
      if (savedHistory) {
        setHistory(JSON.parse(savedHistory));
      }
    } catch (e) {
      console.error('Error loading history:', e);
    }
  }, []);

  const generateContent = async () => {
    if (loading) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await api.generateContent({
        persona: persona || undefined,
        cjm_stage: cjmStage || undefined,
        channel: channel || 'website_main',
        goal: goal || undefined,
      });

      setResult(response);
      
      // Сохранение в историю
      const newHistory = [response, ...history].slice(0, 10); // Последние 10
      setHistory(newHistory);
      localStorage.setItem('content_generator_history', JSON.stringify(newHistory));
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Произошла ошибка при генерации контента';
      setError(errorMessage);
      console.error('Error generating content:', err);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    alert('Контент скопирован в буфер обмена!');
  };

  const exportContent = (content: string, format: 'txt' | 'json') => {
    let blob: Blob;
    let filename: string;

    if (format === 'txt') {
      blob = new Blob([content], { type: 'text/plain' });
      filename = `content-${Date.now()}.txt`;
    } else {
      blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
      filename = `content-${Date.now()}.json`;
    }

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-gray-800 mb-6">Content Generator</h1>
      <p className="text-gray-600 mb-6">
        Генерация контента для бренда GLAME с учетом персоны, этапа Customer Journey Map и канала коммуникации.
      </p>

      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Параметры генерации</h2>

        {/* Персона */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Персона (опционально)
          </label>
          <textarea
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
            placeholder="Опишите целевую персону..."
            className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-gold-500"
            rows={3}
          />
          <div className="mt-2 flex flex-wrap gap-2">
            {QUICK_PERSONAS.map((p, idx) => (
              <button
                key={idx}
                onClick={() => setPersona(p)}
                className="px-3 py-1.5 text-xs bg-white border border-gray-300 text-gray-800 hover:bg-gold-50 hover:border-gold-300 rounded-lg transition font-medium"
              >
                {p.substring(0, 30)}...
              </button>
            ))}
          </div>
        </div>

        {/* Этап CJM */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Этап Customer Journey Map
          </label>
          <select
            value={cjmStage}
            onChange={(e) => setCjmStage(e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
          >
            <option value="">Не выбран</option>
            {CJM_STAGES.map((stage) => (
              <option key={stage.value} value={stage.value} className="bg-white text-gray-900">
                {stage.label}
              </option>
            ))}
          </select>
        </div>

        {/* Канал */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Канал коммуникации *
          </label>
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
            required
          >
            {CHANNELS.map((ch) => (
              <option key={ch.value} value={ch.value} className="bg-white text-gray-900">
                {ch.label}
              </option>
            ))}
          </select>
        </div>

        {/* Цель */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Цель контента (опционально)
          </label>
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="Опишите цель контента..."
            className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-gold-500"
            rows={2}
          />
          <div className="mt-2 flex flex-wrap gap-2">
            {QUICK_GOALS.map((g, idx) => (
              <button
                key={idx}
                onClick={() => setGoal(g)}
                className="px-3 py-1.5 text-xs bg-white border border-gray-300 text-gray-800 hover:bg-gold-50 hover:border-gold-300 rounded-lg transition font-medium"
              >
                {g}
              </button>
            ))}
          </div>
        </div>

        {/* Кнопка генерации */}
        <button
          onClick={generateContent}
          disabled={loading || !channel}
          className="w-full px-6 py-3 bg-gold-500 text-white rounded-lg hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed transition font-semibold"
        >
          {loading ? (
            <span className="flex items-center justify-center">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2"></div>
              Генерация...
            </span>
          ) : (
            'Сгенерировать контент'
          )}
        </button>
      </div>

      {/* Ошибка */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <p className="text-red-800 font-medium">Ошибка</p>
          <p className="text-red-600 text-sm mt-1">{error}</p>
        </div>
      )}

      {/* Результат */}
      {result && (
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold">Сгенерированный контент</h2>
            <div className="flex gap-2">
              <button
                onClick={() => copyToClipboard(result.content)}
                className="px-4 py-2 bg-white border border-gray-300 text-gray-800 hover:bg-gray-50 rounded-lg transition text-sm font-medium"
              >
                Копировать
              </button>
              <button
                onClick={() => exportContent(result.content, 'txt')}
                className="px-4 py-2 bg-white border border-gray-300 text-gray-800 hover:bg-gray-50 rounded-lg transition text-sm font-medium"
              >
                Экспорт TXT
              </button>
              <button
                onClick={() => exportContent(result.content, 'json')}
                className="px-4 py-2 bg-white border border-gray-300 text-gray-800 hover:bg-gray-50 rounded-lg transition text-sm font-medium"
              >
                Экспорт JSON
              </button>
            </div>
          </div>

          <div className="mb-4">
            {result.persona && (
              <p className="text-sm text-gray-600 mb-1">
                <strong>Персона:</strong> {result.persona}
              </p>
            )}
            {result.cjm_stage && (
              <p className="text-sm text-gray-600 mb-1">
                <strong>Этап CJM:</strong> {result.cjm_stage}
              </p>
            )}
          </div>

          <textarea
            value={result.content}
            readOnly
            className="w-full px-4 py-3 border border-gray-300 rounded-lg bg-gray-50 font-mono text-sm text-gray-900"
            rows={10}
          />
        </div>
      )}

      {/* История */}
      {history.length > 0 && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold mb-4">История генераций</h2>
          <div className="space-y-4">
            {history.map((item, idx) => (
              <div key={idx} className="border border-gray-200 rounded-lg p-4">
                <div className="flex justify-between items-start mb-2">
                  <div className="text-sm text-gray-600">
                    {item.persona && <p><strong>Персона:</strong> {item.persona}</p>}
                    {item.cjm_stage && <p><strong>Этап:</strong> {item.cjm_stage}</p>}
                  </div>
                  <button
                    onClick={() => copyToClipboard(item.content)}
                    className="px-3 py-1.5 text-xs bg-white border border-gray-300 text-gray-800 hover:bg-gray-50 rounded-lg transition font-medium"
                  >
                    Копировать
                  </button>
                </div>
                <p className="text-sm text-gray-800 line-clamp-3">{item.content}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
