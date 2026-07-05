'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import AgentBoardChat from '@/components/agents/AgentBoardChat';
import BoardHeader from '@/components/boards/BoardHeader';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { TrendingUp, TrendingDown, AlertTriangle, Lightbulb, BarChart3, Users, ShoppingCart, Save, Activity } from 'lucide-react';
import { agentInteractions, aiMarketer, apiClient, type AgentInteractionTask } from '@/lib/api';

const formatNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const formatCurrency = new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 });

type MetricItem = {
  id: string;
  title: string;
  value: string;
  change: number;
  icon: React.ReactNode;
};

function n(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function isAnalyticsTask(task: AgentInteractionTask) {
  const text = `${task.source_agent} ${task.target_agent} ${task.task_type}`.toLowerCase();
  return text.includes('analytics') || text.includes('report') || text.includes('analysis');
}

function taskTitle(task: AgentInteractionTask) {
  return task.input_data?.title || task.task_context?.title || task.task_type.replaceAll('_', ' ');
}

export default function AnalyticsBoard() {
  const router = useRouter();
  const [inventory, setInventory] = useState<Record<string, any> | null>(null);
  const [salesMetrics, setSalesMetrics] = useState<Record<string, any> | null>(null);
  const [visits, setVisits] = useState<Record<string, any> | null>(null);
  const [aiDashboard, setAiDashboard] = useState<Record<string, any> | null>(null);
  const [tasks, setTasks] = useState<AgentInteractionTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(null);
    const [inventoryData, salesData, visitsData, aiData, loadedTasks] = await Promise.all([
      apiClient.get<Record<string, any>>('/api/inventory/dashboard?period=month').then((response) => response.data).catch(() => null),
      apiClient.get<Record<string, any>>('/api/analytics/1c-sales/metrics?period=month').then((response) => response.data).catch(() => null),
      apiClient.get<Record<string, any>>('/api/analytics/store-visits/daily?days=14').then((response) => response.data).catch(() => null),
      apiClient.get<Record<string, any>>('/api/ai-marketer/dashboard').then((response) => response.data).catch(() => null),
      agentInteractions.listTasks({ limit: 200 }).then((items) => items.filter(isAnalyticsTask)).catch(() => []),
    ]);
    setInventory(inventoryData);
    setSalesMetrics(salesData);
    setVisits(visitsData);
    setAiDashboard(aiData);
    setTasks(loadedTasks);
    setLoading(false);
  }

  async function createAnalyticsTask(seed: { title: string; description: string; taskType?: string }) {
    setCreating(true);
    setError(null);
    try {
      const { task: created } = await aiMarketer.ensureBoardTask('analytics', {
        source_agent: 'analytics-board',
        target_agent: 'analytics-agent',
        task_type: seed.taskType || 'analytics_review',
        priority: 2,
        input_data: {
          title: seed.title,
          description: seed.description,
          expected_result: 'Аналитический вывод, риски, рекомендации и список действий',
          source_board: 'analytics',
        },
        task_context: {
          board: 'analytics',
          created_from: 'analytics_board',
          inventory_snapshot: inventory,
          sales_snapshot: salesMetrics,
          visits_snapshot: visits,
          crm_snapshot: aiDashboard,
        },
      });
      router.push(`/ai-marketer/tasks/${created.id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось создать аналитическую задачу');
    } finally {
      setCreating(false);
    }
  }

  const visitors = useMemo(() => {
    const rows = visits?.daily_data || visits?.data || [];
    return Array.isArray(rows) ? rows.reduce((sum, row) => sum + n(row.visitors ?? row.visitor_count ?? row.visits), 0) : 0;
  }, [visits]);

  const metrics = useMemo<MetricItem[]>(() => [
    { id: 'traffic', title: 'Трафик 14 дней', value: loading ? '...' : formatNumber.format(visitors), change: n(visits?.change_percent), icon: <Users className="h-5 w-5" /> },
    { id: 'revenue', title: 'Выручка месяц', value: loading ? '...' : formatCurrency.format(n(salesMetrics?.revenue ?? inventory?.sales?.revenue)), change: n(salesMetrics?.revenue_change_percent), icon: <ShoppingCart className="h-5 w-5" /> },
    { id: 'saves', title: 'CRM high risk', value: loading ? '...' : formatNumber.format(n(aiDashboard?.churn_risk?.high_risk)), change: 0, icon: <Save className="h-5 w-5" /> },
    { id: 'tasks', title: 'Аналитические задачи', value: loading ? '...' : formatNumber.format(tasks.length), change: 0, icon: <Activity className="h-5 w-5" /> },
  ], [aiDashboard, inventory, loading, salesMetrics, tasks.length, visitors, visits]);

  const alerts = useMemo(() => {
    const failed = tasks.filter((task) => ['failed', 'rejected'].includes(task.status)).map((task) => ({
      id: task.id,
      title: taskTitle(task),
      type: 'failure',
      description: task.error_message || task.input_data?.description || 'Проблема в аналитической задаче',
      href: `/ai-marketer/tasks/${task.id}`,
    }));
    const stockCritical = n(inventory?.stock?.critical_count);
    if (stockCritical > 0) {
      failed.unshift({ id: 'stock-critical', title: 'Критические остатки', type: 'anomaly', description: `${stockCritical} товаров требуют внимания`, href: '' });
    }
    return failed.slice(0, 6);
  }, [inventory, tasks]);

  const recommendations = useMemo(() => {
    const items: Array<{ title: string; expectedOutcome: string; impact: 'high' | 'medium' | 'low' }> = [];
    if (n(inventory?.stock?.critical_count) > 0) {
      items.push({
        title: 'Проверить критические остатки',
        expectedOutcome: `${formatNumber.format(n(inventory?.stock?.critical_count))} товарных позиций для решения: дозаказ, вывод из кампаний или распродажа`,
        impact: 'high',
      });
    }
    if (n(aiDashboard?.churn_risk?.high_risk) > 0) {
      items.push({
        title: 'Найти CRM-сегменты для реактивации',
        expectedOutcome: `${formatNumber.format(n(aiDashboard?.churn_risk?.high_risk))} клиентов с высоким риском оттока`,
        impact: 'high',
      });
    }
    if (visitors > 0 || n(salesMetrics?.revenue ?? inventory?.sales?.revenue) > 0) {
      items.push({
        title: 'Собрать недельный executive report',
        expectedOutcome: 'Единый отчет по продажам, трафику, CRM и складу на основе текущих данных',
        impact: 'medium',
      });
    }
    if (items.length === 0 && tasks.length > 0) {
      items.push({
        title: 'Разобрать текущие аналитические задачи',
        expectedOutcome: `${formatNumber.format(tasks.length)} задач для приоритизации и вывода решений`,
        impact: 'low',
      });
    }
    return items;
  }, [aiDashboard, inventory, salesMetrics, tasks.length, visitors]);

  return (
    <div className="min-h-screen bg-gray-50">
      <BoardHeader
        title="Analytics Board"
        description="Бизнес-аналитика на основе 1С, inventory, CRM, посещений и задач AI-агентов."
        boardId="analytics"
        actions={<Button variant="default" size="sm" onClick={() => createAnalyticsTask({ title: 'Сформировать аналитический отчет', description: 'Собрать отчет по всем текущим данным досок', taskType: 'executive_report' })} disabled={creating}>{creating ? 'Создание...' : 'Экспорт отчета'}</Button>}
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-8">
        {error && <Card className="p-3 text-sm text-red-700 border-red-200 bg-red-50">{error}</Card>}
        <AgentBoardChat
          agentId="analytics-agent"
          agentName="AI Analytics"
          boardId="analytics"
          aliases={['analytics-board', 'executive_report']}
        />

        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2"><BarChart3 className="h-5 w-5" />Executive Dashboard</h2>
            <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>Обновить</Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {metrics.map((metric) => (
              <Card key={metric.id} className="p-5">
                <div className="flex items-start justify-between">
                  <div className="p-2 bg-gray-100 rounded-lg">{metric.icon}</div>
                  <div className={`flex items-center gap-1 text-sm ${metric.change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {metric.change >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                    {Math.abs(metric.change).toFixed(1)}%
                  </div>
                </div>
                <div className="mt-4">
                  <p className="text-sm text-gray-500">{metric.title}</p>
                  <p className="text-2xl font-semibold text-gray-900 mt-1">{metric.value}</p>
                </div>
              </Card>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2"><AlertTriangle className="h-5 w-5" />Alerts Layer</h2>
          <div className="grid grid-cols-1 gap-3">
            {alerts.length === 0 ? <Card className="p-4 text-sm text-gray-500">Активных алертов нет.</Card> : null}
            {alerts.map((alert) => (
              <div key={alert.id} className="p-4 rounded-lg border bg-yellow-50 border-yellow-200 text-yellow-800">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="font-medium">{alert.title}</h3>
                    <p className="text-sm mt-1 opacity-80">{alert.description}</p>
                  </div>
                  {alert.href ? <LinkButton href={alert.href}>Разобраться</LinkButton> : <Button size="sm" variant="outline" onClick={() => createAnalyticsTask({ title: alert.title, description: alert.description })}>Разобраться</Button>}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2"><Lightbulb className="h-5 w-5" />AI Recommendation Layer</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {recommendations.length === 0 ? <Card className="p-5 text-sm text-gray-500">Рекомендации появятся после загрузки продаж, трафика, CRM или inventory-сигналов.</Card> : null}
            {recommendations.map((rec) => (
              <Card key={rec.title} className="p-5">
                <div className="flex items-start justify-between mb-3"><Badge className={rec.impact === 'high' ? 'bg-red-100 text-red-800' : 'bg-yellow-100 text-yellow-800'}>{rec.impact}</Badge></div>
                <h3 className="font-medium text-gray-900 mb-2">{rec.title}</h3>
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-green-600 font-medium">{rec.expectedOutcome}</p>
                  <Button size="sm" onClick={() => createAnalyticsTask({ title: rec.title, description: rec.expectedOutcome })} disabled={creating}>Применить</Button>
                </div>
              </Card>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function LinkButton({ href, children }: { href: string; children: React.ReactNode }) {
  return <Link href={href} className="inline-flex h-9 items-center rounded-md border px-3 text-sm font-medium hover:bg-white">{children}</Link>;
}
