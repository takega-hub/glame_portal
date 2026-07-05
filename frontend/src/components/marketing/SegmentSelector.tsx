'use client';

import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { adminCustomers, aiMarketer, customerSegmentation, type SegmentAnalysisItem, type SegmentRules } from '@/lib/api';

type Props = {
  open: boolean;
  onClose: () => void;
  onSaved?: (segmentId: string) => void;
};

export default function SegmentSelector({ open, onClose, onSaved }: Props) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messageCount, setMessageCount] = useState<number>(1000);
  const [totalCustomers, setTotalCustomers] = useState<number>(0);
  const [analysis, setAnalysis] = useState<SegmentAnalysisItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [savedSegments, setSavedSegments] = useState<Array<{ id: string; name: string; customer_count: number }>>([]);
  const [customRules, setCustomRules] = useState<SegmentRules>({ logic: 'AND', filters: [] });
  const [customCount, setCustomCount] = useState<number>(0);
  const [customName, setCustomName] = useState<string>('');

  useEffect(() => {
    if (!open) return;
    setError(null);
    setStep(1);
    setSelectedId(null);
    setCustomName('');
    setCustomRules({ logic: 'AND', filters: [] });
    setCustomCount(0);
    loadBaseStats();
    loadSaved();
  }, [open]);

  async function loadBaseStats() {
    try {
      const o = await adminCustomers.getOverview();
      setTotalCustomers(o.total_customers || 0);
    } catch {
      setTotalCustomers(0);
    }
  }

  async function loadSaved() {
    try {
      const segs = await customerSegmentation.getSegments();
      setSavedSegments(segs.map(s => ({ id: s.id, name: s.name, customer_count: s.customer_count })));
    } catch {
      setSavedSegments([]);
    }
  }

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      await aiMarketer.autoGenerateSegments();
      const res = await aiMarketer.getSegmentsAnalysis();
      setAnalysis(res.segments || []);
      setStep(2);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось выполнить сегментацию';
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  const selectedItem = useMemo(() => {
    return analysis.find(a => a.segment_id === selectedId) || null;
  }, [analysis, selectedId]);

  const selectedCount = selectedItem ? selectedItem.size : customCount;
  const withinRange = useMemo(() => {
    const min = Math.floor(messageCount * 0.9);
    const max = Math.ceil(messageCount * 1.1);
    return selectedCount >= min && selectedCount <= max;
  }, [selectedCount, messageCount]);

  async function recalcCustomCount(nextRules: SegmentRules) {
    setCustomRules(nextRules);
    setBusy(true);
    setError(null);
    try {
      const { count } = await customerSegmentation.calculateSegmentCount(nextRules);
      setCustomCount(count || 0);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Ошибка расчета количества';
      setError(msg);
      setCustomCount(0);
    } finally {
      setBusy(false);
    }
  }

  async function saveSelected() {
    if (!withinRange) {
      setError('Размер сегмента выходит за пределы ±10% от заявленного объема');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (selectedItem) {
        if (onSaved) onSaved(selectedItem.segment_id);
        onClose();
        return;
      }
      const name = customName && customName.trim() ? customName.trim() : `custom_${Date.now()}`;
      const created = await customerSegmentation.createSegment({
        name,
        description: 'Пользовательский сегмент для рассылки',
        rules: customRules,
      });
      if (onSaved) onSaved(created.id);
      onClose();
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось сохранить сегмент';
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl">
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900">Определить сегмент</h3>
            <button onClick={onClose} className="text-gray-500 hover:text-gray-700">✕</button>
          </div>
        </div>
        <div className="p-6 space-y-4">
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-700 mb-1">Планируемый объём сообщений</label>
                <input
                  type="number"
                  min={1}
                  value={messageCount}
                  onChange={(e) => setMessageCount(Math.max(1, Number(e.target.value || 0)))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2"
                  placeholder="Например: 1000"
                />
                <div className="text-xs text-gray-500 mt-1">База: {totalCustomers}</div>
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button variant="outline" onClick={onClose}>Отмена</Button>
                <Button onClick={generate} disabled={busy}>{busy ? 'Анализ…' : 'Автосегментация'}</Button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="text-sm text-gray-700">Заявленный объём: {messageCount}</div>
                <div className="text-sm text-gray-700">База: {totalCustomers}</div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[420px] overflow-auto pr-1">
                {analysis.map(a => {
                  const coverage = totalCustomers > 0 ? Math.round((a.size / totalCustomers) * 100) : 0;
                  const selected = a.segment_id === selectedId;
                  return (
                    <button
                      key={a.segment_id}
                      onClick={() => setSelectedId(a.segment_id)}
                      className={`text-left border rounded-lg p-3 hover:bg-gray-50 ${selected ? 'border-gold-500' : 'border-gray-200'}`}
                    >
                      <div className="font-medium text-gray-900 mb-1">{a.name}</div>
                      <div className="text-sm text-gray-700 mb-2">{a.description || 'Сегмент'}</div>
                      <div className="text-xs text-gray-600">Размер: {a.size} • Покрытие: {coverage}%</div>
                      <div className="text-xs text-gray-500 mt-1 line-clamp-3">{a.insights}</div>
                    </button>
                  );
                })}
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" onClick={() => setStep(3)}>Настроить фильтры</Button>
                <div className={`text-sm ${withinRange ? 'text-green-700' : 'text-red-700'}`}>
                  Выбрано: {selectedCount} {withinRange ? '✓' : '✕'}
                </div>
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button variant="outline" onClick={onClose}>Отмена</Button>
                <Button onClick={saveSelected} disabled={!selectedId || busy}>{busy ? 'Сохранение…' : 'Выбрать'}</Button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Город</label>
                  <input
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                    placeholder="Например: Москва"
                    onChange={(e) => {
                      const v = e.target.value.trim();
                      const next = {
                        ...customRules,
                        filters: [
                          ...customRules.filters.filter(f => f.field !== 'city' || f.operator !== 'equals' ),
                          ...(v ? [{ field: 'city', operator: 'equals', value: v }] as any : [])
                        ]
                      };
                      recalcCustomCount(next);
                    }}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Бренд</label>
                  <input
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                    placeholder="Например: GLAME"
                    onChange={(e) => {
                      const v = e.target.value.trim();
                      const next = {
                        ...customRules,
                        filters: [
                          ...customRules.filters.filter(f => f.field !== 'brand' ),
                          ...(v ? [{ field: 'brand', operator: 'contains', value: v }] as any : [])
                        ]
                      };
                      recalcCustomCount(next);
                    }}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Дней без покупок ≥</label>
                  <input
                    type="number"
                    min={0}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                    placeholder="Например: 180"
                    onChange={(e) => {
                      const n = Number(e.target.value || 0);
                      const next = {
                        ...customRules,
                        filters: [
                          ...customRules.filters.filter(f => f.field !== 'last_purchase_date' ),
                          ...(n > 0 ? [{ field: 'last_purchase_date', operator: 'within_last_days', value: n }] as any : [])
                        ]
                      };
                      recalcCustomCount(next);
                    }}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Минимум покупок</label>
                  <input
                    type="number"
                    min={0}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                    placeholder="Например: 2"
                    onChange={(e) => {
                      const n = Number(e.target.value || 0);
                      const next = {
                        ...customRules,
                        filters: [
                          ...customRules.filters.filter(f => f.field !== 'total_purchases' ),
                          ...(n > 0 ? [{ field: 'total_purchases', operator: '>=', value: n }] as any : [])
                        ]
                      };
                      recalcCustomCount(next);
                    }}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Пол</label>
                  <select
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                    onChange={(e) => {
                      const v = e.target.value;
                      const next = {
                        ...customRules,
                        filters: [
                          ...customRules.filters.filter(f => f.field !== 'gender' ),
                          ...(v ? [{ field: 'gender', operator: 'equals', value: v }] as any : [])
                        ]
                      };
                      recalcCustomCount(next);
                    }}
                  >
                    <option value="">Любой</option>
                    <option value="male">Мужской</option>
                    <option value="female">Женский</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-700 mb-1">Название сегмента</label>
                  <input
                    value={customName}
                    onChange={(e) => setCustomName(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2"
                    placeholder="Например: Клиенты без покупок 180+"
                  />
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className={`text-sm ${withinRange ? 'text-green-700' : 'text-red-700'}`}>Размер: {customCount} из {messageCount}</div>
                <div className="text-sm text-gray-700">Покрытие: {totalCustomers > 0 ? Math.round((customCount / totalCustomers) * 100) : 0}%</div>
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button variant="outline" onClick={() => setStep(2)}>Назад</Button>
                <Button onClick={saveSelected} disabled={busy || customCount === 0}>{busy ? 'Сохранение…' : 'Сохранить сегмент'}</Button>
              </div>
              <div>
                <div className="text-sm font-medium text-gray-900 mb-2">Сохранённые сегменты</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-40 overflow-auto pr-1">
                  {savedSegments.map(s => (
                    <button
                      key={s.id}
                      onClick={() => {
                        setSelectedId(s.id);
                        setStep(2);
                      }}
                      className="text-left border border-gray-200 rounded-lg p-2 hover:bg-gray-50"
                    >
                      <div className="font-medium text-gray-900">{s.name}</div>
                      <div className="text-xs text-gray-600">Размер: {s.customer_count}</div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {error && <div className="text-sm text-red-600">{error}</div>}
        </div>
      </div>
    </div>
  );
}
