'use client';

import { useEffect, useState, useMemo } from 'react';
import { api } from '@/lib/api';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

interface ModelStat {
  model: string;
  total_cost: number;
  requests: number;
}

interface DayStat {
  date: string;
  total_cost: number;
  by_model: Record<string, number>;
}

interface StatsData {
  avg_daily: number;
  remaining_credits: number;
  days_left: number;
  by_model: ModelStat[];
  by_day: DayStat[];
}

const COLORS = [
  '#ef4444', '#f97316', '#f59e0b', '#84cc16', '#22c55e',
  '#14b8a6', '#06b6d4', '#0ea5e9', '#3b82f6', '#6366f1',
  '#8b5cf6', '#a855f7', '#d946ef', '#ec4899', '#f43f5e',
];

export default function OpenRouterStatsPanel() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getOpenRouterStats();
      setStats(data);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Не удалось загрузить статистику OpenRouter');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStats();
  }, []);

  // Формируем данные для гистограммы
  const chartData = useMemo(() => {
    if (!stats?.by_day?.length) return [];
    
    // Получаем топ-10 моделей по сумме расходов
    const topModels = stats.by_model
      .slice(0, 10)
      .map(m => m.model);
    
    // Формируем данные для каждого дня
    return stats.by_day.map(day => {
      const row: Record<string, number | string> = {
        date: new Date(day.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }),
        total: Math.round(day.total_cost * 100) / 100,
      };
      
      // Добавляем данные для каждой топ-модели
      topModels.forEach(model => {
        row[model] = Math.round((day.by_model[model] || 0) * 100) / 100;
      });
      
      // Добавляем "Другие" для остальных моделей
      const otherCost = Object.entries(day.by_model)
        .filter(([model]) => !topModels.includes(model))
        .reduce((sum, [, cost]) => sum + cost, 0);
      
      if (otherCost > 0) {
        row['Другие'] = Math.round(otherCost * 100) / 100;
      }
      
      return row;
    });
  }, [stats]);

  // Получаем список моделей для легенды (топ-10 + Другие)
  const chartModels = useMemo(() => {
    if (!stats?.by_model?.length) return [];
    const models = stats.by_model.slice(0, 10).map(m => m.model);
    const hasOthers = stats.by_day?.some(day => 
      Object.entries(day.by_model)
        .filter(([model]) => !models.includes(model))
        .reduce((sum, [, cost]) => sum + cost, 0) > 0
    );
    if (hasOthers) models.push('Другие');
    return models;
  }, [stats]);

  const formatCurrency = (value: number) => {
    if (value === 0) return '$0.00';
    if (value < 0.01) return `$${value.toFixed(6)}`;
    return `$${value.toFixed(2)}`;
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-4">Статистика использования OpenRouter</h2>
        <p className="text-gray-500">Загрузка статистики…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-4">Статистика использования OpenRouter</h2>
        <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-3">
          {error}
        </div>
        <button
          onClick={loadStats}
          className="mt-3 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition text-sm font-medium"
        >
          Повторить
        </button>
      </div>
    );
  }

  if (!stats) {
    return null;
  }

  const hasUnlimitedKey = stats.remaining_credits === 0 && stats.avg_daily > 0;

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold text-gray-800">Статистика использования OpenRouter</h2>
        <button
          onClick={loadStats}
          disabled={loading}
          className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition text-sm font-medium"
        >
          {loading ? 'Обновление…' : 'Обновить'}
        </button>
      </div>

      {/* Карточки с основной статистикой */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-blue-50 rounded-lg p-4">
          <p className="text-sm text-blue-600 mb-1">Средние дневные траты</p>
          <p className="text-2xl font-bold text-blue-900">
            {formatCurrency(stats.avg_daily)}/день
          </p>
        </div>
        <div className="bg-green-50 rounded-lg p-4">
          <p className="text-sm text-green-600 mb-1">Остаток на аккаунте</p>
          <p className="text-2xl font-bold text-green-900">
            {hasUnlimitedKey ? 'Без лимита' : formatCurrency(stats.remaining_credits)}
          </p>
        </div>
        <div className="bg-purple-50 rounded-lg p-4">
          <p className="text-sm text-purple-600 mb-1">Хватит примерно на</p>
          <p className="text-2xl font-bold text-purple-900">
            {hasUnlimitedKey ? '∞' : stats.days_left > 0 ? `${stats.days_left} дн.` : '—'}
          </p>
        </div>
      </div>

      {/* Гистограмма расходов по дням */}
      {chartData.length > 0 && (
        <div className="mb-6">
          <h3 className="text-lg font-medium text-gray-800 mb-3">Расходы по дням</h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis 
                  dataKey="date" 
                  tick={{ fontSize: 12 }}
                  stroke="#6b7280"
                />
                <YAxis 
                  tick={{ fontSize: 12 }}
                  stroke="#6b7280"
                  tickFormatter={(value) => `$${value}`}
                />
                <Tooltip
                  formatter={(value: number | undefined) => value !== undefined ? formatCurrency(value) : ''}
                  contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e5e7eb' }}
                />
                <Legend />
                {chartModels.map((model, index) => (
                  <Bar
                    key={model}
                    dataKey={model}
                    stackId="a"
                    fill={model === 'Другие' ? '#9ca3af' : COLORS[index % COLORS.length]}
                    radius={index === chartModels.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Таблица расходов по моделям */}
      {stats.by_model.length > 0 && (
        <div>
          <h3 className="text-lg font-medium text-gray-800 mb-3">Расходы по моделям</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-2 px-3 font-medium text-gray-600">Модель</th>
                  <th className="text-right py-2 px-3 font-medium text-gray-600">Запросов</th>
                  <th className="text-right py-2 px-3 font-medium text-gray-600">Сумма</th>
                </tr>
              </thead>
              <tbody>
                {stats.by_model.map((model) => (
                  <tr key={model.model} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-2 px-3 font-mono text-gray-900">{model.model}</td>
                    <td className="py-2 px-3 text-right text-gray-600">
                      {model.requests.toLocaleString('ru-RU')}
                    </td>
                    <td className="py-2 px-3 text-right font-medium text-gray-900">
                      {formatCurrency(model.total_cost)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {stats.by_model.length === 0 && (
        <p className="text-gray-500 text-sm">Нет данных о расходах по моделям за последний период.</p>
      )}
    </div>
  );
}
