'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';

type ModelOption = {
  id: string;
  name: string;
  label: string;
  pricingLabel: string;
  contextLabel: string;
};

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

export default function SettingsPage() {
  const router = useRouter();
  const { logout } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [currentModel, setCurrentModel] = useState<string>('');
  const [source, setSource] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [customModel, setCustomModel] = useState<string>('');
  const [userTouchedSelection, setUserTouchedSelection] = useState(false);

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

  useEffect(() => {
    load();
    loadModels();
    loadImageModelSettings();
    loadImageModels();
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

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-gray-800 mb-2">Настройки</h1>
      <p className="text-gray-600 mb-6">Конфигурация моделей OpenRouter для LLM и генерации изображений.</p>

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
              <label className="block text-sm font-medium text-gray-700 mb-2">Выбор модели</label>
              {modelsError && (
                <div className="mb-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-3">
                  {modelsError}
                </div>
              )}

              <div className="mb-2">
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Поиск по названию или id (например: claude, gpt-4o, gemini...)"
                  className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
                />
              </div>

              <select
                value={selectedModel}
                onChange={(e) => {
                  setUserTouchedSelection(true);
                  setSelectedModel(e.target.value);
                }}
                disabled={modelsLoading && models.length === 0}
                className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
              >
                {models.length === 0 && (
                  <option value="" disabled>
                    {modelsLoading ? 'Загрузка моделей…' : 'Нет списка моделей (можно ввести вручную)'}
                  </option>
                )}
                {filteredModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
                <option value="__custom__">Другая (ввести вручную)</option>
              </select>
              <p className="mt-2 text-xs text-gray-500">
                Это OpenRouter model id. В скобках показана цена: <span className="font-mono">$prompt/M</span> и{' '}
                <span className="font-mono">$completion/M</span>.
              </p>
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
              <label className="block text-sm font-medium text-gray-700 mb-2">Выбор модели для генерации изображений</label>
              {imageModelsError && (
                <div className="mb-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-3">
                  {imageModelsError}
                </div>
              )}

              <div className="mb-2">
                <input
                  value={imageSearch}
                  onChange={(e) => setImageSearch(e.target.value)}
                  placeholder="Поиск по названию или id (например: flux, nano, dall-e...)"
                  className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
                />
              </div>

              <select
                value={selectedImageModel}
                onChange={(e) => {
                  setUserTouchedImageSelection(true);
                  setSelectedImageModel(e.target.value);
                }}
                disabled={imageModelsLoading && imageModels.length === 0}
                className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500 focus:border-gold-500"
              >
                {imageModels.length === 0 && !imageModelsError && (
                  <option value="" disabled>
                    {imageModelsLoading ? 'Загрузка моделей…' : 'Нет списка моделей (можно ввести вручную)'}
                  </option>
                )}
                {imageModelsError && (
                  <option value="" disabled>
                    Ошибка загрузки моделей
                  </option>
                )}
                {filteredImageModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
                <option value="__custom__">Другая (ввести вручную)</option>
              </select>
              <p className="mt-2 text-xs text-gray-500">
                Модели для генерации изображений (Flux, DALL-E, Nano и др.). В скобках показана цена.
              </p>
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

      {/* Смена пароля */}
      <div className="bg-white rounded-lg shadow-md p-6 mt-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-4">Смена пароля</h2>
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

