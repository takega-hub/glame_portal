import 'dart:convert';
import 'dart:math' as math;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/network/asset_url.dart';
import '../../core/analytics/analytics_service.dart';
import '../../core/formatters/rub.dart';
import '../../core/theme/glame_theme.dart';
import 'product_providers.dart';
import '../auth/auth_controller.dart';
import '../customer/stylist_entry.dart';
import '../wishlist/wishlist_controller.dart';
import '../cart/cart_controller.dart';

class ProductScreen extends ConsumerStatefulWidget {
  final String productId;

  const ProductScreen({super.key, required this.productId});

  @override
  ConsumerState<ProductScreen> createState() => _ProductScreenState();
}

class _ProductScreenState extends ConsumerState<ProductScreen> {
  static const _recentlyViewedKey = 'glame_recently_viewed_products';
  final pageController = PageController();
  final lookController = PageController();
  int page = 0;
  int lookPage = 0;
  List<Map<String, dynamic>> _recentlyViewed = const [];
  String? _lastTrackedProductId;

  @override
  void initState() {
    super.initState();
    _loadRecentlyViewed();
  }

  @override
  void didUpdateWidget(covariant ProductScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.productId != widget.productId) {
      setState(() => page = 0);
      _lastTrackedProductId = null;
      if (pageController.hasClients) {
        pageController.jumpToPage(0);
      }
    }
  }

  @override
  void dispose() {
    pageController.dispose();
    lookController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(productProvider(widget.productId));
    final variantsAsync = ref.watch(productVariantsProvider(widget.productId));
    final looksAsync = ref.watch(productLooksProvider(widget.productId));
    final recommendationsAsync = ref.watch(
      productRecommendationsProvider(widget.productId),
    );
    final variantsData = variantsAsync.maybeWhen(
      data: (x) => x,
      orElse: () => null,
    );

    return Scaffold(
      backgroundColor: GlameColors.surface2,
      appBar: GlameTopAppBar(
        leadingIcon: Icons.arrow_back,
        leadingTooltip: 'Назад',
        onMenuPressed: () {
          if (context.canPop()) {
            context.pop();
          } else {
            context.go('/home?tab=1');
          }
        },
      ),
      body: async.when(
        loading: () => const Center(
          child: CircularProgressIndicator(color: GlameColors.gold),
        ),
        error: (error, stackTrace) => _ErrorState(
          onRetry: () {
            ref.invalidate(productProvider(widget.productId));
            ref.invalidate(productVariantsProvider(widget.productId));
          },
        ),
        data: (item) {
          final name = (item['name'] as String?) ?? '';
          final basePrice = item['price'];
          final article = (item['article'] as String?)?.trim();
          final imagesRaw = item['images'];
          var images = (imagesRaw is List)
              ? imagesRaw.map(resolveAssetUrl).whereType<String>().toList()
              : <String>[];
          final baseForMedia = variantsData?['base'];
          if (images.isEmpty && baseForMedia is Map) {
            final baseImagesRaw = baseForMedia['images'];
            images = (baseImagesRaw is List)
                ? baseImagesRaw
                      .map(resolveAssetUrl)
                      .whereType<String>()
                      .toList()
                : <String>[];
          }
          final ownDescription = _stripHtml(
            (item['description'] as String?) ??
                (item['full_description'] as String?) ??
                '',
          );
          final baseDescription = baseForMedia is Map
              ? _stripHtml(
                  (baseForMedia['description'] as String?) ??
                      (baseForMedia['full_description'] as String?) ??
                      '',
                )
              : '';
          final productDescription = ownDescription.isNotEmpty
              ? ownDescription
              : baseDescription;
          final specs = item['specifications'];
          final stock = item['stock'];
          final loyaltyPoints =
              ref.watch(authControllerProvider).user?.loyaltyPoints ?? 0;
          final isWishlisted = ref
              .watch(wishlistControllerProvider)
              .contains(widget.productId);
          final brandRaw = (item['brand'] as String?)?.trim() ?? '';
          final productBrand = brandRaw.isEmpty
              ? 'GLAME'
              : brandRaw.toUpperCase();

          final isVariant =
              specs is Map &&
              (specs['parent_external_id'] as String?)?.isNotEmpty == true;

          final canonicalVariantId = _firstVariantId(variantsData);
          if (!isVariant &&
              canonicalVariantId != null &&
              canonicalVariantId != widget.productId) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (!mounted) return;
              context.pushReplacement('/product/$canonicalVariantId');
            });
            return const Center(
              child: CircularProgressIndicator(color: GlameColors.gold),
            );
          }

          final prices = <int>[];
          if (basePrice is num && basePrice > 0) prices.add(basePrice.toInt());
          if (!isVariant) {
            final variantsRaw = variantsData?['variants'];
            if (variantsRaw is List) {
              for (final v in variantsRaw) {
                if (v is Map) {
                  final p = v['price'];
                  if (p is num && p > 0) prices.add(p.toInt());
                }
              }
            }
          }

          String priceLabel;
          if (isVariant) {
            priceLabel = formatRubFromKopeks(basePrice);
          } else if (prices.isEmpty) {
            priceLabel = '—';
          } else {
            prices.sort();
            final min = prices.first;
            final max = prices.last;
            priceLabel = (min == max)
                ? formatRubFromKopeks(min)
                : '${formatRubFromKopeks(min)} — ${formatRubFromKopeks(max)}';
          }

          _trackRecentlyViewed(item, images, priceLabel);

          return Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 720),
              child: _buildProductScroll(
                context,
                name: name,
                productBrand: productBrand,
                article: article,
                priceLabel: priceLabel,
                basePriceKopeks: basePrice is num ? basePrice.toInt() : null,
                loyaltyPoints: loyaltyPoints,
                images: images,
                productDescription: productDescription,
                stock: stock,
                isWishlisted: isWishlisted,
                looksAsync: looksAsync,
                recommendationsAsync: recommendationsAsync,
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildProductScroll(
    BuildContext context, {
    required String name,
    required String productBrand,
    required String? article,
    required String priceLabel,
    required int? basePriceKopeks,
    required int loyaltyPoints,
    required List<String> images,
    required String productDescription,
    required num? stock,
    required bool isWishlisted,
    required AsyncValue<List<dynamic>> looksAsync,
    required AsyncValue<List<dynamic>> recommendationsAsync,
  }) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(12, 6, 12, 28),
      children: [
        _buildImageGallery(
          context,
          images,
          brand: productBrand,
          isWishlisted: isWishlisted,
        ),
        const SizedBox(height: 14),
        _buildTopInfoBlock(
          context,
          name: name,
          article: article,
          priceLabel: priceLabel,
          basePriceKopeks: basePriceKopeks,
          loyaltyPoints: loyaltyPoints,
          stock: stock,
        ),
        const SizedBox(height: 14),
        _buildActionButtons(context, stock, isWishlisted),
        const SizedBox(height: 14),
        _buildBenefitsBlock(),
        const SizedBox(height: 12),
        _buildStylistBlock(name, priceLabel, images, productDescription),
        const SizedBox(height: 14),
        _buildLookSetBlock(looksAsync, loyaltyPoints: loyaltyPoints),
        const SizedBox(height: 16),
        _buildDetailsBlock(),
        const SizedBox(height: 16),
        _buildPackagingBlock(images),
        const SizedBox(height: 16),
        _buildSimilarBlock(recommendationsAsync),
        const SizedBox(height: 16),
        _buildRecentlyViewedBlock(images),
      ],
    );
  }

  Widget _buildRecentlyViewedBlock(List<String> fallbackImages) {
    final preview = fallbackImages.isNotEmpty ? fallbackImages.first : null;
    final seen = <String>{};
    final items = _recentlyViewed
        .where((x) => (x['id'] as String?) != widget.productId)
        .where((x) => seen.add((x['id'] as String?) ?? ''))
        .toList();
    if (items.isEmpty) return const SizedBox.shrink();

    return _ProductSection(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _BlockTitle('НЕДАВНО ПРОСМОТРЕННЫЕ'),
          const SizedBox(height: 8),
          SizedBox(
            height: 224,
            child: ListView.builder(
              scrollDirection: Axis.horizontal,
              itemBuilder: (context, index) {
                final item = items[index % items.length];
                return Padding(
                  padding: const EdgeInsets.only(right: 10),
                  child: SizedBox(
                    width: 148,
                    child: GestureDetector(
                      onTap: () {
                        final productId = _extractProductId(item);
                        if (productId != null) {
                          context.push(
                            '/product/${Uri.encodeComponent(productId)}',
                          );
                        }
                      },
                      child: _SimilarTile(
                        imageUrl: _productImageUrl(item) ?? preview,
                        title: (item['name'] as String?) ?? 'GLAME',
                        price: formatRubFromKopeks(item['price']),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _loadRecentlyViewed() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_recentlyViewedKey) ?? const <String>[];
    final parsed = <Map<String, dynamic>>[];
    final seen = <String>{};
    for (final row in raw) {
      try {
        final decoded = jsonDecode(row);
        if (decoded is Map) {
          final item = Map<String, dynamic>.from(decoded);
          final id = item['id'];
          if (id is String && id.isNotEmpty && seen.add(id)) parsed.add(item);
        }
      } catch (_) {}
    }
    if (!mounted) return;
    setState(() => _recentlyViewed = parsed);
  }

  Future<void> _trackRecentlyViewed(
    Map<String, dynamic> item,
    List<String> images,
    String priceLabel,
  ) async {
    final id = (item['id'] as String?)?.trim();
    if (id == null || id.isEmpty) return;
    if (_lastTrackedProductId == id) return;
    _lastTrackedProductId = id;
    await ref
        .read(analyticsServiceProvider)
        .trackProductView(
          id,
          data: {
            'name': (item['name'] as String?) ?? '',
            'price_label': priceLabel,
          },
        );

    final price = item['price'];
    final parsedPrice = price is num ? price.toInt() : null;
    final entry = <String, dynamic>{
      'id': id,
      'name': (item['name'] as String?) ?? '',
      'price': parsedPrice,
      'images': images,
      'price_label': priceLabel,
    };

    final next = <Map<String, dynamic>>[
      entry,
      ..._recentlyViewed.where((x) => (x['id'] as String?) != id),
    ].take(16).toList();

    if (mounted) {
      setState(() => _recentlyViewed = next);
    }

    final prefs = await SharedPreferences.getInstance();
    final encoded = next.map((x) => jsonEncode(x)).toList();
    await prefs.setStringList(_recentlyViewedKey, encoded);
  }

  Widget _buildImageGallery(
    BuildContext context,
    List<String> images, {
    required String brand,
    required bool isWishlisted,
  }) {
    if (images.isEmpty) return _NoImage();

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 46,
          child: Column(
            children: [
              ...List.generate(images.length > 5 ? 5 : images.length, (i) {
                final active = i == page;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: InkWell(
                    onTap: () {
                      pageController.animateToPage(
                        i,
                        duration: const Duration(milliseconds: 220),
                        curve: Curves.easeOut,
                      );
                    },
                    borderRadius: BorderRadius.circular(2),
                    child: Container(
                      width: 38,
                      height: 38,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(2),
                        border: Border.all(
                          color: active
                              ? GlameColors.textPrimary
                              : GlameColors.lightGray,
                        ),
                      ),
                      clipBehavior: Clip.antiAlias,
                      child: CachedNetworkImage(
                        imageUrl: images[i],
                        fit: BoxFit.cover,
                        placeholder: (_, _) =>
                            Container(color: GlameColors.surface),
                        errorWidget: (_, _, _) =>
                            Container(color: GlameColors.surface),
                      ),
                    ),
                  ),
                );
              }),
              if (images.length > 5)
                Container(
                  width: 38,
                  height: 38,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: GlameColors.surface,
                    borderRadius: BorderRadius.circular(2),
                    border: Border.all(color: GlameColors.lightGray),
                  ),
                  child: Text(
                    '+${images.length - 5}',
                    style: const TextStyle(
                      fontSize: 11,
                      color: GlameColors.textSecondary,
                    ),
                  ),
                ),
              const SizedBox(height: 6),
              Text(
                '${(page + 1).toString().padLeft(2, '0')} / ${images.length.toString().padLeft(2, '0')}',
                style: const TextStyle(
                  fontSize: 10,
                  color: GlameColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: AspectRatio(
            aspectRatio: 1,
            child: Stack(
              fit: StackFit.expand,
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(2),
                  child: PageView.builder(
                    controller: pageController,
                    onPageChanged: (v) => setState(() => page = v),
                    itemCount: images.length,
                    itemBuilder: (context, i) {
                      return CachedNetworkImage(
                        imageUrl: images[i],
                        fit: BoxFit.cover,
                        placeholder: (_, _) =>
                            Container(color: GlameColors.surface),
                        errorWidget: (_, _, _) =>
                            Container(color: GlameColors.surface),
                      );
                    },
                  ),
                ),
                Positioned(
                  top: 10,
                  left: 10,
                  child: Container(
                    constraints: const BoxConstraints(maxWidth: 168),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: GlameColors.surface2.withValues(alpha: 0.82),
                      border: Border.all(
                        color: GlameColors.surface2.withValues(alpha: 0.42),
                      ),
                    ),
                    child: Text(
                      brand,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.45,
                        color: GlameColors.textPrimary,
                      ),
                    ),
                  ),
                ),
                Positioned(
                  top: 10,
                  right: 10,
                  child: Row(
                    children: [
                      _ProductHeroOverlayIcon(
                        icon: isWishlisted
                            ? Icons.favorite
                            : Icons.favorite_border,
                        onTap: () => ref
                            .read(wishlistControllerProvider.notifier)
                            .toggle(widget.productId),
                      ),
                      const SizedBox(width: 6),
                      _ProductHeroOverlayIcon(
                        icon: Icons.ios_share_outlined,
                        onTap: () async {
                          await Clipboard.setData(
                            ClipboardData(
                              text:
                                  'https://app.glamejewelry.ru/#/product/${widget.productId}',
                            ),
                          );
                          if (!context.mounted) return;
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Ссылка на товар скопирована'),
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
        ),
      ],
    );
  }

  Widget _buildTopInfoBlock(
    BuildContext context, {
    required String name,
    required String? article,
    required String priceLabel,
    required int? basePriceKopeks,
    required int loyaltyPoints,
    required num? stock,
  }) {
    final available = stock != null && stock > 0;
    return LayoutBuilder(
      builder: (context, constraints) {
        final gap = constraints.maxWidth >= 560 ? 22.0 : 12.0;
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name.toUpperCase(),
                    style: const TextStyle(
                      fontSize: 18,
                      height: 1.2,
                      fontWeight: FontWeight.w400,
                      letterSpacing: 0.1,
                      color: GlameColors.textPrimary,
                    ),
                  ),
                  if (article != null && article.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      article.toUpperCase(),
                      style: const TextStyle(
                        fontSize: 10,
                        letterSpacing: 0.6,
                        color: GlameColors.textSecondary,
                      ),
                    ),
                  ],
                  const SizedBox(height: 10),
                  _PriceWithBonus(
                    priceLabel: priceLabel,
                    basePriceKopeks: basePriceKopeks,
                    loyaltyPoints: loyaltyPoints,
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Container(
                        width: 6,
                        height: 6,
                        decoration: BoxDecoration(
                          color: available
                              ? GlameColors.gold
                              : GlameColors.graphite,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        available ? 'В наличии' : 'Нет в наличии',
                        style: const TextStyle(
                          fontSize: 11,
                          color: GlameColors.textPrimary,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            SizedBox(width: gap),
            Expanded(
              child: Align(
                alignment: Alignment.topLeft,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 230),
                  child: _VariantsSelector(productId: widget.productId),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildActionButtons(
    BuildContext context,
    num? stock,
    bool isWishlisted,
  ) {
    final available = stock != null && stock > 0;
    if (!available) {
      return Column(
        children: [
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('Сообщим, когда товар появится в наличии'),
                  ),
                );
              },
              style: FilledButton.styleFrom(
                backgroundColor: GlameColors.textPrimary,
                foregroundColor: GlameColors.surface2,
                minimumSize: const Size.fromHeight(42),
                shape: const RoundedRectangleBorder(),
              ),
              child: const Text(
                'Сообщить о поступлении',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w400),
              ),
            ),
          ),
          const SizedBox(height: 8),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 12),
            child: Text(
              'Оставьте контакт, и мы сообщим, когда изделие вернется. Это поможет прогнозировать спрос.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 10,
                height: 1.35,
                color: GlameColors.textSecondary,
              ),
            ),
          ),
        ],
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final gap = constraints.maxWidth >= 560 ? 22.0 : 12.0;
        return Row(
          children: [
            Expanded(
              child: FilledButton(
                onPressed: () => _addToCart(context),
                style: FilledButton.styleFrom(
                  backgroundColor: GlameColors.textPrimary,
                  foregroundColor: GlameColors.surface2,
                  minimumSize: const Size.fromHeight(42),
                  shape: const RoundedRectangleBorder(),
                ),
                child: const Text(
                  'Добавить в корзину',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w400),
                ),
              ),
            ),
            SizedBox(width: gap),
            Expanded(
              child: OutlinedButton(
                onPressed: () async {
                  final added = await _addToCart(context);
                  if (added && context.mounted) {
                    context.go('/checkout');
                  }
                },
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(42),
                  side: const BorderSide(color: GlameColors.lightGray),
                  shape: const RoundedRectangleBorder(),
                  foregroundColor: GlameColors.textPrimary,
                ),
                child: const Text(
                  'Купить сейчас',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w400),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Future<bool> _addToCart(BuildContext context) async {
    final auth = ref.read(authControllerProvider);
    if (auth.user == null) {
      context.go(
        '/login?next=${Uri.encodeComponent('/product/${widget.productId}')}',
      );
      return false;
    }

    await ref.read(cartControllerProvider.notifier).addOne(widget.productId);
    final cartState = ref.read(cartControllerProvider);
    if (cartState.error != null) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(cartState.error!)));
      }
      return false;
    }
    if (!context.mounted) return false;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Товар добавлен в корзину'),
        backgroundColor: GlameColors.textPrimary,
        duration: const Duration(seconds: 2),
        action: SnackBarAction(
          label: 'ПЕРЕЙТИ',
          textColor: GlameColors.gold,
          onPressed: () => context.go('/home?tab=11'),
        ),
      ),
    );
    return true;
  }

  Future<void> _showStylistEntrySheet(
    BuildContext context, {
    required String name,
    required String priceLabel,
    required String? imageUrl,
  }) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: GlameColors.textPrimary,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
      ),
      builder: (sheetContext) {
        return _StylistEntrySheet(
          name: name,
          priceLabel: priceLabel,
          imageUrl: imageUrl,
          onProductQuestion: () {
            Navigator.of(sheetContext).pop();
            _showProductQuestionSheet(
              context,
              name: name,
              priceLabel: priceLabel,
              imageUrl: imageUrl,
            );
          },
          onChoiceHelp: () {
            Navigator.of(sheetContext).pop();
            _showChoiceHelpSheet(
              context,
              name: name,
              priceLabel: priceLabel,
              imageUrl: imageUrl,
            );
          },
        );
      },
    );
  }

  Future<void> _showProductQuestionSheet(
    BuildContext context, {
    required String name,
    required String priceLabel,
    required String? imageUrl,
  }) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: GlameColors.textPrimary,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
      ),
      builder: (sheetContext) {
        return _ProductQuestionSheet(
          name: name,
          priceLabel: priceLabel,
          imageUrl: imageUrl,
          onSubmit: (question) {
            Navigator.of(sheetContext).pop();
            _openStylistChat(
              context,
              'Вопрос по изделию ${name.toUpperCase()}: $question',
            );
          },
        );
      },
    );
  }

  Future<void> _showChoiceHelpSheet(
    BuildContext context, {
    required String name,
    required String priceLabel,
    required String? imageUrl,
  }) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: GlameColors.textPrimary,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
      ),
      builder: (sheetContext) {
        return _ChoiceHelpSheet(
          name: name,
          priceLabel: priceLabel,
          imageUrl: imageUrl,
          onSubmit: (answers) {
            Navigator.of(sheetContext).pop();
            _openStylistChat(
              context,
              'Нужна помощь в выборе. Изделие: ${name.toUpperCase()}. ${answers.join('. ')}.',
            );
          },
        );
      },
    );
  }

  void _openStylistChat(BuildContext context, String message) {
    showStylistContactSheet(
      context,
      productId: widget.productId,
      initialMessage: message,
      source: 'product_card',
      scenario: 'live_stylist',
    );
  }

  Widget _buildBenefitsBlock() {
    final items = [
      (Icons.self_improvement_outlined, 'Примерка\nперед покупкой'),
      (Icons.verified_user_outlined, '30 дней\nгарантии'),
      (Icons.local_shipping_outlined, 'Быстрая доставка\n1-4 дня'),
      (Icons.straighten_outlined, 'Поможем\nс размером'),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
        return GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: items.length,
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 4,
            mainAxisExtent: 84,
            crossAxisSpacing: 8,
            mainAxisSpacing: 8,
          ),
          itemBuilder: (context, index) {
            final item = items[index];
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 8),
              decoration: BoxDecoration(
                color: GlameColors.surface2,
                border: Border.all(color: GlameColors.lightGray),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(item.$1, size: 18, color: GlameColors.textPrimary),
                  const SizedBox(height: 6),
                  Flexible(
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      alignment: Alignment.topCenter,
                      child: Text(
                        item.$2,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          fontSize: 9.5,
                          height: 1.18,
                          color: GlameColors.textPrimary,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildStylistBlock(
    String name,
    String priceLabel,
    List<String> images,
    String productDescription,
  ) {
    final description = productDescription.isNotEmpty
        ? _limitToSentences(productDescription, 2)
        : 'Четкая форма и отражающие поверхности создают эффект архитектурной скульптуры. Идеальны для минималистичных образов с акцентом на характер и осанку.';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _BlockTitle('СТИЛЕВОЕ ДНК GLAME'),
        const SizedBox(height: 8),
        _ProductSection(
          child: Column(
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _SquarePreview(
                    imageUrl: images.length > 1
                        ? images[1]
                        : (images.isNotEmpty ? images.first : null),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          description,
                          style: const TextStyle(
                            fontSize: 12,
                            color: GlameColors.textSecondary,
                            height: 1.4,
                          ),
                        ),
                        const SizedBox(height: 10),
                        InkWell(
                          onTap: () {
                            final loggedIn =
                                ref.read(authControllerProvider).user != null;
                            if (!loggedIn) {
                              final target = buildStylistChatRoute(
                                productId: widget.productId,
                                source: 'product_card',
                                scenario: 'live_stylist',
                              );
                              context.push(
                                '/login?next=${Uri.encodeComponent(target)}',
                              );
                              return;
                            }
                            _showStylistEntrySheet(
                              context,
                              name: name,
                              priceLabel: priceLabel,
                              imageUrl: images.isNotEmpty ? images.first : null,
                            );
                          },
                          child: Container(
                            width: double.infinity,
                            height: 34,
                            decoration: BoxDecoration(
                              border: Border.all(color: GlameColors.lightGray),
                            ),
                            child: const Stack(
                              alignment: Alignment.center,
                              children: [
                                Text(
                                  'Подобрать под меня',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    fontSize: 14,
                                    color: GlameColors.textPrimary,
                                  ),
                                ),
                                Positioned(
                                  right: 10,
                                  child: Icon(
                                    Icons.arrow_forward,
                                    size: 16,
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
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildLookSetBlock(
    AsyncValue<List<dynamic>> looksAsync, {
    required int loyaltyPoints,
  }) {
    return looksAsync.when(
      data: (looksRaw) {
        final looks = looksRaw
            .whereType<Map>()
            .map((x) => Map<String, dynamic>.from(x))
            .toList();
        if (looks.isEmpty) return const SizedBox.shrink();
        final clampedPage = lookPage.clamp(0, looks.length - 1);

        return _ProductSection(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _BlockTitle('СОБРАННЫЙ КОМПЛЕКТ GLAME'),
              const SizedBox(height: 8),
              SizedBox(
                height: 264,
                child: Stack(
                  children: [
                    PageView.builder(
                      controller: lookController,
                      itemCount: looks.length,
                      onPageChanged: (value) =>
                          setState(() => lookPage = value),
                      itemBuilder: (context, index) => _LookBundleView(
                        look: looks[index],
                        loyaltyPoints: loyaltyPoints,
                        onBuildSet: (productIds) =>
                            _addLookBundleToCart(context, productIds),
                      ),
                    ),
                    if (looks.length > 1) ...[
                      Positioned(
                        left: 0,
                        top: 112,
                        child: _RoundArrowButton(
                          icon: Icons.chevron_left,
                          onTap: () =>
                              _showLookPage(clampedPage - 1, looks.length),
                        ),
                      ),
                      Positioned(
                        right: 0,
                        top: 112,
                        child: _RoundArrowButton(
                          icon: Icons.chevron_right,
                          onTap: () =>
                              _showLookPage(clampedPage + 1, looks.length),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
    );
  }

  void _showLookPage(int target, int count) {
    if (count <= 0) return;
    final next = target < 0 ? count - 1 : (target >= count ? 0 : target);
    lookController.animateToPage(
      next,
      duration: const Duration(milliseconds: 260),
      curve: Curves.easeOut,
    );
  }

  Future<void> _addLookBundleToCart(
    BuildContext context,
    List<String> productIds,
  ) async {
    if (productIds.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Выберите товары в комплекте')),
      );
      return;
    }
    final auth = ref.read(authControllerProvider);
    if (auth.user == null) {
      context.go(
        '/login?next=${Uri.encodeComponent('/product/${widget.productId}')}',
      );
      return;
    }

    await ref.read(cartControllerProvider.notifier).addMany(productIds);
    final cartState = ref.read(cartControllerProvider);
    if (cartState.error != null) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(cartState.error!)));
      }
      return;
    }
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Комплект добавлен в корзину'),
        backgroundColor: GlameColors.textPrimary,
        duration: const Duration(seconds: 2),
        action: SnackBarAction(
          label: 'ПЕРЕЙТИ',
          textColor: GlameColors.gold,
          onPressed: () => context.go('/home?tab=11'),
        ),
      ),
    );
  }

  Widget _buildDetailsBlock() {
    final items = [
      (
        Icons.auto_awesome_outlined,
        'Четкая форма',
        'Держит акцент даже в лаконичном образе.',
      ),
      (
        Icons.water_drop_outlined,
        'Гладкая поверхность',
        'Отражает свет и добавляет глубину украшению.',
      ),
      (
        Icons.lock_outline,
        'Надежный замок',
        'Комфортная посадка и уверенность в течение дня.',
      ),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _BlockTitle('ДЕТАЛИ'),
        const SizedBox(height: 12),
        _ProductSection(
          child: LayoutBuilder(
            builder: (context, constraints) {
              final columns = constraints.maxWidth >= 620 ? 3 : 1;
              return GridView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: items.length,
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: columns,
                  mainAxisExtent: 96,
                  crossAxisSpacing: 10,
                  mainAxisSpacing: 10,
                ),
                itemBuilder: (context, index) {
                  final item = items[index];
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(item.$1, size: 28, color: GlameColors.textSecondary),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              item.$2,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: GlameColors.textPrimary,
                              ),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              item.$3,
                              maxLines: 3,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 12,
                                color: GlameColors.textSecondary,
                                height: 1.35,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  );
                },
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildPackagingBlock(List<String> images) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _BlockTitle('УПАКОВКА'),
        const SizedBox(height: 12),
        _ProductSection(
          child: Row(
            children: [
              const _WidePreview(
                imageUrl: '/static/content_media/IMG_0576.jpg',
              ),
              const SizedBox(width: 16),
              const Expanded(
                child: Text(
                  'Каждое изделие в фирменной упаковке GLAME. Готово к подарку.',
                  style: TextStyle(
                    fontSize: 13,
                    height: 1.55,
                    color: GlameColors.textPrimary,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSimilarBlock(AsyncValue<List<dynamic>> recommendationsAsync) {
    final recommendations = recommendationsAsync.maybeWhen(
      data: (items) => items
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(),
      orElse: () => <Map<String, dynamic>>[],
    );
    final items = recommendations
        .map((item) => _recommendationProduct(item))
        .whereType<Map<String, dynamic>>()
        .take(3)
        .toList();
    final displayItems = items.isNotEmpty
        ? items
        : <Map<String, dynamic>>[
            {'name': 'Серьги SOLIS', 'price': 1890000},
            {'name': 'Серьги ECLIPSE', 'price': 1690000},
            {'name': 'Серьги ORBIT', 'price': 1790000},
          ];
    return _ProductSection(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionHeader(
            title: 'ПОХОЖИЕ ПО НАСТРОЕНИЮ',
            action: 'Смотреть все',
          ),
          const SizedBox(height: 14),
          SizedBox(
            height: 224,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                ...List.generate(3, (index) {
                  final item = index < displayItems.length
                      ? displayItems[index]
                      : null;
                  return Padding(
                    padding: const EdgeInsets.only(right: 10),
                    child: SizedBox(
                      width: 148,
                      child: GestureDetector(
                        onTap: item == null
                            ? null
                            : () {
                                final productId = _extractProductId(item);
                                if (productId != null) {
                                  context.push(
                                    '/product/${Uri.encodeComponent(productId)}',
                                  );
                                }
                              },
                        child: _SimilarTile(
                          imageUrl: _productImageUrl(item),
                          title: (item?['name'] as String?) ?? 'GLAME',
                          price: formatRubFromKopeks(item?['price']),
                        ),
                      ),
                    ),
                  );
                }),
                GestureDetector(
                  onTap: () => context.go('/home?tab=1'),
                  child: const SizedBox(width: 96, child: _MoreTile()),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String? _firstVariantId(Map<String, dynamic>? variantsData) {
    final variants = variantsData?['variants'];
    if (variants is! List) return null;
    for (final item in variants) {
      if (item is! Map) continue;
      final id = item['id'];
      final price = item['price'];
      if (id is String && id.isNotEmpty && price is num && price > 0) {
        return id;
      }
    }
    for (final item in variants) {
      if (item is! Map) continue;
      final id = item['id'];
      if (id is String && id.isNotEmpty) return id;
    }
    return null;
  }

  String _stripHtml(String html) {
    return html
        .replaceAll(RegExp(r'<[^>]*>'), ' ')
        .replaceAll('&nbsp;', ' ')
        .replaceAll('&amp;', '&')
        .replaceAll('&quot;', '"')
        .replaceAll('&#39;', "'")
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  String _limitToSentences(String text, int maxSentences) {
    final normalized = text.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (normalized.isEmpty || maxSentences <= 0) return '';

    final matches = RegExp(r'[^.!?]+[.!?]*').allMatches(normalized);
    final parts = <String>[];
    for (final match in matches) {
      final part = match.group(0)?.trim();
      if (part == null || part.isEmpty) continue;
      parts.add(part);
      if (parts.length >= maxSentences) break;
    }

    if (parts.isEmpty) return normalized;
    return parts.join(' ').trim();
  }
}

class _ProductHeroOverlayIcon extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;

  const _ProductHeroOverlayIcon({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        width: 28,
        height: 28,
        decoration: BoxDecoration(
          color: GlameColors.surface2.withValues(alpha: 0.82),
          border: Border.all(
            color: GlameColors.surface2.withValues(alpha: 0.42),
          ),
        ),
        alignment: Alignment.center,
        child: Icon(icon, size: 15, color: GlameColors.textPrimary),
      ),
    );
  }
}

List<Map<String, dynamic>> _lookProducts(Map<String, dynamic> look) {
  final raw = look['products'];
  if (raw is! List) return <Map<String, dynamic>>[];
  return raw
      .whereType<Map>()
      .map((item) => Map<String, dynamic>.from(item))
      .toList();
}

Map<String, dynamic>? _recommendationProduct(Map<String, dynamic> item) {
  final raw = item['product'];
  if (raw is Map) return Map<String, dynamic>.from(raw);
  if (item['id'] is String) return item;
  return null;
}

int _productsTotal(List<Map<String, dynamic>> products, List<String> keys) {
  return products.fold<int>(0, (sum, product) {
    for (final key in keys) {
      final price = product[key];
      if (price is int && price > 0) return sum + price;
      if (price is num && price > 0) return sum + price.toInt();
    }
    return sum;
  });
}

String? _lookImageUrl(Map<String, dynamic> look) {
  final media = look['media_items'];
  if (media is List) {
    for (final item in media) {
      if (item is! Map) continue;
      final url = resolveAssetUrl(item['thumbnail_url'] ?? item['url']);
      if (url != null) return url;
    }
  }
  final imageUrl = resolveAssetUrl(look['image_url']);
  if (imageUrl != null) return imageUrl;
  final imageUrls = look['image_urls'];
  if (imageUrls is List) {
    for (final item in imageUrls) {
      final url = item is Map
          ? resolveAssetUrl(item['url'])
          : resolveAssetUrl(item);
      if (url != null) return url;
    }
  }
  return null;
}

String? _productImageUrl(Map<String, dynamic>? product) {
  if (product == null) return null;
  final images = product['images'];
  if (images is List) {
    for (final image in images) {
      final url = resolveAssetUrl(image);
      if (url != null) return url;
    }
  }
  return null;
}

String? _extractProductId(Map<String, dynamic>? product) {
  if (product == null) return null;
  final candidates = <dynamic>[
    product['id'],
    product['product_id'],
    product['external_id'],
  ];
  for (final raw in candidates) {
    if (raw is String) {
      final value = raw.trim();
      if (value.isNotEmpty) return value;
    } else if (raw is num) {
      return raw.toInt().toString();
    }
  }
  return null;
}

int _discountedPriceKopeks(int basePriceKopeks, int loyaltyPoints) {
  if (basePriceKopeks <= 0 || loyaltyPoints <= 0) return basePriceKopeks;
  final maxDiscountByRule = (basePriceKopeks * 0.1).round();
  final availableByPoints = loyaltyPoints * 100;
  final discount = math.min(maxDiscountByRule, availableByPoints);
  return math.max(0, basePriceKopeks - discount);
}

class _PriceWithBonus extends StatelessWidget {
  final String priceLabel;
  final int? basePriceKopeks;
  final int loyaltyPoints;

  const _PriceWithBonus({
    required this.priceLabel,
    required this.basePriceKopeks,
    required this.loyaltyPoints,
  });

  @override
  Widget build(BuildContext context) {
    final price = basePriceKopeks ?? 0;
    if (price <= 0 || loyaltyPoints <= 0) {
      return Text(
        priceLabel,
        style: const TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w400,
          color: GlameColors.textPrimary,
        ),
      );
    }
    final discounted = _discountedPriceKopeks(price, loyaltyPoints);
    final hasDiscount = discounted < price;
    if (!hasDiscount) {
      return Text(
        priceLabel,
        style: const TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w400,
          color: GlameColors.textPrimary,
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          formatRubFromKopeks(price),
          style: const TextStyle(
            fontSize: 14,
            color: GlameColors.textSecondary,
            decoration: TextDecoration.lineThrough,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          formatRubFromKopeks(discounted),
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w500,
            color: GlameColors.textPrimary,
          ),
        ),
        const SizedBox(height: 4),
        const Text(
          'Баллами в приложении можно оплатить до 10 % скидки',
          style: TextStyle(fontSize: 10, color: GlameColors.textSecondary),
        ),
        const Text(
          'Цена с учетом скидки',
          style: TextStyle(fontSize: 10, color: GlameColors.textSecondary),
        ),
      ],
    );
  }
}

class _NoImage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 1,
      child: Container(
        color: GlameColors.surface,
        child: const Center(
          child: Icon(
            Icons.image_outlined,
            size: 48,
            color: GlameColors.textSecondary,
          ),
        ),
      ),
    );
  }
}

class _BlockTitle extends StatelessWidget {
  final String text;

  const _BlockTitle(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontSize: 12,
        letterSpacing: 0.4,
        color: GlameColors.textPrimary,
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  final String action;

  const _SectionHeader({required this.title, required this.action});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(child: _BlockTitle(title)),
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Text(
            action,
            style: const TextStyle(
              fontSize: 12,
              color: GlameColors.textSecondary,
            ),
          ),
        ),
        const SizedBox(width: 8),
        const Icon(
          Icons.arrow_forward,
          size: 18,
          color: GlameColors.textSecondary,
        ),
      ],
    );
  }
}

class _ProductSection extends StatelessWidget {
  final Widget child;

  const _ProductSection({required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      color: GlameColors.surface2,
      child: child,
    );
  }
}

class _SheetScaffold extends StatelessWidget {
  final String title;
  final Widget child;

  const _SheetScaffold({required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          18,
          10,
          18,
          18 + MediaQuery.of(context).viewInsets.bottom,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 42,
                height: 3,
                decoration: BoxDecoration(
                  color: GlameColors.lightGray,
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(fontSize: 16, letterSpacing: 1.2),
                  ),
                ),
                IconButton(
                  onPressed: () => Navigator.of(context).pop(),
                  icon: const Icon(Icons.close, size: 18),
                ),
              ],
            ),
            const SizedBox(height: 10),
            child,
          ],
        ),
      ),
    );
  }
}

class _SheetProductCard extends StatelessWidget {
  final String name;
  final String priceLabel;
  final String? imageUrl;

  const _SheetProductCard({
    required this.name,
    required this.priceLabel,
    required this.imageUrl,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        border: Border.all(color: GlameColors.lightGray),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: SizedBox(
              width: 42,
              height: 42,
              child: imageUrl == null
                  ? Container(color: GlameColors.surface)
                  : CachedNetworkImage(imageUrl: imageUrl!, fit: BoxFit.cover),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              name.toUpperCase(),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 12, letterSpacing: .4),
            ),
          ),
          const SizedBox(width: 10),
          Text(priceLabel, style: const TextStyle(fontSize: 12)),
        ],
      ),
    );
  }
}

class _StylistEntrySheet extends StatelessWidget {
  final String name;
  final String priceLabel;
  final String? imageUrl;
  final VoidCallback onProductQuestion;
  final VoidCallback onChoiceHelp;

  const _StylistEntrySheet({
    required this.name,
    required this.priceLabel,
    required this.imageUrl,
    required this.onProductQuestion,
    required this.onChoiceHelp,
  });

  @override
  Widget build(BuildContext context) {
    return _SheetScaffold(
      title: 'ПОДОБРАТЬ ПОД МЕНЯ',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Чтобы быстрее помочь, сначала уточним, что вам нужно',
            style: TextStyle(fontSize: 12, color: GlameColors.textSecondary),
          ),
          const SizedBox(height: 14),
          _SheetProductCard(
            name: name,
            priceLabel: priceLabel,
            imageUrl: imageUrl,
          ),
          const SizedBox(height: 18),
          const _SelectorLabel('ЧТО ВАМ НУЖНО?'),
          const SizedBox(height: 10),
          _SheetActionButton(
            icon: Icons.chat_bubble_outline,
            label: 'Вопрос по этому изделию',
            onTap: onProductQuestion,
          ),
          const SizedBox(height: 10),
          _SheetActionButton(
            icon: Icons.checkroom_outlined,
            label: 'Нужна помощь в выборе',
            onTap: onChoiceHelp,
          ),
          const SizedBox(height: 10),
          const Text(
            'Дальше вопросы меняются в зависимости от ответа',
            style: TextStyle(fontSize: 11, color: GlameColors.textSecondary),
          ),
        ],
      ),
    );
  }
}

class _ProductQuestionSheet extends StatelessWidget {
  final String name;
  final String priceLabel;
  final String? imageUrl;
  final ValueChanged<String> onSubmit;

  const _ProductQuestionSheet({
    required this.name,
    required this.priceLabel,
    required this.imageUrl,
    required this.onSubmit,
  });

  @override
  Widget build(BuildContext context) {
    final questions = [
      ('Подойдет ли мне?', Icons.person_outline),
      ('С чем носить?', Icons.checkroom_outlined),
      ('Характеристики', Icons.tune),
      ('Размер / посадка', Icons.straighten),
    ];
    return _SheetScaffold(
      title: 'ПО ЭТОМУ ИЗДЕЛИЮ',
      child: Column(
        children: [
          _SheetProductCard(
            name: name,
            priceLabel: priceLabel,
            imageUrl: imageUrl,
          ),
          const SizedBox(height: 14),
          const Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'Что хотите узнать?',
              style: TextStyle(fontSize: 12, color: GlameColors.textSecondary),
            ),
          ),
          const SizedBox(height: 10),
          ...questions.map(
            (item) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _SheetActionButton(
                icon: item.$2,
                label: item.$1,
                onTap: () => onSubmit(item.$1),
              ),
            ),
          ),
          const SizedBox(height: 4),
          SizedBox(
            width: double.infinity,
            height: 52,
            child: FilledButton(
              onPressed: () => onSubmit('Хочу консультацию по этому изделию'),
              child: const Text('ПЕРЕЙТИ К СТИЛИСТУ'),
            ),
          ),
        ],
      ),
    );
  }
}

class _ChoiceHelpSheet extends StatefulWidget {
  final String name;
  final String priceLabel;
  final String? imageUrl;
  final ValueChanged<List<String>> onSubmit;

  const _ChoiceHelpSheet({
    required this.name,
    required this.priceLabel,
    required this.imageUrl,
    required this.onSubmit,
  });

  @override
  State<_ChoiceHelpSheet> createState() => _ChoiceHelpSheetState();
}

class _ChoiceHelpSheetState extends State<_ChoiceHelpSheet> {
  String who = 'Для себя';
  String task = 'На каждый день';
  String priority = 'Универсальность';

  @override
  Widget build(BuildContext context) {
    return _SheetScaffold(
      title: 'ПОМОЩЬ В ВЫБОРЕ',
      child: Column(
        children: [
          _SheetProductCard(
            name: widget.name,
            priceLabel: widget.priceLabel,
            imageUrl: widget.imageUrl,
          ),
          const SizedBox(height: 14),
          _QuestionGroup(
            title: '1. Для кого выбираете?',
            value: who,
            options: const ['Для себя', 'В подарок'],
            onChanged: (value) => setState(() => who = value),
          ),
          _QuestionGroup(
            title: '2. Для какой задачи?',
            value: task,
            options: const [
              'На каждый день',
              'На событие',
              'На работу',
              'Просто понравилось',
            ],
            onChanged: (value) => setState(() => task = value),
          ),
          _QuestionGroup(
            title: '3. Что для вас важнее?',
            value: priority,
            options: const [
              'Универсальность',
              'Акцент',
              'Характеристики',
              'Нужен совет стилиста',
            ],
            onChanged: (value) => setState(() => priority = value),
          ),
          SizedBox(
            width: double.infinity,
            height: 52,
            child: FilledButton(
              onPressed: () => widget.onSubmit([
                'Кому: $who',
                'Задача: $task',
                'Важно: $priority',
              ]),
              child: const Text('ПЕРЕДАТЬ СТИЛИСТУ'),
            ),
          ),
        ],
      ),
    );
  }
}

class _QuestionGroup extends StatelessWidget {
  final String title;
  final String value;
  final List<String> options;
  final ValueChanged<String> onChanged;

  const _QuestionGroup({
    required this.title,
    required this.value,
    required this.options,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontSize: 12)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: options.map((option) {
              final selected = option == value;
              return ChoiceChip(
                label: Text(option),
                selected: selected,
                onSelected: (_) => onChanged(option),
                showCheckmark: false,
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

class _SheetActionButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _SheetActionButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        height: 52,
        padding: const EdgeInsets.symmetric(horizontal: 14),
        decoration: BoxDecoration(
          border: Border.all(color: GlameColors.lightGray),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 20, color: GlameColors.textSecondary),
            const SizedBox(width: 10),
            Text(label, style: const TextStyle(fontSize: 13)),
          ],
        ),
      ),
    );
  }
}

class _SimilarTile extends StatelessWidget {
  final String? imageUrl;
  final String title;
  final String price;

  const _SimilarTile({
    required this.imageUrl,
    required this.title,
    required this.price,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: GlameColors.surface,
        borderRadius: BorderRadius.circular(8),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Container(
              width: double.infinity,
              color: GlameColors.surface2,
              padding: const EdgeInsets.all(6),
              child: imageUrl != null
                  ? CachedNetworkImage(
                      imageUrl: imageUrl!,
                      fit: BoxFit.contain,
                      placeholder: (_, _) =>
                          Container(color: GlameColors.surface2),
                      errorWidget: (_, _, _) =>
                          Container(color: GlameColors.surface2),
                    )
                  : Container(color: GlameColors.surface2),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 12,
                    color: GlameColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  price,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
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
}

class _MoreTile extends StatelessWidget {
  const _MoreTile();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: GlameColors.surface,
        borderRadius: BorderRadius.circular(8),
      ),
      child: const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.arrow_forward, size: 26, color: GlameColors.textPrimary),
            SizedBox(height: 18),
            Text(
              'ЕЩЁ',
              style: TextStyle(
                fontSize: 14,
                letterSpacing: 1,
                color: GlameColors.textPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LookBundleView extends StatefulWidget {
  final Map<String, dynamic> look;
  final int loyaltyPoints;
  final Future<void> Function(List<String> productIds) onBuildSet;

  const _LookBundleView({
    required this.look,
    required this.loyaltyPoints,
    required this.onBuildSet,
  });

  @override
  State<_LookBundleView> createState() => _LookBundleViewState();
}

class _LookBundleViewState extends State<_LookBundleView> {
  final Set<String> _selectedIds = <String>{};

  void _toggleSelection(Map<String, dynamic>? product) {
    final productId = _extractProductId(product);
    if (productId == null) return;
    setState(() {
      if (_selectedIds.contains(productId)) {
        _selectedIds.remove(productId);
      } else {
        _selectedIds.add(productId);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final products = _lookProducts(widget.look);
    final cover =
        _lookImageUrl(widget.look) ??
        _productImageUrl(products.isNotEmpty ? products.first : null);
    final visibleProducts = products.take(3).toList();
    final selectedProducts = products.where((product) {
      final id = _extractProductId(product);
      return id != null && _selectedIds.contains(id);
    }).toList();
    final selectedProductIds = selectedProducts
        .map(_extractProductId)
        .whereType<String>()
        .toList();
    final total = _productsTotal(selectedProducts, ['price']);

    return LayoutBuilder(
      builder: (context, constraints) {
        final spacing = constraints.maxWidth < 420 ? 10.0 : 14.0;
        return Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              flex: 7,
              child: cover != null
                  ? CachedNetworkImage(
                      imageUrl: cover,
                      fit: BoxFit.cover,
                      placeholder: (_, _) =>
                          Container(color: GlameColors.surface),
                      errorWidget: (_, _, _) =>
                          Container(color: GlameColors.surface),
                    )
                  : Container(color: GlameColors.surface),
            ),
            SizedBox(width: spacing),
            Expanded(
              flex: 10,
              child: Column(
                children: [
                  Expanded(
                    child: Row(
                      children: List.generate(3, (index) {
                        final product = index < visibleProducts.length
                            ? visibleProducts[index]
                            : null;
                        final productId = _extractProductId(product);
                        final selected =
                            productId != null &&
                            _selectedIds.contains(productId);
                        return Expanded(
                          child: Padding(
                            padding: EdgeInsets.only(
                              right: index == 2 ? 0 : spacing,
                            ),
                            child: _SetTile(
                              imageUrl: _productImageUrl(product),
                              priceLabel: _bundleProductPriceLabel(product),
                              availabilityLabel:
                                  _bundleProductAvailabilityLabel(product),
                              selected: selected,
                              onTap: productId == null
                                  ? null
                                  : () => _toggleSelection(product),
                            ),
                          ),
                        );
                      }),
                    ),
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    height: 44,
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: selectedProductIds.isEmpty
                          ? null
                          : () => widget.onBuildSet(selectedProductIds),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: GlameColors.textPrimary,
                        foregroundColor: GlameColors.surface2,
                        disabledBackgroundColor: GlameColors.textPrimary
                            .withValues(alpha: 0.54),
                        disabledForegroundColor: GlameColors.surface2
                            .withValues(alpha: 0.7),
                        shadowColor: Colors.transparent,
                        surfaceTintColor: Colors.transparent,
                        elevation: 0,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                      child: const Text(
                        'Собрать комплект',
                        style: TextStyle(fontSize: 13, letterSpacing: 0.4),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  _LookBundlePrice(
                    total: total,
                    loyaltyPoints: widget.loyaltyPoints,
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

class _LookBundlePrice extends StatelessWidget {
  final int total;
  final int loyaltyPoints;

  const _LookBundlePrice({required this.total, required this.loyaltyPoints});

  @override
  Widget build(BuildContext context) {
    if (total <= 0) {
      return const Text(
        'Нажмите на фото, чтобы добавить товары в комплект',
        style: TextStyle(fontSize: 12, color: GlameColors.textSecondary),
      );
    }
    final discounted = _discountedPriceKopeks(total, loyaltyPoints);
    final hasDiscount = discounted < total;
    return Column(
      children: [
        if (hasDiscount)
          Text(
            formatRubFromKopeks(total),
            style: const TextStyle(
              fontSize: 16,
              color: GlameColors.textSecondary,
              decoration: TextDecoration.lineThrough,
            ),
          ),
        Text(
          formatRubFromKopeks(hasDiscount ? discounted : total),
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: GlameColors.textPrimary,
          ),
        ),
        if (hasDiscount) ...[
          const SizedBox(height: 4),
          const Text(
            'Баллами в приложении можно оплатить до 10 % скидки',
            style: TextStyle(fontSize: 10, color: GlameColors.textSecondary),
          ),
          const Text(
            'Цена с учетом скидки',
            style: TextStyle(fontSize: 10, color: GlameColors.textSecondary),
          ),
        ],
      ],
    );
  }
}

class _RoundArrowButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;

  const _RoundArrowButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      customBorder: const CircleBorder(),
      child: Container(
        width: 34,
        height: 34,
        decoration: BoxDecoration(
          color: GlameColors.textPrimary.withAlpha(220),
          shape: BoxShape.circle,
          border: Border.all(color: GlameColors.lightGray),
        ),
        child: Icon(icon, size: 22, color: GlameColors.textPrimary),
      ),
    );
  }
}

class _SquarePreview extends StatelessWidget {
  final String? imageUrl;

  const _SquarePreview({this.imageUrl});

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(2),
      child: SizedBox(
        width: 112,
        height: 112,
        child: imageUrl != null
            ? CachedNetworkImage(
                imageUrl: imageUrl!,
                fit: BoxFit.cover,
                placeholder: (_, _) => Container(color: GlameColors.surface),
                errorWidget: (_, _, _) => Container(color: GlameColors.surface),
              )
            : Container(
                color: GlameColors.surface,
                child: const Icon(
                  Icons.image_outlined,
                  color: GlameColors.textSecondary,
                ),
              ),
      ),
    );
  }
}

class _WidePreview extends StatelessWidget {
  final String? imageUrl;

  const _WidePreview({this.imageUrl});

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(2),
      child: SizedBox(
        width: 150,
        height: 86,
        child: imageUrl != null
            ? CachedNetworkImage(
                imageUrl: imageUrl!,
                fit: BoxFit.cover,
                placeholder: (_, _) => Container(color: GlameColors.surface),
                errorWidget: (_, _, _) => Container(color: GlameColors.surface),
              )
            : Container(color: GlameColors.surface),
      ),
    );
  }
}

class _SetTile extends StatelessWidget {
  final String? imageUrl;
  final String? priceLabel;
  final String? availabilityLabel;
  final bool selected;
  final VoidCallback? onTap;

  const _SetTile({
    this.imageUrl,
    this.priceLabel,
    this.availabilityLabel,
    this.selected = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final hasData =
        imageUrl != null ||
        (priceLabel != null && priceLabel!.isNotEmpty) ||
        (availabilityLabel != null && availabilityLabel!.isNotEmpty);

    return Material(
      color: Colors.transparent,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: InkWell(
              onTap: onTap,
              splashColor: GlameColors.textPrimary.withValues(alpha: 0.12),
              highlightColor: GlameColors.textPrimary.withValues(alpha: 0.05),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  if (imageUrl != null)
                    CachedNetworkImage(
                      imageUrl: imageUrl!,
                      fit: BoxFit.cover,
                      placeholder: (_, _) =>
                          Container(color: GlameColors.surface),
                      errorWidget: (_, _, _) =>
                          Container(color: GlameColors.surface),
                    )
                  else
                    Container(color: GlameColors.surface),
                  Positioned.fill(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: selected
                            ? GlameColors.textPrimary.withValues(alpha: 0.18)
                            : Colors.transparent,
                        border: Border.all(color: GlameColors.lightGray),
                      ),
                    ),
                  ),
                  if (hasData)
                    Center(
                      child: Container(
                        width: 34,
                        height: 34,
                        decoration: BoxDecoration(
                          color: selected
                              ? GlameColors.gold
                              : GlameColors.surface2.withValues(alpha: 0.92),
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: selected
                                ? GlameColors.gold
                                : GlameColors.lightGray,
                          ),
                        ),
                        child: Icon(
                          selected ? Icons.check : Icons.add,
                          size: selected ? 20 : 24,
                          color: selected
                              ? GlameColors.black
                              : GlameColors.textPrimary,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          if (priceLabel != null && priceLabel!.isNotEmpty)
            Text(
              priceLabel!,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 12,
                color: GlameColors.textPrimary,
              ),
            ),
          if (availabilityLabel != null && availabilityLabel!.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              availabilityLabel!,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 11,
                color: availabilityLabel == 'В наличии'
                    ? GlameColors.gold
                    : GlameColors.graphite,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

String? _bundleProductPriceLabel(Map<String, dynamic>? product) {
  if (product == null) return null;
  final value = product['price'];
  if (value is int && value > 0) return formatRubFromKopeks(value);
  if (value is num && value > 0) return formatRubFromKopeks(value.toInt());
  return 'Цена уточняется';
}

String? _bundleProductAvailabilityLabel(Map<String, dynamic>? product) {
  if (product == null) return null;
  final stock = product['stock'];
  final amount = stock is num ? stock.toDouble() : null;
  return (amount != null && amount > 0) ? 'В наличии' : 'Нет в наличии';
}

class _VariantsSelector extends ConsumerWidget {
  final String productId;

  const _VariantsSelector({required this.productId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final variantsAsync = ref.watch(productVariantsProvider(productId));
    return variantsAsync.when(
      data: (data) {
        final variantsRaw = data['variants'];
        final variants = variantsRaw is List
            ? variantsRaw
                  .whereType<Map>()
                  .map((x) => Map<String, dynamic>.from(x))
                  .where((x) => (x['id'] as String?)?.isNotEmpty == true)
                  .toList()
            : <Map<String, dynamic>>[];
        if (variants.length <= 1) return const SizedBox();

        final current = variants.firstWhere(
          (x) => x['id'] == productId,
          orElse: () => variants.first,
        );
        final currentColor =
            _specValue(current, 'Цвет') ?? _variantSuffix(current);
        final currentSize = _specValue(current, 'Размер');
        final colors = _uniqueValues(
          variants,
          (x) => _specValue(x, 'Цвет') ?? _variantSuffix(x),
        );
        final sizes = _uniqueValues(variants, (x) => _specValue(x, 'Размер'));

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (colors.length > 1) ...[
              const _SelectorLabel('МЕТАЛЛ'),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: colors.map((color) {
                  final selected = color == currentColor;
                  final target = _findVariant(
                    variants,
                    color: color,
                    size: currentSize,
                  );
                  return _VariantChip(
                    label: color,
                    selected: selected,
                    enabled: target != null,
                    leading: _ColorDot(color),
                    onTap: target == null
                        ? null
                        : () => context.pushReplacement(
                            '/product/${target['id']}',
                          ),
                  );
                }).toList(),
              ),
              const SizedBox(height: 18),
            ],
            if (sizes.length > 1) ...[
              const _SelectorLabel('РАЗМЕР'),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: sizes.map((size) {
                  final selected = size == currentSize;
                  final target = _findVariant(
                    variants,
                    color: currentColor,
                    size: size,
                  );
                  return _VariantChip(
                    label: size,
                    selected: selected,
                    enabled: target != null,
                    onTap: target == null
                        ? null
                        : () => context.pushReplacement(
                            '/product/${target['id']}',
                          ),
                  );
                }).toList(),
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () {},
                style: TextButton.styleFrom(
                  padding: EdgeInsets.zero,
                  minimumSize: const Size(0, 32),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: const Text(
                  'Не знаете размер? Поможем подобрать',
                  style: TextStyle(
                    fontSize: 10,
                    color: GlameColors.textSecondary,
                  ),
                ),
              ),
            ],
          ],
        );
      },
      loading: () => const SizedBox(),
      error: (_, _) => const SizedBox(),
    );
  }

  String? _specValue(Map<String, dynamic> item, String key) {
    final specs = item['specifications'];
    if (specs is! Map) return null;
    final value = specs[key];
    if (value == null) return null;
    final text = '$value'.trim();
    return text.isEmpty ? null : text;
  }

  String? _variantSuffix(Map<String, dynamic> item) {
    final article = (item['article'] as String?)?.trim() ?? '';
    final match = RegExp(r'[-_\s]([^/_\s-]+)').firstMatch(article);
    final value = match?.group(1)?.trim();
    return value == null || value.isEmpty ? null : value;
  }

  List<String> _uniqueValues(
    List<Map<String, dynamic>> variants,
    String? Function(Map<String, dynamic>) pick,
  ) {
    final result = <String>[];
    final seen = <String>{};
    for (final variant in variants) {
      final value = pick(variant);
      if (value == null || value.isEmpty) continue;
      final key = value.toLowerCase();
      if (seen.add(key)) result.add(value);
    }
    result.sort((a, b) => _naturalKey(a).compareTo(_naturalKey(b)));
    return result;
  }

  String _naturalKey(String value) {
    final number = num.tryParse(value.replaceAll(',', '.'));
    if (number != null) return number.toString().padLeft(8, '0');
    return value.toLowerCase();
  }

  Map<String, dynamic>? _findVariant(
    List<Map<String, dynamic>> variants, {
    String? color,
    String? size,
  }) {
    for (final variant in variants) {
      final variantColor =
          _specValue(variant, 'Цвет') ?? _variantSuffix(variant);
      final variantSize = _specValue(variant, 'Размер');
      if (color != null && variantColor != color) continue;
      if (size != null && variantSize != size) continue;
      return variant;
    }
    if (color != null) {
      for (final variant in variants) {
        final variantColor =
            _specValue(variant, 'Цвет') ?? _variantSuffix(variant);
        if (variantColor == color) return variant;
      }
    }
    if (size != null) {
      for (final variant in variants) {
        final variantSize = _specValue(variant, 'Размер');
        if (variantSize == size) return variant;
      }
    }
    return null;
  }
}

class _SelectorLabel extends StatelessWidget {
  final String label;

  const _SelectorLabel(this.label);

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: const TextStyle(
        fontSize: 9,
        letterSpacing: 0.6,
        color: GlameColors.textSecondary,
      ),
    );
  }
}

class _VariantChip extends StatelessWidget {
  final String label;
  final bool selected;
  final bool enabled;
  final Widget? leading;
  final VoidCallback? onTap;

  const _VariantChip({
    required this.label,
    required this.selected,
    required this.enabled,
    this.leading,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: enabled ? onTap : null,
      borderRadius: BorderRadius.circular(2),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 160),
        height: 28,
        padding: const EdgeInsets.symmetric(horizontal: 10),
        decoration: BoxDecoration(
          color: GlameColors.surface2,
          border: Border.all(
            color: selected ? GlameColors.graphite : GlameColors.lightGray,
          ),
          borderRadius: BorderRadius.circular(2),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (leading != null) ...[leading!, const SizedBox(width: 8)],
            Text(
              label,
              style: TextStyle(
                fontSize: 10,
                color: enabled
                    ? GlameColors.textPrimary
                    : GlameColors.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ColorDot extends StatelessWidget {
  final String label;

  const _ColorDot(this.label);

  @override
  Widget build(BuildContext context) {
    final lower = label.toLowerCase();
    final color = lower.contains('сер')
        ? GlameColors.coolLightGray
        : lower.contains('роз')
        ? GlameColors.warmGray
        : GlameColors.gold;
    return Container(
      width: 14,
      height: 14,
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        border: Border.all(color: GlameColors.lightGray),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  final VoidCallback onRetry;

  const _ErrorState({required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(
            Icons.error_outline,
            size: 48,
            color: GlameColors.textSecondary,
          ),
          const SizedBox(height: 16),
          const Text(
            'Ошибка загрузки',
            style: TextStyle(fontSize: 16, color: GlameColors.surface2),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: onRetry,
            child: const Text(
              'ПОВТОРИТЬ',
              style: TextStyle(color: GlameColors.gold, letterSpacing: 1),
            ),
          ),
        ],
      ),
    );
  }
}
