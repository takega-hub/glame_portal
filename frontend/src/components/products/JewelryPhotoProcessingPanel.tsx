'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { api, apiClient } from '@/lib/api';

type JewelryHistoryItem = {
  article: string;
  urls: string[];
  updated_at: string;
};

type JewelryProcessResult = {
  urls: string[];
  provider?: { runtime?: string; model?: string; profile?: string; quality?: string };
  prompt_used?: string | null;
};

type Props = {
  compact?: boolean;
};

const DEFAULT_JEWELRY_PROMPT = `Обработай предметное фото украшения GLAME в эстетике Net-a-Porter / Farfetch luxury jewelry catalog / Vogue Jewelry / Tiffany clean product photography.

Сохрани реальное изделие: не меняй форму, толщину, пропорции, геометрию, конструкцию, посадку, ракурс, камни, жемчуг, замки и реальные особенности украшения. Это должна быть ретушь исходного фото, а не генерация нового изделия и не CGI.

Сделай чистый белый или холодно-белый фон без бумаги, пятен, стола, рук, телефона, лишних объектов и грязных серых зон. Изделие строго по центру, с большим количеством воздуха вокруг. Масштаб реалистичный, без чрезмерного увеличения.

Свет мягкий студийный, премиальный, с аккуратными контролируемыми бликами. Тень короткая, мягкая, чистая, контактная, без грязного ореола.

Металл сделай дорогим и реалистичным: если золото — нейтральное luxury gold без оранжевости, кислотной желтизны и зеленцы; если серебро — холодное, чистое, полированное, не серое, не белесое и не пластиковое. Убери отражения телефона, рук, комнаты и грязные пятна, но сохрани живой объем металла.

Если есть жемчуг — сделай его натуральным, перламутровым, мягким и объемным, без пластика и мыльности. Если есть камни/Swarovski — добавь аккуратную четкость и премиальный блеск без дешевого glitter-эффекта.

Финальный формат: 1536 × 2048 px, вертикальный 3:4. Без текста, логотипов, интерфейса и декоративных элементов.`;

function imageFullUrl(url: string) {
  if (!url) return '';
  let normalized = url.trim();
  if (!normalized.startsWith('/')) {
    if (normalized.startsWith('look_images/')) normalized = `/${normalized}`;
    else if (normalized.startsWith('content_media/')) normalized = `/${normalized}`;
    else if (normalized.startsWith('jewelry_processed/')) normalized = `/static/${normalized}`;
    else return normalized;
  }

  if (normalized.startsWith('/look_images/')) {
    normalized = `/static${normalized}`;
  } else if (normalized.startsWith('/content_media/')) {
    normalized = `/static${normalized}`;
  }

  const apiBase = (process.env.NEXT_PUBLIC_API_URL || '').trim();
  const isAbsolute = apiBase.startsWith('http://') || apiBase.startsWith('https://');
  return isAbsolute ? `${apiBase}${normalized}` : normalized;
}

function formatDate(value: string) {
  if (!value) return '';
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function JewelryPhotoProcessingPanel({ compact = false }: Props) {
  const [article, setArticle] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultUrls, setResultUrls] = useState<string[] | null>(null);
  const [applyLoading, setApplyLoading] = useState(false);
  const [revisionDescription, setRevisionDescription] = useState('');
  const [promptOverride, setPromptOverride] = useState(DEFAULT_JEWELRY_PROMPT);
  const [promptUsed, setPromptUsed] = useState<string | null>(null);
  const [history, setHistory] = useState<JewelryHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);
  const [providerLabel, setProviderLabel] = useState('Hermes · GPT Image 2');
  const [showPromptEditor, setShowPromptEditor] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const inputPreviews = useMemo(
    () => files.map((file) => ({ file, url: URL.createObjectURL(file) })),
    [files]
  );

  useEffect(() => {
    return () => {
      inputPreviews.forEach((preview) => URL.revokeObjectURL(preview.url));
    };
  }, [inputPreviews]);

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const res = await apiClient.get<{ items: JewelryHistoryItem[] }>('/api/content/jewelry-photo/history');
      setHistory(Array.isArray(res.data?.items) ? res.data.items : []);
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  useEffect(() => {
    if (!lightboxUrl) return;
    const onEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLightboxUrl(null);
    };
    window.addEventListener('keydown', onEscape);
    return () => window.removeEventListener('keydown', onEscape);
  }, [lightboxUrl]);

  const currentPrompt = promptOverride.trim() || DEFAULT_JEWELRY_PROMPT;

  const processPhotos = async () => {
    if (!article.trim() || files.length === 0) return;
    setError(null);
    setProcessing(true);
    setPromptUsed(null);
    abortRef.current = new AbortController();
    try {
      const data: JewelryProcessResult = await api.processJewelryPhoto(
        files,
        article.trim(),
        abortRef.current.signal,
        revisionDescription.trim() || undefined,
        currentPrompt
      );
      setResultUrls(Array.isArray(data?.urls) ? data.urls : []);
      setPromptUsed(data?.prompt_used || currentPrompt);
      const provider = data?.provider;
      if (provider?.runtime === 'hermes') {
        setProviderLabel(`Hermes · ${provider.model || 'gpt-image-2'} · ${provider.profile || 'glame-jewelry-retoucher'}`);
      } else if (provider?.runtime) {
        setProviderLabel(`${provider.runtime} · ${provider.model || ''}`.trim());
      }
      await loadHistory();
    } catch (e: any) {
      if (e.name === 'CanceledError' || e.code === 'ERR_CANCELED') return;
      const msg = e.response?.data?.detail || e.message || 'Ошибка обработки фото';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      setResultUrls(null);
    } finally {
      setProcessing(false);
      abortRef.current = null;
    }
  };

  const cancelGeneration = () => {
    abortRef.current?.abort();
  };

  const reset = () => {
    setResultUrls(null);
    setPromptUsed(null);
    setError(null);
    setRevisionDescription('');
  };

  const regenerate = () => {
    setResultUrls(null);
    setPromptUsed(null);
    setError(null);
    processPhotos();
  };

  const applyToProduct = async (sourceArticle?: string, sourceUrls?: string[]) => {
    const targetArticle = (sourceArticle ?? article).trim();
    const list = sourceUrls ?? resultUrls ?? [];
    if (!targetArticle || list.length === 0) return;
    setApplyLoading(true);
    setError(null);
    try {
      await api.applyJewelryPhotoToProduct(targetArticle, list);
      alert(`Добавлено ${list.length} фото к карточке товара.`);
      if (!sourceUrls) setResultUrls(null);
      await loadHistory();
      setFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || 'Ошибка добавления к карточке';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setApplyLoading(false);
    }
  };

  const deleteHistoryFile = async (url: string) => {
    if (!confirm('Удалить это фото из истории?')) return;
    try {
      await apiClient.delete('/api/content/jewelry-photo/file', { params: { url } });
      await loadHistory();
      if (resultUrls?.includes(url)) {
        const next = resultUrls.filter((u) => u !== url);
        setResultUrls(next.length > 0 ? next : null);
      }
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || 'Ошибка удаления';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
  };

  const onFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = e.target.files ? Array.from(e.target.files) : [];
    if (list.length > 5) {
      setError('Максимум 5 фото за раз.');
      setFiles(list.slice(0, 5));
    } else {
      setError(null);
      setFiles(list);
    }
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <>
      <section className={`mt-6 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm ${compact ? 'p-0' : 'p-2'}`} id="jewelry-photo-section">
        <div className="border-b border-gray-100 bg-gradient-to-r from-white via-amber-50/40 to-indigo-50/40 p-5 lg:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gold-700">AI photo retouch</p>
              <h2 className="mt-1 text-2xl font-semibold text-gray-950">Обработка фото украшений</h2>
              <p className="mt-2 max-w-4xl text-sm leading-6 text-gray-600">
                Загрузите фото из магазина, проверьте крупный результат, при необходимости скорректируйте промпт или комментарий и только потом добавьте изображения в карточку товара.
              </p>
            </div>
            <span className="rounded-full border border-indigo-200 bg-white/80 px-3 py-1.5 text-xs font-medium text-indigo-700 shadow-sm">
              {providerLabel}
            </span>
          </div>
          <div className="mt-5 grid gap-3 text-sm text-gray-700 md:grid-cols-3">
            <div className="rounded-xl border border-white/80 bg-white/70 p-3 shadow-sm">1. Артикул + исходники до 5 фото</div>
            <div className="rounded-xl border border-white/80 bg-white/70 p-3 shadow-sm">2. Контроль промпта и пожеланий</div>
            <div className="rounded-xl border border-white/80 bg-white/70 p-3 shadow-sm">3. Крупная проверка перед применением</div>
          </div>
        </div>

        <div className="grid gap-0 xl:grid-cols-[420px_minmax(0,1fr)]">
          <div className="border-b border-gray-100 p-5 lg:p-6 xl:border-b-0 xl:border-r">
            <div className="space-y-5 xl:sticky xl:top-4">
              <div>
                <label className="mb-1 block text-sm font-semibold text-gray-800">Артикул изделия *</label>
                <input
                  type="text"
                  value={article}
                  onChange={(e) => setArticle(e.target.value)}
                  placeholder="Например: U10046"
                  className="w-full rounded-xl border border-gray-300 bg-white px-4 py-3 text-gray-950 shadow-sm focus:outline-none focus:ring-2 focus:ring-gold-500"
                />
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <label className="block text-sm font-semibold text-gray-800">Исходные фото</label>
                  <span className="text-xs text-gray-500">до 5 шт. · 10 MB</span>
                </div>
                <label className="flex min-h-[126px] cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed border-gold-300 bg-gold-50/50 px-4 py-5 text-center transition hover:bg-gold-50">
                  <span className="text-sm font-medium text-gold-800">Выбрать или заменить файлы</span>
                  <span className="mt-1 text-xs text-gray-500">JPG/PNG, лучше один чистый ракурс на фото</span>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/jpg"
                    multiple
                    onChange={onFilesChange}
                    className="sr-only"
                  />
                </label>

                {inputPreviews.length > 0 && (
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    {inputPreviews.map((preview, idx) => (
                      <div key={`${preview.file.name}-${idx}`} className="group relative overflow-hidden rounded-xl border border-gray-200 bg-gray-50">
                        <button
                          type="button"
                          onClick={() => setLightboxUrl(preview.url)}
                          className="block aspect-[3/4] w-full bg-white focus:outline-none focus:ring-2 focus:ring-gold-500 focus:ring-inset"
                          title="Открыть исходник"
                        >
                          <img src={preview.url} alt={preview.file.name} className="h-full w-full object-contain" />
                        </button>
                        <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-xs text-gray-600">
                          <span className="truncate">{preview.file.name}</span>
                          <button type="button" onClick={() => removeFile(idx)} className="text-red-600 hover:text-red-800" aria-label="Удалить">
                            ×
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">Промпт генерации</h3>
                    <p className="mt-1 text-xs text-gray-500">Редактируется перед запуском и отправляется именно в текущую генерацию.</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowPromptEditor((v) => !v)}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100"
                  >
                    {showPromptEditor ? 'Свернуть' : 'Открыть'}
                  </button>
                </div>
                {showPromptEditor && (
                  <div className="mt-3 space-y-3">
                    <textarea
                      value={promptOverride}
                      onChange={(e) => setPromptOverride(e.target.value)}
                      rows={11}
                      className="w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm leading-5 text-gray-900 focus:outline-none focus:ring-2 focus:ring-gold-500"
                    />
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setPromptOverride(DEFAULT_JEWELRY_PROMPT)}
                        className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-100"
                      >
                        Вернуть базовый
                      </button>
                      <button
                        type="button"
                        onClick={() => setPromptOverride((prev) => `${prev.trim()}\n\nОсобый контроль: сохранить артикул ${article || 'изделия'} максимально близко к исходному фото.`)}
                        className="rounded-lg border border-gold-300 bg-white px-3 py-1.5 text-xs text-gold-800 hover:bg-gold-50"
                      >
                        + контроль формы
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div>
                <label className="mb-1 block text-sm font-semibold text-gray-800">Комментарий к перегенерации</label>
                <textarea
                  value={revisionDescription}
                  onChange={(e) => setRevisionDescription(e.target.value)}
                  placeholder="Например: фон холоднее, тень мягче, больше воздуха вокруг изделия"
                  rows={3}
                  className="w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-gold-500"
                />
              </div>

              {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 p-3">
                  <p className="text-sm text-red-700">{error}</p>
                </div>
              )}

              {processing && (
                <div className="rounded-xl border border-gold-200 bg-gold-50/70 p-4">
                  <p className="mb-2 text-sm font-semibold text-gray-900">Hermes обрабатывает фото...</p>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
                    <div className="h-full w-[70%] animate-pulse rounded-full bg-gold-500" />
                  </div>
                  <p className="mt-2 text-xs text-gray-600">GPT Image 2 может занять несколько минут. Не закрывайте страницу.</p>
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={processPhotos}
                  disabled={processing || !article.trim() || files.length === 0}
                  className="rounded-xl bg-gold-600 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-gold-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {processing ? 'Обработка...' : 'Обработать фото'}
                </button>
                {processing && (
                  <button type="button" onClick={cancelGeneration} className="rounded-xl border border-red-300 px-4 py-3 text-sm text-red-700 hover:bg-red-50">
                    Отменить
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-6 p-5 lg:p-6">
            {resultUrls && resultUrls.length > 0 && (
              <div className="rounded-2xl border border-gold-200 bg-gold-50/40 p-4">
                <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-950">Результат ретуши</h3>
                    <p className="mt-1 text-sm text-gray-600">Проверьте крупно: форма, металл, камни, тени, фон. Затем добавляйте в карточку.</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={regenerate} disabled={processing} className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">
                      Перегенерировать
                    </button>
                    <button type="button" onClick={() => applyToProduct()} disabled={applyLoading} className="rounded-lg bg-gold-600 px-3 py-2 text-sm font-semibold text-white hover:bg-gold-700 disabled:opacity-50">
                      {applyLoading ? 'Добавление...' : `Добавить к карточке (${resultUrls.length})`}
                    </button>
                  </div>
                </div>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {resultUrls.map((url, i) => (
                    <div key={url} className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
                      <button
                        type="button"
                        onClick={() => setLightboxUrl(imageFullUrl(url))}
                        className="block aspect-[3/4] w-full bg-white focus:outline-none focus:ring-2 focus:ring-gold-500 focus:ring-inset"
                        title="Открыть в полном размере"
                      >
                        <img src={imageFullUrl(url)} alt={`Ракурс ${i + 1}`} className="h-full w-full object-contain" />
                      </button>
                      <div className="flex items-center justify-between px-3 py-2 text-xs text-gray-600">
                        <span>Ракурс {i + 1}</span>
                        <button type="button" onClick={() => setLightboxUrl(imageFullUrl(url))} className="font-medium text-gold-700 hover:text-gold-800">
                          Увеличить
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
                {promptUsed && (
                  <details className="mt-4 rounded-xl border border-gray-200 bg-white p-3">
                    <summary className="cursor-pointer text-sm font-semibold text-gray-800">Промпт, использованный в этой генерации</summary>
                    <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-xs leading-5 text-gray-700">{promptUsed}</pre>
                  </details>
                )}
                <button type="button" onClick={reset} className="mt-3 text-sm text-gray-500 hover:text-gray-800">
                  Скрыть результат
                </button>
              </div>
            )}

            <div>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-lg font-semibold text-gray-950">История генераций</h3>
                  <p className="mt-1 text-sm text-gray-500">Последние обработанные фото, сгруппированы по артикулу.</p>
                </div>
                <button type="button" onClick={loadHistory} className="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">
                  Обновить
                </button>
              </div>

              {historyLoading ? (
                <p className="rounded-xl border border-gray-200 bg-gray-50 p-4 text-sm text-gray-500">Загрузка...</p>
              ) : history.length === 0 ? (
                <p className="rounded-xl border border-gray-200 bg-gray-50 p-4 text-sm text-gray-500">Пока нет обработанных фото.</p>
              ) : (
                <div className="space-y-4">
                  {history.map((item) => (
                    <article key={item.article} className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
                      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h4 className="text-base font-semibold text-gray-950">Артикул: {item.article}</h4>
                          <p className="text-xs text-gray-500">{item.urls.length} фото · {formatDate(item.updated_at)}</p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setArticle(item.article);
                              document.getElementById('jewelry-photo-section')?.scrollIntoView({ behavior: 'smooth' });
                            }}
                            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
                          >
                            Взять артикул
                          </button>
                          <button
                            type="button"
                            onClick={() => applyToProduct(item.article, item.urls)}
                            disabled={applyLoading}
                            className="rounded-lg bg-gold-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-gold-700 disabled:opacity-50"
                          >
                            {applyLoading ? 'Добавление...' : `Добавить (${item.urls.length})`}
                          </button>
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
                        {item.urls.map((url, i) => (
                          <div key={url} className="group relative overflow-hidden rounded-xl border border-gray-200 bg-gray-50">
                            <button
                              type="button"
                              onClick={() => setLightboxUrl(imageFullUrl(url))}
                              className="block aspect-[3/4] w-full bg-white focus:outline-none focus:ring-2 focus:ring-gold-500 focus:ring-inset"
                              title="Открыть в полном размере"
                            >
                              <img src={imageFullUrl(url)} alt={`${item.article} ${i + 1}`} className="h-full w-full object-contain" />
                            </button>
                            <div className="flex items-center justify-between px-2 py-1.5 text-xs text-gray-600">
                              <span>Фото {i + 1}</span>
                              <button type="button" onClick={() => deleteHistoryFile(url)} className="text-red-600 opacity-70 hover:opacity-100">
                                Удалить
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {lightboxUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4"
          onClick={() => setLightboxUrl(null)}
          role="dialog"
          aria-modal="true"
          aria-label="Фото в полном размере"
        >
          <button
            type="button"
            onClick={() => setLightboxUrl(null)}
            className="absolute right-4 top-4 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-white/90 text-2xl text-gray-800 hover:bg-white"
            aria-label="Закрыть"
          >
            ×
          </button>
          <img
            src={lightboxUrl}
            alt="Фото в полном размере"
            className="h-auto max-h-[92vh] w-auto max-w-[95vw] object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  );
}
