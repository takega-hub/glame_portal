'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import AgentBoardChat from '@/components/agents/AgentBoardChat';
import BoardHeader from '@/components/boards/BoardHeader';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { agentInteractions, aiMarketer, api, type AgentInteractionTask, type ContentProjectTopic, type CampaignMediaAsset, type CampaignMediaResponse } from '@/lib/api';

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
  const [viewMode, setViewMode] = useState<'calendar' | 'pipeline'>('calendar');
  const [mediaFilter, setMediaFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [cityFilter, setCityFilter] = useState('all');
  const [dnaFilter, setDnaFilter] = useState('all');
  const [tasks, setTasks] = useState<AgentInteractionTask[]>([]);
  const [projectTopics, setProjectTopics] = useState<ContentProjectTopic[]>([]);
  const [selectedProjectTaskId, setSelectedProjectTaskId] = useState('');
  const [campaignMedia, setCampaignMedia] = useState<CampaignMediaResponse | null>(null);
  const [mediaLoading, setMediaLoading] = useState(false);
  const [platformQuery, setPlatformQuery] = useState('');
  const [platformCategory, setPlatformCategory] = useState('all');
  const [platformAssets, setPlatformAssets] = useState<CampaignMediaAsset[]>([]);
  const [platformSearchPerformed, setPlatformSearchPerformed] = useState(false);
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [runningTaskId, setRunningTaskId] = useState('');
  const [deletingProjectId, setDeletingProjectId] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (!selectedProjectTaskId) {
      setCampaignMedia(null);
      return;
    }
    setMediaLoading(true);
    agentInteractions.getContentProjectCampaignMedia(selectedProjectTaskId)
      .then(setCampaignMedia)
      .catch(() => setCampaignMedia(null))
      .finally(() => setMediaLoading(false));
  }, [selectedProjectTaskId]);

  async function loadData() {
    setLoading(true);
    setError(null);
    const [loadedTasks, loadedPlans, loadedProjects] = await Promise.all([
      agentInteractions.listTasks({ limit: 200 }).then((items) => items.filter(isContentTask)).catch(() => []),
      api.listContentPlans({ limit: 30 }).catch(() => []),
      agentInteractions.listContentProjects(50).catch(() => []),
    ]);
    setTasks(loadedTasks);
    setPlans(Array.isArray(loadedPlans) ? loadedPlans : []);
    setProjectTopics(loadedProjects);
    if (!selectedProjectTaskId && loadedProjects[0]?.task_id) {
      setSelectedProjectTaskId(loadedProjects[0].task_id);
    } else if (selectedProjectTaskId && !loadedProjects.some((project) => project.task_id === selectedProjectTaskId)) {
      setSelectedProjectTaskId(loadedProjects[0]?.task_id || '');
    }
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
      setSelectedProjectTaskId(created.id);
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось создать задачу контента');
    } finally {
      setCreating(false);
    }
  }

  async function deleteProject(taskId: string, title: string) {
    if (deletingProjectId || !window.confirm(`Удалить проект «${title}» из списка? История сообщений и аудит сохранятся.`)) return;
    setDeletingProjectId(taskId);
    setError(null);
    try {
      await agentInteractions.deleteContentProject(taskId);
      const remaining = projectTopics.filter((project) => project.task_id !== taskId);
      setProjectTopics(remaining);
      if (selectedProjectTaskId === taskId) setSelectedProjectTaskId(remaining[0]?.task_id || '');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось удалить контент-проект');
    } finally {
      setDeletingProjectId('');
    }
  }

  async function approveAndRunProject(taskId: string) {
    if (runningTaskId) return;
    setRunningTaskId(taskId);
    setError(null);
    try {
      const task = await agentInteractions.getTask(taskId);
      if (task.status === 'pending_approval' || task.status === 'draft' || task.status === 'pending') {
        await agentInteractions.approveTask(taskId, 'Согласовано для подготовки внутреннего пакета креативов. Публикация наружу запрещена.');
      }
      await agentInteractions.processTask(taskId);
      await loadData();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось запустить задачу AI Brand Media');
      await loadData();
    } finally {
      setRunningTaskId('');
    }
  }

  async function uploadCampaignMedia(files: FileList | null) {
    if (!selectedProjectTaskId || !files?.length) return;
    setMediaLoading(true);
    setError(null);
    try {
      let media = campaignMedia;
      for (const file of Array.from(files)) {
        const uploaded = await api.uploadAppAdminMedia('store', file);
        media = await agentInteractions.addContentProjectCampaignMediaUpload(selectedProjectTaskId, {
          url: uploaded.url,
          title: file.name.replace(/\.[^.]+$/, '') || 'Пользовательское фото',
          kind: 'custom',
        });
      }
      setCampaignMedia(media || null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось загрузить изображение в медиатеку кампании');
    } finally {
      setMediaLoading(false);
    }
  }

  async function addMediaFromLibrary(asset: CampaignMediaAsset) {
    if (!selectedProjectTaskId || !campaignMedia) return;
    setMediaLoading(true);
    try {
      const ids = Array.from(new Set([...campaignMedia.assets.map((item) => item.id), asset.id]));
      setCampaignMedia(await agentInteractions.saveContentProjectCampaignMediaSelection(selectedProjectTaskId, ids, [asset]));
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось добавить изображение в кампанию');
    } finally {
      setMediaLoading(false);
    }
  }

  async function searchPlatformMedia() {
    if (!selectedProjectTaskId) return;
    setMediaLoading(true);
    try {
      const media = await agentInteractions.getContentProjectCampaignMedia(selectedProjectTaskId, { query: platformQuery.trim() || undefined, category: platformCategory });
      setPlatformAssets(media.available_assets);
      setPlatformSearchPerformed(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось найти изображения');
    } finally {
      setMediaLoading(false);
    }
  }

  async function removeCampaignMedia(assetId: string) {
    if (!selectedProjectTaskId || !campaignMedia) return;
    setMediaLoading(true);
    try {
      setCampaignMedia(await agentInteractions.removeContentProjectCampaignMediaAsset(selectedProjectTaskId, assetId));
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось удалить изображение из кампании');
    } finally {
      setMediaLoading(false);
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
        <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
          <Card className="p-3">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">Контент-проекты</h2>
                <p className="text-xs text-gray-500">Каждая задача — отдельная тема и история AI Brand Media.</p>
              </div>
              <div className="flex items-center gap-1">
                <Button variant="default" size="sm" onClick={() => createContentTask()} disabled={creating} className="h-8 w-8 p-0 text-lg" aria-label="Добавить контент-проект" title="Добавить контент-проект">+</Button>
                <Button variant="outline" size="sm" onClick={loadData} disabled={loading} aria-label="Обновить контент-проекты">↻</Button>
              </div>
            </div>
            <div className="space-y-2">
              {projectTopics.map((project) => (
                <div key={project.task_id} role="button" tabIndex={0} onClick={() => setSelectedProjectTaskId(project.task_id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedProjectTaskId(project.task_id); } }} className={`w-full rounded-lg border p-3 text-left transition ${selectedProjectTaskId === project.task_id ? 'border-gold-400 bg-amber-50' : 'border-gray-200 bg-white hover:bg-gray-50'}`}>
                  <div className="mb-2 flex items-center justify-between gap-2"><Badge variant="outline">{project.content_type || 'content'}</Badge><span className="text-[11px] text-gray-400">{project.history_count} сообщ.</span></div>
                  <div className="text-sm font-medium text-gray-900">{project.title}</div>
                  <div className="mt-1 text-xs text-gray-500">Статус: {project.status}</div>
                  {project.discussion_result ? <div className="mt-2 line-clamp-3 text-xs text-gray-600">Результат: {project.discussion_result}</div> : <div className="mt-2 text-xs text-gray-400">Результат пока не зафиксирован.</div>}
                  <span role="button" tabIndex={0} onClick={(event) => { event.stopPropagation(); deleteProject(project.task_id, project.title); }} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); deleteProject(project.task_id, project.title); } }} className={`mt-3 inline-block text-xs text-red-600 hover:text-red-800 ${deletingProjectId === project.task_id ? 'pointer-events-none opacity-50' : ''}`}>{deletingProjectId === project.task_id ? 'Удаление...' : 'Удалить проект'}</span>
                </div>
              ))}
              {!loading && projectTopics.length === 0 && <div className="rounded-lg border border-dashed border-gray-300 p-3 text-xs text-gray-500">Создайте первый контент-проект — он появится здесь.</div>}
            </div>
          </Card>
          <div className="space-y-3">
            {selectedProjectTaskId && (() => {
              const selected = projectTopics.find((project) => project.task_id === selectedProjectTaskId);
              const actionable = selected && ['pending_approval', 'pending', 'draft', 'approved', 'queued'].includes(selected.status);
              return actionable ? <Card className="flex flex-wrap items-center justify-between gap-3 border-amber-200 bg-amber-50 p-3"><div><div className="text-sm font-medium text-gray-900">Пакет готовится только после согласования</div><div className="text-xs text-gray-600">Агент создаст внутренние тексты и ТЗ; объявления и медиафайлы не публикуются автоматически.</div></div><Button size="sm" onClick={() => approveAndRunProject(selectedProjectTaskId)} disabled={runningTaskId === selectedProjectTaskId}>{runningTaskId === selectedProjectTaskId ? 'Подготовка...' : selected?.status === 'pending_approval' ? 'Согласовать и подготовить' : 'Подготовить пакет'}</Button></Card> : null;
            })()}
            {selectedProjectTaskId && (
              <Card className="p-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">Медиатека кампании</h3>
                    <p className="text-xs text-gray-500">Агент получает эту подборку при подготовке креативов.</p>
                  </div>
                  <div className="flex gap-2"><label className="inline-flex h-8 cursor-pointer items-center rounded-md border border-gray-300 bg-white px-3 text-xs font-medium hover:bg-gray-50"><input type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={(event) => { uploadCampaignMedia(event.target.files); event.currentTarget.value = ''; }} />Загрузить фото</label><Button size="sm" variant="outline" onClick={() => { setMediaLoading(true); agentInteractions.getContentProjectCampaignMedia(selectedProjectTaskId).then(setCampaignMedia).catch(() => setCampaignMedia(null)).finally(() => setMediaLoading(false)); }} disabled={mediaLoading}>{mediaLoading ? 'Загрузка...' : 'Обновить'}</Button></div>
                </div>
                {campaignMedia?.assets?.length ? <><p className="mb-2 text-xs font-medium text-gray-700">Выбрано для этой кампании ({campaignMedia.assets.length})</p><div className="grid grid-cols-3 gap-2 sm:grid-cols-5">{campaignMedia.assets.map((asset) => <div key={asset.id} className="group relative overflow-hidden rounded border border-amber-300 bg-amber-50"><a href={asset.url} target="_blank" rel="noreferrer" title={`${asset.title} · ${asset.usage}`}><img src={asset.url} alt={asset.title} className="aspect-square w-full object-cover" /></a><button type="button" onClick={() => removeCampaignMedia(asset.id)} className="absolute right-1 top-1 rounded bg-white/90 px-1.5 py-0.5 text-xs text-red-700 shadow" title="Удалить из кампании">×</button><div className="truncate p-1 text-[10px] text-gray-600">{asset.title}</div></div>)}</div></> : <p className="text-xs text-gray-500">{mediaLoading ? 'Собираем фото GLAME…' : 'Выберите медиа ниже или загрузите свои файлы.'}</p>}
                <div className="mt-4 border-t border-gray-200 pt-3"><div className="mb-3 flex flex-wrap items-center gap-2"><input value={platformQuery} onChange={(event) => { setPlatformQuery(event.target.value); setPlatformSearchPerformed(false); }} onKeyDown={(event) => { if (event.key === 'Enter') searchPlatformMedia(); }} placeholder="Поиск изделия: название, артикул или код" className="h-9 min-w-64 flex-1 rounded border border-gray-300 px-2 text-sm" /><select value={platformCategory} onChange={(event) => { setPlatformCategory(event.target.value); setPlatformSearchPerformed(false); }} className="h-9 rounded border border-gray-300 bg-white px-2 text-xs"><option value="all">Все категории</option><option value="store">Пространства</option><option value="product">Изделия</option><option value="look">Образы</option><option value="generation">Генерации</option></select><Button size="sm" onClick={searchPlatformMedia} disabled={mediaLoading}>{platformQuery.trim() ? 'Найти' : 'Показать все'}</Button></div><div className="grid max-h-96 grid-cols-3 gap-2 overflow-y-auto sm:grid-cols-5">{(platformSearchPerformed ? platformAssets : (campaignMedia?.available_assets || [])).filter((asset) => !campaignMedia?.assets.some((item) => item.id === asset.id)).map((asset) => <button key={asset.id} type="button" onClick={() => addMediaFromLibrary(asset)} disabled={mediaLoading} className="overflow-hidden rounded border border-gray-200 bg-white text-left hover:border-amber-400"><img src={asset.url} alt={asset.title} className="aspect-square w-full object-cover" /><div className="truncate p-1 text-[10px] text-gray-600">+ {asset.title}</div></button>)}</div>{platformSearchPerformed && platformAssets.length === 0 ? <p className="mt-2 text-xs text-gray-500">В этой категории пока нет доступных изображений.</p> : null}</div>
                {campaignMedia?.maps_card_url ? <a className="mt-3 inline-block text-xs text-blue-700 underline" href={campaignMedia.maps_card_url} target="_blank" rel="noreferrer">Открыть карточку GLAME в Яндекс Картах для ручной проверки фото</a> : null}
                {campaignMedia?.note ? <p className="mt-2 text-[11px] text-gray-500">{campaignMedia.note}</p> : null}
              </Card>
            )}
            <AgentBoardChat agentId="brand-media-agent" agentName="AI Brand Media" boardId="content" aliases={['content-agent', 'brand-media', 'content-board']} hiddenTaskContextKey="content_project_hidden" selectedTaskIdOverride={selectedProjectTaskId} onSelectedTaskChange={setSelectedProjectTaskId} />
          </div>
        </div>

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
