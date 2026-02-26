'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Look, LookWithProducts } from '@/types';
import type { DigitalModelInfo } from '@/lib/api';
import LookCard from '@/components/looks/LookCard';
import LookGenerator from '@/components/looks/LookGenerator';
import PhotoTryOn from '@/components/looks/PhotoTryOn';

export default function LooksPage() {
  const [looks, setLooks] = useState<Look[]>([]);
  const [digitalModels, setDigitalModels] = useState<DigitalModelInfo[]>([]);
  const [selectedDigitalModel, setSelectedDigitalModel] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'list' | 'generate' | 'tryon'>('list');
  const [selectedLookId, setSelectedLookId] = useState<string | undefined>();
  const [portfolioSlideIndex, setPortfolioSlideIndex] = useState<number | null>(null);
  const [deletingPortfolioUrl, setDeletingPortfolioUrl] = useState<string | null>(null);
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

  const handleLookGenerated = (look: LookWithProducts) => {
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
          <div className="mb-3">
            <h2 className="text-base font-semibold text-concrete-900">Цифровые модели</h2>
            <p className="text-sm text-concrete-600">
              Ядро: исходные фото в `backend/static/models`. Портфолио: сгенерированные образы выбранной модели.
            </p>
          </div>

          {digitalModels.length === 0 ? (
            <p className="text-sm text-concrete-500">
              В `backend/static/models` пока нет моделей. Добавьте папку модели с исходными фото.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
              {digitalModels.map((model) => {
                const isSelected = selectedDigitalModel === model.id;
                return (
                  <button
                    key={model.id}
                    onClick={() => {
                      setSelectedDigitalModel(model.id);
                      setActiveTab('list');
                    }}
                    className={`rounded-lg border p-3 text-left transition ${
                      isSelected
                        ? 'border-gold-500 bg-gold-50'
                        : 'border-concrete-200 bg-white hover:border-concrete-300'
                    }`}
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <p className="font-medium text-concrete-900">{model.name}</p>
                      {isSelected && (
                        <span className="rounded-full bg-gold-500 px-2 py-0.5 text-xs text-white">Выбрана</span>
                      )}
                    </div>
                    {model.source_images?.[0] ? (
                      <img
                        src={model.source_images[0]}
                        alt={model.name}
                        className="mb-2 h-40 w-full rounded-md object-cover"
                      />
                    ) : (
                      <div className="mb-2 flex h-40 w-full items-center justify-center rounded-md bg-concrete-100 text-sm text-concrete-500">
                        Нет фото в ядре
                      </div>
                    )}
                    <div className="text-xs text-concrete-700">
                      <p>Ядро: {model.source_images_count} фото</p>
                      <p>Портфолио: {model.portfolio_images_count} изображений</p>
                    </div>
                  </button>
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
                      <div
                        key={`${url}-${idx}`}
                        className="group relative overflow-hidden rounded-md border border-concrete-200"
                      >
                        <button
                          onClick={() => openPortfolioSlider(idx)}
                          className="block w-full text-left"
                        >
                          <img
                            src={url}
                            alt={`${selectedModel.name} portfolio ${idx + 1}`}
                            className="h-36 w-full object-cover transition group-hover:scale-[1.02]"
                          />
                        </button>
                        <button
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            void handleDeletePortfolioImage(url);
                          }}
                          disabled={deletingPortfolioUrl === url}
                          className="absolute right-2 top-2 rounded-full bg-black/60 px-2 py-1 text-xs text-white hover:bg-black/75 disabled:cursor-not-allowed disabled:opacity-60"
                          title="Удалить из портфолио"
                          aria-label="Удалить из портфолио"
                        >
                          {deletingPortfolioUrl === url ? '...' : 'Удалить'}
                        </button>
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
                  Используйте вкладку "Генерация образа" для создания персонализированных образов
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

        {activeTab === 'tryon' && (
          <PhotoTryOn lookId={selectedLookId} onTryOnComplete={handleTryOnComplete} />
        )}

        {/* Полноэкранный просмотр портфолио модели */}
        {portfolioSlideIndex !== null && portfolioImages.length > 0 && (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm">
            <div className="mx-auto flex h-full w-full max-w-6xl items-center justify-center px-4 py-6">
              <button
                onClick={closePortfolioSlider}
                className="absolute right-6 top-6 rounded-full bg-white/20 px-3 py-2 text-white hover:bg-white/30"
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
