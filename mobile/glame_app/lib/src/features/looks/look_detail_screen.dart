import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters/rub.dart';
import '../../core/network/asset_url.dart';
import '../../core/analytics/analytics_service.dart';
import '../../core/theme/glame_theme.dart';
import '../auth/auth_controller.dart';
import '../cart/cart_controller.dart';
import '../customer/customer_cabinet_providers.dart';
import '../customer/stylist_entry.dart';
import '../product/product_providers.dart';
import '../wishlist/wishlist_controller.dart';
import 'looks_providers.dart';

class LookDetailScreen extends ConsumerStatefulWidget {
  final String lookId;
  final Map<String, dynamic>? localLook;

  const LookDetailScreen({super.key, required this.lookId, this.localLook});

  @override
  ConsumerState<LookDetailScreen> createState() => _LookDetailScreenState();
}

class _LookDetailScreenState extends ConsumerState<LookDetailScreen> {
  late final PageController _heroController;
  bool _busy = false;
  bool _heroAlignedToPreferred = false;
  int _heroPage = 0;
  String? _selectionInitializedForLookId;
  final Set<String> _selectedProductIds = <String>{};
  final Map<String, Map<String, dynamic>> _selectedVariantsByProductId =
      <String, Map<String, dynamic>>{};
  String? _trackedLookId;

  @override
  void initState() {
    super.initState();
    _heroController = PageController();
  }

  @override
  void dispose() {
    _heroController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final AsyncValue<Map<String, dynamic>> lookAsync = widget.localLook == null
        ? ref.watch(lookByIdProvider(widget.lookId))
        : AsyncValue.data(_normalizeLocalLook(widget.localLook!));
    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      body: lookAsync.when(
        loading: () => const Center(
          child: CircularProgressIndicator(color: GlameColors.gold),
        ),
        error: (_, _) =>
            const Center(child: Text('Не удалось загрузить образ')),
        data: (look) {
          _trackLookViewOnce(look);
          final images = _lookImages(look);
          final preferredPage = _preferredLookImageIndex(look, images.length);
          final products = _products(look);
          final allProductIds = _productIds(products);
          _initializeSelectionIfNeeded(allProductIds);
          _alignHeroToPreferredPageIfNeeded(preferredPage);

          final title = (look['name'] as String?)?.trim();
          final description = _lookDescription(look);
          final style = (look['style'] as String?)?.trim();
          final mood = (look['mood'] as String?)?.trim();
          final totalCount = products.length;
          final selectedProducts = _selectedProducts(products);
          final loyaltyPoints =
              ref.watch(authControllerProvider).user?.loyaltyPoints ?? 0;

          return CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: _LookHeroSection(
                  controller: _heroController,
                  images: images,
                  currentPage: _heroPage.clamp(
                    0,
                    images.isEmpty ? 0 : images.length - 1,
                  ),
                  onPageChanged: (page) => setState(() => _heroPage = page),
                  onSelectPage: _selectHeroPage,
                  title: title?.isNotEmpty == true ? title! : 'Образ',
                  description: description,
                  tag: _heroTag(style, mood),
                  piecesLabel: _piecesLabel(totalCount),
                  isFavorited: look['favorited_by_me'] == true,
                  onBack: () => context.canPop()
                      ? context.pop()
                      : context.go('/home?tab=5'),
                  onToggleFavorite: _busy ? null : () => _toggleFavorite(look),
                  onShare: _shareLook,
                ),
              ),
              SliverToBoxAdapter(
                child: Transform.translate(
                  offset: Offset.zero,
                  child: Column(
                    children: [
                      _LookBodyCard(
                        title: title?.isNotEmpty == true ? title! : 'Образ',
                        description: description,
                        style: style,
                        mood: mood,
                        totalCount: totalCount,
                        products: products,
                        selectedIds: _selectedProductIds,
                        selectedVariants: _selectedVariantsByProductId,
                        onToggleSelected: _toggleProductSelected,
                        onToggleAll: () => _toggleAllProducts(products),
                        onSave: _busy ? null : () => _toggleFavorite(look),
                        onShare: _shareLook,
                        onEdit: look['is_user_created'] == true
                            ? () => context.push('/look-builder', extra: look)
                            : null,
                        isFavorited: look['favorited_by_me'] == true,
                        onVariantChanged: _setSelectedVariant,
                        selectedCount: selectedProducts.length,
                        totalPrice: _discountedPriceKopeks(
                          _totalPrice(selectedProducts),
                          loyaltyPoints,
                        ),
                        loyaltyPoints: loyaltyPoints,
                        busy: _busy,
                        onCollect: () => _addLookBundleToCart(selectedProducts),
                        onTalkToStylist: () => showStylistContactSheet(
                          context,
                          initialMessage:
                              'Хочу обсудить этот образ со стилистом GLAME.',
                          source: 'look_detail',
                          scenario: 'live_stylist',
                        ),
                      ),
                      const SizedBox(height: 96),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  void _initializeSelectionIfNeeded(List<String> productIds) {
    if (_selectionInitializedForLookId == widget.lookId) return;
    _selectionInitializedForLookId = widget.lookId;
    _selectedProductIds
      ..clear()
      ..addAll(productIds);
    _selectedVariantsByProductId.clear();
  }

  void _alignHeroToPreferredPageIfNeeded(int preferredPage) {
    if (_heroAlignedToPreferred) return;
    _heroAlignedToPreferred = true;
    _heroPage = preferredPage;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_heroController.hasClients) return;
      _heroController.jumpToPage(preferredPage);
    });
  }

  void _toggleProductSelected(String productId) {
    if (productId.isEmpty) return;
    setState(() {
      if (_selectedProductIds.contains(productId)) {
        _selectedProductIds.remove(productId);
      } else {
        _selectedProductIds.add(productId);
      }
    });
  }

  void _toggleAllProducts(List<Map<String, dynamic>> products) {
    final productIds = _productIds(products);
    if (productIds.isEmpty) return;
    setState(() {
      final shouldSelectAll = _selectedProductIds.length != productIds.length;
      _selectedProductIds
        ..clear()
        ..addAll(shouldSelectAll ? productIds : const <String>[]);
    });
  }

  void _setSelectedVariant(
    String productId,
    Map<String, dynamic>? selectedVariant,
  ) {
    if (productId.isEmpty) return;
    setState(() {
      if (selectedVariant == null || _productId(selectedVariant) == productId) {
        _selectedVariantsByProductId.remove(productId);
        return;
      }
      _selectedVariantsByProductId[productId] = selectedVariant;
    });
  }

  List<Map<String, dynamic>> _selectedProducts(
    List<Map<String, dynamic>> products,
  ) {
    return products
        .where((product) => _selectedProductIds.contains(_productId(product)))
        .map(_resolveSelectedProduct)
        .toList(growable: false);
  }

  Map<String, dynamic> _resolveSelectedProduct(Map<String, dynamic> product) {
    final productId = _productId(product);
    return _selectedVariantsByProductId[productId] ?? product;
  }

  void _selectHeroPage(int page) {
    if (page < 0) return;
    setState(() => _heroPage = page);
    if (_heroController.hasClients) {
      _heroController.animateToPage(
        page,
        duration: const Duration(milliseconds: 240),
        curve: Curves.easeOutCubic,
      );
    }
  }

  Future<void> _addLookBundleToCart(List<Map<String, dynamic>> products) async {
    final productIds = _productIds(products);
    if (productIds.isEmpty) {
      _showSnack('Выберите хотя бы одно украшение');
      return;
    }

    final auth = ref.read(authControllerProvider);
    if (auth.user == null) {
      if (!mounted) return;
      context.go(
        '/login?next=${Uri.encodeComponent('/look/${widget.lookId}')}',
      );
      return;
    }

    setState(() => _busy = true);
    await ref.read(cartControllerProvider.notifier).addMany(productIds);
    if (!mounted) return;
    final cartState = ref.read(cartControllerProvider);
    if (cartState.error != null) {
      _showSnack(cartState.error!);
      setState(() => _busy = false);
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Образ добавлен в корзину: ${productIds.length} поз.'),
        backgroundColor: GlameColors.textPrimary,
        action: SnackBarAction(
          label: 'ПЕРЕЙТИ',
          textColor: GlameColors.gold,
          onPressed: () => context.go('/home?tab=3'),
        ),
      ),
    );
    setState(() => _busy = false);
  }

  Future<void> _toggleFavorite(Map<String, dynamic> look) async {
    final lookId = (look['id'] as String?)?.trim() ?? '';
    if (lookId.isEmpty) return;

    setState(() => _busy = true);
    try {
      await ref.read(looksApiProvider).toggleFavorite(lookId);
      ref.invalidate(lookByIdProvider(widget.lookId));
      ref.invalidate(looksFeedProvider);
      ref.invalidate(customerSavedLooksProvider);
      ref.invalidate(customerFavoriteLooksProvider);
    } catch (_) {
      _showSnack('Войдите, чтобы сохранять образы');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _trackLookViewOnce(Map<String, dynamic> look) {
    final lookId = (look['id'] as String?)?.trim() ?? widget.lookId;
    if (lookId.isEmpty || _trackedLookId == lookId) return;
    _trackedLookId = lookId;
    unawaited(
      ref
          .read(analyticsServiceProvider)
          .trackLookView(
            lookId,
            data: {
              'name': (look['name'] as String?)?.trim(),
              'style': (look['style'] as String?)?.trim(),
              'mood': (look['mood'] as String?)?.trim(),
            },
          ),
    );
  }

  Future<void> _shareLook() async {
    await Clipboard.setData(
      ClipboardData(
        text: 'https://app.glamejewelry.ru/#/look/${widget.lookId}',
      ),
    );
    _showSnack('Ссылка на образ скопирована');
  }

  void _showSnack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }
}

class _LookHeroSection extends StatelessWidget {
  final PageController controller;
  final List<String> images;
  final int currentPage;
  final ValueChanged<int> onPageChanged;
  final ValueChanged<int> onSelectPage;
  final String title;
  final String description;
  final String? tag;
  final String piecesLabel;
  final bool isFavorited;
  final VoidCallback onBack;
  final VoidCallback? onToggleFavorite;
  final VoidCallback onShare;

  const _LookHeroSection({
    required this.controller,
    required this.images,
    required this.currentPage,
    required this.onPageChanged,
    required this.onSelectPage,
    required this.title,
    required this.description,
    required this.tag,
    required this.piecesLabel,
    required this.isFavorited,
    required this.onBack,
    required this.onToggleFavorite,
    required this.onShare,
  });

  @override
  Widget build(BuildContext context) {
    final heroImages = images.isEmpty ? const [null] : images;

    final heroHeight = (MediaQuery.of(context).size.height * 0.42).clamp(
      330.0,
      470.0,
    );

    return SizedBox(
      height: heroHeight,
      child: Stack(
        fit: StackFit.expand,
        children: [
          PageView.builder(
            controller: controller,
            itemCount: heroImages.length,
            onPageChanged: onPageChanged,
            itemBuilder: (context, index) {
              final imageUrl = heroImages[index];
              if (imageUrl == null) {
                return const ColoredBox(color: GlameColors.nearBlack);
              }
              return CachedNetworkImage(
                imageUrl: imageUrl,
                fit: BoxFit.cover,
                color: Colors.black.withValues(alpha: 0.18),
                colorBlendMode: BlendMode.darken,
                placeholder: (_, _) =>
                    const ColoredBox(color: GlameColors.nearBlack),
                errorWidget: (_, _, _) =>
                    const ColoredBox(color: GlameColors.nearBlack),
              );
            },
          ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    GlameColors.nearBlack.withValues(alpha: 0.48),
                    Colors.transparent,
                    GlameColors.nearBlack.withValues(alpha: 0.78),
                  ],
                ),
              ),
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: 250,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    GlameColors.nearBlack.withValues(alpha: 0),
                    GlameColors.nearBlack.withValues(alpha: 0.34),
                    GlameColors.nearBlack.withValues(alpha: 0.94),
                  ],
                ),
              ),
            ),
          ),
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: SafeArea(
              bottom: false,
              child: Container(
                height: 56,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Row(
                  children: [
                    _OverlayIconButton(icon: Icons.arrow_back, onTap: onBack),
                    const Spacer(),
                    _OverlayIconButton(
                      icon: Icons.ios_share_outlined,
                      onTap: onShare,
                    ),
                  ],
                ),
              ),
            ),
          ),
          Positioned(
            left: 18,
            right: 18,
            bottom: 34,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (tag != null && tag!.isNotEmpty) ...[
                  Text(
                    tag!.toUpperCase(),
                    style: const TextStyle(
                      fontSize: 11,
                      letterSpacing: 1.1,
                      color: GlameColors.textSecondary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 10),
                ],
                Text(
                  title.toUpperCase(),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 28,
                    height: 1.02,
                    color: GlameColors.whiteGlame,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (description.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Text(
                    description,
                    maxLines: 4,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 14,
                      height: 1.42,
                      color: GlameColors.textSecondary,
                    ),
                  ),
                ],
                const SizedBox(height: 18),
                Row(
                  children: [
                    _HeroDots(
                      count: heroImages.length,
                      currentIndex: currentPage,
                    ),
                    const Spacer(),
                    Row(
                      children: [
                        const Icon(
                          Icons.auto_awesome_outlined,
                          size: 14,
                          color: GlameColors.whiteGlame,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          piecesLabel,
                          style: const TextStyle(
                            fontSize: 12,
                            color: GlameColors.whiteGlame,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ],
            ),
          ),
          if (heroImages.length > 1)
            Positioned(
              right: 16,
              top: 118,
              child: _HeroThumbRail(
                images: heroImages,
                currentIndex: currentPage,
                onSelect: onSelectPage,
              ),
            ),
        ],
      ),
    );
  }
}

class _LookBodyCard extends StatelessWidget {
  final String title;
  final String description;
  final String? style;
  final String? mood;
  final int totalCount;
  final List<Map<String, dynamic>> products;
  final Set<String> selectedIds;
  final Map<String, Map<String, dynamic>> selectedVariants;
  final ValueChanged<String> onToggleSelected;
  final VoidCallback onToggleAll;
  final VoidCallback? onSave;
  final VoidCallback onShare;
  final VoidCallback? onEdit;
  final bool isFavorited;
  final void Function(String, Map<String, dynamic>?) onVariantChanged;
  final int selectedCount;
  final int totalPrice;
  final int loyaltyPoints;
  final bool busy;
  final VoidCallback onCollect;
  final VoidCallback onTalkToStylist;

  const _LookBodyCard({
    required this.title,
    required this.description,
    required this.style,
    required this.mood,
    required this.totalCount,
    required this.products,
    required this.selectedIds,
    required this.selectedVariants,
    required this.onToggleSelected,
    required this.onToggleAll,
    required this.onSave,
    required this.onShare,
    this.onEdit,
    required this.isFavorited,
    required this.onVariantChanged,
    required this.selectedCount,
    required this.totalPrice,
    required this.loyaltyPoints,
    required this.busy,
    required this.onCollect,
    required this.onTalkToStylist,
  });

  @override
  Widget build(BuildContext context) {
    return _LookDetailStitchBody(
      totalCount: totalCount,
      products: products,
      selectedIds: selectedIds,
      selectedVariants: selectedVariants,
      onToggleSelected: onToggleSelected,
      onToggleAll: onToggleAll,
      onVariantChanged: onVariantChanged,
      selectedCount: selectedCount,
      totalPrice: totalPrice,
      loyaltyPoints: loyaltyPoints,
      busy: busy,
      onCollect: onCollect,
      onTalkToStylist: onTalkToStylist,
      onEdit: onEdit,
    );
    // ignore: dead_code
    return Container(
      width: double.infinity,
      decoration: const BoxDecoration(color: GlameColors.nearBlack),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _StylistCommentCard(
              title: title,
              description: description,
              style: style,
              mood: mood,
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Text(
                  'Состав образа',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontSize: 18,
                    color: GlameColors.whiteGlame,
                  ),
                ),
                const Spacer(),
                InkWell(
                  onTap: onToggleAll,
                  borderRadius: BorderRadius.circular(10),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 4,
                      vertical: 2,
                    ),
                    child: Row(
                      children: [
                        Text(
                          selectedIds.length == totalCount
                              ? 'Снять выбор'
                              : 'Выбрать все',
                          style: const TextStyle(
                            fontSize: 11,
                            color: GlameColors.textSecondary,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Icon(
                          selectedIds.length == totalCount
                              ? Icons.check_box
                              : Icons.check_box_outline_blank,
                          size: 18,
                          color: GlameColors.whiteGlame,
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (products.isEmpty)
              const Padding(
                padding: EdgeInsets.only(bottom: 16),
                child: Text(
                  'Товары не найдены',
                  style: TextStyle(color: GlameColors.textSecondary),
                ),
              )
            else
              ...products.map((product) {
                final productId = _productId(product);
                final displayProduct = selectedVariants[productId] ?? product;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _LookProductCard(
                    product: displayProduct,
                    selected: selectedIds.contains(productId),
                    onToggleSelected: productId.isEmpty
                        ? null
                        : () => onToggleSelected(productId),
                    onVariantChanged: (variant) =>
                        onVariantChanged(productId, variant),
                  ),
                );
              }),
            const SizedBox(height: 14),
            Row(
              children: [
                InkWell(
                  onTap: onSave,
                  borderRadius: BorderRadius.circular(10),
                  child: Row(
                    children: [
                      Icon(
                        isFavorited ? Icons.favorite : Icons.favorite_border,
                        size: 18,
                        color: GlameColors.textSecondary,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        isFavorited ? 'В избранном' : 'Сохранить образ',
                        style: const TextStyle(
                          fontSize: 13,
                          color: GlameColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                const Spacer(),
                InkWell(
                  onTap: onShare,
                  borderRadius: BorderRadius.circular(10),
                  child: const Row(
                    children: [
                      Text(
                        'Поделиться',
                        style: TextStyle(
                          fontSize: 13,
                          color: GlameColors.textSecondary,
                        ),
                      ),
                      SizedBox(width: 8),
                      Icon(
                        Icons.ios_share_outlined,
                        size: 18,
                        color: GlameColors.textSecondary,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _LookDetailStitchBody extends StatelessWidget {
  final int totalCount;
  final List<Map<String, dynamic>> products;
  final Set<String> selectedIds;
  final Map<String, Map<String, dynamic>> selectedVariants;
  final ValueChanged<String> onToggleSelected;
  final VoidCallback onToggleAll;
  final void Function(String, Map<String, dynamic>?) onVariantChanged;
  final int selectedCount;
  final int totalPrice;
  final int loyaltyPoints;
  final bool busy;
  final VoidCallback onCollect;
  final VoidCallback onTalkToStylist;
  final VoidCallback? onEdit;

  const _LookDetailStitchBody({
    required this.totalCount,
    required this.products,
    required this.selectedIds,
    required this.selectedVariants,
    required this.onToggleSelected,
    required this.onToggleAll,
    required this.onVariantChanged,
    required this.selectedCount,
    required this.totalPrice,
    required this.loyaltyPoints,
    required this.busy,
    required this.onCollect,
    required this.onTalkToStylist,
    this.onEdit,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: GlameColors.nearBlack,
      padding: const EdgeInsets.fromLTRB(16, 26, 16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  'СОСТАВ ОБРАЗА',
                  style: TextStyle(
                    fontSize: 15,
                    height: 1,
                    letterSpacing: 1.3,
                    color: GlameColors.whiteGlame,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              InkWell(
                onTap: onToggleAll,
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Text(
                    selectedIds.length == totalCount ? 'СНЯТЬ' : 'ВСЕ',
                    style: const TextStyle(
                      fontSize: 11,
                      letterSpacing: 1,
                      color: GlameColors.coldLightGray,
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          const Divider(height: 1, color: GlameColors.borderGray),
          const SizedBox(height: 22),
          if (products.isEmpty)
            const Padding(
              padding: EdgeInsets.only(bottom: 24),
              child: Text(
                'Товары не найдены',
                style: TextStyle(color: GlameColors.coldLightGray),
              ),
            )
          else
            ...products.map((product) {
              final productId = _productId(product);
              final displayProduct = selectedVariants[productId] ?? product;
              return Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: _LookDetailProductCard(
                  product: displayProduct,
                  loyaltyPoints: loyaltyPoints,
                  selected: selectedIds.contains(productId),
                  onToggleSelected: productId.isEmpty
                      ? null
                      : () => onToggleSelected(productId),
                  onVariantChanged: (variant) =>
                      onVariantChanged(productId, variant),
                ),
              );
            }),
          const SizedBox(height: 10),
          _LookSummaryPanel(
            selectedCount: selectedCount,
            totalCount: totalCount,
            totalPrice: totalPrice,
            busy: busy,
            onCollect: onCollect,
            onTalkToStylist: onTalkToStylist,
            onEdit: onEdit,
          ),
        ],
      ),
    );
  }
}

class _LookDetailProductCard extends ConsumerWidget {
  final Map<String, dynamic> product;
  final int loyaltyPoints;
  final bool selected;
  final VoidCallback? onToggleSelected;
  final ValueChanged<Map<String, dynamic>?> onVariantChanged;

  const _LookDetailProductCard({
    required this.product,
    required this.loyaltyPoints,
    required this.selected,
    required this.onToggleSelected,
    required this.onVariantChanged,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final id = _productId(product);
    final name = (product['name'] as String?)?.trim() ?? 'Украшение';
    final imageUrl = _productImage(product);
    final category = _cleanText(product['category']) ?? 'Jewelry';
    final price = _priceKopeks(product);
    final isWishlisted =
        id.isNotEmpty && ref.watch(wishlistControllerProvider).contains(id);

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF121416),
        border: Border.all(color: GlameColors.borderGray),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AspectRatio(
            aspectRatio: 1.38,
            child: Stack(
              fit: StackFit.expand,
              children: [
                Container(
                  color: const Color(0xFFEFF1F2),
                  alignment: Alignment.center,
                  child: imageUrl == null
                      ? const Icon(
                          Icons.diamond_outlined,
                          color: GlameColors.borderGray,
                          size: 48,
                        )
                      : CachedNetworkImage(
                          imageUrl: imageUrl,
                          width: double.infinity,
                          height: double.infinity,
                          fit: BoxFit.cover,
                          alignment: Alignment.center,
                          placeholder: (_, _) =>
                              const ColoredBox(color: Color(0xFFEFF1F2)),
                          errorWidget: (_, _, _) => const Icon(
                            Icons.diamond_outlined,
                            color: GlameColors.borderGray,
                            size: 48,
                          ),
                        ),
                ),
                Positioned(
                  top: 10,
                  right: 10,
                  child: _LookProductOverlayIcon(
                    icon: isWishlisted ? Icons.favorite : Icons.favorite_border,
                    onTap: id.isEmpty
                        ? null
                        : () => ref
                              .read(wishlistControllerProvider.notifier)
                              .toggle(id),
                  ),
                ),
                Positioned(
                  left: 10,
                  bottom: 10,
                  child: InkWell(
                    onTap: onToggleSelected,
                    child: Container(
                      width: 28,
                      height: 28,
                      decoration: BoxDecoration(
                        color: GlameColors.nearBlack.withValues(alpha: 0.72),
                        border: Border.all(color: GlameColors.borderGray),
                      ),
                      child: Icon(
                        selected
                            ? Icons.check_box
                            : Icons.check_box_outline_blank,
                        size: 16,
                        color: GlameColors.whiteGlame,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  category.toUpperCase(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 9,
                    letterSpacing: 1.2,
                    color: GlameColors.coldLightGray,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 7),
                Text(
                  name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 15,
                    height: 1.15,
                    color: GlameColors.whiteGlame,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 12),
                if (id.isNotEmpty)
                  _LookProductSizes(
                    productId: id,
                    onVariantChanged: onVariantChanged,
                  ),
                Row(
                  children: [
                    Expanded(
                      child: _LookCompositionPrice(
                        priceKopeks: price,
                        loyaltyPoints: loyaltyPoints,
                      ),
                    ),
                    TextButton(
                      onPressed: id.isEmpty
                          ? null
                          : () => context.push('/product/$id'),
                      style: TextButton.styleFrom(
                        foregroundColor: GlameColors.whiteGlame,
                        padding: EdgeInsets.zero,
                        minimumSize: const Size(58, 36),
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                      child: const Text(
                        'ВЫБРАТЬ',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 1,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _LookCompositionPrice extends StatelessWidget {
  final int priceKopeks;
  final int loyaltyPoints;

  const _LookCompositionPrice({
    required this.priceKopeks,
    required this.loyaltyPoints,
  });

  @override
  Widget build(BuildContext context) {
    final discounted = _discountedPriceKopeks(priceKopeks, loyaltyPoints);
    final hasDiscount = discounted < priceKopeks;
    if (!hasDiscount) {
      return Text(
        formatRubFromKopeks(priceKopeks),
        style: const TextStyle(
          fontSize: 18,
          color: GlameColors.whiteGlame,
          fontWeight: FontWeight.w700,
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          formatRubFromKopeks(priceKopeks),
          style: const TextStyle(
            fontSize: 12,
            color: GlameColors.coldLightGray,
            decoration: TextDecoration.lineThrough,
            decorationColor: GlameColors.coldLightGray,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          formatRubFromKopeks(discounted),
          style: const TextStyle(
            fontSize: 18,
            color: GlameColors.whiteGlame,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }
}

class _LookSummaryPanel extends StatelessWidget {
  final int selectedCount;
  final int totalCount;
  final int totalPrice;
  final bool busy;
  final VoidCallback onCollect;
  final VoidCallback onTalkToStylist;
  final VoidCallback? onEdit;

  const _LookSummaryPanel({
    required this.selectedCount,
    required this.totalCount,
    required this.totalPrice,
    required this.busy,
    required this.onCollect,
    required this.onTalkToStylist,
    this.onEdit,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 18),
      decoration: BoxDecoration(
        color: const Color(0xFF0C0E10),
        border: Border.all(color: GlameColors.borderGray),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'СТОИМОСТЬ ВЫБРАННОГО',
            style: TextStyle(
              fontSize: 10,
              letterSpacing: 1.1,
              color: GlameColors.coldLightGray,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            formatRubFromKopeks(totalPrice),
            style: const TextStyle(
              fontSize: 34,
              height: 1,
              color: GlameColors.whiteGlame,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 10),
          Align(
            alignment: Alignment.centerRight,
            child: Text(
              '$selectedCount из $totalCount изделий выбрано',
              style: const TextStyle(
                fontSize: 11,
                color: GlameColors.coldLightGray,
              ),
            ),
          ),
          const SizedBox(height: 14),
          const Divider(height: 1, color: GlameColors.borderGray),
          const SizedBox(height: 14),
          FilledButton.icon(
            onPressed: busy ? null : onCollect,
            icon: const Icon(Icons.shopping_cart_outlined, size: 17),
            label: const Text('ДОБАВИТЬ ОБРАЗ В КОРЗИНУ'),
            style: FilledButton.styleFrom(
              minimumSize: const Size.fromHeight(46),
              backgroundColor: GlameColors.whiteGlame,
              foregroundColor: GlameColors.nearBlack,
              disabledBackgroundColor: GlameColors.whiteGlame.withValues(
                alpha: 0.38,
              ),
              shape: const RoundedRectangleBorder(),
              textStyle: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.8,
              ),
            ),
          ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: onTalkToStylist,
            icon: const Icon(Icons.chat_bubble_outline, size: 16),
            label: const Text('ОБСУДИТЬ ОБРАЗ СО СТИЛИСТОМ'),
            style: OutlinedButton.styleFrom(
              minimumSize: const Size.fromHeight(46),
              foregroundColor: GlameColors.whiteGlame,
              side: const BorderSide(color: GlameColors.whiteGlame),
              shape: const RoundedRectangleBorder(),
              textStyle: const TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.8,
              ),
            ),
          ),
          if (onEdit != null) ...[
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: onEdit,
              icon: const Icon(Icons.edit_outlined, size: 16),
              label: const Text('РЕДАКТИРОВАТЬ ОБРАЗ'),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(46),
                foregroundColor: GlameColors.whiteGlame,
                side: const BorderSide(color: GlameColors.borderGray),
                shape: const RoundedRectangleBorder(),
                textStyle: const TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.8,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _StylistCommentCard extends StatelessWidget {
  final String title;
  final String description;
  final String? style;
  final String? mood;

  const _StylistCommentCard({
    required this.title,
    required this.description,
    required this.style,
    required this.mood,
  });

  @override
  Widget build(BuildContext context) {
    final comment = _stylistComment(
      title: title,
      description: description,
      style: style,
      mood: mood,
    );

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: GlameColors.nearBlack,
        border: Border.all(color: GlameColors.borderGray),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: GlameColors.nearBlack,
              shape: BoxShape.circle,
              border: Border.all(color: GlameColors.borderGray),
            ),
            alignment: Alignment.center,
            child: const Icon(
              Icons.person_outline,
              size: 18,
              color: GlameColors.whiteGlame,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Комментарий стилиста',
                  style: TextStyle(fontSize: 13, color: GlameColors.whiteGlame),
                ),
                const SizedBox(height: 6),
                Text(
                  comment,
                  style: const TextStyle(
                    fontSize: 12,
                    height: 1.35,
                    color: GlameColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          InkWell(
            onTap: () => showStylistContactSheet(
              context,
              initialMessage: 'Хочу обсудить этот образ со стилистом GLAME.',
              source: 'look_detail',
              scenario: 'live_stylist',
            ),
            borderRadius: BorderRadius.circular(12),
            child: Container(
              width: 118,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: GlameColors.nearBlack,
                border: Border.all(color: GlameColors.borderGray),
              ),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Нужна помощь?',
                    style: TextStyle(
                      fontSize: 11,
                      color: GlameColors.textSecondary,
                    ),
                  ),
                  SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Обсудить со стилистом',
                          style: TextStyle(
                            fontSize: 12,
                            color: GlameColors.whiteGlame,
                          ),
                        ),
                      ),
                      SizedBox(width: 6),
                      Icon(
                        Icons.arrow_forward,
                        size: 16,
                        color: GlameColors.whiteGlame,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _LookProductCard extends ConsumerWidget {
  final Map<String, dynamic> product;
  final bool selected;
  final VoidCallback? onToggleSelected;
  final ValueChanged<Map<String, dynamic>?> onVariantChanged;

  const _LookProductCard({
    required this.product,
    required this.selected,
    required this.onToggleSelected,
    required this.onVariantChanged,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final id = _productId(product);
    final name = (product['name'] as String?)?.trim() ?? 'Украшение';
    final imageUrl = _productImage(product);
    final brandRaw = ((product['brand'] as String?) ?? '').trim();
    final brand = (brandRaw.isEmpty ? 'GLAME' : brandRaw).toUpperCase();
    final price = formatRubFromKopeks(product['price']);
    final stock = (product['stock'] as num?)?.toDouble() ?? 0;
    final subtitle = _lookProductSubtitle(product);
    final isWishlisted = id.isNotEmpty
        ? ref.watch(wishlistControllerProvider).contains(id)
        : false;

    return Container(
      padding: const EdgeInsets.fromLTRB(10, 10, 10, 12),
      decoration: BoxDecoration(
        color: GlameColors.nearBlack,
        border: Border.all(color: GlameColors.borderGray),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: InkWell(
              onTap: onToggleSelected,
              borderRadius: BorderRadius.circular(8),
              child: Icon(
                selected ? Icons.check_box : Icons.check_box_outline_blank,
                size: 20,
                color: selected
                    ? GlameColors.whiteGlame
                    : GlameColors.textSecondary,
              ),
            ),
          ),
          const SizedBox(width: 10),
          SizedBox(
            width: 84,
            height: 84,
            child: Stack(
              fit: StackFit.expand,
              children: [
                imageUrl == null
                    ? const ColoredBox(color: GlameColors.nearBlack)
                    : CachedNetworkImage(
                        imageUrl: imageUrl,
                        fit: BoxFit.cover,
                        errorWidget: (_, _, _) =>
                            const ColoredBox(color: GlameColors.nearBlack),
                      ),
                Positioned(
                  top: 5,
                  left: 5,
                  right: 44,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: GlameColors.nearBlack.withValues(alpha: 0.8),
                      border: Border.all(
                        color: GlameColors.borderGray.withValues(alpha: 0.72),
                      ),
                    ),
                    child: Text(
                      brand,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 8.5,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.4,
                        color: GlameColors.whiteGlame,
                      ),
                    ),
                  ),
                ),
                Positioned(
                  top: 5,
                  right: 5,
                  child: Row(
                    children: [
                      _LookProductOverlayIcon(
                        icon: isWishlisted
                            ? Icons.favorite
                            : Icons.favorite_border,
                        onTap: id.isEmpty
                            ? null
                            : () => ref
                                  .read(wishlistControllerProvider.notifier)
                                  .toggle(id),
                      ),
                      const SizedBox(width: 3),
                      _LookProductOverlayIcon(
                        icon: Icons.ios_share_outlined,
                        onTap: id.isEmpty
                            ? null
                            : () async {
                                await Clipboard.setData(
                                  ClipboardData(
                                    text:
                                        'https://app.glamejewelry.ru/#/product/$id',
                                  ),
                                );
                                if (!context.mounted) return;
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text(
                                      'Ссылка на товар скопирована',
                                    ),
                                  ),
                                );
                              },
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 14,
                    height: 1.15,
                    color: GlameColors.whiteGlame,
                  ),
                ),
                if (subtitle.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    subtitle,
                    style: const TextStyle(
                      fontSize: 11,
                      color: GlameColors.textSecondary,
                    ),
                  ),
                ],
                const SizedBox(height: 8),
                Text(
                  price,
                  style: const TextStyle(
                    fontSize: 18,
                    color: GlameColors.whiteGlame,
                  ),
                ),
                const SizedBox(height: 8),
                if (id.isNotEmpty)
                  _LookProductSizes(
                    productId: id,
                    onVariantChanged: onVariantChanged,
                  ),
                const SizedBox(height: 8),
                Text(
                  stock > 0 ? 'В наличии' : 'Нет в наличии',
                  style: TextStyle(
                    fontSize: 12,
                    color: stock > 0 ? GlameColors.gold : GlameColors.graphite,
                  ),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Доставка 1-2 дня',
                  style: TextStyle(
                    fontSize: 11,
                    color: GlameColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              const SizedBox(height: 28),
              OutlinedButton(
                onPressed: id.isEmpty
                    ? null
                    : () => context.push('/product/$id'),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size(118, 36),
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  foregroundColor: GlameColors.whiteGlame,
                  side: const BorderSide(color: GlameColors.borderGray),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text('Смотреть изделие', style: TextStyle(fontSize: 12)),
                    SizedBox(width: 8),
                    Icon(Icons.arrow_forward, size: 15),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _LookProductOverlayIcon extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onTap;

  const _LookProductOverlayIcon({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        width: 18,
        height: 18,
        decoration: BoxDecoration(
          color: GlameColors.nearBlack.withValues(alpha: 0.8),
          border: Border.all(color: GlameColors.borderGray),
        ),
        alignment: Alignment.center,
        child: Icon(icon, size: 10.5, color: GlameColors.whiteGlame),
      ),
    );
  }
}

class _LookProductSizes extends ConsumerWidget {
  final String productId;
  final ValueChanged<Map<String, dynamic>?> onVariantChanged;

  const _LookProductSizes({
    required this.productId,
    required this.onVariantChanged,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final variantsAsync = ref.watch(productVariantsProvider(productId));
    return variantsAsync.when(
      data: (data) {
        final variants = _variantMaps(data['variants']);
        if (variants.isEmpty) return const SizedBox.shrink();
        final current = variants.firstWhere(
          (variant) => (variant['id'] as String?) == productId,
          orElse: () => variants.first,
        );
        final sizes = _uniqueVariantValues(
          variants,
          (variant) => _variantSpec(variant, 'Размер'),
        );
        final currentSize = _variantSpec(current, 'Размер');
        if (sizes.isEmpty) return const SizedBox.shrink();

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Размер',
              style: TextStyle(fontSize: 10, color: GlameColors.textSecondary),
            ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: sizes
                  .take(5)
                  .map((size) {
                    final selected = size == currentSize;
                    final variantForSize = variants.firstWhere(
                      (variant) => _variantSpec(variant, 'Размер') == size,
                      orElse: () => current,
                    );
                    return Container(
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: InkWell(
                        onTap: () => onVariantChanged(
                          _productId(variantForSize) == productId
                              ? null
                              : variantForSize,
                        ),
                        borderRadius: BorderRadius.circular(8),
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 10,
                            vertical: 6,
                          ),
                          decoration: BoxDecoration(
                            color: selected
                                ? GlameColors.textPrimary
                                : GlameColors.surface,
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: GlameColors.lightGray),
                          ),
                          child: Text(
                            size,
                            style: TextStyle(
                              fontSize: 11,
                              color: selected
                                  ? GlameColors.black
                                  : GlameColors.textPrimary,
                            ),
                          ),
                        ),
                      ),
                    );
                  })
                  .toList(growable: false),
            ),
          ],
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
    );
  }
}

// Kept as a fallback while the look detail screen is being migrated to the
// Stitch in-page summary panel.
// ignore: unused_element
class _LookBottomBar extends StatelessWidget {
  final int selectedCount;
  final int totalCount;
  final int totalPrice;
  final bool busy;
  final bool isFavorited;
  final VoidCallback onCollect;
  final VoidCallback? onToggleFavorite;

  const _LookBottomBar({
    required this.selectedCount,
    required this.totalCount,
    required this.totalPrice,
    required this.busy,
    required this.isFavorited,
    required this.onCollect,
    required this.onToggleFavorite,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
        decoration: BoxDecoration(
          color: GlameColors.nearBlack,
          border: const Border(top: BorderSide(color: GlameColors.borderGray)),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.24),
              blurRadius: 14,
              offset: const Offset(0, -4),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '$selectedCount из $totalCount изделий выбрано',
                        style: const TextStyle(
                          fontSize: 12,
                          color: GlameColors.textSecondary,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        formatRubFromKopeks(totalPrice),
                        style: const TextStyle(
                          fontSize: 32,
                          height: 0.95,
                          color: GlameColors.whiteGlame,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  flex: 2,
                  child: FilledButton(
                    onPressed: busy ? null : onCollect,
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(52),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.zero,
                      ),
                    ),
                    child: const Text('Собрать образ'),
                  ),
                ),
                const SizedBox(width: 10),
                InkWell(
                  onTap: onToggleFavorite,
                  borderRadius: BorderRadius.circular(12),
                  child: Container(
                    width: 48,
                    height: 52,
                    decoration: BoxDecoration(
                      color: GlameColors.surface,
                      border: Border.all(color: GlameColors.borderGray),
                    ),
                    child: Icon(
                      isFavorited ? Icons.bookmark : Icons.bookmark_border,
                      size: 22,
                      color: GlameColors.nearBlack,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            const Align(
              alignment: Alignment.centerRight,
              child: Text(
                'В выбранных размерах. Доставка 1-2 дня',
                style: TextStyle(
                  fontSize: 10,
                  color: GlameColors.textSecondary,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HeroThumbRail extends StatelessWidget {
  final List<String?> images;
  final int currentIndex;
  final ValueChanged<int> onSelect;

  const _HeroThumbRail({
    required this.images,
    required this.currentIndex,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 6),
      decoration: BoxDecoration(
        color: GlameColors.surface2.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        children: List.generate(images.length.clamp(0, 4), (index) {
          final imageUrl = images[index];
          final selected = index == currentIndex;
          return Padding(
            padding: EdgeInsets.only(
              bottom: index == images.length - 1 ? 0 : 8,
            ),
            child: InkWell(
              onTap: () => onSelect(index),
              borderRadius: BorderRadius.circular(10),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                width: selected ? 50 : 42,
                height: selected ? 68 : 58,
                padding: const EdgeInsets.all(2),
                decoration: BoxDecoration(
                  color: GlameColors.surface2.withValues(
                    alpha: selected ? 0.96 : 0.82,
                  ),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: selected
                        ? GlameColors.textPrimary
                        : GlameColors.surface2.withValues(alpha: 0.22),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: GlameColors.textPrimary.withValues(
                        alpha: selected ? 0.08 : 0.03,
                      ),
                      blurRadius: selected ? 10 : 6,
                      offset: const Offset(0, 3),
                    ),
                  ],
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(10),
                  child: imageUrl == null
                      ? const ColoredBox(color: GlameColors.surface)
                      : CachedNetworkImage(
                          imageUrl: imageUrl,
                          fit: BoxFit.cover,
                          errorWidget: (_, _, _) =>
                              const ColoredBox(color: GlameColors.surface),
                        ),
                ),
              ),
            ),
          );
        }),
      ),
    );
  }
}

class _HeroDots extends StatelessWidget {
  final int count;
  final int currentIndex;

  const _HeroDots({required this.count, required this.currentIndex});

  @override
  Widget build(BuildContext context) {
    if (count <= 1) return const SizedBox.shrink();
    return Row(
      children: List.generate(count, (index) {
        final selected = index == currentIndex;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          margin: const EdgeInsets.only(right: 6),
          width: selected ? 10 : 6,
          height: selected ? 10 : 6,
          decoration: BoxDecoration(
            color: selected
                ? GlameColors.surface2
                : GlameColors.surface2.withValues(alpha: 0.55),
            borderRadius: BorderRadius.circular(999),
          ),
        );
      }),
    );
  }
}

class _OverlayIconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onTap;

  const _OverlayIconButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(999),
      child: Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(
          color: GlameColors.nearBlack.withValues(alpha: 0.24),
          borderRadius: BorderRadius.circular(999),
          border: Border.all(
            color: GlameColors.whiteGlame.withValues(alpha: 0.34),
          ),
        ),
        child: Icon(icon, size: 18, color: GlameColors.whiteGlame),
      ),
    );
  }
}

List<String> _lookImages(Map<String, dynamic> look) {
  final result = <String>[];
  final seen = <String>{};

  void add(dynamic raw) {
    final url = _resolveLookImageItem(raw);
    if (url == null || url.isEmpty) return;
    if (seen.add(url)) result.add(url);
  }

  final imageUrls = look['image_urls'];
  if (imageUrls is List) {
    for (final item in imageUrls) {
      add(item);
    }
  }

  final mediaItems = look['media_items'];
  if (mediaItems is List) {
    for (final item in mediaItems) {
      add(item);
    }
  }

  add(look['image_url']);
  return result;
}

int _preferredLookImageIndex(Map<String, dynamic> look, int imagesCount) {
  if (imagesCount <= 1) return 0;
  final preferred = _asNullableInt(look['current_image_index']) ?? 0;
  if (preferred < 0) return 0;
  if (preferred >= imagesCount) return imagesCount - 1;
  return preferred;
}

List<Map<String, dynamic>> _products(Map<String, dynamic> look) {
  final raw = look['products'];
  if (raw is! List) return const <Map<String, dynamic>>[];
  return raw.whereType<Map>().map((x) => Map<String, dynamic>.from(x)).toList();
}

Map<String, dynamic> _normalizeLocalLook(Map<String, dynamic> look) {
  final products = _products(look)
      .map((product) {
        final imageUrl = resolveAssetUrl(product['image_url']);
        return {
          ...product,
          'images': product['images'] is List
              ? product['images']
              : [
                  if (imageUrl != null) {'url': imageUrl},
                ],
        };
      })
      .toList(growable: false);
  final cover =
      resolveAssetUrl(look['image_url']) ??
      resolveAssetUrl(look['look_image_url']) ??
      (products.isEmpty ? null : _productImage(products.first));
  return {
    ...look,
    'id': _cleanText(look['id']) ?? _cleanText(look['look_id']) ?? '',
    'name':
        _cleanText(look['name']) ?? _cleanText(look['look_name']) ?? 'Образ',
    'style': _cleanText(look['style']) ?? _cleanText(look['look_style']),
    'mood': _cleanText(look['mood']) ?? _cleanText(look['look_mood']),
    'description':
        _cleanText(look['description']) ?? _cleanText(look['look_description']),
    'image_url': cover,
    'image_urls': [?cover],
    'products': products,
    'is_user_created': true,
  };
}

List<String> _productIds(List<Map<String, dynamic>> products) {
  return products
      .map(_productId)
      .where((id) => id.isNotEmpty)
      .toList(growable: false);
}

String _productId(Map<String, dynamic> product) {
  return (product['id'] as String?)?.trim() ?? '';
}

int _totalPrice(List<Map<String, dynamic>> products) {
  return products.fold<int>(0, (sum, product) => sum + _priceKopeks(product));
}

int _priceKopeks(Map<String, dynamic> product) {
  final raw = product['price'];
  if (raw is int) return raw;
  if (raw is num) return raw.toInt();
  if (raw is String) return int.tryParse(raw) ?? 0;
  return 0;
}

int _discountedPriceKopeks(int basePriceKopeks, int loyaltyPoints) {
  if (basePriceKopeks <= 0 || loyaltyPoints <= 0) return basePriceKopeks;
  final maxDiscountByRule = (basePriceKopeks * 0.1).round();
  final availableByPoints = loyaltyPoints * 100;
  final discount = maxDiscountByRule < availableByPoints
      ? maxDiscountByRule
      : availableByPoints;
  return (basePriceKopeks - discount).clamp(0, basePriceKopeks).toInt();
}

String _lookDescription(Map<String, dynamic> look) {
  final description = (look['description'] as String?)?.trim();
  if (description != null && description.isNotEmpty) return description;
  final caption = (look['caption'] as String?)?.trim();
  if (caption != null && caption.isNotEmpty) return caption;
  return '';
}

String? _heroTag(String? style, String? mood) {
  final primary = style?.trim();
  if (primary != null && primary.isNotEmpty) return primary.toUpperCase();
  final secondary = mood?.trim();
  if (secondary != null && secondary.isNotEmpty) {
    return secondary.toUpperCase();
  }
  return null;
}

String _stylistComment({
  required String title,
  required String description,
  required String? style,
  required String? mood,
}) {
  final fragments = <String>[
    if (description.isNotEmpty) description,
    if (style != null && style.trim().isNotEmpty)
      'Образ в стиле ${style.trim().toLowerCase()}.',
    if (mood != null && mood.trim().isNotEmpty)
      'Настроение: ${mood.trim().toLowerCase()}.',
  ];

  if (fragments.isEmpty) {
    return 'Этот образ собран так, чтобы выглядеть цельно и легко адаптироваться под Ваш день: от спокойного выхода до более акцентной подачи.';
  }

  final text = fragments.join(' ');
  return text.length > 180 ? '${text.substring(0, 177)}...' : text;
}

String _lookProductSubtitle(Map<String, dynamic> product) {
  final specifications = product['specifications'];
  if (specifications is Map) {
    final material = _cleanText(specifications['Металл']);
    final category = _cleanText(product['category']);
    final composition = <String?>[
      material,
      category?.toLowerCase(),
    ].whereType<String>().toList(growable: false);
    if (composition.isNotEmpty) return composition.join(', ');
  }

  return _cleanText(product['article']) ?? '';
}

String? _productImage(Map<String, dynamic> product) {
  final raw = product['images'];
  if (raw is List) {
    for (final item in raw) {
      final url = item is Map
          ? resolveAssetUrl(item['url'])
          : resolveAssetUrl(item);
      if (url != null && url.isNotEmpty) return url;
    }
  }
  return resolveAssetUrl(product['image_url']) ??
      resolveAssetUrl(product['image']);
}

String _piecesLabel(int count) {
  if (count == 1) return '1 изделие в образе';
  if (count >= 2 && count <= 4) return '$count изделия в образе';
  return '$count изделий в образе';
}

int? _asNullableInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}

String? _resolveLookImageItem(dynamic item) {
  if (item is Map) {
    return resolveAssetUrl(item['url']) ??
        resolveAssetUrl(item['thumbnail_url']) ??
        resolveAssetUrl(item['image_url']);
  }
  return resolveAssetUrl(item);
}

List<Map<String, dynamic>> _variantMaps(dynamic raw) {
  if (raw is! List) return const <Map<String, dynamic>>[];
  return raw
      .whereType<Map>()
      .map((x) => Map<String, dynamic>.from(x))
      .where((x) => (x['id'] as String?)?.isNotEmpty == true)
      .toList(growable: false);
}

String? _variantSpec(Map<String, dynamic> item, String key) {
  final specs = item['specifications'];
  if (specs is! Map) return null;
  final value = specs[key];
  return _cleanText(value);
}

List<String> _uniqueVariantValues(
  List<Map<String, dynamic>> variants,
  String? Function(Map<String, dynamic>) pick,
) {
  final result = <String>[];
  final seen = <String>{};

  for (final variant in variants) {
    final value = pick(variant);
    if (value == null) continue;
    final key = value.toLowerCase();
    if (seen.add(key)) result.add(value);
  }

  result.sort((a, b) => _naturalKey(a).compareTo(_naturalKey(b)));
  return result;
}

String _naturalKey(String value) {
  final parsed = num.tryParse(value.replaceAll(',', '.'));
  if (parsed != null) return parsed.toString().padLeft(8, '0');
  return value.toLowerCase();
}

String? _cleanText(dynamic value) {
  final text = '$value'.trim();
  return text.isEmpty || text == 'null' ? null : text;
}
