'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRight, BookOpen, CheckCircle2, ChevronRight, CircleCheck, CircleHelp, ClipboardCheck, Clock3, LockKeyhole, MessageCircle, PlayCircle, Sparkles, Target, X } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';

type Program = {
  id: string;
  code: string;
  title: string;
  description?: string | null;
  status: string;
  progress: { completed_steps: number; total_steps: number; percent: number; pending_reviews: number; revision_count: number };
  next_assignment?: { id?: string; step_id?: string; title: string; status: string } | null;
  preview_mode?: boolean;
};

type Step = {
  id: string;
  title: string;
  status: string;
  lesson_text?: string | null;
  practice_text?: string | null;
  answer_template?: string | null;
  assessment_rubric?: Record<string, unknown>;
  learning_flow?: { slides: Array<{ id: string; eyebrow: string; title: string; body: string; image_url?: string | null; material_id?: string }>; quiz: Array<{ id: string; question: string; options: string[] }>; passing_score: number } | null;
  lesson_material_count?: number;
  lesson_materials?: Array<{ id: string; title: string; role: string; slides: Array<{ id: string; title: string; body?: string | null; image_url?: string | null; order_index: number }> }>;
};

type ProgramDetail = {
  program: { id: string; title: string };
  preview_mode?: boolean;
  next_step?: { id: string; title: string; status: string } | null;
  modules: Array<{ id: string; title: string; steps: Step[] }>;
};

type CurrentTask = {
  primary_task?: { program_id?: string | null; step_id?: string | null; title?: string | null; cta?: string | null } | null;
  seller_guidance?: { recommended_action?: string; micro_practice?: string; review_rule?: string };
};

type Attestation = {
  id: string;
  program_id: string;
  attestation_type: string;
  status: string;
  ai_score?: number | null;
  task_payload?: { title?: string; source?: string; instructions?: string; time_limit_minutes?: number; time_limit_message?: string; started_at?: string; questions?: Array<{ id: string; section: string; question: string }> };
  ai_evaluation?: { overall_summary?: string; manager_recommendation?: string };
};

const statusText: Record<string, string> = {
  available: 'Можно начать',
  in_progress: 'В процессе',
  opened: 'Открыто',
  submitted: 'На проверке',
  waiting_review: 'На проверке',
  needs_revision: 'Нужно доработать',
  accepted: 'Принято',
  completed: 'Пройдено',
};

const completedStatuses = new Set(['accepted', 'completed', 'certified']);

function statusLabel(value?: string | null) {
  return statusText[String(value || '').toLowerCase()] || 'Следующий шаг';
}

function rubricItems(rubric?: Record<string, unknown>) {
  if (!rubric) return [];
  const criteria = rubric.criteria;
  if (Array.isArray(criteria)) return criteria.map(String).filter(Boolean);
  return Object.values(rubric).filter((value): value is string => typeof value === 'string' && Boolean(value.trim())).slice(0, 4);
}

function firstMeaningfulParagraph(text?: string | null) {
  return String(text || '')
    .split(/\n\s*\n|\n/)
    .map((part) => part.replace(/^[-#*\d.\s]+/, '').trim())
    .find(Boolean) || '';
}

export default function LearnerTrainingPage() {
  const { user, accountPreview } = useAuth();
  const subjectConfig = useMemo(() => (
    user?.is_role_preview && accountPreview?.id ? { params: { seller_user_id: accountPreview.id } } : undefined
  ), [accountPreview?.id, user?.is_role_preview]);
  const workspaceRef = useRef<HTMLElement | null>(null);
  const [programs, setPrograms] = useState<Program[]>([]);
  const [catalogMode, setCatalogMode] = useState(false);
  const [currentTask, setCurrentTask] = useState<CurrentTask | null>(null);
  const [attestations, setAttestations] = useState<Attestation[]>([]);
  const [detail, setDetail] = useState<ProgramDetail | null>(null);
  const [selectedProgramId, setSelectedProgramId] = useState<string | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [lessonOpen, setLessonOpen] = useState(false);
  const [lessonStage, setLessonStage] = useState<'slides' | 'quiz'>('slides');
  const [slideIndex, setSlideIndex] = useState(0);
  const [quizAnswers, setQuizAnswers] = useState<Record<string, string>>({});
  const [quizStartedAt, setQuizStartedAt] = useState<string | null>(null);
  const [answer, setAnswer] = useState('');
  const [reflection, setReflection] = useState('');
  const [examAnswers, setExamAnswers] = useState<Record<string, string>>({});
  const [examNow, setExamNow] = useState(() => Date.now());
  const [mentorQuestion, setMentorQuestion] = useState('');
  const [mentorReply, setMentorReply] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [asking, setAsking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [programsResponse, taskResponse, attestationsResponse] = await Promise.all([
        apiClient.get('/api/profile/training/programs', subjectConfig),
        apiClient.get('/api/profile/training/current-task', subjectConfig).catch(() => null),
        apiClient.get('/api/profile/training/attestations', subjectConfig).catch(() => ({ data: { attestations: [] } })),
      ]);
      const loadedPrograms = programsResponse.data.programs || [];
      setPrograms(loadedPrograms);
      setCatalogMode(Boolean(programsResponse.data?.summary?.catalog_mode));
      setCurrentTask(taskResponse?.data?.current_task || null);
      setAttestations(attestationsResponse?.data?.attestations || []);
      const assignedProgram = loadedPrograms.find((program: Program) => ['available', 'in_progress', 'needs_revision', 'waiting_review'].includes(program.status));
      setSelectedProgramId((current) => current || assignedProgram?.id || taskResponse?.data?.current_task?.primary_task?.program_id || loadedPrograms.find((program: Program) => program.next_assignment)?.id || loadedPrograms[0]?.id || null);
    } catch (cause: any) {
      setError(cause.response?.data?.detail || cause.message || 'Не удалось загрузить обучение');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subjectConfig?.params?.seller_user_id]);

  const selectedProgram = programs.find((program) => program.id === selectedProgramId) || null;
  const allSteps = useMemo(() => detail?.modules.flatMap((module) => module.steps) || [], [detail]);
  const selectedStep = allSteps.find((step) => step.id === selectedStepId)
    || allSteps.find((step) => step.id === currentTask?.primary_task?.step_id)
    || allSteps.find((step) => step.id === detail?.next_step?.id)
    || allSteps.find((step) => ['available', 'in_progress', 'needs_revision'].includes(step.status))
    || null;
  const courseTitle = selectedProgram?.title || 'Программа обучения';
  const isAdminPreview = catalogMode && Boolean(selectedProgram?.preview_mode || detail?.preview_mode);
  const traineeExam = attestations.find((item) => item.program_id === selectedProgram?.id && item.attestation_type === 'trainee_blank_2025') || null;
  const examQuestions = traineeExam?.task_payload?.questions || [];
  const canStartTraineeExam = selectedProgram?.code === 'trainee_base' && selectedProgram.progress.percent >= 100 && !traineeExam;
  const examTimeLimitMinutes = traineeExam?.task_payload?.time_limit_minutes || 45;
  const examStartedAt = traineeExam?.task_payload?.started_at ? new Date(traineeExam.task_payload.started_at).getTime() : null;
  const examRemainingSeconds = examStartedAt ? Math.max(0, Math.ceil((examTimeLimitMinutes * 60 * 1000 - (examNow - examStartedAt)) / 1000)) : null;
  const courseNextLesson = selectedStep?.title || selectedProgram?.next_assignment?.title || 'Первый доступный урок';
  const completedLessons = allSteps.filter((step) => completedStatuses.has(step.status)).length;
  const availableLessons = allSteps.filter((step) => ['available', 'in_progress', 'needs_revision'].includes(step.status)).length;
  const lessonText = selectedStep?.lesson_text || '';
  const linkedLessonSlides = useMemo(() => (selectedStep?.lesson_materials || [])
    .flatMap((material) => material.slides.map((slide) => ({ ...slide, material_id: material.id, material_title: material.title })))
    .sort((left, right) => left.order_index - right.order_index), [selectedStep?.lesson_materials]);
  const hasLinkedLessonMaterial = Boolean(selectedStep?.lesson_material_count);
  const learningFlow = linkedLessonSlides.length ? {
    slides: linkedLessonSlides.map((slide, index) => ({
      id: slide.id,
      eyebrow: `Урок программы · слайд ${index + 1}`,
      title: slide.title,
      body: slide.body || '',
      image_url: slide.image_url,
      material_id: slide.material_id,
    })),
    // Until the material question pool is opened in the learner flow, retain
    // the existing validated quiz transport. The visible teaching content is
    // always the attached, published deck.
    quiz: selectedStep?.learning_flow?.quiz || [],
    passing_score: selectedStep?.learning_flow?.passing_score || 0,
  } : hasLinkedLessonMaterial ? null : selectedStep?.learning_flow || null;
  const practiceText = selectedStep?.practice_text || '';
  const answerGuide = selectedStep?.answer_template || '';
  const lessonCards = [
    {
      index: '01',
      title: 'Суть урока',
      text: firstMeaningfulParagraph(lessonText) || 'Поймите одну идею, которую сможете применить в разговоре с клиентом.',
      tone: 'bg-slate-950 text-white',
    },
    {
      index: '02',
      title: 'Держите фокус',
      text: answerGuide || 'Выберите конкретный пример и объясните его спокойно, без давления.',
      tone: 'bg-[#f6eee3] text-amber-950',
    },
    {
      index: '03',
      title: 'Сделайте в смене',
      text: practiceText || 'Попробуйте один приём в реальном диалоге и запомните, что получилось.',
      tone: 'bg-[#eef4f1] text-emerald-950',
    },
  ];

  const openProgram = async (program: Program, scrollToCourse = true) => {
    setSelectedProgramId(program.id);
    setDetail(null);
    setSelectedStepId(null);
    setError(null);
    try {
      const response = await apiClient.get(`/api/profile/training/programs/${program.id}`, subjectConfig);
      setDetail(response.data);
      const nextId = response.data.next_step?.id || program.next_assignment?.step_id || program.next_assignment?.id || null;
      setSelectedStepId(nextId);
      if (scrollToCourse) workspaceRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (cause: any) {
      setError(cause.response?.data?.detail || cause.message || 'Не удалось открыть программу');
    }
  };

  const openLesson = (stepId?: string | null) => {
    if (stepId) setSelectedStepId(stepId);
    setError(null);
    setLessonStage('slides');
    setSlideIndex(0);
    setQuizAnswers({});
    setQuizStartedAt(null);
    setLessonOpen(true);
  };

  const markLessonSlideViewed = async (slide?: { id: string; material_id?: string }) => {
    // Administrator catalogue mode is strictly read-only: it must not create
    // a slide-progress record for the administrator account.
    if (isAdminPreview || !slide?.material_id) return;
    await apiClient.post(`/api/profile/training/materials/${slide.material_id}/slides/${slide.id}/viewed`, {}, subjectConfig);
  };

  const startQuiz = async () => {
    if (!selectedProgram || !selectedStep) return;
    if (isAdminPreview) {
      setLessonStage('quiz');
      return;
    }
    setError(null);
    try {
      const response = await apiClient.post(`/api/profile/training/programs/${selectedProgram.id}/steps/${selectedStep.id}/quiz-start`, {}, subjectConfig);
      setQuizStartedAt(response.data?.quiz_started_at || new Date().toISOString());
    } catch {
      // The server timestamp is preferred for reporting. The fallback keeps
      // the learner moving if a transient network error occurs.
      setQuizStartedAt(new Date().toISOString());
    }
    setLessonStage('quiz');
  };

  const advanceLessonSlide = async () => {
    if (!learningFlow) return;
    const currentSlide = learningFlow.slides[slideIndex];
    setError(null);
    try {
      await markLessonSlideViewed(currentSlide);
      if (slideIndex + 1 < learningFlow.slides.length) {
        setSlideIndex((index) => index + 1);
      } else {
        await startQuiz();
      }
    } catch (cause: any) {
      setError(cause.response?.data?.detail || cause.message || 'Не удалось зафиксировать просмотр слайда');
    }
  };

  useEffect(() => {
    if (!selectedProgram || detail?.program.id === selectedProgram.id) return;
    void openProgram(selectedProgram, false);
    // Program selection is the single source of truth; the detail is loaded eagerly for the course outline.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProgram?.id, detail?.program.id]);

  useEffect(() => {
    if (traineeExam?.status !== 'draft' || !examStartedAt) return;
    setExamNow(Date.now());
    const timer = window.setInterval(() => setExamNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [examStartedAt, traineeExam?.status]);

  const submit = async () => {
    if (learningFlow && learningFlow.quiz.some((question) => !quizAnswers[question.id])) {
      setError('Ответьте на все вопросы короткого опросника.');
      return;
    }
    if (!learningFlow && !answer.trim()) {
      setError('Сначала напишите свой ответ. Его можно коротко сформулировать по шаблону ниже.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      let accepted = false;
      if (selectedProgram && selectedStep) {
        const response = await apiClient.post(`/api/profile/training/programs/${selectedProgram.id}/steps/${selectedStep.id}/submit`, learningFlow ? { quiz_answers: quizAnswers, quiz_started_at: quizStartedAt } : { practice_answer: answer, evening_review: reflection || null }, subjectConfig);
        accepted = response.data?.submission?.status === 'accepted';
        setMessage(response.data?.note || (accepted ? 'Урок закрыт. Открыт следующий этап.' : 'Ответ отправлен.'));
        if (accepted) setLessonOpen(false);
      } else {
        throw new Error('Выберите учебное задание');
      }
      setAnswer('');
      setReflection('');
      await load();
      if (accepted && selectedProgram) await openProgram(selectedProgram, false);
    } catch (cause: any) {
      setError(cause.response?.data?.detail?.message || cause.response?.data?.detail || cause.message || 'Не удалось отправить ответ');
    } finally {
      setSaving(false);
    }
  };

  const askMentor = async () => {
    if (!mentorQuestion.trim()) return;
    setAsking(true);
    setError(null);
    try {
      const response = await apiClient.post('/api/profile/training/mentor/ask', {
        question: mentorQuestion,
        program_id: selectedProgram?.id || currentTask?.primary_task?.program_id || null,
        step_id: selectedStep?.id || currentTask?.primary_task?.step_id || null,
      }, subjectConfig);
      setMentorReply(response.data?.message?.response_text || response.data?.response?.response_text || 'Наставник подготовил подсказку.');
      setMentorQuestion('');
    } catch (cause: any) {
      setError(cause.response?.data?.detail || cause.message || 'Наставник сейчас недоступен');
    } finally {
      setAsking(false);
    }
  };

  const startTraineeExam = async () => {
    if (!selectedProgram) return;
    setSaving(true);
    setError(null);
    try {
      const response = await apiClient.post('/api/profile/training/attestations', { program_id: selectedProgram.id, attestation_type: 'trainee_blank_2025' }, subjectConfig);
      const created = response.data as Attestation;
      setAttestations((current) => [created, ...current]);
      setExamAnswers({});
      setMessage(`Итоговая проверка открыта. У вас ${created.task_payload?.time_limit_minutes || 45} минут; отсчёт уже начался.`);
    } catch (cause: any) {
      setError(cause.response?.data?.detail || cause.message || 'Не удалось открыть итоговую проверку');
    } finally {
      setSaving(false);
    }
  };

  const submitTraineeExam = async () => {
    if (!traineeExam) return;
    const unanswered = examQuestions.filter((question) => !examAnswers[question.id]?.trim());
    if (unanswered.length && examRemainingSeconds !== 0) {
      setError(`Ответьте на все вопросы: осталось ${unanswered.length}.`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const response = await apiClient.post(`/api/profile/training/attestations/${traineeExam.id}/submit`, { answer_payload: examAnswers }, subjectConfig);
      const submitted = response.data as Attestation;
      setAttestations((current) => current.map((item) => item.id === submitted.id ? submitted : item));
      setMessage('Ответы отправлены. AI-наставник подготовил предварительную оценку, управляющий увидит результат и подтвердит итог.');
    } catch (cause: any) {
      setError(cause.response?.data?.detail || cause.message || 'Не удалось отправить проверку');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="mx-auto max-w-3xl p-6 text-sm text-slate-500">Готовим ваш учебный маршрут…</div>;
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:py-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-amber-700">GLAME Academy</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">Обучение</h1>
          <p className="mt-2 text-sm text-slate-600">Сначала программа и урок, затем практика в смене и обратная связь.</p>
        </div>
        <div className="rounded-2xl bg-white px-4 py-3 text-right shadow-sm ring-1 ring-slate-200">
          <div className="text-xs text-slate-500">{isAdminPreview ? 'Режим просмотра' : 'Ваш прогресс'}</div>
          <div className="mt-0.5 text-lg font-semibold text-slate-950">{isAdminPreview ? 'Админ' : `${selectedProgram?.progress.percent || 0}%`}</div>
        </div>
      </header>

      {error ? <div role="alert" className="mb-5 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{typeof error === 'string' ? error : 'Не удалось выполнить действие'}</div> : null}
      {message ? <div role="status" className="mb-5 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">{message}</div> : null}

      {catalogMode ? <section className="mb-6 rounded-3xl border border-indigo-100 bg-indigo-50 p-5 sm:p-6">
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-indigo-700">Режим администратора</p>
        <h2 className="mt-1 text-xl font-semibold text-slate-950">Доступные программы обучения</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">Просмотр не меняет назначения, прогресс и результаты сотрудников. Чтобы назначить программу, используйте GLAME AI Trainer.</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {programs.map((program) => <button key={program.id} type="button" onClick={() => void openProgram(program)} className={`rounded-2xl border p-4 text-left transition ${selectedProgram?.id === program.id ? 'border-slate-950 bg-white shadow-sm' : 'border-indigo-100 bg-white/70 hover:border-indigo-400'}`}><div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold text-slate-950">{program.title}</h3><p className="mt-1 text-sm leading-5 text-slate-600">{program.description || 'Описание программы будет добавлено.'}</p></div><ChevronRight size={18} className="shrink-0 text-indigo-600" /></div><p className="mt-3 text-xs font-semibold text-indigo-700">{program.progress.total_steps} уроков · открыть структуру</p></button>)}
        </div>
      </section> : null}

      <section className="overflow-hidden rounded-3xl bg-slate-950 text-white shadow-xl">
        <div className="grid gap-6 p-6 sm:p-8 lg:grid-cols-[1fr_210px] lg:items-end">
          <div>
            <div className="flex items-center gap-2 text-sm font-medium text-amber-300"><Sparkles size={16} /> {isAdminPreview ? 'Предпросмотр программы' : 'Ваша программа'}</div>
            <h2 className="mt-3 max-w-2xl text-2xl font-semibold leading-tight sm:text-3xl">{courseTitle}</h2>
            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300">{isAdminPreview ? 'Откройте структуру, чтобы проверить порядок и состав уроков.' : <>Следующий урок: <b className="text-white">{courseNextLesson}</b>. После урока можно перейти к практике в смене.</>}</p>
            <button onClick={() => { if (selectedProgram) void openProgram(selectedProgram, false); if (!isAdminPreview) openLesson(selectedStep?.id); }} className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-white px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-amber-50">
              {isAdminPreview ? 'Открыть структуру' : 'Открыть урок'} <ArrowRight size={17} />
            </button>
          </div>
          <div className="rounded-2xl bg-white/10 p-5">
            <div className="text-xs uppercase tracking-[0.14em] text-slate-400">Прохождение</div>
            <div className="mt-2 text-lg font-semibold">{completedLessons || selectedProgram?.progress.completed_steps || 0} из {allSteps.length || selectedProgram?.progress.total_steps || 0} уроков</div>
            <div className="mt-5 h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-amber-300" style={{ width: `${selectedProgram?.progress.percent || 0}%` }} /></div>
            <div className="mt-2 text-xs text-slate-400">{selectedProgram?.progress.completed_steps || 0} из {selectedProgram?.progress.total_steps || 0} этапов</div>
          </div>
        </div>
      </section>

      <section ref={workspaceRef} className="mt-6 rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200 sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">Структура программы</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">{courseTitle}</h2>
            <p className="mt-1 text-sm text-slate-500">Курс открывается последовательно: пройденный урок открывает следующий.</p>
          </div>
          <div className="flex gap-2 text-center text-xs">
            <div className="rounded-xl bg-emerald-50 px-3 py-2 text-emerald-800"><b className="block text-base">{completedLessons || selectedProgram?.progress.completed_steps || 0}</b>пройдено</div>
            <div className="rounded-xl bg-amber-50 px-3 py-2 text-amber-900"><b className="block text-base">{availableLessons}</b>доступно</div>
            <div className="rounded-xl bg-slate-100 px-3 py-2 text-slate-600"><b className="block text-base">{Math.max(0, (allSteps.length || selectedProgram?.progress.total_steps || 0) - (completedLessons || selectedProgram?.progress.completed_steps || 0) - availableLessons)}</b>впереди</div>
          </div>
        </div>
        <div className="mt-5 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-slate-950 transition-all" style={{ width: `${selectedProgram?.progress.percent || 0}%` }} /></div>
        {detail ? (
          <div className="mt-5 space-y-4">
            {detail.modules.map((module) => (
              <section key={module.id} className="rounded-2xl border border-slate-200 p-4">
                <h3 className="text-sm font-semibold text-slate-950">{module.title}</h3>
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  {module.steps.map((step, index) => {
                    const done = completedStatuses.has(step.status);
                    const locked = step.status === 'locked';
                    const isCurrent = selectedStep?.id === step.id;
                    return (
                      <button key={step.id} type="button" disabled={locked} onClick={() => openLesson(step.id)} className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${isCurrent ? 'border-slate-950 bg-slate-50' : 'border-slate-200 hover:border-slate-400'}`}>
                        {done ? <CircleCheck size={20} className="shrink-0 text-emerald-600" /> : locked ? <LockKeyhole size={18} className="shrink-0 text-slate-400" /> : <PlayCircle size={20} className="shrink-0 text-amber-700" />}
                        <span className="min-w-0 flex-1"><b className="block truncate text-slate-900">{index + 1}. {step.title}</b><span className="text-xs text-slate-500">{statusLabel(step.status)}</span></span>
                        {!locked && !done ? <ChevronRight size={17} className="text-slate-400" /> : null}
                      </button>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        ) : <div className="mt-5 rounded-2xl bg-slate-50 p-4 text-sm text-slate-500">Загружаем уроки программы…</div>}
      </section>

      {selectedProgram?.code === 'trainee_base' && !isAdminPreview ? <section className="mt-6 rounded-3xl border border-amber-100 bg-amber-50 p-5 sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="text-xs font-bold uppercase tracking-[0.14em] text-amber-800">Финальный этап</p><h2 className="mt-1 text-xl font-semibold text-slate-950">Итоговая проверка стажёра</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-700">Контрольные вопросы составлены по бланку стажёра 2025. AI-наставник даст предварительную оценку, а управляющий подтвердит результат.</p></div>
          {traineeExam?.ai_score !== null && traineeExam?.ai_score !== undefined ? <div className="rounded-2xl bg-white px-4 py-3 text-right shadow-sm"><div className="text-xs text-slate-500">Предварительная оценка AI</div><div className="text-xl font-semibold text-slate-950">{traineeExam.ai_score}/100</div></div> : null}
        </div>
        {!traineeExam && !canStartTraineeExam ? <div className="mt-5 rounded-2xl bg-white/70 p-4 text-sm text-slate-700">Проверка откроется после завершения всех обязательных уроков программы.</div> : null}
        {canStartTraineeExam ? <button type="button" onClick={startTraineeExam} disabled={saving} className="mt-5 inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white disabled:bg-slate-400"><ClipboardCheck size={17} />{saving ? 'Открываем…' : 'Пройти итоговую проверку (45 мин)'}</button> : null}
        {traineeExam?.status === 'draft' ? <div className="mt-6 space-y-5">{traineeExam.task_payload?.instructions ? <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-white/70 p-4 text-sm leading-6 text-slate-700"><p>{traineeExam.task_payload.instructions}<br />{traineeExam.task_payload.time_limit_message || `На проверку отводится ${examTimeLimitMinutes} минут.`}</p><div className={`rounded-xl px-3 py-2 text-right font-semibold ${examRemainingSeconds === 0 ? 'bg-red-100 text-red-800' : 'bg-slate-950 text-white'}`}><span className="block text-xs font-normal">Осталось</span>{examRemainingSeconds == null ? '—' : `${String(Math.floor(examRemainingSeconds / 60)).padStart(2, '0')}:${String(examRemainingSeconds % 60).padStart(2, '0')}`}</div></div> : null}{examQuestions.map((question, index) => <label key={question.id} className="block rounded-2xl bg-white p-4 shadow-sm"><span className="text-xs font-bold uppercase tracking-[0.12em] text-amber-800">{question.section}</span><span className="mt-2 block text-sm font-semibold leading-6 text-slate-950">{index + 1}. {question.question}</span><textarea disabled={examRemainingSeconds === 0} value={examAnswers[question.id] || ''} onChange={(event) => setExamAnswers((current) => ({ ...current, [question.id]: event.target.value }))} placeholder="Ответьте своими словами; приведите пример, если он уместен." className="mt-3 min-h-28 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm leading-6 outline-none focus:border-slate-950 focus:ring-2 focus:ring-slate-100 disabled:bg-slate-100" /></label>)}<button type="button" onClick={submitTraineeExam} disabled={saving} className="inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white disabled:bg-slate-400"><ClipboardCheck size={17} />{examRemainingSeconds === 0 ? 'Отправить результат с отметкой о времени' : saving ? 'Проверяем…' : 'Отправить на итоговую проверку'}</button></div> : null}
        {traineeExam && traineeExam.status !== 'draft' ? <div className="mt-5 rounded-2xl bg-white p-5 text-sm leading-6 text-slate-700"><p className="font-semibold text-slate-950">{traineeExam.status === 'review_pending' ? 'AI-наставник оценил ответы — результат передан управляющему.' : 'Итоговая проверка завершена.'}</p><p className="mt-2">{traineeExam.ai_evaluation?.overall_summary || 'Управляющий проверит результат и сообщит следующий шаг.'}</p>{traineeExam.ai_evaluation?.manager_recommendation ? <p className="mt-3"><b>Дальше:</b> {traineeExam.ai_evaluation.manager_recommendation}</p> : null}</div> : null}
      </section> : null}

      <section className="hidden" aria-hidden="true">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-amber-50 p-2 text-amber-800"><BookOpen size={20} /></div>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">Текущий урок программы</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">{selectedStep?.title || 'Ожидайте назначения программы'}</h2>
          </div>
        </div>

        {selectedStep ? (
          <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div>
              <div className="grid gap-3 sm:grid-cols-3">
                {lessonCards.map((card) => (
                  <article key={card.index} className={`min-h-44 rounded-2xl p-5 ${card.tone}`}>
                    <div className="text-xs font-bold tracking-[0.16em] opacity-60">{card.index}</div>
                    <h3 className="mt-6 text-base font-semibold">{card.title}</h3>
                    <p className="mt-2 text-sm leading-6 opacity-85">{card.text}</p>
                  </article>
                ))}
              </div>
              {lessonText ? (
                <details className="mt-4 rounded-2xl bg-slate-50 px-5 py-4 text-sm text-slate-700">
                  <summary className="cursor-pointer font-semibold text-slate-900">Открыть методичку полностью</summary>
                  <p className="mt-4 whitespace-pre-wrap leading-7">{lessonText}</p>
                </details>
              ) : null}
              <div className="mt-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-950"><Target size={17} /> Результат задания</div>
                <label htmlFor="training-answer" className="mt-2 block text-sm text-slate-600">Напишите, как применили тему в разговоре с клиентом.</label>
                <textarea id="training-answer" value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="Опишите, как выполнили практику урока…" className="mt-2 min-h-36 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm leading-6 outline-none transition focus:border-slate-950 focus:ring-2 focus:ring-slate-100" />
                <label htmlFor="training-reflection" className="mt-3 block text-sm font-medium text-slate-700">Короткий вывод после смены <span className="font-normal text-slate-400">(необязательно)</span></label>
                <textarea id="training-reflection" value={reflection} onChange={(event) => setReflection(event.target.value)} placeholder="Что сработало или что хочется разобрать?" className="mt-2 min-h-20 w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-slate-950 focus:ring-2 focus:ring-slate-100" />
                <button onClick={submit} disabled={saving} className="mt-4 inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:bg-slate-300"><CheckCircle2 size={17} /> {saving ? 'Отправляем…' : 'Отправить на проверку'}</button>
              </div>
            </div>
            <aside className="space-y-4">
              <div className="rounded-2xl border border-slate-200 p-5">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-950"><CircleHelp size={17} /> Как ответить хорошо</div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-600">{answerGuide || 'Назовите конкретный пример, объясните пользу для клиента и опишите своё действие.'}</p>
                {rubricItems(selectedStep?.assessment_rubric).length ? <ul className="mt-3 space-y-2 text-xs leading-5 text-slate-500">{rubricItems(selectedStep?.assessment_rubric).map((item) => <li key={item}>• {item}</li>)}</ul> : null}
              </div>
              <div className="rounded-2xl bg-slate-50 p-5">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-950"><Clock3 size={17} /> Что дальше</div>
                <p className="mt-2 text-sm leading-6 text-slate-600">После отправки руководитель проверит ответ и либо примет этап, либо бережно подскажет, что доработать.</p>
              </div>
            </aside>
          </div>
        ) : <p className="mt-5 rounded-2xl bg-slate-50 p-5 text-sm leading-6 text-slate-600">Пока нет назначенного задания. Обратитесь к управляющему, чтобы он назначил вам программу обучения.</p>}
      </section>

      {lessonOpen ? <div role="dialog" aria-modal="true" aria-label="Урок программы" className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/60 px-3 py-4 backdrop-blur-sm sm:p-8" onMouseDown={() => setLessonOpen(false)}>
        <div className="mx-auto min-h-full max-w-4xl rounded-3xl bg-white shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
          <div className="sticky top-0 z-10 flex items-start justify-between gap-4 rounded-t-3xl border-b border-slate-100 bg-white/95 px-5 py-5 backdrop-blur sm:px-7">
            <div><p className="text-xs font-bold uppercase tracking-[0.14em] text-amber-700">Урок программы</p><h2 className="mt-1 text-xl font-semibold text-slate-950 sm:text-2xl">{selectedStep?.title || 'Загружаем урок…'}</h2></div>
            <button type="button" aria-label="Закрыть урок" onClick={() => setLessonOpen(false)} className="rounded-xl p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-950"><X size={22} /></button>
          </div>
          {selectedStep ? <div className="p-5 sm:p-7">
            {learningFlow && lessonStage === 'slides' ? <div>
              <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-[0.14em] text-slate-400"><span>Изучение материала</span><span>{slideIndex + 1} / {learningFlow.slides.length}</span></div>
              {learningFlow.slides.map((slide, index) => index === slideIndex ? <article key={slide.id} className="mt-4 overflow-hidden rounded-3xl bg-slate-950 p-7 text-white sm:p-10">{slide.image_url ? <img src={slide.image_url} alt="" className="mb-7 h-56 w-full rounded-2xl object-cover sm:h-80" /> : null}<p className="text-xs font-bold uppercase tracking-[0.16em] text-amber-300">{slide.eyebrow}</p><h3 className="mt-4 text-2xl font-semibold sm:text-3xl">{slide.title}</h3><p className="mt-6 max-w-2xl whitespace-pre-wrap text-base leading-8 text-slate-200">{slide.body}</p></article> : null)}
              <div className="mt-5 flex justify-end"><button type="button" onClick={() => void advanceLessonSlide()} className="inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white">{slideIndex + 1 < learningFlow.slides.length ? <>Следующий слайд <ChevronRight size={17} /></> : <>Перейти к опроснику <ArrowRight size={17} /></>}</button></div>
            </div> : learningFlow ? <div>
              <div className="rounded-2xl bg-amber-50 p-4"><p className="text-xs font-bold uppercase tracking-[0.14em] text-amber-800">Короткий опросник</p><h3 className="mt-1 text-xl font-semibold text-slate-950">Проверьте понимание урока</h3><p className="mt-2 text-sm text-slate-600">Ответьте на {learningFlow.quiz.length} вопроса. Для закрытия урока нужно минимум {learningFlow.passing_score} правильных ответа.</p></div>
              <div className="mt-5 space-y-4">{learningFlow.quiz.map((question, index) => <fieldset key={question.id} className="rounded-2xl border border-slate-200 p-4"><legend className="px-1 text-sm font-semibold leading-6 text-slate-950">{index + 1}. {question.question}</legend><div className="mt-3 space-y-2">{question.options.map((option) => <label key={option} className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-3 text-sm transition ${quizAnswers[question.id] === option ? 'border-slate-950 bg-slate-50' : 'border-slate-200 hover:border-slate-400'}`}><input type="radio" name={question.id} checked={quizAnswers[question.id] === option} onChange={() => setQuizAnswers((current) => ({ ...current, [question.id]: option }))} /><span>{option}</span></label>)}</div></fieldset>)}</div>
              <div className="mt-5 flex flex-wrap justify-between gap-3"><button type="button" onClick={() => setLessonStage('slides')} className="rounded-2xl border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700">К слайдам</button>{isAdminPreview ? <button type="button" onClick={() => setLessonOpen(false)} className="inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white"><X size={17} />Закрыть просмотр</button> : <button type="button" onClick={submit} disabled={saving} className="inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white disabled:bg-slate-300"><ClipboardCheck size={17} />{saving ? 'Проверяем…' : 'Завершить урок'}</button>}</div>
            </div> : <div className="rounded-2xl bg-slate-50 p-5 text-sm text-slate-600">Для этого урока пока нет опубликованных слайдов. Стажёр увидит материал после публикации слайдов администратором.</div>}
          </div> : <div className="p-7 text-sm text-slate-500">Готовим урок…</div>}
        </div>
      </div> : null}

      <section className="mt-6 rounded-3xl border border-amber-100 bg-amber-50 p-5 sm:p-7">
        <div className="flex items-center gap-2 text-amber-950"><MessageCircle size={19} /><h2 className="font-semibold">Спросите AI-наставника</h2></div>
        <p className="mt-2 text-sm leading-6 text-amber-900">Если формулировка или практика непонятны, задайте короткий вопрос. Финальное решение по ответу остаётся за руководителем.</p>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row"><input value={mentorQuestion} onChange={(event) => setMentorQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') askMentor(); }} placeholder="Например: как мягко предложить комплект?" className="min-w-0 flex-1 rounded-xl border border-amber-200 bg-white px-4 py-3 text-sm outline-none focus:border-amber-600" /><button onClick={askMentor} disabled={asking || !mentorQuestion.trim()} className="rounded-xl bg-amber-800 px-5 py-3 text-sm font-semibold text-white disabled:bg-amber-300">{asking ? 'Думаю…' : 'Спросить'}</button></div>
        {mentorReply ? <div className="mt-4 rounded-2xl bg-white p-4 text-sm leading-6 text-slate-700">{mentorReply}</div> : null}
      </section>
    </div>
  );
}
