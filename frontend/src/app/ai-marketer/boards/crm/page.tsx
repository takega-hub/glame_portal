'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import AgentBoardChat from '@/components/agents/AgentBoardChat';
import BoardHeader from '@/components/boards/BoardHeader';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  agentInteractions,
  aiMarketer,
  apiClient,
  type AgentInteractionTask,
} from '@/lib/api';

const CRM_STAGES = [
  'Idea',
  'Segmented',
  'Drafted',
  'Needs Approval',
  'Approved',
  'Scheduled',
  'Sent',
  'Measured',
  'Optimized',
];

type ViewMode = 'dashboard' | 'pipeline';

type MarketingCampaign = {
  id: string;
  name: string;
  type: string;
  status: string;
  start_date: string;
  end_date?: string | null;
  target_audience?: Record<string, any> | null;
  channels?: string[] | null;
  metrics?: Record<string, any> | null;
};

type CampaignRow = {
  id: string;
  segment: string;
  objective: string;
  trigger: string;
  channel: string;
  message: string;
  status: string;
  sendDate: string;
  href?: string;
  metrics?: Record<string, any> | null;
};

function stageFromStatus(status: string) {
  const map: Record<string, string> = {
    pending: 'Idea',
    validating: 'Segmented',
    validated: 'Needs Approval',
    pending_approval: 'Needs Approval',
    approved: 'Approved',
    queued: 'Scheduled',
    processing: 'Sent',
    completed: 'Measured',
    draft: 'Idea',
    active: 'Sent',
    paused: 'Scheduled',
    archived: 'Optimized',
  };
  return map[status] || status;
}

function taskTitle(task: AgentInteractionTask) {
  return task.input_data?.title || task.task_context?.title || task.task_type.replaceAll('_', ' ');
}

function segmentNameFromTarget(target: unknown) {
  if (!target) return 'Все клиенты';
  if (typeof target === 'string') return target;
  if (Array.isArray(target)) return target.filter(Boolean).join(', ') || 'Все клиенты';
  if (typeof target === 'object') {
    const data = target as Record<string, any>;
    return data.segment || data.segment_name || data.name || data.audience || 'Все клиенты';
  }
  return 'Все клиенты';
}

function getStageColor(stage: string) {
  const index = CRM_STAGES.indexOf(stage);
  if (index < 3) return 'bg-blue-100 text-blue-800';
  if (index < 6) return 'bg-yellow-100 text-yellow-800';
  if (index < 8) return 'bg-green-100 text-green-800';
  return 'bg-gray-100 text-gray-800';
}

function isCrmTask(task: AgentInteractionTask) {
  const text = `${task.source_agent} ${task.target_agent} ${task.task_type}`.toLowerCase();
  return text.includes('crm') || text.includes('communication') || text.includes('mailing') || text.includes('segment');
}

export default function CRMBoard() {
  const router = useRouter();
  const [viewMode, setViewMode] = useState<ViewMode>('dashboard');
  const [tasks, setTasks] = useState<AgentInteractionTask[]>([]);
  const [campaigns, setCampaigns] = useState<MarketingCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadCrmData();
  }, []);

  async function loadCrmData() {
    setLoading(true);
    setError(null);
    const [loadedTasks, loadedCampaigns] = await Promise.all([
      agentInteractions.listTasks({ limit: 150 }).catch(() => []),
      apiClient.get<MarketingCampaign[]>('/api/marketing/campaigns').then((response) => response.data || []).catch(() => []),
    ]);
    setTasks(loadedTasks.filter(isCrmTask));
    setCampaigns(loadedCampaigns.filter((campaign) => ['email', 'sms', 'push', 'crm', 'loyalty'].includes(campaign.type)));
    setLoading(false);
  }

  async function createMailingTask() {
    setCreating(true);
    setError(null);
    try {
      const { task: created } = await aiMarketer.ensureBoardTask('crm', {
        source_agent: 'crm-board',
        target_agent: 'crm-agent',
        task_type: 'crm_mailing',
        priority: 2,
        input_data: {
          title: 'Подготовить CRM-рассылку',
          description: 'Собрать сегмент, сценарий сообщения и план отправки на основе актуальных CRM-данных',
          expected_result: 'Готовая рассылка с сегментом, текстом, каналом и планом запуска',
          campaign: 'crm_board',
          channel: 'crm',
          source_board: 'crm',
        },
        task_context: {
          board: 'crm',
          created_from: 'crm_board_action',
        },
      });
      router.push(`/ai-marketer/tasks/${created.id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось создать задачу рассылки');
    } finally {
      setCreating(false);
    }
  }

  const campaignRows = useMemo<CampaignRow[]>(() => {
    const marketingRows = campaigns.map((campaign) => ({
      id: campaign.id,
      segment: segmentNameFromTarget(campaign.target_audience),
      objective: campaign.name,
      trigger: campaign.type,
      channel: (campaign.channels || [campaign.type]).join(' + '),
      message: campaign.metrics?.summary || campaign.metrics?.message || 'Маркетинговая кампания из CRM/marketing campaign store',
      status: stageFromStatus(campaign.status),
      sendDate: new Date(campaign.start_date).toLocaleDateString('ru-RU'),
      metrics: campaign.metrics,
    }));

    const taskRows = tasks.slice(0, 12).map((task) => ({
      id: task.id,
      segment: task.input_data?.segment_name || task.input_data?.segment || task.task_context?.segment_name || 'CRM',
      objective: taskTitle(task),
      trigger: task.input_data?.trigger || task.task_type,
      channel: [task.input_data?.channel, task.input_data?.platform].filter(Boolean).join(' + ') || 'crm',
      message: task.input_data?.message || task.input_data?.description || task.output_data?.summary || 'Задача CRM-коммуникации',
      status: stageFromStatus(task.status),
      sendDate: task.deadline_at ? new Date(task.deadline_at).toLocaleDateString('ru-RU') : new Date(task.created_at).toLocaleDateString('ru-RU'),
      href: `/ai-marketer/tasks/${task.id}`,
      metrics: task.output_metadata || task.output_data || null,
    }));

    return [...marketingRows, ...taskRows];
  }, [campaigns, tasks]);

  return (
    <div className="min-h-screen bg-gray-50">
      <BoardHeader
        title="CRM Board"
        description="Центральная панель управления CRM-коммуникациями: сегментация клиентов, планирование рассылок, отслеживание эффективности программ лояльности."
        boardId="crm"
        actions={
          <Button variant="default" size="sm" onClick={createMailingTask} disabled={creating}>
            {creating ? 'Создание...' : 'Создать рассылку'}
          </Button>
        }
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {error && <Card className="p-3 text-sm text-red-700 border-red-200 bg-red-50">{error}</Card>}

        <AgentBoardChat
          agentId="crm-agent"
          agentName="AI CRM"
          boardId="crm"
          aliases={['communication-agent', 'crm-board', 'loyalty']}
        />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-gray-900">Рабочие CRM-задачи</h2>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={loadCrmData} disabled={loading}>Обновить</Button>
            <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as ViewMode)}>
              <TabsList>
                <TabsTrigger value="dashboard">Дашборд</TabsTrigger>
                <TabsTrigger value="pipeline">Пайплайн</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
        </div>

        {viewMode === 'dashboard' ? (
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Активные CRM-кампании</h2>
            <div className="space-y-3">
              {campaignRows.length === 0 ? (
                <Card className="p-4 text-sm text-gray-500">CRM-кампаний и задач коммуникаций пока нет.</Card>
              ) : (
                campaignRows.map((campaign) => (
                  <Card key={campaign.id} className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="flex flex-wrap items-center gap-2 mb-2">
                          <Badge>{campaign.segment}</Badge>
                          <Badge className={getStageColor(campaign.status)}>{campaign.status}</Badge>
                          <Badge variant="outline">{campaign.channel}</Badge>
                        </div>
                        <h3 className="font-medium text-gray-900">{campaign.objective}</h3>
                        <p className="text-sm text-gray-600 mt-1">{campaign.message}</p>
                        <p className="text-xs text-gray-500 mt-2">
                          Триггер: {campaign.trigger} • Дата: {campaign.sendDate}
                        </p>
                      </div>
                      {campaign.href ? (
                        <Link
                          href={campaign.href}
                          className="inline-flex h-9 items-center rounded-md bg-gray-900 px-3 text-sm font-medium text-white hover:bg-gray-800"
                        >
                          Открыть
                        </Link>
                      ) : null}
                    </div>
                  </Card>
                ))
              )}
            </div>
          </section>
        ) : (
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">CRM Flow Pipeline — Пайплайн коммуникаций</h2>
            <div className="overflow-x-auto">
              <div className="flex gap-2 min-w-max">
                {CRM_STAGES.map((stage) => (
                  <div key={stage} className="w-48 flex-shrink-0">
                    <h3 className={`text-xs font-semibold p-2 rounded-t ${getStageColor(stage)} text-center`}>
                      {stage}
                    </h3>
                    <div className="bg-gray-50 p-2 min-h-80 rounded-b border-x border-b border-gray-200 space-y-2">
                      {campaignRows
                        .filter((item) => item.status === stage)
                        .map((item) => (
                          <Card key={item.id} className="p-3 text-xs">
                            <p className="font-medium text-gray-900">{item.objective}</p>
                            <p className="text-gray-500 mt-1">{item.channel} • {item.segment}</p>
                          </Card>
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
