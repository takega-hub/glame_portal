'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import AgentBoardChat from '@/components/agents/AgentBoardChat';
import BoardHeader from '@/components/boards/BoardHeader';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { agentInteractions, aiMarketer, api, type AgentInteractionTask } from '@/lib/api';

const formatNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });

function taskTitle(task: AgentInteractionTask) {
  return task.input_data?.title || task.task_context?.title || task.task_type.replaceAll('_', ' ');
}

function isPersonalTask(task: AgentInteractionTask) {
  const text = `${task.source_agent} ${task.target_agent} ${task.task_type}`.toLowerCase();
  return text.includes('personal-media') || text.includes('personal') || text.includes('elena');
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    pending: 'Идея',
    validating: 'Планирование',
    validated: 'На согласовании',
    pending_approval: 'На согласовании',
    approved: 'Одобрено',
    queued: 'Запланировано',
    processing: 'В работе',
    completed: 'Завершено',
    failed: 'Ошибка',
    cancelled: 'Отменено',
  };
  return map[status] || status;
}

export default function PersonalMediaBoard() {
  const router = useRouter();
  const [tasks, setTasks] = useState<AgentInteractionTask[]>([]);
  const [contentPerformance, setContentPerformance] = useState<Record<string, any> | null>(null);
  const [engagement, setEngagement] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(null);
    const [loadedTasks, performanceData, engagementData] = await Promise.all([
      agentInteractions.listTasks({ limit: 150 }).then((items) => items.filter(isPersonalTask)).catch(() => []),
      api.getContentPerformance(30).catch(() => null),
      api.getEngagementMetrics(30).catch(() => null),
    ]);
    setTasks(loadedTasks);
    setContentPerformance(performanceData);
    setEngagement(engagementData);
    setLoading(false);
  }

  async function createPostTask(seed?: { title?: string; description?: string; storyline?: string }) {
    setCreating(true);
    setError(null);
    try {
      const { task: created } = await aiMarketer.ensureBoardTask('personal-media', {
        source_agent: 'personal-media-board',
        target_agent: 'personal-media-agent',
        task_type: 'personal_media_post',
        priority: 3,
        input_data: {
          title: seed?.title || 'Создать пост для личного блога',
          description: seed?.description || 'Подготовить личный пост Елены с bridge к GLAME',
          expected_result: 'Готовый пост: идея, текст, CTA, платформа и план публикации',
          storyline: seed?.storyline,
          media_layer: 'personal',
          platform: 'Instagram',
          source_board: 'personal-media',
        },
        task_context: {
          board: 'personal-media',
          created_from: 'personal_media_board',
        },
      });
      router.push(`/ai-marketer/tasks/${created.id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось создать задачу личного медиа');
    } finally {
      setCreating(false);
    }
  }

  const bridgeMetrics = useMemo(() => {
    const taskMentions = tasks.reduce((sum, task) => sum + Number(task.output_metadata?.app_mentions || task.output_data?.app_mentions || 0), 0);
    const taskVisits = tasks.reduce((sum, task) => sum + Number(task.output_metadata?.store_visits || task.output_data?.store_visits || 0), 0);
    return [
      { label: 'Упоминаний приложения', value: taskMentions || Number(contentPerformance?.app_mentions || contentPerformance?.mentions || 0) },
      { label: 'Переходов в магазины', value: taskVisits || Number(engagement?.store_visits || engagement?.visits || 0) },
      { label: 'Активных задач', value: tasks.filter((task) => !['completed', 'cancelled', 'failed'].includes(task.status)).length },
    ];
  }, [contentPerformance, engagement, tasks]);

  const storylines = useMemo(() => {
    const counts = new Map<string, number>();
    tasks.forEach((task) => {
      const key = task.input_data?.storyline || task.task_context?.storyline || task.input_data?.theme;
      if (key) counts.set(String(key), (counts.get(String(key)) || 0) + 1);
    });
    return Array.from(counts.entries()).map(([name, count]) => ({ name, count }));
  }, [tasks]);

  return (
    <div className="min-h-screen bg-gray-50">
      <BoardHeader
        title="Personal Media Board"
        description="Личный медиа-блог Елены: задачи, экспертные сюжетные линии и bridge-эффект на GLAME."
        boardId="personal-media"
        actions={<Button variant="default" size="sm" onClick={() => createPostTask()} disabled={creating}>{creating ? 'Создание...' : 'Создать пост'}</Button>}
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-8">
        {error && <Card className="p-3 text-sm text-red-700 border-red-200 bg-red-50">{error}</Card>}

        <AgentBoardChat
          agentId="personal-media-agent"
          agentName="AI Personal Media"
          boardId="personal-media"
          aliases={['personal-media', 'elena']}
        />

        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Viral Opportunities — Идеи из текущих задач</h2>
            <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>Обновить</Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {tasks.filter((task) => ['pending', 'validating', 'validated', 'pending_approval'].includes(task.status)).slice(0, 4).map((task) => (
              <Card key={task.id} className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="font-medium text-gray-900">{taskTitle(task)}</h3>
                    <p className="text-sm text-gray-600 mt-1">{task.input_data?.description || task.input_data?.hook || 'Задача личного медиа'}</p>
                    <p className="text-sm text-green-600 mt-2">Статус: {statusLabel(task.status)}</p>
                  </div>
                  <LinkButton href={`/ai-marketer/tasks/${task.id}`}>Открыть</LinkButton>
                </div>
              </Card>
            ))}
            {!loading && tasks.length === 0 ? <Card className="p-5 text-sm text-gray-500">Задач личного медиа пока нет.</Card> : null}
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Authority Layer — Экспертные направления</h2>
          <Card className="p-5">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {['Бизнес-наблюдения', 'Стилистическая логика', 'Экспертные мнения'].map((title) => (
                <button key={title} type="button" onClick={() => createPostTask({ title, storyline: title })} className="p-4 bg-gray-50 rounded-lg text-left hover:bg-gray-100">
                  <h3 className="font-medium text-gray-900">{title}</h3>
                  <p className="text-sm text-gray-600 mt-1">Создать задачу по направлению</p>
                </button>
              ))}
            </div>
          </Card>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Bridge to GLAME — Переходы на брендовые ресурсы</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            {bridgeMetrics.map((metric) => (
              <Card key={metric.label} className="p-4 text-center">
                <p className="text-3xl font-bold text-gray-900">{loading ? '...' : formatNumber.format(metric.value)}</p>
                <p className="text-sm text-gray-500 mt-1">{metric.label}</p>
              </Card>
            ))}
          </div>
          <div className="space-y-3">
            {tasks.slice(0, 8).map((task) => (
              <Card key={task.id} className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <Badge>{task.input_data?.content_type || task.task_type}</Badge>
                      <Badge variant="outline">{task.input_data?.platform || 'personal media'}</Badge>
                    </div>
                    <h3 className="font-medium text-gray-900">{taskTitle(task)}</h3>
                    <p className="text-sm text-gray-500 mt-1">Дата: {new Date(task.created_at).toLocaleDateString('ru-RU')} • Статус: {statusLabel(task.status)}</p>
                  </div>
                  <LinkButton href={`/ai-marketer/tasks/${task.id}`}>Детали</LinkButton>
                </div>
              </Card>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Personal Storylines — Постоянные сюжетные линии</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {storylines.length === 0 ? <Card className="p-4 text-sm text-gray-500">Сюжетные линии появятся из задач личного медиа.</Card> : null}
            {storylines.map((story) => (
              <Card key={story.name} className="p-4">
                <h3 className="font-medium text-gray-900">{story.name}</h3>
                <p className="text-sm text-gray-600 mt-1">Задач в линии: {story.count}</p>
              </Card>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function LinkButton({ href, children }: { href: string; children: React.ReactNode }) {
  return <Link href={href} className="inline-flex h-9 items-center rounded-md border px-3 text-sm font-medium hover:bg-gray-50">{children}</Link>;
}
