'use client';

import { useEffect, useMemo, useState } from 'react';
import type { ChangeEvent } from 'react';
import { apiClient } from '@/lib/api';

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
  stats?: { assigned: number; submitted: number; accepted: number };
};

type TrainingSubmission = {
  id: string;
  topic_id: string;
  seller?: { full_name?: string | null; email?: string | null; phone?: string | null } | null;
  practice_answer: string;
  evening_review?: string | null;
  ai_score?: number | null;
  ai_evaluation?: { review_comment?: string; criteria?: Record<string, number>; recommendation?: string };
  review_status: string;
  consultant_feedback?: string | null;
  created_at?: string | null;
};

type TrainingStepSubmission = TrainingSubmission & {
  program_id: string;
  step_id: string;
  step_title?: string | null;
  status: string;
};

type TeamCompetencyResponse = {
  team_competencies: Array<{ code: string; label: string; accepted_steps: number; total_steps: number; percent: number }>;
  sellers: Array<{ seller?: { full_name?: string | null; email?: string | null }; profile: { level: string; completed_steps: number; total_steps: number; average_score?: number | null; attestation_ready: boolean } }>;
  risks: Array<{ seller?: { full_name?: string | null; email?: string | null }; profile: { level: string; completed_steps: number; weakest_competencies?: Array<{ label: string; percent: number }> } }>;
};

type TrainingCareerLevels = {
  summary: { total_sellers: number; average_score: number; attention_count: number; level_distribution: Record<string, number> };
  level_track: Array<{ code: string; title: string; min_score: number }>;
  salary_policy: { status: string; description: string };
  sellers: Array<{
    seller?: { full_name?: string | null; email?: string | null } | null;
    career_level: {
      current_level: { code: string; title: string; score: number };
      next_level?: { code: string; title: string; min_score: number } | null;
      score_breakdown: Record<string, number>;
      requirements_to_next_level: string[];
    };
    manager_next_action: string;
  }>;
  month?: string | null;
  kpi_error?: string | null;
};

type Attestation = {
  id: string;
  attestation_type: string;
  status: string;
  ai_score?: number | null;
  recommended_level?: string | null;
  certified_level?: string | null;
  manager_feedback?: string | null;
  ai_evaluation?: { review_comment?: string; recommendation?: string };
  seller?: { full_name?: string | null; email?: string | null } | null;
};

type MentorMessage = {
  id: string;
  question_text?: string | null;
  response_text: string;
  context?: { focus_tags?: string[]; program_title?: string; step_title?: string };
  risk_flags?: string[];
  seller?: { full_name?: string | null; email?: string | null } | null;
  created_at?: string | null;
};

type ShiftReflection = {
  id: string;
  shift_date?: string | null;
  store_name?: string | null;
  status: string;
  ai_score?: number | null;
  risk_flags?: string[];
  manager_note?: string | null;
  reflection_payload?: { worked_well?: string; difficult_scenario?: string; glame_argument?: string; needs_help?: string };
  seller?: { full_name?: string | null; email?: string | null } | null;
  created_at?: string | null;
};

type CoachingAction = {
  id: string;
  reflection_id?: string | null;
  status: string;
  planned_for?: string | null;
  store_name?: string | null;
  coaching_topic: string;
  competency?: string | null;
  kpi_metric?: string | null;
  risk_flags?: string[];
  manager_script?: string | null;
  seller_next_step?: string | null;
  manager_result?: string | null;
  seller_visible_feedback?: string | null;
  seller?: { full_name?: string | null; email?: string | null } | null;
  created_at?: string | null;
};

type TrainingProgram = {
  id: string;
  code: string;
  title: string;
  description?: string | null;
  program_type: string;
  status: string;
  is_required: boolean;
  order_index: number;
};

type TrainingProgramAssignment = {
  id: string;
  program_id: string;
  seller_user_id?: string | null;
  status: string;
  average_score?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
};

type TrainingProgramAssignmentUser = {
  id: string;
  full_name?: string | null;
  email?: string | null;
  role?: string | null;
  active_program_id?: string | null;
  assigned_programs?: TrainingProgramAssignment[];
};

type TrainingProgramDetail = {
  program: { id: string; title: string; code: string };
  progress: { completed_steps: number; total_steps: number; percent: number };
  modules: Array<{
    id: string;
    title: string;
    description?: string | null;
    steps: Array<{ id: string; title: string; status: string; competencies?: string[] }>;
  }>;
};

type TrainingAnalytics = {
  summary: {
    active_learners: number;
    zero_progress: number;
    pending_reviews: number;
    revision_count: number;
    attestation_ready: number;
    attestation_pending: number;
    certified: number;
    mentor_risk_count: number;
  };
  risk_sellers: Array<{ seller?: { full_name?: string | null; email?: string | null }; completed_steps: number; total_steps: number; weakest_competencies?: Array<{ label: string; percent: number }> }>;
  competency_heatmap: Array<{ code: string; label: string; risk_count: number; average_percent: number }>;
  submission_bottlenecks: Array<{ step_title: string; pending_or_revision: number; revision_count: number }>;
  mentor_focus_tags: Array<{ tag: string; count: number }>;
  recommendations: Array<{ type: string; title: string; text: string }>;
  kpi_linkage?: {
    month?: string | null;
    summary: { matched_sellers: number; low_kpi_and_low_training: number; avg_completion_low_training?: number | null; avg_completion_trained?: number | null };
    seller_actions: Array<{
      seller?: { full_name?: string | null; email?: string | null };
      store_name?: string | null;
      priority: string;
      recommended_training_focus: string;
      manager_action: string;
      kpi_weaknesses?: string[];
      training: { level?: string | null; completed_steps: number; total_steps: number; percent: number; attestation_ready: boolean };
      kpi: { revenue?: number | null; revenue_plan?: number | null; completion_percent?: number | null; avg_check?: number | null; items_per_check?: number | null; checks?: number | null };
    }>;
    recommendations: Array<{ type: string; title: string; text: string }>;
    error?: string;
    note?: string;
  };
};

type TrainingAccountMatching = {
  month?: string | null;
  summary: { total_kpi_sellers: number; training_accounts: number; matched: number; matched_by_external_id: number; matched_by_name: number; unresolved: number; training_only: number };
  unresolved: Array<{ seller_external_id?: string | null; seller_name?: string | null; store_name?: string | null; reason?: string }>;
  matches: Array<{ match_type: string; confidence: string; kpi_seller: { seller_external_id?: string | null; seller_name?: string | null; store_name?: string | null }; user: { id: string; full_name?: string | null; email?: string | null; role?: string | null } }>;
  training_only: Array<{ id: string; full_name?: string | null; email?: string | null; role?: string | null }>;
  recommendations: Array<{ type: string; title: string; text: string }>;
  error?: string;
};

type DocumentExtractorStatus = {
  summary?: { ready?: boolean; free_disk_gb?: number | null };
  recommendation?: string;
  supported_extensions?: string[];
  warnings?: string[];
  extractors?: Record<string, { available?: boolean; installed?: boolean; purpose?: string }>;
};

type TrainingAssessmentQuestion = {
  question: string;
  type?: string;
  difficulty?: string;
  expected_answer?: string;
  criteria?: string[];
  source_excerpt?: string;
  order_index?: number;
};

type TrainingMaterialExtraction = {
  quality?: string;
  ocr_required?: boolean;
  extraction_reviewed?: boolean;
  warnings?: string[];
  text_chars?: number;
  word_count?: number;
  extractor?: string;
  manager_note?: string;
  filename?: string;
  extension?: string;
  learning_pack?: {
    practice?: { task?: string; answer_template?: string[] };
    assessment?: { criteria?: string[]; manager_review_note?: string; question_pool?: TrainingAssessmentQuestion[] };
    agent?: Record<string, any>;
    updated_at?: string;
  };
};

type TrainingMaterialSourceFile = {
  filename?: string | null;
  mime_type?: string | null;
  extension?: string | null;
  size_bytes?: number | null;
  has_content?: boolean;
  storage?: string | null;
};

type TrainingMaterialVisualAsset = {
  asset_id: string;
  filename?: string | null;
  mime_type?: string | null;
  extension?: string | null;
  page?: number | null;
  image_index?: number | null;
  width?: number | null;
  height?: number | null;
  size_bytes?: number | null;
  status: string;
  source?: string | null;
  admin_only?: boolean;
  has_content?: boolean;
  image_url?: string | null;
  review_note?: string | null;
  attached_slide_id?: string | null;
};

type TrainingMaterialFolder = {
  program?: TrainingProgram | null;
  program_code?: string | null;
  title: string;
  count: number;
  materials: TrainingMaterial[];
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
  source_type?: string | null;
  source_file?: TrainingMaterialSourceFile | null;
  visual_assets?: TrainingMaterialVisualAsset[];
  visual_assets_summary?: { total?: number; pending_review?: number; approved?: number; rejected?: number; attached?: number } | null;
  extraction?: TrainingMaterialExtraction;
  program_code?: string | null;
  competencies?: string[];
  internal_notes?: string | null;
  order_index?: number;
};

type TrainingMaterialSlide = {
  id: string;
  material_id: string;
  title: string;
  body?: string | null;
  image_url?: string | null;
  image_prompt?: string | null;
  speaker_note?: string | null;
  quiz_question?: string | null;
  status: string;
  order_index: number;
};

type TrainingMaterialHistoryEvent = {
  id: string;
  from_status?: string | null;
  to_status: string;
  note?: string | null;
  changed_by_user_id?: string | null;
  created_at?: string | null;
};

type TrainingMaterialProgressAnalytics = {
  summary: {
    published_materials: number;
    published_slides: number;
    active_learners: number;
    completed_material_instances: number;
    blocked_materials: number;
    average_completion_percent: number;
    program_subscribed_sellers?: number;
    program_in_progress_sellers?: number;
    program_completed_sellers?: number;
    average_understanding_percent?: number | null;
  };
  programs?: Array<{
    program_id: string;
    code?: string | null;
    title?: string | null;
    status?: string | null;
    published_materials: number;
    subscribed_sellers: number;
    in_progress_sellers: number;
    completed_sellers: number;
    average_understanding_percent?: number | null;
    attention_level: string;
    manager_action: string;
  }>;
  materials: Array<{
    material_id: string;
    title?: string | null;
    topic?: string | null;
    category?: string | null;
    required_to_complete: boolean;
    slides: number;
    started_learners: number;
    completed_learners: number;
    completion_percent: number;
    average_slide_progress: number;
    risk_level: string;
    manager_action: string;
  }>;
  recommendations: Array<{ type: string; title: string; text: string }>;
};

type TrainingMaterialLearningPack = {
  status: string;
  review_required: boolean;
  message?: string;
  slides: Array<TrainingMaterialSlide & { content_format?: string }>;
  practice: { task?: string; answer_template?: string[] };
  assessment: { criteria?: string[]; manager_review_note?: string; question_pool?: TrainingAssessmentQuestion[] };
  created_slides?: TrainingMaterialSlide[];
};

const today = new Date();
const defaultMonth = today.toISOString().slice(0, 7);
const tomorrow = new Date(today.getTime() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

const statusLabels: Record<string, string> = {
  draft: 'Черновик',
  review: 'На проверке',
  published: 'Опубликовано',
  monthly_approval: 'План месяца на согласовании',
  approved: 'Согласовано',
  needs_revision: 'Нужно доработать',
  ready_to_publish: 'Готово к отправке',
  sent_to_consultants: 'Отправлено консультантам',
  completion_tracking: 'Прохождение и обратная связь',
  archived: 'Архив',
  available: 'Назначен',
  in_progress: 'Проходит',
  waiting_review: 'Ждет проверки',
  completed: 'Завершен',
  certified: 'Сертифицирован',
  locked: 'Заблокирован',
};

function statusLabel(status: string) {
  return statusLabels[status] || status;
}

function formatFileSize(size?: number | null) {
  if (!size) return 'размер не указан';
  if (size < 1024) return `${size} Б`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} КБ`;
  return `${(size / (1024 * 1024)).toFixed(1)} МБ`;
}

function buildProgramCodeFromTitle(title: string) {
  const translit: Record<string, string> = {
    а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'h', ц: 'c', ч: 'ch', ш: 'sh', щ: 'sch', ы: 'y', э: 'e', ю: 'yu', я: 'ya', ь: '', ъ: '',
  };
  const code = title
    .trim()
    .toLowerCase()
    .split('')
    .map((char) => translit[char] ?? char)
    .join('')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 60);
  return code || `program_${Date.now().toString(36)}`;
}

function renderMarkdownPreview(markdown: string) {
  const lines = markdown.split('\n');
  return lines.map((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) return <div key={index} className="h-3" />;
    if (trimmed.startsWith('# ')) return <h1 key={index} className="mt-3 text-xl font-semibold text-slate-900">{trimmed.slice(2)}</h1>;
    if (trimmed.startsWith('## ')) return <h2 key={index} className="mt-3 text-lg font-semibold text-slate-900">{trimmed.slice(3)}</h2>;
    if (trimmed.startsWith('- ')) return <div key={index} className="ml-4 text-sm text-slate-600">• {trimmed.slice(2)}</div>;
    return <p key={index} className="text-sm leading-6 text-slate-600">{line}</p>;
  });
}

const activeAssignmentStatuses = new Set(['available', 'in_progress', 'waiting_review', 'needs_revision', 'completed', 'certified']);

export default function ConsultantTrainingAdminPage() {
  const [month, setMonth] = useState(defaultMonth);
  const [programs, setPrograms] = useState<TrainingProgram[]>([]);
  const [programDetail, setProgramDetail] = useState<TrainingProgramDetail | null>(null);
  const [topics, setTopics] = useState<TrainingTopic[]>([]);
  const [submissions, setSubmissions] = useState<TrainingSubmission[]>([]);
  const [stepSubmissions, setStepSubmissions] = useState<TrainingStepSubmission[]>([]);
  const [teamCompetencies, setTeamCompetencies] = useState<TeamCompetencyResponse | null>(null);
  const [careerLevels, setCareerLevels] = useState<TrainingCareerLevels | null>(null);
  const [trainingAnalytics, setTrainingAnalytics] = useState<TrainingAnalytics | null>(null);
  const [accountMatching, setAccountMatching] = useState<TrainingAccountMatching | null>(null);
  const [attestations, setAttestations] = useState<Attestation[]>([]);
  const [mentorMessages, setMentorMessages] = useState<MentorMessage[]>([]);
  const [shiftReflections, setShiftReflections] = useState<ShiftReflection[]>([]);
  const [coachingActions, setCoachingActions] = useState<CoachingAction[]>([]);
  const [trainingMaterials, setTrainingMaterials] = useState<TrainingMaterial[]>([]);
  const [materialFolders, setMaterialFolders] = useState<TrainingMaterialFolder[]>([]);
  const [programAssignmentUsers, setProgramAssignmentUsers] = useState<TrainingProgramAssignmentUser[]>([]);
  const [selectedProgramSubscribersId, setSelectedProgramSubscribersId] = useState<string | null>(null);
  const [excludingEnrollmentId, setExcludingEnrollmentId] = useState<string | null>(null);
  const [activeMaterialProgramCode, setActiveMaterialProgramCode] = useState<string>('');
  const [assignmentForm, setAssignmentForm] = useState({ seller_user_id: '', program_id: '', note: '' });
  const [assigningProgram, setAssigningProgram] = useState(false);
  const [showNewProgramForm, setShowNewProgramForm] = useState(false);
  const [creatingProgram, setCreatingProgram] = useState(false);
  const [newProgramForm, setNewProgramForm] = useState({ title: '', code: '', description: '', program_type: 'custom' });
  const [materialProgressAnalytics, setMaterialProgressAnalytics] = useState<TrainingMaterialProgressAnalytics | null>(null);
  const [documentExtractorStatus, setDocumentExtractorStatus] = useState<DocumentExtractorStatus | null>(null);
  const [selectedMaterial, setSelectedMaterial] = useState<TrainingMaterial | null>(null);
  const [materialHistory, setMaterialHistory] = useState<TrainingMaterialHistoryEvent[]>([]);
  const [materialSlides, setMaterialSlides] = useState<TrainingMaterialSlide[]>([]);
  const [materialVisualAssets, setMaterialVisualAssets] = useState<TrainingMaterialVisualAsset[]>([]);
  const [reviewingVisualAssetId, setReviewingVisualAssetId] = useState<string | null>(null);
  const [selectedSlideId, setSelectedSlideId] = useState<string | null>(null);
  const [editingSlideId, setEditingSlideId] = useState<string | null>(null);
  const [learningPackPreview, setLearningPackPreview] = useState<TrainingMaterialLearningPack | null>(null);
  const [extractionReviewNote, setExtractionReviewNote] = useState('');
  const [retryExtractionFile, setRetryExtractionFile] = useState<{ filename: string; content?: string; content_base64?: string; mime_type?: string } | null>(null);
  const [retryingExtraction, setRetryingExtraction] = useState(false);
  const [generatingLearningPack, setGeneratingLearningPack] = useState(false);
  const [savingMaterial, setSavingMaterial] = useState(false);
  const [deletingMaterialId, setDeletingMaterialId] = useState<string | null>(null);
  const [materialSearch, setMaterialSearch] = useState('');
  const [showManualMaterialForm, setShowManualMaterialForm] = useState(false);
  const [materialTopicFilter, setMaterialTopicFilter] = useState('');
  const [materialStatusFilter, setMaterialStatusFilter] = useState('');
  const [importFiles, setImportFiles] = useState<Array<{ filename: string; content?: string; content_base64?: string; mime_type?: string }>>([]);
  const [importingMaterials, setImportingMaterials] = useState(false);
  const [importSummary, setImportSummary] = useState<{ ready_to_import?: number; skipped?: number; total_files?: number; warnings?: number } | null>(null);
  const [materialForm, setMaterialForm] = useState({
    title: 'Первый контакт 30–60 секунд',
    topic: 'Сервис',
    category: 'База стажера',
    description: '',
    markdown_content: '# Первый контакт\n\nКороткий учебный материал для продавца: что сказать клиенту и какую практику выполнить на смене.',
    status: 'draft',
    tags: 'сервис, первый контакт',
    program_code: 'trainee_base',
  });
  const [materialEditorForm, setMaterialEditorForm] = useState({
    title: '',
    topic: '',
    category: '',
    description: '',
    markdown_content: '',
    status: 'draft',
    tags: '',
    competencies: '',
    program_code: '',
    internal_notes: '',
    order_index: '100',
    status_note: '',
  });
  const [stepMaterialForm, setStepMaterialForm] = useState({ program_id: '', step_id: '', role: 'primary_lesson', required_to_complete: true, order_index: '100' });
  const [slideForm, setSlideForm] = useState({ title: 'Слайд 1: идея урока', body: 'Коротко объясните учебную мысль и действие продавца.', image_url: '', image_prompt: '', speaker_note: '', quiz_question: '', status: 'draft', order_index: '100' });
  const [linkSelections, setLinkSelections] = useState<Record<string, string>>({});
  const [linkingKey, setLinkingKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    lesson_date: tomorrow,
    title: 'Стилистический подбор украшений в GLAME',
    theme: '',
    goal: '',
    material_text: '',
    assignment_text: 'Взять 3 изделия и объяснить, что они дают образу.',
    focus_text: 'Перед показом украшения сформулировать: что я хочу усилить в образе клиента?',
    status: 'monthly_approval',
  });

  const tomorrowTopic = useMemo(() => topics.find((topic) => topic.lesson_date === tomorrow), [topics]);
  const programSteps = useMemo(() => (programDetail?.modules || []).flatMap((module) => module.steps.map((step) => ({ ...step, module_id: module.id, module_title: module.title }))), [programDetail]);
  const selectedSlide = useMemo(() => materialSlides.find((slide) => slide.id === selectedSlideId) || materialSlides[0] || null, [materialSlides, selectedSlideId]);
  const selectedProgramSubscribers = useMemo(() => {
    if (!selectedProgramSubscribersId) return [];
    return programAssignmentUsers
      .map((user) => {
        const assignment = (user.assigned_programs || []).find((item) => item.program_id === selectedProgramSubscribersId && activeAssignmentStatuses.has((item.status || '').toLowerCase()));
        return assignment ? { user, assignment } : null;
      })
      .filter((item): item is { user: TrainingProgramAssignmentUser; assignment: TrainingProgramAssignment } => Boolean(item));
  }, [programAssignmentUsers, selectedProgramSubscribersId]);

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [programsResponse, topicsResponse, submissionsResponse, stepSubmissionsResponse, competenciesResponse, careerLevelsResponse, analyticsResponse, accountMatchingResponse, attestationsResponse, mentorResponse, reflectionsResponse, coachingResponse, materialsResponse, materialProgressResponse, extractorStatusResponse, assignmentsResponse] = await Promise.all([
        apiClient.get('/api/admin/consultant-training/programs'),
        apiClient.get('/api/admin/consultant-training/topics', { params: { month } }),
        apiClient.get('/api/admin/consultant-training/submissions'),
        apiClient.get('/api/admin/consultant-training/step-submissions'),
        apiClient.get('/api/admin/consultant-training/competencies'),
        apiClient.get('/api/admin/consultant-training/career-levels', { params: { month } }).catch(() => null),
        apiClient.get('/api/admin/consultant-training/analytics', { params: { month } }),
        apiClient.get('/api/admin/consultant-training/account-matching', { params: { month } }),
        apiClient.get('/api/admin/consultant-training/attestations'),
        apiClient.get('/api/admin/consultant-training/mentor/messages'),
        apiClient.get('/api/admin/consultant-training/shift-reflections').catch(() => null),
        apiClient.get('/api/admin/consultant-training/coaching-actions').catch(() => null),
        apiClient.get('/api/admin/consultant-training/materials').catch(() => null),
        apiClient.get('/api/admin/consultant-training/material-progress-analytics').catch(() => null),
        apiClient.get('/api/admin/consultant-training/document-extractors/status').catch(() => null),
        apiClient.get('/api/admin/consultant-training/program-assignments').catch(() => null),
      ]);
      setPrograms(programsResponse.data.programs || []);
      setTopics(topicsResponse.data.topics || []);
      setSubmissions(submissionsResponse.data.submissions || []);
      setStepSubmissions(stepSubmissionsResponse.data.submissions || []);
      setTeamCompetencies(competenciesResponse.data || null);
      setCareerLevels(careerLevelsResponse?.data?.career_levels || null);
      setTrainingAnalytics(analyticsResponse.data || null);
      setAccountMatching(accountMatchingResponse.data || null);
      setAttestations(attestationsResponse.data.attestations || []);
      setMentorMessages(mentorResponse.data.messages || []);
      setShiftReflections(reflectionsResponse?.data?.reflections || []);
      setCoachingActions(coachingResponse?.data?.coaching_actions || []);
      setTrainingMaterials(materialsResponse?.data?.materials || []);
      setMaterialFolders(materialsResponse?.data?.program_folders || []);
      setMaterialProgressAnalytics(materialProgressResponse?.data || null);
      setDocumentExtractorStatus(extractorStatusResponse?.data || null);
      setProgramAssignmentUsers(assignmentsResponse?.data?.users || []);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось загрузить AI-тренера');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);

  const createTopic = async () => {
    setError(null);
    try {
      await apiClient.post('/api/admin/consultant-training/topics', form);
      setMessage('Тема создана и добавлена на доску.');
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось создать тему');
    }
  };

  const createTrainingMaterial = async () => {
    setError(null);
    try {
      await apiClient.post('/api/admin/consultant-training/materials', {
        ...materialForm,
        tags: materialForm.tags.split(',').map((item) => item.trim()).filter(Boolean),
        source_type: 'manual_md',
      });
      setMessage('Учебный материал сохранен в библиотеку.');
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить материал');
    }
  };

  const createTrainingProgram = async () => {
    const title = newProgramForm.title.trim();
    const code = (newProgramForm.code.trim() || buildProgramCodeFromTitle(title)).toLowerCase();
    if (!title || !code) return;
    setError(null);
    setCreatingProgram(true);
    try {
      const response = await apiClient.post('/api/admin/consultant-training/programs', {
        title,
        code,
        description: newProgramForm.description || 'Новая программа обучения GLAME. Добавьте материалы и структуру уроков.',
        program_type: newProgramForm.program_type || 'custom',
        status: 'active',
        is_required: true,
        order_index: (programs.length + 1) * 100,
        meta: { created_from: 'training_material_folder_ui' },
      });
      const createdProgram: TrainingProgram = response.data;
      setActiveMaterialProgramCode(createdProgram.code);
      setMaterialForm((prev) => ({ ...prev, program_code: createdProgram.code, category: createdProgram.title }));
      setAssignmentForm((prev) => ({ ...prev, program_id: createdProgram.id }));
      setNewProgramForm({ title: '', code: '', description: '', program_type: 'custom' });
      setShowNewProgramForm(false);
      setMessage(`Создана новая папка программы: ${createdProgram.title}. Теперь можно загружать в нее материалы.`);
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось создать программу обучения');
    } finally {
      setCreatingProgram(false);
    }
  };

  const assignTrainingProgram = async () => {
    if (!assignmentForm.seller_user_id || !assignmentForm.program_id) return;
    setError(null);
    setAssigningProgram(true);
    try {
      const response = await apiClient.post('/api/admin/consultant-training/program-assignments', {
        seller_user_id: assignmentForm.seller_user_id,
        program_id: assignmentForm.program_id,
        status: 'available',
        lock_other_programs: true,
        note: assignmentForm.note || 'Назначено из панели AI Тренера',
      });
      setMessage(response.data.message || 'Программа назначена пользователю.');
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось назначить программу');
    } finally {
      setAssigningProgram(false);
    }
  };

  const unassignTrainingProgram = async (assignment: TrainingProgramAssignment, user: TrainingProgramAssignmentUser, programTitle?: string | null) => {
    const userName = user.full_name || user.email || 'сотрудника';
    if (!window.confirm(`Исключить ${userName} из курса «${programTitle || 'Программа обучения'}»? История прохождения сохранится.`)) return;
    setError(null);
    setExcludingEnrollmentId(assignment.id);
    try {
      const response = await apiClient.patch(`/api/admin/consultant-training/program-assignments/${assignment.id}/unassign`, {
        note: `Исключено из списка подписанных курса ${programTitle || assignment.program_id}`,
      });
      setMessage(response.data?.message || 'Курс исключен из активного обучения продавца.');
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось исключить продавца из курса');
    } finally {
      setExcludingEnrollmentId(null);
    }
  };

  const publishTrainingMaterial = async (material: TrainingMaterial) => {
    setError(null);
    try {
      const response = await apiClient.patch(`/api/admin/consultant-training/materials/${material.id}`, { status: 'published', status_note: 'Быстрая публикация из списка материалов' });
      setMessage(response.data?.message || 'Материал опубликован для продавцов вместе со всеми слайдами и визуалами.');
      await loadAll();
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.manager_message || e.message || 'Не удалось опубликовать материал');
    }
  };

  const readImportFile = async (file: File) => {
    const filename = file.webkitRelativePath || file.name;
    const extension = file.name.toLowerCase().split('.').pop() || '';
    if (['md', 'markdown', 'txt', 'text'].includes(extension)) {
      return { filename, content: await file.text(), mime_type: file.type || undefined };
    }
    const contentBase64 = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || '').split(',', 2)[1] || '');
      reader.onerror = () => reject(reader.error || new Error('Не удалось прочитать файл'));
      reader.readAsDataURL(file);
    });
    return { filename, content_base64: contentBase64, mime_type: file.type || undefined };
  };

  const readMarkdownFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    const allowed = ['.md', '.markdown', '.txt', '.text', '.pdf', '.doc', '.docx'];
    const files = Array.from(event.target.files || []).filter((file) => allowed.some((ext) => file.name.toLowerCase().endsWith(ext)));
    const loaded = await Promise.all(files.map(readImportFile));
    setImportFiles(loaded);
    setImportSummary(null);
  };

  const importMarkdownMaterials = async (dryRun = false) => {
    if (!importFiles.length) return;
    setError(null);
    setImportingMaterials(true);
    try {
      const response = await apiClient.post('/api/admin/consultant-training/materials/import-documents', {
        files: importFiles,
        default_topic: 'Общее',
        default_category: selectedMaterialFolder?.title || 'Импорт документов',
        default_status: 'draft',
        default_program_code: activeMaterialProgramCode || null,
        auto_generate_learning_pack: true,
        dry_run: dryRun,
      });
      setImportSummary(response.data.summary || null);
      setMessage(dryRun ? 'Предпросмотр импорта документов готов.' : response.data.message || 'Учебные документы импортированы.');
      if (!dryRun) {
        setImportFiles([]);
        await loadAll();
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось импортировать документы');
    } finally {
      setImportingMaterials(false);
    }
  };

  const openMaterialEditor = async (material: TrainingMaterial) => {
    setError(null);
    try {
      const response = await apiClient.get(`/api/admin/consultant-training/materials/${material.id}`);
      const slidesResponse = await apiClient.get(`/api/admin/consultant-training/materials/${material.id}/slides`).catch(() => null);
      const visualAssetsResponse = await apiClient.get(`/api/admin/consultant-training/materials/${material.id}/visual-assets`).catch(() => null);
      const detail: TrainingMaterial = response.data.material || material;
      setSelectedMaterial(detail);
      setMaterialHistory(response.data.history || []);
      setMaterialSlides(slidesResponse?.data?.slides || []);
      setMaterialVisualAssets(visualAssetsResponse?.data?.visual_assets || detail.visual_assets || []);
      setSelectedSlideId((slidesResponse?.data?.slides || [])[0]?.id || null);
      setEditingSlideId(null);
      setLearningPackPreview(null);
      setExtractionReviewNote('');
      setRetryExtractionFile(null);
      setMaterialEditorForm({
        title: detail.title || '',
        topic: detail.topic || '',
        category: detail.category || '',
        description: detail.description || '',
        markdown_content: detail.markdown_content || '',
        status: detail.status || 'draft',
        tags: (detail.tags || []).join(', '),
        competencies: (detail.competencies || []).join(', '),
        program_code: detail.program_code || '',
        internal_notes: detail.internal_notes || '',
        order_index: String(detail.order_index || 100),
        status_note: '',
      });
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось открыть материал');
    }
  };

  const downloadMaterialSourceFile = async (material: TrainingMaterial) => {
    setError(null);
    try {
      const response = await apiClient.get(`/api/admin/consultant-training/materials/${material.id}/source-file`, { responseType: 'blob' });
      const blob = new Blob([response.data], { type: material.source_file?.mime_type || response.headers['content-type'] || 'application/octet-stream' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = material.source_file?.filename || `${material.title || 'training-material'}.${material.source_file?.extension || 'bin'}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : e.message || 'Исходный файл пока недоступен для скачивания');
    }
  };

  const saveMaterialEditor = async (nextStatus?: string) => {
    if (!selectedMaterial) return;
    setError(null);
    setSavingMaterial(true);
    const status = nextStatus || materialEditorForm.status;
    try {
      const response = await apiClient.patch(`/api/admin/consultant-training/materials/${selectedMaterial.id}`, {
        title: materialEditorForm.title,
        topic: materialEditorForm.topic,
        category: materialEditorForm.category,
        description: materialEditorForm.description || null,
        markdown_content: materialEditorForm.markdown_content,
        status,
        tags: materialEditorForm.tags.split(',').map((item) => item.trim()).filter(Boolean),
        competencies: materialEditorForm.competencies.split(',').map((item) => item.trim()).filter(Boolean),
        program_code: materialEditorForm.program_code || null,
        internal_notes: materialEditorForm.internal_notes || null,
        order_index: Number(materialEditorForm.order_index) || 100,
        status_note: materialEditorForm.status_note || (nextStatus ? `Статус изменен на ${statusLabel(status)}` : undefined),
      });
      setMessage(response.data?.message || 'Материал обновлен.');
      await loadAll();
      await openMaterialEditor({ ...selectedMaterial, status });
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.manager_message || e.message || 'Не удалось сохранить материал');
    } finally {
      setSavingMaterial(false);
    }
  };

  const deleteTrainingMaterial = async (material: TrainingMaterial) => {
    const title = material.title || 'материал без названия';
    const confirmed = window.prompt(`Полностью удалить учебный материал «${title}»?\n\nБудут удалены слайды, прогресс слайдов, привязки к этапам и история статусов. Это действие нельзя отменить.\n\nВведите УДАЛИТЬ для подтверждения.`);
    if (confirmed !== 'УДАЛИТЬ') return;
    setError(null);
    setDeletingMaterialId(material.id);
    try {
      const response = await apiClient.delete(`/api/admin/consultant-training/materials/${material.id}`);
      setMessage(response.data?.message || 'Учебный материал полностью удален.');
      if (selectedMaterial?.id === material.id) {
        setSelectedMaterial(null);
        setMaterialSlides([]);
        setMaterialVisualAssets([]);
        setMaterialHistory([]);
        setSelectedSlideId(null);
        setEditingSlideId(null);
        setLearningPackPreview(null);
      }
      await loadAll();
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : e.message || 'Не удалось удалить материал');
    } finally {
      setDeletingMaterialId(null);
    }
  };

  const loadProgramDetailForMaterials = async (programId: string) => {
    setStepMaterialForm((prev) => ({ ...prev, program_id: programId, step_id: '' }));
    if (!programId) {
      setProgramDetail(null);
      return;
    }
    try {
      const response = await apiClient.get(`/api/admin/consultant-training/programs/${programId}/modules`);
      setProgramDetail(response.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось загрузить структуру программы');
    }
  };

  const selectRetryExtractionFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      setRetryExtractionFile(null);
      return;
    }
    setRetryExtractionFile(await readImportFile(file));
  };

  const retrySelectedMaterialExtraction = async () => {
    if (!selectedMaterial || !retryExtractionFile) return;
    setError(null);
    setRetryingExtraction(true);
    try {
      const response = await apiClient.patch(`/api/admin/consultant-training/materials/${selectedMaterial.id}/retry-extraction`, {
        ...retryExtractionFile,
        note: extractionReviewNote || 'Повторное извлечение/OCR из редактора материала',
        mark_reviewed: true,
      });
      setMessage(response.data.message || 'Повторное извлечение применено.');
      await loadAll();
      await openMaterialEditor({ ...selectedMaterial, extraction: response.data.material?.extraction });
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.manager_message || e.message || 'Не удалось повторно извлечь текст');
    } finally {
      setRetryingExtraction(false);
    }
  };

  const reviewSelectedMaterialExtraction = async () => {
    if (!selectedMaterial || !materialEditorForm.markdown_content.trim()) return;
    setError(null);
    setSavingMaterial(true);
    try {
      const response = await apiClient.patch(`/api/admin/consultant-training/materials/${selectedMaterial.id}/extraction-review`, {
        reviewed_markdown: materialEditorForm.markdown_content,
        note: extractionReviewNote || 'Текст проверен руководителем в редакторе материала',
      });
      setMessage(response.data.message || 'Качество извлечения подтверждено.');
      await loadAll();
      await openMaterialEditor({ ...selectedMaterial, extraction: response.data.material?.extraction });
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.manager_message || e.message || 'Не удалось подтвердить extraction/OCR');
    } finally {
      setSavingMaterial(false);
    }
  };

  const resetSlideForm = () => {
    const nextOrder = Math.max(0, ...materialSlides.map((slide) => Number(slide.order_index) || 0)) + 10;
    setEditingSlideId(null);
    setSlideForm({ title: `Слайд ${materialSlides.length + 1}: идея урока`, body: 'Коротко объясните учебную мысль и действие продавца.', image_url: '', image_prompt: '', speaker_note: '', quiz_question: '', status: 'draft', order_index: String(nextOrder || 100) });
  };

  const startEditMaterialSlide = (slide: TrainingMaterialSlide) => {
    setEditingSlideId(slide.id);
    setSelectedSlideId(slide.id);
    setSlideForm({
      title: slide.title || '',
      body: slide.body || '',
      image_url: slide.image_url || '',
      image_prompt: slide.image_prompt || '',
      speaker_note: slide.speaker_note || '',
      quiz_question: slide.quiz_question || '',
      status: slide.status || 'draft',
      order_index: String(slide.order_index || 100),
    });
  };

  const saveMaterialSlide = async () => {
    if (!selectedMaterial || !slideForm.title.trim()) return;
    setError(null);
    const payload = {
      title: slideForm.title,
      body: slideForm.body || null,
      image_url: slideForm.image_url || null,
      image_prompt: slideForm.image_prompt || null,
      speaker_note: slideForm.speaker_note || null,
      quiz_question: slideForm.quiz_question || null,
      status: slideForm.status,
      order_index: Number(slideForm.order_index) || 100,
    };
    try {
      const response = editingSlideId
        ? await apiClient.patch(`/api/admin/consultant-training/materials/${selectedMaterial.id}/slides/${editingSlideId}`, payload)
        : await apiClient.post(`/api/admin/consultant-training/materials/${selectedMaterial.id}/slides`, payload);
      setMessage(editingSlideId ? 'Слайд обновлен.' : 'Слайд добавлен в методический материал.');
      setSelectedSlideId(response.data?.slide?.id || editingSlideId || selectedSlideId);
      await openMaterialEditor(selectedMaterial);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить слайд');
    }
  };

  const deleteMaterialSlide = async (slide: TrainingMaterialSlide) => {
    if (!selectedMaterial) return;
    if (!window.confirm(`Удалить слайд «${slide.title}»?`)) return;
    setError(null);
    try {
      await apiClient.delete(`/api/admin/consultant-training/materials/${selectedMaterial.id}/slides/${slide.id}`);
      setMessage('Слайд удален.');
      await openMaterialEditor(selectedMaterial);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось удалить слайд');
    }
  };

  const reviewVisualAsset = async (asset: TrainingMaterialVisualAsset, status: 'approved' | 'rejected', attachToSelectedSlide = false) => {
    if (!selectedMaterial) return;
    setError(null);
    setReviewingVisualAssetId(asset.asset_id);
    try {
      const response = await apiClient.patch(`/api/admin/consultant-training/materials/${selectedMaterial.id}/visual-assets/${asset.asset_id}`, {
        status,
        note: status === 'approved' ? 'Визуал подтвержден руководителем для использования в учебных слайдах' : 'Визуал отклонен руководителем',
        slide_id: attachToSelectedSlide && selectedSlide ? selectedSlide.id : null,
        apply_to_slide: attachToSelectedSlide,
      });
      setMaterialVisualAssets(response.data?.visual_assets || []);
      if (response.data?.slide) {
        setSelectedSlideId(response.data.slide.id);
      }
      setMessage(response.data?.message || 'Визуальный ассет обновлен.');
      await openMaterialEditor(selectedMaterial);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось обновить визуальный ассет');
    } finally {
      setReviewingVisualAssetId(null);
    }
  };

  const attachAllVisualAssets = async () => {
    if (!selectedMaterial) return;
    const candidates = materialVisualAssets.filter((asset) => asset.image_url && asset.status !== 'rejected');
    if (!candidates.length) {
      setError('Нет доступных визуалов для добавления.');
      return;
    }
    setError(null);
    setReviewingVisualAssetId('all');
    try {
      const response = await apiClient.post(`/api/admin/consultant-training/materials/${selectedMaterial.id}/visual-assets/attach-all`, {
        create_missing_slides: true,
        replace_existing_slide_images: false,
      });
      setMaterialVisualAssets(response.data?.visual_assets || []);
      if (response.data?.slides?.length) {
        setSelectedSlideId(response.data.slides[0].id);
      }
      setMessage(response.data?.message || 'Все визуалы добавлены в draft-слайды.');
      await openMaterialEditor(selectedMaterial);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось добавить все визуалы');
    } finally {
      setReviewingVisualAssetId(null);
    }
  };

  const generateLearningPack = async (apply = false, replaceAllSlides = false, replaceDraftSlides = false) => {
    if (!selectedMaterial) return;
    if (replaceAllSlides && !window.confirm('Полностью перегенерировать слайды? Все текущие слайды материала будут удалены и заменены draft-слайдами.')) return;
    setError(null);
    setGeneratingLearningPack(true);
    try {
      const response = await apiClient.post(`/api/admin/consultant-training/materials/${selectedMaterial.id}/learning-pack`, {
        target_slide_count: 5,
        apply,
        replace_existing_draft_slides: replaceDraftSlides,
        replace_all_slides: replaceAllSlides,
      });
      setLearningPackPreview(response.data);
      setMessage(response.data.message || (apply ? 'Draft learning pack сохранен.' : 'Предпросмотр learning pack готов.'));
      if (apply) {
        await openMaterialEditor(selectedMaterial);
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось сформировать learning pack');
    } finally {
      setGeneratingLearningPack(false);
    }
  };

  const attachMaterialToStep = async () => {
    if (!selectedMaterial || !stepMaterialForm.program_id || !stepMaterialForm.step_id) return;
    setError(null);
    try {
      await apiClient.post('/api/admin/consultant-training/step-materials', {
        program_id: stepMaterialForm.program_id,
        step_id: stepMaterialForm.step_id,
        material_id: selectedMaterial.id,
        role: stepMaterialForm.role,
        required_to_complete: stepMaterialForm.required_to_complete,
        order_index: Number(stepMaterialForm.order_index) || 100,
      });
      setMessage('Материал привязан к этапу обучения.');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось привязать материал к этапу');
    }
  };

  const approveTopic = async (topic: TrainingTopic, approved = true) => {
    setError(null);
    try {
      await apiClient.post(`/api/admin/consultant-training/topics/${topic.id}/approve`, { approved });
      setMessage(approved ? 'Тема согласована.' : 'Тема отправлена на доработку.');
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось обновить согласование');
    }
  };

  const publishTopic = async (topic: TrainingTopic) => {
    setError(null);
    try {
      const response = await apiClient.post(`/api/admin/consultant-training/topics/${topic.id}/publish`);
      setMessage(`Материал отправлен в личные кабинеты: назначений ${response.data.created_assignments}.`);
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось отправить консультантам');
    }
  };

  const openProgramStructure = async (program: TrainingProgram) => {
    setError(null);
    try {
      const response = await apiClient.get(`/api/admin/consultant-training/programs/${program.id}/modules`);
      setProgramDetail(response.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось открыть структуру программы');
    }
  };

  const reviewSubmission = async (submission: TrainingSubmission, review_status: string) => {
    setError(null);
    try {
      const defaultFeedback = submission.ai_evaluation?.review_comment || '';
      await apiClient.post(`/api/admin/consultant-training/submissions/${submission.id}/review`, {
        review_status,
        manager_feedback: defaultFeedback,
        consultant_feedback: defaultFeedback,
        send_to_consultant: review_status === 'sent_to_consultant',
      });
      setMessage('Решение по ответу сохранено.');
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось проверить ответ');
    }
  };

  const reviewStepSubmission = async (submission: TrainingStepSubmission, review_status: string) => {
    setError(null);
    try {
      const defaultFeedback = submission.ai_evaluation?.review_comment || '';
      await apiClient.patch(`/api/admin/consultant-training/step-submissions/${submission.id}/review`, {
        review_status,
        manager_feedback: defaultFeedback,
        consultant_feedback: defaultFeedback,
        send_to_consultant: review_status === 'sent_to_consultant',
      });
      setMessage('Решение по этапу сохранено.');
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось проверить этап');
    }
  };

  const reviewAttestation = async (attestation: Attestation, manager_decision: string) => {
    setError(null);
    try {
      await apiClient.patch(`/api/admin/consultant-training/attestations/${attestation.id}/review`, {
        manager_decision,
        manager_feedback: attestation.ai_evaluation?.review_comment || '',
        certified_level: attestation.recommended_level,
      });
      setMessage('Решение по аттестации сохранено.');
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось проверить аттестацию');
    }
  };

  const linkTrainingAccount = async (item: NonNullable<TrainingAccountMatching['unresolved']>[number]) => {
    const key = `${item.seller_external_id || item.seller_name}-${item.store_name}`;
    const userId = linkSelections[key];
    if (!userId) {
      setError('Выберите аккаунт сотрудника для связи.');
      return;
    }
    setError(null);
    setLinkingKey(key);
    try {
      await apiClient.post('/api/admin/consultant-training/account-matching/link', {
        user_id: userId,
        seller_external_id: item.seller_external_id,
        seller_name: item.seller_name,
        store_name: item.store_name,
      });
      setMessage('Аккаунт связан с 1C-продавцом. Диагностика обновлена.');
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось связать аккаунт');
    } finally {
      setLinkingKey(null);
    }
  };

  const createCoachingFromReflection = async (reflection: ShiftReflection) => {
    setError(null);
    try {
      await apiClient.post('/api/admin/consultant-training/coaching-actions', {
        reflection_id: reflection.id,
        planned_for: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
      });
      setMessage('Coaching-задача создана из рефлексии.');
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось создать coaching-задачу');
    }
  };

  const updateCoachingStatus = async (action: CoachingAction, status: string) => {
    setError(null);
    try {
      await apiClient.patch(`/api/admin/consultant-training/coaching-actions/${action.id}`, {
        status,
        seller_visible_feedback: status === 'resolved' ? action.seller_visible_feedback || action.seller_next_step : undefined,
      });
      setMessage('Статус coaching обновлен.');
      await loadAll();
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось обновить coaching');
    }
  };

  const materialTopics = useMemo(() => Array.from(new Set(trainingMaterials.map((material) => material.topic).filter(Boolean))).sort(), [trainingMaterials]);
  const displayMaterialFolders = useMemo(() => {
    if (materialFolders.length) return materialFolders;
    return programs.filter((program) => program.status === 'active').map((program) => {
      const items = trainingMaterials.filter((material) => material.program_code === program.code);
      return { program, program_code: program.code, title: program.title, count: items.length, materials: items };
    });
  }, [materialFolders, programs, trainingMaterials]);
  const selectedMaterialFolder = useMemo(() => displayMaterialFolders.find((folder) => (folder.program_code || '') === activeMaterialProgramCode) || null, [activeMaterialProgramCode, displayMaterialFolders]);
  const visibleTrainingMaterials = useMemo(() => {
    const query = materialSearch.trim().toLowerCase();
    return trainingMaterials.filter((material) => {
      if (activeMaterialProgramCode && (material.program_code || '') !== activeMaterialProgramCode) return false;
      if (materialTopicFilter && material.topic !== materialTopicFilter) return false;
      if (materialStatusFilter && material.status !== materialStatusFilter) return false;
      if (!query) return true;
      return [material.title, material.topic, material.category, material.description || '', material.markdown_content, ...(material.tags || [])].join(' ').toLowerCase().includes(query);
    });
  }, [activeMaterialProgramCode, materialSearch, materialStatusFilter, materialTopicFilter, trainingMaterials]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <header className="rounded-3xl bg-white p-6 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-400">GLAME AI Trainer</p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-900">AI Тренер консультантов</h1>
        <p className="mt-3 max-w-3xl text-slate-600">
          Доска тем, согласование материалов, прохождение в личном кабинете продавца и обратная связь только после проверки руководителем.
        </p>
      </header>

      {error && <div className="rounded-2xl bg-red-50 p-4 text-red-700">{error}</div>}
      {message && <div className="rounded-2xl bg-emerald-50 p-4 text-emerald-700">{message}</div>}

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Библиотека материалов</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-900">Учебные материалы для продавцов</h2>
            <p className="mt-1 text-sm text-slate-500">Материал можно писать в Markdown или загрузить PDF/DOC/DOCX/TXT. Документ конвертируется в draft Markdown, затем AI делает learning pack; публикация только после проверки.</p>
          </div>
          <div className="rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white">{visibleTrainingMaterials.length}/{trainingMaterials.length} материалов</div>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_360px]">
          <div className="rounded-2xl bg-slate-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="font-semibold text-slate-900">Папки программ обучения</h3>
                <p className="mt-1 text-sm text-slate-500">Загружайте материалы сразу в нужную программу: стажер или GLAME Stylist Academy.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button onClick={() => setShowNewProgramForm((value) => !value)} className="rounded-xl bg-indigo-600 px-3 py-2 text-sm font-semibold text-white">+ Добавить программу обучения</button>
                <button onClick={() => { setActiveMaterialProgramCode(''); setMaterialForm((prev) => ({ ...prev, program_code: '' })); }} className={`rounded-xl px-3 py-2 text-sm font-semibold ${!activeMaterialProgramCode ? 'bg-slate-900 text-white' : 'bg-white text-slate-600'}`}>Все папки</button>
              </div>
            </div>
            {showNewProgramForm ? (
              <div className="mt-3 rounded-2xl border border-indigo-100 bg-white p-4">
                <div className="grid gap-2 md:grid-cols-2">
                  <input className="rounded-xl border p-3 text-sm" placeholder="Название программы, например: Руководитель смены GLAME" value={newProgramForm.title} onChange={(e) => setNewProgramForm((prev) => ({ ...prev, title: e.target.value, code: prev.code || buildProgramCodeFromTitle(e.target.value) }))} />
                  <input className="rounded-xl border p-3 text-sm" placeholder="Код папки: shift_lead_glame" value={newProgramForm.code} onChange={(e) => setNewProgramForm((prev) => ({ ...prev, code: e.target.value.toLowerCase().replace(/[^a-z0-9_]+/g, '_') }))} />
                </div>
                <textarea className="mt-2 w-full rounded-xl border p-3 text-sm" rows={2} placeholder="Краткое описание: для кого программа и какие навыки закрывает" value={newProgramForm.description} onChange={(e) => setNewProgramForm((prev) => ({ ...prev, description: e.target.value }))} />
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs text-slate-500">После создания появится новая папка в библиотеке, и импорт PDF/DOC можно будет сразу направлять в нее.</span>
                  <button onClick={createTrainingProgram} disabled={creatingProgram || !newProgramForm.title.trim()} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:bg-slate-300">Создать папку программы</button>
                </div>
              </div>
            ) : null}
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {displayMaterialFolders.map((folder) => (
                <button key={folder.program_code || 'unassigned'} onClick={() => { setActiveMaterialProgramCode(folder.program_code || ''); setMaterialForm((prev) => ({ ...prev, program_code: folder.program_code || '' })); }} className={`rounded-2xl border p-4 text-left transition ${activeMaterialProgramCode === (folder.program_code || '') ? 'border-slate-900 bg-white shadow-sm' : 'border-slate-200 bg-white/70 hover:bg-white'}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">{folder.program_code || 'без программы'}</div>
                      <div className="mt-1 font-semibold text-slate-900">📁 {folder.title}</div>
                    </div>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">{folder.count}</span>
                  </div>
                  <p className="mt-2 text-xs text-slate-500">{folder.count ? folder.materials.slice(0, 2).map((item) => item.title).join(' · ') : 'Папка пока пустая — можно загружать первые уроки.'}</p>
                </button>
              ))}
            </div>
          </div>
          <div className="rounded-2xl border border-indigo-100 bg-indigo-50 p-4">
            <h3 className="font-semibold text-slate-900">Назначить программу продавцу</h3>
            <p className="mt-1 text-sm text-slate-600">При входе в обучение агент выберет назначенную администратором программу и поведет пользователя по ней.</p>
            <div className="mt-3 space-y-2">
              <select className="w-full rounded-xl border border-indigo-100 p-3" value={assignmentForm.seller_user_id} onChange={(e) => setAssignmentForm((prev) => ({ ...prev, seller_user_id: e.target.value }))}>
                <option value="">Выберите пользователя</option>
                {programAssignmentUsers.map((user) => <option key={user.id} value={user.id}>{user.full_name || user.email || user.id}</option>)}
              </select>
              <select className="w-full rounded-xl border border-indigo-100 p-3" value={assignmentForm.program_id} onChange={(e) => setAssignmentForm((prev) => ({ ...prev, program_id: e.target.value }))}>
                <option value="">Выберите программу</option>
                {programs.filter((program) => program.status === 'active').map((program) => <option key={program.id} value={program.id}>{program.title}</option>)}
              </select>
              <input className="w-full rounded-xl border border-indigo-100 p-3" placeholder="Комментарий к назначению" value={assignmentForm.note} onChange={(e) => setAssignmentForm((prev) => ({ ...prev, note: e.target.value }))} />
              <button onClick={assignTrainingProgram} disabled={assigningProgram || !assignmentForm.seller_user_id || !assignmentForm.program_id} className="w-full rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white disabled:bg-slate-300">Назначить программу</button>
            </div>
          </div>
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-[420px_1fr]">
          <div className="space-y-3 rounded-2xl bg-slate-50 p-4">
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-4">
              <div className="font-semibold text-slate-900">AI-импорт исходников</div>
              <p className="mt-1 text-sm text-slate-500">Просто выберите PDF/DOC/DOCX/TXT. Агент сам извлечет текст, распознает тему, категорию, теги, компетенции, привяжет к выбранной папке программы и сформирует draft-слайды. Ручные поля ниже не нужны для загрузки.</p>
              <div className="mt-2 rounded-xl bg-slate-50 p-3 text-xs text-slate-600">Папка импорта: <b>{selectedMaterialFolder?.title || 'не выбрана — без программы'}</b></div>
              <input type="file" accept=".md,.markdown,.txt,.text,.pdf,.doc,.docx,text/plain,text/markdown,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" multiple onChange={readMarkdownFiles} className="mt-3 w-full rounded-xl border p-3 text-sm" />
              {importFiles.length ? <div className="mt-2 text-sm text-slate-600">Выбрано файлов: {importFiles.length}</div> : null}
              {importSummary ? <div className="mt-2 rounded-xl bg-slate-50 p-3 text-sm text-slate-600">Готово: {importSummary.ready_to_import || 0} · пропущено: {importSummary.skipped || 0} · предупреждений: {importSummary.warnings || 0} · всего: {importSummary.total_files || 0}</div> : null}
              {importSummary?.warnings ? <div className="mt-2 rounded-xl bg-amber-50 p-3 text-xs text-amber-900">Есть файлы с низким качеством извлечения или PDF без текстового слоя. Они импортируются как черновики, но перед AI-pack/публикацией нужен OCR или ручная проверка текста.</div> : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <button onClick={() => importMarkdownMaterials(true)} disabled={!importFiles.length || importingMaterials} className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 disabled:text-slate-300">Предпросмотр</button>
                <button onClick={() => importMarkdownMaterials(false)} disabled={!importFiles.length || importingMaterials} className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:bg-slate-300">Импортировать и сформировать материал</button>
              </div>
            </div>
            {documentExtractorStatus ? (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-900">Extractors / OCR readiness</div>
                    <p className="mt-1 text-sm text-slate-500">Статус доступных конвертеров без автоустановки тяжелых OCR-зависимостей.</p>
                  </div>
                  <span className={`rounded-full px-2 py-1 text-xs font-semibold ${documentExtractorStatus.summary?.ready ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>{documentExtractorStatus.recommendation || 'unknown'}</span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {Object.entries(documentExtractorStatus.extractors || {}).slice(0, 6).map(([key, value]) => (
                    <div key={key} className="rounded-xl bg-slate-50 p-2 text-xs">
                      <b>{key}</b><br /><span className={value.available ? 'text-emerald-700' : 'text-amber-700'}>{value.available ? 'доступен' : 'не подключен'}</span>
                    </div>
                  ))}
                </div>
                {documentExtractorStatus.warnings?.length ? <div className="mt-2 rounded-xl bg-amber-50 p-2 text-xs text-amber-900">{documentExtractorStatus.warnings.join(', ')}</div> : null}
              </div>
            ) : null}
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-4">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="font-semibold text-slate-900">Ручное создание материала</div>
                  <p className="mt-1 text-sm text-slate-500">Опционально. Для загрузки PDF/DOC это не требуется — агент заполнит поля сам.</p>
                </div>
                <button onClick={() => setShowManualMaterialForm((value) => !value)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700">{showManualMaterialForm ? 'Скрыть' : 'Создать вручную'}</button>
              </div>
              {showManualMaterialForm ? (
                <div className="mt-3 space-y-3">
                  <input className="w-full rounded-xl border p-3" placeholder="Название" value={materialForm.title} onChange={(e) => setMaterialForm((prev) => ({ ...prev, title: e.target.value }))} />
                  <select className="w-full rounded-xl border p-3" value={materialForm.program_code} onChange={(e) => { setMaterialForm((prev) => ({ ...prev, program_code: e.target.value })); setActiveMaterialProgramCode(e.target.value); }}>
                    <option value="">Без программы</option>
                    {programs.filter((program) => program.status === 'active').map((program) => <option key={program.id} value={program.code}>📁 {program.title}</option>)}
                  </select>
                  <div className="grid gap-3 md:grid-cols-2">
                    <input className="w-full rounded-xl border p-3" placeholder="Тема" value={materialForm.topic} onChange={(e) => setMaterialForm((prev) => ({ ...prev, topic: e.target.value }))} />
                    <input className="w-full rounded-xl border p-3" placeholder="Категория" value={materialForm.category} onChange={(e) => setMaterialForm((prev) => ({ ...prev, category: e.target.value }))} />
                  </div>
                  <input className="w-full rounded-xl border p-3" placeholder="Теги через запятую" value={materialForm.tags} onChange={(e) => setMaterialForm((prev) => ({ ...prev, tags: e.target.value }))} />
                  <textarea className="h-44 w-full rounded-xl border p-3 font-mono text-sm" placeholder="Markdown материал" value={materialForm.markdown_content} onChange={(e) => setMaterialForm((prev) => ({ ...prev, markdown_content: e.target.value }))} />
                  <div className="flex flex-wrap gap-2">
                    <select className="rounded-xl border p-3" value={materialForm.status} onChange={(e) => setMaterialForm((prev) => ({ ...prev, status: e.target.value }))}>
                      <option value="draft">Черновик</option>
                      <option value="review">На проверке</option>
                      <option value="published">Опубликовать продавцам</option>
                    </select>
                    <button onClick={createTrainingMaterial} disabled={!materialForm.title.trim() || !materialForm.markdown_content.trim()} className="rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white disabled:bg-slate-300">Сохранить материал</button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {selectedMaterial ? (
              <div className="md:col-span-2 rounded-2xl border border-amber-200 bg-amber-50 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-600">Редактор материала</p>
                    <h3 className="mt-1 text-lg font-semibold text-slate-900">{selectedMaterial.title}</h3>
                    <p className="mt-1 text-sm text-slate-600">Редактирование .md, предпросмотр и история статусов перед публикацией продавцам.</p>
                  </div>
                  <button onClick={() => setSelectedMaterial(null)} className="rounded-xl bg-white px-3 py-2 text-sm font-semibold text-slate-600">Закрыть</button>
                </div>
                <div className="mt-4 rounded-2xl border border-dashed border-amber-200 bg-white/70 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-600">Исходный файл администратора</p>
                      <h4 className="mt-1 font-semibold text-slate-900">{selectedMaterial.source_file?.filename || selectedMaterial.extraction?.filename || 'Файл не прикреплен'}</h4>
                      <p className="mt-1 text-sm text-slate-600">
                        {selectedMaterial.source_file?.filename || selectedMaterial.extraction?.filename
                          ? `Оригинал, из которого был собран Markdown: ${selectedMaterial.source_file?.mime_type || selectedMaterial.extraction?.extension || selectedMaterial.source_type || 'тип не указан'} · ${formatFileSize(selectedMaterial.source_file?.size_bytes)}`
                          : 'Материал создан вручную или был загружен до включения хранения исходных вложений.'}
                      </p>
                    </div>
                    {selectedMaterial.source_file?.has_content ? (
                      <button onClick={() => downloadMaterialSourceFile(selectedMaterial)} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">Скачать исходник</button>
                    ) : (
                      <span className="rounded-xl bg-amber-100 px-3 py-2 text-xs font-semibold text-amber-800">нет файла для скачивания</span>
                    )}
                  </div>
                </div>
                <div className="mt-4 rounded-2xl border border-indigo-100 bg-indigo-50 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-indigo-500">Admin-only визуальные ассеты из PDF</p>
                      <h4 className="mt-1 font-semibold text-slate-900">Кандидаты для учебных слайдов</h4>
                      <p className="mt-1 text-sm text-slate-600">Изображения из исходника не попадают продавцам автоматически. Руководитель сначала подтверждает визуал, затем может прикрепить его к выбранному слайду.</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-indigo-700">{materialVisualAssets.length} ассетов</span>
                      {materialVisualAssets.length ? (
                        <button onClick={attachAllVisualAssets} disabled={reviewingVisualAssetId === 'all'} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:bg-slate-300">
                          {reviewingVisualAssetId === 'all' ? 'Добавляю…' : 'Добавить все'}
                        </button>
                      ) : null}
                    </div>
                  </div>
                  {materialVisualAssets.length ? (
                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      {materialVisualAssets.map((asset) => (
                        <div key={asset.asset_id} className="rounded-2xl bg-white p-3 shadow-sm">
                          {asset.image_url ? <div role="img" aria-label={asset.filename || asset.asset_id} className="h-36 rounded-xl bg-slate-100 bg-contain bg-center bg-no-repeat" style={{ backgroundImage: `url(${asset.image_url})` }} /> : <div className="flex h-36 items-center justify-center rounded-xl bg-slate-100 text-xs text-slate-400">preview недоступен</div>}
                          <div className="mt-2 text-sm font-semibold text-slate-900">{asset.filename || asset.asset_id}</div>
                          <div className="mt-1 text-xs text-slate-500">стр. {asset.page || '—'} · {asset.width || '?'}×{asset.height || '?'} · {formatFileSize(asset.size_bytes)}</div>
                          <div className="mt-2 flex flex-wrap gap-1 text-xs">
                            <span className={`rounded-full px-2 py-1 font-semibold ${asset.status === 'approved' ? 'bg-emerald-50 text-emerald-700' : asset.status === 'rejected' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-800'}`}>{asset.status}</span>
                            {asset.attached_slide_id ? <span className="rounded-full bg-indigo-50 px-2 py-1 font-semibold text-indigo-700">прикреплен</span> : null}
                          </div>
                          {asset.review_note ? <p className="mt-2 text-xs text-slate-500">{asset.review_note}</p> : null}
                          <div className="mt-3 flex flex-wrap gap-2">
                            <button onClick={() => reviewVisualAsset(asset, 'approved')} disabled={reviewingVisualAssetId === asset.asset_id} className="rounded-lg bg-emerald-600 px-2 py-1 text-xs font-semibold text-white disabled:bg-slate-300">Подтвердить</button>
                            <button onClick={() => reviewVisualAsset(asset, 'approved', true)} disabled={reviewingVisualAssetId === asset.asset_id || !selectedSlide} className="rounded-lg bg-indigo-600 px-2 py-1 text-xs font-semibold text-white disabled:bg-slate-300">В выбранный слайд</button>
                            <button onClick={() => reviewVisualAsset(asset, 'rejected')} disabled={reviewingVisualAssetId === asset.asset_id} className="rounded-lg bg-red-50 px-2 py-1 text-xs font-semibold text-red-700 disabled:text-slate-300">Отклонить</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl bg-white/80 p-3 text-sm text-slate-500">В этом материале пока нет извлеченных PDF-изображений. Для новых PDF агент будет сохранять их здесь как pending_review.</div>
                  )}
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <input className="rounded-xl border p-3" value={materialEditorForm.title} onChange={(e) => setMaterialEditorForm((prev) => ({ ...prev, title: e.target.value }))} placeholder="Название" />
                  <select className="rounded-xl border p-3" value={materialEditorForm.status} onChange={(e) => setMaterialEditorForm((prev) => ({ ...prev, status: e.target.value }))}>
                    <option value="draft">Черновик</option>
                    <option value="review">На проверке</option>
                    <option value="published">Опубликован</option>
                    <option value="archived">Архив</option>
                  </select>
                  <input className="rounded-xl border p-3" value={materialEditorForm.topic} onChange={(e) => setMaterialEditorForm((prev) => ({ ...prev, topic: e.target.value }))} placeholder="Тема" />
                  <input className="rounded-xl border p-3" value={materialEditorForm.category} onChange={(e) => setMaterialEditorForm((prev) => ({ ...prev, category: e.target.value }))} placeholder="Категория" />
                  <input className="rounded-xl border p-3" value={materialEditorForm.tags} onChange={(e) => setMaterialEditorForm((prev) => ({ ...prev, tags: e.target.value }))} placeholder="Теги через запятую" />
                  <input className="rounded-xl border p-3" value={materialEditorForm.competencies} onChange={(e) => setMaterialEditorForm((prev) => ({ ...prev, competencies: e.target.value }))} placeholder="Компетенции через запятую" />
                  <input className="rounded-xl border p-3" value={materialEditorForm.program_code} onChange={(e) => setMaterialEditorForm((prev) => ({ ...prev, program_code: e.target.value }))} placeholder="program_code" />
                  <input className="rounded-xl border p-3" value={materialEditorForm.order_index} onChange={(e) => setMaterialEditorForm((prev) => ({ ...prev, order_index: e.target.value }))} placeholder="Порядок" />
                  <textarea className="md:col-span-2 h-20 rounded-xl border p-3" value={materialEditorForm.description} onChange={(e) => setMaterialEditorForm((prev) => ({ ...prev, description: e.target.value }))} placeholder="Описание" />
                  <textarea className="md:col-span-2 h-20 rounded-xl border p-3" value={materialEditorForm.internal_notes} onChange={(e) => setMaterialEditorForm((prev) => ({ ...prev, internal_notes: e.target.value }))} placeholder="Внутренние заметки руководителя, продавцам не видны" />
                  <textarea className="md:col-span-2 h-72 rounded-xl border p-3 font-mono text-sm" value={materialEditorForm.markdown_content} onChange={(e) => setMaterialEditorForm((prev) => ({ ...prev, markdown_content: e.target.value }))} placeholder="Markdown" />
                  {selectedMaterial.extraction?.quality ? (
                    <div className={`md:col-span-2 rounded-2xl border p-4 ${selectedMaterial.extraction.ocr_required || ['low', 'needs_ocr'].includes(selectedMaterial.extraction.quality || '') ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-emerald-100 bg-emerald-50 text-emerald-900'}`}>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h4 className="font-semibold">Качество извлечения документа: {selectedMaterial.extraction.quality}</h4>
                          <p className="mt-1 text-sm">Extractor: {selectedMaterial.extraction.extractor || 'builtin'} · символов: {selectedMaterial.extraction.text_chars || 0} · слов: {selectedMaterial.extraction.word_count || 0}</p>
                          {selectedMaterial.extraction.warnings?.length ? <p className="mt-1 text-sm">Warnings: {selectedMaterial.extraction.warnings.join(', ')}</p> : null}
                          {selectedMaterial.extraction.manager_note ? <p className="mt-2 text-sm">{selectedMaterial.extraction.manager_note}</p> : null}
                        </div>
                        <span className="rounded-full bg-white/80 px-3 py-1 text-xs font-semibold">{selectedMaterial.extraction.extraction_reviewed ? 'проверено' : 'нужна проверка'}</span>
                      </div>
                      {(selectedMaterial.extraction.ocr_required || ['low', 'needs_ocr'].includes(selectedMaterial.extraction.quality || '')) && !selectedMaterial.extraction.extraction_reviewed ? (
                        <div className="mt-3 rounded-xl bg-white/80 p-3">
                          <p className="text-sm">Перед публикацией или AI-pack замените Markdown на OCR/ручной текст и подтвердите проверку.</p>
                          <input className="mt-2 w-full rounded-xl border border-amber-200 p-2 text-sm" value={extractionReviewNote} onChange={(e) => setExtractionReviewNote(e.target.value)} placeholder="Комментарий: OCR проверен / текст сверила Елена / исправлены ошибки" />
                          <button onClick={reviewSelectedMaterialExtraction} disabled={savingMaterial || !materialEditorForm.markdown_content.trim()} className="mt-2 rounded-xl bg-amber-600 px-4 py-2 text-sm font-semibold text-white disabled:bg-slate-300">Подтвердить OCR/ручную проверку текста</button>
                          <div className="mt-3 rounded-xl border border-dashed border-amber-200 p-3">
                            <p className="text-sm font-semibold">Повторное извлечение / OCR-upload</p>
                            <p className="mt-1 text-xs">Загрузите повторно PDF/DOC/DOCX/TXT или уже OCR-распознанный TXT. Результат заменит Markdown и будет помечен как проверенный.</p>
                            <input type="file" accept=".md,.markdown,.txt,.text,.pdf,.doc,.docx,text/plain,text/markdown,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={selectRetryExtractionFile} className="mt-2 w-full rounded-xl border border-amber-200 p-2 text-sm" />
                            {retryExtractionFile ? <div className="mt-1 text-xs">Файл: {retryExtractionFile.filename}</div> : null}
                            <button onClick={retrySelectedMaterialExtraction} disabled={retryingExtraction || !retryExtractionFile} className="mt-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:bg-slate-300">Применить повторное извлечение</button>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  <div className="rounded-2xl bg-white p-4">
                    <h4 className="font-semibold text-slate-900">Предпросмотр Markdown</h4>
                    <div className="mt-2 max-h-72 overflow-auto rounded-xl border border-slate-100 p-3">{renderMarkdownPreview(materialEditorForm.markdown_content)}</div>
                  </div>
                  <div className="rounded-2xl bg-white p-4">
                    <h4 className="font-semibold text-slate-900">История статусов</h4>
                    <div className="mt-2 space-y-2">
                      {materialHistory.slice(0, 6).map((event) => (
                        <div key={event.id} className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
                          <div className="font-semibold text-slate-800">{event.from_status || 'создан'} → {event.to_status}</div>
                          {event.note ? <div className="mt-1">{event.note}</div> : null}
                          {event.created_at ? <div className="mt-1 text-xs text-slate-400">{new Date(event.created_at).toLocaleString('ru-RU')}</div> : null}
                        </div>
                      ))}
                      {!materialHistory.length ? <div className="text-sm text-slate-500">История появится после первого изменения статуса.</div> : null}
                    </div>
                  </div>
                </div>
                <textarea className="mt-3 h-16 w-full rounded-xl border p-3" value={materialEditorForm.status_note} onChange={(e) => setMaterialEditorForm((prev) => ({ ...prev, status_note: e.target.value }))} placeholder="Комментарий к изменению статуса" />
                <div className="mt-3 rounded-2xl bg-white p-4">
                  <h4 className="font-semibold text-slate-900">Привязка к учебному этапу</h4>
                  <p className="mt-1 text-sm text-slate-500">После привязки материал будет открываться продавцу по программе, шагу и статусу прохождения.</p>
                  <div className="mt-3 grid gap-2 md:grid-cols-2">
                    <select className="rounded-xl border p-3" value={stepMaterialForm.program_id} onChange={(e) => loadProgramDetailForMaterials(e.target.value)}>
                      <option value="">Выберите программу</option>
                      {programs.map((program) => <option key={program.id} value={program.id}>{program.title}</option>)}
                    </select>
                    <select className="rounded-xl border p-3" value={stepMaterialForm.step_id} onChange={(e) => setStepMaterialForm((prev) => ({ ...prev, step_id: e.target.value }))}>
                      <option value="">Выберите этап</option>
                      {programSteps.map((step) => <option key={step.id} value={step.id}>{step.module_title} · {step.title}</option>)}
                    </select>
                    <select className="rounded-xl border p-3" value={stepMaterialForm.role} onChange={(e) => setStepMaterialForm((prev) => ({ ...prev, role: e.target.value }))}>
                      <option value="primary_lesson">Основной урок</option>
                      <option value="reference">Справочник</option>
                      <option value="practice_template">Шаблон практики</option>
                      <option value="visual_examples">Визуальные примеры</option>
                      <option value="assessment_material">Материал проверки</option>
                    </select>
                    <input className="rounded-xl border p-3" value={stepMaterialForm.order_index} onChange={(e) => setStepMaterialForm((prev) => ({ ...prev, order_index: e.target.value }))} placeholder="Порядок" />
                  </div>
                  <label className="mt-3 flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={stepMaterialForm.required_to_complete} onChange={(e) => setStepMaterialForm((prev) => ({ ...prev, required_to_complete: e.target.checked }))} /> Обязателен для завершения шага</label>
                  <button onClick={attachMaterialToStep} disabled={!selectedMaterial || !stepMaterialForm.program_id || !stepMaterialForm.step_id} className="mt-3 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white disabled:bg-slate-300">Привязать к этапу</button>
                </div>
                <div className="mt-3 rounded-2xl bg-white p-4">
                  <h4 className="font-semibold text-slate-900">AI-слайды материала</h4>
                  <p className="mt-1 text-sm text-slate-500">AI может подготовить draft-слайды из текста материала. Руководитель просматривает, редактирует и публикует каждый слайд отдельно.</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button onClick={() => generateLearningPack(false)} disabled={generatingLearningPack || !selectedMaterial} className="rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm font-semibold text-indigo-800 disabled:bg-slate-100 disabled:text-slate-400">Предпросмотр AI pack</button>
                    <button onClick={() => generateLearningPack(true, false, false)} disabled={generatingLearningPack || !selectedMaterial} className="rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white disabled:bg-slate-300">Добавить AI-слайды</button>
                    <button onClick={() => generateLearningPack(true, false, true)} disabled={generatingLearningPack || !selectedMaterial} className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900 disabled:bg-slate-100 disabled:text-slate-400">Заменить draft-слайды</button>
                    <button onClick={() => generateLearningPack(true, true, false)} disabled={generatingLearningPack || !selectedMaterial} className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-800 disabled:bg-slate-100 disabled:text-slate-400">Полностью перегенерировать</button>
                  </div>
                  {learningPackPreview ? (
                    <div className="mt-4 grid gap-3 lg:grid-cols-[1fr_280px]">
                      <div className="space-y-2">
                        {learningPackPreview.slides.slice(0, 7).map((slide, index) => (
                          <div key={`${slide.title}-${index}`} className="rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
                            <div className="flex items-start justify-between gap-2"><b>{slide.title}</b><span className="rounded-full bg-white px-2 py-1 text-xs">{slide.status}</span></div>
                            {slide.body ? <p className="mt-2 whitespace-pre-wrap">{slide.body}</p> : null}
                            {slide.quiz_question ? <p className="mt-2 rounded-lg bg-white p-2 text-xs text-indigo-700">Самопроверка: {slide.quiz_question}</p> : null}
                            {slide.image_prompt ? <p className="mt-2 text-xs text-slate-400">Visual prompt: {slide.image_prompt}</p> : null}
                          </div>
                        ))}
                      </div>
                      <div className="space-y-2">
                        <div className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900"><b>Практика</b><br />{learningPackPreview.practice.task || 'Будет сформирована после проверки текста.'}</div>
                        <div className="rounded-xl bg-blue-50 p-3 text-sm text-blue-900"><b>Критерии</b><ul className="mt-1 list-disc pl-5">{(learningPackPreview.assessment.criteria || []).map((criterion) => <li key={criterion}>{criterion}</li>)}</ul></div>
                        {learningPackPreview.assessment.question_pool?.length ? (
                          <div className="rounded-xl bg-violet-50 p-3 text-sm text-violet-950">
                            <b>Пул проверочных вопросов · {learningPackPreview.assessment.question_pool.length}</b>
                            <div className="mt-2 max-h-72 space-y-2 overflow-auto">
                              {learningPackPreview.assessment.question_pool.slice(0, 12).map((item, index) => (
                                <div key={`${item.question}-${index}`} className="rounded-lg bg-white/80 p-2">
                                  <div className="text-xs font-bold uppercase tracking-[0.12em] text-violet-500">{item.type || 'question'} · {item.difficulty || 'medium'}</div>
                                  <div className="mt-1 font-semibold">{item.question}</div>
                                  {item.expected_answer ? <div className="mt-1 text-xs text-violet-700">Ожидаем: {item.expected_answer}</div> : null}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                        <div className="rounded-xl bg-amber-50 p-3 text-xs text-amber-900">{learningPackPreview.assessment.manager_review_note || 'Перед публикацией нужна проверка руководителем.'}</div>
                      </div>
                    </div>
                  ) : null}
                  {selectedMaterial.extraction?.learning_pack?.assessment?.question_pool?.length ? (
                    <div className="mt-4 rounded-2xl border border-violet-100 bg-violet-50 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h4 className="font-semibold text-violet-950">Сохранённый пул проверочных вопросов</h4>
                          <p className="mt-1 text-sm text-violet-700">Эти вопросы агент подготовил при последнем применении AI pack. Они хранятся как draft/admin-only и нужны для оценки знания после урока.</p>
                        </div>
                        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-violet-700">{selectedMaterial.extraction.learning_pack.assessment.question_pool.length} вопросов</span>
                      </div>
                      <div className="mt-3 grid gap-2 md:grid-cols-2">
                        {selectedMaterial.extraction.learning_pack.assessment.question_pool.slice(0, 12).map((item, index) => (
                          <div key={`${item.question}-${index}`} className="rounded-xl bg-white p-3 text-sm text-violet-950">
                            <div className="text-xs font-bold uppercase tracking-[0.12em] text-violet-500">{item.type || 'question'} · {item.difficulty || 'medium'}</div>
                            <div className="mt-1 font-semibold">{item.question}</div>
                            {item.expected_answer ? <div className="mt-1 text-xs text-violet-700">Ожидаемый ответ: {item.expected_answer}</div> : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
                <div className="mt-3 rounded-2xl bg-white p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h4 className="font-semibold text-slate-900">Слайдовый формат материала</h4>
                      <p className="mt-1 text-sm text-slate-500">Полноценный редактор: просмотр выбранного слайда, ручное добавление, редактирование и удаление. При публикации всего материала все слайды и прикрепленные фото публикуются автоматически.</p>
                    </div>
                    <button onClick={resetSlideForm} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700">+ Новый слайд вручную</button>
                  </div>
                  {selectedSlide ? (
                    <div className="mt-4 rounded-3xl border border-slate-200 bg-gradient-to-br from-white to-indigo-50 p-5 shadow-sm">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-500">Полный просмотр слайда</div>
                          <h3 className="mt-2 text-2xl font-semibold text-slate-950">{selectedSlide.title}</h3>
                          <div className="mt-2 flex flex-wrap gap-2 text-xs">
                            <span className="rounded-full bg-white px-3 py-1 font-semibold text-slate-600">#{selectedSlide.order_index}</span>
                            <span className="rounded-full bg-indigo-100 px-3 py-1 font-semibold text-indigo-700">{statusLabel(selectedSlide.status)}</span>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button onClick={() => startEditMaterialSlide(selectedSlide)} className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Редактировать</button>
                          <button onClick={() => deleteMaterialSlide(selectedSlide)} className="rounded-xl border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-700">Удалить</button>
                        </div>
                      </div>
                      {selectedSlide.image_url ? <div role="img" aria-label={selectedSlide.title} className="mt-4 h-72 w-full rounded-2xl bg-cover bg-center" style={{ backgroundImage: `url(${selectedSlide.image_url})` }} /> : <div className="mt-4 rounded-2xl border border-dashed border-indigo-200 bg-white/70 p-8 text-center text-sm text-slate-400">Визуал не прикреплен. Можно указать image_url или подготовить prompt для генерации.</div>}
                      {selectedSlide.body ? <div className="mt-4 whitespace-pre-wrap text-base leading-7 text-slate-700">{selectedSlide.body}</div> : null}
                      {selectedSlide.quiz_question ? <div className="mt-4 rounded-2xl bg-white p-4 text-sm font-semibold text-indigo-800">Самопроверка: {selectedSlide.quiz_question}</div> : null}
                      {selectedSlide.speaker_note ? <div className="mt-3 rounded-2xl bg-amber-50 p-4 text-sm text-amber-900"><b>Заметка методиста:</b><br />{selectedSlide.speaker_note}</div> : null}
                      {selectedSlide.image_prompt ? <div className="mt-3 rounded-2xl bg-slate-100 p-4 text-xs text-slate-500"><b>AI visual prompt:</b> {selectedSlide.image_prompt}</div> : null}
                    </div>
                  ) : null}
                  <div className="mt-4 grid gap-2 md:grid-cols-2">
                    <input className="rounded-xl border p-3" value={slideForm.title} onChange={(e) => setSlideForm((prev) => ({ ...prev, title: e.target.value }))} placeholder="Название слайда" />
                    <input className="rounded-xl border p-3" value={slideForm.order_index} onChange={(e) => setSlideForm((prev) => ({ ...prev, order_index: e.target.value }))} placeholder="Порядок" />
                    <textarea className="h-24 rounded-xl border p-3 md:col-span-2" value={slideForm.body} onChange={(e) => setSlideForm((prev) => ({ ...prev, body: e.target.value }))} placeholder="Текст слайда для продавца" />
                    <input className="rounded-xl border p-3" value={slideForm.image_url} onChange={(e) => setSlideForm((prev) => ({ ...prev, image_url: e.target.value }))} placeholder="image_url / ссылка на визуал" />
                    <input className="rounded-xl border p-3" value={slideForm.image_prompt} onChange={(e) => setSlideForm((prev) => ({ ...prev, image_prompt: e.target.value }))} placeholder="prompt для будущей генерации визуала" />
                    <textarea className="h-20 rounded-xl border p-3" value={slideForm.speaker_note} onChange={(e) => setSlideForm((prev) => ({ ...prev, speaker_note: e.target.value }))} placeholder="Заметка руководителя / методиста, продавцу не видна" />
                    <textarea className="h-20 rounded-xl border p-3" value={slideForm.quiz_question} onChange={(e) => setSlideForm((prev) => ({ ...prev, quiz_question: e.target.value }))} placeholder="Вопрос самопроверки" />
                    <select className="rounded-xl border p-3" value={slideForm.status} onChange={(e) => setSlideForm((prev) => ({ ...prev, status: e.target.value }))}>
                      <option value="draft">Черновик</option>
                      <option value="review">На проверке</option>
                      <option value="published">Опубликован продавцу</option>
                    </select>
                    <button onClick={saveMaterialSlide} disabled={!selectedMaterial || !slideForm.title.trim()} className="rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white disabled:bg-slate-300">{editingSlideId ? 'Сохранить слайд' : 'Добавить слайд'}</button>
                  </div>
                  <div className="mt-4 grid gap-2 md:grid-cols-2">
                    {materialSlides.map((slide) => (
                      <div key={slide.id} onClick={() => setSelectedSlideId(slide.id)} className={`cursor-pointer rounded-xl border p-3 text-sm transition ${selectedSlide?.id === slide.id ? 'border-indigo-300 bg-indigo-50 text-slate-900' : 'border-slate-100 bg-slate-50 text-slate-700 hover:bg-white'}`}>
                        <div className="flex items-start justify-between gap-2"><b>{slide.title}</b><span className="rounded-full bg-white px-2 py-1 text-xs">{slide.status}</span></div>
                        {slide.body ? <p className="mt-2 line-clamp-3 whitespace-pre-wrap">{slide.body}</p> : null}
                        {slide.quiz_question ? <p className="mt-2 rounded-lg bg-white p-2 text-xs text-indigo-700">Проверка: {slide.quiz_question}</p> : null}
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button type="button" onClick={(event) => { event.stopPropagation(); setSelectedSlideId(slide.id); }} className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-semibold text-slate-600">Смотреть</button>
                          <button type="button" onClick={(event) => { event.stopPropagation(); startEditMaterialSlide(slide); }} className="rounded-lg bg-slate-900 px-2 py-1 text-xs font-semibold text-white">Редактировать</button>
                          <button type="button" onClick={(event) => { event.stopPropagation(); deleteMaterialSlide(slide); }} className="rounded-lg bg-red-50 px-2 py-1 text-xs font-semibold text-red-700">Удалить</button>
                        </div>
                      </div>
                    ))}
                    {!materialSlides.length ? <div className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">Слайдов пока нет. Материал будет показываться как Markdown.</div> : null}
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button onClick={() => saveMaterialEditor()} disabled={savingMaterial || !materialEditorForm.title.trim() || !materialEditorForm.markdown_content.trim()} className="rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white disabled:bg-slate-300">Сохранить</button>
                  <button onClick={() => saveMaterialEditor('review')} disabled={savingMaterial} className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700">На проверку</button>
                  <button onClick={() => saveMaterialEditor('published')} disabled={savingMaterial} className="rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white disabled:bg-slate-300">Опубликовать всё: материал, слайды, фото</button>
                  <button onClick={() => saveMaterialEditor('archived')} disabled={savingMaterial} className="rounded-xl bg-slate-200 px-4 py-3 text-sm font-semibold text-slate-700">В архив</button>
                  <button onClick={() => selectedMaterial && deleteTrainingMaterial(selectedMaterial)} disabled={savingMaterial || deletingMaterialId === selectedMaterial.id} className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-800 disabled:bg-slate-100 disabled:text-slate-400">Удалить полностью</button>
                </div>
              </div>
            ) : null}
            <div className="md:col-span-2 grid self-start gap-2 md:grid-cols-3">
              <input className="h-10 rounded-xl border px-3 py-2 text-sm" placeholder="Поиск по библиотеке" value={materialSearch} onChange={(e) => setMaterialSearch(e.target.value)} />
              <select className="h-10 rounded-xl border px-3 py-2 text-sm" value={materialTopicFilter} onChange={(e) => setMaterialTopicFilter(e.target.value)}>
                <option value="">Все темы</option>
                {materialTopics.map((topic) => <option key={topic} value={topic}>{topic}</option>)}
              </select>
              <select className="h-10 rounded-xl border px-3 py-2 text-sm" value={materialStatusFilter} onChange={(e) => setMaterialStatusFilter(e.target.value)}>
                <option value="">Все статусы</option>
                <option value="draft">Черновики</option>
                <option value="review">На проверке</option>
                <option value="published">Опубликованные</option>
                <option value="archived">Архив</option>
              </select>
            </div>
            {visibleTrainingMaterials.slice(0, 12).map((material) => (
              <article key={material.id} className="rounded-2xl border border-slate-200 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-900">{material.title}</div>
                    <div className="mt-1 text-sm text-slate-500">{material.topic} · {material.category}</div>
                    <div className="mt-1 text-xs font-semibold text-indigo-700">📁 {programs.find((program) => program.code === material.program_code)?.title || material.program_code || 'Без программы'}</div>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-500">{material.status}</span>
                </div>
                <p className="mt-3 line-clamp-3 whitespace-pre-wrap text-sm text-slate-600">{material.markdown_content}</p>
                {(material.source_file?.filename || material.extraction?.filename) ? (
                  <div className="mt-3 rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
                    <span className="font-semibold text-slate-800">Исходник:</span> {material.source_file?.filename || material.extraction?.filename}
                    {material.source_file?.has_content ? <span className="ml-2 rounded-full bg-emerald-100 px-2 py-1 text-emerald-700">прикреплен</span> : <span className="ml-2 rounded-full bg-amber-100 px-2 py-1 text-amber-700">только имя файла</span>}
                  </div>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-2">
                  <button onClick={() => openMaterialEditor(material)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700">Открыть / редактировать</button>
                  {material.status !== 'published' ? <button onClick={() => publishTrainingMaterial(material)} className="rounded-xl bg-emerald-600 px-3 py-2 text-sm font-semibold text-white">Опубликовать</button> : null}
                  <button onClick={() => deleteTrainingMaterial(material)} disabled={deletingMaterialId === material.id} className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700 disabled:bg-slate-100 disabled:text-slate-400">Удалить</button>
                </div>
              </article>
            ))}
            {!visibleTrainingMaterials.length ? <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-500">Материалы не найдены. Измените поиск или добавьте первый .md материал.</div> : null}
          </div>
        </div>
      </section>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Программы обучения · аналитика</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-900">Назначения, прохождение и понимание тем</h2>
            <p className="mt-1 text-sm text-slate-500">Руководитель видит не прогресс загруженного файла, а реальное состояние программ: кто подписан, кто сейчас проходит, кто завершил и какой средний результат понимания.</p>
          </div>
          <div className={`rounded-2xl px-4 py-3 text-sm font-semibold ${materialProgressAnalytics?.summary.blocked_materials ? 'bg-red-50 text-red-800' : 'bg-emerald-50 text-emerald-800'}`}>
            {materialProgressAnalytics?.summary.blocked_materials || 0} блокировок
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-5">
          {[
            ['Подписаны на программы', materialProgressAnalytics?.summary.program_subscribed_sellers || 0],
            ['Сейчас проходят', materialProgressAnalytics?.summary.program_in_progress_sellers || 0],
            ['Завершили программы', materialProgressAnalytics?.summary.program_completed_sellers || 0],
            ['Среднее понимание', materialProgressAnalytics?.summary.average_understanding_percent == null ? '—' : `${materialProgressAnalytics.summary.average_understanding_percent}%`],
            ['Опубликовано материалов', materialProgressAnalytics?.summary.published_materials || 0],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-2xl bg-slate-50 p-4">
              <div className="text-xs text-slate-500">{label}</div>
              <div className="mt-1 text-xl font-semibold text-slate-900">{value}</div>
            </div>
          ))}
        </div>
        <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_320px]">
          <div className="space-y-3">
            {(materialProgressAnalytics?.programs || []).map((program) => {
              const subscribed = program.subscribed_sellers || 0;
              const completedPercent = subscribed ? Math.round((program.completed_sellers / subscribed) * 100) : 0;
              const inProgressPercent = subscribed ? Math.round((program.in_progress_sellers / subscribed) * 100) : 0;
              const subscribersOpen = selectedProgramSubscribersId === program.program_id;
              return (
                <article key={program.program_id} className={`rounded-2xl border p-4 ${program.attention_level === 'high' ? 'border-red-100 bg-red-50' : program.attention_level === 'medium' ? 'border-amber-100 bg-amber-50' : 'border-slate-200 bg-white'}`}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-slate-900">{program.title || 'Программа без названия'}</div>
                      <div className="text-sm text-slate-500">{program.code || 'без кода'} · материалов {program.published_materials}</div>
                    </div>
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${program.attention_level === 'high' ? 'bg-red-100 text-red-800' : program.attention_level === 'medium' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}`}>
                      {program.attention_level === 'high' ? 'требует запуска' : program.attention_level === 'medium' ? 'наблюдать' : 'норма'}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-2 text-sm md:grid-cols-4">
                    <button
                      type="button"
                      onClick={() => setSelectedProgramSubscribersId(subscribersOpen ? null : program.program_id)}
                      className={`rounded-xl p-3 text-left transition ${subscribersOpen ? 'bg-indigo-600 text-white shadow-sm' : 'bg-white/70 hover:bg-white'}`}
                    >
                      <span className={subscribersOpen ? 'text-indigo-100' : 'text-slate-600'}>Подписаны:</span> <b>{program.subscribed_sellers}</b>
                      <span className="mt-1 block text-xs opacity-80">открыть список</span>
                    </button>
                    <div className="rounded-xl bg-white/70 p-3">Проходят: <b>{program.in_progress_sellers}</b></div>
                    <div className="rounded-xl bg-white/70 p-3">Завершили: <b>{program.completed_sellers}</b></div>
                    <div className="rounded-xl bg-white/70 p-3">Понимание: <b>{program.average_understanding_percent == null ? '—' : `${program.average_understanding_percent}%`}</b></div>
                  </div>
                  <div className="mt-3 h-3 overflow-hidden rounded-full bg-white/80">
                    <div className="flex h-full w-full">
                      <div className="h-full bg-emerald-500" style={{ width: `${Math.min(completedPercent, 100)}%` }} />
                      <div className="h-full bg-blue-500" style={{ width: `${Math.min(inProgressPercent, Math.max(0, 100 - completedPercent))}%` }} />
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
                    <span><b className="text-emerald-600">■</b> завершили {completedPercent}%</span>
                    <span><b className="text-blue-600">■</b> проходят {inProgressPercent}%</span>
                    <span><b className="text-slate-300">■</b> не стартовали/нет статуса {Math.max(0, 100 - completedPercent - inProgressPercent)}%</span>
                  </div>
                  {subscribersOpen ? (
                    <div className="mt-4 rounded-2xl border border-indigo-100 bg-white/90 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <h4 className="text-sm font-semibold text-slate-900">Подписанные продавцы</h4>
                          <p className="text-xs text-slate-500">Можно исключить продавца из курса без удаления истории прохождения.</p>
                        </div>
                        <button type="button" onClick={() => setSelectedProgramSubscribersId(null)} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">закрыть</button>
                      </div>
                      <div className="mt-3 space-y-2">
                        {selectedProgramSubscribers.map(({ user, assignment }) => (
                          <div key={assignment.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 p-3 text-sm">
                            <div>
                              <div className="font-semibold text-slate-900">{user.full_name || user.email || 'Сотрудник без имени'}</div>
                              <div className="text-xs text-slate-500">
                                {user.email || user.role || 'аккаунт обучения'} · {statusLabel(assignment.status)}
                                {assignment.average_score != null ? ` · понимание ${assignment.average_score}` : ''}
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={() => unassignTrainingProgram(assignment, user, program.title)}
                              disabled={excludingEnrollmentId === assignment.id}
                              className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 disabled:bg-slate-100 disabled:text-slate-400"
                            >
                              {excludingEnrollmentId === assignment.id ? 'Исключаем…' : 'Исключить с курса'}
                            </button>
                          </div>
                        ))}
                        {!selectedProgramSubscribers.length ? <div className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">Активных подписчиков по этой программе не найдено.</div> : null}
                      </div>
                    </div>
                  ) : null}
                  <p className="mt-3 text-sm text-slate-700"><b>Действие:</b> {program.manager_action}</p>
                </article>
              );
            })}
            {!materialProgressAnalytics?.programs?.length ? <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-500">Пока нет программ или назначений. После назначения продавцов здесь появится аналитика по каждой программе.</div> : null}
          </div>
          <div className="space-y-3">
            {(materialProgressAnalytics?.recommendations || []).map((item) => (
              <div key={`${item.type}-${item.title}`} className="rounded-2xl bg-blue-50 p-4 text-sm text-blue-900"><b>{item.title}</b><br />{item.text}</div>
            ))}
            <div className="rounded-2xl bg-slate-50 p-4 text-xs leading-5 text-slate-500">Логика: блок считает назначения из consultant_training_enrollments. «Подписаны» — все продавцы с назначенной программой, «проходят» — назначение активно, «завершили» — completed/certified или есть completed_at. Среднее понимание берется из average_score назначения и оценок ответов по этапам.</div>
          </div>
        </div>
      </section>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Управленческая аналитика</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-900">Пульс обучения и риски запуска</h2>
          </div>
          <div className="rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white">{trainingAnalytics?.summary.active_learners || 0} сотрудников</div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          {[
            ['На проверке', trainingAnalytics?.summary.pending_reviews || 0],
            ['Доработки', trainingAnalytics?.summary.revision_count || 0],
            ['Без прогресса', trainingAnalytics?.summary.zero_progress || 0],
            ['Готовы к аттестации', trainingAnalytics?.summary.attestation_ready || 0],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-2xl bg-slate-50 p-4">
              <div className="text-sm text-slate-500">{label}</div>
              <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
            </div>
          ))}
        </div>
        <div className="mt-5 grid gap-4 lg:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 p-4">
            <h3 className="font-semibold text-slate-900">Heatmap слабых компетенций</h3>
            <div className="mt-3 space-y-2">
              {(trainingAnalytics?.competency_heatmap || []).slice(0, 5).map((item) => (
                <div key={item.code}>
                  <div className="flex justify-between text-sm"><span>{item.label}</span><span>{item.risk_count} риск.</span></div>
                  <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-amber-500" style={{ width: `${Math.min(100 - item.average_percent, 100)}%` }} /></div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-2xl border border-slate-200 p-4">
            <h3 className="font-semibold text-slate-900">Этапы-бутылочные горлышки</h3>
            <div className="mt-3 space-y-2">
              {(trainingAnalytics?.submission_bottlenecks || []).slice(0, 5).map((item) => (
                <div key={item.step_title} className="rounded-xl bg-slate-50 p-3 text-sm text-slate-700">{item.step_title}: {item.pending_or_revision} на проверке/доработке</div>
              ))}
            </div>
          </div>
          <div className="rounded-2xl border border-slate-200 p-4">
            <h3 className="font-semibold text-slate-900">AI-рекомендации руководителю</h3>
            <div className="mt-3 space-y-2">
              {(trainingAnalytics?.recommendations || []).map((item) => (
                <div key={`${item.type}-${item.title}`} className="rounded-xl bg-blue-50 p-3 text-sm text-blue-900"><b>{item.title}</b><br />{item.text}</div>
              ))}
              {!trainingAnalytics?.recommendations?.length ? <p className="text-sm text-slate-500">Критичных рекомендаций пока нет.</p> : null}
            </div>
          </div>
        </div>
        {trainingAnalytics?.risk_sellers?.length ? (
          <div className="mt-5 rounded-2xl bg-red-50 p-4">
            <h3 className="font-semibold text-red-900">Сотрудники в зоне внимания</h3>
            <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {trainingAnalytics.risk_sellers.slice(0, 6).map((item, index) => (
                <div key={`${item.seller?.email || index}`} className="rounded-xl bg-white p-3 text-sm text-red-900">
                  <b>{item.seller?.full_name || item.seller?.email || 'Сотрудник'}</b><br />{item.completed_steps}/{item.total_steps} этапов
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Обучение ↔ KPI</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-900">Как обучение влияет на план, чек и смены</h2>
            <p className="mt-1 text-sm text-slate-500">Это управленческие гипотезы: проверяем через ближайшие смены и динамику KPI, не выдаем как доказанную причинность.</p>
          </div>
          <div className="rounded-2xl bg-blue-50 px-4 py-3 text-sm font-semibold text-blue-900">
            {trainingAnalytics?.kpi_linkage?.summary.matched_sellers || 0} связок с KPI
          </div>
        </div>
        {trainingAnalytics?.kpi_linkage?.error ? (
          <div className="mt-4 rounded-2xl bg-amber-50 p-4 text-sm text-amber-800">{trainingAnalytics.kpi_linkage.error}</div>
        ) : (
          <>
            <div className="mt-4 grid gap-3 md:grid-cols-4">
              {[
                ['Низкое обучение + слабый KPI', trainingAnalytics?.kpi_linkage?.summary.low_kpi_and_low_training ?? 0],
                ['KPI при низком обучении', `${trainingAnalytics?.kpi_linkage?.summary.avg_completion_low_training ?? '—'}%`],
                ['KPI у обученных', `${trainingAnalytics?.kpi_linkage?.summary.avg_completion_trained ?? '—'}%`],
                ['Месяц KPI', trainingAnalytics?.kpi_linkage?.month?.slice(0, 7) || month],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-2xl bg-slate-50 p-4">
                  <div className="text-sm text-slate-500">{label}</div>
                  <div className="mt-1 text-xl font-semibold text-slate-900">{value}</div>
                </div>
              ))}
            </div>
            <div className="mt-5 grid gap-4 lg:grid-cols-3">
              <div className="space-y-3 lg:col-span-2">
                {(trainingAnalytics?.kpi_linkage?.seller_actions || []).slice(0, 6).map((item, index) => (
                  <article key={`${item.seller?.email || item.seller?.full_name || index}`} className="rounded-2xl border border-slate-200 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold text-slate-900">{item.seller?.full_name || item.seller?.email || 'Сотрудник'}</div>
                        <div className="text-sm text-slate-500">{item.store_name || 'магазин не указан'} · {item.training.level || 'уровень не указан'} · обучение {item.training.percent}%</div>
                      </div>
                      <span className={`rounded-full px-3 py-1 text-xs font-semibold ${item.priority === 'high' ? 'bg-red-50 text-red-800' : 'bg-amber-50 text-amber-800'}`}>{item.priority === 'high' ? 'высокий приоритет' : 'наблюдать'}</span>
                    </div>
                    <div className="mt-3 grid gap-2 text-sm md:grid-cols-3">
                      <div className="rounded-xl bg-slate-50 p-3">План: {item.kpi.completion_percent ?? '—'}%</div>
                      <div className="rounded-xl bg-slate-50 p-3">Средний чек: {item.kpi.avg_check ?? '—'}</div>
                      <div className="rounded-xl bg-slate-50 p-3">Изделий/чек: {item.kpi.items_per_check ?? '—'}</div>
                    </div>
                    <div className="mt-3 rounded-xl bg-blue-50 p-3 text-sm text-blue-900"><b>Учебный фокус:</b> {item.recommended_training_focus}<br /><b>Действие:</b> {item.manager_action}</div>
                    {item.kpi_weaknesses?.length ? <div className="mt-2 flex flex-wrap gap-1">{item.kpi_weaknesses.map((weakness) => <span key={weakness} className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">{weakness}</span>)}</div> : null}
                  </article>
                ))}
                {!trainingAnalytics?.kpi_linkage?.seller_actions?.length ? <p className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-500">Пока нет продавцов, где обучение и KPI сопоставились как зона риска.</p> : null}
              </div>
              <div className="space-y-3">
                {(trainingAnalytics?.kpi_linkage?.recommendations || []).map((item) => (
                  <div key={`${item.type}-${item.title}`} className="rounded-2xl bg-emerald-50 p-4 text-sm text-emerald-900"><b>{item.title}</b><br />{item.text}</div>
                ))}
                {trainingAnalytics?.kpi_linkage?.note ? <div className="rounded-2xl bg-slate-50 p-4 text-xs text-slate-500">{trainingAnalytics.kpi_linkage.note}</div> : null}
              </div>
            </div>
          </>
        )}
      </section>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Карьерные уровни</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-900">Карьерные уровни и зарплатная политика</h2>
            <p className="mt-1 text-sm text-slate-500">Уровень складывается из знаний, достижений, аттестаций, реальных продаж и KPI. Зарплатная связь не применяется автоматически.</p>
          </div>
          <div className="rounded-2xl bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">Требует утверждения руководством</div>
        </div>
        {careerLevels?.kpi_error ? <div className="mt-4 rounded-2xl bg-amber-50 p-4 text-sm text-amber-800">{careerLevels.kpi_error}</div> : null}
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          {[
            ['Продавцов', careerLevels?.summary.total_sellers || 0],
            ['Средний индекс роста', careerLevels?.summary.average_score || 0],
            ['Нужен фокус', careerLevels?.summary.attention_count || 0],
            ['Месяц KPI', careerLevels?.month || month],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-2xl bg-slate-50 p-4">
              <div className="text-sm text-slate-500">{label}</div>
              <div className="mt-1 text-xl font-semibold text-slate-900">{value}</div>
            </div>
          ))}
        </div>
        <div className="mt-5 grid gap-4 lg:grid-cols-[280px_1fr]">
          <div className="rounded-2xl border border-slate-200 p-4">
            <h3 className="font-semibold text-slate-900">Распределение по уровням</h3>
            <div className="mt-3 space-y-2">
              {Object.entries(careerLevels?.summary.level_distribution || {}).map(([level, count]) => (
                <div key={level}>
                  <div className="flex justify-between text-sm"><span>{level}</span><span>{count}</span></div>
                  <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-slate-900" style={{ width: `${Math.min(100, Number(count) * 12)}%` }} /></div>
                </div>
              ))}
              {!Object.keys(careerLevels?.summary.level_distribution || {}).length ? <p className="text-sm text-slate-500">Данных по уровням пока нет.</p> : null}
            </div>
            <p className="mt-4 rounded-xl bg-amber-50 p-3 text-xs text-amber-900">{careerLevels?.salary_policy.description || 'Связь уровня с зарплатой будет включена только после утверждения правил.'}</p>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {(careerLevels?.sellers || []).slice(0, 9).map((item, index) => (
              <article key={`${item.seller?.email || index}`} className="rounded-2xl border border-slate-200 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-slate-900">{item.seller?.full_name || item.seller?.email || 'Сотрудник'}</div>
                    <div className="mt-1 text-sm text-slate-500">{item.career_level.current_level.title} · индекс {item.career_level.current_level.score}</div>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">→ {item.career_level.next_level?.title || 'верхний уровень'}</span>
                </div>
                <div className="mt-3 grid gap-2 text-xs text-slate-600">
                  {Object.entries(item.career_level.score_breakdown || {}).map(([label, value]) => (
                    <div key={label} className="rounded-xl bg-slate-50 p-2">{label}: <b>{value}</b></div>
                  ))}
                </div>
                <div className="mt-3 rounded-xl bg-blue-50 p-3 text-sm text-blue-900"><b>Действие руководителя:</b> {item.manager_next_action}</div>
                <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-500">
                  {(item.career_level.requirements_to_next_level || []).slice(0, 3).map((requirement) => <li key={requirement}>{requirement}</li>)}
                </ul>
              </article>
            ))}
            {!careerLevels?.sellers?.length ? <p className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-500">Карьерные уровни появятся после перезапуска backend и загрузки данных обучения/KPI.</p> : null}
          </div>
        </div>
      </section>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Сопоставление 1C ↔ обучение</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-900">Диагностика аккаунтов продавцов</h2>
            <p className="mt-1 text-sm text-slate-500">Проверяем, у каких KPI-продавцов есть связанный user account для обучения. Совпадение по имени — временный мост, надежный ключ — seller_external_id.</p>
          </div>
          <div className={`rounded-2xl px-4 py-3 text-sm font-semibold ${accountMatching?.summary.unresolved ? 'bg-amber-50 text-amber-800' : 'bg-emerald-50 text-emerald-800'}`}>
            {accountMatching?.summary.unresolved || 0} не связано
          </div>
        </div>
        {accountMatching?.error ? <div className="mt-4 rounded-2xl bg-amber-50 p-4 text-sm text-amber-800">{accountMatching.error}</div> : null}
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          {[
            ['KPI-продавцы', accountMatching?.summary.total_kpi_sellers || 0],
            ['Связаны по ID', accountMatching?.summary.matched_by_external_id || 0],
            ['Связаны по имени', accountMatching?.summary.matched_by_name || 0],
            ['Аккаунты без KPI', accountMatching?.summary.training_only || 0],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-2xl bg-slate-50 p-4">
              <div className="text-sm text-slate-500">{label}</div>
              <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
            </div>
          ))}
        </div>
        <div className="mt-5 grid gap-4 lg:grid-cols-3">
          <div className="space-y-2 lg:col-span-2">
            <h3 className="font-semibold text-slate-900">Несопоставленные KPI-продавцы</h3>
            {(accountMatching?.unresolved || []).slice(0, 8).map((item) => {
              const key = `${item.seller_external_id || item.seller_name}-${item.store_name}`;
              return (
                <div key={key} className="rounded-2xl border border-amber-100 bg-amber-50 p-4 text-sm text-amber-900">
                  <b>{item.seller_name || 'Без имени'}</b> · {item.store_name || 'магазин не указан'}<br />1C ID: {item.seller_external_id || '—'} · причина: {item.reason || 'нет связи'}
                  <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                    <select
                      className="min-w-0 flex-1 rounded-xl border border-amber-200 bg-white px-3 py-2 text-sm text-slate-800"
                      value={linkSelections[key] || ''}
                      onChange={(event) => setLinkSelections((prev) => ({ ...prev, [key]: event.target.value }))}
                    >
                      <option value="">Выбрать аккаунт сотрудника…</option>
                      {(accountMatching?.training_only || []).map((user) => (
                        <option key={user.id} value={user.id}>{user.full_name || user.email || user.id} · {user.role || 'role?'}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      disabled={!item.seller_external_id || !linkSelections[key] || linkingKey === key}
                      onClick={() => linkTrainingAccount(item)}
                      className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                    >
                      {linkingKey === key ? 'Связываю…' : 'Связать'}
                    </button>
                  </div>
                </div>
              );
            })}
            {!accountMatching?.unresolved?.length ? <p className="rounded-2xl bg-emerald-50 p-4 text-sm text-emerald-800">Все KPI-продавцы сопоставлены с аккаунтами обучения.</p> : null}
          </div>
          <div className="space-y-3">
            {(accountMatching?.recommendations || []).map((item) => (
              <div key={`${item.type}-${item.title}`} className="rounded-2xl bg-blue-50 p-4 text-sm text-blue-900"><b>{item.title}</b><br />{item.text}</div>
            ))}
            {(accountMatching?.matches || []).filter((item) => item.match_type === 'name_fallback').slice(0, 4).map((item) => (
              <div key={`${item.kpi_seller.seller_external_id || item.kpi_seller.seller_name}-${item.user.id}`} className="rounded-2xl bg-slate-50 p-4 text-xs text-slate-600">
                Name fallback: <b>{item.kpi_seller.seller_name}</b> → {item.user.full_name || item.user.email}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Командная аттестация</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-900">Компетенции и уровни продавцов</h2>
          </div>
          <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">Сотрудников: {teamCompetencies?.sellers?.length || 0}</div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {(teamCompetencies?.team_competencies || []).map((competency) => (
            <div key={competency.code} className="rounded-2xl border border-slate-200 p-4">
              <div className="text-sm font-semibold text-slate-900">{competency.label}</div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-slate-900" style={{ width: `${Math.min(competency.percent, 100)}%` }} /></div>
              <div className="mt-2 text-xs text-slate-500">{competency.accepted_steps}/{competency.total_steps} · {competency.percent}%</div>
            </div>
          ))}
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(teamCompetencies?.sellers || []).slice(0, 9).map((item, index) => (
            <div key={`${item.seller?.email || index}`} className="rounded-2xl bg-slate-50 p-4">
              <div className="font-semibold text-slate-900">{item.seller?.full_name || item.seller?.email || 'Сотрудник'}</div>
              <div className="mt-1 text-sm text-slate-500">{item.profile.level} · {item.profile.completed_steps}/{item.profile.total_steps} этапов · {item.profile.attestation_ready ? 'готов к аттестации' : 'в обучении'}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">AI-наставник: вопросы продавцов</h2>
        <p className="mt-1 text-sm text-slate-500">Видимость для руководителя: где продавцы просят помощь, какие темы вызывают трудности, где AI отметил риск manager review.</p>
        <div className="mt-4 space-y-3">
          {mentorMessages.length === 0 ? <p className="text-slate-500">Вопросов наставнику пока нет.</p> : null}
          {mentorMessages.map((item) => (
            <article key={item.id} className="rounded-2xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="font-semibold text-slate-900">{item.seller?.full_name || item.seller?.email || 'Сотрудник'}</div>
                  <div className="text-sm text-slate-500">{item.context?.program_title || 'Программа'} {item.context?.step_title ? `· ${item.context.step_title}` : ''}</div>
                </div>
                {item.risk_flags?.length ? <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">нужен контроль руководителя</span> : null}
              </div>
              {item.question_text ? <p className="mt-3 rounded-xl bg-slate-50 p-3 text-sm text-slate-700">Вопрос: {item.question_text}</p> : null}
              <p className="mt-2 rounded-xl bg-blue-50 p-3 text-sm text-blue-800">Ответ AI: {item.response_text}</p>
              {item.context?.focus_tags?.length ? <div className="mt-2 flex flex-wrap gap-1">{item.context.focus_tags.map((tag) => <span key={tag} className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-500">{tag}</span>)}</div> : null}
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">Рефлексии после смен</h2>
        <p className="mt-1 text-sm text-slate-500">Сигналы для coaching: сложные клиентские сценарии, запросы помощи, возражения по цене и слабые GLAME-аргументы.</p>
        <div className="mt-4 space-y-3">
          {shiftReflections.length === 0 ? <p className="text-slate-500">Рефлексий после смен пока нет.</p> : null}
          {shiftReflections.slice(0, 10).map((item) => (
            <article key={item.id} className="rounded-2xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="font-semibold text-slate-900">{item.seller?.full_name || item.seller?.email || 'Сотрудник'}</div>
                  <div className="text-sm text-slate-500">{item.shift_date || 'дата не указана'} {item.store_name ? `· ${item.store_name}` : ''} · {item.status} · AI {item.ai_score ?? '—'}/10</div>
                </div>
                {item.risk_flags?.length ? <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">нужен coaching</span> : null}
              </div>
              {item.reflection_payload?.worked_well ? <p className="mt-3 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900">Получилось: {item.reflection_payload.worked_well}</p> : null}
              {item.reflection_payload?.difficult_scenario ? <p className="mt-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Сложность: {item.reflection_payload.difficult_scenario}</p> : null}
              {item.manager_note ? <p className="mt-2 rounded-xl bg-blue-50 p-3 text-sm text-blue-800">AI для руководителя: {item.manager_note}</p> : null}
              {item.risk_flags?.length ? <div className="mt-2 flex flex-wrap gap-1">{item.risk_flags.map((flag) => <span key={flag} className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-500">{flag}</span>)}</div> : null}
              {item.risk_flags?.length ? <button onClick={() => createCoachingFromReflection(item)} className="mt-3 rounded-xl bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Создать coaching-задачу</button> : null}
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">Coaching loop руководителя</h2>
        <p className="mt-1 text-sm text-slate-500">Планирование и закрытие коротких разборов после смен: тема, скрипт руководителя, следующий шаг продавца.</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {coachingActions.length === 0 ? <p className="text-slate-500">Активных coaching-задач пока нет.</p> : null}
          {coachingActions.slice(0, 12).map((action) => (
            <article key={action.id} className="rounded-2xl border border-slate-200 p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-semibold text-slate-900">{action.seller?.full_name || action.seller?.email || 'Сотрудник'}</div>
                  <div className="text-sm text-slate-500">{action.status} {action.planned_for ? `· ${action.planned_for}` : ''} {action.store_name ? `· ${action.store_name}` : ''}</div>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-500">{action.kpi_metric || action.competency || 'coaching'}</span>
              </div>
              <h3 className="mt-3 font-semibold text-slate-900">{action.coaching_topic}</h3>
              {action.manager_script ? <p className="mt-2 rounded-xl bg-blue-50 p-3 text-sm text-blue-800">Скрипт: {action.manager_script}</p> : null}
              {action.seller_next_step ? <p className="mt-2 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900">Шаг продавцу: {action.seller_next_step}</p> : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <button onClick={() => updateCoachingStatus(action, 'planned')} className="rounded-xl bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-700">Запланировано</button>
                <button onClick={() => updateCoachingStatus(action, 'discussed')} className="rounded-xl bg-amber-100 px-3 py-2 text-xs font-semibold text-amber-800">Обсуждено</button>
                <button onClick={() => updateCoachingStatus(action, 'resolved')} className="rounded-xl bg-emerald-600 px-3 py-2 text-xs font-semibold text-white">Закрыть</button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">Аттестации</h2>
        <p className="mt-1 text-sm text-slate-500">Финальное решение принимает руководитель. AI-оценка — только черновик.</p>
        <div className="mt-4 space-y-3">
          {attestations.length === 0 ? <p className="text-slate-500">Аттестаций пока нет.</p> : null}
          {attestations.map((attestation) => (
            <article key={attestation.id} className="rounded-2xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-semibold text-slate-900">{attestation.seller?.full_name || attestation.seller?.email || 'Сотрудник'}</div>
                  <div className="text-sm text-slate-500">{attestation.attestation_type} · {attestation.status} · AI {attestation.ai_score ?? '—'}/10 · уровень {attestation.certified_level || attestation.recommended_level || '—'}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => reviewAttestation(attestation, 'passed')} className="rounded-xl bg-emerald-600 px-3 py-2 text-sm font-semibold text-white">Сертифицировать</button>
                  <button onClick={() => reviewAttestation(attestation, 'revision_requested')} className="rounded-xl bg-amber-100 px-3 py-2 text-sm font-semibold text-amber-800">Доработать</button>
                  <button onClick={() => reviewAttestation(attestation, 'failed')} className="rounded-xl bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">Не сдано</button>
                </div>
              </div>
              {attestation.ai_evaluation?.review_comment ? <p className="mt-3 rounded-xl bg-blue-50 p-3 text-sm text-blue-800">AI: {attestation.ai_evaluation.review_comment}</p> : null}
            </article>
          ))}
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        {programs.map((program) => (
          <article key={program.id} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Программа обучения</p>
                <h2 className="mt-2 text-xl font-semibold text-slate-900">{program.title}</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">{program.description || 'Описание будет добавлено в конструкторе программ.'}</p>
              </div>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">{program.status}</span>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-500">
              <span className="rounded-full bg-slate-50 px-3 py-1">{program.code}</span>
              <span className="rounded-full bg-slate-50 px-3 py-1">{program.program_type}</span>
              <span className="rounded-full bg-slate-50 px-3 py-1">{program.is_required ? 'обязательная' : 'дополнительная'}</span>
            </div>
            <button onClick={() => openProgramStructure(program)} className="mt-4 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">Открыть этапы</button>
          </article>
        ))}
      </section>

      {programDetail ? (
        <section className="rounded-3xl bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Структура программы</p>
              <h2 className="mt-1 text-xl font-semibold text-slate-900">{programDetail.program.title}</h2>
            </div>
            <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">{programDetail.progress.completed_steps}/{programDetail.progress.total_steps} этапов</div>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {programDetail.modules.map((module) => (
              <article key={module.id} className="rounded-2xl border border-slate-200 p-4">
                <h3 className="font-semibold text-slate-900">{module.title}</h3>
                {module.description ? <p className="mt-1 text-sm text-slate-500">{module.description}</p> : null}
                <div className="mt-3 space-y-2">
                  {module.steps.map((step) => (
                    <div key={step.id} className="rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
                      <div className="font-medium text-slate-900">{step.title}</div>
                      <div className="mt-1 text-xs text-slate-500">{step.status} {step.competencies?.length ? `· ${step.competencies.join(' · ')}` : ''}</div>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section className="grid gap-6 lg:grid-cols-[380px_1fr]">
        <div className="rounded-3xl bg-white p-5 shadow-sm">
          <h2 className="text-xl font-semibold text-slate-900">Тема на согласование</h2>
          <p className="mt-1 text-sm text-slate-500">Каждый день в 09:00 здесь должна быть тема на завтра.</p>
          {tomorrowTopic ? (
            <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
              <div className="text-sm text-amber-700">Тема на завтра уже есть</div>
              <div className="mt-1 font-semibold text-slate-900">{tomorrowTopic.title}</div>
              <div className="mt-1 text-sm text-slate-600">{statusLabel(tomorrowTopic.status)}</div>
            </div>
          ) : null}
          <div className="mt-4 space-y-3">
            <input className="w-full rounded-xl border p-3" type="date" value={form.lesson_date} onChange={(e) => setForm({ ...form, lesson_date: e.target.value })} />
            <input className="w-full rounded-xl border p-3" placeholder="Название дня" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <input className="w-full rounded-xl border p-3" placeholder="Тема дня" value={form.theme} onChange={(e) => setForm({ ...form, theme: e.target.value })} />
            <textarea className="h-20 w-full rounded-xl border p-3" placeholder="Цель" value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} />
            <textarea className="h-32 w-full rounded-xl border p-3" placeholder="Материал для сотрудника" value={form.material_text} onChange={(e) => setForm({ ...form, material_text: e.target.value })} />
            <textarea className="h-20 w-full rounded-xl border p-3" placeholder="Практическое задание" value={form.assignment_text} onChange={(e) => setForm({ ...form, assignment_text: e.target.value })} />
            <button onClick={createTopic} className="w-full rounded-xl bg-slate-900 px-4 py-3 font-semibold text-white hover:bg-slate-700">Добавить тему</button>
          </div>
        </div>

        <div className="rounded-3xl bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-semibold text-slate-900">Доска тем</h2>
            <input className="rounded-xl border p-2" type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
          </div>
          {loading ? <p className="mt-6 text-slate-500">Загрузка…</p> : null}
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {topics.map((topic) => (
              <article key={topic.id} className="rounded-2xl border border-slate-200 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm text-slate-500">{topic.lesson_date}</div>
                    <h3 className="mt-1 font-semibold text-slate-900">{topic.title}</h3>
                  </div>
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">{statusLabel(topic.status)}</span>
                </div>
                <p className="mt-3 line-clamp-3 text-sm text-slate-600">{topic.goal || topic.theme || 'Без описания'}</p>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs text-slate-500">
                  <div className="rounded-xl bg-slate-50 p-2">Назначено<br /><b>{topic.stats?.assigned || 0}</b></div>
                  <div className="rounded-xl bg-slate-50 p-2">Ответы<br /><b>{topic.stats?.submitted || 0}</b></div>
                  <div className="rounded-xl bg-slate-50 p-2">Принято<br /><b>{topic.stats?.accepted || 0}</b></div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button onClick={() => approveTopic(topic, true)} className="rounded-xl bg-emerald-600 px-3 py-2 text-sm font-semibold text-white">Согласовать</button>
                  <button onClick={() => approveTopic(topic, false)} className="rounded-xl bg-amber-100 px-3 py-2 text-sm font-semibold text-amber-800">Доработать</button>
                  <button onClick={() => publishTopic(topic)} className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-semibold text-white">В кабинеты</button>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">Ответы по этапам программ</h2>
        <p className="mt-1 text-sm text-slate-500">AI-черновик видит руководитель. Продавцу комментарий уходит только после подтверждения.</p>
        <div className="mt-4 space-y-3">
          {stepSubmissions.length === 0 ? <p className="text-slate-500">Ответов по этапам пока нет.</p> : null}
          {stepSubmissions.map((submission) => (
            <article key={submission.id} className="rounded-2xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="font-semibold text-slate-900">{submission.step_title || 'Этап программы'}</div>
                  <div className="text-sm text-slate-500">{submission.seller?.full_name || submission.seller?.email || 'Консультант'} · статус: {submission.review_status || submission.status} · AI: {submission.ai_score ?? '—'}/10</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => reviewStepSubmission(submission, 'accepted')} className="rounded-xl bg-emerald-600 px-3 py-2 text-sm font-semibold text-white">Принять этап</button>
                  <button onClick={() => reviewStepSubmission(submission, 'revision_requested')} className="rounded-xl bg-amber-100 px-3 py-2 text-sm font-semibold text-amber-800">Доработать</button>
                  <button onClick={() => reviewStepSubmission(submission, 'sent_to_consultant')} className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Отправить комментарий</button>
                </div>
              </div>
              <p className="mt-3 whitespace-pre-wrap rounded-xl bg-slate-50 p-3 text-sm text-slate-700">{submission.practice_answer}</p>
              {submission.evening_review ? <p className="mt-2 whitespace-pre-wrap rounded-xl bg-slate-50 p-3 text-sm text-slate-700">{submission.evening_review}</p> : null}
              {submission.ai_evaluation?.review_comment ? <p className="mt-2 rounded-xl bg-blue-50 p-3 text-sm text-blue-800">Черновик AI: {submission.ai_evaluation.review_comment}</p> : null}
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-3xl bg-white p-5 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">Ответы на проверку</h2>
        <div className="mt-4 space-y-3">
          {submissions.length === 0 ? <p className="text-slate-500">Ответов пока нет.</p> : null}
          {submissions.map((submission) => (
            <article key={submission.id} className="rounded-2xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="font-semibold text-slate-900">{submission.seller?.full_name || submission.seller?.email || submission.seller?.phone || 'Консультант'}</div>
                  <div className="text-sm text-slate-500">Статус: {submission.review_status} · оценка AI: {submission.ai_score ?? '—'}/10</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => reviewSubmission(submission, 'approved')} className="rounded-xl bg-emerald-600 px-3 py-2 text-sm font-semibold text-white">Принять</button>
                  <button onClick={() => reviewSubmission(submission, 'revision_requested')} className="rounded-xl bg-amber-100 px-3 py-2 text-sm font-semibold text-amber-800">Попросить доработать</button>
                  <button onClick={() => reviewSubmission(submission, 'sent_to_consultant')} className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Отправить комментарий</button>
                </div>
              </div>
              <p className="mt-3 whitespace-pre-wrap rounded-xl bg-slate-50 p-3 text-sm text-slate-700">{submission.practice_answer}</p>
              {submission.evening_review ? <p className="mt-2 whitespace-pre-wrap rounded-xl bg-slate-50 p-3 text-sm text-slate-700">{submission.evening_review}</p> : null}
              {submission.ai_evaluation?.review_comment ? <p className="mt-2 rounded-xl bg-blue-50 p-3 text-sm text-blue-800">Черновик AI: {submission.ai_evaluation.review_comment}</p> : null}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
