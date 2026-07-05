'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

export default function AppFeaturesPanel() {
  const [enabled, setEnabled] = useState(true);
  const [source, setSource] = useState<string>('default');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getAiStylistSettings();
      setEnabled(res.enabled);
      setSource(res.source);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось загрузить настройки функций');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const save = async (nextEnabled: boolean) => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await api.setAiStylistSettings({ enabled: nextEnabled });
      setEnabled(res.enabled);
      setSource(res.source);
      setSuccess(res.enabled ? 'AI стилист включен для чата покупателей.' : 'AI автоответы стилиста выключены.');
    } catch (e: any) {
      setEnabled(!nextEnabled);
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить настройку');
    } finally {
      setSaving(false);
    }
  };

  const onToggle = () => {
    const next = !enabled;
    setEnabled(next);
    save(next);
  };

  return (
    <div className="rounded-lg bg-white p-6 shadow-md">
      <div className="mb-5">
        <h2 className="text-xl font-semibold text-gray-900">Функции приложения</h2>
        <p className="mt-1 text-sm text-gray-600">
          Управление возможностями, которые видят покупатели в мобильном приложении.
        </p>
      </div>

      {error && <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {success && (
        <div className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {success}
        </div>
      )}

      <div className="flex items-start justify-between gap-4 rounded-md border border-gray-200 p-4">
        <div>
          <div className="font-semibold text-gray-900">AI стилист в чате покупателя</div>
          <div className="mt-1 text-sm text-gray-600">
            Когда включено, после сообщения покупателя backend сразу добавляет ответ AI стилиста в чат.
            Когда выключено, сообщения покупателя сохраняются без автоответа.
          </div>
          <div className="mt-2 text-xs text-gray-500">Источник настройки: {source}</div>
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          disabled={loading || saving}
          onClick={onToggle}
          className={`relative h-7 w-12 shrink-0 rounded-full transition disabled:opacity-50 ${
            enabled ? 'bg-gold-500' : 'bg-gray-300'
          }`}
        >
          <span
            className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow transition ${
              enabled ? 'left-6' : 'left-1'
            }`}
          />
        </button>
      </div>
    </div>
  );
}
