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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { agentInteractions, aiMarketer, api, type AgentInteractionTask } from '@/lib/api';

const PRODUCTION_STAGES = ['Idea', 'Briefed', 'Planned', 'In Production', 'Editing', 'Needs Approval', 'Approved', 'Scheduled', 'Published', 'Measured', 'Done'];
const MEDIA_LAYERS = [
  { value: 'all', label: 'Все медиа' },
  { value: 'personal', label: 'Personal Media' },
  { value: 'brand', label: 'GLAME Brand Media' },
  { value: 'campaign', label: 'Campaign' },
  { value: 'crm', label: 'CRM Support Content' },
  { value: 'partnership', label: 'Partnership Content' },
  { value: 'app', label: 'App Content' },
];
const CONTENT_TYPES = ['all', 'reels', 'stories', 'carousel', 'hero-shoot', 'fast-content', 'bts', 'styling', 'arrivals'];
const CITY_FILTERS = [
  { value: 'all', label: 'Все города' },
  { value: 'simferopol', label: 'Симферополь' },
  { value: 'yalta', label: 'Ялта' },
];
const DNA_FILTERS = ['all', 'classic', 'dramatic', 'romantic', 'naturalistic'];

type ContentRow = {
  id: string;
  title: string;
  hook: string;
  contentType: string;
  platform: string;
  city: string;
  dna: string;
  mediaLayer: string;
  status: string;
  publishDate: string;
  assignedTo: string;
  href?: string;
};

function stageFromStatus(status: string) {
  const map: Record<string, string> = {
    pending: 'Idea',
    validating: 'Briefed',
    validated: 'Needs Approval',
    pending_approval: 'Needs Approval',
    approved: 'Approved',
    queued: 'Scheduled',
    processing: 'In Production',
    completed: 'Done',
    failed: 'Editing',
    published: 'Published',
    scheduled: 'Scheduled',
    draft: 'Idea',
  };
  return map[status] || status;
}

function stageColor(stage: string) {
  const index = PRODUCTION_STAGES.indexOf(stage);
  if (index < 3) return 'bg-blue-100 text-blue-800';
  if (index < 6) return 'bg-yellow-100 text-yellow-800';
  if (index < 9) return 'bg-green-100 text-green-800';
  return 'bg-gray-100 text-gray-800';
}

function taskTitle(task: AgentInteractionTask) {
  return task.input_data?.title || task.task_context?.title || task.task_type.replaceAll('_', ' ');
}

function isContentTask(task: AgentInteractionTask) {
  const text = `${task.source_agent} ${task.target_agent} ${task.task_type}`.toLowerCase();
  return text.includes('content') || text.includes('brand-media') || text.includes('personal-media') || text.includes('publication');
}

export default function ContentBoard() {
  const router = useRouter();
  const [viewMode, setViewMode] = useState<'calendar' | 'pipeline'>('calendar');
  const [mediaFilter, setMediaFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [cityFilter, setCityFilter] = useState('all');
  const [dnaFilter, setDnaFilter] = useState('all');
  const [tasks, setTasks] = useState<AgentInteractionTask[]>([]);
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(null);
    const [loadedTasks, loadedPlans] = await Promise.all([
      agentInteractions.listTasks({ limit: 200 }).then((items) => items.filter(isContentTask)).catch(() => []),
      api.listContentPlans({ limit: 30 }).catch(() => []),
    ]);
    setTasks(loadedTasks);
    setPlans(Array.isArray(loadedPlans) ? loadedPlans : []);
    setLoading(false);
  }

  async function createContentTask(seed?: Partial<ContentRow>) {
    setCreating(true);
    setError(null);
    try {
      const { task: created } = await aiMarketer.ensureBoardTask('content', {
        source_agent: 'content-board',
        target_agent: seed?.mediaLayer === 'personal' ? 'personal-media-agent' : 'brand-media-agent',
        task_type: 'content_production',
        priority: 3,
        input_data: {
          title: seed?.title || 'Создать контент',
          description: seed?.hook || 'Подготовить контент с учетом медиа-слоя, города, DNA и канала публикации',
          expected_result: 'Готовый контент-пакет: идея, текст, визуальный brief, канал и дата публикации',
          content_type: seed?.contentType || (typeFilter !== 'all' ? typeFilter : undefined),
          media_layer: seed?.mediaLayer || (mediaFilter !== 'all' ? mediaFilter : 'brand'),
          city: seed?.city || (cityFilter !== 'all' ? cityFilter : undefined),
          dna: seed?.dna || (dnaFilter !== 'all' ? dnaFilter : undefined),
          platform: seed?.platform || 'Instagram',
          source_board: 'content',
        },
        task_context: {
          board: 'content',
          created_from: 'content_board',
          filters: { mediaFilter, typeFilter, cityFilter, dnaFilter },
        },
      });
      router.push(`/ai-marketer/tasks/${created.id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось создать задачу контента');
    } finally {
      setCreating(false);
    }
  }

  const rows = useMemo<ContentRow[]>(() => {
    const taskRows = tasks.map((task) => ({
      id: task.id,
      title: taskTitle(task),
      hook: task.input_data?.hook || task.input_data?.description || task.output_data?.summary || 'Задача контент-производства',
      contentType: task.input_data?.content_type || task.input_data?.type || task.task_type,
      platform: task.input_data?.platform || task.input_data?.channel || '—',
      city: task.input_data?.city || 'all',
      dna: task.input_data?.dna || 'all',
      mediaLayer: task.input_data?.media_layer || task.task_context?.media_layer || (task.target_agent === 'personal-media' || task.target_agent === 'personal-media-agent' ? 'personal' : 'brand'),
      status: stageFromStatus(task.status),
      publishDate: task.deadline_at ? new Date(task.deadline_at).toLocaleDateString('ru-RU') : new Date(task.created_at).toLocaleDateString('ru-RU'),
      assignedTo: task.target_agent,
      href: `/ai-marketer/tasks/${task.id}`,
    }));
    const planRows = plans.map((plan: any) => ({
      id: String(plan.id),
      title: plan.title || plan.name || 'Контент-план',
      hook: plan.description || plan.objective || 'Контент-план из backend',
      contentType: 'content-plan',
      platform: Array.isArray(plan.platforms) ? plan.platforms.join(', ') : plan.platform || '—',
      city: plan.city || 'all',
      dna: plan.dna || 'all',
      mediaLayer: plan.media_layer || 'brand',
      status: stageFromStatus(plan.status || 'planned'),
      publishDate: plan.start_date ? new Date(plan.start_date).toLocaleDateString('ru-RU') : '—',
      assignedTo: 'content-plan',
    }));
    return [...taskRows, ...planRows];
  }, [plans, tasks]);

  const filteredRows = rows.filter((item) => {
    if (mediaFilter !== 'all' && item.mediaLayer !== mediaFilter) return false;
    if (typeFilter !== 'all' && item.contentType !== typeFilter) return false;
    if (cityFilter !== 'all' && item.city !== cityFilter) return false;
    if (dnaFilter !== 'all' && item.dna !== dnaFilter) return false;
    return true;
  });

  return (
    <div className="min-h-screen bg-gray-50">
      <BoardHeader
        title="Content Board"
        description="Контент-производство, публикации и задачи AI-агентов по всем медиа-слоям."
        boardId="content"
        actions={<Button variant="default" size="sm" onClick={() => createContentTask()} disabled={creating}>{creating ? 'Создание...' : 'Создать контент'}</Button>}
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {error && <Card className="p-3 text-sm text-red-700 border-red-200 bg-red-50">{error}</Card>}
        <AgentBoardChat
          agentId="brand-media-agent"
          agentName="AI Brand Media"
          boardId="content"
          aliases={['content-agent', 'brand-media', 'content-board']}
        />

        <section className="bg-white rounded-lg shadow p-4">
          <div className="flex items-center justify-between gap-3 mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Фильтры контента</h2>
            <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>Обновить</Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <FilterSelect label="Медиа-слой" value={mediaFilter} onChange={setMediaFilter} items={MEDIA_LAYERS} />
            <FilterSelect label="Тип контента" value={typeFilter} onChange={setTypeFilter} items={CONTENT_TYPES.map((value) => ({ value, label: value === 'all' ? 'Все типы' : value }))} />
            <FilterSelect label="Город" value={cityFilter} onChange={setCityFilter} items={CITY_FILTERS} />
            <FilterSelect label="Стиль (DNA)" value={dnaFilter} onChange={setDnaFilter} items={DNA_FILTERS.map((value) => ({ value, label: value === 'all' ? 'Все стили' : value }))} />
          </div>
          <div className="mt-4 flex items-center justify-end">
            <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as 'calendar' | 'pipeline')}>
              <TabsList>
                <TabsTrigger value="calendar">Календарь</TabsTrigger>
                <TabsTrigger value="pipeline">Пайплайн</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
        </section>

        {viewMode === 'calendar' ? (
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Календарь контента</h2>
            <div className="grid gap-4">
              {loading ? <Card className="p-4 text-sm text-gray-500">Загрузка...</Card> : null}
              {!loading && filteredRows.length === 0 ? <Card className="p-4 text-sm text-gray-500">Контент-задач по текущим фильтрам нет.</Card> : null}
              {filteredRows.map((item) => (
                <Card key={item.id} className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        <Badge>{item.contentType}</Badge>
                        <Badge className={stageColor(item.status)}>{item.status}</Badge>
                        {item.city !== 'all' && <Badge variant="outline">{item.city}</Badge>}
                        {item.dna !== 'all' && <Badge variant="outline">{item.dna}</Badge>}
                      </div>
                      <h3 className="font-medium text-gray-900">{item.title}</h3>
                      <p className="text-sm text-gray-600 mt-1">{item.hook}</p>
                      <div className="text-xs text-gray-500 mt-2">
                        Платформа: {item.platform} • Дата: {item.publishDate} • Ответственный: {item.assignedTo}
                      </div>
                    </div>
                    {item.href ? <LinkButton href={item.href}>Открыть</LinkButton> : <Button size="sm" variant="outline" onClick={() => createContentTask(item)}>Создать задачу</Button>}
                  </div>
                </Card>
              ))}
            </div>
          </section>
        ) : (
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Производственный пайплайн</h2>
            <div className="overflow-x-auto">
              <div className="flex gap-2 min-w-max">
                {PRODUCTION_STAGES.map((stage) => (
                  <div key={stage} className="w-64 flex-shrink-0">
                    <h3 className={`text-xs font-semibold p-2 rounded-t ${stageColor(stage)} text-center`}>{stage}</h3>
                    <div className="bg-gray-50 p-2 min-h-96 rounded-b border-x border-b border-gray-200 space-y-2">
                      {filteredRows.filter((item) => item.status === stage).map((item) => (
                        <Card key={item.id} className="p-3 text-xs">
                          <p className="font-medium text-gray-900">{item.title}</p>
                          <p className="text-gray-500 mt-1">{item.platform} • {item.city}</p>
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

function FilterSelect({ label, value, onChange, items }: { label: string; value: string; onChange: (value: string) => void; items: Array<{ value: string; label: string }> }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger><SelectValue /></SelectTrigger>
        <SelectContent>
          {items.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
}

function LinkButton({ href, children }: { href: string; children: React.ReactNode }) {
  return <Link href={href} className="inline-flex h-9 items-center rounded-md bg-gray-900 px-3 text-sm font-medium text-white hover:bg-gray-800">{children}</Link>;
}
