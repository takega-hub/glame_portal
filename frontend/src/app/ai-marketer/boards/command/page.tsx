'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import BoardHeader from '@/components/boards/BoardHeader';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { agentInteractions, aiMarketer, apiClient, type AgentInteractionTask } from '@/lib/api';

type Health = 'healthy' | 'warning' | 'critical' | 'offline';
type ApprovalAction = 'approve' | 'reject' | 'revise';

const AGENTS = [
  { id: 'director-agent', name: 'AI Marketing Director', aliases: ['director-agent', 'marketing-director', 'marketing'] },
  { id: 'personal-media-agent', name: 'AI Personal Media', aliases: ['personal-media-agent', 'personal-media', 'personal'] },
  { id: 'brand-media-agent', name: 'AI Brand Media', aliases: ['brand-media-agent', 'brand-media', 'content', 'content-agent'] },
  { id: 'crm-agent', name: 'AI CRM', aliases: ['crm-agent', 'crm', 'communication', 'communication-agent'] },
  { id: 'pr-partnerships-agent', name: 'AI PR & Partnerships', aliases: ['pr-partnerships-agent', 'pr', 'partnership'] },
  { id: 'traffic-growth-agent', name: 'AI Traffic & Growth', aliases: ['traffic-growth-agent', 'traffic-growth', 'traffic', 'growth'] },
  { id: 'analytics-agent', name: 'AI Analytics', aliases: ['analytics-agent', 'analytics', 'report'] },
  { id: 'assortment-agent', name: 'AI Assortment', aliases: ['assortment-agent', 'assortment', 'inventory', 'product', 'marketing-inventory-agent'] },
];

const ACTIVE_STATUSES = new Set(['pending', 'validating', 'validated', 'pending_approval', 'approved', 'queued', 'processing']);
const APPROVAL_STATUSES = new Set(['pending', 'validated', 'pending_approval']);
const BLOCKED_STATUSES = new Set(['failed', 'rejected']);
const FINAL_MATCH_EXCLUDED_STATUSES = new Set(['deleted']);

const WEEKLY_FOCUS_AGENT_MAP: Record<string, string> = {
  assortment: 'assortment-agent',
  inventory: 'assortment-agent',
  crm: 'crm-agent',
  analytics: 'analytics-agent',
  'traffic-growth': 'traffic-growth-agent',
  'pr-partnerships': 'pr-partnerships-agent',
  'brand-media': 'brand-media-agent',
  'personal-media': 'personal-media-agent',
};

const formatNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const formatCurrency = new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 });

const n = (value: unknown) => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

function priorityLabel(priority?: number) {
  if (priority === 1) return 'P0';
  if (priority === 2) return 'P1';
  if (priority === 3) return 'P2';
  return 'P3';
}

function taskTitle(task: AgentInteractionTask) {
  return task.input_data?.title || task.task_context?.title || task.task_type.replaceAll('_', ' ');
}

function normalizeTaskText(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, ' ');
}

function findExistingWeeklyFocusTask(
  source: AgentInteractionTask,
  candidates: AgentInteractionTask[],
  targetAgent: string,
  sourceTitle: string
) {
  const normalizedTitle = normalizeTaskText(sourceTitle);
  return candidates.find((candidate) => {
    if (FINAL_MATCH_EXCLUDED_STATUSES.has(candidate.status)) return false;
    if (candidate.id === source.id) return false;
    const candidateTitle = normalizeTaskText(taskTitle(candidate));
    const sameTemplate = candidate.task_context?.template_id === source.id;
    const sameWeeklyTitle = Boolean(candidate.task_context?.weekly_focus) && candidateTitle === normalizedTitle;
    const sameCommandTitle = candidate.input_data?.source_board === 'command' && candidateTitle === normalizedTitle;
    const sameTaskShape = candidate.task_type === source.task_type && candidate.target_agent === targetAgent && candidateTitle === normalizedTitle;
    return sameTemplate || sameWeeklyTitle || sameCommandTitle || sameTaskShape;
  });
}

function taskRisk(task: AgentInteractionTask): 'low' | 'high' {
  return task.input_data?.risk_level === 'high' || task.task_context?.risk_level === 'high' ? 'high' : 'low';
}

function isOverdue(task: AgentInteractionTask) {
  if (!task.deadline_at || ['completed', 'cancelled', 'rejected'].includes(task.status)) return false;
  return new Date(task.deadline_at).getTime() < Date.now();
}

function deadlineLabel(task: AgentInteractionTask) {
  if (!task.deadline_at) return 'Без дедлайна';
  return new Date(task.deadline_at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    pending: 'Планирование',
    validating: 'Валидация',
    validated: 'Нужно согласование',
    pending_approval: 'Нужно согласование',
    approved: 'Одобрено',
    queued: 'В очереди',
    processing: 'В работе',
    completed: 'Готово',
    failed: 'Ошибка',
    rejected: 'Отклонено',
    cancelled: 'Отменено',
  };
  return map[status] || status;
}

function getStatusColor(status: Health) {
  switch (status) {
    case 'healthy':
      return 'bg-green-100 text-green-800';
    case 'warning':
      return 'bg-yellow-100 text-yellow-800';
    case 'critical':
      return 'bg-red-100 text-red-800';
    case 'offline':
      return 'bg-gray-100 text-gray-800';
  }
}

function getRiskColor(risk: string) {
  return risk === 'low' ? 'bg-green-100 text-green-800' : 'bg-orange-100 text-orange-800';
}

function agentMatches(task: AgentInteractionTask, aliases: string[]) {
  const text = `${task.source_agent} ${task.target_agent} ${task.task_type}`.toLowerCase();
  return aliases.some((alias) => text.includes(alias));
}

async function safeGet<T>(url: string): Promise<T | null> {
  try {
    const response = await apiClient.get<T>(url);
    return response.data;
  } catch (error) {
    console.error(`Failed to load ${url}`, error);
    return null;
  }
}

export default function MarketingCommandBoard() {
  const router = useRouter();
  const [tasks, setTasks] = useState<AgentInteractionTask[]>([]);
  const [inventory, setInventory] = useState<Record<string, any> | null>(null);
  const [aiDashboard, setAiDashboard] = useState<Record<string, any> | null>(null);
  const [storeVisits, setStoreVisits] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [creatingFocusId, setCreatingFocusId] = useState<string | null>(null);

  useEffect(() => {
    loadBoard();
  }, []);

  async function loadBoard() {
    setLoading(true);
    const [loadedTasks, inventoryData, aiData, visitsData] = await Promise.all([
      agentInteractions.listTasks({ limit: 150 }).catch(() => []),
      safeGet<Record<string, any>>('/api/inventory/dashboard?period=month'),
      safeGet<Record<string, any>>('/api/ai-marketer/dashboard'),
      safeGet<Record<string, any>>('/api/analytics/store-visits/daily?days=7'),
    ]);
    setTasks(loadedTasks);
    setInventory(inventoryData);
    setAiDashboard(aiData);
    setStoreVisits(visitsData);
    setLoading(false);
  }

  async function handleApproval(task: AgentInteractionTask, action: ApprovalAction) {
    const fallback = action === 'approve' ? 'Одобрено из Marketing Command Board' : action === 'reject' ? 'Отклонено из Marketing Command Board' : 'Нужна доработка';
    const comment = action === 'approve' ? fallback : window.prompt('Комментарий для агента', fallback) || fallback;
    setBusyTaskId(task.id);
    try {
      if (action === 'approve') {
        await agentInteractions.approveTask(task.id, comment);
      } else if (action === 'reject') {
        await agentInteractions.rejectTask(task.id, comment);
      } else {
        await agentInteractions.reviseTask(task.id, comment);
      }
      await loadBoard();
    } catch (error: any) {
      alert(error?.response?.data?.detail || 'Не удалось выполнить действие');
    } finally {
      setBusyTaskId(null);
    }
  }

  async function createWeeklyFocusTask(task: AgentInteractionTask) {
    const sourceTitle = taskTitle(task);
    const targetAgent = WEEKLY_FOCUS_AGENT_MAP[task.target_agent] || task.target_agent || 'marketing-director';
    if (task.id.length > 10) {
      router.push(`/ai-marketer/tasks/${task.id}`);
      return;
    }

    const deadline = new Date();
    deadline.setDate(deadline.getDate() + 7);

    setCreatingFocusId(task.id);
    try {
      const latestTasks = await agentInteractions.listTasks({ limit: 150 }).catch(() => tasks);
      setTasks(latestTasks);
      const existingTask = findExistingWeeklyFocusTask(task, latestTasks, targetAgent, sourceTitle);
      if (existingTask) {
        router.push(`/ai-marketer/tasks/${existingTask.id}`);
        return;
      }

      const { task: created } = await aiMarketer.ensureBoardTask('command', {
        source_agent: 'marketing-director',
        target_agent: targetAgent,
        task_type: task.task_type || 'weekly_focus',
        priority: task.priority || 3,
        deadline_at: deadline.toISOString(),
        input_data: {
          ...(task.input_data || {}),
          title: sourceTitle,
          description: task.input_data?.description || sourceTitle,
          expected_result: task.input_data?.expected_result || 'Готовое решение и план действий по фокусу недели',
          campaign: task.input_data?.campaign || 'weekly_focus',
          channel: task.input_data?.channel || 'command_board',
          source_board: 'command',
        },
        task_context: {
          ...(task.task_context || {}),
          title: sourceTitle,
          weekly_focus: true,
          board: 'command',
          created_from: 'weekly_focus_card',
          template_id: task.id,
        },
        requirements: {
          use_current_inventory: ['inventory_focus', 'assortment'].includes(task.task_type) || task.target_agent.includes('assortment'),
          use_customer_segments: task.task_type.includes('crm') || task.target_agent.includes('crm'),
          use_sales_and_traffic_data: task.task_type.includes('analytics') || task.target_agent.includes('analytics'),
        },
      });
      router.push(`/ai-marketer/tasks/${created.id}`);
    } catch (error: any) {
      alert(error?.response?.data?.detail || 'Не удалось создать задачу');
    } finally {
      setCreatingFocusId(null);
    }
  }

  function exportReport() {
    const payload = {
      generated_at: new Date().toISOString(),
      priority_tasks: priorityTasks,
      approvals,
      agents,
      analytics: analyticsSnapshot,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `glame-command-board-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const approvals = useMemo(
    () => tasks.filter((task) => APPROVAL_STATUSES.has(task.status)).sort((a, b) => a.priority - b.priority),
    [tasks]
  );

  const priorityTasks = useMemo(
    () =>
      tasks
        .filter((task) => task.priority <= 2 || BLOCKED_STATUSES.has(task.status) || isOverdue(task))
        .sort((a, b) => a.priority - b.priority)
        .slice(0, 8),
    [tasks]
  );

  const agents = useMemo(
    () =>
      AGENTS.map((agent) => {
        const agentTasks = tasks.filter((task) => agentMatches(task, agent.aliases));
        const activeTasks = agentTasks.filter((task) => ACTIVE_STATUSES.has(task.status)).length;
        const blockedTasks = agentTasks.filter((task) => BLOCKED_STATUSES.has(task.status) || isOverdue(task)).length;
        const pendingApprovals = agentTasks.filter((task) => APPROVAL_STATUSES.has(task.status)).length;
        const lastUpdate = agentTasks[0]?.created_at || null;
        const status: Health = blockedTasks > 0 ? 'critical' : pendingApprovals > 2 ? 'warning' : activeTasks > 0 ? 'healthy' : 'offline';
        return { ...agent, activeTasks, blockedTasks, pendingApprovals, lastUpdate, status };
      }),
    [tasks]
  );

  const weeklyFocus = useMemo(() => {
    const focusTasks = tasks
      .filter((task) => ACTIVE_STATUSES.has(task.status))
      .filter((task) => task.task_context?.campaign || task.input_data?.campaign || task.task_context?.weekly_focus || task.priority <= 2)
      .slice(0, 3);
    const fallbackTask = (id: string, title: string, taskType: string, targetAgent: string): AgentInteractionTask => ({
      id,
      source_agent: 'system',
      target_agent: targetAgent,
      task_type: taskType,
      task_context: {},
      input_data: { title },
      priority: 3,
      status: 'pending',
      created_at: new Date().toISOString(),
    });
    return focusTasks.length > 0
      ? focusTasks
      : [
          fallbackTask('inventory', 'Связать продуктовый фокус с текущими остатками', 'inventory_focus', 'assortment'),
          fallbackTask('crm', 'Подготовить CRM-сценарии по активным сегментам', 'crm_focus', 'crm'),
          fallbackTask('analytics', 'Собрать недельные выводы по продажам и трафику', 'weekly_review', 'analytics'),
        ];
  }, [tasks]);

  const visitors = useMemo(() => {
    const rows = storeVisits?.daily_data || storeVisits?.data || [];
    if (!Array.isArray(rows)) return 0;
    return rows.reduce((sum, row) => sum + n(row.visitors ?? row.visitor_count ?? row.visits), 0);
  }, [storeVisits]);

  const analyticsSnapshot = useMemo(
    () => [
      { label: 'Трафик 7 дней', value: formatNumber.format(visitors) },
      { label: 'Продажи месяц', value: formatCurrency.format(n(inventory?.sales?.revenue)) },
      { label: 'Чеки', value: formatNumber.format(n(inventory?.sales?.checks_count)) },
      { label: 'Средний чек', value: inventory?.sales?.avg_check ? formatCurrency.format(n(inventory.sales.avg_check)) : '—' },
      { label: 'CRM high risk', value: formatNumber.format(n(aiDashboard?.churn_risk?.high_risk)) },
      { label: 'Критические остатки', value: formatNumber.format(n(inventory?.stock?.critical_count)) },
    ],
    [aiDashboard, inventory, visitors]
  );

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <BoardHeader title="Marketing Command Board" description="Центральная операционная панель управления всеми процессами маркетинга" boardId="command" />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto" />
          <p className="mt-4 text-gray-600">Загрузка командной панели...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <BoardHeader
        title="Marketing Command Board"
        description="Центральная операционная панель: критические задачи, статусы AI-агентов, согласования, фокус недели и бизнес-снимок."
        boardId="command"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={loadBoard}>Обновить</Button>
            <Button variant="default" size="sm" onClick={exportReport}>Экспорт отчета</Button>
          </>
        }
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Priority Strip</h2>
          <div className="grid gap-3">
            {priorityTasks.length === 0 ? (
              <Card className="p-4 text-sm text-gray-500">Критических задач и просроченных согласований сейчас нет.</Card>
            ) : (
              priorityTasks.map((task) => (
                <TaskCard key={task.id} task={task} busy={busyTaskId === task.id} onAction={handleApproval} priority />
              ))
            )}
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Weekly Focus</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {weeklyFocus.map((task) => (
              <button
                key={task.id}
                type="button"
                className="text-left disabled:cursor-wait"
                disabled={creatingFocusId === task.id}
                onClick={() => createWeeklyFocusTask(task)}
              >
                <Card className="p-4 hover:border-pink-300 transition-colors min-h-[112px]">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge variant="outline">{priorityLabel(task.priority)}</Badge>
                    <Badge className="bg-gray-100 text-gray-700">{task.target_agent}</Badge>
                  </div>
                  <h3 className="font-medium text-gray-900">{taskTitle(task)}</h3>
                  <p className="text-sm text-gray-600 mt-1">
                    {creatingFocusId === task.id ? 'Создание задачи...' : statusLabel(task.status)}
                  </p>
                </Card>
              </button>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-3">AI Agent Status</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {agents.map((agent) => (
              <Card key={agent.id} className="p-4">
                <div className="flex items-center justify-between mb-3 gap-2">
                  <h3 className="font-medium text-gray-900 text-sm">{agent.name}</h3>
                  <Badge className={getStatusColor(agent.status)}>{agent.status}</Badge>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div>
                    <p className="font-semibold text-gray-900">{agent.activeTasks}</p>
                    <p className="text-gray-500">активных</p>
                  </div>
                  <div>
                    <p className="font-semibold text-red-600">{agent.blockedTasks}</p>
                    <p className="text-gray-500">блок</p>
                  </div>
                  <div>
                    <p className="font-semibold text-orange-600">{agent.pendingApprovals}</p>
                    <p className="text-gray-500">approval</p>
                  </div>
                </div>
                <p className="text-[11px] text-gray-400 mt-3">
                  Last update: {agent.lastUpdate ? new Date(agent.lastUpdate).toLocaleString('ru-RU') : 'нет задач'}
                </p>
              </Card>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Approval Queue</h2>
          <div className="space-y-3">
            {approvals.length === 0 ? (
              <Card className="p-4 text-sm text-gray-500">Очередь согласований пуста.</Card>
            ) : (
              approvals.map((task) => (
                <TaskCard key={task.id} task={task} busy={busyTaskId === task.id} onAction={handleApproval} />
              ))
            )}
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Analytics Snapshot</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {analyticsSnapshot.map((metric) => (
              <Card key={metric.label} className="p-4 text-center">
                <p className="text-2xl font-bold text-gray-900">{metric.value}</p>
                <p className="text-xs text-gray-500 mt-1">{metric.label}</p>
              </Card>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function TaskCard({
  task,
  busy,
  onAction,
  priority = false,
}: {
  task: AgentInteractionTask;
  busy: boolean;
  onAction: (task: AgentInteractionTask, action: ApprovalAction) => void;
  priority?: boolean;
}) {
  const risk = taskRisk(task);
  const overdue = isOverdue(task);
  return (
    <Card className={`p-4 ${priority || overdue ? 'border-l-4 border-l-red-500' : ''}`}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <Badge variant="outline" className={task.priority <= 2 ? 'bg-red-50' : ''}>{priorityLabel(task.priority)}</Badge>
            <Badge className={getRiskColor(risk)}>{risk}-risk</Badge>
            <Badge className="bg-gray-100 text-gray-700">{statusLabel(task.status)}</Badge>
            {overdue && <Badge className="bg-red-100 text-red-800">overdue</Badge>}
            {task.input_data?.city_context && <Badge className="bg-blue-50 text-blue-700">{task.input_data.city_context}</Badge>}
            {task.input_data?.dna && <Badge className="bg-purple-50 text-purple-700">{task.input_data.dna}</Badge>}
          </div>
          <p className="font-medium text-gray-900">{taskTitle(task)}</p>
          <p className="text-sm text-gray-500 mt-1">
            {task.source_agent} → {task.target_agent} · Дедлайн: {deadlineLabel(task)}
          </p>
          {task.input_data?.expected_result && (
            <p className="text-sm text-gray-600 mt-2">Ожидаемый результат: {task.input_data.expected_result}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          {APPROVAL_STATUSES.has(task.status) && (
            <>
              <Button size="sm" className="bg-green-600 hover:bg-green-700" disabled={busy} onClick={() => onAction(task, 'approve')}>Approve</Button>
              <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction(task, 'revise')}>Revise</Button>
              <Button size="sm" variant="destructive" disabled={busy} onClick={() => onAction(task, 'reject')}>Reject</Button>
            </>
          )}
          <Link href={`/ai-marketer/tasks/${task.id}`}>
            <Button size="sm" variant="outline">Подробнее</Button>
          </Link>
        </div>
      </div>
    </Card>
  );
}
