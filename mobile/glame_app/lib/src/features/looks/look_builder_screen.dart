import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters/rub.dart';
import '../../core/network/asset_url.dart';
import '../../core/theme/glame_theme.dart';
import '../catalog/catalog_controller.dart';
import '../customer/customer_cabinet_providers.dart';
import '../wishlist/wishlist_controller.dart';
import 'user_created_looks_controller.dart';

class LookBuilderScreen extends ConsumerStatefulWidget {
  final Map<String, dynamic>? initialLook;

  const LookBuilderScreen({super.key, this.initialLook});

  @override
  ConsumerState<LookBuilderScreen> createState() => _LookBuilderScreenState();
}

class _LookBuilderScreenState extends ConsumerState<LookBuilderScreen> {
  String _goal = 'Подарок';
  late final TextEditingController _nameController;
  String? _baseProductId;
  final Map<String, Map<String, dynamic>> _pickedCatalogProducts =
      <String, Map<String, dynamic>>{};
  final Set<String> _accentProductIds = <String>{};
  final ScrollController _scrollController = ScrollController();
  final GlobalKey _baseSectionKey = GlobalKey();
  final GlobalKey _accentSectionKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController();
    final initialLook = widget.initialLook;
    if (initialLook == null) return;
    _nameController.text =
        _asText(initialLook['look_name'] ?? initialLook['name']) ?? '';
    _goal = _asText(initialLook['look_style'] ?? initialLook['style']) ?? _goal;
    final products = _lookProducts(initialLook);
    for (final product in products) {
      final id = _productId(product);
      if (id.isEmpty) continue;
      _pickedCatalogProducts[id] = product;
    }
    if (products.isNotEmpty) {
      _baseProductId = _productId(products.first);
      _accentProductIds.addAll(
        products.skip(1).map(_productId).where((id) => id.isNotEmpty).take(3),
      );
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final catalog = ref.watch(catalogControllerProvider);
    final purchaseProducts = _productsFromAsync(
      ref.watch(customerPurchaseHistoryProvider),
    );
    final favoriteProducts = _favoriteProductsFromState(catalog.items);
    final purchasedIds = _productIdSet(purchaseProducts);
    final favoriteIds = _productIdSet(favoriteProducts)
      ..addAll(ref.watch(wishlistControllerProvider));
    final products = _mergePickedProducts([
      ...purchaseProducts,
      ...favoriteProducts,
      ...catalog.items,
    ]);
    final baseProducts = _uniqueProducts([
      ...purchaseProducts,
      ...favoriteProducts,
      ...products,
    ]).take(3).toList(growable: false);
    final baseProduct = _selectedProduct(products, _baseProductId);
    final accentProducts = baseProduct == null
        ? const <Map<String, dynamic>>[]
        : _rankAccentProducts(
            baseProduct: baseProduct,
            candidates: products,
            purchasedIds: purchasedIds,
            favoriteIds: favoriteIds,
          ).take(6).toList(growable: false);
    final selectedAccentProducts = _accentProductIds
        .map((id) => _selectedProduct(products, id))
        .whereType<Map<String, dynamic>>()
        .toList(growable: false);
    final hasBase = _baseProductId != null;
    final totalPrice =
        (baseProduct == null ? 0 : _productPriceKopeks(baseProduct)) +
        selectedAccentProducts.fold<int>(
          0,
          (sum, product) => sum + _productPriceKopeks(product),
        );
    final summaryHint = !hasBase
        ? 'ШАГ 1: ДОБАВЬТЕ ОСНОВУ ДЛЯ ПРОДОЛЖЕНИЯ'
        : _accentProductIds.isEmpty
        ? 'ШАГ 2: ДОБАВЬТЕ АКЦЕНТ ИЛИ СОХРАНИТЕ ОСНОВУ'
        : 'ГОТОВО: ПРОВЕРЬТЕ СЕТ И СОХРАНИТЕ';

    return Scaffold(
      backgroundColor: const Color(0xFF121416),
      body: Column(
        children: [
          GlameTopAppBar(
            onLogoPressed: () => context.go('/home'),
            onCartPressed: () => context.go('/home?tab=11'),
            onSearchPressed: () => context.go('/home?tab=1'),
          ),
          _BuilderStepProgress(
            baseSelected: hasBase,
            accentCount: _accentProductIds.length,
          ),
          Expanded(
            child: RefreshIndicator(
              color: GlameColors.whiteGlame,
              backgroundColor: const Color(0xFF1A1C1E),
              onRefresh: () =>
                  ref.read(catalogControllerProvider.notifier).refresh(),
              child: ListView(
                controller: _scrollController,
                padding: EdgeInsets.zero,
                children: [
                  const _LookBuilderIntro(),
                  _CanvasSection(
                    baseProduct: baseProduct,
                    accents: selectedAccentProducts,
                    onBaseTap: () => _scrollToKey(_baseSectionKey),
                    onAccentTap: () {
                      if (hasBase) {
                        _scrollToKey(_accentSectionKey);
                      } else {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Сначала выберите основу образа.'),
                          ),
                        );
                      }
                    },
                  ),
                  _NameSection(
                    controller: _nameController,
                    suggestedName: _generatedLookName([
                      ?baseProduct,
                      ...selectedAccentProducts,
                    ]),
                    selectedOccasion: _goal,
                    onOccasionChanged: (value) => setState(() => _goal = value),
                  ),
                  KeyedSubtree(
                    key: _baseSectionKey,
                    child: _ProductsSection(
                      title: '1. ВАША ОСНОВА',
                      counter: _baseProductId == null ? '0 / 1' : '1 / 1',
                      products: baseProducts,
                      selectedIds: {?_baseProductId},
                      maxSelected: 1,
                      loading: catalog.loading && products.isEmpty,
                      error: catalog.error,
                      onProductTap: (product) {
                        final id = _productId(product);
                        if (id.isEmpty) return;
                        setState(() {
                          _baseProductId = _baseProductId == id ? null : id;
                          if (_baseProductId == null) {
                            _accentProductIds.clear();
                          }
                        });
                      },
                      onMoreTap: () => _pickBaseFromCatalog(context),
                    ),
                  ),
                  KeyedSubtree(
                    key: _accentSectionKey,
                    child: _ProductsSection(
                      title: '2. АКЦЕНТЫ',
                      counter: '${_accentProductIds.length} / 3',
                      products: hasBase
                          ? accentProducts
                          : const <Map<String, dynamic>>[],
                      selectedIds: _accentProductIds,
                      maxSelected: 3,
                      locked: !hasBase,
                      lockedText:
                          'Выберите основу, чтобы разблокировать доступ к акцентам.',
                      loading: catalog.loading && products.isEmpty,
                      onProductTap: (product) {
                        final id = _productId(product);
                        if (id.isEmpty) return;
                        setState(() {
                          if (_accentProductIds.contains(id)) {
                            _accentProductIds.remove(id);
                          } else if (_accentProductIds.length < 3) {
                            _accentProductIds.add(id);
                          }
                        });
                      },
                      onMoreTap: () => context.go('/home?tab=1'),
                    ),
                  ),
                  _BuilderSummaryPanel(
                    totalPrice: totalPrice,
                    canSave: hasBase,
                    hint: summaryHint,
                    onSave: () => _saveLook(context),
                  ),
                  const SizedBox(height: 88),
                ],
              ),
            ),
          ),
        ],
      ),
      bottomNavigationBar: const _LookBuilderBottomBar(),
    );
  }

  Map<String, dynamic>? _selectedProduct(
    List<Map<String, dynamic>> products,
    String? id,
  ) {
    if (id == null || id.isEmpty) return null;
    for (final product in products) {
      if (_productId(product) == id) return product;
    }
    return null;
  }

  List<Map<String, dynamic>> _mergePickedProducts(
    List<Map<String, dynamic>> products,
  ) {
    if (_pickedCatalogProducts.isEmpty) return products;
    final seen = products.map(_productId).where((id) => id.isNotEmpty).toSet();
    final picked = _pickedCatalogProducts.values
        .where((item) => seen.add(_productId(item)))
        .toList(growable: false);
    return [...picked, ...products];
  }

  Future<void> _saveLook(BuildContext context) async {
    final products = _allBuilderProducts();
    final baseProduct = _selectedProduct(products, _baseProductId);
    if (baseProduct == null) return;
    final accentProducts = _accentProductIds
        .map((id) => _selectedProduct(products, id))
        .whereType<Map<String, dynamic>>()
        .toList(growable: false);
    final selectedProducts = [baseProduct, ...accentProducts];
    final totalPrice = selectedProducts.fold<int>(
      0,
      (sum, product) => sum + _productPriceKopeks(product),
    );
    await ref
        .read(userCreatedLooksProvider.notifier)
        .upsertLook(
          id: _editingLookId,
          name: _effectiveLookName(selectedProducts),
          goal: _goal,
          totalPrice: totalPrice,
          products: selectedProducts,
        );
    if (!context.mounted) return;
    final count = selectedProducts.length;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Образ "${_effectiveLookName(selectedProducts)}" сохранен: $count издел.',
        ),
        action: SnackBarAction(
          label: 'МОЙ СТИЛЬ',
          onPressed: () => context.go('/home?tab=2'),
        ),
      ),
    );
  }

  Future<void> _pickBaseFromCatalog(BuildContext context) async {
    final result = await context.push<Map<String, dynamic>>(
      '/catalog?pick=look_base',
    );
    if (!mounted || result == null) return;
    final id = _productId(result);
    if (id.isEmpty) return;
    setState(() {
      _pickedCatalogProducts[id] = result;
      _baseProductId = id;
      _accentProductIds.clear();
    });
    _scrollToKey(_accentSectionKey);
  }

  String? get _editingLookId {
    final id = _asText(widget.initialLook?['id']);
    return id == null || id.isEmpty ? null : id;
  }

  String _effectiveLookName(List<Map<String, dynamic>> selectedProducts) {
    final customName = _nameController.text.trim();
    if (customName.isNotEmpty) return customName;
    return _generatedLookName(selectedProducts);
  }

  List<Map<String, dynamic>> _favoriteProductsFromState(
    List<Map<String, dynamic>> catalogProducts,
  ) {
    final favoriteRows = ref
        .watch(customerFavoriteProductsProvider)
        .maybeWhen(
          data: (rows) => rows,
          orElse: () => const <Map<String, dynamic>>[],
        );
    final fromServer = favoriteRows
        .map(_normalizeProductRow)
        .whereType<Map<String, dynamic>>()
        .toList(growable: false);
    if (fromServer.isNotEmpty) return fromServer;

    final favoriteIds = ref.watch(wishlistControllerProvider);
    if (favoriteIds.isEmpty) return const <Map<String, dynamic>>[];
    return catalogProducts
        .where((product) => favoriteIds.contains(_productId(product)))
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _allBuilderProducts() {
    final catalogItems = ref.read(catalogControllerProvider).items;
    final purchaseProducts = _productsFromAsync(
      ref.read(customerPurchaseHistoryProvider),
    );
    final favoriteProducts = _favoriteProductsFromState(catalogItems);
    return _mergePickedProducts([
      ...purchaseProducts,
      ...favoriteProducts,
      ...catalogItems,
    ]);
  }

  void _scrollToKey(GlobalKey key) {
    final targetContext = key.currentContext;
    if (targetContext == null) return;
    Scrollable.ensureVisible(
      targetContext,
      duration: const Duration(milliseconds: 360),
      curve: Curves.easeOutCubic,
      alignment: 0.08,
    );
  }
}

// Kept only for compatibility with hot-reload sessions that may still reference
// the previous builder route tree.
// ignore: unused_element
class _LookBuilderTopBar extends StatelessWidget {
  final VoidCallback onMenu;
  final VoidCallback onCart;

  const _LookBuilderTopBar({required this.onMenu, required this.onCart});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 54,
      decoration: const BoxDecoration(
        color: Color(0xFF121416),
        border: Border(bottom: BorderSide(color: Color(0xFF5C6064))),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Row(
        children: [
          IconButton(
            onPressed: onMenu,
            icon: const Icon(Icons.menu, color: Colors.white, size: 24),
            tooltip: 'Меню',
          ),
          const Spacer(),
          const Text(
            'GLAME',
            style: TextStyle(
              color: Colors.white,
              fontSize: 24,
              fontWeight: FontWeight.w700,
              letterSpacing: 5,
            ),
          ),
          const Spacer(),
          IconButton(
            onPressed: onCart,
            icon: const Icon(
              Icons.shopping_bag_outlined,
              color: Colors.white,
              size: 22,
            ),
            tooltip: 'Корзина',
          ),
        ],
      ),
    );
  }
}

class _BuilderStepProgress extends StatelessWidget {
  final bool baseSelected;
  final int accentCount;

  const _BuilderStepProgress({
    required this.baseSelected,
    required this.accentCount,
  });

  @override
  Widget build(BuildContext context) {
    final activeIndex = !baseSelected
        ? 0
        : accentCount == 0
        ? 1
        : 2;
    const labels = ['1. ОСНОВА', '2. АКЦЕНТЫ', '3. ГОТОВО'];

    return Container(
      color: const Color(0xFF121416),
      padding: const EdgeInsets.fromLTRB(26, 10, 26, 12),
      child: Row(
        children: [
          for (var i = 0; i < labels.length; i++) ...[
            Expanded(
              child: Column(
                children: [
                  Text(
                    labels[i],
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: i == activeIndex
                          ? Colors.white
                          : Colors.white.withValues(alpha: 0.42),
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.1,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Container(
                    height: 2,
                    color: i <= activeIndex
                        ? Colors.white
                        : const Color(0xFF434749),
                  ),
                ],
              ),
            ),
            if (i != labels.length - 1) const SizedBox(width: 10),
          ],
        ],
      ),
    );
  }
}

class _LookBuilderIntro extends StatelessWidget {
  const _LookBuilderIntro();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(26, 32, 26, 30),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Color(0xFF5C6064))),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Сборка образа',
            style: TextStyle(
              color: Colors.white,
              fontSize: 30,
              height: 1.05,
              fontWeight: FontWeight.w600,
            ),
          ),
          SizedBox(height: 14),
          Text(
            'Создайте персонализированный сет для особого случая.',
            style: TextStyle(
              color: Color(0xFFC4C7C8),
              fontSize: 16,
              height: 1.35,
            ),
          ),
        ],
      ),
    );
  }
}

class _CanvasSection extends StatelessWidget {
  final Map<String, dynamic>? baseProduct;
  final List<Map<String, dynamic>> accents;
  final VoidCallback onBaseTap;
  final VoidCallback onAccentTap;

  const _CanvasSection({
    required this.baseProduct,
    required this.accents,
    required this.onBaseTap,
    required this.onAccentTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: const Color(0xFF1A1C1E),
      padding: const EdgeInsets.fromLTRB(26, 28, 26, 34),
      child: Column(
        children: [
          Container(
            width: double.infinity,
            constraints: const BoxConstraints(maxWidth: 620),
            decoration: BoxDecoration(
              color: const Color(0xFF121416),
              border: Border.all(color: const Color(0xFF5C6064)),
            ),
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 20),
            child: Column(
              children: [
                AspectRatio(
                  aspectRatio: 1.28,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      Icon(
                        Icons.checkroom_outlined,
                        size: 74,
                        color: Colors.white.withValues(alpha: 0.08),
                      ),
                      Align(
                        alignment: Alignment.topCenter,
                        child: SizedBox(
                          width: double.infinity,
                          height: double.infinity,
                          child: _CanvasSlot(
                            product: baseProduct,
                            label: baseProduct == null
                                ? 'ДОБАВИТЬ ОСНОВУ'
                                : 'ОСНОВА ВЫБРАНА',
                            large: true,
                            onTap: onBaseTap,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: SizedBox(
                        height: 86,
                        child: _CanvasSlot(
                          product: accents.isEmpty ? null : accents.first,
                          label: accents.isEmpty ? 'АКЦЕНТ' : 'АКЦЕНТ ВЫБРАН',
                          onTap: onAccentTap,
                        ),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: SizedBox(
                        height: 86,
                        child: _CanvasSlot(
                          product: accents.length > 1 ? accents[1] : null,
                          label: baseProduct == null
                              ? 'ПОСЛЕ ОСНОВЫ'
                              : 'АКЦЕНТ',
                          locked: baseProduct == null,
                          onTap: onAccentTap,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          const Text(
            'ВАШ БУДУЩИЙ СЕТ',
            style: TextStyle(
              color: Colors.white,
              fontSize: 14,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.4,
            ),
          ),
        ],
      ),
    );
  }
}

class _CanvasSlot extends StatelessWidget {
  final Map<String, dynamic>? product;
  final String label;
  final bool large;
  final bool locked;
  final VoidCallback onTap;

  const _CanvasSlot({
    required this.product,
    required this.label,
    required this.onTap,
    this.large = false,
    this.locked = false,
  });

  @override
  Widget build(BuildContext context) {
    final imageUrl = product == null ? null : _productImage(product!);
    return InkWell(
      onTap: onTap,
      child: CustomPaint(
        painter: _DashedBorderPainter(
          color: locked ? const Color(0xFF434749) : const Color(0xFF8E9192),
        ),
        child: Padding(
          padding: EdgeInsets.all(large ? 14 : 8),
          child: imageUrl == null
              ? Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      locked ? Icons.lock_outline : Icons.add,
                      color: Colors.white.withValues(
                        alpha: locked ? 0.22 : 0.5,
                      ),
                      size: large ? 30 : 20,
                    ),
                    const SizedBox(height: 10),
                    Text(
                      label,
                      textAlign: TextAlign.center,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: Colors.white.withValues(
                          alpha: locked ? 0.34 : 0.78,
                        ),
                        fontSize: large ? 12 : 10,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 1.1,
                      ),
                    ),
                  ],
                )
              : Stack(
                  fit: StackFit.expand,
                  children: [
                    CachedNetworkImage(
                      imageUrl: imageUrl,
                      fit: BoxFit.cover,
                      color: Colors.black.withValues(alpha: 0.18),
                      colorBlendMode: BlendMode.darken,
                      errorWidget: (_, _, _) => const ColoredBox(
                        color: Color(0xFF1A1C1E),
                        child: Icon(Icons.add, color: Color(0xFF8E9192)),
                      ),
                    ),
                    Align(
                      alignment: Alignment.bottomLeft,
                      child: Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(8),
                        color: Colors.black.withValues(alpha: 0.42),
                        child: Text(
                          label,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}

class _NameSection extends StatelessWidget {
  final TextEditingController controller;
  final String suggestedName;
  final String selectedOccasion;
  final ValueChanged<String> onOccasionChanged;

  const _NameSection({
    required this.controller,
    required this.suggestedName,
    required this.selectedOccasion,
    required this.onOccasionChanged,
  });

  @override
  Widget build(BuildContext context) {
    const occasions = ['Подарок', 'Вечер', 'На каждый день'];
    return _BuilderSectionFrame(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionTitle(title: 'НАЗВАНИЕ ОБРАЗА'),
          const SizedBox(height: 12),
          TextField(
            controller: controller,
            textCapitalization: TextCapitalization.sentences,
            style: const TextStyle(color: Colors.white, fontSize: 15),
            decoration: InputDecoration(
              hintText: suggestedName,
              hintStyle: const TextStyle(color: Color(0xFF8E9192)),
              filled: true,
              fillColor: const Color(0xFF0C0E10),
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 14,
                vertical: 14,
              ),
              enabledBorder: const OutlineInputBorder(
                borderRadius: BorderRadius.zero,
                borderSide: BorderSide(color: Color(0xFF5C6064)),
              ),
              focusedBorder: const OutlineInputBorder(
                borderRadius: BorderRadius.zero,
                borderSide: BorderSide(color: Colors.white),
              ),
            ),
          ),
          const SizedBox(height: 10),
          const Text(
            'Можно оставить пустым — GLAME назовет образ по составу.',
            style: TextStyle(
              color: Color(0xFF8E9192),
              fontSize: 12,
              height: 1.3,
            ),
          ),
          const SizedBox(height: 18),
          const _SectionTitle(title: 'ПОВОД'),
          const SizedBox(height: 14),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (var i = 0; i < occasions.length; i++) ...[
                  _GoalChip(
                    label: occasions[i],
                    selected: selectedOccasion == occasions[i],
                    onTap: () => onOccasionChanged(occasions[i]),
                  ),
                  if (i != occasions.length - 1) const SizedBox(width: 8),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ProductsSection extends StatelessWidget {
  final String title;
  final String counter;
  final List<Map<String, dynamic>> products;
  final Set<String> selectedIds;
  final int maxSelected;
  final bool locked;
  final String? lockedText;
  final bool loading;
  final String? error;
  final ValueChanged<Map<String, dynamic>> onProductTap;
  final VoidCallback onMoreTap;

  const _ProductsSection({
    required this.title,
    required this.counter,
    required this.products,
    required this.selectedIds,
    required this.maxSelected,
    this.locked = false,
    this.lockedText,
    this.loading = false,
    this.error,
    required this.onProductTap,
    required this.onMoreTap,
  });

  @override
  Widget build(BuildContext context) {
    return _BuilderSectionFrame(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: _SectionTitle(title: title)),
              Text(
                counter,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  letterSpacing: 1,
                ),
              ),
            ],
          ),
          if (lockedText != null) ...[
            const SizedBox(height: 22),
            Text(
              lockedText!,
              style: const TextStyle(
                color: Color(0xFFE2E2E5),
                fontSize: 16,
                height: 1.35,
              ),
            ),
          ],
          const SizedBox(height: 18),
          if (loading)
            const SizedBox(
              height: 156,
              child: Center(
                child: CircularProgressIndicator(color: Colors.white),
              ),
            )
          else if (error != null && products.isEmpty)
            _BuilderHint(text: error!)
          else if (locked)
            const Row(
              children: [
                Expanded(child: _LockedProductSlot()),
                SizedBox(width: 14),
                Expanded(child: _LockedProductSlot()),
              ],
            )
          else
            Wrap(
              spacing: 0,
              runSpacing: 0,
              children: [
                for (final product in products.take(3))
                  SizedBox(
                    width: (MediaQuery.of(context).size.width - 52) / 2,
                    child: _BuilderProductTile(
                      product: product,
                      selected: selectedIds.contains(_productId(product)),
                      disabled:
                          selectedIds.length >= maxSelected &&
                          !selectedIds.contains(_productId(product)),
                      onTap: () => onProductTap(product),
                    ),
                  ),
                SizedBox(
                  width: (MediaQuery.of(context).size.width - 52) / 2,
                  child: _MoreTile(onTap: onMoreTap),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

class _BuilderSectionFrame extends StatelessWidget {
  final Widget child;

  const _BuilderSectionFrame({required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(26, 28, 26, 28),
      decoration: const BoxDecoration(
        color: Color(0xFF121416),
        border: Border(top: BorderSide(color: Color(0xFF5C6064))),
      ),
      child: child,
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String title;

  const _SectionTitle({required this.title});

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: const TextStyle(
        color: Colors.white,
        fontSize: 14,
        fontWeight: FontWeight.w800,
        letterSpacing: 1.6,
      ),
    );
  }
}

class _GoalChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _GoalChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        height: 42,
        padding: const EdgeInsets.symmetric(horizontal: 18),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: selected ? Colors.white : Colors.transparent,
          border: Border.all(color: const Color(0xFF8E9192)),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? const Color(0xFF121416) : Colors.white,
            fontSize: 14,
          ),
        ),
      ),
    );
  }
}

class _BuilderProductTile extends StatelessWidget {
  final Map<String, dynamic> product;
  final bool selected;
  final bool disabled;
  final VoidCallback onTap;

  const _BuilderProductTile({
    required this.product,
    required this.selected,
    required this.disabled,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final imageUrl = _productImage(product);
    final name = ((product['name'] as String?) ?? 'Украшение').trim();
    final price = formatRubFromKopeks(product['price']);

    return InkWell(
      onTap: disabled ? null : onTap,
      child: Opacity(
        opacity: disabled ? 0.42 : 1,
        child: Container(
          height: 196,
          decoration: BoxDecoration(
            color: const Color(0xFF121416),
            border: Border.all(
              color: selected ? Colors.white : const Color(0xFF5C6064),
            ),
          ),
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: Container(
                        color: const Color(0xFF0C0E10),
                        child: imageUrl == null
                            ? const Icon(
                                Icons.diamond_outlined,
                                color: Color(0xFF5C6064),
                              )
                            : CachedNetworkImage(
                                imageUrl: imageUrl,
                                fit: BoxFit.cover,
                                color: Colors.black.withValues(alpha: 0.12),
                                colorBlendMode: BlendMode.darken,
                                errorWidget: (_, _, _) => const Icon(
                                  Icons.diamond_outlined,
                                  color: Color(0xFF5C6064),
                                ),
                              ),
                      ),
                    ),
                    if (selected)
                      Positioned(
                        top: 8,
                        right: 8,
                        child: Container(
                          width: 24,
                          height: 24,
                          decoration: const BoxDecoration(
                            color: Colors.white,
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(
                            Icons.check,
                            size: 16,
                            color: Color(0xFF121416),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 10),
              Text(
                name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Colors.white, fontSize: 12),
              ),
              const SizedBox(height: 4),
              Text(
                price,
                maxLines: 1,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MoreTile extends StatelessWidget {
  final VoidCallback onTap;

  const _MoreTile({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: CustomPaint(
        painter: _DashedBorderPainter(color: const Color(0xFF5C6064)),
        child: const SizedBox(
          height: 150,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.search, color: Colors.white, size: 32),
              SizedBox(height: 18),
              Text(
                'Больше вариантов',
                style: TextStyle(color: Colors.white, fontSize: 12),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LockedProductSlot extends StatelessWidget {
  const _LockedProductSlot();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 116,
      decoration: BoxDecoration(
        color: const Color(0xFF121416),
        border: Border.all(color: const Color(0xFF434749)),
      ),
      child: Icon(
        Icons.lock_outline,
        color: Colors.white.withValues(alpha: 0.18),
      ),
    );
  }
}

class _BuilderHint extends StatelessWidget {
  final String text;

  const _BuilderHint({required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        border: Border.all(color: const Color(0xFF5C6064)),
      ),
      child: Text(
        text,
        style: const TextStyle(color: Color(0xFFC4C7C8), fontSize: 14),
      ),
    );
  }
}

class _BuilderSummaryPanel extends StatelessWidget {
  final int totalPrice;
  final bool canSave;
  final String hint;
  final VoidCallback onSave;

  const _BuilderSummaryPanel({
    required this.totalPrice,
    required this.canSave,
    required this.hint,
    required this.onSave,
  });

  @override
  Widget build(BuildContext context) {
    return _BuilderSectionFrame(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'ИТОГОВАЯ СТОИМОСТЬ',
            style: TextStyle(
              color: Color(0xFF8E9192),
              fontSize: 12,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.4,
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: Text(
                  formatRubFromKopeks(totalPrice),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 30,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.2,
                  ),
                ),
              ),
              const Text(
                'СЕРВИСНЫЙ СБОР\nВключен',
                textAlign: TextAlign.right,
                style: TextStyle(
                  color: Color(0xFFC4C7C8),
                  fontSize: 11,
                  height: 1.35,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.9,
                ),
              ),
            ],
          ),
          const SizedBox(height: 22),
          FilledButton(
            onPressed: canSave ? onSave : null,
            style: FilledButton.styleFrom(
              minimumSize: const Size.fromHeight(56),
              backgroundColor: Colors.white,
              disabledBackgroundColor: Colors.white.withValues(alpha: 0.26),
              foregroundColor: const Color(0xFF121416),
              disabledForegroundColor: const Color(
                0xFF121416,
              ).withValues(alpha: 0.45),
              shape: const RoundedRectangleBorder(),
            ),
            child: const Text(
              'СОХРАНИТЬ В МОЙ СТИЛЬ',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.4,
              ),
            ),
          ),
          const SizedBox(height: 16),
          Center(
            child: Text(
              hint,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Color(0xFF8E9192),
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 1,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _LookBuilderBottomBar extends StatelessWidget {
  const _LookBuilderBottomBar();

  @override
  Widget build(BuildContext context) {
    final hasBottomInset = MediaQuery.of(context).padding.bottom > 0;
    final bottomAir = hasBottomInset ? 6.0 : 0.0;

    return DecoratedBox(
      decoration: const BoxDecoration(
        color: GlameColors.surface2,
        border: Border(top: BorderSide(color: GlameColors.borderGray)),
      ),
      child: SizedBox(
        height: GlameUi.mobileBottomNavHeight + bottomAir,
        child: Padding(
          padding: EdgeInsets.only(bottom: bottomAir),
          child: Row(
            children: [
              _BuilderBottomHome(onTap: () => context.go('/home')),
              _BuilderBottomItem(
                label: 'Украшения',
                onTap: () => context.go('/home?tab=1'),
              ),
              _BuilderBottomItem(
                label: 'Мой стиль',
                selected: true,
                onTap: () => context.go('/home?tab=2'),
              ),
              _BuilderBottomItem(
                label: 'Подбор',
                onTap: () => context.go('/home?tab=3'),
              ),
              _BuilderBottomItem(
                label: 'Профиль',
                onTap: () => context.go('/home?tab=4'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BuilderBottomHome extends StatelessWidget {
  final VoidCallback onTap;

  const _BuilderBottomHome({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 64,
      child: InkWell(
        onTap: onTap,
        child: Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: Opacity(
              opacity: 0.64,
              child: Image.asset(GlameAssets.sign, fit: BoxFit.contain),
            ),
          ),
        ),
      ),
    );
  }
}

class _BuilderBottomItem extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _BuilderBottomItem({
    required this.label,
    this.selected = false,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        child: Center(
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 12,
              fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
              color: selected
                  ? GlameColors.textPrimary
                  : GlameColors.textSecondary,
            ),
          ),
        ),
      ),
    );
  }
}

class _DashedBorderPainter extends CustomPainter {
  final Color color;

  const _DashedBorderPainter({this.color = const Color(0xFF8E9192)});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 1
      ..style = PaintingStyle.stroke;
    const dash = 4.0;
    const gap = 3.0;

    void drawDashedLine(Offset start, Offset end) {
      final delta = end - start;
      final distance = delta.distance;
      final direction = delta / distance;
      var current = 0.0;
      while (current < distance) {
        final next = (current + dash).clamp(0.0, distance);
        canvas.drawLine(
          start + direction * current,
          start + direction * next,
          paint,
        );
        current += dash + gap;
      }
    }

    drawDashedLine(Offset.zero, Offset(size.width, 0));
    drawDashedLine(Offset(size.width, 0), Offset(size.width, size.height));
    drawDashedLine(Offset(size.width, size.height), Offset(0, size.height));
    drawDashedLine(Offset(0, size.height), Offset.zero);
  }

  @override
  bool shouldRepaint(covariant _DashedBorderPainter oldDelegate) {
    return oldDelegate.color != color;
  }
}

String _productId(Map<String, dynamic> product) {
  return ((product['id'] as String?) ?? '').trim();
}

String? _productImage(Map<String, dynamic> product) {
  final images = product['images'];
  if (images is List) {
    for (final item in images) {
      final url = item is Map
          ? resolveAssetUrl(item['url'])
          : resolveAssetUrl(item);
      if (url != null && url.isNotEmpty) return url;
    }
  }
  return resolveAssetUrl(product['image_url']) ??
      resolveAssetUrl(product['image']);
}

int _productPriceKopeks(Map<String, dynamic> product) {
  final raw = product['price'];
  if (raw is int) return raw;
  if (raw is num) return raw.toInt();
  if (raw is String) return int.tryParse(raw.trim()) ?? 0;
  return 0;
}

List<Map<String, dynamic>> _productsFromAsync(
  AsyncValue<List<Map<String, dynamic>>> asyncValue,
) {
  return asyncValue.maybeWhen(
    data: (rows) => rows
        .map(_normalizeProductRow)
        .whereType<Map<String, dynamic>>()
        .toList(growable: false),
    orElse: () => const <Map<String, dynamic>>[],
  );
}

List<Map<String, dynamic>> _lookProducts(Map<String, dynamic> look) {
  final raw = look['products'];
  if (raw is! List) return const <Map<String, dynamic>>[];
  return raw
      .map(_normalizeProductRow)
      .whereType<Map<String, dynamic>>()
      .toList(growable: false);
}

Map<String, dynamic>? _normalizeProductRow(dynamic raw) {
  if (raw is! Map) return null;
  final row = Map<String, dynamic>.from(raw);
  final nested = row['product'];
  if (nested is Map) {
    return _normalizeProductRow({
      ...Map<String, dynamic>.from(nested),
      'id': nested['id'] ?? row['product_id'] ?? row['id'],
      'price': nested['price'] ?? row['price'] ?? row['amount'],
    });
  }

  final id = _asText(
    row['product_id'] ?? row['productId'] ?? row['id'] ?? row['sku'],
  );
  if (id == null || id.isEmpty) return null;
  final name =
      _asText(row['product_name'] ?? row['name'] ?? row['title']) ??
      'Украшение GLAME';
  final image = _asText(
    row['image_url'] ??
        row['image'] ??
        row['product_image_url'] ??
        row['photo_url'] ??
        row['thumbnail_url'],
  );
  final images = row['images'] is List
      ? row['images']
      : [
          if (image != null && image.isNotEmpty) {'url': image},
        ];
  return {
    ...row,
    'id': id,
    'name': name,
    'price': row['price'] ?? row['amount'] ?? row['total'] ?? 0,
    'image_url': image,
    'images': images,
  };
}

List<Map<String, dynamic>> _uniqueProducts(
  List<Map<String, dynamic>> products,
) {
  final seen = <String>{};
  final result = <Map<String, dynamic>>[];
  for (final product in products) {
    final id = _productId(product);
    if (id.isEmpty || !seen.add(id)) continue;
    result.add(product);
  }
  return result;
}

Set<String> _productIdSet(List<Map<String, dynamic>> products) {
  return products.map(_productId).where((id) => id.isNotEmpty).toSet();
}

List<Map<String, dynamic>> _rankAccentProducts({
  required Map<String, dynamic> baseProduct,
  required List<Map<String, dynamic>> candidates,
  required Set<String> purchasedIds,
  required Set<String> favoriteIds,
}) {
  final baseId = _productId(baseProduct);
  final unique = _uniqueProducts(
    candidates,
  ).where((product) => _productId(product) != baseId).toList(growable: false);
  final scored = unique
      .map(
        (product) => _ScoredProduct(
          product: product,
          score: _accentScore(
            baseProduct: baseProduct,
            candidate: product,
            purchasedIds: purchasedIds,
            favoriteIds: favoriteIds,
          ),
        ),
      )
      .toList();
  scored.sort((a, b) {
    final byScore = b.score.compareTo(a.score);
    if (byScore != 0) return byScore;
    return (_asText(a.product['name']) ?? '').compareTo(
      _asText(b.product['name']) ?? '',
    );
  });
  return scored.map((item) => item.product).toList(growable: false);
}

double _accentScore({
  required Map<String, dynamic> baseProduct,
  required Map<String, dynamic> candidate,
  required Set<String> purchasedIds,
  required Set<String> favoriteIds,
}) {
  final candidateId = _productId(candidate);
  var score = 0.0;

  if (purchasedIds.contains(candidateId)) score += 28;
  if (favoriteIds.contains(candidateId)) score += 22;

  final baseCategory = _productTrait(baseProduct, const ['category', 'тип']);
  final candidateCategory = _productTrait(candidate, const ['category', 'тип']);
  if (baseCategory != null && candidateCategory != null) {
    if (_categoriesComplement(baseCategory, candidateCategory)) {
      score += 20;
    } else if (_normalizedToken(baseCategory) ==
        _normalizedToken(candidateCategory)) {
      score -= 8;
    } else {
      score += 8;
    }
  }

  score += _traitMatchScore(baseProduct, candidate, const [
    'brand',
    'бренд',
  ], 14);
  score += _traitMatchScore(baseProduct, candidate, const [
    'metal',
    'металл',
    'material',
    'материал',
  ], 18);
  score += _traitMatchScore(baseProduct, candidate, const [
    'color',
    'цвет',
  ], 10);
  score += _traitMatchScore(baseProduct, candidate, const [
    'insert',
    'вставка',
    'stone',
    'камень',
  ], 10);
  score += _traitMatchScore(baseProduct, candidate, const [
    'coating',
    'покрытие',
    'plating',
  ], 8);

  score += _priceAffinityScore(baseProduct, candidate);
  score += _nameTokenAffinityScore(baseProduct, candidate);
  return score;
}

double _traitMatchScore(
  Map<String, dynamic> baseProduct,
  Map<String, dynamic> candidate,
  List<String> keys,
  double weight,
) {
  final baseValue = _productTrait(baseProduct, keys);
  final candidateValue = _productTrait(candidate, keys);
  if (baseValue == null || candidateValue == null) return 0;
  return _normalizedToken(baseValue) == _normalizedToken(candidateValue)
      ? weight
      : 0;
}

double _priceAffinityScore(
  Map<String, dynamic> baseProduct,
  Map<String, dynamic> candidate,
) {
  final basePrice = _productPriceKopeks(baseProduct);
  final candidatePrice = _productPriceKopeks(candidate);
  if (basePrice <= 0 || candidatePrice <= 0) return 0;
  final diffRatio = (basePrice - candidatePrice).abs() / basePrice;
  if (diffRatio <= 0.25) return 12;
  if (diffRatio <= 0.5) return 7;
  if (diffRatio <= 0.85) return 3;
  return 0;
}

double _nameTokenAffinityScore(
  Map<String, dynamic> baseProduct,
  Map<String, dynamic> candidate,
) {
  final baseTokens = _nameTokens(baseProduct);
  if (baseTokens.isEmpty) return 0;
  final candidateTokens = _nameTokens(candidate);
  return baseTokens.intersection(candidateTokens).length.clamp(0, 3) * 2.0;
}

Set<String> _nameTokens(Map<String, dynamic> product) {
  final values = [
    _asText(product['name']),
    _asText(product['brand']),
    _productTrait(product, const ['style', 'стиль']),
  ].whereType<String>().join(' ');
  return values
      .toLowerCase()
      .split(RegExp(r'[^a-zа-яё0-9]+', unicode: true))
      .where((token) => token.length > 3)
      .toSet();
}

String? _productTrait(Map<String, dynamic> product, List<String> keys) {
  for (final key in keys) {
    final value = _asText(product[key]);
    if (value != null) return value;
  }

  final specs = product['specifications'];
  if (specs is Map) {
    for (final entry in specs.entries) {
      final key = _normalizedToken(entry.key);
      if (keys.any((needle) => key.contains(_normalizedToken(needle)))) {
        final value = _asText(entry.value);
        if (value != null) return value;
      }
    }
  }
  return null;
}

bool _categoriesComplement(String baseCategory, String candidateCategory) {
  final base = _categoryKind(baseCategory);
  final candidate = _categoryKind(candidateCategory);
  if (base == null || candidate == null) return false;
  if (base == candidate) return false;
  const complements = <String, Set<String>>{
    'ring': {'earrings', 'neck', 'bracelet'},
    'earrings': {'ring', 'neck', 'bracelet'},
    'neck': {'earrings', 'ring', 'bracelet'},
    'bracelet': {'ring', 'earrings', 'neck'},
    'brooch': {'earrings', 'ring'},
  };
  return complements[base]?.contains(candidate) == true;
}

String? _categoryKind(String value) {
  final token = _normalizedToken(value);
  if (token.contains('кольц') || token.contains('ring')) return 'ring';
  if (token.contains('серь') || token.contains('earring')) return 'earrings';
  if (token.contains('брасл') || token.contains('bracelet')) return 'bracelet';
  if (token.contains('колье') ||
      token.contains('кулон') ||
      token.contains('подвес') ||
      token.contains('neck') ||
      token.contains('pendant')) {
    return 'neck';
  }
  if (token.contains('брош') || token.contains('brooch')) return 'brooch';
  return null;
}

String _normalizedToken(dynamic value) {
  return value
      .toString()
      .trim()
      .toLowerCase()
      .replaceAll('ё', 'е')
      .replaceAll(RegExp(r'\s+'), ' ');
}

String _generatedLookName(List<Map<String, dynamic>> products) {
  if (products.isEmpty) return 'Мой образ GLAME';
  final brands = products
      .map((product) => _productTrait(product, const ['brand', 'бренд']))
      .whereType<String>()
      .where((brand) => brand.trim().isNotEmpty)
      .toSet()
      .take(2)
      .toList(growable: false);
  final categories = products
      .map((product) {
        final raw = _productTrait(product, const ['category', 'тип']);
        return raw == null ? null : _categoryNameLabel(raw);
      })
      .whereType<String>()
      .toSet()
      .take(3)
      .toList(growable: false);

  final prefix = brands.isEmpty ? 'Образ' : brands.join(' + ');
  if (categories.isEmpty) return '$prefix GLAME';
  return '$prefix: ${categories.join(' + ')}';
}

String _categoryNameLabel(String value) {
  switch (_categoryKind(value)) {
    case 'ring':
      return 'кольцо';
    case 'earrings':
      return 'серьги';
    case 'bracelet':
      return 'браслет';
    case 'neck':
      return 'колье';
    case 'brooch':
      return 'брошь';
  }
  final text = value.trim();
  return text.isEmpty ? 'украшение' : text.toLowerCase();
}

class _ScoredProduct {
  final Map<String, dynamic> product;
  final double score;

  const _ScoredProduct({required this.product, required this.score});
}

String? _asText(dynamic value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}
