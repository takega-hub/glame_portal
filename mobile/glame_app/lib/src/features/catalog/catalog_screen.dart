import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/glame_theme.dart';
import '../../core/layout/glame_layout.dart';
import '../../core/network/asset_url.dart';
import '../../core/formatters/rub.dart';
import '../auth/auth_controller.dart';
import '../home/home_providers.dart';
import 'catalog_filter_sheet.dart';
import 'catalog_controller.dart';
import '../product/product_providers.dart';
import '../wishlist/wishlist_controller.dart';

const double _glameMediaAspectRatio = 3 / 4;

Future<void> showCatalogSearchDialog(BuildContext context) {
  return showDialog<void>(
    context: context,
    builder: (_) => const _CatalogSearchDialog(),
  );
}

class CatalogScreen extends ConsumerStatefulWidget {
  final String title;
  final String? initialCategory;
  final String? initialBrand;
  final String? initialSearch;
  final String? initialStoreId;
  final String? initialStoreTitle;
  final String? storeBackRoute;
  final bool pickLookBase;

  const CatalogScreen({
    super.key,
    this.title = 'КАТАЛОГ',
    this.initialCategory,
    this.initialBrand,
    this.initialSearch,
    this.initialStoreId,
    this.initialStoreTitle,
    this.storeBackRoute,
    this.pickLookBase = false,
  });

  @override
  ConsumerState<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends ConsumerState<CatalogScreen> {
  final scroll = ScrollController();
  String? selectedCategory;

  @override
  void initState() {
    super.initState();
    selectedCategory = _normalizeCategory(widget.initialCategory);
    scroll.addListener(() {
      if (!scroll.hasClients) return;
      final maxScroll = scroll.position.maxScrollExtent;
      final current = scroll.position.pixels;
      if (current > maxScroll - 600) {
        ref.read(catalogControllerProvider.notifier).loadMore();
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final initial = _normalizeCategory(widget.initialCategory);
      final initialBrand = _normalizeValue(widget.initialBrand);
      final initialSearch = (widget.initialSearch ?? '').trim();
      final initialStoreId = _normalizeValue(widget.initialStoreId);
      if (initial != null ||
          initialBrand != null ||
          initialSearch.isNotEmpty ||
          initialStoreId != null) {
        ref
            .read(catalogControllerProvider.notifier)
            .resetAndApply(
              category: initial,
              brand: initialBrand,
              search: initialSearch,
              storeId: initialStoreId,
            );
      }
    });
  }

  @override
  void didUpdateWidget(covariant CatalogScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.initialCategory == widget.initialCategory &&
        oldWidget.initialBrand == widget.initialBrand &&
        oldWidget.initialSearch == widget.initialSearch &&
        oldWidget.initialStoreId == widget.initialStoreId) {
      return;
    }
    final next = _normalizeCategory(widget.initialCategory);
    final nextBrand = _normalizeValue(widget.initialBrand);
    final nextSearch = (widget.initialSearch ?? '').trim();
    setState(() {
      selectedCategory = next;
    });
    ref
        .read(catalogControllerProvider.notifier)
        .resetAndApply(
          category: next,
          brand: nextBrand,
          search: nextSearch,
          storeId: _normalizeValue(widget.initialStoreId),
        );
  }

  @override
  void dispose() {
    scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final catalog = ref.watch(catalogControllerProvider);
    final controller = ref.read(catalogControllerProvider.notifier);
    final sectionsAsync = ref.watch(homeCatalogSectionsProvider);
    final characteristicsAsync = ref.watch(productCharacteristicsProvider);

    final groupedItems = _groupCatalogItems(catalog.items);

    final categories = sectionsAsync.maybeWhen(
      data: _buildCategoryLabels,
      orElse: () => const [
        'Все',
        'Кольца',
        'Серьги',
        'Колье',
        'Браслеты',
        'Каффы',
        'NEW',
        'SALE',
      ],
    );
    final isWideScreen = GlameLayout.isTablet(context);
    final gutter = GlameLayout.horizontalGutter(context);
    // Keep the established 16px phone grid geometry; larger viewports use
    // the shared responsive gutter.
    final gridGutter = isWideScreen ? gutter : 16.0;
    final catalogColumns = GlameLayout.catalogColumns(context);

    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      body: SafeArea(
        child: GlameContentWidth(
          child: Column(
            children: [
              _buildHeader(context, catalog, characteristicsAsync),
              _buildCatalogControls(
                context,
                categories,
                catalog,
                characteristicsAsync,
                isWideScreen,
              ),
              Expanded(
                child: RefreshIndicator(
                  color: GlameColors.whiteGlame,
                  onRefresh: controller.refresh,
                  child: CustomScrollView(
                    controller: scroll,
                    slivers: [
                      SliverPadding(
                        padding: EdgeInsets.fromLTRB(
                          gridGutter,
                          isWideScreen ? 28 : 18,
                          gridGutter,
                          isWideScreen ? 44 : 28,
                        ),
                        sliver: SliverGrid(
                          delegate: SliverChildBuilderDelegate((context, i) {
                            final item = groupedItems[i];
                            return _ProductCardDarkrain(
                              key: ValueKey(
                                (item['id'] as String?) ??
                                    (item['article'] as String?) ??
                                    '$i',
                              ),
                              item: item,
                              pickMode: widget.pickLookBase,
                              onPick: widget.pickLookBase
                                  ? (product) => context.pop(product)
                                  : null,
                            );
                          }, childCount: groupedItems.length),
                          gridDelegate:
                              SliverGridDelegateWithFixedCrossAxisCount(
                                crossAxisCount: catalog.oneColumn
                                    ? 1
                                    : catalogColumns,
                                mainAxisSpacing: isWideScreen ? 30 : 22,
                                crossAxisSpacing: isWideScreen ? 24 : 14,
                                childAspectRatio: catalog.oneColumn
                                    ? (isWideScreen ? 2.25 : 0.92)
                                    : widget.pickLookBase
                                    ? (isWideScreen ? 0.56 : 0.48)
                                    : (isWideScreen ? 0.62 : 0.52),
                              ),
                        ),
                      ),
                      SliverToBoxAdapter(
                        child: Padding(
                          padding: EdgeInsets.all(gridGutter),
                          child: Column(
                            children: [
                              if (catalog.loading)
                                const Center(
                                  child: Padding(
                                    padding: EdgeInsets.symmetric(vertical: 20),
                                    child: CircularProgressIndicator(
                                      color: GlameColors.whiteGlame,
                                    ),
                                  ),
                                ),
                              const SizedBox.shrink(),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(
    BuildContext context,
    CatalogState catalog,
    AsyncValue<Map<String, dynamic>> characteristicsAsync,
  ) {
    final isWideScreen = GlameLayout.isTablet(context);
    final gutter = GlameLayout.horizontalGutter(context);
    final controller = ref.read(catalogControllerProvider.notifier);
    final activeFilters = _activeFiltersCount(catalog);
    final title = widget.pickLookBase ? 'ВЫБЕРИТЕ ОСНОВУ' : widget.title;
    final storeTitle = _normalizeValue(widget.initialStoreTitle);
    final backRoute = _normalizeValue(widget.storeBackRoute);
    final showBack = widget.pickLookBase || backRoute != null;
    return Container(
      padding: EdgeInsets.fromLTRB(gutter, 24, gutter, 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (showBack) ...[
            IconButton(
              tooltip: 'Назад',
              onPressed: () {
                if (widget.pickLookBase) {
                  context.pop();
                  return;
                }
                if (backRoute != null) context.go(backRoute);
              },
              style: IconButton.styleFrom(
                foregroundColor: GlameColors.whiteGlame,
                side: const BorderSide(color: GlameColors.borderGray),
                shape: const CircleBorder(),
              ),
              icon: const Icon(Icons.arrow_back),
            ),
            const SizedBox(width: 12),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        title,
                        style: TextStyle(
                          fontSize: isWideScreen ? 44 : 36,
                          fontWeight: FontWeight.w400,
                          height: 0.95,
                          color: GlameColors.whiteGlame,
                        ),
                      ),
                    ),
                    _CatalogControlIcon(
                      tooltip: 'Фильтры',
                      icon: Icons.tune,
                      badge: activeFilters,
                      selected: activeFilters > 0,
                      onTap: () =>
                          _openFilters(context, catalog, characteristicsAsync),
                    ),
                    const SizedBox(width: 8),
                    _CatalogControlIcon(
                      tooltip: catalog.oneColumn ? 'Плитка' : 'Список',
                      icon: catalog.oneColumn
                          ? Icons.grid_view
                          : Icons.view_agenda,
                      onTap: controller.toggleLayout,
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Container(width: 54, height: 1, color: GlameColors.steelGray),
                if (storeTitle != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    'В наличии в $storeTitle',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 12,
                      letterSpacing: 0.7,
                      color: GlameColors.coldLightGray,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCatalogControls(
    BuildContext context,
    List<String> categories,
    CatalogState catalog,
    AsyncValue<Map<String, dynamic>> characteristicsAsync,
    bool isWideScreen,
  ) {
    final gutter = GlameLayout.horizontalGutter(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(gutter, 0, gutter, 12),
      child: SizedBox(
        height: 48,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          itemCount: categories.length,
          separatorBuilder: (_, _) => SizedBox(width: isWideScreen ? 12 : 8),
          itemBuilder: (context, index) {
            final label = categories[index];
            final isActive =
                (index == 0 && selectedCategory == null) ||
                selectedCategory == label;
            return _CatalogControlChip(
              label: label.toUpperCase(),
              selected: isActive,
              onTap: () {
                setState(() => selectedCategory = index == 0 ? null : label);
                ref
                    .read(catalogControllerProvider.notifier)
                    .setCategory(index == 0 ? null : label);
              },
            );
          },
        ),
      ),
    );
  }

  Future<void> _openFilters(
    BuildContext context,
    CatalogState catalog,
    AsyncValue<Map<String, dynamic>> characteristicsAsync,
  ) async {
    final characteristics = await _loadFilterCharacteristics(
      characteristicsAsync,
    );
    if (!context.mounted) return;
    final result = await showModalBottomSheet<CatalogFiltersDraft>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: GlameColors.surface2,
      shape: const RoundedRectangleBorder(),
      builder: (context) {
        return SizedBox(
          height: MediaQuery.sizeOf(context).height,
          child: CatalogFilterSheet(
            characteristics: characteristics,
            countLoader: (draft) => _loadFilteredCount(catalog, draft),
            initial: CatalogFiltersDraft(
              priceMin: catalog.priceMin,
              priceMax: catalog.priceMax,
              brand: catalog.brand,
              material: catalog.material,
              vstavka: catalog.vstavka,
              pokrytie: catalog.pokrytie,
              razmer: catalog.razmer,
              tipZamka: catalog.tipZamka,
              color: catalog.color,
              sort: catalog.sort,
              inStockOnly: catalog.inStockOnly,
            ),
          ),
        );
      },
    );
    if (result == null || !mounted) return;
    await ref
        .read(catalogControllerProvider.notifier)
        .setFilters(
          priceMin: result.priceMin,
          priceMax: result.priceMax,
          brand: result.brand,
          material: result.material,
          vstavka: result.vstavka,
          pokrytie: result.pokrytie,
          razmer: result.razmer,
          tipZamka: result.tipZamka,
          color: result.color,
          sort: result.sort,
          inStockOnly: result.inStockOnly,
        );
  }

  Future<Map<String, dynamic>> _loadFilterCharacteristics(
    AsyncValue<Map<String, dynamic>> characteristicsAsync,
  ) async {
    final loaded = characteristicsAsync.valueOrNull;
    if (loaded != null && loaded.isNotEmpty) return loaded;
    try {
      final providerLoaded = await ref.read(
        productCharacteristicsProvider.future,
      );
      if (providerLoaded.isNotEmpty) return providerLoaded;
    } catch (_) {
      ref.invalidate(productCharacteristicsProvider);
    }
    try {
      final directLoaded = await ref
          .read(catalogControllerProvider.notifier)
          .api
          .getCharacteristicsValues();
      if (directLoaded.isNotEmpty) return directLoaded;
    } catch (_) {
      // The sheet can still open; individual sections will show empty states.
    }
    return const <String, dynamic>{};
  }

  Future<int> _loadFilteredCount(
    CatalogState catalog,
    CatalogFiltersDraft draft,
  ) async {
    final raw = await ref
        .read(catalogControllerProvider.notifier)
        .api
        .getProductsPaged(
          skip: 0,
          limit: 1,
          category: catalog.category,
          brand: draft.brand,
          search: catalog.search,
          inStock: draft.inStockOnly ? true : null,
          hasImages: true,
          priceMin: draft.priceMin,
          priceMax: draft.priceMax,
          material: draft.material,
          vstavka: draft.vstavka,
          pokrytie: draft.pokrytie,
          razmer: draft.razmer,
          tipZamka: draft.tipZamka,
          color: draft.color,
          sort: draft.sort,
        );
    final total = raw['total'];
    if (total is int) return total;
    if (total is num) return total.toInt();
    final items = raw['items'];
    return items is List ? items.length : 0;
  }

  int _activeFiltersCount(CatalogState catalog) {
    var count = 0;
    if (catalog.priceMin != null) count++;
    if (catalog.priceMax != null) count++;
    if ((catalog.brand ?? '').trim().isNotEmpty) count++;
    if ((catalog.material ?? '').trim().isNotEmpty) count++;
    if ((catalog.vstavka ?? '').trim().isNotEmpty) count++;
    if ((catalog.pokrytie ?? '').trim().isNotEmpty) count++;
    if ((catalog.razmer ?? '').trim().isNotEmpty) count++;
    if ((catalog.tipZamka ?? '').trim().isNotEmpty) count++;
    if ((catalog.color ?? '').trim().isNotEmpty) count++;
    if ((catalog.sort ?? '').trim().isNotEmpty) count++;
    return count;
  }

  List<Map<String, dynamic>> _groupCatalogItems(
    List<Map<String, dynamic>> items,
  ) {
    final grouped = <String, List<Map<String, dynamic>>>{};
    for (final item in items) {
      final key = _catalogGroupKey(item);
      grouped.putIfAbsent(key, () => <Map<String, dynamic>>[]).add(item);
    }

    final result = <Map<String, dynamic>>[];
    for (final entry in grouped.entries) {
      final variants = entry.value;
      if (variants.length == 1) {
        final single = Map<String, dynamic>.from(variants.first);
        single['_variants'] = [Map<String, dynamic>.from(variants.first)];
        result.add(single);
        continue;
      }

      final base = _baseArticle(((variants.first)['article'] as String?) ?? '');
      Map<String, dynamic> selected = variants.first;
      for (final item in variants) {
        if (_hasPositiveStock(item)) {
          selected = item;
          break;
        }
      }
      if (!_hasPositiveStock(selected) && base.isNotEmpty) {
        for (final item in variants) {
          final article = ((item['article'] as String?) ?? '').trim();
          if (article == base) {
            selected = item;
            break;
          }
        }
      }

      final normalized = variants
          .where((x) {
            final xId = x['id'];
            if (xId == selected['id'] && variants.length > 1) return false;
            return true;
          })
          .map((x) => Map<String, dynamic>.from(x))
          .toList();

      final merged = Map<String, dynamic>.from(selected);
      merged['_variants'] = normalized;
      if (base.isNotEmpty) {
        merged['article'] = base;
      }
      result.add(merged);
    }
    return result;
  }

  String _catalogGroupKey(Map<String, dynamic> item) {
    final specs = item['specifications'];
    if (specs is Map) {
      final parent = (specs['parent_external_id'] as String?)?.trim() ?? '';
      if (parent.isNotEmpty) return 'g:$parent';
    }
    final externalId = (item['external_id'] as String?)?.trim() ?? '';
    if (externalId.isNotEmpty) return 'g:$externalId';
    final article = ((item['article'] as String?) ?? '').trim();
    final base = _baseArticle(article);
    if (base.isNotEmpty) return 'a:$base';
    return 'id:${(item['id'] as String?) ?? ''}';
  }

  String _baseArticle(String article) {
    final raw = article.trim();
    if (raw.isEmpty) return '';
    final idx = raw.indexOf('-');
    if (idx <= 0) return raw;
    return raw.substring(0, idx).trim();
  }

  static String? _normalizeCategory(String? category) {
    final next = (category ?? '').trim();
    if (next.isEmpty) return null;
    final normalized = next.toLowerCase();
    if (normalized == 'все' || normalized == 'all') return null;
    return next;
  }

  static String? _normalizeValue(String? value) {
    final next = (value ?? '').trim();
    return next.isEmpty ? null : next;
  }

  List<String> _buildCategoryLabels(List<dynamic> sections) {
    final namesByLower = <String, String>{};
    for (final section in sections) {
      if (section is! Map) continue;
      final raw = section['name'];
      final name = raw is String ? raw.trim() : '';
      if (name.isEmpty) continue;
      namesByLower.putIfAbsent(name.toLowerCase(), () => name);
    }

    // Customer catalog exposes product categories and the 1C-managed
    // "Новинки" section. Brand and line values stay out of quick filters.
    const customerCategories = [
      'Новинки',
      'Серьги',
      'Кольца',
      'Колье',
      'Браслеты',
      'Каффы',
    ];

    final result = <String>['Все'];
    for (final label in customerCategories) {
      result.add(namesByLower[label.toLowerCase()] ?? label);
    }
    return result;
  }
}

class _CatalogControlChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _CatalogControlChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Container(
          height: 36,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: selected ? GlameColors.whiteGlame : Colors.transparent,
            border: Border.all(
              color: selected
                  ? GlameColors.whiteGlame
                  : GlameColors.borderGray.withAlpha(120),
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                label,
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 0.7,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                  color: selected
                      ? GlameColors.nearBlack
                      : GlameColors.coldLightGray,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CatalogControlIcon extends StatelessWidget {
  final String tooltip;
  final IconData icon;
  final int badge;
  final bool selected;
  final VoidCallback onTap;

  const _CatalogControlIcon({
    required this.tooltip,
    required this.icon,
    required this.onTap,
    this.badge = 0,
    this.selected = false,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Tooltip(
          message: tooltip,
          child: Material(
            color: selected ? GlameColors.whiteGlame : Colors.transparent,
            child: InkWell(
              onTap: onTap,
              child: SizedBox(
                width: 36,
                height: 36,
                child: Icon(
                  icon,
                  size: 20,
                  color: selected
                      ? GlameColors.nearBlack
                      : GlameColors.whiteGlame,
                ),
              ),
            ),
          ),
        ),
        if (badge > 0)
          Positioned(
            top: -5,
            right: -5,
            child: Container(
              width: 17,
              height: 17,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                color: GlameColors.whiteGlame,
                shape: BoxShape.circle,
              ),
              child: Text(
                badge.toString(),
                style: const TextStyle(
                  fontSize: 9,
                  color: GlameColors.nearBlack,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _CatalogSearchDialog extends ConsumerStatefulWidget {
  const _CatalogSearchDialog();

  @override
  ConsumerState<_CatalogSearchDialog> createState() =>
      _CatalogSearchDialogState();
}

class _CatalogSearchDialogState extends ConsumerState<_CatalogSearchDialog> {
  final _controller = TextEditingController();
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _controller.text = ref.read(catalogControllerProvider).search ?? '';
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    _debounce?.cancel();
    ref.read(catalogControllerProvider.notifier).setSearch(_controller.text);
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: GlameColors.nearBlack,
      shape: const RoundedRectangleBorder(),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 540),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 12, 16),
          child: Row(
            children: [
              const Icon(Icons.search, color: GlameColors.whiteGlame),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _controller,
                  autofocus: true,
                  textInputAction: TextInputAction.search,
                  cursorColor: GlameColors.nearBlack,
                  onSubmitted: (_) => _submit(),
                  onChanged: (value) {
                    _debounce?.cancel();
                    _debounce = Timer(
                      const Duration(milliseconds: 350),
                      () => ref
                          .read(catalogControllerProvider.notifier)
                          .setSearch(value),
                    );
                  },
                  style: const TextStyle(color: GlameColors.nearBlack),
                  decoration: const InputDecoration(
                    hintText: 'Поиск по каталогу',
                    hintStyle: TextStyle(color: GlameColors.steelGray),
                    border: InputBorder.none,
                  ),
                ),
              ),
              IconButton(
                tooltip: 'Закрыть',
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Icons.close, color: GlameColors.whiteGlame),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

String _normalizeCatalogDisplayLabel(String value) {
  final normalized = value.trim();
  if (normalized.isEmpty) return normalized;
  const replacements = {
    'WRINKLES OG TIME': 'WRINKLES OF TIME',
    'Wrinkles Og Time': 'Wrinkles Of Time',
    'wrinkles og time': 'Wrinkles of Time',
  };
  return replacements[normalized] ?? normalized;
}

bool _hasPositiveStock(Map<String, dynamic> item) {
  final stock =
      _asStockNumber(item['stock']) ?? _asStockNumber(item['quantity']);
  if (stock != null && stock > 0) return true;

  final specs = item['specifications'];
  if (specs is Map) {
    final quantity = _asStockNumber(specs['quantity']);
    if (quantity != null && quantity > 0) return true;
  }
  return false;
}

num? _asStockNumber(dynamic value) {
  if (value is num) return value;
  if (value is String) return num.tryParse(value.trim().replaceAll(',', '.'));
  return null;
}

class _ProductCardDarkrain extends ConsumerWidget {
  final Map<String, dynamic> item;
  final bool pickMode;
  final ValueChanged<Map<String, dynamic>>? onPick;

  const _ProductCardDarkrain({
    super.key,
    required this.item,
    this.pickMode = false,
    this.onPick,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final variants = _extractVariants(item);
    if (variants.isEmpty) return const SizedBox();

    final current = variants.first;
    final id = (current['id'] as String?) ?? '';
    final name = (current['name'] as String?) ?? '';
    final brandRaw =
        ((current['brand'] as String?) ?? (item['brand'] as String?) ?? '')
            .trim();
    final brand = brandRaw.isEmpty
        ? null
        : _normalizeCatalogDisplayLabel(brandRaw).toUpperCase();
    var totalStock = _totalStock(variants);
    final loyaltyPoints =
        ref.watch(authControllerProvider).user?.loyaltyPoints ?? 0;
    var priceLabel = _buildPriceLabel(item, variants, loyaltyPoints);
    String? remoteImageUrl;
    if (id.isNotEmpty) {
      final remoteVariants = ref.watch(productVariantsProvider(id));
      final remoteData = remoteVariants.maybeWhen(
        data: (data) {
          final baseRaw = data['base'];
          final base = baseRaw is Map
              ? Map<String, dynamic>.from(baseRaw)
              : <String, dynamic>{};
          final variantsRaw = data['variants'];
          final remote = variantsRaw is List
              ? variantsRaw
                    .whereType<Map>()
                    .map((x) => Map<String, dynamic>.from(x))
                    .toList()
              : <Map<String, dynamic>>[];
          if (base.isEmpty && remote.isEmpty) return '';
          final baseImages = base['images'];
          if (baseImages is List && baseImages.isNotEmpty) {
            remoteImageUrl = resolveAssetUrl(baseImages.first);
          }
          totalStock = _totalStock([if (base.isNotEmpty) base, ...remote]);
          return _buildPriceLabel(
            base.isEmpty ? item : base,
            remote,
            loyaltyPoints,
          );
        },
        orElse: () => '',
      );
      if (remoteData.isNotEmpty) {
        priceLabel = remoteData;
      }
    }
    final isAvailable = totalStock > 0;
    final images = current['images'];
    String? imageUrl = (images is List && images.isNotEmpty)
        ? resolveAssetUrl(images.first)
        : null;

    if (imageUrl == null) {
      final parentImages = item['images'];
      if (parentImages is List && parentImages.isNotEmpty) {
        imageUrl = resolveAssetUrl(parentImages.first);
      }
    }
    imageUrl ??= remoteImageUrl;

    final pickProduct = <String, dynamic>{
      ...item,
      ...current,
      'id': id,
      'name': name,
      'brand': brandRaw.isNotEmpty ? brandRaw : item['brand'],
      'image_url': imageUrl,
      'images': current['images'] ?? item['images'],
      'price': current['price'] ?? item['price'],
    };

    return InkWell(
      onTap: id.isEmpty
          ? null
          : pickMode
          ? () => onPick?.call(pickProduct)
          : () => context.push('/product/$id'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: _glameMediaAspectRatio,
            child: Stack(
              fit: StackFit.expand,
              children: [
                imageUrl != null
                    ? CachedNetworkImage(
                        imageUrl: imageUrl,
                        fit: BoxFit.cover,
                        placeholder: (_, _) =>
                            Container(color: GlameColors.graphite),
                        errorWidget: (_, _, _) =>
                            Container(color: GlameColors.graphite),
                      )
                    : Container(color: GlameColors.graphite),
                Positioned(
                  top: 8,
                  left: 8,
                  child: brand == null
                      ? const SizedBox.shrink()
                      : Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 4,
                          ),
                          decoration: BoxDecoration(
                            color: GlameColors.nearBlack.withAlpha(166),
                          ),
                          child: Text(
                            brand,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 9,
                              fontWeight: FontWeight.w600,
                              letterSpacing: 0.6,
                              color: GlameColors.whiteGlame,
                            ),
                          ),
                        ),
                ),
                Positioned(
                  top: 8,
                  right: 8,
                  child: _WishlistButton(productId: id),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 32,
            child: Text(
              name.toUpperCase(),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 11,
                letterSpacing: 0.8,
                color: GlameColors.whiteGlame,
                height: 1.4,
              ),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            priceLabel,
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w400,
              color: GlameColors.coldLightGray,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            isAvailable ? 'В наличии' : 'Скоро в наличии',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 10,
              letterSpacing: 0.4,
              color: isAvailable
                  ? GlameColors.steelGray
                  : GlameColors.borderGray,
            ),
          ),
          if (pickMode) ...[
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              height: 36,
              child: OutlinedButton(
                onPressed: id.isEmpty ? null : () => onPick?.call(pickProduct),
                style: OutlinedButton.styleFrom(
                  foregroundColor: GlameColors.whiteGlame,
                  side: const BorderSide(color: GlameColors.whiteGlame),
                  shape: const RoundedRectangleBorder(),
                  padding: EdgeInsets.zero,
                ),
                child: const Text(
                  'ВЫБРАТЬ ОСНОВУ',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  List<Map<String, dynamic>> _extractVariants(Map<String, dynamic> item) {
    final result = <Map<String, dynamic>>[Map<String, dynamic>.from(item)];
    final seenIds = <String>{
      if ((item['id'] as String?)?.isNotEmpty == true) item['id'] as String,
    };
    final raw = item['_variants'];
    if (raw is List) {
      for (final variant in raw.whereType<Map>()) {
        final normalized = Map<String, dynamic>.from(variant);
        final id = normalized['id'] as String?;
        if (id != null && id.isNotEmpty && !seenIds.add(id)) continue;
        result.add(normalized);
      }
    }
    return result;
  }

  num _totalStock(List<Map<String, dynamic>> variants) {
    var total = 0.0;
    final seenIds = <String>{};
    for (final variant in variants) {
      final id = variant['id'] as String?;
      if (id != null && id.isNotEmpty && !seenIds.add(id)) continue;
      total += _stockAmount(variant).toDouble();
    }
    return total;
  }

  num _stockAmount(Map<String, dynamic> item) {
    final stock =
        _asStockNumber(item['stock']) ?? _asStockNumber(item['quantity']);
    if (stock != null) return stock;

    final specs = item['specifications'];
    if (specs is Map) {
      return _asStockNumber(specs['quantity']) ?? 0;
    }
    return 0;
  }

  int? _asInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) return int.tryParse(value.trim());
    return null;
  }

  String _buildPriceLabel(
    Map<String, dynamic> item,
    List<Map<String, dynamic>> variants,
    int loyaltyPoints,
  ) {
    final candidates = <Map<String, dynamic>>[item, ...variants];
    final all = candidates
        .map((x) => _asInt(x['price']))
        .whereType<int>()
        .toList();
    if (all.isEmpty) return '';

    final positive = all.where((x) => x > 0).toList();
    if (positive.isEmpty) return '';
    final prices = positive
        .map((price) => discountedPriceKopeks(price, loyaltyPoints))
        .toList();
    prices.sort();

    final max = prices.last;
    return formatRubFromKopeks(max);
  }
}

class _WishlistButton extends ConsumerWidget {
  final String productId;

  const _WishlistButton({required this.productId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isOn = ref.watch(wishlistControllerProvider).contains(productId);
    return InkWell(
      onTap: () =>
          ref.read(wishlistControllerProvider.notifier).toggle(productId),
      child: Container(
        padding: const EdgeInsets.all(6),
        decoration: const BoxDecoration(),
        child: Icon(
          isOn ? Icons.favorite : Icons.favorite_border,
          size: 16,
          color: isOn ? GlameColors.whiteGlame : GlameColors.whiteGlame,
        ),
      ),
    );
  }
}
