'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
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
  type CrmProjectTopic,
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

type SuggestedCrmProject = {
  id: string;
  title: string;
  description: string;
  taskType: string;
  channel: string;
};

const SUGGESTED_CRM_PROJECTS: SuggestedCrmProject[] = [
  {
    id: 'calls',
    title: 'Проект по созвонам',
    description: 'История обсуждения скриптов, сегментов, статусов обзвона и результата по CRM-звонкам.',
    taskType: 'crm_calls_project',
    channel: 'call',
  },
  {
    id: 'sms',
    title: 'Проект по SMS-рассылке',
    description: 'История подготовки SMS, согласования текста, статусов отправки и результата рассылки.',
    taskType: 'crm_sms_mailing_project',
    channel: 'sms',
  },
];

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

function crmProjectLabel(project: CrmProjectTopic) {
  if (project.project_type === 'calls') return 'Созвоны';
  if (project.project_type === 'sms_mailing') return 'SMS';
  return project.channel || 'CRM';
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
  const searchParams = useSearchParams();
  const [viewMode, setViewMode] = useState<ViewMode>('dashboard');
  const [tasks, setTasks] = useState<AgentInteractionTask[]>([]);
  const [campaigns, setCampaigns] = useState<MarketingCampaign[]>([]);
  const [projectTopics, setProjectTopics] = useState<CrmProjectTopic[]>([]);
  const [selectedProjectTaskId, setSelectedProjectTaskId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState('');
  const [newCampaignHandled, setNewCampaignHandled] = useState(false);

  useEffect(() => {
    loadCrmData();
  }, []);

  useEffect(() => {
    if (loading || creating || newCampaignHandled || searchParams.get('new_campaign') !== '1') return;
    setNewCampaignHandled(true);
    createProjectTopic({
      id: `new-campaign-${Date.now()}`,
      title: 'Новая CRM-кампания',
      description: 'Чат создания новой CRM-кампании: цель, сегмент, канал, сценарий, скрипты, согласование и передача в задачи продавцам.',
      taskType: 'crm_campaign_project',
      channel: 'crm',
    }).finally(() => {
      router.replace('/ai-marketer/boards/crm');
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [creating, loading, newCampaignHandled, searchParams]);

  async function loadCrmData() {
    setLoading(true);
    setError(null);
    const [loadedTasks, loadedCampaigns, loadedProjects] = await Promise.all([
      agentInteractions.listTasks({ limit: 150 }).catch(() => []),
      apiClient.get<MarketingCampaign[]>('/api/marketing/campaigns').then((response) => response.data || []).catch(() => []),
      agentInteractions.listCrmProjects(50).catch(() => []),
    ]);
    const visibleProjects = loadedProjects.filter((project) => project.status !== 'deleted');
    setTasks(loadedTasks.filter(isCrmTask));
    setCampaigns(loadedCampaigns.filter((campaign) => ['email', 'sms', 'push', 'crm', 'loyalty'].includes(campaign.type)));
    setProjectTopics(visibleProjects);
    if (!selectedProjectTaskId && visibleProjects[0]?.task_id) {
      setSelectedProjectTaskId(visibleProjects[0].task_id);
    } else if (selectedProjectTaskId && !visibleProjects.some((project) => project.task_id === selectedProjectTaskId)) {
      setSelectedProjectTaskId(visibleProjects[0]?.task_id || '');
    }
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

  async function createProjectTopic(project: SuggestedCrmProject) {
    setCreating(true);
    setError(null);
    try {
      const { task: created } = await aiMarketer.ensureBoardTask('crm', {
        source_agent: 'crm-board',
        target_agent: 'crm-agent',
        task_type: project.taskType,
        priority: 2,
        idempotency_key: `crm-project:${project.id}`,
        input_data: {
          title: project.title,
          description: project.description,
          expected_result: 'История обсуждения, итоговый CRM-план, результат обсуждения и следующий запуск проекта.',
          channel: project.channel,
          source_board: 'crm',
        },
        task_context: {
          board: 'crm',
          project_topic: project.id,
          title: project.title,
          channel: project.channel,
          created_from: 'crm_project_topics_panel',
        },
      });
      setSelectedProjectTaskId(created.id);
      await loadCrmData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось создать CRM-проект');
    } finally {
      setCreating(false);
    }
  }

  async function createCustomProject() {
    const title = window.prompt('Название нового CRM-проекта:')?.trim();
    if (!title || creating) return;
    await createProjectTopic({
      id: `custom-${Date.now()}`,
      title,
      description: `Рабочая история CRM-проекта «${title}»: обсуждение, решения, результат и следующие действия.`,
      taskType: 'crm_project',
      channel: 'crm',
    });
  }

  async function deleteProject(taskId: string, title: string) {
    if (deletingProjectId || !window.confirm(`Удалить проект «${title}» из списка? История останется в базе.`)) return;
    setDeletingProjectId(taskId);
    setError(null);
    try {
      await agentInteractions.deleteCrmProject(taskId);
      const remaining = projectTopics.filter((project) => project.task_id !== taskId);
      setProjectTopics(remaining);
      if (selectedProjectTaskId === taskId) {
        setSelectedProjectTaskId(remaining[0]?.task_id || '');
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось удалить CRM-проект');
    } finally {
      setDeletingProjectId('');
    }
  }

  const suggestedMissingProjects = useMemo(() => {
    const existingTypes = new Set(projectTopics.map((project) => project.project_type));
    return SUGGESTED_CRM_PROJECTS.filter((project) => {
      if (project.id === 'calls') return !existingTypes.has('calls');
      if (project.id === 'sms') return !existingTypes.has('sms_mailing');
      return true;
    });
  }, [projectTopics]);

  const selectedProject = projectTopics.find((project) => project.task_id === selectedProjectTaskId) || projectTopics[0] || null;

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

        <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
          <Card className="p-3">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">CRM-проекты</h2>
                <p className="text-xs text-gray-500">Темы Елены: история обсуждения и результат.</p>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="default"
                  size="sm"
                  onClick={createCustomProject}
                  disabled={creating}
                  aria-label="Добавить CRM-проект"
                  title="Добавить CRM-проект"
                  className="h-8 w-8 p-0 text-lg"
                >
                  +
                </Button>
                <Button variant="outline" size="sm" onClick={loadCrmData} disabled={loading} aria-label="Обновить CRM-проекты">↻</Button>
              </div>
            </div>

            <div className="space-y-2">
              {projectTopics.map((project) => (
                <div
                  key={project.task_id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedProjectTaskId(project.task_id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      setSelectedProjectTaskId(project.task_id);
                    }
                  }}
                  className={`w-full rounded-lg border p-3 text-left transition ${selectedProject?.task_id === project.task_id ? 'border-gold-400 bg-amber-50' : 'border-gray-200 bg-white hover:bg-gray-50'}`}
                >
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <Badge variant="outline">{crmProjectLabel(project)}</Badge>
                    <span className="text-[11px] text-gray-400">{project.history_count} сообщ.</span>
                  </div>
                  <div className="text-sm font-medium text-gray-900">{project.title}</div>
                  <div className="mt-1 text-xs text-gray-500">Статус: {project.crm_plan_status || project.status}</div>
                  {project.discussion_result ? (
                    <div className="mt-2 line-clamp-3 text-xs text-gray-600">Результат: {project.discussion_result}</div>
                  ) : (
                    <div className="mt-2 text-xs text-gray-400">Результат обсуждения пока не зафиксирован.</div>
                  )}
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={(event) => {
                      event.stopPropagation();
                      deleteProject(project.task_id, project.title);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        event.stopPropagation();
                        deleteProject(project.task_id, project.title);
                      }
                    }}
                    aria-disabled={deletingProjectId === project.task_id}
                    className={`mt-3 inline-block text-xs text-red-600 hover:text-red-800 ${deletingProjectId === project.task_id ? 'pointer-events-none opacity-50' : ''}`}
                  >
                    {deletingProjectId === project.task_id ? 'Удаление...' : 'Удалить проект'}
                  </span>
                </div>
              ))}

              {suggestedMissingProjects.map((project) => (
                <button
                  key={project.id}
                  type="button"
                  onClick={() => createProjectTopic(project)}
                  disabled={creating}
                  className="w-full rounded-lg border border-dashed border-gray-300 bg-gray-50 p-3 text-left hover:bg-white disabled:opacity-60"
                >
                  <div className="text-sm font-medium text-gray-700">{project.title}</div>
                  <div className="mt-1 text-xs text-gray-500">Создать тему-проект и вести историю внутри неё.</div>
                </button>
              ))}

              {projectTopics.length === 0 && suggestedMissingProjects.length === 0 ? (
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs text-gray-500">CRM-проектов пока нет.</div>
              ) : null}
            </div>
          </Card>

          <AgentBoardChat
            key={selectedProjectTaskId || 'crm-empty'}
            agentId="crm-agent"
            agentName="AI CRM"
            boardId="crm"
            aliases={['communication-agent', 'crm-board', 'loyalty']}
            crmMode
            selectedTaskIdOverride={selectedProjectTaskId}
            onSelectedTaskChange={setSelectedProjectTaskId}
          />
        </div>

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
