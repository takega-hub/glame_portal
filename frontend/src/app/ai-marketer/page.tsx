'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  BarChart3,
  Camera,
  CheckCircle2,
  Clock3,
  FileText,
  Handshake,
  LineChart,
  Megaphone,
  MessageSquare,
  PieChart,
  RefreshCw,
  Sparkles,
  Target,
  Users,
} from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import DirectorChatInterface from '@/components/director/DirectorChatInterface';

type BoardId = 'command' | 'content' | 'personal-media' | 'crm' | 'partnership' | 'traffic' | 'product' | 'analytics';
type BoardTone = 'good' | 'active' | 'attention';

interface AgentTask {
  id: string;
  source_agent: string;
  target_agent: string;
  task_type: string;
  status: string;
  priority: number;
  created_at?: string | null;
  deadline_at?: string | null;
}

interface OperationalData {
  aiDashboard: Record<string, any> | null;
  tasks: AgentTask[];
  inventoryDashboard: Record<string, any> | null;
  marketingLink: Record<string, any> | null;
  salesMetrics: Record<string, any> | null;
  storeVisits: Record<string, any> | null;
}

interface BoardConfig {
  id: BoardId;
  name: string;
  description: string;
  agents: string[];
  icon: React.ComponentType<{ className?: string }>;
  summary: (data: OperationalData, tasks: AgentTask[]) => {
    status: string;
    tone: BoardTone;
    focus: string;
    metrics: Array<{ label: string; value: string; accent?: string }>;
  };
}

const ACTIVE_STATUSES = new Set(['pending', 'validating', 'validated', 'pending_approval', 'approved', 'queued', 'processing']);
const APPROVAL_STATUSES = new Set(['pending_approval', 'validated']);
const COMPLETED_STATUSES = new Set(['completed']);

const formatNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const formatCurrency = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
});

const n = (value: unknown): number => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const money = (value: unknown) => formatCurrency.format(n(value));
const count = (value: unknown) => formatNumber.format(n(value));

const isToday = (value?: string | null) => {
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  const today = new Date();
  return date.toDateString() === today.toDateString();
};

const getTaskTitle = (task: AgentTask) => {
  const type = task.task_type.replaceAll('_', ' ');
  return `${type} · ${task.status}`;
};

const taskCounts = (tasks: AgentTask[]) => ({
  active: tasks.filter((task) => ACTIVE_STATUSES.has(task.status)).length,
  approvals: tasks.filter((task) => APPROVAL_STATUSES.has(task.status)).length,
  completedToday: tasks.filter((task) => COMPLETED_STATUSES.has(task.status) && isToday(task.created_at)).length,
});

const matchBoardTasks = (tasks: AgentTask[], config: Pick<BoardConfig, 'id' | 'agents'>) => {
  return tasks.filter((task) => {
    const haystack = `${task.source_agent} ${task.target_agent} ${task.task_type}`.toLowerCase();
    return config.agents.some((agent) => haystack.includes(agent)) || haystack.includes(config.id);
  });
};

const sumVisits = (data: OperationalData) => {
  const rows = data.storeVisits?.daily_data || data.storeVisits?.data || [];
  if (!Array.isArray(rows)) return 0;
  return rows.reduce((acc, row) => acc + n(row.visitors ?? row.visitor_count ?? row.visits), 0);
};

const buildBoards = (): BoardConfig[] => [
  {
    id: 'command',
    name: 'Marketing Command Board',
    icon: Target,
    description: 'Главная панель управления маркетингом',
    agents: ['marketing-director', 'marketing', 'director'],
    summary: (data, tasks) => {
      const allCounts = taskCounts(data.tasks);
      return {
        status: allCounts.approvals > 0 ? 'Нужно согласование' : allCounts.active > 0 ? 'В работе' : 'Стабильно',
        tone: allCounts.approvals > 0 ? 'attention' : allCounts.active > 0 ? 'active' : 'good',
        focus: allCounts.approvals > 0 ? 'Разобрать approvals и приоритеты на сегодня' : 'Контроль активных потоков и готовности плана',
        metrics: [
          { label: 'Активные задачи', value: count(allCounts.active) },
          { label: 'На согласовании', value: count(allCounts.approvals), accent: allCounts.approvals > 0 ? 'text-orange-600' : undefined },
          { label: 'Готово сегодня', value: count(allCounts.completedToday), accent: 'text-green-700' },
        ],
      };
    },
  },
  {
    id: 'content',
    name: 'Content Board',
    icon: FileText,
    description: 'Управление контентными задачами',
    agents: ['content', 'brand-media'],
    summary: (_, tasks) => {
      const c = taskCounts(tasks);
      return {
        status: c.approvals > 0 ? 'Контент на ревью' : c.active > 0 ? 'Производство идет' : 'Очередь чистая',
        tone: c.approvals > 0 ? 'attention' : c.active > 0 ? 'active' : 'good',
        focus: c.active > 0 ? 'Проверить ближайшие публикации и материалы в производстве' : 'Можно планировать следующий контент-пакет',
        metrics: [
          { label: 'В работе', value: count(c.active) },
          { label: 'На ревью', value: count(c.approvals), accent: c.approvals > 0 ? 'text-orange-600' : undefined },
          { label: 'Готово сегодня', value: count(c.completedToday), accent: 'text-green-700' },
        ],
      };
    },
  },
  {
    id: 'personal-media',
    name: 'Personal Media Board',
    icon: Camera,
    description: 'Личный блог Елены',
    agents: ['personal-media', 'personal'],
    summary: (_, tasks) => {
      const c = taskCounts(tasks);
      return {
        status: c.active > 0 ? 'Есть текущие задачи' : 'Нет срочных задач',
        tone: c.approvals > 0 ? 'attention' : c.active > 0 ? 'active' : 'good',
        focus: c.active > 0 ? 'Проверить сценарии, съемки и согласования личного медиа' : 'Доска готова к новым идеям и планам',
        metrics: [
          { label: 'Задачи', value: count(c.active) },
          { label: 'Согласования', value: count(c.approvals) },
          { label: 'Готово', value: count(c.completedToday), accent: 'text-green-700' },
        ],
      };
    },
  },
  {
    id: 'crm',
    name: 'CRM Board',
    icon: Users,
    description: 'CRM-коммуникации и лояльность',
    agents: ['crm', 'communication'],
    summary: (data, tasks) => {
      const c = taskCounts(tasks);
      const segments = n(data.aiDashboard?.segments_overview?.total_segments ?? data.aiDashboard?.segments?.length);
      const churn = n(data.aiDashboard?.churn_risk?.high_risk);
      return {
        status: churn > 0 ? 'Есть риск оттока' : c.active > 0 ? 'Коммуникации в работе' : 'Спокойно',
        tone: churn > 0 || c.approvals > 0 ? 'attention' : c.active > 0 ? 'active' : 'good',
        focus: churn > 0 ? 'Нужна реактивация клиентов с высоким риском' : 'Следить за сегментами и готовностью рассылок',
        metrics: [
          { label: 'CRM задачи', value: count(c.active) },
          { label: 'Сегменты', value: count(segments) },
          { label: 'Риск оттока', value: count(churn), accent: churn > 0 ? 'text-orange-600' : undefined },
        ],
      };
    },
  },
  {
    id: 'partnership',
    name: 'Partnership Board',
    icon: Handshake,
    description: 'PR и партнерства',
    agents: ['partnership', 'pr'],
    summary: (_, tasks) => {
      const c = taskCounts(tasks);
      return {
        status: c.active > 0 ? 'Пайплайн активен' : 'Нужны новые лиды',
        tone: c.approvals > 0 ? 'attention' : c.active > 0 ? 'active' : 'good',
        focus: c.active > 0 ? 'Проверить статусы партнерских диалогов' : 'Добавить текущие PR и collab opportunities',
        metrics: [
          { label: 'В пайплайне', value: count(c.active) },
          { label: 'На согласовании', value: count(c.approvals) },
          { label: 'Закрыто сегодня', value: count(c.completedToday), accent: 'text-green-700' },
        ],
      };
    },
  },
  {
    id: 'traffic',
    name: 'Traffic/Growth Board',
    icon: LineChart,
    description: 'Трафик и рост',
    agents: ['traffic', 'growth'],
    summary: (data, tasks) => {
      const c = taskCounts(tasks);
      const visitors = sumVisits(data);
      const revenue = n(data.inventoryDashboard?.sales?.revenue ?? data.salesMetrics?.total_revenue);
      const revenuePerVisitor = visitors > 0 ? revenue / visitors : 0;
      return {
        status: visitors > 0 ? 'Трафик обновлен' : c.active > 0 ? 'Рост в работе' : 'Ждем данные',
        tone: c.approvals > 0 ? 'attention' : visitors > 0 || c.active > 0 ? 'active' : 'good',
        focus: visitors > 0 ? 'Сверить трафик, выручку на посетителя и конверсию' : 'Подключить свежие данные по посещениям',
        metrics: [
          { label: 'Посетители 7д', value: count(visitors) },
          { label: '₽ / посетитель', value: visitors > 0 ? money(revenuePerVisitor) : '—' },
          { label: 'Growth задачи', value: count(c.active) },
        ],
      };
    },
  },
  {
    id: 'product',
    name: 'Product Focus Board',
    icon: Sparkles,
    description: 'Ассортимент и фокус на продуктах',
    agents: ['assortment', 'inventory', 'product'],
    summary: (data, tasks) => {
      const c = taskCounts(tasks);
      const critical = n(data.inventoryDashboard?.stock?.critical_count);
      const slow = n(data.inventoryDashboard?.stock?.slow_moving_count);
      const promoCandidates = n(data.marketingLink?.total);
      return {
        status: critical > 0 ? 'Критические остатки' : slow > 0 ? 'Есть slow moving' : 'Ассортимент стабилен',
        tone: critical > 0 ? 'attention' : slow > 0 || c.active > 0 ? 'active' : 'good',
        focus: critical > 0 ? 'Проверить дозаказ и защиту hero-позиций' : 'Сверить фокус товаров для маркетинга',
        metrics: [
          { label: 'Критические', value: count(critical), accent: critical > 0 ? 'text-orange-600' : undefined },
          { label: 'Slow moving', value: count(slow) },
          { label: 'Для продвижения', value: count(promoCandidates) },
        ],
      };
    },
  },
  {
    id: 'analytics',
    name: 'Analytics Board',
    icon: BarChart3,
    description: 'Аналитика и отчетность',
    agents: ['analytics', 'report'],
    summary: (data, tasks) => {
      const c = taskCounts(tasks);
      const revenue = n(data.inventoryDashboard?.sales?.revenue ?? data.salesMetrics?.total_revenue);
      const checks = n(data.inventoryDashboard?.sales?.checks_count ?? data.salesMetrics?.total_orders);
      const avgCheck = n(data.inventoryDashboard?.sales?.avg_check ?? data.salesMetrics?.average_order_value);
      return {
        status: revenue > 0 ? 'Данные доступны' : 'Нужна синхронизация',
        tone: c.approvals > 0 ? 'attention' : revenue > 0 || c.active > 0 ? 'active' : 'good',
        focus: revenue > 0 ? 'Собрать выводы по продажам, трафику и складу' : 'Проверить источники аналитики',
        metrics: [
          { label: 'Выручка месяц', value: revenue > 0 ? money(revenue) : '—' },
          { label: 'Чеки', value: count(checks) },
          { label: 'Средний чек', value: avgCheck > 0 ? money(avgCheck) : '—' },
        ],
      };
    },
  },
];

const emptyData: OperationalData = {
  aiDashboard: null,
  tasks: [],
  inventoryDashboard: null,
  marketingLink: null,
  salesMetrics: null,
  storeVisits: null,
};

async function safeJson<T>(url: string): Promise<T | null> {
  try {
    const response = await fetch(url, { method: 'GET', cache: 'no-store' });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch (error) {
    console.error(`Failed to load ${url}`, error);
    return null;
  }
}

export default function AIMarketerPage() {
  const { loading } = useAuth();
  const [data, setData] = useState<OperationalData>(emptyData);
  const [loadingData, setLoadingData] = useState(true);
  const [activeTab, setActiveTab] = useState('chat');

  const boards = useMemo(() => buildBoards(), []);
  const allCounts = useMemo(() => taskCounts(data.tasks), [data.tasks]);

  useEffect(() => {
    if (!loading) {
      loadOperationalData();
    }
  }, [loading]);

  const loadOperationalData = async () => {
    setLoadingData(true);
    const [aiDashboard, tasks, inventoryDashboard, marketingLink, salesMetrics, storeVisits] = await Promise.all([
      safeJson<Record<string, any>>('/api/ai-marketer/dashboard'),
      safeJson<AgentTask[]>('/api/agent-interactions/tasks?limit=100'),
      safeJson<Record<string, any>>('/api/inventory/dashboard?period=month'),
      safeJson<Record<string, any>>('/api/inventory/marketing-link?period=month&limit=50'),
      safeJson<Record<string, any>>('/api/analytics/1c-sales/metrics?period=month'),
      safeJson<Record<string, any>>('/api/analytics/store-visits/daily?days=7'),
    ]);

    setData({
      aiDashboard,
      tasks: Array.isArray(tasks) ? tasks : [],
      inventoryDashboard,
      marketingLink,
      salesMetrics,
      storeVisits,
    });
    setLoadingData(false);
  };

  if (loading || loadingData) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-pink-600 mx-auto" />
          <p className="mt-4 text-gray-600">Загрузка AI Marketing Director...</p>
        </div>
      </div>
    );
  }

  const recentTasks = data.tasks.filter((task) => ACTIVE_STATUSES.has(task.status)).slice(0, 5);
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <Link href="/" className="text-pink-600 hover:text-pink-700 mb-4 inline-block">
            ← Назад
          </Link>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">AI Marketing Director</h1>
              <p className="mt-2 text-gray-600">
                Живая панель досок: статистика, статусы, задачи и текущие операционные сигналы.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={loadOperationalData}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                type="button"
              >
                <RefreshCw className="h-4 w-4" />
                Обновить
              </button>
              <Link
                href="/ai-marketer/tasks"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-pink-600 text-white hover:bg-pink-700"
              >
                <Clock3 className="h-4 w-4" />
                Все задачи {allCounts.approvals > 0 ? `(${allCounts.approvals})` : ''}
              </Link>
            </div>
          </div>
        </div>

        
        <Tabs value={activeTab} onValueChange={setActiveTab} className="mb-8">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="chat">
              <MessageSquare className="h-4 w-4 mr-1.5" />
              Чат
            </TabsTrigger>
            <TabsTrigger value="overview">Обзор</TabsTrigger>
            <TabsTrigger value="boards">Рабочие доски</TabsTrigger>
            <TabsTrigger value="reports">Отчеты</TabsTrigger>
          </TabsList>

          <TabsContent value="chat" className="min-h-[620px]">
            <div className="h-full min-h-0">
              <DirectorChatInterface />
            </div>
          </TabsContent>

          <TabsContent value="overview" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
              <div className="lg:col-span-3 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                {boards.map((board) => (
                  <BoardCard key={board.id} board={board} data={data} tasks={matchBoardTasks(data.tasks, board)} />
                ))}
              </div>
              <CurrentTasksPanel tasks={recentTasks} />
            </div>
          </TabsContent>

          <TabsContent value="boards">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {boards.map((board) => (
                <BoardCard key={board.id} board={board} data={data} tasks={matchBoardTasks(data.tasks, board)} wide />
              ))}
            </div>
          </TabsContent>

          <TabsContent value="reports">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h2 className="text-xl font-bold text-gray-900 mb-6">Плановые отчеты</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <ReportCard title="Ежедневный отчет" text="План на завтра, approvals, риски и быстрые операционные выводы." href="/ai-marketer/reports/daily" action="Сформировать" />
                <ReportCard title="Недельный обзор" text="Продажи, трафик, CRM, контент, склад и решения на следующую неделю." href="/ai-marketer/reports/weekly" action="История отчетов" />
                <ReportCard title="Месячный стратегический" text="Структура ассортимента, retention, growth и вклад каналов." href="/ai-marketer/reports/monthly" action="История отчетов" />
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

function KpiCard({
  label,
  value,
  icon: Icon,
  accent = 'text-gray-900',
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  accent?: string;
}) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-gray-500">{label}</p>
        <Icon className="h-4 w-4 text-gray-400" />
      </div>
      <p className={`text-3xl font-bold mt-2 ${accent}`}>{value}</p>
    </div>
  );
}

function BoardCard({
  board,
  data,
  tasks,
  wide = false,
}: {
  board: BoardConfig;
  data: OperationalData;
  tasks: AgentTask[];
  wide?: boolean;
}) {
  const Icon = board.icon;
  const summary = board.summary(data, tasks);
  const latestTask = tasks.find((task) => ACTIVE_STATUSES.has(task.status));

  const toneClass = {
    good: 'bg-green-50 text-green-800 border-green-200',
    active: 'bg-blue-50 text-blue-800 border-blue-200',
    attention: 'bg-orange-50 text-orange-800 border-orange-200',
  }[summary.tone];

  return (
    <Link
      href={`/ai-marketer/boards/${board.id}`}
      className={`bg-white rounded-lg shadow-sm border border-gray-200 p-4 hover:border-pink-300 hover:shadow-md transition-all ${wide ? 'min-h-[220px]' : 'min-h-[236px]'}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="h-10 w-10 rounded-lg bg-gray-50 border border-gray-200 flex items-center justify-center shrink-0">
            <Icon className="h-5 w-5 text-gray-800" />
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-gray-900 text-sm leading-5 truncate">{board.name}</h3>
            <p className="text-xs text-gray-500 line-clamp-2">{board.description}</p>
          </div>
        </div>
        <span className={`shrink-0 px-2 py-1 rounded border text-[11px] font-medium ${toneClass}`}>{summary.status}</span>
      </div>

      <div className="grid grid-cols-3 gap-2 mt-4">
        {summary.metrics.map((metric) => (
          <div key={metric.label} className="rounded-md bg-gray-50 border border-gray-100 p-2 min-h-[62px]">
            <p className={`text-base font-bold leading-5 ${metric.accent || 'text-gray-900'}`}>{metric.value}</p>
            <p className="text-[11px] text-gray-500 leading-4 mt-1">{metric.label}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 border-t border-gray-100 pt-3">
        <p className="text-xs text-gray-500">Сейчас важно</p>
        <p className="text-sm text-gray-800 mt-1 line-clamp-2">{summary.focus}</p>
        <p className="text-xs text-gray-500 mt-2 truncate">
          {latestTask ? `Текущая задача: ${getTaskTitle(latestTask)}` : 'Текущих задач на доске нет'}
        </p>
      </div>
    </Link>
  );
}

function CurrentTasksPanel({ tasks }: { tasks: AgentTask[] }) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="font-semibold text-gray-900">Текущая работа</h2>
          <p className="text-xs text-gray-500">Последние активные задачи агентов</p>
        </div>
        <Link href="/ai-marketer/tasks" className="text-sm text-pink-600 hover:text-pink-700">
          Открыть
        </Link>
      </div>
      <div className="space-y-3">
        {tasks.length === 0 ? (
          <div className="rounded-lg bg-gray-50 border border-gray-100 p-4 text-sm text-gray-500">
            Активных задач сейчас нет. Когда агенты начнут работу, здесь появятся свежие статусы.
          </div>
        ) : (
          tasks.map((task) => (
            <Link key={task.id} href={`/ai-marketer/tasks/${task.id}`} className="block rounded-lg border border-gray-100 p-3 hover:border-pink-200">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-gray-900 truncate">{task.task_type.replaceAll('_', ' ')}</p>
                <span className="text-[11px] rounded bg-gray-100 px-2 py-0.5 text-gray-700">{task.status}</span>
              </div>
              <p className="text-xs text-gray-500 mt-1 truncate">{task.source_agent} → {task.target_agent}</p>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

function ReportCard({ title, text, href, action }: { title: string; text: string; href: string; action: string }) {
  return (
    <div className="border border-gray-200 rounded-lg p-4">
      <h3 className="font-semibold text-gray-900">{title}</h3>
      <p className="text-sm text-gray-500 mt-1">{text}</p>
      <Link href={href} className="mt-4 inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-gray-900 text-white hover:bg-gray-800">
        <BarChart3 className="h-4 w-4" />
        {action}
      </Link>
    </div>
  );
}
