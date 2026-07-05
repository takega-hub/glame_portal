'use client';

import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { AppHomeSlide } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ManualLookOptionsResponse } from '@/lib/api';

const defaultBlockKey = 'style_inside';

const brandHeroBlockOptions = [
  { key: 'brand_detail_geometry', label: 'Block 4 / Бренд / Geometry' },
  { key: 'brand_detail_magna', label: 'Block 4 / Бренд / Magna' },
  { key: 'brand_detail_pearl', label: 'Block 4 / Бренд / Pearl' },
  { key: 'brand_detail_crystal', label: 'Block 4 / Бренд / Crystal' },
  { key: 'brand_detail_bicolor', label: 'Block 4 / Бренд / Bicolor' },
  {
    key: 'brand_detail_prism-of-elegance',
    label: 'Block 4 / Бренд / Prism Of Elegance',
  },
  { key: 'brand_detail_unode50', label: 'Block 4 / Бренд / UNOde50' },
  {
    key: 'brand_detail_raganella-princess',
    label: 'Block 4 / Бренд / Raganella Princess',
  },
  { key: 'brand_detail_island-soul', label: 'Block 4 / Бренд / Island Soul' },
  { key: 'brand_detail_agafi', label: 'Block 4 / Бренд / AGafi' },
  { key: 'brand_detail_antura', label: 'Block 4 / Бренд / Antura' },
  { key: 'brand_detail_kalliope', label: 'Block 4 / Бренд / Kalliope' },
  {
    key: 'brand_detail_wrinkles-of-time',
    label: 'Block 4 / Бренд / Wrinkles of Time',
  },
  {
    key: 'brand_detail_claudio-canzian',
    label: 'Block 4 / Бренд / Claudio Canzian',
  },
] as const;

const homeBlockOptions = [
  {
    key: 'style_inside',
    label: 'Главная / Стиль внутри',
    helper:
      'Для каждого слайда можно загрузить визуальный слой, при необходимости отдельную подложку, настроить действие по клику на изображение и до 2 кнопок.',
  },
  {
    key: 'collected_glame',
    label: 'Главная / Собрано GLAME',
    helper:
      'Для Block 4 задаются отдельно подложка без текста и визуальный слой без текста. Текст, CTA и список брендов накладываются приложением.',
  },
  {
    key: 'photo_selection',
    label: 'Главная / Блок 3 / Подбор по фото',
    helper:
      'Для Flutter-блока 3 загрузите две картинки: `image_url` — карточка блока на Главной, `background_image_url` — верхнее изображение экрана загрузки фото. Тексты и кнопки в приложении остаются системными.',
  },
  {
    key: 'service_how_to_buy',
    label: 'Главная / Блок 6 / Как купить в GLAME',
    helper:
      'Для финального Block 6 загрузите графитовую подложку блока в `background_image_url`. `image_url` можно не использовать: тексты, action-panels, сервисная зона и логика CTA теперь полностью системные и рендерятся приложением на Главной.',
  },
  {
    key: 'collected_glame_brands',
    label: 'Block 4 / Смотреть бренды',
    helper:
      'Для второго экрана Block 4 загрузите hero-изображение страницы брендов. Приложение показывает верхнюю картинку из `image_url`; подложка опциональна и может использоваться позже.',
  },
  ...brandHeroBlockOptions.map((item) => ({
    ...item,
    helper:
      'Для страницы выбранного бренда загрузите уникальную hero-картинку. Приложение использует `image_url` как верхнее изображение карточки бренда; если запись не создана, останется fallback.',
  })),
] as const;

function getBlockMeta(blockKey: string) {
  return homeBlockOptions.find((item) => item.key === blockKey) || homeBlockOptions[0];
}

type ActionType =
  | 'none'
  | 'catalog'
  | 'looks'
  | 'selection'
  | 'stylist'
  | 'url'
  | 'home_block';

type ActionFormState = {
  text: string;
  type: ActionType;
  legacyLink: string;
  category: string;
  search: string;
  lookFilter: string;
  lookMood: string;
  lookStyle: string;
  lookCollection: string;
  lookRadical: string;
  selectionMode: string;
  externalUrl: string;
  homeBlock: string;
};

const actionOptions: { value: ActionType; label: string }[] = [
  { value: 'none', label: 'Без действия' },
  { value: 'catalog', label: 'Каталог' },
  { value: 'looks', label: 'Образы' },
  { value: 'selection', label: 'Подбор' },
  { value: 'stylist', label: 'Подбор / Стилист' },
  { value: 'url', label: 'Внешняя ссылка' },
  { value: 'home_block', label: 'Блок главной' },
];

const defaultCatalogCategoryOptions = [
  'Все',
  'NEW',
  'SALE',
  'Кольца',
  'Серьги',
  'Колье',
  'Браслеты',
  'Каффы',
];

const emptyLookOptions: ManualLookOptionsResponse = {
  styles: [],
  moods: [],
  style_dna: [],
  radicals: [],
};

function toInt(value: string) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.floor(n);
}

function createEmptyActionState(text: string = ''): ActionFormState {
  return {
    text,
    type: 'none',
    legacyLink: '',
    category: '',
    search: '',
    lookFilter: '',
    lookMood: '',
    lookStyle: '',
    lookCollection: '',
    lookRadical: '',
    selectionMode: '',
    externalUrl: '',
    homeBlock: '2',
  };
}

function fromSlideAction(args: {
  text?: string | null;
  type?: string | null;
  payload?: Record<string, unknown> | null;
  legacyLink?: string | null;
}): ActionFormState {
  const payload = args.payload || {};
  const type = ((args.type || 'none').trim().toLowerCase() as ActionType) || 'none';

  return {
    text: args.text || '',
    type,
    legacyLink: args.legacyLink || '',
    category: readPayloadString(payload, 'category'),
    search: readPayloadString(payload, 'search'),
    lookFilter: readPayloadString(payload, 'filter'),
    lookMood: readPayloadString(payload, 'mood'),
    lookStyle: readPayloadString(payload, 'style'),
    lookCollection: readPayloadString(payload, 'collection'),
    lookRadical: readPayloadString(payload, 'radical'),
    selectionMode: readPayloadString(payload, 'mode') || readPayloadString(payload, 'variant'),
    externalUrl: readPayloadString(payload, 'url') || readPayloadString(payload, 'link'),
    homeBlock:
      readPayloadString(payload, 'block') ||
      readPayloadString(payload, 'block_number') ||
      readPayloadString(payload, 'target') ||
      '2',
  };
}

function readPayloadString(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return typeof value === 'string' ? value : '';
}

function buildActionPayload(state: ActionFormState): Record<string, string> | null {
  if (state.type === 'catalog') {
    const payload: Record<string, string> = {};
    if (state.category.trim() && state.category !== 'Все') payload.category = state.category.trim();
    if (state.search.trim()) payload.search = state.search.trim();
    return Object.keys(payload).length ? payload : null;
  }

  if (state.type === 'looks') {
    const payload: Record<string, string> = {};
    if (state.lookFilter.trim()) payload.filter = state.lookFilter.trim();
    if (state.lookMood.trim()) payload.mood = state.lookMood.trim();
    if (state.lookStyle.trim()) payload.style = state.lookStyle.trim();
    if (state.lookCollection.trim()) payload.collection = state.lookCollection.trim();
    if (state.lookRadical.trim()) payload.radical = state.lookRadical.trim();
    return Object.keys(payload).length ? payload : null;
  }

  if (state.type === 'selection') {
    const payload: Record<string, string> = {};
    if (state.selectionMode.trim()) payload.mode = state.selectionMode.trim();
    return Object.keys(payload).length ? payload : null;
  }

  if (state.type === 'url') {
    const url = state.externalUrl.trim();
    return url ? { url } : null;
  }

  if (state.type === 'home_block') {
    return { block: state.homeBlock.trim() || '2' };
  }

  return null;
}

function buildLegacyLink(state: ActionFormState): string | null {
  if (state.type === 'url') {
    return state.externalUrl.trim() || state.legacyLink.trim() || null;
  }
  return state.legacyLink.trim() || null;
}

function actionSummary(state: ActionFormState): string {
  if (state.type === 'catalog') {
    const parts = [state.category.trim(), state.search.trim() ? `поиск: ${state.search.trim()}` : '']
      .filter(Boolean)
      .join(' · ');
    return parts || 'Каталог без доп. фильтров';
  }
  if (state.type === 'looks') {
    const parts = [state.lookFilter, state.lookMood, state.lookStyle, state.lookCollection, state.lookRadical]
      .map((x) => x.trim())
      .filter(Boolean)
      .join(' · ');
    return parts || 'Образы без доп. фильтров';
  }
  if (state.type === 'selection') {
    return state.selectionMode.trim()
      ? `Подбор · режим: ${state.selectionMode.trim()}`
      : 'Открыть экран подбора';
  }
  if (state.type === 'stylist') return 'Переход в стилист-чат';
  if (state.type === 'url') return state.externalUrl.trim() || 'Внешняя ссылка';
  if (state.type === 'home_block') return `Прокрутка к блоку ${state.homeBlock.trim() || '2'}`;
  return 'Действие не задано';
}

export default function HomeSlidesPanel() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<AppHomeSlide[]>([]);
  const [selectedBlockKey, setSelectedBlockKey] = useState<string>(defaultBlockKey);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [catalogCategories, setCatalogCategories] = useState<string[]>(
    defaultCatalogCategoryOptions
  );
  const [lookOptions, setLookOptions] =
    useState<ManualLookOptionsResponse>(emptyLookOptions);

  const selected = useMemo(() => items.find((x) => x.id === selectedId) || null, [items, selectedId]);
  const lookFilterOptions = useMemo(() => {
    const values = new Set<string>();
    for (const item of [
      ...lookOptions.styles,
      ...lookOptions.moods,
      ...lookOptions.radicals,
      ...lookOptions.style_dna,
    ]) {
      const value = item.trim();
      if (value) values.add(value);
    }
    return Array.from(values);
  }, [lookOptions]);
  const lookCollectionOptions = useMemo(() => {
    const values = new Set<string>();
    for (const slide of items) {
      const image = (slide.image_action_payload || {}) as Record<string, unknown>;
      const primary = (slide.primary_button_action_payload || {}) as Record<
        string,
        unknown
      >;
      const secondary = (slide.secondary_button_action_payload || {}) as Record<
        string,
        unknown
      >;
      for (const payload of [image, primary, secondary]) {
        const collection = readPayloadString(payload, 'collection').trim();
        if (collection) values.add(collection);
      }
    }
    return Array.from(values).sort((a, b) => a.localeCompare(b, 'ru'));
  }, [items]);

  const [title, setTitle] = useState('');
  const [subtitle, setSubtitle] = useState('');
  const [backgroundImageUrl, setBackgroundImageUrl] = useState('');
  const [imageUrl, setImageUrl] = useState('');
  const [imageAction, setImageAction] = useState<ActionFormState>(createEmptyActionState());
  const [primaryAction, setPrimaryAction] = useState<ActionFormState>(createEmptyActionState());
  const [secondaryAction, setSecondaryAction] = useState<ActionFormState>(createEmptyActionState());
  const [sortOrder, setSortOrder] = useState('0');
  const [isActive, setIsActive] = useState(true);

  const resetForm = () => {
    setSelectedId(null);
    setTitle('');
    setSubtitle('');
    setBackgroundImageUrl('');
    setImageUrl('');
    setImageAction(createEmptyActionState());
    setPrimaryAction(createEmptyActionState());
    setSecondaryAction(createEmptyActionState());
    setSortOrder('0');
    setIsActive(true);
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listAppHomeSlides(true, selectedBlockKey);
      setItems(res);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки слайдов главной');
    } finally {
      setLoading(false);
    }
  };

  const loadActionOptions = async () => {
    try {
      const [sections, manualLookOptions] = await Promise.all([
        api.getCatalogSections(),
        api.getManualLookOptions(),
      ]);
      const nextCategories = Array.from(
        new Set(
          ['Все', 'NEW', 'SALE', ...sections.map((section) => section.name.trim())].filter(
            Boolean
          )
        )
      );
      setCatalogCategories(nextCategories);
      setLookOptions(manualLookOptions);
    } catch {
      setCatalogCategories(defaultCatalogCategoryOptions);
      setLookOptions(emptyLookOptions);
    }
  };

  useEffect(() => {
    load();
    loadActionOptions();
  }, [selectedBlockKey]);

  useEffect(() => {
    if (selectedId && !items.some((item) => item.id === selectedId)) {
      resetForm();
    }
  }, [items, selectedId]);

  useEffect(() => {
    if (!selected) return;
    setTitle(selected.title || '');
    setSubtitle(selected.subtitle || '');
    setBackgroundImageUrl(selected.background_image_url || '');
    setImageUrl(selected.image_url || '');
    setImageAction(
      fromSlideAction({
        type: selected.image_action_type,
        payload: selected.image_action_payload,
        legacyLink: selected.image_action_link,
      })
    );
    setPrimaryAction(
      fromSlideAction({
        text: selected.primary_button_text,
        type: selected.primary_button_action_type,
        payload: selected.primary_button_action_payload,
        legacyLink: selected.primary_button_link,
      })
    );
    setSecondaryAction(
      fromSlideAction({
        text: selected.secondary_button_text,
        type: selected.secondary_button_action_type,
        payload: selected.secondary_button_action_payload,
        legacyLink: selected.secondary_button_link,
      })
    );
    setSortOrder(String(selected.sort_order ?? 0));
    setIsActive(!!selected.is_active);
  }, [selected]);

  const onUpload = async (file: File, target: 'background' | 'visual') => {
    setSaving(true);
    setError(null);
    try {
      const { url } = await api.uploadAppAdminMedia('home_slide', file);
      if (target === 'background') {
        setBackgroundImageUrl(url);
      } else {
        setImageUrl(url);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки изображения');
    } finally {
      setSaving(false);
    }
  };

  const onSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const primaryText = primaryAction.text.trim();
      const secondaryText = secondaryAction.text.trim();
      const payload = {
        block_key: selectedBlockKey,
        title: title.trim(),
        subtitle: subtitle.trim() ? subtitle.trim() : null,
        background_image_url: isCollectedGlameHomeBlock
          ? null
          : backgroundImageUrl.trim() || null,
        image_url: imageUrl.trim(),
        image_action_type: imageAction.type === 'none' ? null : imageAction.type,
        image_action_payload: buildActionPayload(imageAction),
        image_action_link: buildLegacyLink(imageAction),
        primary_button_text: primaryText || null,
        primary_button_action_type:
          primaryText && primaryAction.type !== 'none' ? primaryAction.type : null,
        primary_button_action_payload:
          primaryText ? buildActionPayload(primaryAction) : null,
        primary_button_link: primaryText ? buildLegacyLink(primaryAction) : null,
        secondary_button_text: secondaryText || null,
        secondary_button_action_type:
          secondaryText && secondaryAction.type !== 'none'
            ? secondaryAction.type
            : null,
        secondary_button_action_payload:
          secondaryText ? buildActionPayload(secondaryAction) : null,
        secondary_button_link: secondaryText ? buildLegacyLink(secondaryAction) : null,
        sort_order: toInt(sortOrder),
        is_active: isActive,
      };

      if (selectedId) {
        await api.updateAppHomeSlide(selectedId, payload);
      } else {
        await api.createAppHomeSlide(payload);
      }
      await load();
      resetForm();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка сохранения слайда');
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (id: string) => {
    if (!confirm('Удалить слайд главной?')) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteAppHomeSlide(id);
      if (selectedId === id) resetForm();
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка удаления слайда');
    } finally {
      setSaving(false);
    }
  };

  const blockMeta = getBlockMeta(selectedBlockKey);
  const isCollectedGlameHomeBlock = selectedBlockKey === 'collected_glame';
  const isPhotoSelectionBlock = selectedBlockKey === 'photo_selection';

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>{blockMeta.label}</CardTitle>
        </CardHeader>
        <CardContent>
          {error ? <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
          <div className="mb-4 rounded-md border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200">
            {blockMeta.helper}
          </div>
          <div className="mb-4">
            <div className="mb-2 text-xs text-gray-500 dark:text-gray-400">Блок главной</div>
            <Select
              value={selectedBlockKey}
              onValueChange={(value) => {
                setSelectedBlockKey(value);
                resetForm();
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {homeBlockOptions.map((opt) => (
                  <SelectItem key={opt.key} value={opt.key}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-2">
            <Button onClick={load} disabled={loading || saving}>Обновить</Button>
            <Button variant="outline" onClick={resetForm} disabled={saving}>Новый слайд</Button>
          </div>

          <div className="mt-4 space-y-2">
            {loading ? <div className="text-sm text-gray-600 dark:text-gray-300">Загрузка…</div> : null}
            {!loading && items.length === 0 ? <div className="text-sm text-gray-600 dark:text-gray-300">Пока нет слайдов</div> : null}
            {items.map((slide) => (
              <div
                key={slide.id}
                className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
                  slide.id === selectedId
                    ? 'border-blue-300 bg-blue-50 dark:border-blue-900 dark:bg-blue-950'
                    : 'border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950'
                }`}
              >
                {slide.image_url ? (
                  <img src={slide.image_url} alt={slide.title || 'slide'} className="h-16 w-20 rounded object-cover" />
                ) : (
                  <div className="flex h-16 w-20 items-center justify-center rounded bg-gray-100 text-xs text-gray-500 dark:bg-gray-900">GLAME</div>
                )}
                <button onClick={() => setSelectedId(slide.id)} className="flex-1 text-left">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-gray-900 dark:text-gray-100">{slide.title || 'Без заголовка'}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">#{slide.sort_order}</div>
                  </div>
                  <div className="mt-1 line-clamp-2 text-sm text-gray-600 dark:text-gray-300">{slide.subtitle || 'Без описания'}</div>
                  <div className="mt-2 space-y-1 text-xs text-gray-500 dark:text-gray-400">
                    <div>
                      Клик по фото:{' '}
                      {actionSummary(
                        fromSlideAction({
                          type: slide.image_action_type,
                          payload: slide.image_action_payload,
                          legacyLink: slide.image_action_link,
                        })
                      )}
                    </div>
                    <div>
                      Кнопка 1:{' '}
                      {actionSummary(
                        fromSlideAction({
                          text: slide.primary_button_text,
                          type: slide.primary_button_action_type,
                          payload: slide.primary_button_action_payload,
                          legacyLink: slide.primary_button_link,
                        })
                      )}
                    </div>
                    <div>
                      Кнопка 2:{' '}
                      {actionSummary(
                        fromSlideAction({
                          text: slide.secondary_button_text,
                          type: slide.secondary_button_action_type,
                          payload: slide.secondary_button_action_payload,
                          legacyLink: slide.secondary_button_link,
                        })
                      )}
                    </div>
                  </div>
                  <div className="mt-2 inline-flex rounded border border-gray-200 bg-white px-2 py-0.5 text-xs text-black dark:border-gray-700 dark:bg-white dark:text-black">
                    {slide.is_active ? 'Активен' : 'Выключен'}
                  </div>
                  {slide.background_image_url ? (
                    <div className="mt-2 ml-2 inline-flex rounded border border-gray-200 bg-white px-2 py-0.5 text-xs text-black dark:border-gray-700 dark:bg-white dark:text-black">
                      Есть подложка
                    </div>
                  ) : null}
                </button>
                <Button variant="destructive" onClick={() => onDelete(slide.id)} disabled={saving}>Удалить</Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{selectedId ? 'Редактирование слайда' : 'Новый слайд'}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Блок</div>
              <Input value={blockMeta.label} disabled />
            </div>

            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Заголовок</div>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Необязательно" />
            </div>

            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Описание</div>
              <Textarea value={subtitle} onChange={(e) => setSubtitle(e.target.value)} placeholder="Необязательно" rows={4} />
            </div>

            {!isCollectedGlameHomeBlock ? (
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  {isPhotoSelectionBlock ? 'Изображение экрана загрузки фото' : 'Подложка'}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) onUpload(f, 'background');
                    }}
                    disabled={saving}
                  />
                  <Input
                    value={backgroundImageUrl}
                    onChange={(e) => setBackgroundImageUrl(e.target.value)}
                    placeholder={
                      isPhotoSelectionBlock
                        ? '/static/... для экрана загрузки фото'
                        : '/static/... или пусто'
                    }
                  />
                </div>
                {backgroundImageUrl ? (
                  <div className="mt-3 overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
                    <img src={backgroundImageUrl} alt="background" className="h-48 w-full object-cover" />
                  </div>
                ) : null}
              </div>
            ) : null}

            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {isCollectedGlameHomeBlock
                  ? 'Фоновое изображение блока'
                  : isPhotoSelectionBlock
                  ? 'Изображение карточки блока на Главной'
                  : 'Визуальный слой'}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) onUpload(f, 'visual');
                  }}
                  disabled={saving}
                />
                <Input
                  value={imageUrl}
                  onChange={(e) => setImageUrl(e.target.value)}
                  placeholder={
                    isCollectedGlameHomeBlock
                      ? '/static/... полноразмерный фон блока'
                      : isPhotoSelectionBlock
                      ? '/static/... для карточки блока 3 на Главной'
                      : '/static/...'
                  }
                />
              </div>
              {imageUrl ? (
                <div className="mt-3 overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
                  <img src={imageUrl} alt="slide" className="h-48 w-full object-cover" />
                </div>
              ) : null}
            </div>

            <ActionEditor
              title="Клик по изображению"
              state={imageAction}
              onChange={setImageAction}
              catalogCategories={catalogCategories}
              lookFilterOptions={lookFilterOptions}
              lookCollectionOptions={lookCollectionOptions}
              lookOptions={lookOptions}
              showTextField={false}
            />

            <ActionEditor
              title="Кнопка 1 (основная)"
              state={primaryAction}
              onChange={setPrimaryAction}
              catalogCategories={catalogCategories}
              lookFilterOptions={lookFilterOptions}
              lookCollectionOptions={lookCollectionOptions}
              lookOptions={lookOptions}
            />

            <ActionEditor
              title="Кнопка 2 (вторичная)"
              state={secondaryAction}
              onChange={setSecondaryAction}
              catalogCategories={catalogCategories}
              lookFilterOptions={lookFilterOptions}
              lookCollectionOptions={lookCollectionOptions}
              lookOptions={lookOptions}
            />

            <div className="rounded-md border border-gray-200 p-3 dark:border-gray-800">
              <div className="mb-2 text-sm font-medium">Превью CTA</div>
              <div className="space-y-2">
                <ActionPreview title="Клик по изображению" state={imageAction} hiddenLabel="Клик по фото отключен" />
                <ActionPreview filled state={primaryAction} />
                <ActionPreview state={secondaryAction} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Порядок</div>
                <Input value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} />
              </div>
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Статус</div>
                <div className="mt-2 flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
                  <span className="rounded border border-gray-200 bg-white px-2 py-0.5 text-black dark:border-gray-700 dark:bg-white dark:text-black">
                    Активен
                  </span>
                </div>
              </div>
            </div>

            <div className="flex gap-2">
              <Button onClick={onSave} disabled={saving || !imageUrl.trim()}>Сохранить</Button>
              <Button variant="outline" onClick={resetForm} disabled={saving}>Отменить</Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ActionEditor({
  title,
  state,
  onChange,
  catalogCategories,
  lookFilterOptions,
  lookCollectionOptions,
  lookOptions,
  showTextField = true,
}: {
  title: string;
  state: ActionFormState;
  onChange: (next: ActionFormState) => void;
  catalogCategories: string[];
  lookFilterOptions: string[];
  lookCollectionOptions: string[];
  lookOptions: ManualLookOptionsResponse;
  showTextField?: boolean;
}) {
  const setField = <K extends keyof ActionFormState>(key: K, value: ActionFormState[K]) => {
    onChange({ ...state, [key]: value });
  };

  return (
    <div className="rounded-md border border-gray-200 p-3 dark:border-gray-800">
      <div className="mb-2 text-sm font-medium">{title}</div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {showTextField ? (
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Текст</div>
            <Input value={state.text} onChange={(e) => setField('text', e.target.value)} placeholder="Текст кнопки" />
          </div>
        ) : (
          <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200">
            Если действие задано, тап по изображению откроет выбранный экран или ссылку.
          </div>
        )}
        <div>
          <div className="text-xs text-gray-500 dark:text-gray-400">Тип действия</div>
          <Select value={state.type} onValueChange={(v) => setField('type', v as ActionType)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {actionOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {state.type === 'catalog' ? (
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Категория</div>
            <Select value={state.category || 'Все'} onValueChange={(v) => setField('category', v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {catalogCategories.map((opt) => (
                  <SelectItem key={opt} value={opt}>
                    {opt}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Поиск</div>
            <Input value={state.search} onChange={(e) => setField('search', e.target.value)} placeholder="Например: кольцо" />
          </div>
        </div>
      ) : null}

      {state.type === 'looks' ? (
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Основной фильтр</div>
            <Select value={state.lookFilter || '__empty__'} onValueChange={(v) => setField('lookFilter', v === '__empty__' ? '' : v)}>
              <SelectTrigger>
                <SelectValue placeholder="Выберите фильтр" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__empty__">Не задан</SelectItem>
                {lookFilterOptions.map((opt) => (
                  <SelectItem key={opt} value={opt}>
                    {opt}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Настроение</div>
            <Select value={state.lookMood || '__empty__'} onValueChange={(v) => setField('lookMood', v === '__empty__' ? '' : v)}>
              <SelectTrigger>
                <SelectValue placeholder="Выберите настроение" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__empty__">Не задано</SelectItem>
                {lookOptions.moods.map((opt) => (
                  <SelectItem key={opt} value={opt}>
                    {opt}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Стиль</div>
            <Select value={state.lookStyle || '__empty__'} onValueChange={(v) => setField('lookStyle', v === '__empty__' ? '' : v)}>
              <SelectTrigger>
                <SelectValue placeholder="Выберите стиль" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__empty__">Не задан</SelectItem>
                {lookOptions.styles.map((opt) => (
                  <SelectItem key={opt} value={opt}>
                    {opt}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Коллекция</div>
            <Input
              value={state.lookCollection}
              onChange={(e) => setField('lookCollection', e.target.value)}
              placeholder="Например: Geometry"
              list={`${title}-collection-options`}
            />
            {lookCollectionOptions.length ? (
              <datalist id={`${title}-collection-options`}>
                {lookCollectionOptions.map((opt) => (
                  <option key={opt} value={opt} />
                ))}
              </datalist>
            ) : null}
          </div>
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Radical / DNA</div>
            <Select value={state.lookRadical || '__empty__'} onValueChange={(v) => setField('lookRadical', v === '__empty__' ? '' : v)}>
              <SelectTrigger>
                <SelectValue placeholder="Выберите radical / DNA" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__empty__">Не задан</SelectItem>
                {[...lookOptions.radicals, ...lookOptions.style_dna].map((opt) => (
                  <SelectItem key={opt} value={opt}>
                    {opt}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      ) : null}

      {state.type === 'selection' ? (
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Режим подбора</div>
            <Select
              value={state.selectionMode || '__default__'}
              onValueChange={(v) => setField('selectionMode', v === '__default__' ? '' : v)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Обычный подбор" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__default__">Обычный подбор</SelectItem>
                <SelectItem value="gift">Подарок</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      ) : null}

      {state.type === 'url' ? (
        <div className="mt-3">
          <div className="text-xs text-gray-500 dark:text-gray-400">Внешняя ссылка</div>
          <Input value={state.externalUrl} onChange={(e) => setField('externalUrl', e.target.value)} placeholder="https://..." />
        </div>
      ) : null}

      {state.type === 'home_block' ? (
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Блок главной</div>
            <Select
              value={state.homeBlock || '2'}
              onValueChange={(v) => setField('homeBlock', v)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Выберите блок" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="2">Блок 2 / Новинки</SelectItem>
                <SelectItem value="3">Блок 3 / Подбор по фото</SelectItem>
                <SelectItem value="4">Блок 4 / Собрано GLAME</SelectItem>
                <SelectItem value="5">Блок 5 / Пространства</SelectItem>
                <SelectItem value="6">Блок 6 / Как купить</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      ) : null}

      {state.type === 'stylist' ? (
        <div className="mt-3 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200">
          Кнопка откроет сценарий подбора в стилист-чате.
        </div>
      ) : null}

      {state.type === 'selection' ? (
        <div className="mt-3 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200">
          Кнопка откроет экран выбора способа подбора. Для hero gift используйте режим `Подарок`.
        </div>
      ) : null}

      <div className="mt-3">
        <div className="text-xs text-gray-500 dark:text-gray-400">Fallback ссылка</div>
        <Input
          value={state.legacyLink}
          onChange={(e) => setField('legacyLink', e.target.value)}
          placeholder="Оставьте пустым, если fallback не нужен"
        />
      </div>

      <div className="mt-3 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-700 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200">
        {showTextField && !state.text.trim()
          ? 'Кнопка будет скрыта, пока текст не заполнен.'
          : null}
        {showTextField && !state.text.trim() ? ' ' : null}
        {actionSummary(state)}
      </div>
    </div>
  );
}

function ActionPreview({
  state,
  filled = false,
  title,
  hiddenLabel,
}: {
  state: ActionFormState;
  filled?: boolean;
  title?: string;
  hiddenLabel?: string;
}) {
  const hasText = state.text.trim().length > 0;
  const showButton = title ? true : hasText;
  return (
    <div className="rounded-md border border-gray-200 p-3 dark:border-gray-800">
      <div className="mb-2 text-xs text-gray-500 dark:text-gray-400">
        {title || (filled ? 'Основная кнопка' : 'Вторичная кнопка')}
      </div>
      {showButton ? (
        <div
          className={`flex min-h-12 items-center justify-center border px-4 text-center text-base ${
            filled
              ? 'border-black bg-black text-white'
              : 'border-black bg-white text-black'
          }`}
        >
          {title ? 'Вся картинка кликабельна' : state.text.trim()}
        </div>
      ) : (
        <div className="flex min-h-12 items-center justify-center border border-dashed px-4 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
          {hiddenLabel || 'Кнопка скрыта: текст не задан'}
        </div>
      )}
      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        {actionSummary(state)}
      </div>
    </div>
  );
}
