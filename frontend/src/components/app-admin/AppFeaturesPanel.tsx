'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

type YooKassaMode = 'test' | 'live';

export default function AppFeaturesPanel() {
  const [enabled, setEnabled] = useState(true);
  const [source, setSource] = useState<string>('default');
  const [yookassaMode, setYookassaMode] = useState<YooKassaMode>('test');
  const [yookassaSource, setYookassaSource] = useState<string>('default');
  const [yookassaTestConfigured, setYookassaTestConfigured] = useState(false);
  const [yookassaLiveConfigured, setYookassaLiveConfigured] = useState(false);
  const [yookassaActiveConfigured, setYookassaActiveConfigured] = useState(false);
  const [yookassaActiveShopId, setYookassaActiveShopId] = useState<string | null>(null);
  const [yookassaTestShopId, setYookassaTestShopId] = useState<string | null>(null);
  const [yookassaLiveShopId, setYookassaLiveShopId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [stylistRes, yookassaRes] = await Promise.all([
        api.getAiStylistSettings(),
        api.getYooKassaSettings(),
      ]);
      setEnabled(stylistRes.enabled);
      setSource(stylistRes.source);
      setYookassaMode(yookassaRes.mode);
      setYookassaSource(yookassaRes.source);
      setYookassaTestConfigured(yookassaRes.test_configured);
      setYookassaLiveConfigured(yookassaRes.live_configured);
      setYookassaActiveConfigured(yookassaRes.active_configured);
      setYookassaActiveShopId(yookassaRes.active_shop_id || null);
      setYookassaTestShopId(yookassaRes.test_shop_id || null);
      setYookassaLiveShopId(yookassaRes.live_shop_id || null);
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

  const saveYooKassaMode = async (mode: YooKassaMode) => {
    const prevMode = yookassaMode;
    setYookassaMode(mode);
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await api.setYooKassaSettings({ mode });
      setYookassaMode(res.mode);
      setYookassaSource(res.source);
      setYookassaTestConfigured(res.test_configured);
      setYookassaLiveConfigured(res.live_configured);
      setYookassaActiveConfigured(res.active_configured);
      setYookassaActiveShopId(res.active_shop_id || null);
      setYookassaTestShopId(res.test_shop_id || null);
      setYookassaLiveShopId(res.live_shop_id || null);
      setSuccess(
        res.active_configured
          ? `Режим ЮKassa переключен: ${res.mode === 'live' ? 'рабочий' : 'тестовый'}.`
          : `Режим ЮKassa сохранен, но ключи для ${res.mode === 'live' ? 'рабочего' : 'тестового'} режима не настроены.`
      );
    } catch (e: any) {
      setYookassaMode(prevMode);
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить режим ЮKassa');
    } finally {
      setSaving(false);
    }
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

      <div className="mt-4 rounded-md border border-gray-200 p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="font-semibold text-gray-900">ЮKassa: режим платежей</div>
            <div className="mt-1 text-sm text-gray-600">
              Выбранный режим применяется к оплате заказов и подарочных сертификатов. Ключи хранятся только в env.
            </div>
            <div className="mt-2 text-xs text-gray-500">
              Источник настройки: {yookassaSource}
              {yookassaActiveShopId ? ` · активный shop_id: ${yookassaActiveShopId}` : ''}
            </div>
          </div>

          <select
            className="h-10 rounded-md border border-gray-300 bg-white px-3 text-sm text-black disabled:opacity-50"
            value={yookassaMode}
            disabled={loading || saving}
            onChange={(e) => saveYooKassaMode(e.target.value as YooKassaMode)}
          >
            <option value="test">Тестовый режим</option>
            <option value="live">Рабочий режим</option>
          </select>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-2 text-sm md:grid-cols-3">
          <div className="rounded border border-gray-200 p-3">
            <div className="text-xs uppercase tracking-wide text-gray-500">Тестовые ключи</div>
            <div className={`mt-1 font-medium ${yookassaTestConfigured ? 'text-emerald-700' : 'text-red-700'}`}>
              {yookassaTestConfigured ? 'Настроены' : 'Не настроены'}
            </div>
            {yookassaTestShopId ? <div className="mt-1 text-xs text-gray-500">shop_id: {yookassaTestShopId}</div> : null}
          </div>
          <div className="rounded border border-gray-200 p-3">
            <div className="text-xs uppercase tracking-wide text-gray-500">Рабочие ключи</div>
            <div className={`mt-1 font-medium ${yookassaLiveConfigured ? 'text-emerald-700' : 'text-red-700'}`}>
              {yookassaLiveConfigured ? 'Настроены' : 'Не настроены'}
            </div>
            {yookassaLiveShopId ? <div className="mt-1 text-xs text-gray-500">shop_id: {yookassaLiveShopId}</div> : null}
          </div>
          <div className="rounded border border-gray-200 p-3">
            <div className="text-xs uppercase tracking-wide text-gray-500">Активный режим</div>
            <div className={`mt-1 font-medium ${yookassaActiveConfigured ? 'text-emerald-700' : 'text-red-700'}`}>
              {yookassaActiveConfigured ? 'Готов к оплатам' : 'Нет ключей'}
            </div>
          </div>
        </div>

        {!yookassaLiveConfigured ? (
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            Для рабочего режима добавьте в backend env переменные YOOKASSA_LIVE_SHOP_ID и YOOKASSA_LIVE_SECRET_KEY.
          </div>
        ) : null}
      </div>
    </div>
  );
}
