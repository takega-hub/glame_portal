 'use client';

import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import type { LookWithProducts, Product } from '@/types';

type CreationMode = 'selected_model' | 'real_shoot';

interface SelectedProductItem {
  product: Product;
  article: string;
  selectedImageUrls: string[];
}

interface PersistedImageItem {
  url: string;
  source: string;
}

interface EditorImageItem {
  url: string;
  previewUrl: string;
  source: string;
  ref: string;
  origin: 'persisted' | 'gallery' | 'new_upload';
}

interface ManualLookCreatorProps {
  selectedDigitalModel?: string;
  initialLook?: LookWithProducts | null;
  mode?: 'create' | 'edit';
  onCancel?: () => void;
  onLookCreated?: (look?: LookWithProducts) => void;
}

interface MultiValueFieldProps {
  label: string;
  values: string[];
  options: string[];
  placeholder: string;
  onChange: (values: string[]) => void;
}

function getErrorMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail ?? error?.message;
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === 'string' ? item : item?.msg || item?.detail || JSON.stringify(item)))
      .join('; ');
  }
  if (typeof detail === 'object') {
    return detail.msg || detail.detail || JSON.stringify(detail);
  }
  return String(detail);
}

function getVariantSpecEntries(product: Product): Array<[string, string]> {
  const specs = product.specifications;
  if (!specs || typeof specs !== 'object') return [];
  return Object.entries(specs)
    .filter(([key, value]) => {
      if (['parent_external_id', 'Parent_Key', 'parent_key', 'characteristic_id', 'quantity', 'barcode'].includes(key)) {
        return false;
      }
      if (value === null || value === undefined) return false;
      const text = String(value).trim();
      return Boolean(text) && text !== '00000000-0000-0000-0000-000000000000';
    })
    .slice(0, 4)
    .map(([key, value]) => [key, String(value)]);
}

function normalizeValues(values: string[]) {
  const result: string[] = [];
  const seen = new Set<string>();
  values.forEach((item) => {
    const clean = item.trim();
    if (!clean) return;
    const key = clean.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    result.push(clean);
  });
  return result;
}

function MultiValueField({
  label,
  values,
  options,
  placeholder,
  onChange,
}: MultiValueFieldProps) {
  const normalizedOptions = useMemo(() => {
    return Array.from(new Set((options || []).map((item) => item.trim()).filter(Boolean)));
  }, [options]);
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [customValue, setCustomValue] = useState('');

  const addValue = (rawValue: string) => {
    const clean = rawValue.trim();
    if (!clean) return;
    onChange(normalizeValues([...values, clean]));
  };

  const removeValue = (valueToRemove: string) => {
    onChange(values.filter((value) => value !== valueToRemove));
  };

  return (
    <div>
      <label className="mb-2 block text-sm font-medium text-concrete-700">{label}</label>
      <select
        value=""
        onChange={(e) => {
          const nextValue = e.target.value;
          if (nextValue === '__custom__') {
            setShowCustomInput(true);
            return;
          }
          if (nextValue) {
            addValue(nextValue);
          }
        }}
        className="w-full rounded-lg border border-concrete-300 px-3 py-2 text-sm focus:border-gold-500 focus:outline-none"
      >
        <option value="">Выберите или добавьте значение</option>
        {normalizedOptions.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
        <option value="__custom__">Свой вариант</option>
      </select>
      {values.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {values.map((item) => (
            <span
              key={`${label}-${item}`}
              className="inline-flex items-center gap-2 rounded-full bg-gold-50 px-3 py-1 text-sm text-gold-900"
            >
              {item}
              <button
                type="button"
                onClick={() => removeValue(item)}
                className="text-gold-700 hover:text-gold-900"
                aria-label={`Удалить значение ${item}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : null}
      {showCustomInput ? (
        <div className="mt-2 flex gap-2">
          <input
            type="text"
            value={customValue}
            onChange={(e) => setCustomValue(e.target.value)}
            placeholder={placeholder}
            className="flex-1 rounded-lg border border-concrete-300 px-3 py-2 text-sm focus:border-gold-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={() => {
              addValue(customValue);
              setCustomValue('');
              setShowCustomInput(false);
            }}
            className="rounded-lg border border-gold-300 bg-gold-50 px-3 py-2 text-sm font-medium text-gold-700 hover:bg-gold-100"
          >
            Добавить
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default function ManualLookCreator({
  selectedDigitalModel,
  initialLook,
  mode = 'create',
  onCancel,
  onLookCreated,
}: ManualLookCreatorProps) {
  const isEditMode = mode === 'edit' && Boolean(initialLook?.id);
  const [creationMode, setCreationMode] = useState<CreationMode>('selected_model');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [styleValues, setStyleValues] = useState<string[]>([]);
  const [moodValues, setMoodValues] = useState<string[]>([]);
  const [styleDnaValues, setStyleDnaValues] = useState<string[]>([]);
  const [radicalValues, setRadicalValues] = useState<string[]>([]);
  const [isNew, setIsNew] = useState(false);
  const [manualOptions, setManualOptions] = useState<{
    styles: string[];
    moods: string[];
    style_dna: string[];
    radicals: string[];
  }>({
    styles: [],
    moods: [],
    style_dna: [],
    radicals: [],
  });
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [generatingCopy, setGeneratingCopy] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Product[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedProducts, setSelectedProducts] = useState<SelectedProductItem[]>([]);
  const [persistedImages, setPersistedImages] = useState<PersistedImageItem[]>([]);
  const [photoFiles, setPhotoFiles] = useState<File[]>([]);
  const [photoPreviewUrls, setPhotoPreviewUrls] = useState<string[]>([]);
  const [imageOrderRefs, setImageOrderRefs] = useState<string[]>([]);
  const [draggedImageRef, setDraggedImageRef] = useState<string | null>(null);
  const [mainImageRef, setMainImageRef] = useState<string | null>(null);
  const [existingVideoUrl, setExistingVideoUrl] = useState<string | null>(null);
  const [removeExistingVideo, setRemoveExistingVideo] = useState(false);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const appendLocalOption = (
    key: 'styles' | 'moods' | 'style_dna' | 'radicals',
    rawValue: string
  ) => {
    const value = rawValue.trim();
    if (!value) return;
    setManualOptions((current) => {
      const existing = current[key] || [];
      if (existing.some((item) => item.toLowerCase() === value.toLowerCase())) {
        return current;
      }
      return {
        ...current,
        [key]: [...existing, value],
      };
    });
  };

  useEffect(() => {
    let mounted = true;
    setLoadingOptions(true);
    api
      .getManualLookOptions()
      .then((data) => {
        if (!mounted) return;
        setManualOptions({
          styles: Array.isArray(data.styles) ? data.styles : [],
          moods: Array.isArray(data.moods) ? data.moods : [],
          style_dna: Array.isArray(data.style_dna) ? data.style_dna : [],
          radicals: Array.isArray(data.radicals) ? data.radicals : [],
        });
      })
      .catch((e) => {
        if (!mounted) return;
        setError(getErrorMessage(e, 'Не удалось загрузить справочники образов'));
      })
      .finally(() => {
        if (mounted) {
          setLoadingOptions(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!initialLook) return;
    setName(initialLook.name || '');
    setDescription(initialLook.description || '');
    setStyleValues(
      normalizeValues(initialLook.style_values || (initialLook.style ? [initialLook.style] : []))
    );
    setMoodValues(
      normalizeValues(initialLook.mood_values || (initialLook.mood ? [initialLook.mood] : []))
    );
    setStyleDnaValues(
      normalizeValues(initialLook.style_dna_values || (initialLook.style_dna ? [initialLook.style_dna] : []))
    );
    setRadicalValues(
      normalizeValues(initialLook.radical_values || (initialLook.radical ? [initialLook.radical] : []))
    );
    setIsNew(Boolean(initialLook.is_new));
    setCreationMode(initialLook.source_provider === 'real_shoot' ? 'real_shoot' : 'selected_model');

    const layoutById = new Map<string, string[]>();
    (initialLook.product_layout || []).forEach((item: any) => {
      const productId = String(item?.product_id || '');
      const selectedImageUrls = Array.isArray(item?.selected_image_urls)
        ? item.selected_image_urls.map((url: any) => String(url))
        : [];
      if (productId) {
        layoutById.set(productId, selectedImageUrls);
      }
    });

    setSelectedProducts(
      (initialLook.products || []).map((product) => ({
        product,
        article: product.article || product.external_code || '',
        selectedImageUrls: layoutById.get(product.id) || [],
      }))
    );
    const persisted = ((initialLook.image_urls || []) as Array<any>)
      .map((item) => {
        if (typeof item === 'string') {
          return { url: item, source: 'look' };
        }
        return {
          url: String(item?.url || '').trim(),
          source: String(item?.source || 'look').trim() || 'look',
        };
      })
      .filter((item) => item.url && item.source !== 'product_gallery');
    setPersistedImages(persisted);
    const currentImageIndex = initialLook.current_image_index ?? 0;
    const currentImage = (initialLook.image_urls || [])[currentImageIndex] as any;
    const currentImageUrl =
      typeof currentImage === 'string'
        ? currentImage
        : typeof currentImage?.url === 'string'
          ? currentImage.url
          : initialLook.image_url || null;
    setMainImageRef(currentImageUrl || null);
    const existingVideo = (initialLook.media_items || []).find((item) => item?.type === 'video' && item?.url)?.url || null;
    setExistingVideoUrl(existingVideo);
    setRemoveExistingVideo(false);
    setPhotoFiles([]);
    setVideoFile(null);
    const initialOrderRefs = ((initialLook.image_urls || []) as Array<any>)
      .map((item) => (typeof item === 'string' ? item : String(item?.url || '').trim()))
      .filter(Boolean);
    setImageOrderRefs(initialOrderRefs);
  }, [initialLook]);

  useEffect(() => {
    const urls = photoFiles.map((file) => URL.createObjectURL(file));
    setPhotoPreviewUrls(urls);
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [photoFiles]);

  useEffect(() => {
    if (!videoFile) {
      setVideoPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(videoFile);
    setVideoPreviewUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [videoFile]);

  useEffect(() => {
    const query = searchQuery.trim();
    if (query.length < 2) {
      setSearchResults([]);
      setSearching(false);
      return;
    }

    let cancelled = false;
    setSearching(true);
    const timeoutId = window.setTimeout(async () => {
      try {
        const data = await api.getProducts({ search: query, limit: 12, variants_only: true });
        if (!cancelled) {
          setSearchResults(Array.isArray(data) ? data : []);
        }
      } catch (e) {
        if (!cancelled) {
          setError(getErrorMessage(e, 'Не удалось найти товары по артикулу'));
        }
      } finally {
        if (!cancelled) {
          setSearching(false);
        }
      }
    }, 300);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [searchQuery]);

  const selectedProductIds = useMemo(
    () => new Set(selectedProducts.map((item) => item.product.id)),
    [selectedProducts]
  );

  const selectedGalleryCount = useMemo(
    () => selectedProducts.reduce((sum, item) => sum + item.selectedImageUrls.length, 0),
    [selectedProducts]
  );

  const galleryEditorImages = useMemo<EditorImageItem[]>(() => {
    const seen = new Set<string>();
    const result: EditorImageItem[] = [];
    selectedProducts.forEach((item) => {
      item.selectedImageUrls.forEach((url) => {
        const clean = String(url || '').trim();
        if (!clean || seen.has(clean)) return;
        seen.add(clean);
        result.push({
          url: clean,
          previewUrl: clean,
          source: 'product_gallery',
          ref: clean,
          origin: 'gallery',
        });
      });
    });
    return result;
  }, [selectedProducts]);

  const persistedEditorImages = useMemo<EditorImageItem[]>(
    () =>
      persistedImages.map((item) => ({
        url: item.url,
        previewUrl: item.url,
        source: item.source,
        ref: item.url,
        origin: 'persisted',
      })),
    [persistedImages]
  );

  const uploadedEditorImages = useMemo<EditorImageItem[]>(
    () =>
      photoPreviewUrls.map((previewUrl, index) => ({
        url: previewUrl,
        previewUrl,
        source: 'manual_upload',
        ref: `new_upload:${index}`,
        origin: 'new_upload',
      })),
    [photoPreviewUrls]
  );

  const editorImages = useMemo<EditorImageItem[]>(
    () => {
      const combined = [...persistedEditorImages, ...galleryEditorImages, ...uploadedEditorImages];
      if (!imageOrderRefs.length) {
        return combined;
      }
      const orderMap = new Map(imageOrderRefs.map((ref, index) => [ref, index]));
      return [...combined].sort((a, b) => {
        const aIndex = orderMap.has(a.ref) ? orderMap.get(a.ref)! : Number.MAX_SAFE_INTEGER;
        const bIndex = orderMap.has(b.ref) ? orderMap.get(b.ref)! : Number.MAX_SAFE_INTEGER;
        if (aIndex !== bIndex) return aIndex - bIndex;
        return 0;
      });
    },
    [persistedEditorImages, galleryEditorImages, uploadedEditorImages, imageOrderRefs]
  );

  useEffect(() => {
    const availableRefs = editorImages.map((item) => item.ref);
    if (!availableRefs.length) {
      setImageOrderRefs([]);
      return;
    }
    setImageOrderRefs((current) => {
      const filtered = current.filter((ref) => availableRefs.includes(ref));
      const missing = availableRefs.filter((ref) => !filtered.includes(ref));
      const next = [...filtered, ...missing];
      if (next.length === current.length && next.every((ref, index) => ref === current[index])) {
        return current;
      }
      return next;
    });
  }, [editorImages]);

  useEffect(() => {
    if (!editorImages.length) {
      setMainImageRef(null);
      return;
    }
    if (mainImageRef && editorImages.some((item) => item.ref === mainImageRef)) {
      return;
    }
    setMainImageRef(editorImages[0].ref);
  }, [editorImages, mainImageRef]);

  const handleAddProduct = (product: Product) => {
    setError(null);
    setSuccessMessage(null);
    setSelectedProducts((current) => {
      if (current.some((item) => item.product.id === product.id)) {
        return current;
      }
      return [
        ...current,
        {
          product,
          article: product.article || product.external_code || '',
          selectedImageUrls: [],
        },
      ];
    });
  };

  const handleRemoveProduct = (productId: string) => {
    setSelectedProducts((current) => current.filter((item) => item.product.id !== productId));
  };

  const handleToggleProductImage = (productId: string, imageUrl: string) => {
    setSelectedProducts((current) =>
      current.map((item) => {
        if (item.product.id !== productId) return item;
        const alreadySelected = item.selectedImageUrls.includes(imageUrl);
        return {
          ...item,
          selectedImageUrls: alreadySelected
            ? item.selectedImageUrls.filter((url) => url !== imageUrl)
            : [...item.selectedImageUrls, imageUrl],
        };
      })
    );
  };

  const handlePhotosSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    setPhotoFiles((current) => [...current, ...files]);
    setError(null);
    setSuccessMessage(null);
  };

  const handleRemovePhoto = (index: number) => {
    if (mainImageRef === `new_upload:${index}`) {
      setMainImageRef(null);
    } else if (mainImageRef?.startsWith('new_upload:')) {
      const currentIndex = Number(mainImageRef.split(':')[1]);
      if (Number.isFinite(currentIndex) && currentIndex > index) {
        setMainImageRef(`new_upload:${currentIndex - 1}`);
      }
    }
    setPhotoFiles((current) => current.filter((_, itemIndex) => itemIndex !== index));
  };

  const handleMoveImage = (fromRef: string, toRef: string) => {
    if (!fromRef || !toRef || fromRef === toRef) return;
    setImageOrderRefs((current) => {
      const next = current.length ? [...current] : editorImages.map((item) => item.ref);
      const fromIndex = next.indexOf(fromRef);
      const toIndex = next.indexOf(toRef);
      if (fromIndex === -1 || toIndex === -1) return current;
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return next;
    });
  };

  const handleRemovePersistedImage = (url: string) => {
    if (mainImageRef === url) {
      setMainImageRef(null);
    }
    setPersistedImages((current) => current.filter((item) => item.url !== url));
  };

  const handleRemoveGalleryImage = (url: string) => {
    if (mainImageRef === url) {
      setMainImageRef(null);
    }
    setSelectedProducts((current) =>
      current.map((item) => ({
        ...item,
        selectedImageUrls: item.selectedImageUrls.filter((imageUrl) => imageUrl !== url),
      }))
    );
  };

  const resetForm = () => {
    setName('');
    setDescription('');
    setStyleValues([]);
    setMoodValues([]);
    setStyleDnaValues([]);
    setRadicalValues([]);
    setIsNew(false);
    setSearchQuery('');
    setSearchResults([]);
    setSelectedProducts([]);
    setPersistedImages([]);
    setPhotoFiles([]);
    setImageOrderRefs([]);
    setMainImageRef(null);
    setExistingVideoUrl(null);
    setRemoveExistingVideo(false);
    setVideoFile(null);
  };

  const handleGenerateCopy = async () => {
    setError(null);
    setSuccessMessage(null);

    if (selectedProducts.length === 0) {
      setError('Для ИИ-генерации сначала добавьте хотя бы один товар');
      return;
    }

    setGeneratingCopy(true);
    try {
      const result = await api.generateManualLookCopy({
        product_ids: selectedProducts.map((item) => item.product.id),
        style: styleValues[0],
        mood: moodValues[0],
        style_values: styleValues,
        mood_values: moodValues,
        style_dna: styleDnaValues[0],
        radical: radicalValues[0],
        style_dna_values: styleDnaValues,
        radical_values: radicalValues,
        source_provider: creationMode === 'real_shoot' ? 'real_shoot' : 'manual',
        current_name: name.trim() || undefined,
        current_description: description.trim() || undefined,
      });

      if (result.name) {
        setName(result.name);
      }
      if (result.description) {
        setDescription(result.description);
      }
      styleValues.forEach((value) => appendLocalOption('styles', value));
      moodValues.forEach((value) => appendLocalOption('moods', value));
      styleDnaValues.forEach((value) => appendLocalOption('style_dna', value));
      radicalValues.forEach((value) => appendLocalOption('radicals', value));
      setSuccessMessage('Название и описание заполнены ИИ на основе товаров');
    } catch (e) {
      setError(getErrorMessage(e, 'Не удалось сгенерировать название и описание образа'));
    } finally {
      setGeneratingCopy(false);
    }
  };

  const handleSaveLook = async () => {
    setError(null);
    setSuccessMessage(null);

    if (creationMode === 'selected_model' && !selectedDigitalModel) {
      setError('Сначала выберите цифровую модель, для которой создается образ');
      return;
    }

    if (!editorImages.length) {
      setError(
        isEditMode
          ? 'Добавьте хотя бы одно фото в медиаблоке или выберите фото из галереи товара'
          : 'Добавьте хотя бы одно фото: загрузите файл или выберите фото из галереи товара'
      );
      return;
    }

    setCreating(true);
    try {
      const productLinks = selectedProducts.map((item, index) => ({
        product_id: item.product.id,
        article: item.article || item.product.article || item.product.external_code || null,
        position: index + 1,
        selected_image_urls: item.selectedImageUrls,
      }));
      const nextStyleValues = normalizeValues(styleValues);
      const nextMoodValues = normalizeValues(moodValues);
      const nextStyleDnaValues = normalizeValues(styleDnaValues);
      const nextRadicalValues = normalizeValues(radicalValues);

      let result: LookWithProducts;
      if (isEditMode && initialLook) {
        await api.updateLook(initialLook.id, {
          name: name.trim() || undefined,
          description: description.trim() || undefined,
          style: nextStyleValues[0],
          mood: nextMoodValues[0],
          style_values: nextStyleValues,
          mood_values: nextMoodValues,
          style_dna: nextStyleDnaValues[0],
          radical: nextRadicalValues[0],
          style_dna_values: nextStyleDnaValues,
          radical_values: nextRadicalValues,
          is_new: isNew,
          product_ids: productLinks.map((item) => item.product_id),
          product_layout: productLinks,
        });
        result = await api.updateManualLookMedia({
          look_id: initialLook.id,
          keep_image_urls: persistedImages.map((item) => item.url),
          main_image_ref: mainImageRef || undefined,
          ordered_image_refs: imageOrderRefs,
          remove_video: removeExistingVideo,
          photos: photoFiles,
          video: videoFile,
        });
        setSuccessMessage('Образ обновлен');
      } else {
        result = await api.createManualLook({
          name: name.trim() || undefined,
          description: description.trim() || undefined,
          digital_model: creationMode === 'selected_model' ? selectedDigitalModel : undefined,
          source_provider: creationMode === 'real_shoot' ? 'real_shoot' : 'manual',
          style: nextStyleValues[0],
          mood: nextMoodValues[0],
          style_values: nextStyleValues,
          mood_values: nextMoodValues,
          style_dna: nextStyleDnaValues[0],
          radical: nextRadicalValues[0],
          style_dna_values: nextStyleDnaValues,
          radical_values: nextRadicalValues,
          is_new: isNew,
          main_image_ref: mainImageRef || undefined,
          ordered_image_refs: imageOrderRefs,
          product_links: productLinks,
          photos: photoFiles,
          video: videoFile,
        });
        setSuccessMessage(
          creationMode === 'real_shoot'
            ? 'Образ реальной съемки сохранен'
            : 'Ручной образ для выбранной модели сохранен'
        );
        resetForm();
      }

      nextStyleValues.forEach((value) => appendLocalOption('styles', value));
      nextMoodValues.forEach((value) => appendLocalOption('moods', value));
      nextStyleDnaValues.forEach((value) => appendLocalOption('style_dna', value));
      nextRadicalValues.forEach((value) => appendLocalOption('radicals', value));
      onLookCreated?.(result);
    } catch (e) {
      setError(getErrorMessage(e, isEditMode ? 'Не удалось обновить образ' : 'Не удалось создать образ'));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-concrete-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-concrete-900">Создать образ вручную</h2>
            <p className="mt-1 text-sm text-concrete-600">
              {isEditMode
                ? 'Редактируйте состав образа, его описание и теги через тот же блок, что и при создании.'
                : 'Загружайте фото, добавляйте видео и собирайте образ из фото товаров, найденных по артикулу.'}
            </p>
          </div>
          <div className="inline-flex rounded-lg border border-concrete-200 bg-concrete-50 p-1">
            <button
              type="button"
              onClick={() => setCreationMode('selected_model')}
              disabled={isEditMode}
              className={`rounded-md px-3 py-2 text-sm font-medium transition ${
                creationMode === 'selected_model'
                  ? 'bg-gold-500 text-white'
                  : 'text-concrete-700 hover:bg-white'
              } ${isEditMode ? 'cursor-not-allowed opacity-60' : ''}`}
            >
              Для выбранной модели
            </button>
            <button
              type="button"
              onClick={() => setCreationMode('real_shoot')}
              disabled={isEditMode}
              className={`rounded-md px-3 py-2 text-sm font-medium transition ${
                creationMode === 'real_shoot'
                  ? 'bg-gold-500 text-white'
                  : 'text-concrete-700 hover:bg-white'
              } ${isEditMode ? 'cursor-not-allowed opacity-60' : ''}`}
            >
              Реальная съемка
            </button>
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-dashed border-concrete-300 bg-concrete-50 p-4 text-sm text-concrete-700">
          {creationMode === 'selected_model' ? (
            <>
              Образ будет привязан к модели:{' '}
              <span className="font-semibold text-concrete-900">
                {selectedDigitalModel ? selectedDigitalModel : 'модель не выбрана'}
              </span>
              . Выбранные фото из галерей товаров сохраняются как изображения образа.
            </>
          ) : (
            <>
              Режим реальной съемки не связан с ИИ-моделью. Сюда можно сохранять образы с фото и видео реальных людей.
            </>
          )}
        </div>

        {successMessage ? (
          <div className="mt-4 rounded-md bg-green-50 p-3 text-sm text-green-800">{successMessage}</div>
        ) : null}
        {error ? <div className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800">{error}</div> : null}

        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <div>
            <label className="mb-2 block text-sm font-medium text-concrete-700">Название образа</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Например: Весенний городской образ"
              className="w-full rounded-lg border border-concrete-300 px-3 py-2 text-sm focus:border-gold-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-concrete-700">Видео образа</label>
            <input
              type="file"
              accept="video/mp4,video/quicktime,video/webm"
              onChange={(e) => {
                setVideoFile(e.target.files?.[0] || null);
                if (e.target.files?.[0]) {
                  setRemoveExistingVideo(false);
                }
              }}
              className="block w-full text-sm text-concrete-700 file:mr-4 file:rounded-md file:border-0 file:bg-concrete-100 file:px-3 file:py-2 file:text-sm file:font-medium"
            />
            {isEditMode && existingVideoUrl && !removeExistingVideo && !videoFile ? (
              <div className="mt-3 overflow-hidden rounded-lg border border-concrete-200 bg-white">
                <video src={existingVideoUrl} controls className="h-52 w-full bg-black object-contain" />
                <button
                  type="button"
                  onClick={() => setRemoveExistingVideo(true)}
                  className="w-full border-t border-concrete-200 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
                >
                  Удалить текущее видео
                </button>
              </div>
            ) : null}
            {isEditMode && removeExistingVideo && !videoFile ? (
              <div className="mt-3 rounded-lg border border-dashed border-red-200 bg-red-50 p-3 text-sm text-red-700">
                Видео будет удалено после сохранения.
              </div>
            ) : null}
            {videoPreviewUrl ? (
              <div className="mt-3 overflow-hidden rounded-lg border border-concrete-200">
                <video src={videoPreviewUrl} controls className="h-52 w-full bg-black object-contain" />
              </div>
            ) : null}
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-concrete-200 bg-concrete-50 px-4 py-3">
          <label className="flex cursor-pointer items-center gap-3 text-sm font-medium text-concrete-800">
            <input
              type="checkbox"
              checked={isNew}
              onChange={(e) => setIsNew(e.target.checked)}
              className="h-4 w-4 rounded border-concrete-300 text-gold-500 focus:ring-gold-500"
            />
            <span>Новинка</span>
            <span className="text-xs font-normal text-concrete-500">
              Образ попадает во второй блок главной и в фильтр новинок
            </span>
          </label>
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <MultiValueField
            label="Стиль"
            values={styleValues}
            options={manualOptions.styles}
            placeholder="Введите свой стиль"
            onChange={setStyleValues}
          />
          <MultiValueField
            label="Настроение"
            values={moodValues}
            options={manualOptions.moods}
            placeholder="Введите свое настроение"
            onChange={setMoodValues}
          />
          <MultiValueField
            label="Стилевой ДНК"
            values={styleDnaValues}
            options={manualOptions.style_dna}
            placeholder="Введите свой ДНК-профиль"
            onChange={setStyleDnaValues}
          />
          <MultiValueField
            label="Радикал"
            values={radicalValues}
            options={manualOptions.radicals}
            placeholder="Введите свой радикал"
            onChange={setRadicalValues}
          />
        </div>

        {loadingOptions ? (
          <div className="mt-3 text-xs text-concrete-500">Загрузка справочников стиля...</div>
        ) : null}

        <div className="mt-6">
          <div className="mb-2 flex items-center justify-between gap-3">
            <label className="block text-sm font-medium text-concrete-700">Описание образа</label>
            <button
              type="button"
              onClick={() => void handleGenerateCopy()}
              disabled={generatingCopy || selectedProducts.length === 0}
              className="rounded-md border border-gold-300 bg-gold-50 px-3 py-2 text-sm font-medium text-gold-700 hover:bg-gold-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {generatingCopy ? 'Генерация...' : 'Сгенерировать ИИ'}
            </button>
          </div>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Опишите образ, настроение съемки и какие товары участвуют, или заполните поле через ИИ."
            rows={5}
            className="w-full rounded-lg border border-concrete-300 px-3 py-2 text-sm focus:border-gold-500 focus:outline-none"
          />
        </div>

        <div className="mt-6">
          <div className="flex items-center justify-between gap-3">
            <label className="block text-sm font-medium text-concrete-700">
              {isEditMode ? 'Фото образа и основное изображение' : 'Загруженные фото образа'}
            </label>
            <span className="text-xs text-concrete-500">JPG, PNG, WebP</span>
          </div>
          <input
            type="file"
            multiple
            accept=".jpg,.jpeg,.png,.webp"
            onChange={handlePhotosSelected}
            className="mt-2 block w-full text-sm text-concrete-700 file:mr-4 file:rounded-md file:border-0 file:bg-concrete-100 file:px-3 file:py-2 file:text-sm file:font-medium"
          />
          {isEditMode ? (
            <div className="mt-2 text-xs text-concrete-500">
              Здесь можно удалить сохранённые фото, выбрать основное изображение, добавлять новые загрузки и перетаскивать карточки, чтобы менять порядок фото вручную.
            </div>
          ) : null}
          {editorImages.length ? (
            <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              {editorImages.map((item, index) => {
                const isMain = mainImageRef === item.ref;
                return (
                  <div
                    key={`${item.ref}-${index}`}
                    draggable
                    onDragStart={() => setDraggedImageRef(item.ref)}
                    onDragOver={(e) => {
                      e.preventDefault();
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      if (draggedImageRef) {
                        handleMoveImage(draggedImageRef, item.ref);
                      }
                      setDraggedImageRef(null);
                    }}
                    onDragEnd={() => setDraggedImageRef(null)}
                    className={`overflow-hidden rounded-lg border bg-white ${
                      draggedImageRef === item.ref
                        ? 'border-gold-400 opacity-70'
                        : 'border-concrete-200'
                    }`}
                  >
                    <div className="relative">
                      <img src={item.previewUrl} alt={`Фото образа ${index + 1}`} className="h-36 w-full object-cover" />
                      {isMain ? (
                        <span className="absolute left-2 top-2 rounded bg-gold-500 px-2 py-1 text-xs font-medium text-white">
                          Основное
                        </span>
                      ) : null}
                      <span className="absolute right-2 top-2 rounded bg-black/60 px-2 py-1 text-[11px] font-medium text-white">
                        #{index + 1}
                      </span>
                    </div>
                    <div className="border-t border-concrete-200 px-3 py-2 text-xs text-concrete-500">
                      <div className="mb-1 text-[11px] uppercase tracking-wide text-concrete-400">Перетащите для сортировки</div>
                      {item.origin === 'gallery'
                        ? 'Фото из галереи товара'
                        : item.origin === 'new_upload'
                          ? 'Новая загрузка'
                          : item.source === 'manual_upload'
                            ? 'Загруженное фото'
                            : 'Сохраненное фото'}
                    </div>
                    <div className="grid grid-cols-2 gap-2 border-t border-concrete-200 p-2">
                      <button
                        type="button"
                        onClick={() => setMainImageRef(item.ref)}
                        className="rounded-md border border-gold-300 px-2 py-2 text-xs font-medium text-gold-700 hover:bg-gold-50"
                      >
                        Сделать основным
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (item.origin === 'gallery') {
                            handleRemoveGalleryImage(item.url);
                          } else if (item.origin === 'new_upload') {
                            const uploadIndex = Number(item.ref.split(':')[1]);
                            if (Number.isFinite(uploadIndex)) {
                              handleRemovePhoto(uploadIndex);
                            }
                          } else {
                            handleRemovePersistedImage(item.url);
                          }
                        }}
                        className="rounded-md border border-red-200 px-2 py-2 text-xs font-medium text-red-600 hover:bg-red-50"
                      >
                        Удалить
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      </div>

      <div className="rounded-lg border border-concrete-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <h3 className="text-base font-semibold text-concrete-900">Товары в образе</h3>
            <p className="mt-1 text-sm text-concrete-600">
              Начните вводить артикул или код товара, добавьте товар и выберите фото из его галереи.
            </p>
          </div>
          <div className="text-sm text-concrete-500">
            Товаров: {selectedProducts.length} • Фото из галерей: {selectedGalleryCount}
          </div>
        </div>

        <div className="mt-4">
          <label className="mb-2 block text-sm font-medium text-concrete-700">Поиск по артикулу или коду</label>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Например: 71136 или код 1С"
            className="w-full rounded-lg border border-concrete-300 px-3 py-2 text-sm focus:border-gold-500 focus:outline-none"
          />
          <div className="mt-2 text-xs text-concrete-500">
            Поиск идет по названию, артикулу и `external_code`.
          </div>
        </div>

        {searching ? <div className="mt-4 text-sm text-concrete-500">Поиск товаров...</div> : null}

        {searchResults.length ? (
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {searchResults.map((product) => (
              <div key={product.id} className="rounded-lg border border-concrete-200 p-3">
                {(() => {
                  const variantSpecs = getVariantSpecEntries(product);
                  return (
                <>
                <div className="flex gap-3">
                  <div className="h-24 w-24 shrink-0 overflow-hidden rounded-md bg-concrete-100">
                    {product.images?.[0] ? (
                      <img src={product.images[0]} alt={product.name} className="h-full w-full object-cover" />
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-concrete-500">Нет фото</div>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="line-clamp-2 text-sm font-semibold text-concrete-900">{product.name}</div>
                    <div className="mt-1 text-xs text-concrete-600">
                      Артикул: {product.article || product.external_code || '—'}
                    </div>
                    {variantSpecs.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {variantSpecs.map(([key, value]) => (
                          <span
                            key={`${product.id}-${key}`}
                            className="rounded-full bg-concrete-100 px-2 py-1 text-[11px] text-concrete-700"
                          >
                            {key}: {value}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    <div className="mt-1 text-xs text-concrete-500">
                      Вариант товара • Фото в галерее: {product.images?.length || 0}
                    </div>
                    <button
                      type="button"
                      onClick={() => handleAddProduct(product)}
                      disabled={selectedProductIds.has(product.id)}
                      className="mt-3 rounded-md bg-gold-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-gold-600 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {selectedProductIds.has(product.id) ? 'Уже добавлен' : 'Добавить товар'}
                    </button>
                  </div>
                </div>
                </>
                  );
                })()}
              </div>
            ))}
          </div>
        ) : null}

        {selectedProducts.length ? (
          <div className="mt-6 space-y-4">
            {selectedProducts.map((item) => (
              <div key={item.product.id} className="rounded-lg border border-concrete-200 p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="text-base font-semibold text-concrete-900">{item.product.name}</div>
                    <div className="mt-1 text-sm text-concrete-600">
                      Артикул: {item.article || item.product.article || item.product.external_code || '—'}
                    </div>
                    <div className="mt-1 text-sm text-concrete-500">
                      Выбрано фото для образа: {item.selectedImageUrls.length}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemoveProduct(item.product.id)}
                    className="rounded-md border border-red-200 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
                  >
                    Убрать товар
                  </button>
                </div>

                {item.product.images?.length ? (
                  <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
                    {item.product.images.map((imageUrl, index) => {
                      const isSelected = item.selectedImageUrls.includes(imageUrl);
                      return (
                        <button
                          key={`${item.product.id}-${imageUrl}-${index}`}
                          type="button"
                          onClick={() => handleToggleProductImage(item.product.id, imageUrl)}
                          className={`overflow-hidden rounded-lg border text-left transition ${
                            isSelected
                              ? 'border-gold-500 ring-2 ring-gold-200'
                              : 'border-concrete-200 hover:border-concrete-300'
                          }`}
                        >
                          <img
                            src={imageUrl}
                            alt={`${item.product.name} ${index + 1}`}
                            className="h-28 w-full object-cover"
                          />
                          <div className="border-t border-concrete-200 px-2 py-2 text-xs font-medium text-concrete-700">
                            {isSelected ? 'Фото выбрано для образа' : 'Выбрать это фото'}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mt-4 rounded-lg border border-dashed border-concrete-300 bg-concrete-50 p-4 text-sm text-concrete-500">
                    У товара нет изображений в галерее.
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-6 rounded-lg border border-dashed border-concrete-300 bg-concrete-50 p-6 text-center text-sm text-concrete-500">
            Пока нет привязанных товаров. Добавьте их по артикулу и выберите нужные фото из галереи.
          </div>
        )}
      </div>

      <div className="flex justify-end">
        {isEditMode && onCancel ? (
          <button
            type="button"
            onClick={onCancel}
            className="mr-3 rounded-lg border border-concrete-300 px-5 py-3 text-sm font-medium text-concrete-700 hover:bg-concrete-50"
          >
            Отмена
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => void handleSaveLook()}
          disabled={creating || generatingCopy}
          className="rounded-lg bg-gold-500 px-5 py-3 text-sm font-medium text-white hover:bg-gold-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {creating
            ? 'Сохранение...'
            : isEditMode
              ? 'Сохранить изменения'
              : creationMode === 'real_shoot'
                ? 'Сохранить реальную съемку'
                : 'Сохранить образ для модели'}
        </button>
      </div>
    </div>
  );
}
