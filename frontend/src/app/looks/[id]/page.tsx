'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { LookWithProducts } from '@/types';
import type { DigitalModelInfo } from '@/lib/api';
import PhotoTryOn from '@/components/looks/PhotoTryOn';
import ProductCard from '@/components/products/ProductCard';
import Link from 'next/link';

export default function LookDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const lookId = params.id as string;
  
  const [look, setLook] = useState<LookWithProducts | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [showTryOn, setShowTryOn] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [regeneratingImage, setRegeneratingImage] = useState(false);
  const [digitalModels, setDigitalModels] = useState<DigitalModelInfo[]>([]);
  const [imageGenerationMode, setImageGenerationMode] = useState<'default' | 'digital'>('digital');
  const [selectedDigitalModel, setSelectedDigitalModel] = useState<string>('');
  const [deleting, setDeleting] = useState(false);
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [deletingImageIndex, setDeletingImageIndex] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({
    name: '',
    style: '',
    mood: '',
    description: '',
  });

  useEffect(() => {
    if (!lookId) return;

    setLoading(true);
    setError(null);

    api
      .getLook(lookId)
      .then((data) => {
        setLook(data as LookWithProducts);
        setCurrentImageIndex(data.current_image_index ?? 0);
      })
      .catch((e: any) => {
        const status = e?.response?.status;
        const detail = e?.response?.data?.detail;
        setError(detail || (status ? `Ошибка загрузки (HTTP ${status})` : 'Не удалось загрузить образ'));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [lookId]);

  useEffect(() => {
    api
      .getDigitalModels()
      .then((data) => {
        const models = Array.isArray(data) ? data : [];
        setDigitalModels(models);
        if (models.length > 0) {
          setSelectedDigitalModel((prev) => prev || models[0].id);
        }
      })
      .catch((e) => {
        console.error('Ошибка загрузки цифровых моделей:', e);
      });
  }, []);

  const handleApprove = async () => {
    if (!look || look.approval_status === 'approved') return;
    
    setApproving(true);
    try {
      await api.approveLook(look.id);
      setLook({ ...look, approval_status: 'approved' });
    } catch (error) {
      console.error('Ошибка при одобрении образа:', error);
    } finally {
      setApproving(false);
    }
  };

  const handleEdit = () => {
    if (!look) return;
    setEditForm({
      name: look.name || '',
      style: look.style || '',
      mood: look.mood || '',
      description: look.description || '',
    });
    setEditing(true);
  };

  const handleSave = async () => {
    if (!look) return;
    
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateLook(look.id, {
        name: editForm.name,
        style: editForm.style,
        mood: editForm.mood,
        description: editForm.description,
      });
      setLook(updated as LookWithProducts);
      setEditing(false);
    } catch (error: any) {
      setError(error?.response?.data?.detail || 'Ошибка при сохранении образа');
    } finally {
      setSaving(false);
    }
  };

  const handleRegenerateImage = async () => {
    if (!look) return;
    if (imageGenerationMode === 'digital' && !selectedDigitalModel) {
      setError('Выберите цифровую модель для генерации изображения');
      return;
    }
    
    setRegeneratingImage(true);
    setError(null);
    try {
      // Используем отдельный endpoint для генерации изображения с увеличенным таймаутом
      const useDefaultModel = imageGenerationMode === 'default';
      const result = await api.generateLookImage(
        look.id,
        useDefaultModel,
        useDefaultModel ? undefined : selectedDigitalModel
      );
      
      // Обновляем образ с новым изображением
      if (result && result.image_url) {
        setLook((prevLook) => (prevLook ? { ...prevLook, image_url: result.image_url } : null));
      } else {
        // Если результат не содержит image_url, загружаем обновленный образ
        const updated = await api.getLook(look.id);
        setLook(updated as LookWithProducts);
      }
    } catch (error: any) {
      const errorMessage = error?.response?.data?.detail || error?.message || 'Ошибка при генерации изображения';
      setError(errorMessage);
      console.error('Ошибка при перегенерации изображения:', error);
    } finally {
      setRegeneratingImage(false);
    }
  };

  const handleCancelEdit = () => {
    setEditing(false);
    if (look) {
      setEditForm({
        name: look.name || '',
        style: look.style || '',
        mood: look.mood || '',
        description: look.description || '',
      });
    }
  };

  const handleDelete = async () => {
    if (!look) return;
    
    // Подтверждение удаления
    if (!confirm('Вы уверены, что хотите удалить этот образ? Это действие нельзя отменить.')) {
      return;
    }
    
    setDeleting(true);
    setError(null);
    try {
      await api.deleteLook(look.id);
      // Перенаправляем на список образов после успешного удаления
      router.push('/looks');
    } catch (error: any) {
      setError(error?.response?.data?.detail || 'Ошибка при удалении образа');
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <main className="min-h-screen bg-gray-50 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gold-500 mx-auto"></div>
            <p className="text-gray-500 mt-4">Загрузка образа...</p>
          </div>
        </div>
      </main>
    );
  }

  if (error || !look) {
    return (
      <main className="min-h-screen bg-gray-50 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-white rounded-lg shadow p-8">
            <p className="text-red-700 font-medium">Ошибка</p>
            <p className="text-red-600 text-sm mt-1">{error || 'Образ не найден'}</p>
            <button
              onClick={() => router.push('/looks')}
              className="mt-4 px-4 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition"
            >
              Вернуться к списку образов
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-6">
          <button
            onClick={() => router.push('/looks')}
            className="text-gray-600 hover:text-gray-900 mb-4"
          >
            ← Назад к образам
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Левая колонка: Изображение и информация */}
          <div className="space-y-6">
            {/* Карусель изображений */}
            <div className="bg-white rounded-lg shadow p-6">
              {(() => {
                // Получаем массив изображений
                const getImageUrls = (): string[] => {
                  if (look.image_urls && look.image_urls.length > 0) {
                    return look.image_urls.map((img: any) => {
                      if (typeof img === 'string') return img;
                      return img.url || img;
                    });
                  }
                  if (look.image_url) return [look.image_url];
                  return [];
                };

                const imageUrls = getImageUrls();
                const currentImage = imageUrls[currentImageIndex] || look.image_url;

                if (look.try_on_image_url) {
                  return (
                    <div className="relative">
                      <img
                        src={look.try_on_image_url}
                        alt={look.name}
                        className="w-full rounded-lg"
                      />
                      <span className="absolute top-4 right-4 px-3 py-1 bg-green-500 text-white text-sm rounded">
                        Примерка
                      </span>
                    </div>
                  );
                }

                if (currentImage) {
                  return (
                    <div className="relative">
                      <img
                        src={currentImage}
                        alt={look.name}
                        className={`w-full rounded-lg transition-opacity ${
                          regeneratingImage ? 'opacity-50' : 'opacity-100'
                        }`}
                      />
                      {regeneratingImage && (
                        <div className="absolute inset-0 bg-black/30 rounded-lg flex flex-col items-center justify-center">
                          <div className="animate-spin rounded-full h-16 w-16 border-4 border-white border-t-transparent mb-4"></div>
                          <p className="text-white text-lg font-medium">Генерация изображения...</p>
                          <p className="text-white/80 text-sm mt-2">Это может занять несколько минут</p>
                          <div className="mt-4 w-64 h-1 bg-white/20 rounded-full overflow-hidden">
                            <div className="h-full bg-white rounded-full animate-pulse" style={{ width: '60%' }}></div>
                          </div>
                        </div>
                      )}
                      {imageUrls.length > 1 && !regeneratingImage && (
                        <>
                          <button
                            onClick={() => setCurrentImageIndex((prev) => (prev > 0 ? prev - 1 : imageUrls.length - 1))}
                            className="absolute left-4 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full p-3 transition"
                            aria-label="Предыдущее изображение"
                          >
                            ←
                          </button>
                          <button
                            onClick={() => setCurrentImageIndex((prev) => (prev < imageUrls.length - 1 ? prev + 1 : 0))}
                            className="absolute right-4 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full p-3 transition"
                            aria-label="Следующее изображение"
                          >
                            →
                          </button>
                          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2">
                            {imageUrls.map((_, idx) => (
                              <button
                                key={idx}
                                onClick={() => setCurrentImageIndex(idx)}
                                className={`w-3 h-3 rounded-full transition ${
                                  idx === currentImageIndex ? 'bg-white' : 'bg-white/50'
                                }`}
                                aria-label={`Изображение ${idx + 1}`}
                              />
                            ))}
                          </div>
                          <div className="absolute top-4 right-4 bg-black/50 text-white text-sm px-3 py-1 rounded">
                            {currentImageIndex + 1} / {imageUrls.length}
                          </div>
                        </>
                      )}
                    </div>
                  );
                }

                return (
                  <div className="w-full h-96 bg-gray-200 rounded-lg flex flex-col items-center justify-center relative">
                    {regeneratingImage ? (
                      <>
                        <div className="animate-spin rounded-full h-16 w-16 border-4 border-gold-500 border-t-transparent mb-4"></div>
                        <p className="text-gray-700 text-lg font-medium">Генерация изображения...</p>
                        <p className="text-gray-500 text-sm mt-2">Это может занять несколько минут</p>
                        <div className="mt-4 w-64 h-1 bg-gray-300 rounded-full overflow-hidden">
                          <div className="h-full bg-gold-500 rounded-full animate-pulse" style={{ width: '60%' }}></div>
                        </div>
                      </>
                    ) : (
                      <span className="text-gray-400">Нет изображения</span>
                    )}
                  </div>
                );
              })()}
              
              {/* Кнопки для генерации/перегенерации изображения */}
              <div className="mt-4 space-y-3">
                <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                  <p className="mb-2 text-xs font-medium text-gray-700">Модель для генерации</p>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => setImageGenerationMode('digital')}
                      disabled={regeneratingImage}
                      className={`px-3 py-1.5 text-xs rounded border transition ${
                        imageGenerationMode === 'digital'
                          ? 'bg-gold-100 border-gold-400 text-gold-800'
                          : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-100'
                      } disabled:opacity-50`}
                    >
                      Цифровая модель
                    </button>
                    <button
                      onClick={() => setImageGenerationMode('default')}
                      disabled={regeneratingImage}
                      className={`px-3 py-1.5 text-xs rounded border transition ${
                        imageGenerationMode === 'default'
                          ? 'bg-indigo-100 border-indigo-400 text-indigo-800'
                          : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-100'
                      } disabled:opacity-50`}
                    >
                      Типовая модель
                    </button>
                  </div>
                  {imageGenerationMode === 'digital' && (
                    <div className="mt-2">
                      <select
                        value={selectedDigitalModel}
                        onChange={(e) => setSelectedDigitalModel(e.target.value)}
                        disabled={regeneratingImage || digitalModels.length === 0}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm bg-white text-gray-900 disabled:opacity-50"
                      >
                        {digitalModels.length === 0 ? (
                          <option value="">Нет доступных цифровых моделей</option>
                        ) : (
                          digitalModels.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.name}
                            </option>
                          ))
                        )}
                      </select>
                    </div>
                  )}
                </div>

                <div className="flex flex-col space-y-2">
                <button
                  onClick={handleRegenerateImage}
                  disabled={regeneratingImage}
                  className="w-full px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition disabled:opacity-50 text-sm flex items-center justify-center gap-2"
                >
                  {regeneratingImage ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                      <span>Генерация изображения...</span>
                    </>
                  ) : (
                    imageGenerationMode === 'default'
                      ? 'Сгенерировать на типовой модели'
                      : 'Сгенерировать на выбранной цифровой модели'
                  )}
                </button>
                </div>
              </div>

              {/* Галерея всех изображений с возможностью выбора основного и удаления */}
              {look.image_urls && look.image_urls.length > 0 && (
                <div className="mt-4">
                  <h3 className="text-sm font-medium text-gray-900 mb-2">Все изображения образа:</h3>
                  <div className="grid grid-cols-3 gap-2">
                    {look.image_urls.map((img: any, idx: number) => {
                      const imgUrl = typeof img === 'string' ? img : img.url || img;
                      const isMain = idx === (look.current_image_index ?? 0);
                      
                      return (
                        <div key={idx} className="relative group">
                          <img
                            src={imgUrl}
                            alt={`${look.name} - изображение ${idx + 1}`}
                            className={`w-full h-24 object-cover rounded-lg border-2 ${
                              isMain ? 'border-gold-500' : 'border-gray-200'
                            } cursor-pointer`}
                            onClick={() => setCurrentImageIndex(idx)}
                          />
                          {isMain && (
                            <span className="absolute top-1 left-1 bg-gold-500 text-white text-xs px-1 py-0.5 rounded">
                              Основное
                            </span>
                          )}
                          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/50 transition rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100">
                            <div className="flex gap-2">
                              {!isMain && (
                                <button
                                  onClick={async (e) => {
                                    e.stopPropagation();
                                    try {
                                      await api.setMainImage(look.id, idx);
                                      const updated = await api.getLook(look.id);
                                      setLook(updated as LookWithProducts);
                                      setCurrentImageIndex(idx);
                                    } catch (error: any) {
                                      setError(error?.response?.data?.detail || 'Ошибка при установке основного изображения');
                                    }
                                  }}
                                  className="px-2 py-1 bg-green-500 text-white text-xs rounded hover:bg-green-600"
                                  title="Сделать основным"
                                >
                                  ✓
                                </button>
                              )}
                              <button
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  if (confirm('Удалить это изображение?')) {
                                    setDeletingImageIndex(idx);
                                    try {
                                      await api.deleteLookImage(look.id, idx);
                                      const updated = await api.getLook(look.id);
                                      setLook(updated as LookWithProducts);
                                      // Обновляем индекс текущего изображения
                                      if (updated.image_urls && updated.image_urls.length > 0) {
                                        const newIndex = updated.current_image_index ?? 0;
                                        setCurrentImageIndex(newIndex);
                                      } else {
                                        setCurrentImageIndex(0);
                                      }
                                    } catch (error: any) {
                                      setError(error?.response?.data?.detail || 'Ошибка при удалении изображения');
                                    } finally {
                                      setDeletingImageIndex(null);
                                    }
                                  }
                                }}
                                disabled={deletingImageIndex === idx}
                                className="px-2 py-1 bg-red-500 text-white text-xs rounded hover:bg-red-600 disabled:opacity-50"
                                title="Удалить"
                              >
                                {deletingImageIndex === idx ? '...' : '×'}
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Информация об образе */}
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex justify-between items-start mb-4">
                {editing ? (
                  <input
                    type="text"
                    value={editForm.name}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                    className="text-2xl font-bold text-gray-900 border border-gray-300 rounded px-2 py-1 flex-1 mr-2"
                    placeholder="Название образа"
                  />
                ) : (
                  <h1 className="text-2xl font-bold text-gray-900">{look.name}</h1>
                )}
                {!editing && (
                  <button
                    onClick={handleEdit}
                    className="ml-4 px-3 py-1 text-sm bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition"
                  >
                    Редактировать
                  </button>
                )}
              </div>
              
              {editing ? (
                <div className="space-y-4 mb-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Стиль</label>
                    <input
                      type="text"
                      value={editForm.style}
                      onChange={(e) => setEditForm({ ...editForm, style: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                      placeholder="Стиль образа"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Настроение</label>
                    <input
                      type="text"
                      value={editForm.mood}
                      onChange={(e) => setEditForm({ ...editForm, mood: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                      placeholder="Настроение образа"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Описание</label>
                    <textarea
                      value={editForm.description}
                      onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                      placeholder="Описание образа"
                      rows={4}
                    />
                  </div>
                  <div className="flex space-x-2">
                    <button
                      onClick={handleSave}
                      disabled={saving}
                      className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition disabled:opacity-50"
                    >
                      {saving ? 'Сохранение...' : 'Сохранить'}
                    </button>
                    <button
                      onClick={handleCancelEdit}
                      disabled={saving}
                      className="px-4 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition disabled:opacity-50"
                    >
                      Отмена
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex flex-wrap gap-2 mb-4">
                {look.status === 'auto_generated' && (
                  <span className="px-3 py-1 bg-purple-100 text-purple-700 text-sm rounded">
                    AI Генерация
                  </span>
                )}
                {look.approval_status === 'approved' && (
                  <span className="px-3 py-1 bg-green-100 text-green-700 text-sm rounded">
                    Одобрен
                  </span>
                )}
                {look.approval_status === 'pending' && (
                  <span className="px-3 py-1 bg-yellow-100 text-yellow-700 text-sm rounded">
                    На рассмотрении
                  </span>
                )}
                {look.style && (
                  <span className="px-3 py-1 bg-gold-100 text-gold-700 text-sm rounded">
                    {look.style}
                  </span>
                )}
                {look.mood && (
                  <span className="px-3 py-1 bg-blue-100 text-blue-700 text-sm rounded">
                    {look.mood}
                  </span>
                )}
              </div>

                    {look.description && (
                      <p className="text-gray-900 mb-4">{look.description}</p>
                    )}
                  </>
              )}

              {/* Модные тренды */}
              {look.fashion_trends && look.fashion_trends.length > 0 && (
                <div className="mb-4">
                  <h3 className="font-semibold text-gray-900 mb-2">Использованные тренды:</h3>
                  <ul className="list-disc list-inside text-sm text-gray-900">
                    {look.fashion_trends.slice(0, 3).map((trend: any, idx: number) => (
                      <li key={idx} className="text-gray-900">{trend.name || trend}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Действия */}
              <div className="space-y-2">
                <button
                  onClick={() => setShowTryOn(!showTryOn)}
                  className="w-full px-4 py-2 bg-gold-500 text-white rounded-lg hover:bg-gold-600 transition shadow-gold"
                >
                  {showTryOn ? 'Скрыть примерку' : 'Примерка на фото'}
                </button>
                
                {look.status === 'auto_generated' && look.approval_status !== 'approved' && (
                  <button
                    onClick={handleApprove}
                    disabled={approving}
                    className="w-full px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition disabled:opacity-50"
                  >
                    {approving ? 'Одобрение...' : 'Одобрить образ'}
                  </button>
                )}
                
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="w-full px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition disabled:opacity-50"
                >
                  {deleting ? 'Удаление...' : 'Удалить образ'}
                </button>
              </div>
            </div>

            {/* Примерка */}
            {showTryOn && (
              <PhotoTryOn lookId={look.id} />
            )}
          </div>

          {/* Правая колонка: Товары */}
          <div>
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">
                Товары в образе ({look.products?.length || 0})
              </h2>
              
              {look.products && look.products.length > 0 ? (
                <div className="space-y-4">
                  {look.products.map((product) => (
                    <ProductCard key={product.id} product={product} />
                  ))}
                </div>
              ) : (
                <p className="text-gray-700">Товары не загружены</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
