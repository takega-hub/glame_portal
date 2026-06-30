import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/glame_theme.dart';
import '../../core/network/asset_url.dart';
import '../../core/formatters/rub.dart';
import '../auth/auth_controller.dart';
import '../home/home_providers.dart';
import 'catalog_filter_sheet.dart';
import 'catalog_controller.dart';
import '../product/product_providers.dart';
import '../wishlist/wishlist_controller.dart';

class CatalogScreen extends ConsumerStatefulWidget {
  final String title;
  final String? initialCategory;
  final String? initialBrand;
  final String? initialSearch;
  final bool pickLookBase;

  const CatalogScreen({
    super.key,
    this.title = 'КАТАЛОГ',
    this.initialCategory,
    this.initialBrand,
    this.initialSearch,
    this.pickLookBase = false,
  });

  @override
  ConsumerState<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends ConsumerState<CatalogScreen> {
  final scroll = ScrollController();
  final searchController = TextEditingController();
  Timer? _searchDebounce;
  String? selectedCategory;

  @override
  void initState() {
    super.initState();
    selectedCategory = _normalizeCategory(widget.initialCategory);
    final initialSearch = (widget.initialSearch ?? '').trim();
    if (initialSearch.isNotEmpty) {
      searchController.text = initialSearch;
    }
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
      if (initial != null || initialBrand != null || initialSearch.isNotEmpty) {
        ref
            .read(catalogControllerProvider.notifier)
            .resetAndApply(
              category: initial,
              brand: initialBrand,
              search: initialSearch,
            );
      }
    });
  }

  @override
  void didUpdateWidget(covariant CatalogScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.initialCategory == widget.initialCategory &&
        oldWidget.initialBrand == widget.initialBrand &&
        oldWidget.initialSearch == widget.initialSearch) {
      return;
    }
    final next = _normalizeCategory(widget.initialCategory);
    final nextBrand = _normalizeValue(widget.initialBrand);
    final nextSearch = (widget.initialSearch ?? '').trim();
    setState(() {
      selectedCategory = next;
      searchController.text = nextSearch;
    });
    ref
        .read(catalogControllerProvider.notifier)
        .resetAndApply(category: next, brand: nextBrand, search: nextSearch);
  }

  @override
  void dispose() {
    scroll.dispose();
    _searchDebounce?.cancel();
    searchController.dispose();
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
    final isWideScreen = MediaQuery.of(context).size.width > 768;

    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(context),
            _buildSearchAndActions(context, catalog, characteristicsAsync),
            _buildCategoryTabs(categories, isWideScreen),
            Expanded(
              child: RefreshIndicator(
                color: GlameColors.whiteGlame,
                onRefresh: controller.refresh,
                child: CustomScrollView(
                  controller: scroll,
                  slivers: [
                    SliverPadding(
                      padding: EdgeInsets.fromLTRB(
                        isWideScreen ? 40 : 16,
                        18,
                        isWideScreen ? 40 : 16,
                        28,
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
                        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: catalog.oneColumn
                              ? 1
                              : (isWideScreen ? 4 : 2),
                          mainAxisSpacing: isWideScreen ? 30 : 22,
                          crossAxisSpacing: isWideScreen ? 24 : 14,
                          childAspectRatio: catalog.oneColumn
                              ? (isWideScreen ? 2.25 : 0.92)
                              : widget.pickLookBase
                              ? (isWideScreen ? 0.56 : 0.48)
                              : (isWideScreen ? 0.62 : 0.56),
                        ),
                      ),
                    ),
                    SliverToBoxAdapter(
                      child: Padding(
                        padding: EdgeInsets.all(isWideScreen ? 40 : 16),
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
                            if (!catalog.loading && !catalog.hasMore)
                              Text(
                                'Показано ${groupedItems.length} из ${catalog.total}',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 12,
                                  letterSpacing: 1,
                                  color: GlameColors.coldLightGray,
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
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    final isWideScreen = MediaQuery.of(context).size.width > 768;
    final title = widget.pickLookBase ? 'ВЫБЕРИТЕ ОСНОВУ' : widget.title;
    return Container(
      padding: EdgeInsets.fromLTRB(
        isWideScreen ? 40 : 20,
        24,
        isWideScreen ? 40 : 20,
        16,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (widget.pickLookBase) ...[
            IconButton(
              tooltip: 'Назад',
              onPressed: () => context.pop(),
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
                Text(
                  title,
                  style: TextStyle(
                    fontSize: isWideScreen ? 44 : 36,
                    fontWeight: FontWeight.w400,
                    height: 0.95,
                    color: GlameColors.whiteGlame,
                  ),
                ),
                const SizedBox(height: 10),
                Container(width: 54, height: 1, color: GlameColors.steelGray),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Text(
            '${_groupCatalogItems(ref.watch(catalogControllerProvider).items).length} товаров',
            style: const TextStyle(
              fontSize: 12,
              color: GlameColors.coldLightGray,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSearchAndActions(
    BuildContext context,
    CatalogState catalog,
    AsyncValue<Map<String, dynamic>> characteristicsAsync,
  ) {
    final isWideScreen = MediaQuery.of(context).size.width > 768;
    final controller = ref.read(catalogControllerProvider.notifier);
    final activeFilters = _activeFiltersCount(catalog);
    return Padding(
      padding: EdgeInsets.fromLTRB(
        isWideScreen ? 40 : 20,
        0,
        isWideScreen ? 40 : 20,
        12,
      ),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: searchController,
                  textInputAction: TextInputAction.search,
                  onChanged: (value) {
                    _searchDebounce?.cancel();
                    _searchDebounce = Timer(
                      const Duration(milliseconds: 350),
                      () {
                        ref
                            .read(catalogControllerProvider.notifier)
                            .setSearch(value);
                      },
                    );
                  },
                  decoration: InputDecoration(
                    hintText: 'Поиск по каталогу',
                    prefixIcon: const Icon(Icons.search, size: 20),
                    suffixIcon: catalog.search == null
                        ? null
                        : IconButton(
                            tooltip: 'Очистить',
                            onPressed: () {
                              _searchDebounce?.cancel();
                              searchController.clear();
                              ref
                                  .read(catalogControllerProvider.notifier)
                                  .setSearch(null);
                            },
                            icon: const Icon(Icons.close, size: 18),
                          ),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Stack(
                clipBehavior: Clip.none,
                children: [
                  IconButton.outlined(
                    tooltip: 'Фильтры',
                    onPressed: () =>
                        _openFilters(context, catalog, characteristicsAsync),
                    style: IconButton.styleFrom(
                      foregroundColor: GlameColors.whiteGlame,
                      side: BorderSide(
                        color: activeFilters > 0
                            ? GlameColors.whiteGlame
                            : GlameColors.borderGray,
                      ),
                      shape: const RoundedRectangleBorder(),
                    ),
                    icon: const Icon(Icons.tune),
                  ),
                  if (activeFilters > 0)
                    Positioned(
                      top: -3,
                      right: -3,
                      child: Container(
                        width: 18,
                        height: 18,
                        alignment: Alignment.center,
                        decoration: const BoxDecoration(
                          color: GlameColors.whiteGlame,
                          shape: BoxShape.circle,
                        ),
                        child: Text(
                          activeFilters.toString(),
                          style: const TextStyle(
                            fontSize: 10,
                            color: GlameColors.nearBlack,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(width: 10),
              IconButton.outlined(
                tooltip: catalog.oneColumn ? 'Плитка' : 'Список',
                onPressed: () {
                  ref.read(catalogControllerProvider.notifier).toggleLayout();
                },
                style: IconButton.styleFrom(
                  foregroundColor: GlameColors.whiteGlame,
                  side: const BorderSide(color: GlameColors.borderGray),
                  shape: const RoundedRectangleBorder(),
                ),
                icon: Icon(
                  catalog.oneColumn ? Icons.grid_view : Icons.view_agenda,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          InkWell(
            onTap: () => controller.setInStockOnly(!catalog.inStockOnly),
            child: Row(
              children: [
                SizedBox(
                  width: 28,
                  height: 28,
                  child: Checkbox(
                    value: catalog.inStockOnly,
                    onChanged: (value) =>
                        controller.setInStockOnly(value ?? false),
                    activeColor: GlameColors.whiteGlame,
                    checkColor: GlameColors.nearBlack,
                    visualDensity: VisualDensity.compact,
                  ),
                ),
                const SizedBox(width: 8),
                const Text(
                  'В наличии',
                  style: TextStyle(fontSize: 13, color: GlameColors.whiteGlame),
                ),
              ],
            ),
          ),
        ],
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
      backgroundColor: const Color(0xFFF7F6F4),
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
      return await ref.read(productCharacteristicsProvider.future);
    } catch (_) {
      return const <String, dynamic>{};
    }
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

  Widget _buildCategoryTabs(List<String> categories, bool isWideScreen) {
    return Container(
      padding: EdgeInsets.symmetric(vertical: 12),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(color: GlameColors.borderGray.withAlpha(130)),
        ),
      ),
      child: SizedBox(
        height: 36,
        child: ListView.separated(
          padding: EdgeInsets.symmetric(horizontal: isWideScreen ? 40 : 20),
          scrollDirection: Axis.horizontal,
          itemCount: categories.length,
          separatorBuilder: (_, _) => SizedBox(width: isWideScreen ? 32 : 16),
          itemBuilder: (context, i) {
            final label = categories[i];
            final isActive =
                (i == 0 && selectedCategory == null) ||
                selectedCategory == label;
            return InkWell(
              onTap: () {
                setState(() {
                  selectedCategory = i == 0 ? null : label;
                });
                ref
                    .read(catalogControllerProvider.notifier)
                    .setCategory(i == 0 ? null : label);
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                decoration: BoxDecoration(
                  border: Border.all(
                    color: isActive
                        ? GlameColors.whiteGlame
                        : GlameColors.borderGray.withAlpha(120),
                  ),
                  color: isActive ? GlameColors.whiteGlame : Colors.transparent,
                ),
                child: Center(
                  child: Text(
                    label.toUpperCase(),
                    style: TextStyle(
                      fontSize: 11,
                      letterSpacing: 0.8,
                      fontWeight: isActive ? FontWeight.w500 : FontWeight.w400,
                      color: isActive
                          ? GlameColors.nearBlack
                          : GlameColors.coldLightGray,
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
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
      if (base.isNotEmpty) {
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
    return next.isEmpty ? null : next;
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

    // Customer catalog must expose only product categories here.
    // Brand/line values (AGafi, Antura, Eva Rites, etc.) and marketing
    // collections (NEW/SALE) belong to filters or dedicated collection flows.
    const customerCategories = [
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
    final isAvailable = [item, ...variants].any(_hasPositiveStock);
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
          Expanded(
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
          Text(
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
            isAvailable ? 'В наличии' : 'Нет в наличии',
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
    final raw = item['_variants'];
    if (raw is List) {
      return raw
          .whereType<Map>()
          .map((x) => Map<String, dynamic>.from(x))
          .toList();
    }
    return [Map<String, dynamic>.from(item)];
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

    final min = prices.first;
    final max = prices.last;
    if (min == max) {
      return formatRubFromKopeks(min);
    }
    return 'от ${formatRubFromKopeks(min)} до ${formatRubFromKopeks(max)}';
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
