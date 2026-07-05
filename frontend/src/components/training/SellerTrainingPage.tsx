'use client';

import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiClient } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';

type TrainingTopic = {
  id: string;
  lesson_date: string;
  title: string;
  theme?: string | null;
  goal?: string | null;
  material_text?: string | null;
  assignment_text?: string | null;
  focus_text?: string | null;
  status: string;
};

type TrainingAssignment = {
  id: string;
  topic_id: string;
  status: string;
  opened_at?: string | null;
  completed_at?: string | null;
};

type TrainingItem = { topic: TrainingTopic; assignment: TrainingAssignment };

type VoiceAnswerDraft = {
  filename?: string;
  mime_type?: string;
  content_base64?: string;
  transcript?: string;
  duration_seconds?: number;
  source: 'uploaded' | 'recorded' | 'dictated';
};

type VoiceAnswerTarget = 'step' | 'topic';

type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop?: () => void;
};

type TrainingProgram = {
  id: string;
  code: string;
  title: string;
  description?: string | null;
  program_type: string;
  status: string;
  access_mode?: 'assigned' | 'free' | 'request_required' | 'requested';
  is_required: boolean;
  average_score?: number | null;
  progress: {
    completed_steps: number;
    total_steps: number;
    percent: number;
    pending_reviews: number;
    revision_count: number;
  };
  next_assignment?: {
    assignment_id?: string;
    topic_id?: string;
    step_id?: string;
    id?: string;
    title: string;
    lesson_date?: string | null;
    status: string;
  } | null;
  cta: string;
  meta?: Record<string, any>;
};

type TrainingProgramDetail = {
  program: { id: string; code: string; title: string; description?: string | null };
  progress: { completed_steps: number; total_steps: number; percent: number };
  next_step?: { id: string; title: string; status: string } | null;
  modules: Array<{
    id: string;
    title: string;
    description?: string | null;
    steps: Array<{
      id: string;
      title: string;
      status: string;
      lesson_text?: string | null;
      practice_text?: string | null;
      answer_template?: string | null;
      assessment_rubric?: Record<string, any>;
      score?: number | null;
      competencies?: string[];
    }>;
  }>;
};

type CompetencySummary = {
  level: string;
  completed_steps: number;
  total_steps: number;
  average_score?: number | null;
  attestation_ready: boolean;
  competencies: Record<string, { code: string; label: string; accepted_steps: number; total_steps: number; percent: number; average_score?: number | null }>;
  strongest_competencies: Array<{ code: string; label: string; percent: number }>;
  weakest_competencies: Array<{ code: string; label: string; percent: number }>;
  achievements: Array<{ code: string; title: string; description: string }>;
};

type Attestation = {
  id: string;
  program_id: string;
  attestation_type: string;
  status: string;
  eligible?: boolean;
  recommended_level?: string | null;
  ai_score?: number | null;
  manager_feedback?: string | null;
  certified_level?: string | null;
  task_payload?: { title?: string; cases?: string[] };
};

type MentorMessage = {
  id: string;
  question_text?: string | null;
  response_text: string;
  context?: {
    focus_tags?: string[];
    program_title?: string;
    step_title?: string;
    library_context?: {
      selected_materials?: number;
      source_materials?: Array<{ id?: string | null; title?: string | null; topic?: string | null; category?: string | null }>;
    };
  };
  created_at?: string | null;
};

type ShiftReflection = {
  id: string;
  shift_date?: string | null;
  store_name?: string | null;
  reflection_payload?: { worked_well?: string; difficult_scenario?: string; glame_argument?: string; needs_help?: string };
  ai_score?: number | null;
  status: string;
  seller_feedback?: string | null;
  manager_feedback?: string | null;
  created_at?: string | null;
};

type CoachingAction = {
  id: string;
  status: string;
  planned_for?: string | null;
  store_name?: string | null;
  coaching_topic: string;
  competency?: string | null;
  kpi_metric?: string | null;
  seller_next_step?: string | null;
  seller_visible_feedback?: string | null;
  created_at?: string | null;
};

type TrainingMaterial = {
  id: string;
  title: string;
  topic: string;
  category: string;
  description?: string | null;
  markdown_content: string;
  status: string;
  tags?: string[];
  program_code?: string | null;
  order_index: number;
};

type TrainingMaterialSlide = {
  id: string;
  title: string;
  body?: string | null;
  image_url?: string | null;
  quiz_question?: string | null;
  status: string;
  order_index: number;
  progress?: { viewed?: boolean; completed?: boolean; viewed_at?: string | null; completed_at?: string | null };
};

type TrainingMaterialSlidesSummary = {
  slides?: number;
  completed_slides?: number;
  progress_percent?: number;
  material_completed?: boolean;
};

type StepMaterialLink = {
  id: string;
  material_id?: string | null;
  step_id: string;
  role: string;
  required_to_complete: boolean;
  title?: string | null;
  topic?: string | null;
  material?: TrainingMaterial;
};

type StepMaterialPracticeGate = {
  can_start_practice: boolean;
  blocked_reason?: string | null;
  required_materials?: number;
  completed_required_materials?: number;
  blocked_materials?: Array<{ material_id?: string | null; title?: string | null; progress_percent?: number; completed_slides?: number; slides?: number }>;
  next_action?: string;
};

type StepMaterialsResponse = {
  summary?: { steps?: number; unlocked_materials?: number };
  current_step?: { id: string; title?: string | null; status?: string; materials?: StepMaterialLink[]; practice_gate?: StepMaterialPracticeGate } | null;
  steps?: Array<{ id: string; title?: string | null; status?: string; is_unlocked?: boolean; locked_reason?: string | null; materials?: StepMaterialLink[] }>;
};

type CurrentLearningTask = {
  primary_task?: {
    program_id?: string | null;
    program_code?: string | null;
    program_title?: string | null;
    step_id?: string | null;
    title?: string | null;
    status?: string;
    cta?: string;
    progress?: { completed_steps?: number; total_steps?: number; percent?: number };
  };
  seller_guidance?: { recommended_action?: string; micro_practice?: string; review_rule?: string; revision_rule?: string };
  learning_flow?: string[];
  knowledge_focus?: { code?: string; label?: string; percent?: number } | null;
  mentor_prompt?: string;
};

type TrainingMentorSession = {
  stage: 'materials' | 'practice' | 'review' | 'waiting' | 'program';
  message?: string;
  next_action?: string;
  material_id?: string | null;
  step_id?: string | null;
  program_id?: string | null;
  mentor_prompt?: string;
  context?: {
    task_title?: string | null;
    step_title?: string | null;
    material_title?: string | null;
    daily_focus?: string | null;
    review_rule?: string;
    material_progress?: {
      slides?: number;
      completed_slides?: number;
      progress_percent?: number;
      material_completed?: boolean;
    };
    practice_assignment?: {
      title?: string;
      task?: string;
      try_phrase?: string;
      answer_template?: string;
      good_answer_example?: string;
      assessment_criteria?: string[];
      review_rule?: string;
    };
  };
};

type CareerLevel = {
  current_level?: { code: string; title: string; score: number };
  next_level?: { code: string; title: string; min_score: number };
  level_track?: Array<{ code: string; title: string; min_score: number }>;
  score_breakdown?: Record<string, number>;
  requirements_to_next_level?: string[];
  salary_policy?: { status: string; description: string };
  mentor_rule?: string;
};

type DailyTrainingFocus = {
  priority: string;
  level?: string | null;
  progress_percent?: number;
  today_focus?: {
    metric?: string;
    training_competency?: string;
    kpi_completion_percent?: number | null;
    avg_check?: number | null;
    items_per_check?: number | null;
  };
  training_step?: { program_title?: string | null; title?: string | null; target_id?: string | null };
  recommended_action?: string;
  micro_practice?: string;
  mentor_prompt?: string;
  tone_guardrails?: string;
  schedule_context?: {
    mode: string;
    title: string;
    shift_count?: number;
    nearest_shift?: { date?: string; store_name?: string | null; start_time?: string | null; end_time?: string | null } | null;
  };
  weakest_competencies?: Array<{ label: string; percent: number }>;
  kpi_focus?: string[];
};

const statusLabels: Record<string, string> = {
  not_opened: 'Не открыто',
  opened: 'Открыто',
  in_progress: 'В процессе',
  submitted: 'Ответ отправлен',
  needs_revision: 'Нужно доработать',
  accepted: 'Принято',
  locked: 'Недоступна',
  available: 'Доступна',
  waiting_review: 'Ожидает проверки',
  completed: 'Завершена',
  certified: 'Аттестована',
};

const programAccent: Record<string, string> = {
  trainee_base: 'from-amber-50 to-white border-amber-200',
  stylist_academy: 'from-slate-50 to-white border-slate-200',
};

export default function SellerTrainingPage() {
  const { user, accountPreview } = useAuth();
  const trainingSubjectParams = useMemo(() => (user?.is_role_preview && accountPreview?.id ? { seller_user_id: accountPreview.id } : undefined), [accountPreview?.id, user?.is_role_preview]);
  const trainingSubjectConfig = useMemo(() => (trainingSubjectParams ? { params: trainingSubjectParams } : undefined), [trainingSubjectParams]);
  const trainingWorkspaceRef = useRef<HTMLElement | null>(null);
  const mentorControlRef = useRef<HTMLElement | null>(null);
  const practiceAssignmentRef = useRef<HTMLDivElement | null>(null);
  const mentorChatRef = useRef<HTMLElement | null>(null);
  const autoRouteDoneRef = useRef(false);
  const [programs, setPrograms] = useState<TrainingProgram[]>([]);
  const [summary, setSummary] = useState<{ level?: string; program_count?: number }>({});
  const [items, setItems] = useState<TrainingItem[]>([]);
  const [active, setActive] = useState<TrainingItem | null>(null);
  const [selectedProgramCode, setSelectedProgramCode] = useState<string | null>(null);
  const [selectedMaterialProgramCode, setSelectedMaterialProgramCode] = useState<string | null>(null);
  const [programDetail, setProgramDetail] = useState<TrainingProgramDetail | null>(null);
  const [programDetailLoading, setProgramDetailLoading] = useState(false);
  const [activeStep, setActiveStep] = useState<TrainingProgramDetail['modules'][number]['steps'][number] | null>(null);
  const [competencySummary, setCompetencySummary] = useState<CompetencySummary | null>(null);
  const [attestations, setAttestations] = useState<Attestation[]>([]);
  const [mentorMessages, setMentorMessages] = useState<MentorMessage[]>([]);
  const [shiftReflections, setShiftReflections] = useState<ShiftReflection[]>([]);
  const [coachingActions, setCoachingActions] = useState<CoachingAction[]>([]);
  const [trainingMaterials, setTrainingMaterials] = useState<TrainingMaterial[]>([]);
  const [stepMaterials, setStepMaterials] = useState<StepMaterialsResponse | null>(null);
  const [activeSlideMaterialId, setActiveSlideMaterialId] = useState<string | null>(null);
  const [activeMaterialSlides, setActiveMaterialSlides] = useState<TrainingMaterialSlide[]>([]);
  const [activeMaterialSlidesSummary, setActiveMaterialSlidesSummary] = useState<TrainingMaterialSlidesSummary | null>(null);
  const [activeSlideIndex, setActiveSlideIndex] = useState(0);
  const [markingSlideId, setMarkingSlideId] = useState<string | null>(null);
  const [materialSearch, setMaterialSearch] = useState('');
  const [materialTopicFilter, setMaterialTopicFilter] = useState('');
  const [dailyFocus, setDailyFocus] = useState<DailyTrainingFocus | null>(null);
  const [currentLearningTask, setCurrentLearningTask] = useState<CurrentLearningTask | null>(null);
  const [mentorSession, setMentorSession] = useState<TrainingMentorSession | null>(null);
  const [careerLevel, setCareerLevel] = useState<CareerLevel | null>(null);
  const [mentorQuestion, setMentorQuestion] = useState('');
  const [mentorLoading, setMentorLoading] = useState(false);
  const [attestationAnswer, setAttestationAnswer] = useState('');
  const [stepAnswer, setStepAnswer] = useState('');
  const [stepEveningReview, setStepEveningReview] = useState('');
  const [voiceAnswer, setVoiceAnswer] = useState<VoiceAnswerDraft | null>(null);
  const [voiceStatus, setVoiceStatus] = useState<string | null>(null);
  const [isRecordingVoice, setIsRecordingVoice] = useState(false);
  const [isDictatingVoice, setIsDictatingVoice] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaChunksRef = useRef<Blob[]>([]);
  const recordingStartedAtRef = useRef<number | null>(null);
  const [reflectionForm, setReflectionForm] = useState({ worked_well: '', difficult_scenario: '', glame_argument: '', needs_help: '' });
  const [reflectionLoading, setReflectionLoading] = useState(false);
  const [practiceAnswer, setPracticeAnswer] = useState('');
  const [eveningReview, setEveningReview] = useState('');
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadItems = async () => {
    setLoading(true);
    setError(null);
    try {
      const [programsResponse, topicsResponse, competenciesResponse, attestationsResponse, mentorResponse, mentorSessionResponse, currentTaskResponse, dailyFocusResponse, reflectionsResponse, coachingResponse, materialsResponse, stepMaterialsResponse] = await Promise.all([
        apiClient.get('/api/profile/training/programs', trainingSubjectConfig),
        apiClient.get('/api/profile/training/topics', trainingSubjectConfig),
        apiClient.get('/api/profile/training/competencies', trainingSubjectConfig),
        apiClient.get('/api/profile/training/attestations', trainingSubjectConfig),
        apiClient.get('/api/profile/training/mentor/messages', trainingSubjectConfig),
        apiClient.get('/api/profile/training/mentor/session', trainingSubjectConfig).catch(() => null),
        apiClient.get('/api/profile/training/current-task', trainingSubjectConfig).catch(() => null),
        apiClient.get('/api/profile/training/daily-focus', trainingSubjectConfig).catch(() => null),
        apiClient.get('/api/profile/training/shift-reflections', trainingSubjectConfig).catch(() => null),
        apiClient.get('/api/profile/training/coaching-actions', trainingSubjectConfig).catch(() => null),
        apiClient.get('/api/profile/training/materials', trainingSubjectConfig).catch(() => null),
        apiClient.get('/api/profile/training/step-materials', trainingSubjectConfig).catch(() => null),
      ]);
      const loadedPrograms = programsResponse.data.programs || [];
      const loadedItems = topicsResponse.data.items || [];
      setPrograms(loadedPrograms);
      setSummary(programsResponse.data.summary || {});
      setCompetencySummary(competenciesResponse.data.summary || null);
      setAttestations(attestationsResponse.data.attestations || []);
      setMentorMessages(mentorResponse.data.messages || []);
      setMentorSession(mentorSessionResponse?.data?.session || null);
      setCurrentLearningTask(mentorSessionResponse?.data?.current_task || currentTaskResponse?.data?.current_task || null);
      setCareerLevel(currentTaskResponse?.data?.career_level || null);
      setDailyFocus(currentTaskResponse?.data?.daily_focus || dailyFocusResponse?.data?.daily_focus || null);
      setShiftReflections(reflectionsResponse?.data?.reflections || []);
      setCoachingActions(coachingResponse?.data?.coaching_actions || []);
      setTrainingMaterials(materialsResponse?.data?.materials || []);
      setStepMaterials(mentorSessionResponse?.data?.step_materials || stepMaterialsResponse?.data || null);
      const preferredMaterialProgramCode = mentorSessionResponse?.data?.current_task?.primary_task?.program_code || currentTaskResponse?.data?.current_task?.primary_task?.program_code || loadedPrograms.find((program: TrainingProgram) => program.next_assignment)?.code || loadedPrograms[0]?.code || null;
      setItems(loadedItems);
      setSelectedProgramCode((current) => current || loadedPrograms[0]?.code || null);
      setSelectedMaterialProgramCode((current) => current || preferredMaterialProgramCode);
      setActive((current) => current || loadedItems[0] || null);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось загрузить обучение');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    autoRouteDoneRef.current = false;
    loadItems();
    return () => {
      mediaRecorderRef.current?.stream.getTracks().forEach((track) => track.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trainingSubjectParams?.seller_user_id]);

  const resetVoiceAnswer = () => {
    setVoiceAnswer(null);
    setVoiceStatus(null);
  };

  const fileToBase64 = (file: Blob): Promise<string> => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      resolve(result.includes(',') ? result.split(',')[1] : result);
    };
    reader.onerror = () => reject(reader.error || new Error('Не удалось прочитать голосовой файл'));
    reader.readAsDataURL(file);
  });

  const applyVoiceTranscript = (target: VoiceAnswerTarget, transcript: string) => {
    const value = transcript.trim();
    if (!value) return;
    if (target === 'step') {
      setStepAnswer((current) => (current.trim() ? `${current.trim()}
${value}` : value));
    } else {
      setPracticeAnswer((current) => (current.trim() ? `${current.trim()}
${value}` : value));
    }
    setVoiceAnswer({ source: 'dictated', transcript: value, mime_type: 'text/plain' });
    setVoiceStatus('Надиктованный ответ распознан и добавлен в текст. Перед отправкой можно поправить формулировку.');
  };

  const handleVoiceFileUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!file.type.startsWith('audio/')) {
      setError('Можно загрузить только аудиофайл с голосовым ответом');
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      setError('Голосовой ответ слишком большой, максимум 15 МБ');
      return;
    }
    setError(null);
    setVoiceStatus('Загружаю голосовой ответ…');
    try {
      const contentBase64 = await fileToBase64(file);
      setVoiceAnswer({ filename: file.name, mime_type: file.type || 'audio/webm', content_base64: contentBase64, source: 'uploaded' });
      setVoiceStatus('Голосовой файл прикреплён. После отправки он пойдёт на транскрибацию и проверку руководителем.');
    } catch (e: any) {
      setError(e.message || 'Не удалось подготовить голосовой файл');
      setVoiceStatus(null);
    }
  };

  const startVoiceRecording = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError('Браузер не поддерживает запись голоса. Можно загрузить готовый аудиофайл.');
      return;
    }
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaChunksRef.current = [];
      recordingStartedAtRef.current = Date.now();
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) mediaChunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        const mimeType = recorder.mimeType || 'audio/webm';
        const audioBlob = new Blob(mediaChunksRef.current, { type: mimeType });
        stream.getTracks().forEach((track) => track.stop());
        const startedAt = recordingStartedAtRef.current;
        recordingStartedAtRef.current = null;
        setIsRecordingVoice(false);
        if (!audioBlob.size) {
          setVoiceStatus(null);
          setError('Голосовая запись пустая');
          return;
        }
        if (audioBlob.size > 15 * 1024 * 1024) {
          setVoiceStatus(null);
          setError('Голосовая запись слишком большая, максимум 15 МБ');
          return;
        }
        try {
          const contentBase64 = await fileToBase64(audioBlob);
          setVoiceAnswer({
            filename: `glame-voice-answer-${new Date().toISOString().replace(/[:.]/g, '-')}.webm`,
            mime_type: mimeType,
            content_base64: contentBase64,
            duration_seconds: startedAt ? Math.round((Date.now() - startedAt) / 1000) : undefined,
            source: 'recorded',
          });
          setVoiceStatus('Голосовой ответ записан. После отправки он будет транскрибирован и разобран AI-наставником/руководителем.');
        } catch (e: any) {
          setError(e.message || 'Не удалось подготовить голосовую запись');
        }
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecordingVoice(true);
      setVoiceStatus('Идёт запись голосового ответа…');
    } catch {
      setError('Не удалось получить доступ к микрофону. Можно загрузить готовый аудиофайл.');
    }
  };

  const stopVoiceRecording = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  };

  const startSpeechDictation = (target: VoiceAnswerTarget) => {
    const SpeechRecognitionCtor = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      setError('В этом браузере нет распознавания речи. Используйте запись голоса или загрузите аудиофайл.');
      return;
    }
    setError(null);
    const recognition: SpeechRecognitionLike = new SpeechRecognitionCtor();
    recognition.lang = 'ru-RU';
    recognition.interimResults = false;
    recognition.continuous = false;
    setIsDictatingVoice(true);
    setVoiceStatus('Говорите ответ вслух — браузер преобразует его в текст для проверки.');
    recognition.onresult = (event: any) => {
      const transcript = Array.from(event.results || [])
        .map((result: any) => result?.[0]?.transcript || '')
        .join(' ')
        .trim();
      applyVoiceTranscript(target, transcript);
    };
    recognition.onerror = () => {
      setIsDictatingVoice(false);
      setVoiceStatus(null);
      setError('Не удалось распознать голос. Можно записать аудио или загрузить файл.');
    };
    recognition.onend = () => setIsDictatingVoice(false);
    recognition.start();
  };

  const buildVoiceSubmissionPayload = () => (voiceAnswer ? { voice_answer: voiceAnswer } : {});

  const hasAnswerForSubmit = (answer: string) => Boolean(answer.trim() || voiceAnswer?.content_base64 || voiceAnswer?.transcript);

  const renderVoiceAnswerControls = (target: VoiceAnswerTarget, disabled = false) => (
    <div className="mt-3 rounded-2xl border border-sky-100 bg-sky-50 p-4 text-sm text-sky-950">
      <div className="font-semibold">Устный ответ продавца</div>
      <p className="mt-1 text-sky-800">
        Ответ лучше сдавать голосом: так руководитель видит живую речь продавца, затем запись транскрибируется в текст и анализируется AI-наставником.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <label className={`cursor-pointer rounded-xl border border-sky-200 bg-white px-3 py-2 font-semibold text-sky-900 ${disabled ? 'pointer-events-none opacity-50' : ''}`}>
          Загрузить голосовое
          <input type="file" accept="audio/*" className="hidden" onChange={handleVoiceFileUpload} disabled={disabled} />
        </label>
        <button type="button" onClick={isRecordingVoice ? stopVoiceRecording : startVoiceRecording} disabled={disabled} className="rounded-xl bg-sky-700 px-3 py-2 font-semibold text-white disabled:bg-slate-300">
          {isRecordingVoice ? 'Остановить запись' : 'Записать голосовое'}
        </button>
        <button type="button" onClick={() => startSpeechDictation(target)} disabled={disabled || isDictatingVoice} className="rounded-xl bg-white px-3 py-2 font-semibold text-sky-900 ring-1 ring-sky-200 disabled:opacity-50">
          {isDictatingVoice ? 'Слушаю…' : 'Надиктовать в текст'}
        </button>
        {voiceAnswer ? (
          <button type="button" onClick={resetVoiceAnswer} className="rounded-xl px-3 py-2 font-semibold text-slate-500 hover:bg-white">Убрать голосовое</button>
        ) : null}
      </div>
      {voiceStatus ? <p className="mt-2 text-xs text-sky-700">{voiceStatus}</p> : null}
      {voiceAnswer?.filename ? <p className="mt-2 text-xs text-slate-600">Файл: {voiceAnswer.filename}</p> : null}
      {voiceAnswer?.transcript ? <p className="mt-2 rounded-xl bg-white p-3 text-xs text-slate-700">Транскрипт: {voiceAnswer.transcript}</p> : null}
    </div>
  );

  const openStepMaterialSlides = async (materialId?: string | null) => {
    if (!materialId) return;
    setError(null);
    try {
      const response = await apiClient.get(`/api/profile/training/materials/${materialId}/slides`, trainingSubjectConfig);
      setActiveSlideMaterialId(materialId);
      setActiveMaterialSlides(response.data.slides || []);
      setActiveMaterialSlidesSummary(response.data.summary || null);
      setActiveSlideIndex(0);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось открыть слайды материала');
    }
  };

  const markSlideViewed = async (materialId: string | undefined | null, slideId: string) => {
    if (!materialId) return;
    setMarkingSlideId(slideId);
    setError(null);
    try {
      const response = await apiClient.post(`/api/profile/training/materials/${materialId}/slides/${slideId}/viewed`, {}, trainingSubjectConfig);
      setActiveSlideMaterialId(materialId);
      setActiveMaterialSlides(response.data.slides || []);
      setActiveMaterialSlidesSummary(response.data.summary || null);
      setMessage(response.data.message || 'Слайд отмечен как изученный');
      await loadItems();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось отметить слайд');
    } finally {
      setMarkingSlideId(null);
    }
  };

  const openTopic = async (item: TrainingItem) => {
    setActive(item);
    setPracticeAnswer('');
    setEveningReview('');
    resetVoiceAnswer();
    if (item.assignment.status === 'not_opened') {
      try {
        await apiClient.post(`/api/profile/training/topics/${item.topic.id}/open`, {}, trainingSubjectConfig);
        await loadItems();
      } catch {
        // открытие не должно мешать чтению материала
      }
    }
  };

  const scrollToTrainingWorkspace = () => {
    window.setTimeout(() => {
      trainingWorkspaceRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 80);
  };

  const scrollToPracticeAssignment = () => {
    window.setTimeout(() => {
      practiceAssignmentRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 80);
  };

  const scrollToMentorChat = (prefill?: string) => {
    if (prefill) setMentorQuestion(prefill);
    window.setTimeout(() => {
      mentorChatRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 80);
  };

  const openProgram = async (program: TrainingProgram, shouldScroll = false) => {
    setSelectedProgramCode(program.code);
    setProgramDetailLoading(true);
    setError(null);
    try {
      const response = await apiClient.get(`/api/profile/training/programs/${program.id}`, trainingSubjectConfig);
      setProgramDetail(response.data);
      setActiveStep(response.data.next_step || null);
      setStepAnswer('');
      setStepEveningReview('');
      resetVoiceAnswer();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось открыть программу');
    } finally {
      setProgramDetailLoading(false);
      if (shouldScroll) {
        scrollToTrainingWorkspace();
      }
    }
    const nextTopicId = program.next_assignment?.topic_id;
    if (nextTopicId) {
      const item = items.find((candidate) => candidate.topic.id === nextTopicId);
      if (item) {
        openTopic(item);
      }
    }
  };

  const subscribeToProgram = async (program: TrainingProgram) => {
    setError(null);
    try {
      const response = await apiClient.post(`/api/profile/training/programs/${program.id}/subscribe`, {}, trainingSubjectConfig);
      setPrograms(response.data.programs || []);
      setMessage(response.data.message || `Вы подписались на программу «${program.title}».`);
      await loadItems();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось подписаться на программу');
    }
  };

  const requestProgramAccess = async (program: TrainingProgram) => {
    setError(null);
    try {
      const response = await apiClient.post(`/api/profile/training/programs/${program.id}/request-access`, {
        message: `Продавец запросил допуск к программе «${program.title}» через AI-наставника`,
      }, trainingSubjectConfig);
      setPrograms(response.data.programs || []);
      setMessage(response.data.message || `Запрос на допуск к программе «${program.title}» отправлен руководителю.`);
      await loadItems();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось отправить запрос на допуск');
    }
  };

  const handleProgramAccessAction = (program: TrainingProgram) => {
    if (program.access_mode === 'free') {
      subscribeToProgram(program);
      return;
    }
    if (program.status === 'access_requested' || program.access_mode === 'requested') {
      setMessage('Запрос на допуск уже отправлен. Наставник предложит свободные материалы или программы, пока руководитель принимает решение.');
      return;
    }
    requestProgramAccess(program);
  };

  const startPrimaryLearning = () => {
    if (agentStage === 'materials' && firstUnlockedMaterial?.id) {
      openStepMaterialSlides(firstUnlockedMaterial.id);
      window.setTimeout(() => mentorControlRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120);
      return;
    }
    if (agentStage === 'practice') {
      if (!activeStep && (assignedCourseProgram || primaryProgram)) {
        openProgram(assignedCourseProgram || primaryProgram, false);
      }
      scrollToPracticeAssignment();
      return;
    }
    if (agentStage === 'review') {
      scrollToMentorChat('Когда будет обратная связь по моему ответу и что повторить пока жду проверку?');
      return;
    }
    const programToOpen = assignedCourseProgram || primaryProgram;
    if (!programToOpen) return;
    if (['locked', 'access_requested'].includes(programToOpen.status) || programToOpen.access_mode === 'request_required') {
      handleProgramAccessAction(programToOpen);
      return;
    }
    openProgram(programToOpen, true);
  };

  const submitAnswer = async () => {
    if (!active) return;
    setError(null);
    try {
      await apiClient.post(`/api/profile/training/topics/${active.topic.id}/submit`, {
        practice_answer: practiceAnswer,
        evening_review: eveningReview,
        ...buildVoiceSubmissionPayload(),
      }, trainingSubjectConfig);
      setMessage('Ответ отправлен на проверку. Голосовая запись будет транскрибирована, AI подготовит черновой разбор, руководитель подтвердит обратную связь.');
      setPracticeAnswer('');
      setEveningReview('');
      resetVoiceAnswer();
      await loadItems();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось отправить ответ');
    }
  };

  const submitStepAnswer = async () => {
    if (!programDetail || !activeStep) return;
    setError(null);
    try {
      await apiClient.post(`/api/profile/training/programs/${programDetail.program.id}/steps/${activeStep.id}/submit`, {
        practice_answer: stepAnswer,
        evening_review: stepEveningReview,
        ...buildVoiceSubmissionPayload(),
      }, trainingSubjectConfig);
      setMessage('Ответ по этапу отправлен на проверку. Голос будет транскрибирован, AI подготовит черновик, руководитель подтвердит обратную связь.');
      setStepAnswer('');
      setStepEveningReview('');
      resetVoiceAnswer();
      const detailResponse = await apiClient.get(`/api/profile/training/programs/${programDetail.program.id}`, trainingSubjectConfig);
      setProgramDetail(detailResponse.data);
      setActiveStep(detailResponse.data.next_step || activeStep);
      await loadItems();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось отправить ответ по этапу');
    }
  };

  const startAttestation = async () => {
    const program = programs.find((item) => item.status !== 'locked') || programs[0];
    if (!program) return;
    setError(null);
    try {
      await apiClient.post('/api/profile/training/attestations', { program_id: program.id, attestation_type: program.code === 'stylist_academy' ? 'stylist_final' : 'trainee_final' }, trainingSubjectConfig);
      setMessage('Аттестация открыта. Заполните практический кейс и отправьте на проверку.');
      await loadItems();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось открыть аттестацию');
    }
  };

  const submitAttestation = async (attestation: Attestation) => {
    setError(null);
    try {
      await apiClient.post(`/api/profile/training/attestations/${attestation.id}/submit`, {
        answer_payload: { case_answer: attestationAnswer },
      }, trainingSubjectConfig);
      setAttestationAnswer('');
      setMessage('Аттестация отправлена руководителю. AI-оценка будет проверена менеджером.');
      await loadItems();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось отправить аттестацию');
    }
  };

  const submitShiftReflection = async () => {
    if (!reflectionForm.worked_well.trim() || !reflectionForm.glame_argument.trim()) {
      setError('Заполните, что получилось, и какой GLAME-аргумент сработал.');
      return;
    }
    setReflectionLoading(true);
    setError(null);
    try {
      const nearestShift = dailyFocus?.schedule_context?.nearest_shift;
      await apiClient.post('/api/profile/training/shift-reflections', {
        ...reflectionForm,
        shift_date: nearestShift?.date || null,
        store_name: nearestShift?.store_name || null,
        daily_focus: dailyFocus || {},
      }, trainingSubjectConfig);
      setMessage('Рефлексия сохранена. Если нужен разбор, руководитель увидит сигнал и поможет без публичной оценки.');
      setReflectionForm({ worked_well: '', difficult_scenario: '', glame_argument: '', needs_help: '' });
      await loadItems();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить рефлексию');
    } finally {
      setReflectionLoading(false);
    }
  };

  const askMentor = async (questionOverride?: string) => {
    const question = (questionOverride || mentorQuestion).trim();
    if (!question) return;
    setMentorLoading(true);
    setError(null);
    try {
      const selectedProgram = programs.find((program) => program.code === selectedProgramCode && !['locked', 'archived'].includes(program.status)) || assignedCourseProgram || activePrograms[0];
      const response = await apiClient.post('/api/profile/training/mentor/ask', {
        question,
        program_id: programDetail?.program.id || selectedProgram?.id,
        step_id: activeStep?.id,
        context: {
          program_title: programDetail?.program.title || selectedProgram?.title,
          step_title: activeStep?.title,
          topic_title: active?.topic.title,
        },
      }, trainingSubjectConfig);
      setMentorMessages((current) => [response.data.message, ...current]);
      setMentorQuestion('');
      if (response.data.requires_manager_review) {
        setMessage('AI-наставник дал учебную подсказку. Финальную оценку подтвердит руководитель.');
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось получить подсказку наставника');
    } finally {
      setMentorLoading(false);
    }
  };

  const totalCompleted = useMemo(() => programs.reduce((sum, program) => sum + (program.progress?.completed_steps || 0), 0), [programs]);
  const totalSteps = useMemo(() => programs.reduce((sum, program) => sum + (program.progress?.total_steps || 0), 0), [programs]);
  const averageScore = useMemo(() => {
    const scores = programs.map((program) => program.average_score).filter((score): score is number => typeof score === 'number');
    if (!scores.length) return null;
    return Math.round((scores.reduce((sum, score) => sum + score, 0) / scores.length) * 10) / 10;
  }, [programs]);

  const assignedPrograms = useMemo(() => programs.filter((program) => {
    if (['locked', 'archived', 'access_requested'].includes(program.status)) return false;
    return Boolean(program.next_assignment || program.progress?.completed_steps || program.status !== 'available');
  }), [programs]);
  const availablePrograms = useMemo(() => programs.filter((program) => !['archived'].includes(program.status)), [programs]);
  const activePrograms = useMemo(() => programs.filter((program) => !['locked', 'archived', 'access_requested'].includes(program.status)), [programs]);
  const primaryProgram = useMemo(() => {
    return assignedPrograms.find((program) => program.next_assignment) || assignedPrograms[0] || null;
  }, [assignedPrograms]);
  const suggestedPrograms = useMemo(() => {
    const assignedIds = new Set(assignedPrograms.map((program) => program.id));
    return availablePrograms.filter((program) => !assignedIds.has(program.id)).slice(0, 4);
  }, [assignedPrograms, availablePrograms]);
  const primaryAssignment = primaryProgram?.next_assignment || null;
  const currentTaskPrimary = currentLearningTask?.primary_task || null;
  const primaryTitle = currentTaskPrimary?.title || primaryAssignment?.title || primaryProgram?.title;
  const basePrimaryCta = currentTaskPrimary?.cta || (primaryProgram?.progress?.completed_steps ? 'Продолжить обучение' : 'Начать обучение');
  const taskProgramTitle = currentTaskPrimary?.program_title || primaryProgram?.title || 'GLAME school';
  const taskStatus = statusLabels[currentTaskPrimary?.status || primaryAssignment?.status || 'available'] || currentTaskPrimary?.status || primaryAssignment?.status || 'Доступна';
  const taskCompetency = currentLearningTask?.knowledge_focus?.label || dailyFocus?.today_focus?.training_competency || 'Стандарты бренда';
  const taskMicroPractice = currentLearningTask?.seller_guidance?.micro_practice || dailyFocus?.micro_practice || 'Выберите конкретное украшение и сформулируйте одну спокойную GLAME-фразу для клиента.';
  const taskAnswerTemplate = '1) Украшение или ситуация клиента. 2) Что оно даёт образу / сервису. 3) Как вы применили это в смене. 4) Точная GLAME-фраза клиенту. 5) Что получилось и что хотите улучшить.';
  const sessionPracticeAssignment = mentorSession?.context?.practice_assignment || null;
  const taskAssessmentCriteria = [
    'конкретика: есть изделие, клиентская ситуация или наблюдение в смене',
    'понимание темы: ответ связан с уроком, а не “всё понятно”',
    'эффект на образ / сервис: объяснено, что меняется для клиента',
    'язык GLAME: спокойно, профессионально, без давления',
    'практическое применение: понятно, как повторить это в работе',
  ];
  const activeStepRubric = Object.values(activeStep?.assessment_rubric || {}).map((item) => String(item)).filter(Boolean);
  const activeStepPracticeGate = stepMaterials?.current_step?.id === activeStep?.id ? stepMaterials?.current_step?.practice_gate : null;
  const isStepPracticeBlocked = Boolean(activeStepPracticeGate && !activeStepPracticeGate.can_start_practice);
  const currentStepMaterials = useMemo(() => stepMaterials?.current_step?.materials || [], [stepMaterials?.current_step?.materials]);
  const sessionMaterial = mentorSession?.material_id ? trainingMaterials.find((material) => material.id === mentorSession.material_id) || currentStepMaterials.find((link) => link.material?.id === mentorSession.material_id)?.material : null;
  const firstUnlockedMaterial = sessionMaterial || currentStepMaterials.find((link) => link.material?.id)?.material || trainingMaterials[0] || null;
  const sessionMaterialProgress = mentorSession?.context?.material_progress || null;
  const sessionRequiresMaterialStudy = Boolean(
    mentorSession?.material_id &&
    sessionMaterialProgress &&
    !sessionMaterialProgress.material_completed
  );
  const agentStage = sessionRequiresMaterialStudy ? 'materials' : (mentorSession?.stage || (isStepPracticeBlocked && firstUnlockedMaterial
    ? 'materials'
    : activeStep
      ? 'practice'
      : primaryProgram
        ? 'program'
        : suggestedPrograms.length
          ? 'program_selection'
          : 'waiting'));
  const agentStageLabel = agentStage === 'materials' ? 'Изучение методички' : agentStage === 'practice' ? 'Практическое задание' : agentStage === 'review' ? 'Ожидает проверки' : agentStage === 'program' ? 'Открытие программы' : agentStage === 'program_selection' ? 'Выбор программы' : 'Ожидание назначения';
  const primaryCta = agentStage === 'materials'
    ? 'Изучать урок'
    : agentStage === 'practice'
      ? 'К заданию'
      : agentStage === 'review'
        ? 'Что дальше?'
        : basePrimaryCta;
  const agentActionText = sessionRequiresMaterialStudy
    ? `Сначала изучаем урок «${firstUnlockedMaterial?.title || mentorSession?.context?.material_title || 'текущий урок'}»: просмотрите все слайды и отметьте их как изученные. После этого наставник откроет закрепление и задание.`
    : mentorSession?.message || (agentStage === 'materials'
    ? `Продолжаем методический материал: ${firstUnlockedMaterial?.title || 'текущий урок'}. Сначала изучите слайды, затем откроется практика.`
    : agentStage === 'practice'
      ? `Материал изучен достаточно для практики. Сейчас задача — выполнить этап «${activeStep?.title || primaryTitle}» и отправить ответ руководителю.`
      : agentStage === 'review'
        ? 'Ответ уже отправлен. Обратная связь появится после проверки руководителем.'
        : primaryProgram
        ? `Я вижу вашу активную программу: ${primaryProgram.title}. Открою ближайший шаг и поведу дальше.`
        : suggestedPrograms.length
          ? 'Программа ещё не назначена, но обучение не останавливается: я покажу доступные программы, помогу подписаться на свободную или отправить запрос на допуск руководителю.'
          : 'Пока нет назначенного шага. Наставник предложит базовую подготовку и сообщит, когда руководитель откроет программу.');
const assignedCourseProgram = useMemo(() => {
    if (mentorSession?.program_id) {
      const bySession = programs.find((program) => program.id === mentorSession.program_id && !['locked', 'archived'].includes(program.status));
      if (bySession) return bySession;
    }
    if (currentTaskPrimary?.program_id) {
      const byTask = programs.find((program) => program.id === currentTaskPrimary.program_id && !['locked', 'archived'].includes(program.status));
      if (byTask) return byTask;
    }
    return primaryProgram && !['locked', 'archived', 'access_requested'].includes(primaryProgram.status) ? primaryProgram : null;
  }, [currentTaskPrimary?.program_id, mentorSession?.program_id, primaryProgram, programs]);
  const assignedCourseMaterials = useMemo(() => trainingMaterials.filter((material) => assignedCourseProgram?.code && material.program_code === assignedCourseProgram.code), [assignedCourseProgram?.code, trainingMaterials]);
  const assignedCourseLessonCount = assignedCourseMaterials.length || assignedCourseProgram?.progress?.total_steps || 0;
  const assignedCourseCompletedLessons = Math.min(assignedCourseProgram?.progress?.completed_steps || 0, assignedCourseLessonCount || assignedCourseProgram?.progress?.completed_steps || 0);
  const assignedCoursePercent = assignedCourseProgram?.progress?.percent || 0;
  const assignedCourseCurrentTitle = mentorSession?.context?.material_title || mentorSession?.context?.step_title || currentTaskPrimary?.title || firstUnlockedMaterial?.title || assignedCourseProgram?.next_assignment?.title || 'Ожидает назначения первого урока';
  const visibleProgramAssignments = useMemo(() => {
    return programs.filter((program) => program.next_assignment || !['locked', 'archived'].includes(program.status));
  }, [programs]);
  const noProgramFolderCode = '__no_program__';
  const materialTopics = useMemo(() => Array.from(new Set(trainingMaterials.map((material) => material.topic).filter(Boolean))).sort(), [trainingMaterials]);
  const currentStepMaterialIds = useMemo(() => new Set(currentStepMaterials.map((link) => link.material?.id || link.material_id).filter(Boolean)), [currentStepMaterials]);
  const hasSequencedMaterialGate = currentStepMaterialIds.size > 0;
  const isMaterialOpen = useCallback((material: TrainingMaterial) => {
    if (mentorSession?.material_id && material.id === mentorSession.material_id) return true;
    if (currentStepMaterialIds.has(material.id)) return true;
    const belongsToAssignedProgram = Boolean(assignedCourseProgram?.code && material.program_code === assignedCourseProgram.code);
    // Если в программе нет связанного/последовательного текущего урока, материалы папки считаются самостоятельными:
    // один урок сразу открыт; несколько standalone-уроков можно брать без последовательности.
    if (belongsToAssignedProgram && !hasSequencedMaterialGate) return true;
    return false;
  }, [assignedCourseProgram?.code, currentStepMaterialIds, hasSequencedMaterialGate, mentorSession?.material_id]);
  const materialProgramFolders = useMemo(() => {
    const programFolders = programs.map((program) => {
      const folderMaterials = trainingMaterials.filter((material) => (material.program_code || noProgramFolderCode) === program.code);
      const openCount = folderMaterials.filter((material) => isMaterialOpen(material)).length;
      return {
        code: program.code,
        title: program.title,
        description: program.description,
        status: program.status,
        progress: program.progress,
        isPrimary: program.code === (currentTaskPrimary?.program_code || primaryProgram?.code),
        isLocked: program.status === 'locked',
        totalCount: folderMaterials.length,
        openCount,
      };
    });
    const withoutProgramMaterials = trainingMaterials.filter((material) => !material.program_code);
    const withoutProgramFolder = withoutProgramMaterials.length
      ? [{
          code: noProgramFolderCode,
          title: 'Без программы',
          description: 'Дополнительные материалы без привязки к программе обучения.',
          status: 'available',
          progress: null,
          isPrimary: false,
          isLocked: false,
          totalCount: withoutProgramMaterials.length,
          openCount: withoutProgramMaterials.filter((material) => isMaterialOpen(material)).length,
        }]
      : [];
    return [...programFolders, ...withoutProgramFolder].sort((a, b) => Number(b.isPrimary) - Number(a.isPrimary) || Number(a.isLocked) - Number(b.isLocked) || a.title.localeCompare(b.title));
  }, [currentTaskPrimary?.program_code, isMaterialOpen, noProgramFolderCode, primaryProgram?.code, programs, trainingMaterials]);
  const activeMaterialFolder = useMemo(() => {
    return materialProgramFolders.find((folder) => folder.code === selectedMaterialProgramCode) || materialProgramFolders.find((folder) => folder.isPrimary) || materialProgramFolders[0] || null;
  }, [materialProgramFolders, selectedMaterialProgramCode]);
  const visibleTrainingMaterials = useMemo(() => {
    const query = materialSearch.trim().toLowerCase();
    const activeFolderCode = activeMaterialFolder?.code;
    return trainingMaterials.filter((material) => {
      const materialProgramCode = material.program_code || noProgramFolderCode;
      if (activeFolderCode && materialProgramCode !== activeFolderCode) return false;
      if (materialTopicFilter && material.topic !== materialTopicFilter) return false;
      if (!query) return true;
      return [material.title, material.topic, material.category, material.description || '', material.markdown_content, ...(material.tags || [])].join(' ').toLowerCase().includes(query);
    });
  }, [activeMaterialFolder?.code, materialSearch, materialTopicFilter, trainingMaterials]);
  const materialCards = useMemo(() => {
    return visibleTrainingMaterials.map((material) => {
      const isCurrent = Boolean(mentorSession?.material_id && material.id === mentorSession.material_id);
      const isUnlocked = isMaterialOpen(material);
      return {
        material,
        isCurrent,
        isUnlocked,
        accessLabel: isUnlocked ? (isCurrent ? 'текущий материал' : 'открыт') : 'закрыт',
        accessHint: isUnlocked
          ? 'Урок открыт: изучите слайды и отметьте прогресс. Если урок самостоятельный, его можно проходить без ожидания предыдущих тем.'
          : 'Урок закрыт последовательностью: он откроется после прохождения нужного урока/этапа.',
      };
    }).sort((a, b) => Number(b.isCurrent) - Number(a.isCurrent) || Number(b.isUnlocked) - Number(a.isUnlocked) || (a.material.order_index || 100) - (b.material.order_index || 100) || a.material.title.localeCompare(b.material.title));
  }, [isMaterialOpen, mentorSession?.material_id, visibleTrainingMaterials]);


  useEffect(() => {
    if (loading || autoRouteDoneRef.current) return;
    if (agentStage === 'materials' && firstUnlockedMaterial?.id) {
      autoRouteDoneRef.current = true;
      openStepMaterialSlides(firstUnlockedMaterial.id);
      window.setTimeout(() => mentorControlRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120);
      return;
    }
    const programToOpen = assignedCourseProgram || primaryProgram;
    if ((agentStage === 'program' || agentStage === 'practice') && programToOpen && !activeStep) {
      autoRouteDoneRef.current = true;
      openProgram(programToOpen, false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, agentStage, firstUnlockedMaterial?.id, assignedCourseProgram?.id, primaryProgram?.id, activeStep?.id, mentorSession?.next_action]);


  const resolveMediaUrl = (value?: string | null) => {
    if (!value) return null;
    if (/^(https?:|data:|blob:)/.test(value)) return value;
    return value.startsWith('/') ? value : `/${value}`;
  };

  const renderSlideBody = (body?: string | null) => {
    if (!body) return null;
    return (
      <div className="mt-5 space-y-3 text-base leading-7 text-slate-700">
        {body.split('\n').map((line, index) => {
          const trimmed = line.trim();
          if (!trimmed) return <div key={`space-${index}`} className="h-1" />;
          const isBullet = /^[-•]\s+/.test(trimmed);
          const isNumbered = /^\d+[).]\s+/.test(trimmed);
          const isSection = /:$/.test(trimmed) && trimmed.length < 90;
          if (isBullet || isNumbered) {
            return (
              <div key={`${trimmed}-${index}`} className="flex gap-3 rounded-xl bg-slate-50 px-4 py-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                <span>{trimmed.replace(/^[-•]\s+/, '')}</span>
              </div>
            );
          }
          if (isSection) return <h4 key={`${trimmed}-${index}`} className="pt-2 text-lg font-bold text-slate-950">{trimmed}</h4>;
          return <p key={`${trimmed}-${index}`} className="text-slate-700">{trimmed}</p>;
        })}
      </div>
    );
  };

  const renderSlideViewer = (materialId?: string | null) => {
    if (!materialId || activeSlideMaterialId !== materialId) return null;
    const activeSlide = activeMaterialSlides[activeSlideIndex] || activeMaterialSlides[0];
    const completed = activeMaterialSlidesSummary?.completed_slides || 0;
    const total = activeMaterialSlidesSummary?.slides || activeMaterialSlides.length;
    const imageUrl = resolveMediaUrl(activeSlide?.image_url);
    if (!activeMaterialSlides.length) {
      return <p className="mt-3 rounded-xl bg-slate-50 p-3 text-sm text-slate-500">Для материала пока нет опубликованных слайдов. Сообщите руководителю: нужен publish слайдов.</p>;
    }
    return (
      <div className="mt-4 overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-lg">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 bg-gradient-to-r from-slate-950 via-slate-900 to-slate-800 p-5 text-white">
          <div>
            <div className="text-xs font-bold uppercase tracking-[0.18em] text-amber-300">Методический урок GLAME</div>
            <div className="mt-1 text-lg font-bold">{completed}/{total} слайдов · {activeMaterialSlidesSummary?.progress_percent || 0}%</div>
          </div>
          {activeMaterialSlidesSummary?.material_completed ? <span className="rounded-full bg-emerald-300 px-4 py-2 text-sm font-bold text-slate-950">Материал изучен</span> : <span className="rounded-full bg-amber-300 px-4 py-2 text-sm font-bold text-slate-950">Изучите все слайды</span>}
        </div>
        <div className="grid gap-0 xl:grid-cols-[300px_1fr]">
          <div className="max-h-[860px] space-y-2 overflow-auto border-r border-slate-100 bg-slate-50 p-4">
            {activeMaterialSlides.map((slide, index) => (
              <button key={slide.id} onClick={() => setActiveSlideIndex(index)} className={`w-full rounded-2xl p-3 text-left text-sm transition ${index === activeSlideIndex ? 'bg-slate-950 text-white shadow-md' : 'bg-white text-slate-700 hover:bg-slate-100'}`}>
                <div className="flex items-center justify-between gap-2 text-xs font-bold opacity-70">
                  <span>Слайд {index + 1}</span>
                  {slide.progress?.completed ? <span className="text-emerald-400">✓</span> : null}
                </div>
                <div className="mt-1 font-semibold leading-5">{slide.title}</div>
              </button>
            ))}
          </div>
          <div className="p-6 lg:p-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-4xl">
                <div className="text-sm font-black uppercase tracking-[0.18em] text-amber-600">Слайд {activeSlideIndex + 1} из {activeMaterialSlides.length}</div>
                <h3 className="mt-3 text-3xl font-black leading-tight text-slate-950 md:text-4xl">{activeSlide?.title}</h3>
              </div>
              {activeSlide?.progress?.completed ? <span className="rounded-full bg-emerald-100 px-4 py-2 text-sm font-bold text-emerald-800">изучен</span> : null}
            </div>
            {imageUrl ? <div aria-label={activeSlide.title} className="mt-6 min-h-[360px] w-full rounded-[1.75rem] border border-slate-100 bg-slate-100 bg-cover bg-center shadow-inner md:min-h-[460px]" style={{ backgroundImage: `url(${imageUrl})` }} /> : null}
            {renderSlideBody(activeSlide?.body)}
            {activeSlide?.quiz_question ? <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-base leading-7 text-amber-950"><b>Самопроверка:</b> {activeSlide.quiz_question}</div> : null}
            <div className="mt-7 flex flex-wrap gap-3">
              <button onClick={() => setActiveSlideIndex((index) => Math.max(0, index - 1))} disabled={activeSlideIndex === 0} className="rounded-xl border border-slate-200 px-5 py-3 text-sm font-bold text-slate-700 disabled:text-slate-300">Назад</button>
              <button onClick={() => setActiveSlideIndex((index) => Math.min(activeMaterialSlides.length - 1, index + 1))} disabled={activeSlideIndex >= activeMaterialSlides.length - 1} className="rounded-xl border border-slate-200 px-5 py-3 text-sm font-bold text-slate-700 disabled:text-slate-300">Дальше</button>
              {!activeSlide?.progress?.completed ? (
                <button onClick={() => activeSlide && markSlideViewed(materialId, activeSlide.id)} disabled={!activeSlide || markingSlideId === activeSlide.id} className="rounded-xl bg-slate-950 px-6 py-3 text-sm font-bold text-white disabled:bg-slate-300">{markingSlideId === activeSlide?.id ? 'Сохраняю…' : 'Отметить слайд изученным'}</button>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <header className="rounded-3xl bg-white p-6 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-400">GLAME AI-наставник</p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold text-slate-900">Персональное обучение продавца</h1>
            <p className="mt-3 max-w-3xl text-slate-600">
              При входе на страницу наставник сам определяет следующий шаг: продолжить методичку, перейти к заданию или отправить ответ на проверку. Лишняя аналитика вынесена ниже и не мешает обучению.
            </p>
          </div>
          <div className="rounded-2xl bg-slate-900 px-5 py-4 text-white">
            <div className="text-xs uppercase tracking-[0.2em] text-slate-300">Текущий статус</div>
            <div className="mt-1 text-xl font-semibold">{agentStageLabel}</div>
          </div>
        </div>
      </header>

      {error && <div className="rounded-2xl bg-red-50 p-4 text-red-700">{error}</div>}
      {message && <div className="rounded-2xl bg-emerald-50 p-4 text-emerald-700">{message}</div>}

      <section className="overflow-hidden rounded-[2rem] border border-amber-100 bg-gradient-to-br from-white via-amber-50 to-slate-50 p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-3xl">
            <p className="text-xs font-black uppercase tracking-[0.22em] text-amber-600">Моя программа обучения</p>
            <h2 className="mt-2 text-3xl font-bold text-slate-950">{assignedCourseProgram?.title || 'Программа обучения пока не назначена'}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              {assignedCourseProgram?.description || (assignedCourseProgram ? 'Это ваш текущий курс GLAME: здесь видны уроки, прогресс и следующий шаг.' : suggestedPrograms.length ? 'Программа ещё не назначена. AI-наставник ниже покажет доступные программы: можно подписаться на свободную или отправить запрос на допуск.' : 'Руководитель назначит программу, после этого здесь появится полный маршрут обучения.')}
            </p>
          </div>
          <div className="rounded-2xl bg-slate-950 px-5 py-4 text-white shadow-sm">
            <div className="text-xs uppercase tracking-[0.18em] text-slate-300">Статус курса</div>
            <div className="mt-1 text-xl font-bold">{assignedCourseProgram ? statusLabels[assignedCourseProgram.status] || assignedCourseProgram.status : 'Не назначен'}</div>
          </div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-4">
          <div className="rounded-2xl bg-white p-4 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Уроков в курсе</div>
            <div className="mt-2 text-3xl font-bold text-slate-950">{assignedCourseLessonCount}</div>
            <div className="mt-1 text-xs text-slate-500">{assignedCourseMaterials.length ? 'по опубликованным материалам' : 'по структуре программы'}</div>
          </div>
          <div className="rounded-2xl bg-white p-4 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Пройдено</div>
            <div className="mt-2 text-3xl font-bold text-slate-950">{assignedCourseCompletedLessons}/{assignedCourseLessonCount || assignedCourseProgram?.progress?.total_steps || 0}</div>
            <div className="mt-1 text-xs text-slate-500">уроки/этапы, подтвержденные наставником</div>
          </div>
          <div className="rounded-2xl bg-white p-4 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Прогресс</div>
            <div className="mt-2 text-3xl font-bold text-slate-950">{assignedCoursePercent}%</div>
            <div className="mt-2 h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-amber-400" style={{ width: `${Math.min(100, Math.max(0, assignedCoursePercent))}%` }} /></div>
          </div>
          <div className="rounded-2xl bg-white p-4 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Проверка</div>
            <div className="mt-2 text-3xl font-bold text-slate-950">{assignedCourseProgram?.progress?.pending_reviews || 0}</div>
            <div className="mt-1 text-xs text-slate-500">ответов ожидает руководителя</div>
          </div>
        </div>
        <div className="mt-4 rounded-2xl border border-amber-100 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Текущий урок / следующий шаг</div>
              <div className="mt-1 text-lg font-bold text-slate-950">{assignedCourseProgram ? assignedCourseCurrentTitle : suggestedPrograms.length ? 'Выбор доступной программы' : assignedCourseCurrentTitle}</div>
              <div className="mt-1 text-sm text-slate-600">{assignedCourseProgram ? 'Наставник ниже открывает именно этот шаг: методичку, практику или ожидание проверки.' : 'AI-наставник ниже предложит, что можно начать сейчас, и поможет запросить допуск к закрытым программам.'}</div>
            </div>
            {assignedCourseProgram ? <button onClick={startPrimaryLearning} className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-bold text-white">{primaryCta}</button> : null}
          </div>
        </div>
      </section>

      {primaryProgram || mentorSession || suggestedPrograms.length ? (
        <section ref={mentorControlRef} className="overflow-hidden rounded-3xl border border-slate-200 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 p-6 text-white shadow-lg">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div className="max-w-4xl">
              <p className="text-sm font-black uppercase tracking-[0.22em] text-amber-300">Персональный AI-наставник</p>
              <h2 className="mt-2 text-3xl font-semibold">Я проверил ваш статус и продолжаю обучение</h2>
              <p className="mt-3 max-w-3xl text-base leading-7 text-slate-200">{agentActionText}</p>
            </div>
            <div className="rounded-2xl bg-white/10 px-5 py-4 shadow-md">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-300">Сейчас этап</div>
              <div className="mt-1 text-2xl font-semibold">{agentStageLabel}</div>
            </div>
          </div>
          <div className="mt-6 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-2xl bg-white p-5 text-slate-900 shadow-sm">
              <div className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">Следующий шаг</div>
              <h3 className="mt-2 text-xl font-bold">{agentStage === 'program_selection' ? 'Выберите программу для старта' : agentStage === 'materials' ? firstUnlockedMaterial?.title : activeStep?.title || mentorSession?.context?.step_title || mentorSession?.context?.task_title || primaryTitle}</h3>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                {agentStage === 'materials'
                  ? 'Откройте слайды ниже и отмечайте каждый как изученный. После обязательных слайдов наставник переведет вас к практике.'
                  : agentStage === 'practice'
                    ? taskMicroPractice
                    : agentStage === 'review'
                      ? 'Ответ уже на проверке. Наставник сохранит контекст и продолжит маршрут после решения руководителя.'
                      : agentStage === 'program_selection'
                        ? 'Можно подписаться на свободную программу или отправить руководителю запрос на допуск. AI-наставник не оставит страницу пустой — он предложит доступный маршрут обучения.'
                        : currentLearningTask?.seller_guidance?.recommended_action || 'Открываем ближайший шаг программы и продолжаем без лишней навигации.'}
              </p>
              {agentStage === 'program_selection' ? (
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {suggestedPrograms.map((program) => (
                    <article key={program.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">{program.access_mode === 'free' ? 'свободная программа' : program.status === 'access_requested' ? 'запрос ожидает' : 'нужен допуск'}</div>
                          <h4 className="mt-1 font-bold text-slate-950">{program.title}</h4>
                        </div>
                        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600">{program.progress?.total_steps || 0} этапов</span>
                      </div>
                      {program.description ? <p className="mt-2 text-sm leading-6 text-slate-600">{program.description}</p> : null}
                      <button
                        onClick={() => handleProgramAccessAction(program)}
                        disabled={program.status === 'access_requested'}
                        className="mt-3 rounded-xl bg-slate-950 px-4 py-2 text-sm font-bold text-white disabled:bg-slate-300"
                      >
                        {program.status === 'access_requested' ? 'Запрос отправлен' : program.access_mode === 'free' ? 'Подписаться' : 'Запросить допуск'}
                      </button>
                    </article>
                  ))}
                </div>
              ) : null}
              <div className="mt-4 flex flex-wrap gap-3">
                {agentStage === 'materials' && firstUnlockedMaterial?.id ? (
                  <button onClick={() => openStepMaterialSlides(firstUnlockedMaterial.id)} className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-bold text-white">Продолжить методичку</button>
                ) : null}
                <button
                  onClick={() => scrollToMentorChat(mentorSession?.mentor_prompt || currentLearningTask?.mentor_prompt || 'Помоги выполнить текущее учебное задание по стандартам GLAME')}
                  className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-3 text-sm font-bold text-amber-900"
                >
                  Задать вопрос наставнику
                </button>
              </div>
            </div>
            <div className="rounded-2xl bg-white/10 p-5 text-sm text-slate-100">
              <div className="font-bold text-white">Контроль наставника</div>
              <ul className="mt-3 space-y-2 leading-6">
                <li>• проверяет, изучены ли обязательные методички;</li>
                <li>• если пора практиковаться — сразу ведет к заданию;</li>
                <li>• помогает сформулировать ответ в языке GLAME;</li>
                <li>• финальную обратную связь подтверждает руководитель.</li>
              </ul>
              <div className="mt-4 rounded-xl bg-white/10 p-3">
                Прогресс: <b>{primaryProgram?.progress?.percent || 0}%</b> · {primaryProgram?.progress?.completed_steps || 0}/{primaryProgram?.progress?.total_steps || 0} этапов
              </div>
            </div>
          </div>
          {agentStage === 'practice' && (activeStep || sessionPracticeAssignment) ? (
            <div ref={practiceAssignmentRef} className="mt-5 rounded-2xl bg-white p-5 text-slate-900 shadow-sm">
              <div className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">Задание прямо сейчас</div>
              <h3 className="mt-2 text-2xl font-bold">{sessionPracticeAssignment?.title || activeStep?.title}</h3>
              {sessionPracticeAssignment?.task ? (
                <p className="mt-3 whitespace-pre-wrap text-base leading-8 text-slate-800 md:text-lg">{sessionPracticeAssignment.task}</p>
              ) : activeStep?.practice_text ? (
                <p className="mt-3 whitespace-pre-wrap text-base leading-8 text-slate-800 md:text-lg">{activeStep.practice_text}</p>
              ) : null}
              {sessionPracticeAssignment?.try_phrase ? (
                <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-5 text-base leading-8 text-amber-950 md:text-lg">
                  <b>Фраза, которую нужно попробовать:</b> {sessionPracticeAssignment.try_phrase}
                </div>
              ) : null}
              {sessionPracticeAssignment?.good_answer_example ? (
                <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-5 text-base leading-8 text-emerald-950 md:text-lg">
                  <b>Как выглядит хороший ответ:</b> {sessionPracticeAssignment.good_answer_example.replace(/^Хороший ответ:\s*/i, '')}
                </div>
              ) : null}
              <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-base leading-8 text-slate-800 md:text-lg">
                <b>Шаблон ответа:</b>
                <div className="mt-2 whitespace-pre-wrap">{sessionPracticeAssignment?.answer_template || activeStep?.answer_template || taskAnswerTemplate}</div>
              </div>
              {(sessionPracticeAssignment?.assessment_criteria?.length || activeStepRubric.length || taskAssessmentCriteria.length) ? (
                <div className="mt-4 rounded-xl bg-slate-50 p-5 text-base leading-8 text-slate-800 md:text-lg">
                  <b>Критерии оценки:</b>
                  <ul className="mt-2 space-y-1">
                    {(sessionPracticeAssignment?.assessment_criteria || activeStepRubric || taskAssessmentCriteria).map((criterion) => <li key={criterion}>• {criterion}</li>)}
                  </ul>
                </div>
              ) : null}
              <textarea
                className="mt-4 h-28 w-full rounded-xl border p-3"
                placeholder="Транскрипт устного ответа появится здесь. Можно поправить текст после надиктовки."
                value={stepAnswer}
                onChange={(event) => setStepAnswer(event.target.value)}
                disabled={isStepPracticeBlocked}
              />
              {renderVoiceAnswerControls('step', isStepPracticeBlocked)}
              <textarea
                className="mt-3 h-20 w-full rounded-xl border p-3"
                placeholder="Короткий вечерний вывод после смены"
                value={stepEveningReview}
                onChange={(event) => setStepEveningReview(event.target.value)}
                disabled={isStepPracticeBlocked}
              />
              <button onClick={submitStepAnswer} disabled={!activeStep || !hasAnswerForSubmit(stepAnswer) || isStepPracticeBlocked || activeStep.status === 'locked' || activeStep.status === 'submitted'} className="mt-3 rounded-xl bg-slate-950 px-5 py-3 font-bold text-white disabled:bg-slate-300">
                Отправить наставнику и руководителю
              </button>
              <p className="mt-2 text-sm text-slate-500">{sessionPracticeAssignment?.review_rule || 'AI сделает предварительный разбор, но продавцу итоговую обратную связь отправит руководитель.'}</p>
            </div>
          ) : null}
          {agentStage === 'materials' && firstUnlockedMaterial?.id ? renderSlideViewer(firstUnlockedMaterial.id) : null}
        </section>
      ) : null}

      {dailyFocus ? (
        <section className="overflow-hidden rounded-3xl bg-slate-900 p-6 text-white shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-300">Фокус на ближайшую смену</p>
              <h2 className="mt-2 text-2xl font-semibold">Что сделать сегодня</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-200">{dailyFocus.recommended_action}</p>
            </div>
            <span className={`rounded-full px-4 py-2 text-sm font-semibold ${dailyFocus.priority === 'high' ? 'bg-amber-300 text-slate-950' : 'bg-white/10 text-white'}`}>
              {dailyFocus.priority === 'high' ? 'Важный фокус' : 'Рабочий фокус'}
            </span>
          </div>
          <div className="mt-5 grid gap-3 md:grid-cols-4">
            <div className="rounded-2xl bg-white/10 p-4">
              <div className="text-sm text-slate-300">Режим</div>
              <div className="mt-1 text-xl font-semibold">{dailyFocus.schedule_context?.title || 'Учебный фокус'}</div>
              <div className="mt-2 text-xs text-slate-300">
                {dailyFocus.schedule_context?.nearest_shift
                  ? `${dailyFocus.schedule_context.nearest_shift.date || ''} · ${dailyFocus.schedule_context.nearest_shift.start_time || '—'}–${dailyFocus.schedule_context.nearest_shift.end_time || '—'}`
                  : 'Сегодня без рабочей смены'}
              </div>
            </div>
            <div className="rounded-2xl bg-white/10 p-4">
              <div className="text-sm text-slate-300">KPI-фокус</div>
              <div className="mt-1 text-xl font-semibold">{dailyFocus.today_focus?.metric || 'Темп и сервис'}</div>
              <div className="mt-2 text-xs text-slate-300">План: {dailyFocus.today_focus?.kpi_completion_percent ?? '—'}%</div>
            </div>
            <div className="rounded-2xl bg-white/10 p-4">
              <div className="text-sm text-slate-300">Учебная компетенция</div>
              <div className="mt-1 text-xl font-semibold">{dailyFocus.today_focus?.training_competency || 'GLAME-фраза'}</div>
              <div className="mt-2 text-xs text-slate-300">Прогресс обучения: {dailyFocus.progress_percent || 0}%</div>
            </div>
            <div className="rounded-2xl bg-white/10 p-4">
              <div className="text-sm text-slate-300">Следующий шаг</div>
              <div className="mt-1 text-xl font-semibold">{dailyFocus.training_step?.title || 'Открыть программу'}</div>
              <div className="mt-2 text-xs text-slate-300">{dailyFocus.training_step?.program_title || 'Программа GLAME'}</div>
            </div>
          </div>
          <div className="mt-4 rounded-2xl bg-white p-4 text-slate-900">
            <div className="font-semibold">Мини-тренировка перед сменой</div>
            {dailyFocus.schedule_context?.nearest_shift?.store_name ? (
              <div className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">{dailyFocus.schedule_context.nearest_shift.store_name}</div>
            ) : null}
            <p className="mt-1 text-sm text-slate-600">{dailyFocus.micro_practice}</p>
            {dailyFocus.mentor_prompt ? (
              <button onClick={() => askMentor(dailyFocus.mentor_prompt)} className="mt-3 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">Спросить AI-наставника по этому фокусу</button>
            ) : null}
          </div>
          <p className="mt-3 text-xs text-slate-300">{dailyFocus.tone_guardrails}</p>
        </section>
      ) : null}

      <section className="rounded-3xl bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">Рефлексия после смены</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">Что получилось и где нужна помощь</h2>
            <p className="mt-2 text-sm text-slate-600">Короткая форма помогает AI и руководителю увидеть, какой сценарий разобрать. Это не публичная оценка и не штраф.</p>
          </div>
          <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">История: {shiftReflections.length}</div>
        </div>
        <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_360px]">
          <div className="space-y-3">
            <textarea className="h-20 w-full rounded-xl border p-3" placeholder="Что получилось сегодня? Например: мягко начала диалог, показала комплект..." value={reflectionForm.worked_well} onChange={(e) => setReflectionForm((prev) => ({ ...prev, worked_well: e.target.value }))} />
            <textarea className="h-20 w-full rounded-xl border p-3" placeholder="Какой клиентский сценарий был сложным?" value={reflectionForm.difficult_scenario} onChange={(e) => setReflectionForm((prev) => ({ ...prev, difficult_scenario: e.target.value }))} />
            <textarea className="h-20 w-full rounded-xl border p-3" placeholder="Какой GLAME-аргумент или фраза сработали?" value={reflectionForm.glame_argument} onChange={(e) => setReflectionForm((prev) => ({ ...prev, glame_argument: e.target.value }))} />
            <textarea className="h-20 w-full rounded-xl border p-3" placeholder="Где нужна помощь AI или руководителя?" value={reflectionForm.needs_help} onChange={(e) => setReflectionForm((prev) => ({ ...prev, needs_help: e.target.value }))} />
            <button onClick={submitShiftReflection} disabled={reflectionLoading} className="rounded-xl bg-slate-900 px-5 py-3 font-semibold text-white disabled:bg-slate-300">{reflectionLoading ? 'Сохраняю…' : 'Сохранить рефлексию'}</button>
          </div>
          <div className="space-y-3 rounded-2xl bg-slate-50 p-4">
            <div className="font-semibold text-slate-900">Последние рефлексии</div>
            {shiftReflections.length === 0 ? <p className="text-sm text-slate-500">Пока нет записей после смены.</p> : null}
            {shiftReflections.slice(0, 3).map((item) => (
              <article key={item.id} className="rounded-2xl bg-white p-3 text-sm shadow-sm">
                <div className="font-semibold text-slate-900">{item.shift_date || 'Смена'} {item.store_name ? `· ${item.store_name}` : ''}</div>
                <div className="mt-1 text-xs text-slate-500">{item.status} · AI {item.ai_score ?? '—'}/10</div>
                {item.seller_feedback ? <p className="mt-2 text-slate-700">{item.seller_feedback}</p> : null}
                {item.manager_feedback ? <p className="mt-2 rounded-xl bg-emerald-50 p-2 text-emerald-800">Руководитель: {item.manager_feedback}</p> : null}
              </article>
            ))}
          </div>
        </div>
      </section>

      {coachingActions.length ? (
        <section className="rounded-3xl bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">Coaching после смены</p>
              <h2 className="mt-2 text-2xl font-semibold text-slate-900">Мои следующие шаги с руководителем</h2>
              <p className="mt-2 text-sm text-slate-600">Здесь показываются только поддерживающие действия: что потренировать и какой разбор запланирован. Внутренние risk-сигналы не отображаются.</p>
            </div>
            <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">Активно: {coachingActions.length}</div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {coachingActions.slice(0, 6).map((action) => (
              <article key={action.id} className="rounded-2xl border border-slate-200 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-900">{action.coaching_topic}</div>
                    <div className="mt-1 text-sm text-slate-500">{action.status} {action.planned_for ? `· ${action.planned_for}` : ''} {action.store_name ? `· ${action.store_name}` : ''}</div>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-500">{action.kpi_metric || action.competency || 'фокус'}</span>
                </div>
                {action.seller_next_step ? <p className="mt-3 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900">{action.seller_next_step}</p> : null}
                {action.seller_visible_feedback ? <p className="mt-2 rounded-xl bg-blue-50 p-3 text-sm text-blue-800">Комментарий: {action.seller_visible_feedback}</p> : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {trainingMaterials.length ? (
        <section className="rounded-3xl bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">Материалы наставника</p>
              <h2 className="mt-2 text-2xl font-semibold text-slate-900">Учебные материалы GLAME</h2>
              <p className="mt-2 text-sm text-slate-600">Материалы разбиты по программам обучения как папки. Внутри видны открытые уроки и закрытые материалы, которые откроются по мере прохождения этапов.</p>
            </div>
            <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">Папок: {materialProgramFolders.length} · материалов: {trainingMaterials.length}</div>
          </div>
          {stepMaterials?.current_step ? (
            <div className="mt-5 rounded-2xl border border-indigo-100 bg-indigo-50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-500">Текущий этап</div>
                  <div className="mt-1 font-semibold text-slate-900">{stepMaterials.current_step.title || 'Текущий урок'}</div>
                  <p className="mt-1 text-sm text-slate-600">
                    {stepMaterials.summary?.unlocked_materials
                      ? 'Открытые материалы этого этапа доступны в папке активной программы. Закрытые уроки останутся видимыми, но откроются после прохождения нужных шагов.'
                      : 'Для этого этапа пока нет опубликованных материалов — наставник предложит доступный урок из папки программы или дождется назначения.'}
                  </p>
                </div>
                <span className="rounded-full bg-white px-3 py-2 text-sm text-slate-600">Открыто сейчас: {stepMaterials.summary?.unlocked_materials || 0}</span>
              </div>
            </div>
          ) : null}

          <div className="mt-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-lg font-bold text-slate-950">Папки программ обучения</h3>
                <p className="mt-1 text-sm text-slate-600">Выберите программу: внутри — материалы этой программы, с отметками “открыт” и “закрыт”.</p>
              </div>
              {activeMaterialFolder ? <span className="rounded-full bg-slate-100 px-3 py-2 text-sm text-slate-600">Открыта папка: {activeMaterialFolder.title}</span> : null}
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {materialProgramFolders.map((folder) => {
                const isSelected = activeMaterialFolder?.code === folder.code;
                return (
                  <button
                    key={folder.code}
                    onClick={() => {
                      setSelectedMaterialProgramCode(folder.code);
                      setMaterialTopicFilter('');
                      setMaterialSearch('');
                    }}
                    className={`rounded-2xl border p-4 text-left transition ${isSelected ? 'border-slate-950 bg-slate-950 text-white shadow-md' : folder.isLocked ? 'border-dashed border-slate-200 bg-slate-50 text-slate-500 hover:bg-slate-100' : 'border-slate-200 bg-white text-slate-900 hover:border-slate-300 hover:bg-slate-50'}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className={`text-xs font-black uppercase tracking-[0.16em] ${isSelected ? 'text-amber-300' : 'text-slate-400'}`}>📁 программа</div>
                        <div className="mt-2 text-base font-bold">{folder.title}</div>
                      </div>
                      {folder.isPrimary ? <span className={`rounded-full px-2 py-1 text-xs font-bold ${isSelected ? 'bg-amber-300 text-slate-950' : 'bg-amber-50 text-amber-900'}`}>активная</span> : null}
                    </div>
                    <p className={`mt-2 line-clamp-2 text-sm ${isSelected ? 'text-slate-200' : 'text-slate-600'}`}>{folder.description || 'Учебная папка программы GLAME.'}</p>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs font-semibold">
                      <span className={`rounded-full px-2 py-1 ${isSelected ? 'bg-white/10 text-white' : 'bg-emerald-50 text-emerald-800'}`}>открыто: {folder.openCount}</span>
                      <span className={`rounded-full px-2 py-1 ${isSelected ? 'bg-white/10 text-white' : 'bg-slate-100 text-slate-600'}`}>закрыто: {Math.max(folder.totalCount - folder.openCount, 0)}</span>
                      <span className={`rounded-full px-2 py-1 ${isSelected ? 'bg-white/10 text-white' : 'bg-slate-100 text-slate-600'}`}>всего: {folder.totalCount}</span>
                    </div>
                    {folder.progress ? <div className={`mt-3 text-xs ${isSelected ? 'text-slate-300' : 'text-slate-500'}`}>Прогресс программы: {folder.progress.percent || 0}% · {folder.progress.completed_steps || 0}/{folder.progress.total_steps || 0}</div> : null}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-5 rounded-[2rem] border border-slate-200 bg-slate-50/70 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Материалы в папке</div>
                <h3 className="mt-1 text-xl font-bold text-slate-950">{activeMaterialFolder?.title || 'Программа обучения'}</h3>
                <p className="mt-1 text-sm text-slate-600">Открытые материалы можно изучать сейчас. Закрытые показаны заранее, но кнопка станет активной после нужного урока.</p>
              </div>
              <div className="rounded-2xl bg-white px-4 py-3 text-sm text-slate-600">Найдено: {materialCards.length}/{activeMaterialFolder?.totalCount || 0}</div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-[1fr_220px]">
              <input className="rounded-xl border bg-white p-3" placeholder="Поиск в папке: сервис, камни, первый контакт…" value={materialSearch} onChange={(e) => setMaterialSearch(e.target.value)} />
              <select className="rounded-xl border bg-white p-3" value={materialTopicFilter} onChange={(e) => setMaterialTopicFilter(e.target.value)}>
                <option value="">Все темы</option>
                {materialTopics.map((topic) => <option key={topic} value={topic}>{topic}</option>)}
              </select>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {materialCards.map(({ material, isCurrent, isUnlocked, accessLabel, accessHint }) => {
                const isOpen = activeSlideMaterialId === material.id;
                return (
                  <article key={material.id} className={`rounded-2xl border p-4 ${isOpen ? 'border-slate-900 bg-white md:col-span-2 xl:col-span-3' : isUnlocked ? 'border-slate-200 bg-white' : 'border-dashed border-slate-200 bg-white/60 opacity-80'}`}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">{isUnlocked ? 'открытый урок' : 'закрытый урок'} · {material.topic}</div>
                        <h3 className="mt-2 font-semibold text-slate-900">{material.title}</h3>
                      </div>
                      <span className={`rounded-full px-3 py-1 text-xs font-semibold ${isUnlocked ? 'bg-emerald-50 text-emerald-800' : 'bg-slate-200 text-slate-600'}`}>{accessLabel}</span>
                    </div>
                    {material.description ? <p className="mt-2 text-sm leading-6 text-slate-600">{material.description}</p> : null}
                    <div className={`mt-3 rounded-xl p-3 text-sm ${isUnlocked ? 'bg-slate-50 text-slate-600' : 'bg-slate-100 text-slate-500'}`}>
                      {accessHint}
                    </div>
                    {isUnlocked ? (
                      <button onClick={() => openStepMaterialSlides(material.id)} className="mt-3 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">{isOpen ? 'Обновить слайды' : isCurrent ? 'Продолжить текущий материал' : 'Изучать материал'}</button>
                    ) : (
                      <button disabled className="mt-3 rounded-xl bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-500">Откроется после прохождения уроков</button>
                    )}
                    {isOpen && isUnlocked ? renderSlideViewer(material.id) : null}
                    {material.tags?.length ? <div className="mt-3 flex flex-wrap gap-1">{material.tags.map((tag) => <span key={tag} className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-500">{tag}</span>)}</div> : null}
                  </article>
                );
              })}
              {!materialCards.length ? <div className="rounded-2xl bg-white p-4 text-sm text-slate-500">В этой папке материалы по выбранному фильтру не найдены.</div> : null}
            </div>
          </div>
        </section>
      ) : null}



      <section className="rounded-3xl bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">Аттестация</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">Мой допуск и сертификация</h2>
            <p className="mt-2 text-sm text-slate-600">Аттестация открывается после закрытия базовых компетенций. Ответ проверяется AI и руководителем.</p>
          </div>
          <button onClick={startAttestation} disabled={!competencySummary?.attestation_ready} className="rounded-xl bg-slate-900 px-5 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300">Открыть аттестацию</button>
        </div>
        <div className="mt-4 space-y-3">
          {attestations.length === 0 ? <p className="text-sm text-slate-500">Активных аттестаций пока нет.</p> : null}
          {attestations.map((attestation) => (
            <article key={attestation.id} className="rounded-2xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-semibold text-slate-900">{attestation.task_payload?.title || 'Аттестация GLAME'}</div>
                  <div className="text-sm text-slate-500">{attestation.attestation_type} · {attestation.status} · уровень: {attestation.certified_level || attestation.recommended_level || '—'}</div>
                </div>
                {attestation.ai_score != null ? <span className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-600">AI {attestation.ai_score}/10</span> : null}
              </div>
              {attestation.status === 'draft' ? (
                <div className="mt-3 space-y-3">
                  <ul className="list-disc pl-5 text-sm text-slate-600">{(attestation.task_payload?.cases || []).map((item) => <li key={item}>{item}</li>)}</ul>
                  <textarea className="h-28 w-full rounded-xl border p-3" placeholder="Ответ на аттестационный кейс" value={attestationAnswer} onChange={(e) => setAttestationAnswer(e.target.value)} />
                  <button onClick={() => submitAttestation(attestation)} disabled={!attestationAnswer.trim()} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:bg-slate-300">Отправить аттестацию</button>
                </div>
              ) : null}
              {attestation.manager_feedback ? <p className="mt-3 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900">Комментарий: {attestation.manager_feedback}</p> : null}
            </article>
          ))}
        </div>
      </section>

      <section ref={mentorChatRef} className="rounded-3xl bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">AI-наставник</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">Учебный чат по GLAME-стандартам</h2>
            <p className="mt-2 text-sm text-slate-600">Наставник помогает усилить формулировку, но не ставит финальную оценку и не заменяет проверку руководителя.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {['Помоги сформулировать GLAME-фразу', 'Проверь, хватает ли конкретики', 'Как объяснить эффект украшения на образ?'].map((prompt) => (
              <button key={prompt} onClick={() => askMentor(prompt)} className="rounded-full bg-slate-100 px-3 py-2 text-sm text-slate-700 hover:bg-slate-200">{prompt}</button>
            ))}
          </div>
        </div>
        <div className="mt-4">
          <textarea
            className="h-28 w-full rounded-xl border p-3"
            placeholder="Задайте вопрос наставнику: например, как сделать ответ точнее, мягче и в стиле GLAME"
            value={mentorQuestion}
            onChange={(e) => setMentorQuestion(e.target.value)}
          />
          <button onClick={() => askMentor()} disabled={!mentorQuestion.trim() || mentorLoading} className="mt-3 rounded-xl bg-slate-900 px-5 py-3 font-semibold text-white disabled:bg-slate-300">
            {mentorLoading ? 'Наставник думает…' : 'Спросить наставника'}
          </button>
          <p className="mt-2 text-sm text-slate-500">Ответы наставника показываются отдельным блоком ниже чата, чтобы не смешивать ввод вопроса и историю подсказок.</p>
        </div>
      </section>

      {mentorMessages.length ? (
        <section className="rounded-3xl bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">AI-наставник</p>
              <h2 className="mt-2 text-2xl font-semibold text-slate-900">Ответы с опорой на библиотеку GLAME</h2>
              <p className="mt-2 text-sm text-slate-600">Если наставник использовал опубликованные учебные материалы, источники показываются под ответом.</p>
            </div>
            <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">Сообщений: {mentorMessages.length}</div>
          </div>
          <div className="mt-4 space-y-3">
            {mentorMessages.slice(0, 4).map((messageItem) => {
              const sources = messageItem.context?.library_context?.source_materials || [];
              return (
                <article key={messageItem.id} className="rounded-2xl border border-slate-200 p-4">
                  {messageItem.question_text ? <div className="text-sm font-semibold text-slate-900">Вопрос: {messageItem.question_text}</div> : null}
                  <p className="mt-2 text-sm leading-6 text-slate-700">{messageItem.response_text}</p>
                  {sources.length ? (
                    <div className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
                      <div className="font-semibold">Источники библиотеки GLAME</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {sources.map((source) => <span key={`${source.id || source.title}`} className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-amber-900">{source.title} · {source.topic}</span>)}
                      </div>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      {false ? <section className="grid gap-4 lg:grid-cols-2">
        {loading ? <div className="rounded-3xl bg-white p-6 text-slate-500 shadow-sm">Загрузка программ…</div> : null}
        {!loading && programs.length === 0 ? <div className="rounded-3xl bg-white p-6 text-slate-500 shadow-sm">Программы пока не назначены.</div> : null}
        {programs.map((program) => (
          <article key={program.id} className={`rounded-3xl border bg-gradient-to-br p-6 shadow-sm ${programAccent[program.code] || 'from-white to-slate-50 border-slate-200'}`}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">{program.is_required ? 'Обязательная программа' : 'Дополнительная программа'}</div>
                <h2 className="mt-2 text-2xl font-semibold text-slate-900">{program.title}</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">{program.description}</p>
              </div>
              <span className="rounded-full bg-white px-3 py-1 text-sm font-medium text-slate-700 shadow-sm">{statusLabels[program.status] || program.status}</span>
            </div>
          </article>
        ))}
      </section> : null}

      {(programDetail || programDetailLoading) && agentStage !== 'practice' && (
        <section ref={trainingWorkspaceRef} className="rounded-3xl bg-white p-6 shadow-sm">
          {programDetailLoading ? <p className="text-slate-500">Загрузка структуры программы…</p> : null}
          {programDetail ? (
            <div className="space-y-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">Структура программы</p>
                  <h2 className="mt-2 text-2xl font-semibold text-slate-900">{programDetail.program.title}</h2>
                  <p className="mt-2 max-w-3xl text-sm text-slate-600">{programDetail.program.description}</p>
                </div>
                <div className="rounded-2xl bg-slate-50 p-4 text-right">
                  <div className="text-sm text-slate-500">Пройдено</div>
                  <div className="text-2xl font-semibold text-slate-900">{programDetail.progress.completed_steps}/{programDetail.progress.total_steps}</div>
                </div>
              </div>
              {programDetail.next_step ? (
                <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-900">
                  Следующий этап: <b>{programDetail.next_step.title}</b>
                </div>
              ) : null}
              <div className="grid gap-4 lg:grid-cols-2">
                {programDetail.modules.map((module) => (
                  <article key={module.id} className="rounded-2xl border border-slate-200 p-4">
                    <h3 className="font-semibold text-slate-900">{module.title}</h3>
                    {module.description ? <p className="mt-1 text-sm text-slate-500">{module.description}</p> : null}
                    <div className="mt-4 space-y-2">
                      {module.steps.map((step) => (
                        <div key={step.id} className="rounded-xl bg-slate-50 p-3">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <div className="font-medium text-slate-900">{step.title}</div>
                              {step.competencies?.length ? <div className="mt-1 text-xs text-slate-500">{step.competencies.join(' · ')}</div> : null}
                            </div>
                            <span className="rounded-full bg-white px-3 py-1 text-xs text-slate-600">{statusLabels[step.status] || step.status}</span>
                          </div>
                          {step.status !== 'locked' ? (
                            <button
                              onClick={() => {
                                setActiveStep(step);
                                setStepAnswer('');
                                setStepEveningReview('');
                              }}
                              className="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100"
                            >
                              Открыть задание этапа
                            </button>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
              {activeStep ? (
                <section className="rounded-2xl border border-slate-200 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Задание этапа</p>
                      <h3 className="mt-1 text-lg font-semibold text-slate-900">{activeStep.title}</h3>
                      <p className="mt-1 text-sm text-slate-500">Статус: {statusLabels[activeStep.status] || activeStep.status}</p>
                    </div>
                    {activeStep.score != null ? <div className="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-600">AI: {activeStep.score}/10</div> : null}
                  </div>
                  <div className="mt-4 grid gap-4 lg:grid-cols-2">
                    <div className="rounded-xl bg-slate-50 p-4">
                      <h4 className="font-semibold text-slate-900">Урок</h4>
                      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{activeStep.lesson_text || 'Прочитайте цель этапа и разберите, зачем этот стандарт нужен клиенту и продавцу GLAME.'}</p>
                    </div>
                    <div className="rounded-xl bg-amber-50 p-4">
                      <h4 className="font-semibold text-amber-950">Практика</h4>
                      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-amber-900">{activeStep.practice_text || 'Примените тему на конкретном украшении или клиентском сценарии: что вы сделали, какую фразу сказали, что изменилось в диалоге.'}</p>
                    </div>
                  </div>
                  <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-white p-4">
                    <h4 className="font-semibold text-slate-900">Шаблон ответа</h4>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{activeStep.answer_template || taskAnswerTemplate}</p>
                  </div>
                  <div className="mt-4 rounded-xl border border-slate-200 p-4">
                    <h4 className="font-semibold text-slate-900">Как будет оцениваться</h4>
                    <ul className="mt-2 space-y-1 text-sm text-slate-600">
                      {(activeStepRubric.length ? activeStepRubric : taskAssessmentCriteria).map((criterion) => <li key={criterion}>• {criterion}</li>)}
                    </ul>
                  </div>
                  {isStepPracticeBlocked ? (
                    <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                      <div className="font-semibold">Практика откроется после изучения обязательных материалов.</div>
                      <div className="mt-1">Изучено: {activeStepPracticeGate?.completed_required_materials || 0}/{activeStepPracticeGate?.required_materials || 0}</div>
                      {activeStepPracticeGate?.blocked_materials?.length ? (
                        <ul className="mt-2 space-y-1">
                          {activeStepPracticeGate.blocked_materials.map((material) => <li key={material.material_id || material.title}>• {material.title || 'Материал'} — {material.progress_percent || 0}%</li>)}
                        </ul>
                      ) : null}
                    </div>
                  ) : null}
                  <textarea
                    className="mt-4 h-28 w-full rounded-xl border p-3"
                    placeholder="Транскрипт устного ответа появится здесь. Можно поправить текст после надиктовки."
                    value={stepAnswer}
                    onChange={(e) => setStepAnswer(e.target.value)}
                    disabled={isStepPracticeBlocked}
                  />
                  {renderVoiceAnswerControls('step', isStepPracticeBlocked)}
                  <textarea
                    className="mt-3 h-20 w-full rounded-xl border p-3"
                    placeholder="Вечерний разбор / наблюдение в смене"
                    value={stepEveningReview}
                    onChange={(e) => setStepEveningReview(e.target.value)}
                    disabled={isStepPracticeBlocked}
                  />
                  <button
                    onClick={submitStepAnswer}
                    disabled={!hasAnswerForSubmit(stepAnswer) || isStepPracticeBlocked || activeStep.status === 'locked' || activeStep.status === 'submitted'}
                    className="mt-3 rounded-xl bg-slate-900 px-5 py-3 font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    Отправить этап на проверку
                  </button>
                  <p className="mt-2 text-sm text-slate-500">
                    {isStepPracticeBlocked
                      ? 'Сначала откройте методические материалы текущего этапа и отметьте обязательные слайды как изученные.'
                      : !hasAnswerForSubmit(stepAnswer) ? 'Кнопка отправки станет активной после устного ответа: надиктуйте, запишите голосовое или загрузите аудиофайл. Если непонятно, что говорить, нажмите “Спросить AI-наставника”.' : 'AI делает только предварительную оценку: голос будет транскрибирован, итоговый комментарий продавцу подтверждает руководитель.'}
                  </p>
                </section>
              ) : null}
            </div>
          ) : null}
        </section>
      )}

      <section className="rounded-3xl bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-400">Аналитика обучения</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">{competencySummary?.level || summary.level || 'Стажер'}</h2>
            <p className="mt-2 text-sm text-slate-600">Отдельный блок для прогресса, компетенций, аттестации и уровня. Он не управляет прохождением урока — продавца ведет AI-наставник выше.</p>
          </div>
          <div className="rounded-2xl bg-slate-50 px-5 py-4 text-right">
            <div className="text-sm text-slate-500">Допуск к аттестации</div>
            <div className="mt-1 text-lg font-semibold text-slate-900">{competencySummary?.attestation_ready ? 'Готов' : 'Набирает базу'}</div>
          </div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-3">
          <div className="rounded-2xl bg-slate-50 p-4">
            <div className="text-sm text-slate-500">Общий прогресс</div>
            <div className="mt-1 text-2xl font-semibold text-slate-900">{totalCompleted}/{totalSteps || '—'}</div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <div className="text-sm text-slate-500">Средний балл</div>
            <div className="mt-1 text-2xl font-semibold text-slate-900">{averageScore ?? '—'}</div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <div className="text-sm text-slate-500">Доступные программы</div>
            <div className="mt-1 text-2xl font-semibold text-slate-900">{programs.length || summary.program_count || 0}</div>
          </div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {Object.values(competencySummary?.competencies || {}).map((competency) => (
            <div key={competency.code} className="rounded-2xl border border-slate-200 p-4">
              <div className="text-sm font-semibold text-slate-900">{competency.label}</div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-slate-900" style={{ width: `${Math.min(competency.percent || 0, 100)}%` }} />
              </div>
              <div className="mt-2 text-xs text-slate-500">{competency.accepted_steps}/{competency.total_steps} · {competency.percent}%</div>
            </div>
          ))}
        </div>
        {competencySummary?.achievements?.length ? (
          <div className="mt-5 flex flex-wrap gap-2">
            {competencySummary.achievements.map((achievement) => (
              <span key={achievement.code} className="rounded-full bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-900" title={achievement.description}>🏅 {achievement.title}</span>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}
