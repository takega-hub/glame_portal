'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import OpenRouterStatsPanel from './OpenRouterStatsPanel';
import UnifiedModelSelect from '@/components/models/UnifiedModelSelect';

type ModelOption = {
  id: string;
  name: string;
  label: string;
  pricingLabel: string;
  contextLabel: string;
};

type ImageOptimizationStatus = Awaited<ReturnType<typeof api.getImageOptimizationStatus>>;

function formatPricePerM(value?: string | null) {
  if (value == null) return '—';
  const n = Number(value);
  if (Number.isFinite(n)) return `$${n}/M`;
  return `$${value}/M`;
}

function buildModelLabel(model: any): ModelOption {
  const id = String(model?.id || '');
  const name = String(model?.name || id || 'Unknown');
  const prompt = formatPricePerM(model?.pricing?.prompt);
  const completion = formatPricePerM(model?.pricing?.completion);
  const pricingLabel = `${prompt} in, ${completion} out`;
  const ctx = model?.context_length ? `${model.context_length} ctx` : 'ctx —';
  const contextLabel = ctx;
  const label = `${name} (${id}) — ${pricingLabel} • ${contextLabel}`;
  return { id, name, label, pricingLabel, contextLabel };
}

function formatBytes(value?: number | null) {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 KB';
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}

export default function SettingsPage() {
  const router = useRouter();
  const { logout, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [currentModel, setCurrentModel] = useState<string>('');
  const [source, setSource] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [customModel, setCustomModel] = useState<string>('');
  const [userTouchedSelection, setUserTouchedSelection] = useState(false);
  const [currentAiCore, setCurrentAiCore] = useState<'openrouter' | 'hermes' | 'local'>('openrouter');
  const [aiCoreSource, setAiCoreSource] = useState<string>('');
  const [selectedAiCore, setSelectedAiCore] = useState<'openrouter' | 'hermes' | 'local'>('openrouter');

  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [search, setSearch] = useState<string>('');

  // Состояния для модели генерации изображений
  const [currentImageModel, setCurrentImageModel] = useState<string>('');
  const [imageSource, setImageSource] = useState<string>('');
  const [selectedImageModel, setSelectedImageModel] = useState<string>('');
  const [customImageModel, setCustomImageModel] = useState<string>('');
  const [userTouchedImageSelection, setUserTouchedImageSelection] = useState(false);

  const [imageModelsLoading, setImageModelsLoading] = useState(false);
  const [imageModelsError, setImageModelsError] = useState<string | null>(null);
  const [imageModels, setImageModels] = useState<ModelOption[]>([]);
  const [imageSearch, setImageSearch] = useState<string>('');

  // Смена пароля
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
  const [imageOptimizationStatus, setImageOptimizationStatus] = useState<ImageOptimizationStatus | null>(null);
  const [imageOptimizationLoading, setImageOptimizationLoading] = useState(true);
  const [imageOptimizationBusy, setImageOptimizationBusy] = useState(false);
  const [imageOptimizationError, setImageOptimizationError] = useState<string | null>(null);
  const [imageOptimizationSuccess, setImageOptimizationSuccess] = useState<string | null>(null);
  const [emailSettingsLoading, setEmailSettingsLoading] = useState(true);
  const [emailSettingsSaving, setEmailSettingsSaving] = useState(false);
  const [emailSettingsTesting, setEmailSettingsTesting] = useState(false);
  const [emailSettingsError, setEmailSettingsError] = useState<string | null>(null);
  const [emailSettingsSuccess, setEmailSettingsSuccess] = useState<string | null>(null);
  const [emailSource, setEmailSource] = useState<string>('default');
  const [emailPasswordSet, setEmailPasswordSet] = useState(false);
  const [emailHost, setEmailHost] = useState('');
  const [emailPort, setEmailPort] = useState('587');
  const [emailUsername, setEmailUsername] = useState('');
  const [emailPassword, setEmailPassword] = useState('');
  const [emailFromEmail, setEmailFromEmail] = useState('');
  const [emailFromName, setEmailFromName] = useState('GLAME Jewelry');
  const [emailUseSsl, setEmailUseSsl] = useState(false);
  const [emailUseStarttls, setEmailUseStarttls] = useState(true);
  const [emailTestTo, setEmailTestTo] = useState('');

  const effectiveSelection = useMemo(() => {
    if (selectedModel === '__custom__') return customModel.trim();
    return selectedModel.trim();
  }, [selectedModel, customModel]);

  const filteredModels = useMemo(() => {
    const q = (search || '').toLowerCase().trim();
    if (!q) return models;
    return models.filter((m) => m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q));
  }, [models, search]);

  const filteredImageModels = useMemo(() => {
    const q = (imageSearch || '').toLowerCase().trim();
    if (!q) return imageModels;
    return imageModels.filter((m) => m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q));
  }, [imageModels, imageSearch]);

  const load = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await api.getModelSettings();
      setCurrentModel(res.default_model);
      setSource(res.source);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Не удалось загрузить настройки модели');
    } finally {
      setLoading(false);
    }
  };

  const loadModels = async () => {
    setModelsLoading(true);
    setModelsError(null);
    try {
      const res = await api.getOpenRouterModels();
      const opts = (res.models || [])
        .map(buildModelLabel)
        .filter((m) => m.id && m.id.includes('/'))
        .sort((a, b) => a.name.localeCompare(b.name));
      setModels(opts);
    } catch (e: any) {
      setModelsError(e.response?.data?.detail || 'Не удалось загрузить список моделей из OpenRouter');
    } finally {
      setModelsLoading(false);
    }
  };

  const loadAiCoreSettings = async () => {
    try {
      const res = await api.getAiCoreSettings();
      setCurrentAiCore(res.ai_core_runtime);
      setSelectedAiCore(res.ai_core_runtime);
      setAiCoreSource(res.source);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Не удалось загрузить настройки ИИ ядра');
    }
  };

  const loadImageModels = async () => {
    setImageModelsLoading(true);
    setImageModelsError(null);
    try {
      const res = await api.getOpenRouterImageModels({ force_refresh: true });
      const models = res.models || [];
      
      if (models.length === 0) {
        setImageModelsError('Модели для генерации изображений не найдены. Проверьте, что OPENROUTER_API_KEY установлен и содержит модели типа Flux, DALL-E, Nano.');
      } else {
        const opts = models
          .map(buildModelLabel)
          .filter((m) => m.id && m.id.includes('/'))
          .sort((a, b) => a.name.localeCompare(b.name));
        setImageModels(opts);
      }
    } catch (e: any) {
      const errorMsg = e.response?.data?.detail || e.message || 'Не удалось загрузить список моделей для генерации изображений';
      setImageModelsError(errorMsg);
      console.error('Error loading image models:', e);
    } finally {
      setImageModelsLoading(false);
    }
  };

  const loadImageModelSettings = async () => {
    try {
      const res = await api.getImageGenerationModelSettings();
      setCurrentImageModel(res.image_generation_model);
      setImageSource(res.source);
    } catch (e: any) {
      console.error('Failed to load image generation model settings:', e);
    }
  };

  const loadImageOptimizationStatus = async (silent = false) => {
    if (!silent) setImageOptimizationLoading(true);
    try {
      const res = await api.getImageOptimizationStatus();
      setImageOptimizationStatus(res);
    } catch (e: any) {
      setImageOptimizationError(e.response?.data?.detail || e.message || 'Не удалось загрузить статус оптимизации изображений');
    } finally {
      if (!silent) setImageOptimizationLoading(false);
    }
  };

  const loadEmailServerSettings = async () => {
    setEmailSettingsLoading(true);
    setEmailSettingsError(null);
    try {
      const res = await api.getEmailServerSettings();
      setEmailHost(res.host || '');
      setEmailPort(String(res.port || 587));
      setEmailUsername(res.username || '');
      setEmailFromEmail(res.from_email || '');
      setEmailFromName(res.from_name || 'GLAME Jewelry');
      setEmailUseSsl(Boolean(res.use_ssl));
      setEmailUseStarttls(Boolean(res.use_starttls));
      setEmailPasswordSet(Boolean(res.password_set));
      setEmailSource(res.source);
      setEmailPassword('');
      if (!emailTestTo && res.from_email) setEmailTestTo(res.from_email);
    } catch (e: any) {
      setEmailSettingsError(e.response?.data?.detail || e.message || 'Не удалось загрузить настройки почты');
    } finally {
      setEmailSettingsLoading(false);
    }
  };

  useEffect(() => {
    load();
    loadAiCoreSettings();
    loadModels();
    loadImageModelSettings();
    loadImageModels();
    loadImageOptimizationStatus();
    loadEmailServerSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!currentModel) return;
    if (userTouchedSelection) return;
    const known = models.some((m) => m.id === currentModel);
    if (known) {
      setSelectedModel(currentModel);
      setCustomModel('');
    } else if (currentModel) {
      setSelectedModel('__custom__');
      setCustomModel(currentModel);
    }
  }, [currentModel, models, userTouchedSelection]);

  // If we couldn't load currentModel but we did load models, preselect the first option so the dropdown is usable.
  useEffect(() => {
    if (userTouchedSelection) return;
    if (selectedModel) return;
    if (models.length === 0) return;
    setSelectedModel(models[0].id);
  }, [models, selectedModel, userTouchedSelection]);

  useEffect(() => {
    if (!currentImageModel) return;
    if (userTouchedImageSelection) return;
    const known = imageModels.some((m) => m.id === currentImageModel);
    if (known) {
      setSelectedImageModel(currentImageModel);
      setCustomImageModel('');
    } else if (currentImageModel) {
      setSelectedImageModel('__custom__');
      setCustomImageModel(currentImageModel);
    }
  }, [currentImageModel, imageModels, userTouchedImageSelection]);

  useEffect(() => {
    if (userTouchedImageSelection) return;
    if (selectedImageModel) return;
    if (imageModels.length === 0) return;
    setSelectedImageModel(imageModels[0].id);
  }, [imageModels, selectedImageModel, userTouchedImageSelection]);

  useEffect(() => {
    if (imageOptimizationStatus?.status !== 'running') return;
    const intervalId = window.setInterval(() => {
      loadImageOptimizationStatus(true);
    }, 3000);
    return () => window.clearInterval(intervalId);
  }, [imageOptimizationStatus?.status]);

  const effectiveImageSelection = useMemo(() => {
    if (selectedImageModel === '__custom__') return customImageModel.trim();
    return selectedImageModel.trim();
  }, [selectedImageModel, customImageModel]);

  const onSave = async () => {
    const model = effectiveSelection;
    if (!model || !model.includes('/')) {
      setError("Укажите модель в формате 'provider/model', например 'openai/gpt-4o-mini'.");
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await api.setModelSettings({ default_model: model });
      setCurrentModel(res.default_model);
      setSource(res.source);
      setSuccess('Сохранено. Новые запросы к LLM будут использовать выбранную модель.');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить настройки');
    } finally {
      setSaving(false);
    }
  };

  const onSaveAiCore = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await api.setAiCoreSettings({ ai_core_runtime: selectedAiCore });
      setCurrentAiCore(res.ai_core_runtime);
      setSelectedAiCore(res.ai_core_runtime);
      setAiCoreSource(res.source);
      setSuccess('ИИ ядро сохранено. Новые ответы агентов будут использовать выбранный runtime.');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить ИИ ядро');
    } finally {
      setSaving(false);
    }
  };

  const onSaveImageModel = async () => {
    const model = effectiveImageSelection;
    if (!model || !model.includes('/')) {
      setError("Укажите модель в формате 'provider/model', например 'black-forest-labs/flux-pro'.");
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await api.setImageGenerationModelSettings({ image_generation_model: model });
      setCurrentImageModel(res.image_generation_model);
      setImageSource(res.source);
      setSuccess('Сохранено. Генерация изображений образов будет использовать выбранную модель.');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить настройки модели генерации изображений');
    } finally {
      setSaving(false);
    }
  };

  const onChangePassword = async () => {
    setPasswordError(null);
    setPasswordSuccess(null);
    if (!newPassword || newPassword.length < 6) {
      setPasswordError('Новый пароль должен быть не короче 6 символов.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('Пароли не совпадают.');
      return;
    }
    setPasswordSaving(true);
    try {
      await api.changePassword(currentPassword || null, newPassword);
      setPasswordSuccess('Пароль успешно изменён.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (e: any) {
      setPasswordError(e.response?.data?.detail || e.message || 'Не удалось изменить пароль.');
    } finally {
      setPasswordSaving(false);
    }
  };

  const onRunImageOptimization = async () => {
    const confirmed = window.confirm(
      'Запустить оптимизацию изображений? Будут обработаны только файлы больше 150 КБ, чтобы уменьшить их размер без смены ссылок.'
    );
    if (!confirmed) return;

    setImageOptimizationBusy(true);
    setImageOptimizationError(null);
    setImageOptimizationSuccess(null);
    try {
      const res = await api.runImageOptimization();
      setImageOptimizationStatus(res);
      setImageOptimizationSuccess(res.message || 'Оптимизация изображений запущена.');
    } catch (e: any) {
      setImageOptimizationError(e.response?.data?.detail || e.message || 'Не удалось запустить оптимизацию изображений');
    } finally {
      setImageOptimizationBusy(false);
    }
  };

  const onSaveEmailSettings = async () => {
    setEmailSettingsSaving(true);
    setEmailSettingsError(null);
    setEmailSettingsSuccess(null);
    try {
      const port = Number(emailPort);
      if (!emailHost.trim() || !emailFromEmail.trim() || !Number.isFinite(port)) {
        throw new Error('Укажите SMTP host, порт и email отправителя.');
      }
      const res = await api.setEmailServerSettings({
        host: emailHost.trim(),
        port,
        username: emailUsername.trim() || undefined,
        password: emailPassword.trim() || undefined,
        from_email: emailFromEmail.trim(),
        from_name: emailFromName.trim() || 'GLAME Jewelry',
        use_ssl: emailUseSsl,
        use_starttls: emailUseStarttls,
      });
      setEmailSource(res.source);
      setEmailPasswordSet(res.password_set);
      setEmailPassword('');
      setEmailSettingsSuccess('Настройки почтового сервера сохранены.');
    } catch (e: any) {
      setEmailSettingsError(e.response?.data?.detail || e.message || 'Не удалось сохранить настройки почты');
    } finally {
      setEmailSettingsSaving(false);
    }
  };

  const onTestEmailSettings = async () => {
    setEmailSettingsTesting(true);
    setEmailSettingsError(null);
    setEmailSettingsSuccess(null);
    try {
      const toEmail = emailTestTo.trim() || emailFromEmail.trim();
      if (!toEmail) throw new Error('Укажите email для тестового письма.');
      const res = await api.testEmailServerSettings(toEmail);
      setEmailSettingsSuccess(res.message || 'Тестовое письмо отправлено.');
    } catch (e: any) {
      setEmailSettingsError(e.response?.data?.detail || e.message || 'Не удалось отправить тестовое письмо');
    } finally {
      setEmailSettingsTesting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-gray-800 mb-2">Настройки</h1>
      <p className="text-gray-600 mb-6">Конфигурация ИИ ядра, моделей LLM и генерации изображений.</p>

      {/* Панель статистики OpenRouter */}
      <OpenRouterStatsPanel />

      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-4">ИИ ядро агентов</h2>
        <div className="mb-4">
          <p className="text-sm text-gray-600">Текущее ядро:</p>
          <p className="font-mono text-sm text-gray-900">{currentAiCore}</p>
          <p className="text-xs text-gray-500 mt-1">Источник: {aiCoreSource}</p>
        </div>
        <div className="grid gap-3 md:grid-cols-3 mb-4">
          {[
            { id: 'hermes', title: 'Hermes', text: 'Агенты GLAME через Hermes-профили, промпты и навыки.' },
            { id: 'openrouter', title: 'OpenRouter', text: 'Прямой legacy-вызов выбранной облачной модели.' },
            { id: 'local', title: 'Локальная LLM', text: 'OpenAI-compatible endpoint LOCAL_LLM_BASE_URL.' },
          ].map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setSelectedAiCore(option.id as 'openrouter' | 'hermes' | 'local')}
              className={`text-left border rounded-lg p-4 transition ${
                selectedAiCore === option.id
                  ? 'border-gold-500 bg-gold-50 ring-2 ring-gold-100'
                  : 'border-gray-200 hover:border-gray-300 bg-white'
              }`}
            >
              <div className="font-semibold text-gray-900">{option.title}</div>
              <div className="text-xs text-gray-500 mt-1">{option.text}</div>
            </button>
          ))}
        </div>
        <button
          onClick={onSaveAiCore}
          disabled={saving || selectedAiCore === currentAiCore}
          className="px-5 py-2.5 bg-gold-500 text-white rounded-lg hover:bg-gold-600 disabled:opacity-50 transition font-semibold"
        >
          {saving ? 'Сохранение…' : 'Сохранить ИИ ядро'}
        </button>
      </div>

      {/* Настройки LLM модели */}
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        {loading ? (
          <p className="text-gray-500">Загрузка…</p>
        ) : (
          <>
            {error && <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">{error}</div>}
            {success && (
              <div className="mb-4 text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg p-3">
                {success}
              </div>
            )}

            <div className="mb-4">
              <p className="text-sm text-gray-600">Текущая модель:</p>
              <p className="font-mono text-sm text-gray-900 break-all">{currentModel}</p>
              <p className="text-xs text-gray-500 mt-1">Источник: {source}</p>
            </div>

            <div className="mb-4">
              <UnifiedModelSelect
                label="Выбор модели"
                value={selectedModel}
                onChange={(v) => {
                  setUserTouchedSelection(true);
                  setSelectedModel(v);
                }}
                mode="llm"
                allowCustom
              />
              <p className="mt-2 text-xs text-gray-500">Это OpenRouter model id.</p>
            </div>

            {selectedModel === '__custom__' && (
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">Модель вручную</label>
                <input
                  value={customModel}
                  onChange={(e) => setCustomModel(e.target.value)}
                  placeholder="например: mistralai/mistral-large"
                  className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 caret-gold-600 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
                />
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={onSave}
                disabled={saving}
                className="px-5 py-2.5 bg-gold-500 text-white rounded-lg hover:bg-gold-600 disabled:opacity-50 transition font-semibold"
              >
                {saving ? 'Сохранение…' : 'Сохранить'}
              </button>
              <button
                onClick={() => {
                  load();
                  loadModels();
                }}
                disabled={saving}
                className="px-5 py-2.5 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition text-gray-900 font-medium"
              >
                Обновить
              </button>
            </div>
          </>
        )}
      </div>

      {/* Настройки модели генерации изображений */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-4">Модель для генерации изображений</h2>
        {loading ? (
          <p className="text-gray-500">Загрузка…</p>
        ) : (
          <>
            <div className="mb-4">
              <p className="text-sm text-gray-600">Текущая модель:</p>
              <p className="font-mono text-sm text-gray-900 break-all">{currentImageModel}</p>
              <p className="text-xs text-gray-500 mt-1">Источник: {imageSource}</p>
            </div>

            <div className="mb-4">
              <UnifiedModelSelect
                label="Выбор модели для генерации изображений"
                value={selectedImageModel}
                onChange={(v) => {
                  setUserTouchedImageSelection(true);
                  setSelectedImageModel(v);
                }}
                mode="image"
                allowCustom
              />
              <p className="mt-2 text-xs text-gray-500">Модели для генерации изображений.</p>
            </div>

            {selectedImageModel === '__custom__' && (
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">Модель вручную</label>
                <input
                  value={customImageModel}
                  onChange={(e) => setCustomImageModel(e.target.value)}
                  placeholder="например: black-forest-labs/flux-pro"
                  className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 caret-gold-600 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
                />
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={onSaveImageModel}
                disabled={saving}
                className="px-5 py-2.5 bg-gold-500 text-white rounded-lg hover:bg-gold-600 disabled:opacity-50 transition font-semibold"
              >
                {saving ? 'Сохранение…' : 'Сохранить'}
              </button>
              <button
                onClick={() => {
                  loadImageModelSettings();
                  loadImageModels();
                }}
                disabled={saving}
                className="px-5 py-2.5 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition text-gray-900 font-medium"
              >
                Обновить
              </button>
            </div>
          </>
        )}
      </div>

      <div className="bg-white rounded-lg shadow-md p-6 mt-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-2">Оптимизация изображений</h2>
        <p className="text-sm text-gray-600 mb-4">
          Админ может вручную запускать оптимизацию существующих файлов изображений. Обрабатываются только файлы больше{' '}
          {formatBytes(imageOptimizationStatus?.min_original_bytes ?? 150 * 1024)}, ссылки на файлы не меняются.
        </p>

        {imageOptimizationError && (
          <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
            {imageOptimizationError}
          </div>
        )}
        {imageOptimizationSuccess && (
          <div className="mb-4 text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg p-3">
            {imageOptimizationSuccess}
          </div>
        )}

        {imageOptimizationLoading ? (
          <p className="text-gray-500">Загрузка статуса…</p>
        ) : (
          <>
            <div className="mb-4 rounded-lg border border-gray-200 p-4">
              <div className="flex flex-wrap items-center gap-3 mb-3">
                <span className="text-sm font-medium text-gray-700">Статус:</span>
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${
                    imageOptimizationStatus?.status === 'running'
                      ? 'bg-amber-100 text-amber-800'
                      : imageOptimizationStatus?.status === 'completed'
                        ? 'bg-emerald-100 text-emerald-800'
                        : imageOptimizationStatus?.status === 'failed'
                          ? 'bg-red-100 text-red-800'
                          : 'bg-gray-100 text-gray-700'
                  }`}
                >
                  {imageOptimizationStatus?.status === 'running'
                    ? 'В процессе'
                    : imageOptimizationStatus?.status === 'completed'
                      ? 'Завершено'
                      : imageOptimizationStatus?.status === 'failed'
                        ? 'Ошибка'
                        : 'Ожидание'}
                </span>
              </div>

              {imageOptimizationStatus?.message && (
                <p className="text-sm text-gray-700 mb-3">{imageOptimizationStatus.message}</p>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm text-gray-700">
                <div>Найдено файлов: {imageOptimizationStatus?.scanned_files ?? 0}</div>
                <div>Крупных файлов: {imageOptimizationStatus?.eligible_files ?? 0}</div>
                <div>Оптимизировано: {imageOptimizationStatus?.optimized_files ?? 0}</div>
                <div>Пропущено как мелкие: {imageOptimizationStatus?.skipped_small_files ?? 0}</div>
                <div>Экономия места: {formatBytes(imageOptimizationStatus?.saved_bytes ?? 0)}</div>
                <div>Ошибок: {imageOptimizationStatus?.failed_files ?? 0}</div>
              </div>

              {(imageOptimizationStatus?.started_at || imageOptimizationStatus?.finished_at) && (
                <div className="mt-3 text-xs text-gray-500 space-y-1">
                  {imageOptimizationStatus.started_at && <div>Запуск: {new Date(imageOptimizationStatus.started_at).toLocaleString()}</div>}
                  {imageOptimizationStatus.finished_at && <div>Завершение: {new Date(imageOptimizationStatus.finished_at).toLocaleString()}</div>}
                </div>
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={onRunImageOptimization}
                disabled={imageOptimizationBusy || imageOptimizationStatus?.status === 'running'}
                className="px-5 py-2.5 bg-gold-500 text-white rounded-lg hover:bg-gold-600 disabled:opacity-50 transition font-semibold"
              >
                {imageOptimizationBusy || imageOptimizationStatus?.status === 'running'
                  ? 'Оптимизация…'
                  : 'Оптимизация изображений'}
              </button>
              <button
                onClick={() => {
                  setImageOptimizationError(null);
                  setImageOptimizationSuccess(null);
                  loadImageOptimizationStatus();
                }}
                disabled={imageOptimizationBusy}
                className="px-5 py-2.5 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition text-gray-900 font-medium"
              >
                Обновить статус
              </button>
            </div>
          </>
        )}
      </div>

      <div className="bg-white rounded-lg shadow-md p-6 mt-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-2">Почтовый сервер</h2>
        <p className="text-sm text-gray-600 mb-4">
          Эти настройки используются для отправки электронных подарочных сертификатов и сервисных писем.
        </p>

        {emailSettingsError && (
          <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
            {emailSettingsError}
          </div>
        )}
        {emailSettingsSuccess && (
          <div className="mb-4 text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg p-3">
            {emailSettingsSuccess}
          </div>
        )}

        {emailSettingsLoading ? (
          <p className="text-gray-500">Загрузка настроек почты…</p>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">SMTP host</label>
                <input
                  value={emailHost}
                  onChange={(e) => setEmailHost(e.target.value)}
                  placeholder="smtp.mail.ru"
                  className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Порт</label>
                <input
                  value={emailPort}
                  onChange={(e) => setEmailPort(e.target.value)}
                  inputMode="numeric"
                  placeholder="465"
                  className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Логин SMTP</label>
                <input
                  value={emailUsername}
                  onChange={(e) => setEmailUsername(e.target.value)}
                  placeholder="ai@glamejewelry.ru"
                  autoComplete="username"
                  className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Пароль SMTP {emailPasswordSet ? '(сохранен)' : ''}
                </label>
                <input
                  value={emailPassword}
                  onChange={(e) => setEmailPassword(e.target.value)}
                  type="password"
                  placeholder={emailPasswordSet ? 'Оставьте пустым, чтобы не менять' : 'Пароль приложения'}
                  autoComplete="new-password"
                  className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email отправителя</label>
                <input
                  value={emailFromEmail}
                  onChange={(e) => setEmailFromEmail(e.target.value)}
                  placeholder="ai@glamejewelry.ru"
                  type="email"
                  className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Имя отправителя</label>
                <input
                  value={emailFromName}
                  onChange={(e) => setEmailFromName(e.target.value)}
                  placeholder="GLAME Jewelry"
                  className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
                />
              </div>
            </div>

            <div className="flex flex-wrap gap-4 text-sm text-gray-700">
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={emailUseSsl}
                  onChange={(e) => {
                    setEmailUseSsl(e.target.checked);
                    if (e.target.checked) setEmailUseStarttls(false);
                  }}
                  className="h-4 w-4 rounded border-gray-300 text-gold-600 focus:ring-gold-500"
                />
                SSL
              </label>
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={emailUseStarttls}
                  onChange={(e) => {
                    setEmailUseStarttls(e.target.checked);
                    if (e.target.checked) setEmailUseSsl(false);
                  }}
                  className="h-4 w-4 rounded border-gray-300 text-gold-600 focus:ring-gold-500"
                />
                STARTTLS
              </label>
              <span className="text-gray-500">Источник: {emailSource}</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3">
              <input
                value={emailTestTo}
                onChange={(e) => setEmailTestTo(e.target.value)}
                placeholder="Email для тестового письма"
                type="email"
                className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
              />
              <button
                onClick={onTestEmailSettings}
                disabled={emailSettingsTesting || emailSettingsSaving}
                className="px-5 py-2.5 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition text-gray-900 font-medium"
              >
                {emailSettingsTesting ? 'Отправка…' : 'Тест письма'}
              </button>
            </div>

            <div className="flex gap-3">
              <button
                onClick={onSaveEmailSettings}
                disabled={emailSettingsSaving}
                className="px-5 py-2.5 bg-gold-500 text-white rounded-lg hover:bg-gold-600 disabled:opacity-50 transition font-semibold"
              >
                {emailSettingsSaving ? 'Сохранение…' : 'Сохранить почту'}
              </button>
              <button
                type="button"
                onClick={loadEmailServerSettings}
                disabled={emailSettingsSaving}
                className="px-5 py-2.5 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition text-gray-900 font-medium"
              >
                Обновить
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Смена пароля */}
      <div className="bg-white rounded-lg shadow-md p-6 mt-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-4">Смена пароля</h2>
        {user?.email && (
          <p className="mb-3 text-sm text-gray-600">
            Текущий пользователь:{' '}
            <span className="font-semibold text-gray-900">{user.email}</span>
          </p>
        )}
        {passwordError && (
          <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">{passwordError}</div>
        )}
        {passwordSuccess && (
          <div className="mb-4 text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg p-3">
            {passwordSuccess}
          </div>
        )}
        <div className="space-y-4 max-w-md">
          <div>
            <label htmlFor="current-password" className="block text-sm font-medium text-gray-700 mb-1">
              Текущий пароль
            </label>
            <input
              id="current-password"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Оставьте пустым, если пароль ещё не задан"
              autoComplete="current-password"
              className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
            />
          </div>
          <div>
            <label htmlFor="new-password" className="block text-sm font-medium text-gray-700 mb-1">
              Новый пароль
            </label>
            <input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Не короче 6 символов"
              autoComplete="new-password"
              className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
            />
          </div>
          <div>
            <label htmlFor="confirm-password" className="block text-sm font-medium text-gray-700 mb-1">
              Подтверждение нового пароля
            </label>
            <input
              id="confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Повторите новый пароль"
              autoComplete="new-password"
              className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
            />
          </div>
          <div className="flex gap-3">
            <button
              onClick={onChangePassword}
              disabled={passwordSaving}
              className="px-5 py-2.5 bg-gold-500 text-white rounded-lg hover:bg-gold-600 disabled:opacity-50 transition font-semibold"
            >
              {passwordSaving ? 'Сохранение…' : 'Изменить пароль'}
            </button>
            <button
              type="button"
              onClick={() => {
                logout();
                router.push('/login');
              }}
              className="px-5 py-2.5 border border-gray-300 rounded-lg hover:bg-gray-50 transition text-gray-700 font-medium"
            >
              Выйти
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
