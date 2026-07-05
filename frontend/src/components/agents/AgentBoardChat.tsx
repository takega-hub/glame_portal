'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { agentInteractions, aiMarketer, api, type AgentInteractionTask, type ChatHistoryItem } from '@/lib/api';

type AgentBoardChatProps = {
  agentId: string;
  agentName: string;
  boardId: string;
  aliases?: string[];
  title?: string;
};

const FINAL_STATUSES = new Set(['completed', 'cancelled', 'failed', 'rejected']);

const DEFAULT_BOARD_TASK_TYPES: Record<string, string> = {
  analytics: 'analytics_review',
  command: 'director_coordination',
  content: 'content_production',
  crm: 'crm_mailing',
  partnership: 'partnership_opportunity',
  'personal-media': 'personal_media_post',
  product: 'product_focus',
  traffic: 'growth_campaign',
};

function taskTitle(task: AgentInteractionTask) {
  return task.input_data?.title || task.task_context?.title || task.task_type.replaceAll('_', ' ');
}

function taskMatches(task: AgentInteractionTask, keys: string[]) {
  if (task.task_type === 'agent_control_chat') return false;
  const haystack = [
    task.source_agent,
    task.target_agent,
    task.task_type,
    task.input_data?.source_board,
    task.task_context?.board,
    task.task_context?.agent_id,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return keys.some((key) => haystack.includes(key.toLowerCase()));
}

function formatDate(value?: string | null) {
  if (!value) return '';
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatModelName(model?: string | null) {
  const value = model || 'openrouter/auto';
  return (value.split('/').pop() || value).replace('-instruct', '');
}

function buildTaskTitle(agentName: string, boardId: string, message: string) {
  const cleanMessage = message.replace(/\s+/g, ' ').trim();
  const snippet = cleanMessage.length > 70 ? `${cleanMessage.slice(0, 70)}...` : cleanMessage;
  return snippet ? `${agentName}: ${snippet}` : `${agentName}: операционная задача ${boardId}`;
}

export default function AgentBoardChat({ agentId, agentName, boardId, aliases = [], title }: AgentBoardChatProps) {
  const [tasks, setTasks] = useState<AgentInteractionTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState('');
  const [messages, setMessages] = useState<ChatHistoryItem[]>([]);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeModel, setActiveModel] = useState('openrouter/auto');
  const [runtimeLabel, setRuntimeLabel] = useState<string | null>(null);
  const bootstrappedRef = useRef(false);

  const matchKeys = useMemo(() => [agentId, boardId, ...aliases], [agentId, aliases, boardId]);
  const selectedTask = tasks.find((task) => task.id === selectedTaskId) || null;

  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;
    setActiveModel(localStorage.getItem('ai_marketer_model_dialog') || 'openrouter/auto');
    api.getAiRuntimeInfo(agentId)
      .then((info) => setRuntimeLabel(info.label))
      .catch(() => setRuntimeLabel(null));
    loadThread();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadThread() {
    setLoading(true);
    setError(null);
    try {
      const allTasks = await agentInteractions.listTasks({ limit: 200 });
      let agentTasks = allTasks.filter((task) => taskMatches(task, matchKeys));
      agentTasks = agentTasks.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      const activeTask = agentTasks.find((task) => !FINAL_STATUSES.has(task.status)) || agentTasks[0];
      setTasks(agentTasks);
      if (activeTask) {
        setSelectedTaskId(activeTask.id);
        const history = await agentInteractions.getChatHistory(activeTask.id, 120);
        setMessages(history);
      } else {
        setSelectedTaskId('');
        setMessages([]);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось открыть рабочий чат агента');
    } finally {
      setLoading(false);
    }
  }

  async function selectTask(taskId: string) {
    setSelectedTaskId(taskId);
    setMessages([]);
    setError(null);
    try {
      const history = await agentInteractions.getChatHistory(taskId, 120);
      setMessages(history);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось загрузить историю');
    }
  }

  async function ensureTaskForMessage(body: string) {
    if (selectedTask) return selectedTask;

    const taskType = DEFAULT_BOARD_TASK_TYPES[boardId] || `${boardId.replaceAll('-', '_')}_request`;
    const taskTitle = buildTaskTitle(agentName, boardId, body);
    const ensured = await aiMarketer.ensureBoardTask(boardId, {
      source_agent: 'director-agent',
      target_agent: agentId,
      task_type: taskType,
      priority: 3,
      idempotency_key: `${boardId}:${agentId}:admin-dialog:${taskTitle.toLowerCase()}`,
      task_context: {
        board: boardId,
        agent_id: agentId,
        title: taskTitle,
        created_from: 'agent_board_chat',
        hierarchy: {
          reports_to: 'director-agent',
          target_agent: agentId,
        },
      },
      input_data: {
        source_board: boardId,
        title: taskTitle,
        description: body,
        initial_admin_message: body,
        expected_result: 'Ответ профильного AI-агента в рабочем чате и зафиксированный следующий шаг.',
      },
      requirements: {
        must_answer_admin_message: true,
        must_keep_glame_agent_hierarchy: true,
      },
    });

    setTasks((current) => {
      const exists = current.some((task) => task.id === ensured.task.id);
      return exists ? current : [ensured.task, ...current];
    });
    setSelectedTaskId(ensured.task.id);
    return ensured.task;
  }

  async function send(text?: string) {
    const body = (text || message).trim();
    if (!body || sending) return;
    setSending(true);
    setError(null);
    setMessage('');
    try {
      const task = await ensureTaskForMessage(body);
      const response = await agentInteractions.chat(task.id, {
        message: body,
        model: activeModel,
        metadata: {
          step_type: 'other',
          task_type: task.task_type,
          dialog_model: activeModel,
          extra: {
            source: 'agent_board_chat',
            board_id: boardId,
            agent_id: agentId,
          },
        },
      });
      const now = new Date().toISOString();
      setMessages((current) => [
        ...current,
        { id: response.user_log_id || `${now}-user`, role: 'user', content: body, created_at: now },
        { id: response.assistant_log_id || `${now}-assistant`, role: 'assistant', content: response.reply, created_at: now },
      ]);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось отправить сообщение агенту');
      setMessage(body);
    } finally {
      setSending(false);
    }
  }

  const quickActions = [
    `Обнови данные по своей доске ${boardId} и зафиксируй, что изменилось.`,
    'Согласовано, можно передавать задачу в работу. Зафиксируй следующий шаг.',
    'Верни на доработку: проверь вводные, уточни риски и предложи правки.',
    'Передай результат дальше директору и укажи, какие данные приложены.',
  ];

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">{title || `Чат задач ${agentName}`}</h2>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <p className="text-sm text-gray-500">Диалог ведется внутри конкретной задачи агента: запрос директора, уточнения, ответ и результат.</p>
            <Badge variant="outline" title={`Подключенное ИИ ядро: ${runtimeLabel || activeModel}`}>
              {runtimeLabel || `Модель: ${formatModelName(activeModel)}`}
            </Badge>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {selectedTask && <Badge variant="outline">{selectedTask.status}</Badge>}
          <Button variant="outline" size="sm" onClick={loadThread} disabled={loading}>Обновить</Button>
          {selectedTask && (
            <Link href={`/ai-marketer/tasks/${selectedTask.id}`} className="rounded-md border px-3 py-2 text-sm hover:bg-gray-50">
              Карточка
            </Link>
          )}
        </div>
      </div>

      {tasks.length > 1 && (
        <div className="mt-4">
          <label className="mb-1 block text-xs font-medium text-gray-500">Рабочий поток</label>
          <select
            value={selectedTaskId}
            onChange={(event) => selectTask(event.target.value)}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
          >
            {tasks.map((task) => (
              <option key={task.id} value={task.id}>
                {taskTitle(task)} · {task.status}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="mt-4 h-80 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-3">
        {loading ? <p className="text-sm text-gray-500">Загружаю историю чата...</p> : null}
        {!loading && messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-center text-sm text-gray-500">
            {selectedTask ? 'История пока пустая. Напишите уточнение по этой задаче.' : 'У агента пока нет конкретных задач для диалога. Директор должен создать задачу, после этого чат появится внутри неё.'}
          </div>
        ) : null}
        <div className="space-y-3">
          {messages.map((item) => (
            <div key={item.id} className={`flex ${item.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[82%] rounded-lg border px-3 py-2 text-sm ${item.role === 'user' ? 'border-blue-200 bg-blue-50' : 'border-gray-200 bg-white'}`}>
                <div className="mb-1 flex items-center justify-between gap-4 text-[11px] text-gray-400">
                  <span>{item.role === 'user' ? 'Пользователь / директор' : agentName}</span>
                  <span>{formatDate(item.created_at)}</span>
                </div>
                <div className="whitespace-pre-wrap text-gray-800">{item.content}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {error && <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

      <div className="mt-3 flex flex-wrap gap-2">
        {quickActions.map((action) => (
          <button
            key={action}
            type="button"
            onClick={() => send(action)}
            disabled={sending}
            className="rounded-full border border-gray-200 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {action.split('.')[0]}
          </button>
        ))}
      </div>

      <div className="mt-3 flex gap-2">
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={`Напишите ${agentName}...`}
          className="min-h-20 flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-gold-500 focus:outline-none"
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
              event.preventDefault();
              send();
            }
          }}
        />
        <Button onClick={() => send()} disabled={sending || !message.trim()}>
          {sending ? 'Отправка...' : 'Отправить'}
        </Button>
      </div>
    </Card>
  );
}
