'use client';

import { useState, useEffect, useCallback } from 'react';
import { systemPrompts, type SystemPromptVersion, type PromptGenerationRequest } from '@/lib/api';

interface SystemPromptPanelProps {
  agentType: string;
  isMarketer?: boolean;
}

export default function SystemPromptPanel({ agentType, isMarketer = false }: SystemPromptPanelProps) {
  const [versions, setVersions] = useState<SystemPromptVersion[]>([]);
  const [activeVersion, setActiveVersion] = useState<SystemPromptVersion | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Create/Edit states
  const [isCreating, setIsCreating] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [editingVersion, setEditingVersion] = useState<SystemPromptVersion | null>(null);
  const [showHistory, setShowHistory] = useState<string | null>(null);
  const [history, setHistory] = useState<any[]>([]);

  // Modal states
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState<SystemPromptVersion | null>(null);
  const [editFormName, setEditFormName] = useState('');
  const [editFormDescription, setEditFormDescription] = useState('');
  const [editFormPrompt, setEditFormPrompt] = useState('');
  const [editFormVersionName, setEditFormVersionName] = useState('');
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  // Form states
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formPrompt, setFormPrompt] = useState('');
  const [formVersionName, setFormVersionName] = useState('');

  // Generation states
  const [genDescription, setGenDescription] = useState('');
  const [genTone, setGenTone] = useState('');
  const [genAudience, setGenAudience] = useState('');
  const [generatedPrompt, setGeneratedPrompt] = useState('');
  const [generationRequests, setGenerationRequests] = useState<PromptGenerationRequest[]>([]);

  const loadVersions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [versionsData, activeData] = await Promise.all([
        systemPrompts.getVersions(agentType),
        systemPrompts.getActive(agentType),
      ]);
      setVersions(versionsData);
      setActiveVersion(activeData);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Ошибка загрузки версий промптов');
    } finally {
      setLoading(false);
    }
  }, [agentType]);

  const loadGenerationRequests = useCallback(async () => {
    try {
      const requests = await systemPrompts.getGenerationRequests(agentType, 10);
      setGenerationRequests(requests);
    } catch (err) {
      console.error('Failed to load generation requests', err);
    }
  }, [agentType]);

  useEffect(() => {
    loadVersions();
    loadGenerationRequests();
  }, [loadVersions, loadGenerationRequests]);

  const handleCreate = async () => {
    if (!formName.trim() || !formPrompt.trim()) {
      setError('Название и системный промпт обязательны');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await systemPrompts.createVersion(agentType, {
        name: formName,
        system_prompt: formPrompt,
        description: formDescription || undefined,
        version_name: formVersionName || undefined,
      });
      setSuccessMessage('Версия промпта создана успешно');
      resetForm();
      setIsCreating(false);
      await loadVersions();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка создания версии');
    } finally {
      setLoading(false);
    }
  };

  const handleActivate = async (promptId: string) => {
    setLoading(true);
    setError(null);
    try {
      await systemPrompts.activateVersion(agentType, promptId);
      setSuccessMessage('Версия активирована');
      await loadVersions();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка активации версии');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitForReview = async (promptId: string) => {
    setLoading(true);
    setError(null);
    try {
      await systemPrompts.submitForReview(agentType, promptId);
      setSuccessMessage('Отправлено на ревью маркетологу');
      await loadVersions();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка отправки на ревью');
    } finally {
      setLoading(false);
    }
  };

  const handleReview = async (promptId: string, status: 'approved' | 'rejected' | 'needs_revision') => {
    setLoading(true);
    setError(null);
    try {
      await systemPrompts.reviewAsMarketer(agentType, promptId, status as 'approved' | 'rejected' | 'needs_revision');
      setSuccessMessage(`Ревью выполнено: ${status}`);
      await loadVersions();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка ревью');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    if (!genDescription.trim()) {
      setError('Описание задачи обязательно');
      return;
    }

    setIsGenerating(true);
    setError(null);
    try {
      const result = await systemPrompts.generateFromDescription(agentType, {
        user_description: genDescription,
        target_tone: genTone || undefined,
        target_audience: genAudience || undefined,
      });
      setSuccessMessage('Промпт генерируется...');
      // Poll for completion
      pollGenerationStatus(result.id);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка генерации промпта');
      setIsGenerating(false);
    }
  };

  const pollGenerationStatus = async (requestId: string) => {
    const checkStatus = async () => {
      try {
        const requests = await systemPrompts.getGenerationRequests(agentType, 10);
        const request = requests.find(r => r.id === requestId);
        if (request) {
          if (request.status === 'completed') {
            setGeneratedPrompt(request.generated_prompt || '');
            setFormPrompt(request.generated_prompt || '');
            setSuccessMessage('Промпт успешно сгенерирован!');
            setIsGenerating(false);
            loadGenerationRequests();
            return;
          } else if (request.status === 'failed') {
            setError(request.error_message || 'Ошибка генерации');
            setIsGenerating(false);
            return;
          }
        }
        // Continue polling
        setTimeout(checkStatus, 2000);
      } catch (err) {
        console.error('Polling error', err);
        setIsGenerating(false);
      }
    };
    checkStatus();
  };

  const handleCreateFromGeneration = async (requestId: string) => {
    if (!formName.trim()) {
      setError('Укажите название для новой версии');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await systemPrompts.createFromGenerationRequest(agentType, requestId, formName);
      setSuccessMessage('Версия создана из сгенерированного промпта');
      setGeneratedPrompt('');
      setFormPrompt('');
      resetForm();
      await loadVersions();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка создания версии');
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = async (promptId: string) => {
    setLoading(true);
    try {
      const historyData = await systemPrompts.getVersionHistory(agentType, promptId);
      setHistory(historyData);
      setShowHistory(promptId);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка загрузки истории');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenEditModal = (version: SystemPromptVersion) => {
    setEditingPrompt(version);
    setEditFormName(version.name || '');
    setEditFormDescription(version.description || '');
    setEditFormPrompt(version.system_prompt || '');
    setEditFormVersionName(version.version_name || '');
    setShowEditModal(true);
  };

  const handleSaveEdit = async () => {
    if (!editingPrompt || !editFormName.trim() || !editFormPrompt.trim()) {
      setError('Название и системный промпт обязательны');
      return;
    }

    setIsSavingEdit(true);
    setError(null);
    try {
      await systemPrompts.updateVersion(agentType, editingPrompt.id, {
        name: editFormName,
        description: editFormDescription || undefined,
        system_prompt: editFormPrompt,
        version_name: editFormVersionName || undefined,
      });
      setSuccessMessage('Версия промпта обновлена успешно');
      setShowEditModal(false);
      setEditingPrompt(null);
      await loadVersions();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Ошибка обновления версии');
    } finally {
      setIsSavingEdit(false);
    }
  };

  const resetForm = () => {
    setFormName('');
    setFormDescription('');
    setFormPrompt('');
    setFormVersionName('');
    setGenDescription('');
    setGenTone('');
    setGenAudience('');
    setGeneratedPrompt('');
  };

  const getStatusBadge = (version: SystemPromptVersion) => {
    if (version.is_active) {
      return <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded">Активная</span>;
    }
    if (version.marketer_review_status === 'approved') {
      return <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded">Утверждена</span>;
    }
    if (version.marketer_review_status === 'pending') {
      return <span className="px-2 py-1 text-xs font-medium bg-yellow-100 text-yellow-800 rounded">На ревью</span>;
    }
    if (version.marketer_review_status === 'rejected') {
      return <span className="px-2 py-1 text-xs font-medium bg-red-100 text-red-800 rounded">Отклонена</span>;
    }
    return <span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-800 rounded">Черновик</span>;
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-semibold">Системные промпты {agentType}</h2>
        <div className="flex gap-2">
          <button
            onClick={() => setIsGenerating(!isGenerating)}
            className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 transition-colors"
            disabled={loading}
          >
            {isGenerating ? 'Отменить' : 'Сгенерировать из описания'}
          </button>
          <button
            onClick={() => setIsCreating(!isCreating)}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
            disabled={loading}
          >
            {isCreating ? 'Отменить' : 'Создать версию'}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded text-red-700">
          {error}
        </div>
      )}

      {successMessage && (
        <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded text-green-700">
          {successMessage}
        </div>
      )}

      {/* Generation Form */}
      {isGenerating && (
        <div className="mb-6 p-4 bg-purple-50 border border-purple-200 rounded">
          <h3 className="font-medium mb-4">Генерация промпта из описания</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Описание задачи *</label>
              <textarea
                value={genDescription}
                onChange={(e) => setGenDescription(e.target.value)}
                className="w-full p-2 border rounded focus:ring-2 focus:ring-purple-500"
                rows={3}
                placeholder="Опишите, как должен вести себя AI агент..."
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Желаемый тон</label>
                <input
                  type="text"
                  value={genTone}
                  onChange={(e) => setGenTone(e.target.value)}
                  className="w-full p-2 border rounded focus:ring-2 focus:ring-purple-500"
                  placeholder="профессиональный, дружелюбный..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Целевая аудитория</label>
                <input
                  type="text"
                  value={genAudience}
                  onChange={(e) => setGenAudience(e.target.value)}
                  className="w-full p-2 border rounded focus:ring-2 focus:ring-purple-500"
                  placeholder="молодые профессионалы..."
                />
              </div>
            </div>
            <button
              onClick={handleGenerate}
              disabled={loading || !genDescription.trim()}
              className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
            >
              {loading ? 'Генерация...' : 'Сгенерировать'}
            </button>

            {generatedPrompt && (
              <div className="mt-4">
                <label className="block text-sm font-medium mb-1">Сгенерированный промпт:</label>
                <textarea
                  value={generatedPrompt}
                  onChange={(e) => {
                    setGeneratedPrompt(e.target.value);
                    setFormPrompt(e.target.value);
                  }}
                  className="w-full p-2 border rounded focus:ring-2 focus:ring-purple-500"
                  rows={6}
                />
                <div className="mt-2 flex gap-2">
                  <input
                    type="text"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="Название версии"
                    className="flex-1 p-2 border rounded"
                  />
                  <button
                    onClick={() => handleCreateFromGeneration(generationRequests[0]?.id)}
                    disabled={loading || !formName.trim()}
                    className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                  >
                    Создать версию
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Create Form */}
      {isCreating && (
        <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded">
          <h3 className="font-medium mb-4">Создание новой версии</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Название *</label>
              <input
                type="text"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500"
                placeholder="Например: Летняя кампания 2026"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Название версии</label>
              <input
                type="text"
                value={formVersionName}
                onChange={(e) => setFormVersionName(e.target.value)}
                className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500"
                placeholder="Версия 2.1"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Описание</label>
              <textarea
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500"
                rows={2}
                placeholder="Краткое описание изменений"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Системный промпт *</label>
              <textarea
                value={formPrompt}
                onChange={(e) => setFormPrompt(e.target.value)}
                className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                rows={10}
                placeholder="Ты - контент-менеджер бренда GLAME..."
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleCreate}
                disabled={loading || !formName.trim() || !formPrompt.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {loading ? 'Создание...' : 'Создать версию'}
              </button>
              <button
                onClick={() => {
                  resetForm();
                  setIsCreating(false);
                }}
                className="px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400"
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Active Version Info */}
      {activeVersion && (
        <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded">
          <div className="flex justify-between items-start">
            <div>
              <h3 className="font-medium text-green-800">Активная версия: {activeVersion.name}</h3>
              <p className="text-sm text-green-600 mt-1">
                Версия {activeVersion.version} • Создана {new Date(activeVersion.created_at).toLocaleDateString('ru-RU')}
              </p>
              {activeVersion.description && (
                <p className="text-sm text-gray-600 mt-2">{activeVersion.description}</p>
              )}
            </div>
            <span className="px-3 py-1 text-sm font-medium bg-green-600 text-white rounded">Активна</span>
          </div>
        </div>
      )}

      {/* Versions List */}
      <div className="space-y-3">
        <h3 className="font-medium text-gray-700">Все версии</h3>
        {versions.length === 0 ? (
          <p className="text-gray-500 text-center py-8">Нет созданных версий промптов</p>
        ) : (
          versions.map((version) => (
            <div
              key={version.id}
              className={`p-4 border rounded transition-colors ${
                version.is_active ? 'border-green-300 bg-green-50' : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h4 className="font-medium">{version.name}</h4>
                    {getStatusBadge(version)}
                    <span className="text-sm text-gray-500">v{version.version}</span>
                  </div>
                  {version.version_name && (
                    <p className="text-sm text-gray-600 mt-1">{version.version_name}</p>
                  )}
                  {version.description && (
                    <p className="text-sm text-gray-500 mt-1">{version.description}</p>
                  )}
                  {version.marketer_feedback && (
                    <div className="mt-2 p-2 bg-yellow-50 border border-yellow-200 rounded text-sm">
                      <span className="font-medium">Обратная связь маркетолога:</span> {version.marketer_feedback}
                    </div>
                  )}
                </div>
                <div className="flex flex-col gap-2 ml-4">
                  {!version.is_active && (
                    <button
                      onClick={() => handleActivate(version.id)}
                      disabled={loading}
                      className="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                    >
                      Активировать
                    </button>
                  )}
                  {!version.is_active && version.marketer_review_status !== 'pending' && !isMarketer && (
                    <button
                      onClick={() => handleSubmitForReview(version.id)}
                      disabled={loading}
                      className="px-3 py-1 text-sm bg-yellow-600 text-white rounded hover:bg-yellow-700 disabled:opacity-50"
                    >
                      На ревью
                    </button>
                  )}
                  {isMarketer && version.marketer_review_status === 'pending' && (
                    <>
                      <button
                        onClick={() => handleReview(version.id, 'approved')}
                        disabled={loading}
                        className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                      >
                        Утвердить
                      </button>
                      <button
                        onClick={() => handleReview(version.id, 'rejected')}
                        disabled={loading}
                        className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                      >
                        Отклонить
                      </button>
                      <button
                        onClick={() => handleReview(version.id, 'needs_revision')}
                        disabled={loading}
                        className="px-3 py-1 text-sm bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50"
                      >
                        На доработку
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => handleOpenEditModal(version)}
                    className="px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                  >
                    Редактировать
                  </button>
                  <button
                    onClick={() => loadHistory(version.id)}
                    className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
                  >
                    История
                  </button>
                </div>
              </div>

              {/* History Modal */}
              {showHistory === version.id && (
                <div className="mt-4 p-4 bg-gray-50 border border-gray-200 rounded">
                  <div className="flex justify-between items-center mb-3">
                    <h5 className="font-medium">История изменений</h5>
                    <button
                      onClick={() => setShowHistory(null)}
                      className="text-gray-500 hover:text-gray-700"
                    >
                      ✕
                    </button>
                  </div>
                  {history.length === 0 ? (
                    <p className="text-gray-500 text-sm">Нет записей в истории</p>
                  ) : (
                    <div className="space-y-2 max-h-60 overflow-y-auto">
                      {history.map((item) => (
                        <div key={item.id} className="p-2 bg-white border rounded text-sm">
                          <div className="flex justify-between">
                            <span className="font-medium">{item.change_type}</span>
                            <span className="text-gray-500">
                              {new Date(item.changed_at).toLocaleString('ru-RU')}
                            </span>
                          </div>
                          {item.change_comment && (
                            <p className="text-gray-600 mt-1">{item.change_comment}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Generation Requests */}
      {generationRequests.length > 0 && (
        <div className="mt-6">
          <h3 className="font-medium text-gray-700 mb-3">История генераций</h3>
          <div className="space-y-2">
            {generationRequests.slice(0, 5).map((req) => (
              <div
                key={req.id}
                className="p-3 border border-gray-200 rounded text-sm flex justify-between items-center"
              >
                <div>
                  <p className="font-medium truncate max-w-md">{req.user_description}</p>
                  <p className="text-gray-500 text-xs mt-1">
                    {new Date(req.created_at).toLocaleString('ru-RU')} • {req.status}
                  </p>
                </div>
                {req.status === 'completed' && req.generated_prompt && (
                  <button
                    onClick={() => {
                      setGeneratedPrompt(req.generated_prompt || '');
                      setFormPrompt(req.generated_prompt || '');
                      setIsCreating(true);
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    className="px-3 py-1 bg-purple-600 text-white rounded hover:bg-purple-700 text-xs"
                  >
                    Использовать
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

    {/* Edit Modal */}
    {showEditModal && (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[90vh] overflow-hidden">
          <div className="p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-semibold">Редактирование промпта</h3>
              <button
                onClick={() => setShowEditModal(false)}
                className="text-gray-500 hover:text-gray-700 text-2xl"
              >
                &times;
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Название *</label>
                <input
                  type="text"
                  value={editFormName}
                  onChange={(e) => setEditFormName(e.target.value)}
                  className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500"
                  placeholder="Например: Летняя кампания 2026"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Название версии</label>
                <input
                  type="text"
                  value={editFormVersionName}
                  onChange={(e) => setEditFormVersionName(e.target.value)}
                  className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500"
                  placeholder="Версия 2.1"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Описание</label>
                <textarea
                  value={editFormDescription}
                  onChange={(e) => setEditFormDescription(e.target.value)}
                  className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500"
                  rows={2}
                  placeholder="Краткое описание изменений"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Системный промпт *</label>
                <textarea
                  value={editFormPrompt}
                  onChange={(e) => setEditFormPrompt(e.target.value)}
                  className="w-full p-2 border rounded focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                  rows={15}
                  placeholder="Ты - контент-менеджер бренда GLAME..."
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowEditModal(false)}
                className="px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400"
              >
                Отмена
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={isSavingEdit || !editFormName.trim() || !editFormPrompt.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {isSavingEdit ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      </div>
    )}
  </div>
);
}
