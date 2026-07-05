'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import AgentBoardChat from '@/components/agents/AgentBoardChat';
import BoardHeader from '@/components/boards/BoardHeader';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { agentInteractions, aiMarketer, apiClient, type AgentInteractionTask } from '@/lib/api';

type MarketingCampaign = {
  id: string;
  name: string;
  type: string;
  status: string;
  budget?: number | null;
  target_audience?: Record<string, any> | null;
  channels?: string[] | null;
  metrics?: Record<string, any> | null;
  start_date: string;
};

const formatNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const formatCurrency = new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 });

function taskTitle(task: AgentInteractionTask) {
  return task.input_data?.title || task.task_context?.title || task.task_type.replaceAll('_', ' ');
}

function isTrafficTask(task: AgentInteractionTask) {
  const text = `${task.source_agent} ${task.target_agent} ${task.task_type}`.toLowerCase();
  return text.includes('traffic') || text.includes('growth') || text.includes('retarget') || text.includes('ads');
}

export default function TrafficGrowthBoard() {
  const router = useRouter();
  const [tasks, setTasks] = useState<AgentInteractionTask[]>([]);
  const [campaigns, setCampaigns] = useState<MarketingCampaign[]>([]);
  const [visits, setVisits] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(null);
    const [loadedTasks, loadedCampaigns, visitsData] = await Promise.all([
      agentInteractions.listTasks({ limit: 150 }).then((items) => items.filter(isTrafficTask)).catch(() => []),
      apiClient.get<MarketingCampaign[]>('/api/marketing/campaigns').then((response) => response.data || []).catch(() => []),
      apiClient.get<Record<string, any>>('/api/analytics/store-visits/daily?days=14').then((response) => response.data).catch(() => null),
    ]);
    setTasks(loadedTasks);
    setCampaigns(loadedCampaigns.filter((campaign) => ['paid', 'social', 'ads', 'traffic', 'retargeting'].includes(campaign.type)));
    setVisits(visitsData);
    setLoading(false);
  }

  async function createGrowthTask(seed: { title: string; description: string; taskType?: string; channel?: string }) {
    setCreating(true);
    setError(null);
    try {
      const { task: created } = await aiMarketer.ensureBoardTask('traffic', {
        source_agent: 'traffic-board',
        target_agent: 'traffic-growth-agent',
        task_type: seed.taskType || 'growth_campaign',
        priority: 2,
        input_data: {
          title: seed.title,
          description: seed.description,
          expected_result: 'План канала роста: аудитория, бюджет, KPI, запуск и измерение',
          channel: seed.channel || 'growth',
          source_board: 'traffic',
        },
        task_context: {
          board: 'traffic',
          created_from: 'traffic_growth_board',
          visits_snapshot: visits,
        },
      });
      router.push(`/ai-marketer/tasks/${created.id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось создать growth-задачу');
    } finally {
      setCreating(false);
    }
  }

  const totalVisitors = useMemo(() => {
    const rows = visits?.daily_data || visits?.data || [];
    return Array.isArray(rows) ? rows.reduce((sum, row) => sum + Number(row.visitors ?? row.visitor_count ?? row.visits ?? 0), 0) : 0;
  }, [visits]);

  return (
    <div className="min-h-screen bg-gray-50">
      <BoardHeader
        title="Traffic & Growth Board"
        description="Привлечение трафика, рекламные кампании, ретаргетинг и рост аудитории."
        boardId="traffic"
        actions={<Button variant="default" size="sm" onClick={() => createGrowthTask({ title: 'Создать growth-кампанию', description: 'Подготовить новую кампанию привлечения трафика' })} disabled={creating}>{creating ? 'Создание...' : 'Создать кампанию'}</Button>}
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {error && <Card className="p-3 text-sm text-red-700 border-red-200 bg-red-50">{error}</Card>}
        <AgentBoardChat
          agentId="traffic-growth-agent"
          agentName="AI Traffic & Growth"
          boardId="traffic"
          aliases={['traffic-growth', 'traffic-board', 'growth']}
        />

        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Active Growth Campaigns — Активные кампании</h2>
            <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>Обновить</Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {campaigns.map((campaign) => (
              <Card key={campaign.id} className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <Badge>{campaign.type}</Badge>
                      {(campaign.channels || []).map((channel) => <Badge key={channel} variant="outline">{channel}</Badge>)}
                      <Badge className={campaign.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}>{campaign.status}</Badge>
                    </div>
                    <h3 className="font-medium text-gray-900">{campaign.name}</h3>
                    <div className="grid grid-cols-3 gap-4 mt-3 text-sm">
                      <Metric label="Бюджет" value={campaign.budget ? formatCurrency.format(campaign.budget) : '—'} />
                      <Metric label="Аудитория" value={String(campaign.target_audience?.name || campaign.target_audience?.segment || '—')} />
                      <Metric label="KPI" value={String(campaign.metrics?.kpi || campaign.metrics?.goal || '—')} />
                    </div>
                  </div>
                </div>
              </Card>
            ))}
            {tasks.map((task) => (
              <Card key={task.id} className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <Badge>{task.input_data?.channel || task.task_type}</Badge>
                      <Badge variant="outline">{task.status}</Badge>
                    </div>
                    <h3 className="font-medium text-gray-900">{taskTitle(task)}</h3>
                    <p className="text-sm text-gray-600 mt-1">{task.input_data?.description || 'Growth-задача'}</p>
                  </div>
                  <LinkButton href={`/ai-marketer/tasks/${task.id}`}>Детали</LinkButton>
                </div>
              </Card>
            ))}
            {!loading && campaigns.length === 0 && tasks.length === 0 ? <Card className="p-5 text-sm text-gray-500">Growth-кампаний и задач пока нет.</Card> : null}
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Amplification Recommendations — Рекомендации по усилению</h2>
          <div className="space-y-3">
            <Card className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-medium text-gray-900">Трафик за 14 дней: {loading ? '...' : formatNumber.format(totalVisitors)}</p>
                  <p className="text-sm text-blue-600 mt-1">Рекомендация формируется как задача для traffic-growth агента на основе текущих визитов и активных кампаний.</p>
                </div>
                <Button size="sm" onClick={() => createGrowthTask({ title: 'Проанализировать усиление трафика', description: 'Найти канал роста по текущим визитам, кампаниям и CRM-данным', taskType: 'traffic_amplification' })} disabled={creating}>Применить</Button>
              </div>
            </Card>
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">App Return Layer — Стратегии возврата пользователей</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              ['Push-уведомления', 'Персональные push о новых поступлениях', 'push'],
              ['CRM-ретаргетинг', 'Рассылки по сохраненным товарам и образам', 'crm-retargeting'],
              ['Рекламный ретаргетинг', 'Кампании в соцсетях по некупившим пользователям', 'ads-retargeting'],
            ].map(([title, description, channel]) => (
              <Card key={channel} className="p-4">
                <h3 className="font-medium text-gray-900">{title}</h3>
                <p className="text-sm text-gray-600 mt-1">{description}</p>
                <Button size="sm" variant="outline" className="mt-3" onClick={() => createGrowthTask({ title, description, taskType: 'return_strategy', channel })} disabled={creating}>Запустить</Button>
              </Card>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><p className="text-gray-500">{label}</p><p className="font-medium text-xs">{value}</p></div>;
}

function LinkButton({ href, children }: { href: string; children: React.ReactNode }) {
  return <Link href={href} className="inline-flex h-9 items-center rounded-md border px-3 text-sm font-medium hover:bg-gray-50">{children}</Link>;
}
