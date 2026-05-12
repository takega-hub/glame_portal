import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/glame_theme.dart';
import '../../core/network/asset_url.dart';
import '../../core/formatters/rub.dart';
import '../home/home_providers.dart';
import 'catalog_controller.dart';
import '../product/product_providers.dart';
import '../wishlist/wishlist_controller.dart';

class CatalogScreen extends ConsumerStatefulWidget {
  final String title;
  final String? initialCategory;
  final String? initialBrand;
  final String? initialSearch;

  const CatalogScreen({
    super.key,
    this.title = 'КАТАЛОГ',
    this.initialCategory,
    this.initialBrand,
    this.initialSearch,
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
      backgroundColor: GlameColors.textPrimary,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(context),
            _buildSearchAndActions(context, catalog),
            _buildCategoryTabs(categories, isWideScreen),
            Expanded(
              child: RefreshIndicator(
                color: GlameColors.gold,
                onRefresh: controller.refresh,
                child: CustomScrollView(
                  controller: scroll,
                  slivers: [
                    SliverPadding(
                      padding: EdgeInsets.symmetric(
                        horizontal: isWideScreen ? 40 : 16,
                        vertical: 20,
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
                          );
                        }, childCount: groupedItems.length),
                        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: catalog.oneColumn
                              ? 1
                              : (isWideScreen ? 4 : 2),
                          mainAxisSpacing: isWideScreen ? 24 : 16,
                          crossAxisSpacing: isWideScreen ? 24 : 12,
                          childAspectRatio: catalog.oneColumn
                              ? (isWideScreen ? 2.1 : 0.92)
                              : (isWideScreen ? 0.65 : 0.6),
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
                                    color: GlameColors.gold,
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
                                  color: GlameColors.textSecondary,
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
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: isWideScreen ? 40 : 20,
        vertical: 18,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  widget.title,
                  style: TextStyle(
                    fontSize: isWideScreen ? 44 : 36,
                    fontWeight: FontWeight.w400,
                    height: 0.95,
                    color: GlameColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 10),
                Container(width: 44, height: 1, color: GlameColors.lightGray),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Text(
            '${_groupCatalogItems(ref.watch(catalogControllerProvider).items).length} товаров',
            style: TextStyle(fontSize: 12, color: GlameColors.steelGray),
          ),
        ],
      ),
    );
  }

  Widget _buildSearchAndActions(BuildContext context, CatalogState catalog) {
    final isWideScreen = MediaQuery.of(context).size.width > 768;
    final controller = ref.read(catalogControllerProvider.notifier);
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
              IconButton.outlined(
                tooltip: catalog.oneColumn ? 'Плитка' : 'Список',
                onPressed: () {
                  ref.read(catalogControllerProvider.notifier).toggleLayout();
                },
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
                    activeColor: GlameColors.gold,
                    visualDensity: VisualDensity.compact,
                  ),
                ),
                const SizedBox(width: 8),
                const Text(
                  'В наличии',
                  style: TextStyle(
                    fontSize: 13,
                    color: GlameColors.textPrimary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCategoryTabs(List<String> categories, bool isWideScreen) {
    return Container(
      padding: EdgeInsets.symmetric(vertical: 12),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(color: GlameColors.lightGray.withAlpha(51)),
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
                        ? GlameColors.textPrimary
                        : GlameColors.lightGray.withAlpha(77),
                  ),
                  color: isActive ? GlameColors.surface : Colors.transparent,
                ),
                child: Center(
                  child: Text(
                    label.toUpperCase(),
                    style: TextStyle(
                      fontSize: 11,
                      letterSpacing: 0.8,
                      fontWeight: isActive ? FontWeight.w500 : FontWeight.w400,
                      color: isActive
                          ? GlameColors.textPrimary
                          : GlameColors.textSecondary,
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
    final names = <String>[];
    final seen = <String>{};
    for (final section in sections) {
      if (section is! Map) continue;
      final raw = section['name'];
      final name = raw is String ? raw.trim() : '';
      if (name.isEmpty || !seen.add(name.toLowerCase())) continue;
      names.add(name);
    }

    const preferred = [
      'Кольца',
      'Серьги',
      'Колье',
      'Браслеты',
      'Каффы',
      'NEW',
      'SALE',
    ];
    final result = <String>['Все'];
    for (final label in preferred) {
      final match = names.where(
        (name) => name.toLowerCase() == label.toLowerCase(),
      );
      if (match.isNotEmpty) result.add(match.first);
    }
    for (final name in names) {
      if (result.any((item) => item.toLowerCase() == name.toLowerCase())) {
        continue;
      }
      result.add(name);
    }
    return result;
  }
}

class _ProductCardDarkrain extends ConsumerWidget {
  final Map<String, dynamic> item;

  const _ProductCardDarkrain({super.key, required this.item});

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
    final brand = brandRaw.isEmpty ? null : brandRaw.toUpperCase();
    var priceLabel = _buildPriceLabel(item, variants);
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
          return _buildPriceLabel(base.isEmpty ? item : base, remote);
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

    return InkWell(
      onTap: id.isEmpty ? null : () => context.push('/product/$id'),
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
                            Container(color: GlameColors.surface),
                        errorWidget: (_, _, _) =>
                            Container(color: GlameColors.surface),
                      )
                    : Container(color: GlameColors.surface),
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
                            color: GlameColors.textPrimary.withAlpha(166),
                          ),
                          child: Text(
                            brand,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 9,
                              fontWeight: FontWeight.w600,
                              letterSpacing: 0.6,
                              color: GlameColors.surface2,
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
              color: GlameColors.textPrimary,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            priceLabel,
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w400,
              color: GlameColors.textPrimary,
            ),
          ),
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
  ) {
    final candidates = <Map<String, dynamic>>[item, ...variants];
    final all = candidates
        .map((x) => _asInt(x['price']))
        .whereType<int>()
        .toList();
    if (all.isEmpty) return '';

    final positive = all.where((x) => x > 0).toList();
    if (positive.isEmpty) return '';
    final prices = positive;
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
        decoration: BoxDecoration(
          color: GlameColors.textPrimary.withAlpha(128),
          border: Border.all(color: GlameColors.surface2.withAlpha(80)),
        ),
        child: Icon(
          isOn ? Icons.favorite : Icons.favorite_border,
          size: 16,
          color: isOn ? GlameColors.gold : GlameColors.surface2,
        ),
      ),
    );
  }
}
