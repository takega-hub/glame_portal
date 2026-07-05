'use client';

import { useState, useEffect, useRef } from 'react';
import { api } from '@/lib/api';
import { Look, LookWithProducts } from '@/types';
import type { DigitalModelInfo } from '@/lib/api';
import LookCard from '@/components/looks/LookCard';
import LookGenerator from '@/components/looks/LookGenerator';
import PhotoTryOn from '@/components/looks/PhotoTryOn';
import ManualLookCreator from '@/components/looks/ManualLookCreator';

export default function LooksPage() {
  const [looks, setLooks] = useState<Look[]>([]);
  const [digitalModels, setDigitalModels] = useState<DigitalModelInfo[]>([]);
  const [selectedDigitalModel, setSelectedDigitalModel] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'list' | 'generate' | 'manual' | 'tryon'>('list');
  const [selectedLookId, setSelectedLookId] = useState<string | undefined>();
  const [portfolioSlideIndex, setPortfolioSlideIndex] = useState<number | null>(null);
  const [deletingPortfolioUrl, setDeletingPortfolioUrl] = useState<string | null>(null);
  
  // Состояния для управления моделями
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newModelName, setNewModelName] = useState('');
  const [creatingModel, setCreatingModel] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingModel, setEditingModel] = useState<DigitalModelInfo | null>(null);
  const [uploadingImages, setUploadingImages] = useState(false);
  const [deletingSourceImage, setDeletingSourceImage] = useState<string | null>(null);
  const [deletingModel, setDeletingModel] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedModel = digitalModels.find((m) => m.id === selectedDigitalModel) || null;
  const portfolioImages = selectedModel?.portfolio_images || [];

  const loadLooks = () => {
    setLoading(true);
    setError(null);

    api
      .getLooks({
        limit: 100,
        digital_model: selectedDigitalModel || undefined,
      })
      .then((data) => {
        setLooks(Array.isArray(data) ? data : []);
      })
      .catch((e: any) => {
        const status = e?.response?.status;
        const detail = e?.response?.data?.detail;
        setError(detail || (status ? `Ошибка загрузки (HTTP ${status})` : 'Не удалось загрузить образы'));
      })
      .finally(() => {
        setLoading(false);
      });
  };

  const loadDigitalModels = () => {
    api
      .getDigitalModels()
      .then((data) => {
        const models = Array.isArray(data) ? data : [];
        setDigitalModels(models);
        if (!selectedDigitalModel && models.length > 0) {
          setSelectedDigitalModel(models[0].id);
        }
      })
      .catch((e: any) => {
        console.error('Ошибка загрузки цифровых моделей:', e);
      });
  };

  useEffect(() => {
    loadDigitalModels();
  }, []);

  useEffect(() => {
    loadLooks();
  }, [selectedDigitalModel]);

  const handleLookGenerated = (_look?: LookWithProducts) => {
    loadLooks();
    loadDigitalModels();
    setActiveTab('list');
  };

  const handleTryOnClick = (lookId: string) => {
    setSelectedLookId(lookId);
    setActiveTab('tryon');
  };

  const handleTryOnComplete = () => {
    loadLooks();
  };

  const openPortfolioSlider = (index: number) => {
    setPortfolioSlideIndex(index);
  };

  const closePortfolioSlider = () => {
    setPortfolioSlideIndex(null);
  };

  const showPrevSlide = () => {
    if (!portfolioImages.length || portfolioSlideIndex === null) return;
    setPortfolioSlideIndex((portfolioSlideIndex - 1 + portfolioImages.length) % portfolioImages.length);
  };

  const showNextSlide = () => {
    if (!portfolioImages.length || portfolioSlideIndex === null) return;
    setPortfolioSlideIndex((portfolioSlideIndex + 1) % portfolioImages.length);
  };

  const handleDeletePortfolioImage = async (url: string) => {
    if (!selectedModel) return;
    const confirmed = window.confirm('Удалить это изображение из портфолио модели? Действие необратимо.');
    if (!confirmed) return;

    setDeletingPortfolioUrl(url);
    setError(null);
    try {
      await api.deleteModelPortfolioImage(selectedModel.id, url);
      await api.getDigitalModels().then((data) => {
        const models = Array.isArray(data) ? data : [];
        setDigitalModels(models);
      });
      if (portfolioSlideIndex !== null) {
        setPortfolioSlideIndex(null);
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(detail || 'Не удалось удалить изображение из портфолио');
    } finally {
      setDeletingPortfolioUrl(null);
    }
  };

  const handleDeleteCurrentPortfolioImage = async () => {
    if (portfolioSlideIndex === null || !portfolioImages.length) return;
    const currentUrl = portfolioImages[portfolioSlideIndex];
    await handleDeletePortfolioImage(currentUrl);
  };

  // Создание новой модели
  const handleCreateModel = async () => {
    if (!newModelName.trim()) {
      setError('Введите имя модели');
      return;
    }
    
    // Валидация имени
    if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(newModelName.trim())) {
      setError('Имя модели должно начинаться с латинской буквы и содержать только латинские буквы, цифры, подчеркивания и дефисы');
      return;
    }

    setCreatingModel(true);
    setError(null);
    try {
      await api.createDigitalModel(newModelName.trim());
      setShowCreateModal(false);
      setNewModelName('');
      await loadDigitalModels();
      // Выбираем созданную модель
      const newModelId = newModelName.trim().toLowerCase();
      setSelectedDigitalModel(newModelId);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(detail || 'Не удалось создать модель');
    } finally {
      setCreatingModel(false);
    }
  };

  // Удаление модели
  const handleDeleteModel = async () => {
    if (!editingModel) return;
    const confirmed = window.confirm(
      `Удалить модель '${editingModel.name}' полностью?\n\n` +
      'Это удалит:\n' +
      '- Все исходные фотографии модели\n' +
      '- Все сгенерированные образы этой модели\n\n' +
      'Действие необратимо!'
    );
    if (!confirmed) return;

    setDeletingModel(true);
    setError(null);
    try {
      await api.deleteDigitalModel(editingModel.id);
      setShowEditModal(false);
      setEditingModel(null);
      if (selectedDigitalModel === editingModel.id) {
        setSelectedDigitalModel(null);
      }
      await loadDigitalModels();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(detail || 'Не удалось удалить модель');
    } finally {
      setDeletingModel(false);
    }
  };

  // Открытие модалки редактирования
  const openEditModal = (model: DigitalModelInfo, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingModel(model);
    setShowEditModal(true);
  };

  // Загрузка исходных фото
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!editingModel || !e.target.files || e.target.files.length === 0) return;
    
    const files = Array.from(e.target.files);
    const allowedTypes = ['image/jpeg', 'image/png', 'image/webp'];
    const invalidFiles = files.filter(f => !allowedTypes.includes(f.type));
    
    if (invalidFiles.length > 0) {
      setError('Поддерживаются только файлы JPG, PNG и WebP');
      return;
    }

    setUploadingImages(true);
    setError(null);
    try {
      await api.uploadModelSourceImages(editingModel.id, files);
      await loadDigitalModels();
      // Обновляем editingModel
      const updatedModel = digitalModels.find(m => m.id === editingModel.id);
      if (updatedModel) {
        setEditingModel(updatedModel);
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(detail || 'Не удалось загрузить изображения');
    } finally {
      setUploadingImages(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  // Удаление исходного фото
  const handleDeleteSourceImage = async (imagePath: string) => {
    if (!editingModel) return;
    const filename = imagePath.split('/').pop();
    if (!filename) return;

    const confirmed = window.confirm('Удалить это исходное фото? Действие необратимо.');
    if (!confirmed) return;

    setDeletingSourceImage(imagePath);
    setError(null);
    try {
      await api.deleteModelSourceImage(editingModel.id, filename);
      await loadDigitalModels();
      // Обновляем editingModel
      const updatedModel = digitalModels.find(m => m.id === editingModel.id);
      if (updatedModel) {
        setEditingModel(updatedModel);
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(detail || 'Не удалось удалить изображение');
    } finally {
      setDeletingSourceImage(null);
    }
  };

  return (
    <main className="min-h-screen bg-concrete-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-concrete-900">Образы</h1>
          <p className="mt-2 text-concrete-600">
            Готовые образы и стилистические решения от GLAME
          </p>
        </div>

        {/* Панель цифровых моделей (ядро + портфолио) */}
        <div className="mb-6 rounded-lg border border-concrete-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-concrete-900">Цифровые модели</h2>
              <p className="text-sm text-concrete-600">
                Ядро: исходные фото в `backend/static/models`. Портфолио: сгенерированные образы выбранной модели.
              </p>
            </div>
            <button
              onClick={() => setShowCreateModal(true)}
              className="rounded-lg bg-gold-500 px-4 py-2 text-sm font-medium text-white hover:bg-gold-600 transition"
            >
              + Добавить модель
            </button>
          </div>

          {digitalModels.length === 0 ? (
            <div className="rounded-lg border border-dashed border-concrete-300 bg-concrete-50 p-6 text-center">
              <p className="text-sm text-concrete-500 mb-2">
                Пока нет цифровых моделей
              </p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="text-sm text-gold-600 hover:text-gold-700 font-medium"
              >
                Создать первую модель
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
              {digitalModels.map((model) => {
                const isSelected = selectedDigitalModel === model.id;
                const isRealShootModel = model.id === 'real_shoot';
                return (
                  <div
                    key={model.id}
                    className={`rounded-lg border p-3 text-left transition cursor-pointer ${
                      isSelected
                        ? 'border-gold-500 bg-gold-50'
                        : 'border-concrete-200 bg-white hover:border-concrete-300'
                    }`}
                    onClick={() => {
                      setSelectedDigitalModel(model.id);
                      setActiveTab('list');
                    }}
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <p className="font-medium text-concrete-900">{model.name}</p>
                      <div className="flex items-center gap-2">
                        {isSelected && (
                          <span className="rounded-full bg-gold-500 px-2 py-0.5 text-xs text-white">Выбрана</span>
                        )}
                        {!isRealShootModel && (
                          <button
                            onClick={(e) => openEditModal(model, e)}
                            className="rounded-md p-1 text-concrete-400 hover:bg-concrete-100 hover:text-concrete-600 transition"
                            title="Редактировать модель"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            </svg>
                          </button>
                        )}
                      </div>
                    </div>
                    {model.source_images?.[0] ? (
                      <img
                        src={model.source_images[0]}
                        alt={model.name}
                        className="mb-2 h-40 w-full rounded-md object-cover"
                      />
                    ) : (
                      <div className="mb-2 flex h-40 w-full items-center justify-center rounded-md bg-concrete-100 text-sm text-concrete-500">
                        {isRealShootModel ? 'Все ручные образы реальной съемки' : 'Нет фото в ядре'}
                      </div>
                    )}
                    <div className="text-xs text-concrete-700">
                      <p>Ядро: {model.source_images_count} фото</p>
                      <p>Портфолио: {model.portfolio_images_count} изображений</p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Табы */}
        <div className="mb-6 border-b border-concrete-200">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('list')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'list'
                  ? 'border-gold-500 text-gold-600'
                  : 'border-transparent text-concrete-700 hover:text-concrete-900 hover:border-concrete-300'
              }`}
            >
              Все образы
            </button>
            <button
              onClick={() => setActiveTab('generate')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'generate'
                  ? 'border-gold-500 text-gold-600'
                  : 'border-transparent text-concrete-700 hover:text-concrete-900 hover:border-concrete-300'
              }`}
            >
              Генерация образа
            </button>
            <button
              onClick={() => setActiveTab('manual')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'manual'
                  ? 'border-gold-500 text-gold-600'
                  : 'border-transparent text-concrete-700 hover:text-concrete-900 hover:border-concrete-300'
              }`}
            >
              Создать образ
            </button>
            <button
              onClick={() => setActiveTab('tryon')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'tryon'
                  ? 'border-gold-500 text-gold-600'
                  : 'border-transparent text-concrete-700 hover:text-concrete-900 hover:border-concrete-300'
              }`}
            >
              Примерка на фото
            </button>
          </nav>
        </div>

        {/* Контент табов */}
        {activeTab === 'list' && (
          <>
            {selectedModel && (
              <div className="mb-6 rounded-lg border border-concrete-200 bg-white p-4 shadow-sm">
                <h3 className="text-base font-semibold text-concrete-900">
                  Портфолио модели: {selectedModel.name}
                </h3>
                <p className="mt-1 text-sm text-concrete-600">
                  Нажатие на карточку модели открывает это портфолио. Здесь объединены образы и контент-генерации.
                </p>
                {selectedModel.portfolio_images?.length ? (
                  <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
                    {selectedModel.portfolio_images.map((url, idx) => (
                      <div key={`${url}-${idx}`} className="overflow-hidden rounded-md border border-concrete-200">
                        <button
                          onClick={() => openPortfolioSlider(idx)}
                          className="block w-full text-left"
                        >
                          <img
                            src={url}
                            alt={`${selectedModel.name} portfolio ${idx + 1}`}
                            className="h-36 w-full object-cover transition hover:scale-[1.02]"
                          />
                        </button>
                        <div className="p-2">
                          <button
                            onClick={() => void handleDeletePortfolioImage(url)}
                            disabled={deletingPortfolioUrl === url}
                            className="w-full rounded-md bg-red-600/90 px-2 py-1.5 text-xs font-medium text-white hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-60"
                            title="Удалить из портфолио"
                            aria-label="Удалить из портфолио"
                          >
                            {deletingPortfolioUrl === url ? 'Удаление...' : 'Удалить'}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-concrete-500">
                    Для этой модели пока не найдено изображений в портфолио.
                  </p>
                )}
              </div>
            )}
            {loading ? (
              <div className="bg-white rounded-lg shadow-concrete p-8 text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gold-500 mx-auto"></div>
                <p className="text-concrete-500 mt-4">Загрузка образов...</p>
              </div>
            ) : error ? (
              <div className="bg-white rounded-lg shadow-concrete p-8">
                <p className="text-red-700 font-medium">Ошибка</p>
                <p className="text-red-600 text-sm mt-1">{error}</p>
              </div>
            ) : looks.length === 0 ? (
              <div className="bg-white rounded-lg shadow-concrete p-8 text-center">
                <p className="text-concrete-500 text-lg">
                  Образы будут доступны после создания через AI Stylist или генерацию
                </p>
                <p className="text-concrete-400 text-sm mt-2">
                  Используйте вкладку &quot;Генерация образа&quot; для создания персонализированных образов
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {looks.map((look) => (
                  <LookCard
                    key={look.id}
                    look={look}
                    showTryOn={true}
                    onTryOnClick={handleTryOnClick}
                  />
                ))}
              </div>
            )}
          </>
        )}

        {activeTab === 'generate' && (
          <LookGenerator onLookGenerated={handleLookGenerated} selectedDigitalModel={selectedDigitalModel || undefined} />
        )}

        {activeTab === 'manual' && (
          <ManualLookCreator
            onLookCreated={handleLookGenerated}
            selectedDigitalModel={selectedDigitalModel || undefined}
          />
        )}

        {activeTab === 'tryon' && (
          <PhotoTryOn lookId={selectedLookId} onTryOnComplete={handleTryOnComplete} />
        )}

        {/* Модальное окно создания модели */}
        {showCreateModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
              <h3 className="text-lg font-semibold text-concrete-900 mb-4">
                Создание новой цифровой модели
              </h3>
              <div className="mb-4">
                <label className="block text-sm font-medium text-concrete-700 mb-2">
                  Имя модели (латиница)
                </label>
                <input
                  type="text"
                  value={newModelName}
                  onChange={(e) => setNewModelName(e.target.value)}
                  placeholder="Например: Elena, Model_01"
                  className="w-full rounded-lg border border-concrete-300 px-3 py-2 text-sm focus:border-gold-500 focus:outline-none"
                />
                <p className="mt-1 text-xs text-concrete-500">
                  Только латинские буквы, цифры, подчеркивания и дефисы. Начинайте с буквы.
                </p>
              </div>
              {error && (
                <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
                  {error}
                </div>
              )}
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowCreateModal(false);
                    setNewModelName('');
                    setError(null);
                  }}
                  className="rounded-lg px-4 py-2 text-sm font-medium text-concrete-600 hover:bg-concrete-100"
                >
                  Отмена
                </button>
                <button
                  onClick={handleCreateModel}
                  disabled={creatingModel}
                  className="rounded-lg bg-gold-500 px-4 py-2 text-sm font-medium text-white hover:bg-gold-600 disabled:opacity-60"
                >
                  {creatingModel ? 'Создание...' : 'Создать модель'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Модальное окно редактирования модели */}
        {showEditModal && editingModel && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-concrete-900">
                  Редактирование модели: {editingModel.name}
                </h3>
                <button
                  onClick={() => {
                    setShowEditModal(false);
                    setEditingModel(null);
                    setError(null);
                  }}
                  className="rounded-md p-1 text-concrete-400 hover:bg-concrete-100"
                >
                  ✕
                </button>
              </div>

              {error && (
                <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              {/* Исходные фото */}
              <div className="mb-6">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-medium text-concrete-900">Исходные фотографии</h4>
                  <div>
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileSelect}
                      accept=".jpg,.jpeg,.png,.webp"
                      multiple
                      className="hidden"
                    />
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploadingImages}
                      className="rounded-lg bg-gold-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-gold-600 disabled:opacity-60"
                    >
                      {uploadingImages ? 'Загрузка...' : '+ Добавить фото'}
                    </button>
                  </div>
                </div>

                {editingModel.source_images?.length ? (
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                    {editingModel.source_images.map((imgPath, idx) => (
                      <div key={`${imgPath}-${idx}`} className="relative group">
                        <img
                          src={imgPath}
                          alt={`Source ${idx + 1}`}
                          className="h-32 w-full rounded-md object-cover"
                        />
                        <button
                          onClick={() => handleDeleteSourceImage(imgPath)}
                          disabled={deletingSourceImage === imgPath}
                          className="absolute top-2 right-2 rounded-full bg-red-600/90 p-1.5 text-white opacity-0 group-hover:opacity-100 transition hover:bg-red-600 disabled:opacity-60"
                          title="Удалить фото"
                        >
                          {deletingSourceImage === imgPath ? (
                            <span className="block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                          ) : (
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          )}
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-lg border border-dashed border-concrete-300 bg-concrete-50 p-6 text-center">
                    <p className="text-sm text-concrete-500 mb-2">
                      Нет исходных фотографий
                    </p>
                    <p className="text-xs text-concrete-400">
                      Загрузите фотографии типажа модели для генерации образов
                    </p>
                  </div>
                )}
              </div>

              {/* Удаление модели */}
              <div className="border-t border-concrete-200 pt-4">
                <h4 className="font-medium text-red-600 mb-2">Опасная зона</h4>
                <p className="text-sm text-concrete-600 mb-3">
                  Удаление модели приведет к безвозвратной потере всех исходных фотографий и сгенерированных образов.
                </p>
                <button
                  onClick={handleDeleteModel}
                  disabled={deletingModel}
                  className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                >
                  {deletingModel ? 'Удаление...' : 'Удалить модель'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Полноэкранный просмотр портфолио модели */}
        {portfolioSlideIndex !== null && portfolioImages.length > 0 && (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm">
            <div className="mx-auto flex h-full w-full max-w-6xl items-center justify-center px-4 py-6">
              <button
                onClick={closePortfolioSlider}
                className="absolute right-6 top-6 z-20 rounded-full bg-white/20 px-3 py-2 text-white hover:bg-white/30"
                aria-label="Закрыть слайдшоу"
              >
                ✕
              </button>

              {portfolioImages.length > 1 && (
                <button
                  onClick={showPrevSlide}
                  className="absolute left-4 rounded-full bg-white/20 px-3 py-2 text-2xl text-white hover:bg-white/30"
                  aria-label="Предыдущий слайд"
                >
                  ‹
                </button>
              )}

              <div className="w-full">
                <img
                  src={portfolioImages[portfolioSlideIndex]}
                  alt={`${selectedModel?.name || 'Model'} slide ${portfolioSlideIndex + 1}`}
                  className="mx-auto max-h-[72vh] w-auto max-w-full rounded-xl object-contain shadow-2xl"
                />

                <div className="mt-4 text-center text-sm text-white/90">
                  {selectedModel?.name} • {portfolioSlideIndex + 1} / {portfolioImages.length}
                </div>

                <div className="mt-3 flex items-center justify-center">
                  <button
                    onClick={() => void handleDeleteCurrentPortfolioImage()}
                    disabled={deletingPortfolioUrl === portfolioImages[portfolioSlideIndex]}
                    className="rounded-full bg-red-600/85 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-60"
                    aria-label="Удалить текущее изображение из портфолио"
                    title="Удалить текущее изображение"
                  >
                    {deletingPortfolioUrl === portfolioImages[portfolioSlideIndex] ? 'Удаление...' : 'Удалить это фото'}
                  </button>
                </div>

                {portfolioImages.length > 1 && (
                  <div className="mx-auto mt-4 flex max-w-4xl gap-2 overflow-x-auto pb-2">
                    {portfolioImages.map((thumb, idx) => (
                      <button
                        key={`${thumb}-thumb-${idx}`}
                        onClick={() => setPortfolioSlideIndex(idx)}
                        className={`h-16 w-16 shrink-0 overflow-hidden rounded-md border ${
                          idx === portfolioSlideIndex ? 'border-gold-400' : 'border-white/20'
                        }`}
                        aria-label={`Слайд ${idx + 1}`}
                      >
                        <img src={thumb} alt={`Thumbnail ${idx + 1}`} className="h-full w-full object-cover" />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {portfolioImages.length > 1 && (
                <button
                  onClick={showNextSlide}
                  className="absolute right-4 rounded-full bg-white/20 px-3 py-2 text-2xl text-white hover:bg-white/30"
                  aria-label="Следующий слайд"
                >
                  ›
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
