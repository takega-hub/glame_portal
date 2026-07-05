'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { agentInteractions, api, apiClient, director, type AgentInteractionTask } from '@/lib/api';
import type { DirectorChatMessage } from '@/types';
import { format } from 'date-fns';
import { ru } from 'date-fns/locale';
import { Search, Trash2, Reply, Send, X, MessageSquare, Briefcase, BookOpen, CheckCircle, AlertCircle, Clock, Target, Loader2, ExternalLink, Paperclip, Upload, FileText, Image as ImageIcon, Activity, Database, Bot } from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';

const STORAGE_KEY = 'glame_director_session_id';

interface DirectorChatInterfaceProps {
  userId?: string;
}

type ViewMode = 'chat' | 'tasks' | 'knowledge';

type DirectorReportTaskAction = {
  id: string;
  title: string;
  description: string;
  targetAgent: string;
  agentLabel: string;
  taskType: string;
  priority: number;
};

const directorQuickActions = [
  {
    id: 'weekly-pulse',
    title: 'Собрать отчет',
    description: 'Продажи, чеки, магазины, сайт, приложение и Instagram за 7 дней.',
    prompt:
      'Собери управленческий отчет за последние 7 дней: продажи, чеки, выручка по магазинам, офлайн-посещения, сайт, приложение и Instagram. Покажи выводы, риски и что нужно сделать дальше.',
    icon: Activity,
    tone: 'text-blue-700 bg-blue-50 border-blue-100',
  },
  {
    id: 'growth-plan',
    title: 'Найти рост',
    description: 'Где теряем конверсию и какие действия дадут быстрый эффект.',
    prompt:
      'Проанализируй текущие данные и найди 3 самые сильные точки роста продаж. Раздели по направлениям: CRM, ассортимент, трафик, контент, работа магазинов. Предложи план задач для агентов.',
    icon: Target,
    tone: 'text-emerald-700 bg-emerald-50 border-emerald-100',
  },
  {
    id: 'campaign-plan',
    title: 'Новая кампания',
    description: 'Сформировать идею, аудиторию, каналы и задачи агентам.',
    prompt:
      'Давай спланируем новую маркетинговую кампанию. Сначала предложи 2-3 гипотезы на основе текущих данных, затем покажи структуру кампании, какие агенты нужны и какие задачи создать после моего согласования.',
    icon: Briefcase,
    tone: 'text-purple-700 bg-purple-50 border-purple-100',
  },
  {
    id: 'crm-mailing',
    title: 'CRM-рассылка',
    description: 'Сегмент, сценарий сообщения и план согласования.',
    prompt:
      'Подготовь CRM-рассылку: предложи сегмент покупателей на основе данных, цель коммуникации, текст сообщения, канал отправки и план согласования перед запуском.',
    icon: MessageSquare,
    tone: 'text-pink-700 bg-pink-50 border-pink-100',
  },
  {
    id: 'knowledge-brief',
    title: 'Пополнить знания',
    description: 'Определить, каких данных не хватает директору и агентам.',
    prompt:
      'Проверь, каких данных или документов сейчас не хватает для качественного планирования. Составь список, что стоит добавить в базу знаний и какие файлы ты хочешь запросить у меня.',
    icon: Database,
    tone: 'text-amber-700 bg-amber-50 border-amber-100',
  },
  {
    id: 'cron-control',
    title: 'Проверить CRON',
    description: 'Регламенты, последние запуски, созданные задачи и улучшения.',
    prompt:
      'Проверь CRON-регламенты: какие включены, когда следующий запуск, какие задачи создавались последними запусками, есть ли риски или что нужно улучшить. Дай советы и предложи правки.',
    icon: Clock,
    tone: 'text-slate-700 bg-slate-50 border-slate-100',
  },
];

export default function DirectorChatInterface({}: DirectorChatInterfaceProps) {
  const [messages, setMessages] = useState<DirectorChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [greetingLoaded, setGreetingLoaded] = useState(false);
  const [activeModel, setActiveModel] = useState('openrouter/auto');
  const [runtimeLabel, setRuntimeLabel] = useState<string | null>(null);
  const [clearingChat, setClearingChat] = useState(false);

  // Поиск
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<DirectorChatMessage[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchPage, setSearchPage] = useState(1);
  const [searchTotal, setSearchTotal] = useState(0);

  // Ответ на сообщение
  const [replyTo, setReplyTo] = useState<DirectorChatMessage | null>(null);

  // Вложения
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadMessage, setUploadMessage] = useState('');
  const [uploadToKnowledge, setUploadToKnowledge] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState(false);

  // View mode
  const [viewMode, setViewMode] = useState<ViewMode>('chat');

  // Задачи
  const [tasks, setTasks] = useState<any[]>([]);
  const [taskColumns, setTaskColumns] = useState<Array<{ id: string; title: string; cards: any[] }>>([]);
  const [draggedTask, setDraggedTask] = useState<any | null>(null);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksFilter, setTasksFilter] = useState<string>('all');
  const [taskActionLoading, setTaskActionLoading] = useState<string | null>(null);
  const [reportTaskLoading, setReportTaskLoading] = useState<string | null>(null);
  const [workActivity, setWorkActivity] = useState<any[]>([]);
  const [activityLoading, setActivityLoading] = useState(false);

  // Знания
  const [knowledgeList, setKnowledgeList] = useState<any[]>([]);
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Загрузка истории при монтировании
  useEffect(() => {
    const savedSessionId = localStorage.getItem(STORAGE_KEY);
    if (savedSessionId) {
      setSessionId(savedSessionId);
    }
    setActiveModel(localStorage.getItem('ai_marketer_model_dialog') || 'openrouter/auto');
    api.getAiRuntimeInfo('director-agent')
      .then((info) => setRuntimeLabel(info.label))
      .catch(() => setRuntimeLabel(null));
    loadHistory();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (searchOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [searchOpen]);

  useEffect(() => {
    loadTasks(tasksFilter);
    loadWorkActivity();
  }, []);

  const loadHistory = async () => {
    try {
      const data = await director.chatHistory({ limit: 50 });
      const loadedMessages = data.messages.reverse();
      setMessages(loadedMessages);
      // Если сообщений нет — загружаем приветствие директора
      if (loadedMessages.length === 0 && !greetingLoaded) {
        setGreetingLoaded(true);
        try {
          const greeting = await director.getGreeting(null);
          const greetingMsg: DirectorChatMessage = {
            id: greeting.director_message_id,
            user_id: '',
            message: greeting.response,
            message_type: 'greeting',
            message_direction: 'director',
            category: null,
            priority: null,
            session_id: null,
            created_at: new Date().toISOString(),
            updated_at: null,
            vector_id: null,
            extra_data: { greeting: true, data_context: greeting.data_context },
            status: 'completed',
            is_important: false,
            parent_message_id: null,
            related_task_id: null,
          };
          setMessages([greetingMsg]);
        } catch {
          // если greeting не получился — пустой чат остаётся как есть
        }
      }
    } catch {
      // silently fail — show empty chat
    }
  };

  const sendMessage = useCallback(async (messageText: string) => {
    if (!messageText.trim() || loading) return;

    const optimisticUserMsg: DirectorChatMessage = {
      id: `temp-${Date.now()}`,
      user_id: '',
      message: messageText,
      message_type: 'text',
      message_direction: 'user',
      category: null,
      priority: null,
      session_id: sessionId,
      created_at: new Date().toISOString(),
      updated_at: null,
      vector_id: null,
      extra_data: {},
      status: 'pending',
      is_important: false,
      parent_message_id: replyTo?.id || null,
      related_task_id: null,
    };

    setMessages(prev => [...prev, optimisticUserMsg]);
    setInput('');
    setReplyTo(null);
    setLoading(true);
    setError(null);

    try {
      const response = await director.chat(
        messageText,
        sessionId,
        replyTo?.category || null,
        activeModel
      );

      setSessionId(response.session_id);
      localStorage.setItem(STORAGE_KEY, response.session_id);

      const assistantMsg: DirectorChatMessage = {
        id: response.response_id,
        user_id: '',
        message: response.response,
        message_type: response.message_type,
        message_direction: 'director',
        category: response.category,
        priority: response.priority,
        session_id: response.session_id,
        created_at: new Date().toISOString(),
        updated_at: null,
        vector_id: null,
        extra_data: {
          ...(response.extra_data || {}),
          action: response.action,
          extracted_task: response.extracted_task,
          suggested_knowledge: response.suggested_knowledge,
        },
        status: 'completed',
        is_important: response.priority === 'P0' || response.priority === 'P1',
        parent_message_id: null,
        related_task_id: null,
      };

      setMessages(prev => [...prev, assistantMsg]);
      await loadWorkActivity();
    } catch (err: any) {
      let errorMsg = 'Ошибка при отправке сообщения директору.';
      if (err.response?.status >= 500) {
        errorMsg = 'Серверная ошибка. Попробуйте позже.';
      } else if (err.response?.status === 429) {
        errorMsg = 'Слишком много запросов. Подождите немного.';
      } else if (!err.response) {
        errorMsg = 'Нет подключения к серверу. Проверьте соединение.';
      }
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  }, [loading, sessionId, replyTo, activeModel]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleFileSelection = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    setSelectedFiles(files);
    if (event.target) event.target.value = '';
  };

  const clearSelectedFiles = () => {
    setSelectedFiles([]);
    setUploadMessage('');
    setUploadToKnowledge(false);
  };

  const uploadSelectedFiles = async () => {
    if (selectedFiles.length === 0 || uploadingFiles) return;
    setUploadingFiles(true);
    setError(null);
    try {
      const uploadedMessages: DirectorChatMessage[] = [];
      for (const file of selectedFiles) {
        const result = await director.uploadChatFile(file, {
          sessionId,
          message: uploadMessage,
          addToKnowledge: uploadToKnowledge,
          knowledgeCategory: 'director_upload',
        });
        uploadedMessages.push(result.user_message, result.director_message);
        if (result.director_message.session_id) {
          setSessionId(result.director_message.session_id);
          localStorage.setItem(STORAGE_KEY, result.director_message.session_id);
        }
      }
      setMessages(prev => [...prev, ...uploadedMessages]);
      clearSelectedFiles();
      if (uploadToKnowledge && viewMode === 'knowledge') loadKnowledge();
      await loadWorkActivity();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Не удалось загрузить файл директору.');
    } finally {
      setUploadingFiles(false);
    }
  };

  // Поиск по сообщениям
  const handleSearch = useCallback(async (page = 1) => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const data = await director.searchChat({ query: searchQuery, page, limit: 20 });
      setSearchResults(data.messages);
      setSearchTotal(data.total);
      setSearchPage(page);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }, [searchQuery]);

  // Очистить поиск
  const clearSearch = () => {
    setSearchQuery('');
    setSearchResults([]);
    setSearchTotal(0);
    setSearchPage(1);
    setSearchOpen(false);
  };

  const handleClearChat = async () => {
    if (loading || clearingChat) return;
    const confirmed = window.confirm('Очистить историю чата с директором? Задачи, сегменты и база знаний, созданные отдельно, останутся.');
    if (!confirmed) return;

    try {
      setClearingChat(true);
      setError(null);
      await director.clearChatHistory({ include_memory: true });
      localStorage.removeItem(STORAGE_KEY);
      setSessionId(null);
      setMessages([]);
      setReplyTo(null);
      clearSelectedFiles();
      clearSearch();
      setGreetingLoaded(true);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Не удалось очистить чат.');
    } finally {
      setClearingChat(false);
    }
  };

  // Загрузить задачи
  const loadTasks = async (filter = 'all') => {
    setTasksLoading(true);
    try {
      const data = await director.tasksKanban({ limit: 200 });
      setTaskColumns(data.columns);
      const allCards = data.columns.flatMap((column) => column.cards);
      setTasks(filter === 'all' ? allCards : allCards.filter((task) => task.status === filter));
    } catch {
      setTasks([]);
      setTaskColumns([]);
    } finally {
      setTasksLoading(false);
    }
  };

  const loadWorkActivity = async () => {
    setActivityLoading(true);
    try {
      const data = await director.workActivity({ limit: 12 });
      setWorkActivity(data.activity);
    } catch {
      setWorkActivity([]);
    } finally {
      setActivityLoading(false);
    }
  };

  // Загрузить базу знаний
  const loadKnowledge = async () => {
    setKnowledgeLoading(true);
    try {
      const data = await director.listKnowledge({ limit: 20 });
      setKnowledgeList(data.knowledge);
    } catch {
      setKnowledgeList([]);
    } finally {
      setKnowledgeLoading(false);
    }
  };

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    if (mode === 'tasks') loadTasks(tasksFilter);
    if (mode === 'knowledge') loadKnowledge();
  };

  const handleTaskFilterChange = (filter: string) => {
    setTasksFilter(filter);
    loadTasks(filter);
  };

  const handleTaskDrop = async (columnId: string) => {
    if (!draggedTask) return;
    const sourceColumn = taskColumns.find((column) =>
      column.cards.some((task) => task.id === draggedTask.id && task.source === draggedTask.source)
    );
    if (sourceColumn?.id === columnId) {
      setDraggedTask(null);
      return;
    }

    const previousColumns = taskColumns;
    setTaskColumns((columns) => columns.map((column) => {
      const cards = column.cards.filter((task) => !(task.id === draggedTask.id && task.source === draggedTask.source));
      if (column.id !== columnId) return { ...column, cards };
      return { ...column, cards: [draggedTask, ...cards] };
    }));

    try {
      await director.moveTaskCard(draggedTask.source, draggedTask.id, columnId);
      await loadTasks(tasksFilter);
    } catch {
      setTaskColumns(previousColumns);
    } finally {
      setDraggedTask(null);
    }
  };

  const handleApproveTaskFromChat = async (task: any) => {
    const key = `${task.source}-${task.id}`;
    setTaskActionLoading(key);
    setError(null);
    try {
      const result = await director.approveTaskCard(task.source, task.id, { sessionId });
      setMessages(prev => [...prev, result.director_message]);
      await loadTasks(tasksFilter);
      await loadWorkActivity();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Не удалось согласовать задачу.');
    } finally {
      setTaskActionLoading(null);
    }
  };

  const handleReviseTaskFromChat = async (task: any) => {
    const comment = window.prompt('Комментарий к доработке');
    if (comment === null) return;
    const key = `${task.source}-${task.id}`;
    setTaskActionLoading(key);
    setError(null);
    try {
      const result = await director.reviseTaskCard(task.source, task.id, {
        sessionId,
        comment: comment.trim() || null,
      });
      setMessages(prev => [...prev, result.director_message]);
      await loadTasks(tasksFilter);
      await loadWorkActivity();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Не удалось отправить задачу на доработку.');
    } finally {
      setTaskActionLoading(null);
    }
  };

  const handleStartReportTask = async (action: DirectorReportTaskAction, sourceMessage: DirectorChatMessage) => {
    setReportTaskLoading(`${sourceMessage.id}:${action.id}`);
    setError(null);
    try {
      const task = await agentInteractions.createTask({
        source_agent: 'director-agent',
        target_agent: action.targetAgent,
        task_type: action.taskType,
        priority: action.priority,
        input_data: {
          title: action.title,
          description: action.description,
          source_message_id: sourceMessage.id,
          source: 'director_report_action',
          requested_by: 'admin_chat',
        },
        task_context: {
          created_from: 'director_chat_report',
          director_session_id: sessionId,
          source_message_id: sourceMessage.id,
          action_id: action.id,
          agent_label: action.agentLabel,
          handoff_protocol: 'director_task_result_for_approval_v1',
          expected_response: action.targetAgent === 'crm-agent'
            ? 'segment_proposal_for_approval'
            : 'work_result_for_director_approval',
        },
      });

      let status = task.status;
      try {
        await agentInteractions.approveTask(task.id, 'Запущено из интерактивного отчета директора.');
        const queued = await agentInteractions.queueTask(task.id);
        status = queued.status;
      } catch {
        status = task.status;
      }

      const createdMessage = buildReportTaskCreatedMessage(task, action, status, sessionId);
      setMessages(prev => [...prev, createdMessage]);

      const handoffPrompt = buildAgentHandoffPrompt(action, sourceMessage);
      try {
        await agentInteractions.updateTask(task.id, { status: 'processing' });
        const agentReply = await agentInteractions.chat(task.id, {
          message: handoffPrompt,
          model: activeModel,
          metadata: {
            step_type: action.id.includes('crm') ? 'segmentation' : action.id.includes('analytics') ? 'analytics' : action.id.includes('content') ? 'content' : 'planning',
            task_type: action.taskType,
            dialog_model: activeModel,
            extra: {
              from_director: true,
              source_message_id: sourceMessage.id,
              report_action_id: action.id,
            },
          },
        });
        const refreshedTask = await agentInteractions.getTask(task.id).catch(() => task);
        setMessages(prev => [...prev, buildAgentDiscussionMessage({
          task: refreshedTask,
          action,
          reply: agentReply.reply,
          sessionId,
        })]);
      } catch (dialogErr: any) {
        setMessages(prev => [...prev, {
          id: `agent-discussion-error-${task.id}-${Date.now()}`,
          user_id: '',
          message: `Задача для ${action.agentLabel} создана, но первый диалог с агентом не удалось выполнить автоматически: ${dialogErr.response?.data?.detail || 'ошибка диалога'}. Откройте карточку задачи и продолжите чат вручную.`,
          message_type: 'task',
          message_direction: 'director',
          category: 'agent_discussion',
          priority: `P${action.priority}`,
          session_id: sessionId,
          created_at: new Date().toISOString(),
          updated_at: null,
          vector_id: null,
          extra_data: {
            card_type: 'agent_discussion_error',
            task_id: task.id,
            target_agent: action.targetAgent,
            href: `/ai-marketer/tasks/${task.id}`,
          },
          status: 'completed',
          is_important: true,
          parent_message_id: null,
          related_task_id: task.id,
        }]);
      }
      await loadTasks(tasksFilter);
      await loadWorkActivity();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Не удалось поставить задачу агенту.');
    } finally {
      setReportTaskLoading(null);
    }
  };

  const activeChatTasks = taskColumns
    .flatMap((column) => column.cards)
    .filter((task) => !['completed', 'cancelled', 'rejected', 'failed'].includes(String(task.status || '').toLowerCase()))
    .slice(0, 6);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      {/* Левая панель — основная */}
      <div className="flex-1 min-h-0 flex flex-col min-w-0 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
        {/* Шапка */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-white shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-600 to-purple-700 flex items-center justify-center shadow-md">
              <Briefcase className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900">AI Marketing Director</h1>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <p className="text-xs text-gray-500">AI Директор GLAME</p>
                <ModelBadge model={activeModel} label={runtimeLabel} />
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleClearChat}
              disabled={loading || clearingChat || messages.length === 0}
              className="p-2 rounded-lg text-gray-500 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-40 disabled:cursor-not-allowed"
              title="Очистить чат"
            >
              {clearingChat ? <Loader2 className="w-5 h-5 animate-spin" /> : <Trash2 className="w-5 h-5" />}
            </button>
            <button
              onClick={() => setSearchOpen(!searchOpen)}
              className={`p-2 rounded-lg transition-colors ${searchOpen ? 'bg-indigo-100 text-indigo-700' : 'text-gray-500 hover:bg-gray-100'}`}
              title="Поиск по сообщениям"
            >
              <Search className="w-5 h-5" />
            </button>
            <div className="flex bg-gray-100 rounded-lg p-0.5">
              <button
                onClick={() => handleViewModeChange('chat')}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${viewMode === 'chat' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
              >
                <MessageSquare className="w-3.5 h-3.5 inline mr-1" />
                Чат
              </button>
              <button
                onClick={() => handleViewModeChange('tasks')}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${viewMode === 'tasks' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
              >
                <CheckCircle className="w-3.5 h-3.5 inline mr-1" />
                Задачи
              </button>
              <button
                onClick={() => handleViewModeChange('knowledge')}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${viewMode === 'knowledge' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
              >
                <BookOpen className="w-3.5 h-3.5 inline mr-1" />
                База знаний
              </button>
            </div>
          </div>
        </div>

        {/* Поисковая строка */}
        {searchOpen && (
          <div className="px-6 py-3 border-b border-gray-200 bg-gray-50">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="Поиск по сообщениям..."
                  className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
              </div>
              <button
                onClick={() => handleSearch()}
                disabled={searching || !searchQuery.trim()}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Найти'}
              </button>
              <button
                onClick={clearSearch}
                className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            {/* Результаты поиска */}
            {searchResults.length > 0 && (
              <div className="mt-3 space-y-2 max-h-60 overflow-y-auto">
                <p className="text-xs text-gray-500 font-medium">
                  Найдено: {searchTotal} сообщений
                </p>
                {searchResults.map((msg) => (
                  <div
                    key={msg.id}
                    className="p-3 bg-white rounded-lg border border-gray-200 cursor-pointer hover:border-indigo-300 transition-colors"
                    onClick={() => {
                      clearSearch();
                    }}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        msg.message_direction === 'director'
                          ? 'bg-indigo-100 text-indigo-700'
                          : 'bg-gray-100 text-gray-600'
                      }`}>
                        {msg.message_direction === 'director' ? 'Директор' : 'Вы'}
                      </span>
                      {msg.created_at && (
                        <span className="text-xs text-gray-400">
                          {format(new Date(msg.created_at), 'dd.MM.yy HH:mm', { locale: ru })}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-700 line-clamp-2">{msg.message}</p>
                  </div>
                ))}
                {searchTotal > searchResults.length && (
                  <button
                    onClick={() => handleSearch(searchPage + 1)}
                    className="w-full py-2 text-sm text-indigo-600 hover:text-indigo-800 font-medium"
                  >
                    Загрузить ещё
                  </button>
                )}
              </div>
            )}
            {searchQuery && !searching && searchResults.length === 0 && (
              <p className="mt-3 text-sm text-gray-500 text-center">Ничего не найдено</p>
            )}
          </div>
        )}

        {/* Область сообщений (чат) */}
        {viewMode === 'chat' && (
          <div className="h-[420px] md:h-[500px] overflow-y-auto px-6 py-4 space-y-4 bg-gray-50/50">
            {messages.length === 0 && !loading && (
              <div className="flex flex-col items-center justify-center h-full text-gray-400">
                <Briefcase className="w-16 h-16 mb-4 text-indigo-300" />
                <h2 className="text-xl font-semibold text-gray-500 mb-2">AI Директор</h2>
                <p className="text-sm text-center max-w-md">
                  Система управления маркетингом. Обсуждайте задачи, ставьте цели,
                  запрашивайте отчёты — директор распределит работу между агентами
                  и предоставит результаты.
                </p>
              </div>
            )}

            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                onActionSelect={(text) => sendMessage(text)}
                onStartReportTask={(action) => handleStartReportTask(action, msg)}
                reportTaskLoading={reportTaskLoading?.startsWith(`${msg.id}:`) ? reportTaskLoading : null}
                onReply={() => setReplyTo(msg)}
                onDelete={async () => {
                  try {
                    await director.chatHistory();
                    setMessages(prev => prev.filter(m => m.id !== msg.id));
                  } catch {}
                }}
              />
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="bg-indigo-50 rounded-2xl rounded-bl-md px-5 py-3 border border-indigo-100">
                  <div className="flex items-center gap-3">
                    <Loader2 className="w-4 h-4 text-indigo-600 animate-spin" />
                    <p className="text-sm text-indigo-600 font-medium">Директор обрабатывает запрос...</p>
                  </div>
                </div>
              </div>
            )}

            {error && (
              <div className="flex justify-center">
                <div className="flex items-center gap-2 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{error}</span>
                  <button
                    onClick={() => setError(null)}
                    className="ml-2 p-1 hover:bg-red-100 rounded transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}

            {!loading && (
              <DirectorQuickActions
                disabled={loading}
                onSelect={(prompt) => sendMessage(prompt)}
              />
            )}

            <div ref={messagesEndRef} />
          </div>
        )}

        {/* Панель задач */}
        {viewMode === 'tasks' && (
          <div className="flex-1 overflow-y-auto px-6 py-4 bg-gray-50/50">
            {/* Фильтры по статусам */}
            <div className="flex items-center justify-between gap-3 mb-4">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">Канбан задач директора</h2>
                <p className="text-xs text-gray-500">Директор видит свои задачи и рабочие задачи агентов.</p>
              </div>
              <button
                onClick={() => handleTaskFilterChange('all')}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
              >
                Обновить
              </button>
            </div>

            {tasksLoading ? (
              <div className="flex items-center justify-center h-40">
                <Loader2 className="w-6 h-6 text-indigo-600 animate-spin" />
              </div>
            ) : taskColumns.flatMap((column) => column.cards).length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-gray-400">
                <CheckCircle className="w-12 h-12 mb-3 text-gray-300" />
                <p className="text-sm font-medium">Задачи не найдены</p>
                <p className="text-xs text-gray-400 mt-1">
                  Нет активных задач. Напишите директору в чате.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-4 gap-3 items-start">
                {taskColumns.map((column) => (
                  <div
                    key={column.id}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={() => handleTaskDrop(column.id)}
                    className="rounded-xl border border-gray-200 bg-gray-100/70 p-2 min-h-80"
                  >
                    <div className="flex items-center justify-between px-2 py-2">
                      <h3 className="text-xs font-semibold text-gray-700">{column.title}</h3>
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-white text-gray-500 border">{column.cards.length}</span>
                    </div>
                    <div className="space-y-2">
                      {column.cards.map((task) => (
                        <DirectorTaskCard
                          key={`${task.source}-${task.id}`}
                          task={task}
                          onDragStart={() => setDraggedTask(task)}
                          onDragEnd={() => setDraggedTask(null)}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Панель базы знаний */}
        {viewMode === 'knowledge' && (
          <div className="flex-1 overflow-y-auto px-6 py-4 bg-gray-50/50">
            {knowledgeLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="w-6 h-6 text-indigo-600 animate-spin" />
              </div>
            ) : knowledgeList.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-400">
                <BookOpen className="w-12 h-12 mb-3 text-gray-300" />
                <p className="text-sm">База знаний пуста</p>
                <p className="text-xs text-gray-400 mt-1">Загрузите документы через раздел «База знаний»</p>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs text-gray-500 font-medium">Всего документов: {knowledgeList.length}</p>
                </div>
                {knowledgeList.map((item) => (
                  <KnowledgeCard
                    key={item.id}
                    item={item}
                    onDelete={async (id) => {
                      try {
                        await director.deleteKnowledge(id);
                        setKnowledgeList(prev => prev.filter(k => k.id !== id));
                      } catch (err) {
                        console.error('Ошибка удаления:', err);
                      }
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Форма ввода (только для чата) */}
        {viewMode === 'chat' && (
          <div className="px-6 py-4 border-t border-gray-200 bg-white shrink-0">
            {replyTo && (
              <div className="flex items-center gap-2 mb-2 px-3 py-2 bg-indigo-50 rounded-lg border border-indigo-200 text-sm">
                <Reply className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                <span className="text-xs text-gray-500 truncate flex-1">
                  Ответ на сообщение: {replyTo.message.slice(0, 80)}{replyTo.message.length > 80 ? '...' : ''}
                </span>
                <button
                  onClick={() => setReplyTo(null)}
                  className="p-1 hover:bg-indigo-100 rounded transition-colors"
                >
                  <X className="w-3.5 h-3.5 text-gray-400" />
                </button>
              </div>
            )}
            {selectedFiles.length > 0 && (
              <div className="mb-3 rounded-xl border border-gray-200 bg-gray-50 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-gray-700 mb-2">Вложения для директора</p>
                    <div className="flex flex-wrap gap-2">
                      {selectedFiles.map((file) => (
                        <div key={`${file.name}-${file.size}`} className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-600">
                          {file.type.startsWith('image/') ? <ImageIcon className="w-3.5 h-3.5 text-indigo-500" /> : <FileText className="w-3.5 h-3.5 text-indigo-500" />}
                          <span className="max-w-44 truncate">{file.name}</span>
                          <span className="text-gray-400">{formatFileSize(file.size)}</span>
                        </div>
                      ))}
                    </div>
                    <input
                      value={uploadMessage}
                      onChange={(e) => setUploadMessage(e.target.value)}
                      placeholder="Комментарий к файлу, если нужен..."
                      className="mt-3 w-full px-3 py-2 border border-gray-200 rounded-lg text-xs bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    />
                    <label className="mt-2 inline-flex items-center gap-2 text-xs text-gray-600">
                      <input
                        type="checkbox"
                        checked={uploadToKnowledge}
                        onChange={(e) => setUploadToKnowledge(e.target.checked)}
                        className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      Добавить в базу знаний директора
                    </label>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={uploadSelectedFiles}
                      disabled={uploadingFiles}
                      className="px-3 py-2 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors flex items-center gap-1.5"
                    >
                      {uploadingFiles ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                      Загрузить
                    </button>
                    <button
                      type="button"
                      onClick={clearSelectedFiles}
                      disabled={uploadingFiles}
                      className="p-2 text-gray-400 hover:text-gray-600 hover:bg-white rounded-lg transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            )}
            <form onSubmit={handleSubmit} className="flex gap-2">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.txt,.md,.csv,.json,image/*"
                onChange={handleFileSelection}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={loading || uploadingFiles}
                className="p-2.5 border border-gray-300 text-gray-500 rounded-xl hover:bg-gray-50 hover:text-indigo-600 disabled:opacity-50 transition-colors"
                title="Прикрепить файл"
              >
                <Paperclip className="w-4 h-4" />
              </button>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={replyTo ? 'Напишите ответ...' : 'Напишите директору...'}
                className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent transition-colors placeholder:text-gray-400"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5 shadow-sm"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                <span className="hidden sm:inline">Отправить</span>
              </button>
            </form>
          </div>
        )}
      </div>
      {viewMode === 'chat' && (workActivity.length > 0 || activityLoading || activeChatTasks.length > 0) && (
        <div className="shrink-0 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Ход работы</h2>
              <p className="text-xs text-gray-500">Цепочка обращений к агентам, инструментам и текущие задачи директора.</p>
            </div>
            <button
              type="button"
              onClick={() => {
                loadTasks(tasksFilter);
                loadWorkActivity();
              }}
              className="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
            >
              Обновить
            </button>
          </div>
          <div className="max-h-72 overflow-y-auto pr-1 space-y-3">
            {(workActivity.length > 0 || activityLoading) && (
              <WorkActivityPanel
                activity={workActivity}
                loading={activityLoading}
                onRefresh={loadWorkActivity}
              />
            )}
            {activeChatTasks.length > 0 && (
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
                <div className="mb-2">
                  <h3 className="text-sm font-semibold text-gray-900">Текущие задачи директора</h3>
                  <p className="text-xs text-gray-500">Карточки для ознакомления, согласования и доработки.</p>
                </div>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                  {activeChatTasks.map((task) => (
                    <ChatTaskCard
                      key={`${task.source}-${task.id}`}
                      task={task}
                      loading={taskActionLoading === `${task.source}-${task.id}`}
                      onApprove={() => handleApproveTaskFromChat(task)}
                      onRevise={() => handleReviseTaskFromChat(task)}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function formatFileSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 Б';
  const units = ['Б', 'КБ', 'МБ', 'ГБ'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, index);
  return `${value >= 10 || index === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
}

function formatModelName(model?: string | null) {
  const value = model || 'openrouter/auto';
  const rawName = value.split('/').pop() || value;
  return rawName
    .replace('-instruct', '')
    .replace('claude-3.5-sonnet', 'openrouter-auto');
}

function ModelBadge({ model, label }: { model?: string | null; label?: string | null }) {
  const text = label || `Модель: ${formatModelName(model)}`;
  return (
    <span
      className="inline-flex items-center rounded-full border border-indigo-100 bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700"
      title={`Подключенное ИИ ядро: ${text}`}
    >
      {text}
    </span>
  );
}

function buildReportTaskCreatedMessage(
  task: AgentInteractionTask,
  action: DirectorReportTaskAction,
  status: string,
  sessionId: string | null
): DirectorChatMessage {
  const now = new Date().toISOString();
  return {
    id: `report-task-created-${task.id}`,
    user_id: '',
    message: `Поставил задачу ${action.agentLabel}: ${action.title}`,
    message_type: 'task',
    message_direction: 'director',
    category: 'task',
    priority: `P${action.priority}`,
    session_id: sessionId,
    created_at: now,
    updated_at: null,
    vector_id: null,
    status: 'completed',
    is_important: true,
    parent_message_id: null,
    related_task_id: task.id,
    extra_data: {
      card_type: 'task_action',
      action: 'created',
      task: {
        id: task.id,
        source: 'agent_interaction',
        title: action.title,
        description: action.description,
        status,
        assigned_to: action.targetAgent,
        priority: `P${action.priority}`,
        extra_data: { href: `/ai-marketer/tasks/${task.id}` },
      },
    },
  };
}

function buildAgentDiscussionMessage({
  task,
  action,
  reply,
  sessionId,
}: {
  task: AgentInteractionTask;
  action: DirectorReportTaskAction;
  reply: string;
  sessionId: string | null;
}): DirectorChatMessage {
  const now = new Date().toISOString();
  const statusNote = task.status === 'completed'
    ? '\n\nСтатус задачи: закрыта, результат можно использовать в отчете.'
    : task.status === 'pending_approval'
      ? '\n\nСтатус задачи: требуется внимание/согласование перед закрытием.'
      : `\n\nСтатус задачи: ${task.status || 'в работе'}. Директор продолжит доводить ее до закрытия.`;
  return {
    id: `agent-discussion-${task.id}-${Date.now()}`,
    user_id: '',
    message: `Получил ответ от ${action.agentLabel} по задаче «${action.title}».${statusNote}\n\n${reply}`,
    message_type: 'report',
    message_direction: 'director',
    category: 'agent_discussion',
    priority: `P${action.priority}`,
    session_id: sessionId,
    created_at: now,
    updated_at: null,
    vector_id: null,
    status: 'completed',
    is_important: true,
    parent_message_id: null,
    related_task_id: task.id,
    extra_data: {
      card_type: 'agent_discussion',
      task_id: task.id,
      target_agent: action.targetAgent,
      agent_label: action.agentLabel,
      action_title: action.title,
      href: `/ai-marketer/tasks/${task.id}`,
    },
  };
}

function buildAgentHandoffPrompt(action: DirectorReportTaskAction, sourceMessage: DirectorChatMessage) {
  const sourceText = stripMarkdown(sourceMessage.message || '').slice(0, 2200);
  if (action.targetAgent === 'crm-agent') {
    return [
      'AI Marketing Director ставит рабочую задачу агенту AI CRM.',
      '',
      `Задача: ${action.title}`,
      '',
      'Нужно подготовить сегментацию и CRM-сценарий НА СОГЛАСОВАНИЕ, а не начинать обсуждение доступных данных.',
      'Результат сегментации должен быть зафиксирован как реальный редактируемый сегмент в БД через существующие фильтры: он должен появиться в «Покупатели → Сегменты покупателей».',
      '',
      `Параметры задачи: ${action.description}`,
      '',
      'Контекст решения директора:',
      sourceText || 'Контекст отсутствует.',
      '',
      'Верни результат строго в таком формате:',
      '1. Название сегмента и цель коммуникации.',
      '2. Критерии включения и исключения: поля CRM/loyalty/покупок/активности, период, канал, магазин/город, consent.',
      '3. Ожидаемый размер сегмента или способ расчета, если точное число требует пересчета.',
      '4. Предложение сообщения: короткий смысл, канал, CTA, ограничения.',
      '5. ID/название сохраненного сегмента и где его отредактировать.',
      '6. Риски и проверки перед запуском.',
      '7. Статус для директора: можно передавать на согласование / нужна доработка, с причиной.',
      '',
      'Не спрашивай “какие данные есть”. Если данных не хватает, укажи это в пункте 5 как проверку, но всё равно предложи рабочую сегментацию на согласование.',
    ].join('\n');
  }

  if (action.targetAgent === 'assortment-agent') {
    return [
      'AI Marketing Director ставит рабочую задачу агенту AI Assortment.',
      '',
      `Задача: ${action.title}`,
      `Параметры: ${action.description}`,
      '',
      'Контекст решения директора:',
      sourceText || 'Контекст отсутствует.',
      '',
      'Верни Product Focus на согласование: товарные группы/SKU-критерии, остатки, приоритет, риски, что передать CRM/контенту.',
    ].join('\n');
  }

  return [
    `AI Marketing Director ставит рабочую задачу агенту ${action.agentLabel}.`,
    '',
    `Задача: ${action.title}`,
    '',
    `Параметры задачи: ${action.description}`,
    '',
    'Контекст решения директора:',
    sourceText || 'Контекст отсутствует.',
    '',
    'Верни рабочий результат на согласование:',
    '1. готовый результат по своей зоне ответственности;',
    '2. какие данные использованы;',
    '3. риски и ограничения;',
    '4. что нужно согласовать;',
    '5. статус для директора: можно передавать дальше / нужна доработка.',
  ].join('\n');
}

function cleanDirectorActionText(value: string) {
  return value
    .replace(/\*\*/g, '')
    .replace(/^["'«»]+|["'«».,;:]+$/g, '')
    .trim();
}

function extractDirectorActionOptions(text: string) {
  const lines = (text || '').split('\n');
  const options: string[] = [];
  let inOptionsBlock = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (/^(варианты|что делаем|можем начать|предлагаю выбрать|выберите|следующие шаги)/i.test(line)) {
      inOptionsBlock = true;
      continue;
    }

    const numbered = line.match(/^\s*(?:[-*]\s*)?(\d{1,2})[.)]\s+(.+)$/);
    if (numbered) {
      const option = cleanDirectorActionText(numbered[2]);
      if (option.length >= 6) options.push(option);
      inOptionsBlock = true;
      continue;
    }

    const bullet = inOptionsBlock ? line.match(/^\s*[-•]\s+(.+)$/) : null;
    if (bullet) {
      const option = cleanDirectorActionText(bullet[1]);
      if (option.length >= 6) options.push(option);
      continue;
    }

    if (inOptionsBlock && !line) continue;
    if (inOptionsBlock && options.length > 0) break;
  }

  return Array.from(new Set(options)).slice(0, 6);
}

function stripMarkdown(value: string) {
  return value
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/\*\*/g, '')
    .replace(/`/g, '')
    .trim();
}

function buildReportSections(text: string) {
  if (!text || text.length < 1200 || !/^#{1,3}\s+/m.test(text)) return null;
  const matches = Array.from(text.matchAll(/^#{1,3}\s+(.+)$/gm));
  if (matches.length < 3) return null;

  const lead = stripMarkdown(text.slice(0, matches[0].index || 0));
  const sections = matches.slice(0, 10).map((match, index) => {
    const start = (match.index || 0) + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index || text.length : text.length;
    const body = stripMarkdown(text.slice(start, end));
    return {
      title: stripMarkdown(match[1]).slice(0, 90),
      body: body.length > 900 ? `${body.slice(0, 900).trim()}...` : body,
    };
  }).filter((section) => section.title && section.body);

  if (!sections.length) return null;
  return { lead, sections, hiddenCount: Math.max(matches.length - sections.length, 0) };
}

function makeReportAction(
  id: string,
  title: string,
  description: string,
  targetAgent: string,
  agentLabel: string,
  taskType: string,
  priority = 2
): DirectorReportTaskAction {
  return { id, title, description, targetAgent, agentLabel, taskType, priority };
}

function extractReportTaskActions(text: string): DirectorReportTaskAction[] {
  const value = (text || '').toLowerCase();
  if (text.length < 900) return [];

  const actions: DirectorReportTaskAction[] = [];
  const has = (...words: string[]) => words.some((word) => value.includes(word.toLowerCase()));

  if (has('crm', 'сегмент', 'vip', 'рассыл')) {
    actions.push(makeReportAction(
      'crm-segmentation',
      'Сегментировать базу и подготовить CRM-сценарий',
      'Собрать релевантные сегменты покупателей, проверить историю покупок, баллы, активность и подготовить сценарий коммуникации с каналами и условиями согласования.',
      'crm-agent',
      'AI CRM',
      'crm_segmentation_and_messaging',
      1
    ));
  }

  if (has('product focus', 'sku', 'uno', 'остат', 'ассортимент')) {
    actions.push(makeReportAction(
      'product-focus',
      'Собрать Product Focus и товарный пул',
      'Проверить остатки, новые SKU, цены, магазины и выделить 12-20 товарных позиций для кампании с тегами hero, statement, giftable и сценариями носки.',
      'assortment-agent',
      'AI Assortment',
      'product_focus_selection',
      1
    ));
  }

  if (has('контент', 'сторис', 'reels', 'фото', 'видео')) {
    actions.push(makeReportAction(
      'content-package',
      'Подготовить контент-пакет кампании',
      'Собрать сторис, фото/видео референсы, hero SKU, тексты и формат визуальной подачи для кампании с учетом роли бренда и персонального медиа.',
      'brand-media-agent',
      'AI Brand Media',
      'campaign_content_package',
      2
    ));
  }

  if (has('kpi', 'измеряем', 'аналитик', 'конверси', 'отчет')) {
    actions.push(makeReportAction(
      'analytics-kpi',
      'Подготовить KPI и аналитику кампании',
      'Определить метрики, базовые значения, контрольные точки и формат отчета: контакт, ответ, визит, покупка, выручка, средний чек и выручка на посетителя.',
      'analytics-agent',
      'AI Analytics',
      'campaign_kpi_report',
      2
    ));
  }

  if (has('трафик', 'digital', 'support', 'канал', 'реклама')) {
    actions.push(makeReportAction(
      'traffic-support',
      'Собрать digital support и каналы трафика',
      'Проверить каналы поддержки кампании, подготовить гипотезы усиления трафика и условия запуска после готовности CRM и контента.',
      'traffic-growth-agent',
      'AI Traffic & Growth',
      'campaign_traffic_support',
      3
    ));
  }

  return actions.slice(0, 5);
}

function DirectorStructuredReport({
  message,
  actions,
  loadingKey,
  onStartReportTask,
}: {
  message: DirectorChatMessage;
  actions: DirectorReportTaskAction[];
  loadingKey?: string | null;
  onStartReportTask?: (action: DirectorReportTaskAction) => void;
}) {
  const report = buildReportSections(message.message);
  if (!report) {
    return <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.message}</p>;
  }

  return (
    <div className="space-y-3">
      {report.lead ? (
        <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 px-3 py-2 text-sm leading-relaxed text-gray-800 whitespace-pre-wrap">
          {report.lead}
        </div>
      ) : null}

      {actions.length > 0 ? (
        <div className="rounded-xl border border-emerald-100 bg-emerald-50/70 p-3">
          <div className="mb-2 flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-emerald-700" />
            <h3 className="text-sm font-semibold text-gray-900">Запустить работу агентам</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {actions.map((action) => {
              const key = `${message.id}:${action.id}`;
              const isLoading = loadingKey === key;
              return (
                <button
                  key={action.id}
                  type="button"
                  disabled={!onStartReportTask || Boolean(loadingKey)}
                  onClick={() => onStartReportTask?.(action)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-xs font-semibold text-emerald-800 shadow-sm transition hover:border-emerald-300 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-60"
                  title={action.description}
                >
                  {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Briefcase className="h-3.5 w-3.5" />}
                  {action.agentLabel}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
        {report.sections.map((section, index) => (
          <details
            key={`${section.title}-${index}`}
            className="rounded-xl border border-gray-200 bg-gray-50 p-3 open:bg-white"
            open={index < 2}
          >
            <summary className="cursor-pointer text-sm font-semibold text-gray-900">
              {section.title}
            </summary>
            <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-gray-600">{section.body}</p>
          </details>
        ))}
      </div>

      <details className="rounded-xl border border-gray-100 bg-white px-3 py-2">
        <summary className="cursor-pointer text-xs font-medium text-gray-500">
          Полный текст отчета{report.hiddenCount ? `, еще разделов: ${report.hiddenCount}` : ''}
        </summary>
        <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-gray-600">{message.message}</p>
      </details>
    </div>
  );
}

function DirectorQuickActions({
  disabled,
  onSelect,
}: {
  disabled: boolean;
  onSelect: (prompt: string) => void;
}) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Предложения директора</h3>
          <p className="text-xs text-gray-500">Быстрый старт для планирования, аналитики и постановки задач агентам.</p>
        </div>
        <Bot className="h-4 w-4 text-gray-400" />
      </div>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-5">
        {directorQuickActions.map((action) => {
          const Icon = action.icon;
          return (
            <button
              key={action.id}
              type="button"
              disabled={disabled}
              onClick={() => onSelect(action.prompt)}
              className="group min-h-24 rounded-xl border border-gray-200 bg-gray-50 p-3 text-left transition hover:-translate-y-0.5 hover:border-indigo-200 hover:bg-white hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            >
              <div className="mb-2 flex items-center gap-2">
                <span className={`flex h-7 w-7 items-center justify-center rounded-lg border ${action.tone}`}>
                  <Icon className="h-3.5 w-3.5" />
                </span>
                <span className="text-sm font-semibold text-gray-900">{action.title}</span>
              </div>
              <p className="text-xs leading-5 text-gray-500">{action.description}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function WorkActivityPanel({
  activity,
  loading,
  onRefresh,
}: {
  activity: any[];
  loading: boolean;
  onRefresh: () => void;
}) {
  const visible = activity.slice(0, 6);
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
            <Activity className="w-4 h-4 text-indigo-600" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Обращения к агентам и инструментам</h2>
            <p className="text-xs text-gray-500">Цепочка обращений к агентам и инструментам.</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-50 flex items-center gap-1.5"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Activity className="w-3.5 h-3.5" />}
          Обновить
        </button>
      </div>
      {visible.length === 0 ? (
        <p className="text-xs text-gray-400">Пока нет зафиксированных обращений.</p>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
          {visible.map((item) => (
            <div key={item.id} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
              <div className="flex items-start gap-2">
                <div className={`mt-0.5 w-7 h-7 rounded-lg flex items-center justify-center ${
                  item.kind === 'tool' ? 'bg-sky-100 text-sky-700' : 'bg-purple-100 text-purple-700'
                }`}>
                  {item.kind === 'tool' ? <Database className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-semibold text-gray-900 truncate">{item.title}</p>
                    {item.created_at ? (
                      <span className="text-[11px] text-gray-400 shrink-0">
                        {format(new Date(item.created_at), 'HH:mm', { locale: ru })}
                      </span>
                    ) : null}
                  </div>
                  <p className="text-xs text-gray-500 truncate">{item.description}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                    <span className="px-1.5 py-0.5 rounded bg-white border border-gray-200 text-gray-500">
                      {item.source} → {item.target}
                    </span>
                    <span className="px-1.5 py-0.5 rounded bg-white border border-gray-200 text-gray-500">
                      {item.status}
                    </span>
                    {item.extra_data?.href ? (
                      <a href={item.extra_data.href} className="text-indigo-600 hover:text-indigo-800">
                        открыть
                      </a>
                    ) : null}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Компонент карточки документа базы знаний
function KnowledgeCard({
  item,
  onDelete,
}: {
  item: any;
  onDelete: (id: string) => Promise<void>;
}) {
  const [deleting, setDeleting] = useState(false);
  const [confirm, setConfirm] = useState(false);

  const handleDelete = async () => {
    if (!confirm) {
      setConfirm(true);
      return;
    }
    setDeleting(true);
    try {
      await onDelete(item.id);
    } finally {
      setDeleting(false);
      setConfirm(false);
    }
  };

  return (
    <div className="p-4 bg-white rounded-xl border border-gray-200 hover:border-gray-300 transition-colors group">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 font-medium">
              {item.category}
            </span>
            <span className="text-xs text-gray-400">{item.content_type}</span>
            {item.content && item.content.includes('элементов') && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700">
                Проиндексировано
              </span>
            )}
          </div>
          <h3 className="text-sm font-semibold text-gray-900">{item.title}</h3>
          <p className="text-xs text-gray-500 mt-1 line-clamp-2">{item.content}</p>
          {item.source && (
            <p className="text-xs text-gray-400 mt-1">Источник: {item.source}</p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {confirm ? (
            <div className="flex items-center gap-1">
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="px-2 py-1 bg-red-600 text-white rounded-lg text-xs font-medium hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {deleting ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Удалить'}
              </button>
              <button
                onClick={() => setConfirm(false)}
                className="p-1 text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <button
              onClick={handleDelete}
              className="p-1.5 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
              title="Удалить документ"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
      {item.created_at && (
        <p className="text-xs text-gray-400 mt-2">
          Добавлено: {format(new Date(item.created_at), 'dd.MM.yyyy', { locale: ru })}
        </p>
      )}
    </div>
  );
}

function ChatTaskCard({
  task,
  loading,
  onApprove,
  onRevise,
}: {
  task: any;
  loading: boolean;
  onApprove: () => void;
  onRevise: () => void;
}) {
  const href = task.extra_data?.href;
  const statusLabel: Record<string, string> = {
    pending: 'Ожидает',
    pending_approval: 'На согласовании',
    validated: 'Проверена',
    approved: 'Согласована',
    queued: 'В очереди',
    processing: 'В работе',
    in_progress: 'В работе',
  };

  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 mb-2">
            <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${
              task.priority === 'P0' ? 'bg-red-100 text-red-700' :
              task.priority === 'P1' ? 'bg-orange-100 text-orange-700' :
              task.priority === 'P2' ? 'bg-yellow-100 text-yellow-700' :
              'bg-gray-100 text-gray-600'
            }`}>
              {task.priority || 'P2'}
            </span>
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-white text-gray-600 border border-gray-200">
              {statusLabel[task.status] || task.status || 'status'}
            </span>
            {task.assigned_to ? (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">
                {task.assigned_to}
              </span>
            ) : null}
          </div>
          <h3 className="text-sm font-semibold text-gray-900 leading-snug">{task.title}</h3>
          {task.description ? <p className="mt-1 text-xs text-gray-500 line-clamp-2">{task.description}</p> : null}
          {task.result_summary ? (
            <div className="mt-2 rounded-lg border border-green-100 bg-green-50 px-2 py-1.5">
              <p className="text-[11px] font-medium text-green-700">Отчет / результат</p>
              <p className="text-xs text-green-700 line-clamp-2">{task.result_summary}</p>
            </div>
          ) : null}
        </div>
        {href ? (
          <a href={href} className="p-1 text-gray-400 hover:text-indigo-600" title="Открыть карточку">
            <ExternalLink className="w-4 h-4" />
          </a>
        ) : null}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onApprove}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-1.5"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
          Согласовать в работу
        </button>
        <button
          type="button"
          onClick={onRevise}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-700 text-xs font-medium hover:bg-gray-50 disabled:opacity-50 flex items-center gap-1.5"
        >
          <Reply className="w-3.5 h-3.5" />
          На доработку
        </button>
      </div>
    </div>
  );
}

function DirectorTaskCard({
  task,
  onDragStart,
  onDragEnd,
}: {
  task: any;
  onDragStart: () => void;
  onDragEnd: () => void;
}) {
  const href = task.extra_data?.href;
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      className="p-3 bg-white rounded-lg border border-gray-200 shadow-sm hover:border-indigo-200 transition-colors cursor-grab active:cursor-grabbing"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5 mb-2">
            <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${
              task.priority === 'P0' ? 'bg-red-100 text-red-700' :
              task.priority === 'P1' ? 'bg-orange-100 text-orange-700' :
              task.priority === 'P2' ? 'bg-yellow-100 text-yellow-700' :
              'bg-gray-100 text-gray-600'
            }`}>
              {task.priority || 'P2'}
            </span>
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-purple-50 text-purple-700">
              {task.task_type}
            </span>
          </div>
          <h4 className="text-sm font-semibold text-gray-900 leading-snug">{task.title}</h4>
        </div>
        {href ? (
          <a href={href} className="p-1 text-gray-400 hover:text-indigo-600" title="Открыть задачу">
            <ExternalLink className="w-4 h-4" />
          </a>
        ) : null}
      </div>
      {task.description ? <p className="text-xs text-gray-500 mt-2 line-clamp-3">{task.description}</p> : null}
      <div className="mt-3 space-y-1 text-[11px] text-gray-400">
        {task.assigned_to ? (
          <div className="flex items-center gap-1">
            <Target className="w-3 h-3" />
            <span>{task.assigned_to}</span>
          </div>
        ) : null}
        {task.created_at ? (
          <div className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            <span>{format(new Date(task.created_at), 'dd.MM.yyyy HH:mm', { locale: ru })}</span>
          </div>
        ) : null}
        {task.deadline_at ? (
          <div className="flex items-center gap-1 text-orange-500">
            <AlertCircle className="w-3 h-3" />
            <span>Срок: {format(new Date(task.deadline_at), 'dd.MM.yyyy', { locale: ru })}</span>
          </div>
        ) : null}
      </div>
      {task.result_summary ? (
        <div className="mt-2 p-2 rounded-md bg-green-50 border border-green-100">
          <p className="text-[11px] font-medium text-green-700">Результат</p>
          <p className="text-xs text-green-700 line-clamp-2">{task.result_summary}</p>
        </div>
      ) : null}
    </div>
  );
}

function DirectorRichBlocks({
  blocks,
  onPeriodRequest,
}: {
  blocks: any[];
  onPeriodRequest?: (prompt: string) => void;
}) {
  if (!blocks?.length) return null;

  return (
    <div className="mt-4 space-y-3">
      {blocks.map((block, index) => (
        <DirectorRichBlock
          key={`${block.type}-${index}`}
          block={block}
          onPeriodRequest={onPeriodRequest}
        />
      ))}
    </div>
  );
}

function DirectorRichBlock({
  block,
  onPeriodRequest,
}: {
  block: any;
  onPeriodRequest?: (prompt: string) => void;
}) {
  if (!block || typeof block !== 'object') return null;

  if (block.type === 'workflow') {
    const steps = Array.isArray(block.steps) ? block.steps : [];
    const dataRequests = Array.isArray(block.data_requests) ? block.data_requests : [];
    const agentRequests = Array.isArray(block.agent_requests) ? block.agent_requests : [];

    return (
      <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 p-3">
        <RichBlockTitle title={block.title || 'Как директор собрал ответ'} meta={block.meta} />
        <div className="grid grid-cols-1 gap-2 xl:grid-cols-3">
          <div className="rounded-lg border border-indigo-100 bg-white p-3">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-indigo-800">
              <Activity className="h-3.5 w-3.5" />
              Цикл
            </div>
            <ol className="space-y-1 text-xs leading-5 text-gray-600">
              {steps.slice(0, 5).map((step: string, index: number) => (
                <li key={index} className="flex gap-2">
                  <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[10px] font-semibold text-indigo-700">
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </div>

          <div className="rounded-lg border border-indigo-100 bg-white p-3">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-indigo-800">
              <Database className="h-3.5 w-3.5" />
              Данные
            </div>
            <div className="space-y-1.5">
              {dataRequests.slice(0, 6).map((item: any) => (
                <div key={item.key || item.label} className="rounded-md bg-gray-50 px-2 py-1.5">
                  <div className="text-xs font-medium text-gray-800">{item.label || item.key}</div>
                  {item.reason ? <div className="mt-0.5 line-clamp-2 text-[11px] text-gray-500">{item.reason}</div> : null}
                </div>
              ))}
              {!dataRequests.length ? <p className="text-xs text-gray-400">Дополнительные источники не потребовались.</p> : null}
            </div>
          </div>

          <div className="rounded-lg border border-indigo-100 bg-white p-3">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-indigo-800">
              <Bot className="h-3.5 w-3.5" />
              Агенты
            </div>
            <div className="space-y-1.5">
              {agentRequests.slice(0, 6).map((item: any) => (
                <div key={item.agent || item.label} className="rounded-md bg-gray-50 px-2 py-1.5">
                  <div className="text-xs font-medium text-gray-800">{item.label || item.agent}</div>
                  {item.expected ? <div className="mt-0.5 line-clamp-2 text-[11px] text-gray-500">{item.expected}</div> : null}
                </div>
              ))}
              {!agentRequests.length ? <p className="text-xs text-gray-400">Ответ собран без профильных агентских задач.</p> : null}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (block.type === 'segment_card') {
    return <SegmentRichBlock block={block} />;
  }

  if (block.type === 'kpi_grid') {
    const items = Array.isArray(block.items) ? block.items : [];
    return (
      <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
        <RichBlockTitle title={block.title} meta={block.meta} />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {items.map((item: any, index: number) => (
            <div key={index} className="rounded-lg border border-gray-200 bg-white px-3 py-2">
              <div className="text-[11px] text-gray-500">{item.label}</div>
              <div className={`mt-1 text-lg font-semibold ${
                item.tone === 'success' ? 'text-emerald-700' :
                item.tone === 'info' ? 'text-indigo-700' :
                'text-gray-900'
              }`}>
                {item.value}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (block.type === 'bar_chart' || block.type === 'line_chart') {
    const data = Array.isArray(block.data) ? block.data : [];
    const series = Array.isArray(block.series) ? block.series : [];
    const xKey = block.x_key || 'name';
    if (!data.length || !series.length) return null;

    return (
      <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <RichBlockTitle title={block.title} compact />
          <ChartPeriodControls
            title={block.title || 'график'}
            onRequest={onPeriodRequest}
          />
        </div>
        <div className="h-64 rounded-lg bg-white p-2">
          <ResponsiveContainer width="100%" height="100%">
            {block.type === 'line_chart' ? (
              <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} width={54} />
                <Tooltip formatter={(value: any) => formatRichValue(value)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {series.map((item: any) => (
                  <Line key={item.key} type="monotone" dataKey={item.key} name={item.label || item.key} stroke={item.color || '#4f46e5'} strokeWidth={2} dot={false} />
                ))}
              </LineChart>
            ) : (
              <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey={xKey} tick={{ fontSize: 11 }} interval={0} angle={-12} textAnchor="end" height={48} />
                <YAxis tick={{ fontSize: 11 }} width={54} />
                <Tooltip formatter={(value: any) => formatRichValue(value)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {series.map((item: any) => (
                  <Bar key={item.key} dataKey={item.key} name={item.label || item.key} fill={item.color || '#4f46e5'} radius={[4, 4, 0, 0]} />
                ))}
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  if (block.type === 'comparison_table') {
    const columns = Array.isArray(block.columns) ? block.columns : [];
    const rows = Array.isArray(block.rows) ? block.rows : [];
    if (!columns.length || !rows.length) return null;

    return (
      <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
        <RichBlockTitle title={block.title} />
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full text-xs">
            <thead className="bg-gray-50 text-gray-500">
              <tr>
                {columns.map((column: any) => (
                  <th key={column.key} className="px-3 py-2 text-left font-medium whitespace-nowrap">{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.map((row: any, rowIndex: number) => (
                <tr key={rowIndex}>
                  {columns.map((column: any) => (
                    <td key={column.key} className="px-3 py-2 text-gray-700 whitespace-nowrap">
                      {formatRichCell(row[column.key], column.format)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (block.type === 'product_cards') {
    const items = Array.isArray(block.items) ? block.items : [];
    if (!items.length) return null;
    return (
      <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
        <RichBlockTitle title={block.title} />
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
          {items.map((item: any, index: number) => (
            <div key={item.id || index} className="flex gap-3 rounded-lg border border-gray-200 bg-white p-2">
              <div className="h-14 w-14 shrink-0 overflow-hidden rounded-md bg-gray-100">
                {item.image_url ? (
                  <img src={item.image_url} alt={item.name || 'Товар'} className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-xs text-gray-400">GLAME</div>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-gray-900">{item.name || 'Товар'}</div>
                <div className="mt-0.5 truncate text-[11px] text-gray-500">{[item.brand, item.category, item.article].filter(Boolean).join(' · ')}</div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {item.metric ? <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] text-indigo-700">{item.metric}</span> : null}
                  {item.revenue ? <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700">{item.revenue}</span> : null}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return null;
}

function RichBlockTitle({
  title,
  meta,
  compact = false,
}: {
  title?: string;
  meta?: Record<string, any>;
  compact?: boolean;
}) {
  return (
    <div className={`${compact ? '' : 'mb-2'} flex flex-wrap items-center justify-between gap-2`}>
      <div className="text-sm font-semibold text-gray-900">{title || 'Данные'}</div>
      {meta?.source ? (
        <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-gray-500 border border-gray-200">{meta.source}</span>
      ) : null}
    </div>
  );
}

function ChartPeriodControls({
  title,
  onRequest,
}: {
  title: string;
  onRequest?: (prompt: string) => void;
}) {
  const [customOpen, setCustomOpen] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const requestPreset = (days: number) => {
    onRequest?.(`Обнови график «${title}» за последние ${days} дней. Покажи только этот график и краткий вывод по нему.`);
  };

  const requestCustom = () => {
    if (!dateFrom || !dateTo) return;
    onRequest?.(`Обнови график «${title}» за период с ${dateFrom} по ${dateTo}. Покажи только этот график и краткий вывод по нему.`);
  };

  return (
    <div className="flex flex-wrap items-center justify-end gap-1.5">
      {[7, 30, 90].map((days) => (
        <button
          key={days}
          type="button"
          onClick={() => requestPreset(days)}
          disabled={!onRequest}
          className="h-7 rounded-md border border-gray-200 bg-white px-2 text-[11px] font-medium text-gray-600 transition hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
          title={`Обновить график за последние ${days} дней`}
        >
          {days}д
        </button>
      ))}
      <button
        type="button"
        onClick={() => setCustomOpen((value) => !value)}
        disabled={!onRequest}
        className="h-7 rounded-md border border-gray-200 bg-white px-2 text-[11px] font-medium text-gray-600 transition hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
        title="Выбрать свой период"
      >
        Период
      </button>
      {customOpen ? (
        <div className="flex flex-wrap items-center gap-1 rounded-lg border border-gray-200 bg-white p-1">
          <input
            type="date"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
            className="h-7 rounded-md border border-gray-200 px-2 text-[11px] text-gray-700 outline-none focus:border-indigo-300"
            aria-label="Дата начала"
          />
          <input
            type="date"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
            className="h-7 rounded-md border border-gray-200 px-2 text-[11px] text-gray-700 outline-none focus:border-indigo-300"
            aria-label="Дата окончания"
          />
          <button
            type="button"
            onClick={requestCustom}
            disabled={!dateFrom || !dateTo}
            className="h-7 rounded-md bg-indigo-600 px-2 text-[11px] font-medium text-white transition hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Обновить
          </button>
        </div>
      ) : null}
    </div>
  );
}

function formatRichValue(value: any) {
  if (typeof value !== 'number') return value;
  return value.toLocaleString('ru-RU');
}

function formatRichCell(value: any, formatType?: string) {
  if (value === null || value === undefined || value === '') return '—';
  const numeric = Number(value);
  if (formatType === 'money' && Number.isFinite(numeric)) return `${numeric.toLocaleString('ru-RU')} ₽`;
  if (formatType === 'percent' && Number.isFinite(numeric)) return `${numeric.toLocaleString('ru-RU')}%`;
  if (formatType === 'number' && Number.isFinite(numeric)) return numeric.toLocaleString('ru-RU');
  return String(value);
}

function SegmentRichBlock({ block }: { block: any }) {
  const segment = block.segment || {};
  const task = block.task || {};
  const actions = Array.isArray(block.actions) ? block.actions : [];
  const rules = segment.rules && typeof segment.rules === 'object'
    ? JSON.stringify(segment.rules, null, 2)
    : '';
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewUsers, setPreviewUsers] = useState<any[]>([]);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [workLoading, setWorkLoading] = useState(false);
  const [workError, setWorkError] = useState<string | null>(null);

  async function openPreview() {
    if (!segment.id) return;
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewUsers([]);
    try {
      const response = await apiClient.get(`/api/customer-segmentation/segments/${segment.id}/users`);
      setPreviewUsers(response.data?.users || []);
    } catch (error: any) {
      try {
        const fallback = await apiClient.get(`/api/admin/customers/segments/${segment.id}/users`);
        setPreviewUsers(fallback.data?.users || []);
      } catch {
        setPreviewError(error?.response?.data?.detail || 'Не удалось загрузить список сегмента');
      }
    } finally {
      setPreviewLoading(false);
    }
  }

  async function sendToWork() {
    if (!task.id) return;
    setWorkLoading(true);
    setWorkError(null);
    try {
      try {
        await agentInteractions.approveTask(task.id, 'Сегмент согласован директором. Переход к подготовке рассылки, сообщений и канала коммуникации.');
      } catch (error: any) {
        const status = error?.response?.status;
        const detail = String(error?.response?.data?.detail || '');
        if (status !== 400 || !detail.toLowerCase().includes('не ожидает одобрения')) {
          throw error;
        }
      }
      window.location.assign(task.href || `/ai-marketer/tasks/${task.id}`);
    } catch (error: any) {
      setWorkError(error?.response?.data?.detail || 'Не удалось перевести задачу в работу');
    } finally {
      setWorkLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-pink-200 bg-pink-50/40 p-3">
      <RichBlockTitle title={block.title || 'Сегмент для согласования'} compact />
      <div className="mt-2 rounded-lg border border-pink-100 bg-white p-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-gray-900">{segment.name || 'Сегмент AI CRM'}</div>
            <div className="mt-1 text-xs text-gray-500">
              segment_id: <span className="font-mono">{segment.id || '—'}</span>
            </div>
            <div className="mt-1 text-xs text-gray-500">
              task_id: <span className="font-mono">{task.id || '—'}</span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[11px] uppercase tracking-wide text-gray-500">Покупателей</div>
            <div className="text-2xl font-bold text-gray-900">{segment.customer_count ?? '—'}</div>
          </div>
        </div>
        {rules ? (
          <details className="mt-3 rounded-md border border-gray-200 bg-gray-50 p-2">
            <summary className="cursor-pointer text-xs font-medium text-gray-700">Фильтр сегмента</summary>
            <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-gray-700">{rules}</pre>
          </details>
        ) : null}
        {actions.length ? (
          <div className="mt-3 space-y-1 text-xs text-gray-700">
            {actions.map((action: string, index: number) => (
              <div key={index}>- {action}</div>
            ))}
          </div>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={openPreview}
            disabled={!segment.id}
            className="inline-flex items-center gap-1 rounded-md border border-pink-200 bg-pink-50 px-3 py-1.5 text-xs font-medium text-pink-700 hover:bg-pink-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Просмотр
          </button>
          <button
            type="button"
            onClick={sendToWork}
            disabled={!task.id || workLoading}
            className="inline-flex items-center gap-1 rounded-md bg-pink-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-pink-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {workLoading ? 'Перевожу...' : 'В работу'}
          </button>
          {task.href ? (
            <a href={task.href} className="inline-flex items-center gap-1 rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800">
              <ExternalLink className="h-3.5 w-3.5" />
              Открыть задачу
            </a>
          ) : null}
          {segment.edit_path ? (
            <a href={segment.edit_path} className="inline-flex items-center gap-1 rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-800 hover:bg-gray-50">
              Редактировать сегмент
            </a>
          ) : null}
        </div>
        {workError ? (
          <div className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{workError}</div>
        ) : null}
      </div>

      {previewOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="flex max-h-[90vh] w-full max-w-5xl flex-col rounded-lg bg-white shadow-xl">
            <div className="flex items-center justify-between border-b p-4">
              <div>
                <div className="text-lg font-semibold text-gray-900">Просмотр сегмента</div>
                <div className="mt-1 text-xs text-gray-500">{segment.name}</div>
              </div>
              <button type="button" onClick={() => setPreviewOpen(false)} className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50">
                Закрыть
              </button>
            </div>
            <div className="overflow-auto p-4">
              {previewLoading ? (
                <div className="py-8 text-center text-sm text-gray-600">Загрузка...</div>
              ) : previewError ? (
                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{previewError}</div>
              ) : previewUsers.length ? (
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-sm font-semibold text-gray-900">Имя</th>
                      <th className="px-3 py-2 text-left text-sm font-semibold text-gray-900">Предпочитаемый магазин</th>
                      <th className="px-3 py-2 text-left text-sm font-semibold text-gray-900">Телефон</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white">
                    {previewUsers.map((user) => (
                      <tr key={user.id}>
                        <td className="px-3 py-2 text-sm text-gray-900">{user.full_name || user.name || '—'}</td>
                        <td className="px-3 py-2 text-sm text-gray-700">{user.preferred_store_name || user.preferred_store || '—'}</td>
                        <td className="px-3 py-2 text-sm text-gray-700">{user.phone || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="py-8 text-center text-sm text-gray-600">В сегменте пока нет покупателей.</div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// Компонент сообщения
function MessageBubble({
  message,
  onActionSelect,
  onStartReportTask,
  reportTaskLoading,
  onReply,
  onDelete,
}: {
  message: DirectorChatMessage;
  onActionSelect: (text: string) => void;
  onStartReportTask?: (action: DirectorReportTaskAction) => void;
  reportTaskLoading?: string | null;
  onReply: () => void;
  onDelete: () => void;
}) {
  const isDirector = message.message_direction === 'director';
  const isSystem = message.status === 'pending' && message.message_direction === 'user';
  const hasError = message.status === 'error';
  const fileMeta = message.extra_data?.file;
  const taskCard = message.extra_data?.card_type === 'task_action' ? message.extra_data?.task : null;
  const richBlocks = Array.isArray(message.extra_data?.rich_blocks) ? message.extra_data.rich_blocks : [];
  const actionOptions = isDirector ? extractDirectorActionOptions(message.message) : [];
  const reportActions = isDirector ? extractReportTaskActions(message.message) : [];

  return (
    <div className={`flex ${isDirector ? 'justify-start' : 'justify-end'} group`}>
      <div className={`${richBlocks.length ? 'max-w-[94%]' : 'max-w-[80%]'} min-w-0 ${isDirector ? 'pr-12' : 'pl-12'}`}>
        {/* Бейдж типа сообщения */}
        {isDirector && message.message_type !== 'text' && (
          <div className="mb-1">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              message.message_type === 'task' ? 'bg-blue-100 text-blue-700' :
              message.message_type === 'report' ? 'bg-green-100 text-green-700' :
              message.message_type === 'approval' ? 'bg-purple-100 text-purple-700' :
              message.message_type === 'knowledge' ? 'bg-amber-100 text-amber-700' :
              message.message_type === 'file' ? 'bg-sky-100 text-sky-700' :
              'bg-gray-100 text-gray-600'
            }`}>
              {message.message_type === 'task' ? 'Задача' :
               message.message_type === 'report' ? 'Отчёт' :
               message.message_type === 'approval' ? 'Согласование' :
               message.message_type === 'knowledge' ? 'База знаний' :
               message.message_type === 'file' ? 'Файл' : 'Сообщение'}
            </span>
          </div>
        )}

        {/* Тело сообщения */}
        <div className={`relative rounded-2xl px-4 py-3 ${
          isDirector
            ? 'bg-white border border-gray-200 rounded-bl-md shadow-sm'
            : hasError
              ? 'bg-red-500 text-white rounded-br-md'
              : isSystem
                ? 'bg-gray-300 text-gray-600 rounded-br-md'
                : 'bg-indigo-600 text-white rounded-br-md'
        }`}>
          {isDirector ? (
            <DirectorStructuredReport
              message={message}
              actions={reportActions}
              loadingKey={reportTaskLoading}
              onStartReportTask={onStartReportTask}
            />
          ) : (
            <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.message}</p>
          )}

          {richBlocks.length > 0 && isDirector ? (
            <DirectorRichBlocks
              blocks={richBlocks}
              onPeriodRequest={onActionSelect}
            />
          ) : null}

          {fileMeta && (
            <div className={`mt-3 rounded-xl border p-3 ${
              isDirector
                ? 'border-gray-200 bg-gray-50'
                : 'border-indigo-400/40 bg-white/10'
            }`}>
              <div className="flex items-start gap-2">
                {String(fileMeta.content_type || '').startsWith('image/') ? (
                  <ImageIcon className={`w-4 h-4 mt-0.5 ${isDirector ? 'text-indigo-500' : 'text-white'}`} />
                ) : (
                  <FileText className={`w-4 h-4 mt-0.5 ${isDirector ? 'text-indigo-500' : 'text-white'}`} />
                )}
                <div className="min-w-0 flex-1">
                  <a
                    href={fileMeta.url}
                    target="_blank"
                    rel="noreferrer"
                    className={`text-xs font-semibold break-all hover:underline ${isDirector ? 'text-gray-800' : 'text-white'}`}
                  >
                    {fileMeta.filename || 'Файл'}
                  </a>
                  <div className={`mt-1 flex flex-wrap items-center gap-2 text-[11px] ${isDirector ? 'text-gray-500' : 'text-indigo-100'}`}>
                    <span>{formatFileSize(Number(fileMeta.file_size || 0))}</span>
                    {fileMeta.detected_type ? <span>{fileMeta.detected_type}</span> : null}
                    {fileMeta.add_to_knowledge ? <span className={isDirector ? 'text-amber-700' : 'text-amber-100'}>в базе знаний</span> : null}
                  </div>
                  {fileMeta.extracted_text_preview ? (
                    <p className={`mt-2 text-xs line-clamp-3 whitespace-pre-wrap ${isDirector ? 'text-gray-600' : 'text-indigo-50'}`}>
                      {fileMeta.extracted_text_preview}
                    </p>
                  ) : null}
                </div>
              </div>
              {String(fileMeta.content_type || '').startsWith('image/') && fileMeta.url ? (
                <img
                  src={fileMeta.url}
                  alt={fileMeta.filename || 'Вложение'}
                  className="mt-3 max-h-48 rounded-lg object-contain bg-white/80"
                />
              ) : null}
            </div>
          )}

          {taskCard && (
            <div className="mt-3 rounded-xl border border-gray-200 bg-gray-50 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5 mb-2">
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 font-medium">
                      {message.extra_data?.action === 'approved' ? 'Согласовано' : 'Доработка'}
                    </span>
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-white text-gray-600 border border-gray-200">
                      {taskCard.status}
                    </span>
                    {taskCard.assigned_to ? (
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">
                        {taskCard.assigned_to}
                      </span>
                    ) : null}
                  </div>
                  <h3 className="text-sm font-semibold text-gray-900">{taskCard.title}</h3>
                  {taskCard.description ? <p className="mt-1 text-xs text-gray-500 line-clamp-2">{taskCard.description}</p> : null}
                  {message.extra_data?.comment ? (
                    <p className="mt-2 rounded-lg bg-white border border-gray-200 px-2 py-1.5 text-xs text-gray-600">
                      Комментарий: {message.extra_data.comment}
                    </p>
                  ) : null}
                </div>
                {taskCard.extra_data?.href ? (
                  <a href={taskCard.extra_data.href} className="p-1 text-gray-400 hover:text-indigo-600" title="Открыть задачу">
                    <ExternalLink className="w-4 h-4" />
                  </a>
                ) : null}
              </div>
            </div>
          )}

          {/* Метаданные для важных сообщений */}
          {message.is_important && isDirector && (
            <div className="mt-2 pt-2 border-t border-indigo-100">
              <div className="flex items-center gap-1 text-xs text-indigo-600">
                <AlertCircle className="w-3 h-3" />
                <span>Важное сообщение</span>
              </div>
            </div>
          )}
        </div>

        {actionOptions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {actionOptions.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onActionSelect(option)}
                className="rounded-full border border-indigo-100 bg-white px-3 py-1.5 text-xs font-medium text-indigo-700 shadow-sm transition hover:border-indigo-200 hover:bg-indigo-50"
                title="Отправить директору этот вариант"
              >
                {option}
              </button>
            ))}
          </div>
        )}

        {/* Нижняя строка: время + кнопки */}
        <div className={`flex items-center gap-2 mt-1 ${isDirector ? '' : 'justify-end'}`}>
          {message.created_at && (
            <span className="text-xs text-gray-400">
              {format(new Date(message.created_at), 'dd.MM.yy HH:mm', { locale: ru })}
            </span>
          )}
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            {!isSystem && !hasError && (
              <>
                <button
                  onClick={onReply}
                  className="p-1 hover:bg-gray-100 rounded transition-colors"
                  title="Ответить"
                >
                  <Reply className="w-3.5 h-3.5 text-gray-400" />
                </button>
                <button
                  onClick={onDelete}
                  className="p-1 hover:bg-red-50 rounded transition-colors"
                  title="Удалить"
                >
                  <Trash2 className="w-3.5 h-3.5 text-gray-400 hover:text-red-500" />
                </button>
              </>
            )}
          </div>
        </div>

        {/* Индикатор parent_message (ответ на сообщение) */}
        {message.parent_message_id && (
          <div className="flex items-center gap-1 mt-0.5">
            <Reply className="w-3 h-3 text-gray-300" />
            <span className="text-xs text-gray-300">Ответ на сообщение</span>
          </div>
        )}
      </div>
    </div>
  );
}
