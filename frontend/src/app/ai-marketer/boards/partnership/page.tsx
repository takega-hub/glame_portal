'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import AgentBoardChat from '@/components/agents/AgentBoardChat';
import BoardHeader from '@/components/boards/BoardHeader';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { agentInteractions, aiMarketer, type AgentInteractionTask } from '@/lib/api';

const PARTNERSHIP_STAGES = ['Identified', 'Researching', 'Outreach', 'Negotiation', 'Approved', 'Planned', 'Executed', 'Measured'];
const PARTNER_CATEGORIES = [
  { value: 'hotels', label: 'Отели' },
  { value: 'restaurants', label: 'Рестораны' },
  { value: 'beauty', label: 'Бьюти-проекты' },
  { value: 'bridal', label: 'Свадебные студии' },
  { value: 'influencers', label: 'Инфлюенсеры' },
  { value: 'photographers', label: 'Фотографы' },
  { value: 'events', label: 'Мероприятия' },
  { value: 'fashion-community', label: 'Модные сообщества' },
];

function stageFromStatus(status: string) {
  const map: Record<string, string> = {
    pending: 'Identified',
    validating: 'Researching',
    validated: 'Outreach',
    pending_approval: 'Negotiation',
    approved: 'Approved',
    queued: 'Planned',
    processing: 'Executed',
    completed: 'Measured',
  };
  return map[status] || status;
}

function stageColor(stage: string) {
  const index = PARTNERSHIP_STAGES.indexOf(stage);
  if (index < 3) return 'bg-blue-100 text-blue-800';
  if (index < 6) return 'bg-yellow-100 text-yellow-800';
  if (index < 8) return 'bg-green-100 text-green-800';
  return 'bg-gray-100 text-gray-800';
}

function taskTitle(task: AgentInteractionTask) {
  return task.input_data?.partner_name || task.input_data?.title || task.task_context?.title || task.task_type.replaceAll('_', ' ');
}

function isPartnershipTask(task: AgentInteractionTask) {
  const text = `${task.source_agent} ${task.target_agent} ${task.task_type}`.toLowerCase();
  return text.includes('partnership') || text.includes('partner') || text.includes('pr-') || text.includes('influencer') || text.includes('collab');
}

export default function PartnershipBoard() {
  const router = useRouter();
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
    const loadedTasks = await agentInteractions.listTasks({ limit: 150 }).then((items) => items.filter(isPartnershipTask)).catch(() => []);
    setTasks(loadedTasks);
    setLoading(false);
  }

  async function createPartnerTask(seed?: { category?: string; title?: string }) {
    setCreating(true);
    setError(null);
    try {
      const { task: created } = await aiMarketer.ensureBoardTask('partnership', {
        source_agent: 'partnership-board',
        target_agent: 'pr-partnerships-agent',
        task_type: 'partnership_opportunity',
        priority: 3,
        input_data: {
          title: seed?.title || 'Добавить партнера',
          description: 'Оценить партнера, формат коллаборации, audience fit, campaign fit и ожидаемый эффект',
          expected_result: 'Партнерский brief: аудитория, формат, статус, следующий шаг',
          category: seed?.category,
          source_board: 'partnership',
        },
        task_context: {
          board: 'partnership',
          created_from: 'partnership_board',
        },
      });
      router.push(`/ai-marketer/tasks/${created.id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось создать партнерскую задачу');
    } finally {
      setCreating(false);
    }
  }

  const partners = useMemo(() => tasks.map((task) => ({
    id: task.id,
    name: taskTitle(task),
    category: task.input_data?.category || task.input_data?.partner_category || 'partnership',
    audienceFit: Number(task.input_data?.audience_fit || task.output_data?.audience_fit || 0),
    campaignFit: Number(task.input_data?.campaign_fit || task.output_data?.campaign_fit || 0),
    format: task.input_data?.format || task.input_data?.description || 'Партнерская задача',
    status: stageFromStatus(task.status),
    responsible: task.target_agent,
    expectedOutcome: task.input_data?.expected_result || task.output_data?.expected_outcome || '—',
  })), [tasks]);

  const getCategoryLabel = (cat: string) => PARTNER_CATEGORIES.find((c) => c.value === cat)?.label || cat;

  return (
    <div className="min-h-screen bg-gray-50">
      <BoardHeader
        title="Partnership Board"
        description="Партнерства, коллаборации, инфлюенсеры и локальные бизнесы как задачи PR-агента."
        boardId="partnership"
        actions={<Button variant="default" size="sm" onClick={() => createPartnerTask()} disabled={creating}>{creating ? 'Создание...' : 'Добавить партнера'}</Button>}
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {error && <Card className="p-3 text-sm text-red-700 border-red-200 bg-red-50">{error}</Card>}
        <AgentBoardChat
          agentId="pr-partnerships-agent"
          agentName="AI PR & Partnerships"
          boardId="partnership"
          aliases={['pr-partnerships', 'partnership-board']}
        />

        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Активные коллаборации</h2>
            <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>Обновить</Button>
          </div>
          <div className="space-y-3">
            {loading ? <Card className="p-5 text-sm text-gray-500">Загрузка...</Card> : null}
            {!loading && partners.length === 0 ? <Card className="p-5 text-sm text-gray-500">Партнерских задач пока нет.</Card> : null}
            {partners.map((partner) => (
              <Card key={partner.id} className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <Badge>{getCategoryLabel(partner.category)}</Badge>
                      <Badge className={stageColor(partner.status)}>{partner.status}</Badge>
                    </div>
                    <h3 className="font-medium text-gray-900">{partner.name}</h3>
                    <p className="text-sm text-gray-600 mt-1">{partner.format}</p>
                    <div className="flex flex-wrap gap-4 mt-2 text-xs text-gray-500">
                      <span>Audience fit: {partner.audienceFit || '—'}%</span>
                      <span>Campaign fit: {partner.campaignFit || '—'}%</span>
                      <span>Ответственный: {partner.responsible}</span>
                    </div>
                    <p className="text-sm text-green-600 mt-2">Ожидаемый эффект: {partner.expectedOutcome}</p>
                  </div>
                  <LinkButton href={`/ai-marketer/tasks/${partner.id}`}>Детали</LinkButton>
                </div>
              </Card>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Partnership Pipeline — Пайплайн партнерств</h2>
          <div className="overflow-x-auto">
            <div className="flex gap-2 min-w-max">
              {PARTNERSHIP_STAGES.map((stage) => (
                <div key={stage} className="w-44 flex-shrink-0">
                  <h3 className={`text-xs font-semibold p-2 rounded-t ${stageColor(stage)} text-center`}>{stage}</h3>
                  <div className="bg-gray-50 p-2 min-h-80 rounded-b border-x border-b border-gray-200 space-y-2">
                    {partners.filter((item) => item.status === stage).map((item) => (
                      <Card key={item.id} className="p-3 text-xs">
                        <p className="font-medium text-gray-900">{item.name}</p>
                        <p className="text-gray-500 mt-1">{getCategoryLabel(item.category)}</p>
                      </Card>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function LinkButton({ href, children }: { href: string; children: React.ReactNode }) {
  return <Link href={href} className="inline-flex h-9 items-center rounded-md border px-3 text-sm font-medium hover:bg-gray-50">{children}</Link>;
}
