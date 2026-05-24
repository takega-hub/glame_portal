import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/formatters/rub.dart';
import '../../core/network/asset_url.dart';
import '../../core/theme/glame_theme.dart';
import '../brands/brands_screen.dart';
import '../customer/customer_cabinet_providers.dart';
import '../customer/stylist_entry.dart';
import '../service/how_to_buy_screen.dart';
import '../stores/stores_screen.dart';
import '../wishlist/wishlist_controller.dart';
import 'home_providers.dart';
import 'photo_upload_screen.dart';

const double _heroCtaWidth = GlameUi.heroPrimaryButtonWidth;
const double _heroCtaHeight = GlameUi.buttonHeight;
const double _heroCtaGap = 16;
const double _heroIndicatorGap = 34;
const double _homeBlockHorizontalPadding = GlameUi.pagePadding;
const double _newInDropCardHeight = 500;
const double _newInProductGap = 13;
const double _newInLookCardHeight = 330;

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  late final PageController _heroPageController;
  late final PageController _blockPageController;
  Timer? _autoPlayTimer;
  int _currentHeroPage = 0;
  int _autoPlaySlideCount = 0;
  bool _isUserInteractingWithSlider = false;
  static const Duration _autoPlayDelay = Duration(seconds: 5);

  @override
  void initState() {
    super.initState();
    _heroPageController = PageController();
    _blockPageController = PageController();
  }

  @override
  void dispose() {
    _autoPlayTimer?.cancel();
    _heroPageController.dispose();
    _blockPageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final mediaQuery = MediaQuery.of(context);
    final isPagedMobileHome = mediaQuery.size.width < 600;
    final slidesAsync = ref.watch(homeSlidesProvider);
    final newLooksAsync = ref.watch(homeNewLooksProvider);

    final slidesData = slidesAsync.asData?.value;
    final preparedSlides = slidesData != null
        ? _normalizeSlides(slidesData)
        : _fallbackHeroSlides;
    _syncAutoPlay(preparedSlides.length);
    if (_currentHeroPage >= preparedSlides.length &&
        preparedSlides.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        setState(() => _currentHeroPage = preparedSlides.length - 1);
      });
    }

    final shuffledLooks = _normalizeNewInLooks(newLooksAsync.asData?.value);
    final featuredLook = shuffledLooks.isNotEmpty ? shuffledLooks.first : null;
    final dropData = featuredLook != null
        ? _NewInDropData.fromLook(featuredLook)
        : null;
    final productCards =
        featuredLook?.products.toList(growable: false) ??
        const <_NewInProductData>[];

    if (isPagedMobileHome) {
      return LayoutBuilder(
        builder: (context, constraints) {
          final viewportHeight = constraints.maxHeight;
          return PageView(
            controller: _blockPageController,
            scrollDirection: Axis.vertical,
            physics: const PageScrollPhysics(),
            children: [
              _HomeFullScreenSection(
                child: _HomeHeroBlock(
                  slides: preparedSlides,
                  currentPage: _currentHeroPage.clamp(
                    0,
                    preparedSlides.isEmpty ? 0 : preparedSlides.length - 1,
                  ),
                  pageController: _heroPageController,
                  onPageChanged: _handlePageChanged,
                  onInteractionStart: _pauseAutoPlay,
                  onInteractionEnd: _resumeAutoPlay,
                  onPrevious: _goToPreviousSlide,
                  onNext: () =>
                      _goToSlide(_currentHeroPage + 1, preparedSlides.length),
                  onRefresh: null,
                  onOpenAction: _openAction,
                ),
              ),
              _HomeFullScreenSection(
                child: _HomeNewInBlock(
                  drop: dropData,
                  products: productCards,
                  loading: newLooksAsync.isLoading,
                  onOpenAllNew: _openAllNew,
                  onOpenDrop: dropData == null
                      ? null
                      : () => _openNewInDrop(dropData),
                  viewportHeight: viewportHeight,
                ),
              ),
              _HomeFullScreenSection(
                child: _HomePhotoSelectionBlock(
                  onOpenUpload: _openPhotoUpload,
                  onOpenGuide: _openPhotoGuide,
                  viewportHeight: viewportHeight,
                ),
              ),
              _HomeFullScreenSection(
                child: HomeCollectedGlameBlock(
                  onCtaPressed: _openBrands,
                  viewportHeight: viewportHeight,
                ),
              ),
              _HomeFullScreenSection(
                child: HomeSpacesBlock(viewportHeight: viewportHeight),
              ),
              _HomeFullScreenSection(
                child: HomeHowToBuyBlock(viewportHeight: viewportHeight),
              ),
            ],
          );
        },
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final viewportHeight = constraints.maxHeight;
        return RefreshIndicator(
          color: GlameColors.textPrimary,
          onRefresh: _refreshHome,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: EdgeInsets.zero,
            children: [
              SizedBox(
                height: viewportHeight,
                child: _HomeHeroBlock(
                  slides: preparedSlides,
                  currentPage: _currentHeroPage.clamp(
                    0,
                    preparedSlides.isEmpty ? 0 : preparedSlides.length - 1,
                  ),
                  pageController: _heroPageController,
                  onPageChanged: _handlePageChanged,
                  onInteractionStart: _pauseAutoPlay,
                  onInteractionEnd: _resumeAutoPlay,
                  onPrevious: _goToPreviousSlide,
                  onNext: () =>
                      _goToSlide(_currentHeroPage + 1, preparedSlides.length),
                  onRefresh: null,
                  onOpenAction: _openAction,
                ),
              ),
              _HomeNewInBlock(
                drop: dropData,
                products: productCards,
                loading: newLooksAsync.isLoading,
                onOpenAllNew: _openAllNew,
                onOpenDrop: dropData == null
                    ? null
                    : () => _openNewInDrop(dropData),
              ),
              _HomePhotoSelectionBlock(
                onOpenUpload: _openPhotoUpload,
                onOpenGuide: _openPhotoGuide,
              ),
              HomeCollectedGlameBlock(onCtaPressed: _openBrands),
              const HomeSpacesBlock(),
              const HomeHowToBuyBlock(),
            ],
          ),
        );
      },
    );
  }

  Future<void> _refreshHome() async {
    ref.invalidate(homeSlidesProvider);
    ref.invalidate(homePhotoSelectionBlockProvider);
    ref.invalidate(homeNewLooksProvider);
    ref.invalidate(homeCollectedGlameBlockProvider);
    ref.invalidate(homeStoresProvider);
    ref.invalidate(homeHowToBuyBlockProvider);
    await Future.wait(<Future<dynamic>>[
      ref.read(homeSlidesProvider.future),
      ref.read(homePhotoSelectionBlockProvider.future),
      ref.read(homeNewLooksProvider.future),
      ref.read(homeCollectedGlameBlockProvider.future),
      ref.read(homeStoresProvider.future),
      ref.read(homeHowToBuyBlockProvider.future),
    ]);
  }

  void _syncAutoPlay(int slideCount) {
    if (_autoPlaySlideCount == slideCount) return;
    _autoPlaySlideCount = slideCount;
    _scheduleNextAutoPlay();
  }

  void _scheduleNextAutoPlay() {
    _autoPlayTimer?.cancel();
    if (_autoPlaySlideCount <= 1 || _isUserInteractingWithSlider) return;
    _autoPlayTimer = Timer(_autoPlayDelay, () {
      if (!mounted || !_heroPageController.hasClients) return;
      _goToSlide(_currentHeroPage + 1, _autoPlaySlideCount);
    });
  }

  void _pauseAutoPlay() {
    _isUserInteractingWithSlider = true;
    _autoPlayTimer?.cancel();
  }

  void _resumeAutoPlay() {
    _isUserInteractingWithSlider = false;
    _scheduleNextAutoPlay();
  }

  void _handlePageChanged(int value) {
    if (!mounted) return;
    setState(() => _currentHeroPage = value);
    _scheduleNextAutoPlay();
  }

  void _goToPreviousSlide() {
    _goToSlide(_currentHeroPage - 1, _autoPlaySlideCount);
  }

  void _goToSlide(int targetIndex, int slideCount) {
    if (!_heroPageController.hasClients || slideCount <= 1) return;
    final normalizedIndex = targetIndex < 0
        ? slideCount - 1
        : targetIndex % slideCount;
    _heroPageController.animateToPage(
      normalizedIndex,
      duration: const Duration(milliseconds: 360),
      curve: Curves.easeOutCubic,
    );
  }

  Future<void> _openAllNew() async {
    if (!mounted) return;
    context.go('/home?tab=5&lookFilter=${Uri.encodeComponent('Новинка')}');
  }

  Future<void> _openNewInDrop(_NewInDropData drop) async {
    if (!mounted) return;
    if (drop.lookId.isNotEmpty) {
      context.push('/look/${drop.lookId}');
      return;
    }
    context.go('/home?tab=5&lookFilter=${Uri.encodeComponent('Новинка')}');
  }

  Future<void> _openPhotoUpload() async {
    if (!mounted) return;
    await startPhotoSelectionFlow(context);
  }

  Future<void> _openPhotoGuide() async {
    if (!mounted) return;
    await showPhotoGuideSheet(
      context,
      primaryLabel: 'Выбрать или сделать фото',
      onPrimaryTap: () => startPhotoSelectionFlow(context),
    );
  }

  void _openBrands() {
    if (!mounted) return;
    context.push('/brands');
  }

  Future<void> _openAction(_HomeSlideAction? action) async {
    if (action == null) return;
    final type = (action.type ?? '').trim().toLowerCase();
    final payload = action.payload ?? const <String, dynamic>{};
    if (type == 'catalog') {
      final query = <String, String>{};
      for (final entry in payload.entries) {
        final key = entry.key.trim();
        final value = '${entry.value ?? ''}'.trim();
        if (key.isEmpty || value.isEmpty) continue;
        query[key] = value;
      }
      if (!mounted) return;
      context.push(Uri(path: '/catalog', queryParameters: query).toString());
      return;
    }
    if (type == 'selection') {
      final mode = _firstNotEmpty(<Object?>[
        payload['mode'],
        payload['variant'],
      ]);
      if (!mounted) return;
      if (mode == 'gift') {
        context.push('/selection/gift');
        return;
      }
      context.push('/selection');
      return;
    }
    if (type == 'looks') {
      final filter = _firstNotEmpty(<Object?>[
        payload['filter'],
        payload['mood'],
        payload['style'],
        payload['collection'],
        payload['radical'],
      ]);
      final query = <String, String>{'tab': '5'};
      if (filter != null) {
        query['lookFilter'] = filter;
      }
      if (!mounted) return;
      context.go(Uri(path: '/home', queryParameters: query).toString());
      return;
    }
    if (type == 'stylist') {
      if (!mounted) return;
      final statusPayload = await _loadStylistStatus();
      if (!mounted) return;
      await showStylistContactSheet(
        context,
        source: 'hero_slide_07',
        scenario: 'live_stylist',
        statusPayload: statusPayload,
      );
      return;
    }
    final urlFromPayload = _firstNotEmpty(<Object?>[
      payload['url'],
      payload['link'],
      action.legacyLink,
    ]);
    await _openLink(urlFromPayload);
  }

  Future<void> _openLink(String? link) async {
    final target = (link ?? '').trim();
    if (target.isEmpty) return;
    if (target.startsWith('http://') || target.startsWith('https://')) {
      final uri = Uri.tryParse(target);
      if (uri != null) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      }
      return;
    }
    if (!mounted) return;
    if (target.startsWith('/home')) {
      context.go(target);
      return;
    }
    if (target.startsWith('/')) {
      context.push(target);
    }
  }

  Future<Map<String, dynamic>?> _loadStylistStatus() async {
    try {
      return await ref.read(customerCabinetApiProvider).getStylistChatStatus();
    } catch (_) {
      return null;
    }
  }

  List<_HomeSlideData> _normalizeSlides(List<dynamic> items) {
    final slides = <_HomeSlideData>[];
    for (final raw in items) {
      if (raw is! Map) continue;
      final imageUrl = resolveAssetUrl(raw['image_url']);
      final backgroundImageUrl = resolveAssetUrl(raw['background_image_url']);
      var slide = _HomeSlideData(
        title: _stringValue(raw['title']),
        subtitle: _stringValue(raw['subtitle']),
        backgroundImageUrl: backgroundImageUrl,
        imageUrl: imageUrl,
        imageAction: _parseAction(
          raw,
          typeKey: 'image_action_type',
          payloadKey: 'image_action_payload',
          legacyLinkKey: 'image_action_link',
          requireText: false,
        ),
        primaryButtonText: _stringValue(raw['primary_button_text']),
        primaryAction: _parseAction(
          raw,
          textKey: 'primary_button_text',
          typeKey: 'primary_button_action_type',
          payloadKey: 'primary_button_action_payload',
          legacyLinkKey: 'primary_button_link',
        ),
        secondaryButtonText: _stringValue(raw['secondary_button_text']),
        secondaryAction: _parseAction(
          raw,
          textKey: 'secondary_button_text',
          typeKey: 'secondary_button_action_type',
          payloadKey: 'secondary_button_action_payload',
          legacyLinkKey: 'secondary_button_link',
        ),
      );
      slides.add(_applyHeroSpec(slide, slides.length));
    }
    return slides.isEmpty ? _fallbackHeroSlides : slides;
  }

  _HomeSlideData _applyHeroSpec(_HomeSlideData slide, int index) {
    if (index < 0 || index >= _fallbackHeroSlides.length) return slide;
    final spec = _fallbackHeroSlides[index];
    return _HomeSlideData(
      title: spec.title,
      subtitle: spec.subtitle,
      backgroundImageUrl: slide.backgroundImageUrl,
      imageUrl: slide.imageUrl,
      imageAction: slide.imageAction ?? spec.imageAction,
      primaryButtonText: spec.primaryButtonText,
      primaryAction: spec.primaryAction,
      secondaryButtonText: spec.secondaryButtonText,
      secondaryAction: spec.secondaryAction,
    );
  }

  String? _stringValue(Object? value) {
    final text = (value as String? ?? '').trim();
    return text.isEmpty ? null : text;
  }

  _HomeSlideAction? _parseAction(
    Map raw, {
    String? textKey,
    required String typeKey,
    required String payloadKey,
    required String legacyLinkKey,
    bool requireText = true,
  }) {
    if (requireText && textKey != null && _stringValue(raw[textKey]) == null) {
      return null;
    }
    final type = _stringValue(raw[typeKey]);
    final payloadRaw = raw[payloadKey];
    final payload = payloadRaw is Map
        ? Map<String, dynamic>.from(payloadRaw)
        : null;
    final legacyLink = _stringValue(raw[legacyLinkKey]);
    if (type == null && payload == null && legacyLink == null) {
      return null;
    }
    return _HomeSlideAction(
      type: type,
      payload: payload,
      legacyLink: legacyLink,
    );
  }

  String? _firstNotEmpty(List<Object?> values) {
    for (final value in values) {
      final text = '${value ?? ''}'.trim();
      if (text.isNotEmpty) return text;
    }
    return null;
  }

  List<_NewInLookData> _normalizeNewInLooks(List<dynamic>? items) {
    final looks = <_NewInLookData>[];
    for (final raw in items ?? const <dynamic>[]) {
      if (raw is! Map) continue;
      final id = _stringValue(raw['id']) ?? '';
      if (id.isEmpty) continue;
      final imageUrl = _resolveLookImage(raw);
      looks.add(
        _NewInLookData(
          id: id,
          title: _stringValue(raw['name']) ?? 'Новый образ',
          description:
              _stringValue(raw['description']) ??
              'Кураторский новый образ GLAME.',
          imageUrl: imageUrl,
          tag: _newLookTag(raw),
          products: _normalizeLookProducts(
            raw['products'],
            raw['product_layout'],
          ),
        ),
      );
    }
    return looks;
  }

  String? _resolveLookImage(Map raw) {
    final imageUrls = raw['image_urls'];
    if (imageUrls is List && imageUrls.isNotEmpty) {
      final currentIndex = raw['current_image_index'];
      final preferredIndex = currentIndex is int ? currentIndex : 0;
      if (preferredIndex >= 0 && preferredIndex < imageUrls.length) {
        final preferred = imageUrls[preferredIndex];
        if (preferred is Map) {
          final url = resolveAssetUrl(preferred['url']);
          if (url != null && url.isNotEmpty) return url;
        } else {
          final url = resolveAssetUrl(preferred);
          if (url != null && url.isNotEmpty) return url;
        }
      }
      for (final item in imageUrls) {
        if (item is Map) {
          final url = resolveAssetUrl(item['url']);
          if (url != null && url.isNotEmpty) return url;
        } else {
          final url = resolveAssetUrl(item);
          if (url != null && url.isNotEmpty) return url;
        }
      }
    }
    final mediaItems = raw['media_items'];
    if (mediaItems is List) {
      for (final item in mediaItems) {
        if (item is! Map) continue;
        final url =
            resolveAssetUrl(item['thumbnail_url']) ??
            resolveAssetUrl(item['url']);
        if (url != null && url.isNotEmpty) return url;
      }
    }
    return resolveAssetUrl(raw['image_url']);
  }

  String _newLookTag(Map raw) {
    if (raw['is_new'] == true) return 'НОВИНКА';
    return (_stringValue(raw['style']) ?? _stringValue(raw['mood']) ?? 'ОБРАЗ')
        .toUpperCase();
  }

  List<_NewInProductData> _normalizeLookProducts(
    Object? rawProducts,
    Object? rawProductLayout,
  ) {
    final result = <_NewInProductData>[];
    if (rawProducts is! List) return result;

    final layoutOrder = <String, int>{};
    if (rawProductLayout is List) {
      for (var index = 0; index < rawProductLayout.length; index++) {
        final item = rawProductLayout[index];
        if (item is! Map) continue;
        final productId = _stringValue(item['product_id']);
        if (productId == null) continue;
        final position = item['position'];
        final normalizedPosition = position is num
            ? position.toInt()
            : index + 1;
        layoutOrder[productId] = normalizedPosition;
      }
    }

    final normalizedProducts = rawProducts
        .whereType<Map>()
        .map((raw) => Map<String, dynamic>.from(raw))
        .toList(growable: false);

    normalizedProducts.sort((a, b) {
      final aId = _stringValue(a['id']) ?? '';
      final bId = _stringValue(b['id']) ?? '';
      final aOrder = layoutOrder[aId] ?? 9999;
      final bOrder = layoutOrder[bId] ?? 9999;
      return aOrder.compareTo(bOrder);
    });

    for (final raw in normalizedProducts) {
      final id = _stringValue(raw['id']) ?? '';
      final imageUrl = _resolveProductImage(raw);
      result.add(
        _NewInProductData(
          id: id,
          brand:
              (_stringValue(raw['brand']) ??
                      _stringValue(raw['category']) ??
                      'GLAME')
                  .toUpperCase(),
          name: _stringValue(raw['name']) ?? 'Украшение',
          availability: _buildAvailabilityLabel(raw),
          imageUrl: imageUrl,
          priceLabel: _buildProductPriceLabel(raw),
        ),
      );
    }
    return result;
  }

  String? _resolveProductImage(Map raw) {
    final images = raw['images'];
    if (images is List) {
      for (final item in images) {
        final url = resolveAssetUrl(item);
        if (url != null && url.isNotEmpty) return url;
      }
    }
    return resolveAssetUrl(raw['image_url']);
  }

  String _buildAvailabilityLabel(Map raw) {
    final city = _stringValue(raw['city']) ?? _stringValue(raw['store_city']);
    if (city != null) {
      return 'В $city · доставка по России';
    }
    final stock = raw['stock'];
    if (stock is num && stock > 0) {
      return 'В наличии · доставка по России';
    }
    return 'Можно забронировать';
  }

  String? _buildProductPriceLabel(Map raw) {
    final formatted = formatRubFromKopeks(raw['price']);
    if (formatted.isEmpty) return null;
    return formatted;
  }
}

class _HomeFullScreenSection extends StatelessWidget {
  final Widget child;

  const _HomeFullScreenSection({required this.child});

  @override
  Widget build(BuildContext context) {
    return SizedBox.expand(child: child);
  }
}

class _HomeHeroBlock extends StatelessWidget {
  final List<_HomeSlideData> slides;
  final int currentPage;
  final PageController pageController;
  final ValueChanged<int> onPageChanged;
  final VoidCallback onInteractionStart;
  final VoidCallback onInteractionEnd;
  final VoidCallback? onPrevious;
  final VoidCallback? onNext;
  final Future<void> Function()? onRefresh;
  final Future<void> Function(_HomeSlideAction? action) onOpenAction;

  const _HomeHeroBlock({
    required this.slides,
    required this.currentPage,
    required this.pageController,
    required this.onPageChanged,
    required this.onInteractionStart,
    required this.onInteractionEnd,
    required this.onPrevious,
    required this.onNext,
    this.onRefresh,
    required this.onOpenAction,
  });

  @override
  Widget build(BuildContext context) {
    final mediaQuery = MediaQuery.of(context);
    final isCompactMobile = mediaQuery.size.width < 600;
    final effectiveSlides = slides.isEmpty ? _fallbackHeroSlides : slides;
    final safeCurrentPage = currentPage.clamp(0, effectiveSlides.length - 1);
    final currentSlide = effectiveSlides[safeCurrentPage];
    final isDesktop = MediaQuery.of(context).size.width >= 900;
    final content = Stack(
      children: [
        Positioned.fill(
          child: Listener(
            onPointerDown: (_) => onInteractionStart(),
            onPointerUp: (_) => onInteractionEnd(),
            onPointerCancel: (_) => onInteractionEnd(),
            child: PageView.builder(
              controller: pageController,
              onPageChanged: onPageChanged,
              itemCount: effectiveSlides.length,
              itemBuilder: (context, index) {
                final slide = effectiveSlides[index];
                return GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: slide.imageAction == null
                      ? null
                      : () => onOpenAction(slide.imageAction),
                  child: _HeroBackground(
                    backgroundImageUrl: slide.backgroundImageUrl,
                    imageUrl: slide.imageUrl,
                  ),
                );
              },
            ),
          ),
        ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.transparent,
                  GlameColors.textPrimary.withValues(alpha: 0.1),
                  GlameColors.textPrimary.withValues(alpha: 0.48),
                  GlameColors.textPrimary.withValues(alpha: 0.68),
                ],
                stops: const [0, 0.52, 0.8, 1],
              ),
            ),
          ),
        ),
        if (isDesktop && effectiveSlides.length > 1) ...[
          Positioned(
            left: 28,
            top: 0,
            bottom: 0,
            child: Center(
              child: _HeroArrowButton(
                icon: Icons.chevron_left,
                onTap: onPrevious,
              ),
            ),
          ),
          Positioned(
            right: 28,
            top: 0,
            bottom: 0,
            child: Center(
              child: _HeroArrowButton(icon: Icons.chevron_right, onTap: onNext),
            ),
          ),
        ],
        Positioned.fill(
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            onHorizontalDragStart: (_) => onInteractionStart(),
            onHorizontalDragEnd: (details) {
              final velocity = details.primaryVelocity ?? 0;
              if (velocity > 120) {
                onPrevious?.call();
              } else if (velocity < -120) {
                onNext?.call();
              }
              onInteractionEnd();
            },
            onHorizontalDragCancel: onInteractionEnd,
            child: isCompactMobile
                ? _HeroFixedMobileOverlay(
                    slide: currentSlide,
                    currentIndex: safeCurrentPage,
                    total: effectiveSlides.length,
                    onOpenAction: onOpenAction,
                  )
                : SafeArea(
                    bottom: false,
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(28, 24, 28, 42),
                      child: Column(
                        children: [
                          const Spacer(),
                          SizedBox(
                            height: 292,
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Expanded(
                                  child: _HeroLeftColumn(
                                    slide: currentSlide,
                                    onOpenAction: onOpenAction,
                                  ),
                                ),
                                const SizedBox(width: _heroIndicatorGap),
                                SizedBox(
                                  width: 148,
                                  child: Align(
                                    alignment: Alignment.bottomRight,
                                    child: _SlideIndicator(
                                      currentIndex: safeCurrentPage,
                                      total: effectiveSlides.length,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
          ),
        ),
      ],
    );

    if (onRefresh == null) return content;

    return RefreshIndicator(
      color: GlameColors.textPrimary,
      onRefresh: onRefresh!,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.zero,
        children: [
          SizedBox(height: MediaQuery.of(context).size.height, child: content),
        ],
      ),
    );
  }
}

class _HeroBackground extends StatelessWidget {
  final String? backgroundImageUrl;
  final String? imageUrl;

  const _HeroBackground({
    required this.backgroundImageUrl,
    required this.imageUrl,
  });

  @override
  Widget build(BuildContext context) {
    final hasBackground =
        backgroundImageUrl != null && backgroundImageUrl!.isNotEmpty;
    final hasImage = imageUrl != null && imageUrl!.isNotEmpty;
    if (!hasBackground && !hasImage) {
      return Container(
        color: GlameColors.coolLightGray,
        alignment: Alignment.center,
        child: Image.asset(
          GlameAssets.logoGraph,
          height: 72,
          fit: BoxFit.contain,
        ),
      );
    }

    return Stack(
      fit: StackFit.expand,
      children: [
        if (hasBackground)
          CachedNetworkImage(
            imageUrl: backgroundImageUrl!,
            fit: BoxFit.cover,
            placeholder: (_, _) => Container(color: GlameColors.coolLightGray),
            errorWidget: (_, _, _) =>
                Container(color: GlameColors.coolLightGray),
          )
        else
          Container(color: GlameColors.coolLightGray),
        if (hasImage)
          CachedNetworkImage(
            imageUrl: imageUrl!,
            fit: BoxFit.cover,
            placeholder: (_, _) => const SizedBox.shrink(),
            errorWidget: (_, _, _) => const SizedBox.shrink(),
          ),
      ],
    );
  }
}

class _GlameHeroButton extends StatelessWidget {
  final String title;
  final bool filled;
  final VoidCallback onTap;
  final double? width;

  const _GlameHeroButton({
    required this.title,
    required this.filled,
    required this.onTap,
    this.width,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: _heroCtaHeight,
      width: width ?? _heroCtaWidth,
      child: Material(
        color: filled ? GlameColors.surface2 : Colors.transparent,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.zero,
          side: BorderSide(color: GlameColors.surface2, width: 1),
        ),
        child: InkWell(
          onTap: onTap,
          child: Center(
            child: Text(
              title,
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w400,
                height: 1.05,
                letterSpacing: 0.1,
                color: filled ? GlameColors.textPrimary : GlameColors.surface2,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _HeroArrowButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onTap;

  const _HeroArrowButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: GlameColors.surface2.withValues(alpha: 0.14),
      shape: const RoundedRectangleBorder(),
      child: InkWell(
        onTap: onTap,
        customBorder: const RoundedRectangleBorder(),
        child: SizedBox(
          width: 56,
          height: 56,
          child: Icon(icon, color: GlameColors.surface2, size: 34),
        ),
      ),
    );
  }
}

class _SlideIndicator extends StatelessWidget {
  final int currentIndex;
  final int total;
  final bool compact;

  const _SlideIndicator({
    required this.currentIndex,
    required this.total,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    final displayTotal = total <= 0 ? 1 : total;
    final displayIndex = (currentIndex + 1).clamp(1, displayTotal);
    final barWidth = compact ? 64.0 : 88.0;
    final progressWidth = total <= 1
        ? barWidth
        : barWidth * (displayIndex / displayTotal);

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text(
          '${displayIndex.toString().padLeft(2, '0')} / ${displayTotal.toString().padLeft(2, '0')}',
          style: TextStyle(
            fontSize: compact ? 18 : 24,
            color: GlameColors.surface2,
            letterSpacing: 0.4,
          ),
        ),
        SizedBox(height: compact ? 10 : 16),
        SizedBox(
          width: barWidth,
          height: 2,
          child: Stack(
            children: [
              Positioned.fill(
                child: Container(
                  color: GlameColors.surface2.withValues(alpha: 0.32),
                ),
              ),
              Align(
                alignment: Alignment.centerLeft,
                child: Container(
                  width: progressWidth,
                  height: 2,
                  color: GlameColors.surface2,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _HeroFixedMobileOverlay extends StatelessWidget {
  final _HomeSlideData slide;
  final int currentIndex;
  final int total;
  final Future<void> Function(_HomeSlideAction? action) onOpenAction;

  const _HeroFixedMobileOverlay({
    required this.slide,
    required this.currentIndex,
    required this.total,
    required this.onOpenAction,
  });

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    final buttonWidth = (width - GlameUi.pagePadding * 2).clamp(
      220.0,
      _heroCtaWidth,
    );
    final topSafe = MediaQuery.of(context).padding.top;
    final textTop =
        topSafe + GlameUi.heroTopOffset + GlameUi.heroTopBarHeight + 42;
    final textBottom = GlameUi.heroPrimaryButtonY - 24;

    return LayoutBuilder(
      builder: (context, constraints) {
        final bottomInset = (constraints.maxHeight - textBottom).clamp(
          0.0,
          constraints.maxHeight,
        );
        return Stack(
          children: [
            Positioned(
              left: GlameUi.pagePadding,
              right: GlameUi.pagePadding,
              top: textTop,
              bottom: bottomInset,
              child: Align(
                alignment: Alignment.bottomLeft,
                child: _HeroTextBlock(slide: slide, compact: true),
              ),
            ),
            if ((slide.primaryButtonText ?? '').isNotEmpty)
              Positioned(
                left: GlameUi.pagePadding,
                top: GlameUi.heroPrimaryButtonY,
                width: buttonWidth,
                height: _heroCtaHeight,
                child: _GlameHeroButton(
                  title: slide.primaryButtonText!,
                  filled: true,
                  onTap: () => onOpenAction(slide.primaryAction),
                  width: buttonWidth,
                ),
              ),
            if ((slide.secondaryButtonText ?? '').isNotEmpty)
              Positioned(
                left: GlameUi.pagePadding,
                top: GlameUi.heroSecondaryButtonY,
                width: buttonWidth,
                height: _heroCtaHeight,
                child: _GlameHeroButton(
                  title: slide.secondaryButtonText!,
                  filled: false,
                  onTap: () => onOpenAction(slide.secondaryAction),
                  width: buttonWidth,
                ),
              ),
            Positioned(
              left: GlameUi.pagePadding,
              top: GlameUi.heroSlideIndicatorY,
              child: _SlideIndicator(
                currentIndex: currentIndex,
                total: total,
                compact: true,
              ),
            ),
          ],
        );
      },
    );
  }
}

class _HeroTextBlock extends StatelessWidget {
  final _HomeSlideData slide;
  final bool compact;

  const _HeroTextBlock({required this.slide, this.compact = false});

  @override
  Widget build(BuildContext context) {
    final hasTitle = (slide.title ?? '').isNotEmpty;
    final hasSubtitle = (slide.subtitle ?? '').isNotEmpty;

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (hasTitle)
          Text(
            slide.title!,
            style: TextStyle(
              fontSize: compact ? 34 : 42,
              height: 1.04,
              fontWeight: FontWeight.w400,
              color: GlameColors.surface2,
              letterSpacing: 0.2,
            ),
          ),
        if (hasSubtitle && hasTitle) SizedBox(height: compact ? 10 : 12),
        if (hasSubtitle)
          Text(
            slide.subtitle!,
            style: TextStyle(
              fontSize: compact ? 18 : 17,
              height: compact ? 1.38 : 1.38,
              fontWeight: FontWeight.w400,
              color: GlameColors.surface2,
              letterSpacing: 0.1,
            ),
          ),
      ],
    );
  }
}

class _HeroLeftColumn extends StatelessWidget {
  final _HomeSlideData slide;
  final Future<void> Function(_HomeSlideAction? action) onOpenAction;

  const _HeroLeftColumn({required this.slide, required this.onOpenAction});

  @override
  Widget build(BuildContext context) {
    final hasTitle = (slide.title ?? '').isNotEmpty;
    final hasSubtitle = (slide.subtitle ?? '').isNotEmpty;
    final hasPrimary = (slide.primaryButtonText ?? '').isNotEmpty;
    final hasSecondary = (slide.secondaryButtonText ?? '').isNotEmpty;

    return Column(
      mainAxisAlignment: MainAxisAlignment.end,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _HeroTextBlock(slide: slide),
        if (hasPrimary || hasSecondary)
          SizedBox(height: hasTitle || hasSubtitle ? 22 : 0),
        if (hasPrimary)
          SizedBox(
            width: _heroCtaWidth,
            child: _GlameHeroButton(
              title: slide.primaryButtonText!,
              filled: true,
              onTap: () => onOpenAction(slide.primaryAction),
            ),
          ),
        if (hasPrimary && hasSecondary) const SizedBox(height: _heroCtaGap),
        if (hasSecondary)
          SizedBox(
            width: _heroCtaWidth,
            child: _GlameHeroButton(
              title: slide.secondaryButtonText!,
              filled: false,
              onTap: () => onOpenAction(slide.secondaryAction),
            ),
          ),
      ],
    );
  }
}

class _HomeNewInBlock extends ConsumerWidget {
  final _NewInDropData? drop;
  final List<_NewInProductData> products;
  final bool loading;
  final Future<void> Function() onOpenAllNew;
  final Future<void> Function()? onOpenDrop;
  final double? viewportHeight;

  const _HomeNewInBlock({
    required this.drop,
    required this.products,
    required this.loading,
    required this.onOpenAllNew,
    required this.onOpenDrop,
    this.viewportHeight,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = products.isEmpty
        ? List<_NewInProductData>.generate(
            3,
            (index) => _NewInProductData.placeholder(index),
          )
        : products;
    final isPagedLayout = viewportHeight != null;
    final blockHeight = viewportHeight ?? MediaQuery.of(context).size.height;
    final compact = isPagedLayout;
    final topPadding = compact ? 64.0 : 36.0;
    final bottomPadding = compact ? 8.0 : 36.0;
    final titleSize = compact ? 30.0 : 36.0;
    final linkSize = compact ? 16.0 : 19.0;
    final bodySize = compact ? 15.0 : 18.0;
    final dropHeight = compact
        ? (blockHeight * 0.34).clamp(220.0, 300.0)
        : _newInDropCardHeight;
    final productCardHeight = compact
        ? (blockHeight * 0.2).clamp(145.0, 190.0)
        : _newInLookCardHeight;

    return Container(
      color: GlameColors.surface2,
      padding: EdgeInsets.fromLTRB(
        _homeBlockHorizontalPadding,
        topPadding,
        _homeBlockHorizontalPadding,
        bottomPadding,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  'Новое в GLAME',
                  style: TextStyle(
                    fontSize: titleSize,
                    fontWeight: FontWeight.w400,
                    color: GlameColors.textPrimary,
                    height: 1.02,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              InkWell(
                onTap: () => onOpenAllNew(),
                child: Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(
                    'Все новинки',
                    style: TextStyle(
                      fontSize: linkSize,
                      fontWeight: FontWeight.w400,
                      color: GlameColors.textPrimary,
                      decoration: TextDecoration.underline,
                      decorationColor: GlameColors.textPrimary,
                    ),
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: compact ? 12 : 18),
          SizedBox(
            width: 310,
            child: Text(
              'Кураторские поступления: онлайн, в бутике или с доставкой по России.',
              style: TextStyle(
                fontSize: bodySize,
                height: 1.4,
                color: GlameColors.textSecondary,
              ),
            ),
          ),
          SizedBox(height: compact ? 16 : 36),
          if (compact)
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final availableHeight = constraints.maxHeight;
                  final hasScrollHint = items.length > 3;
                  final hintHeight = hasScrollHint ? 24.0 : 0.0;
                  final verticalGap = 12.0;
                  final rowGap = hasScrollHint ? 10.0 : 0.0;
                  final preferredProductHeight = (availableHeight * 0.35).clamp(
                    184.0,
                    240.0,
                  );
                  final dynamicDropHeight =
                      (availableHeight -
                              preferredProductHeight -
                              verticalGap -
                              rowGap -
                              hintHeight)
                          .clamp(220.0, 320.0);
                  final dynamicProductHeight =
                      (availableHeight -
                              dynamicDropHeight -
                              verticalGap -
                              rowGap -
                              hintHeight)
                          .clamp(184.0, 240.0);

                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _NewInDropCard(
                        drop: drop,
                        loading: loading,
                        onOpen: onOpenDrop,
                        height: dynamicDropHeight,
                        compact: compact,
                      ),
                      SizedBox(height: verticalGap),
                      if (hasScrollHint)
                        const Padding(
                          padding: EdgeInsets.only(bottom: 10),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.end,
                            children: [
                              Text(
                                'Листайте',
                                style: TextStyle(
                                  fontSize: 12,
                                  letterSpacing: 0.6,
                                  color: GlameColors.textSecondary,
                                ),
                              ),
                              SizedBox(width: 6),
                              Icon(
                                Icons.arrow_forward_rounded,
                                size: 16,
                                color: GlameColors.textSecondary,
                              ),
                            ],
                          ),
                        ),
                      _NewInProductCardsRow(
                        items: items,
                        height: dynamicProductHeight,
                        compact: compact,
                      ),
                    ],
                  );
                },
              ),
            )
          else ...[
            _NewInDropCard(
              drop: drop,
              loading: loading,
              onOpen: onOpenDrop,
              height: dropHeight,
              compact: compact,
            ),
            SizedBox(height: compact ? 14 : 26),
            if (items.length > 3)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: const [
                    Text(
                      'Листайте',
                      style: TextStyle(
                        fontSize: 12,
                        letterSpacing: 0.6,
                        color: GlameColors.textSecondary,
                      ),
                    ),
                    SizedBox(width: 6),
                    Icon(
                      Icons.arrow_forward_rounded,
                      size: 16,
                      color: GlameColors.textSecondary,
                    ),
                  ],
                ),
              ),
            _NewInProductCardsRow(
              items: items,
              height: productCardHeight,
              compact: compact,
            ),
          ],
        ],
      ),
    );
  }
}

class _NewInProductCardsRow extends StatelessWidget {
  final List<_NewInProductData> items;
  final double height;
  final bool compact;

  const _NewInProductCardsRow({
    required this.items,
    required this.height,
    required this.compact,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final cardWidth = (constraints.maxWidth - (_newInProductGap * 2)) / 3;
        if (items.length <= 3) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (var index = 0; index < items.length; index++) ...[
                Expanded(
                  child: _NewInProductCard(
                    product: items[index],
                    height: height,
                    compact: compact,
                  ),
                ),
                if (index != items.length - 1)
                  const SizedBox(width: _newInProductGap),
              ],
            ],
          );
        }

        return Stack(
          children: [
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              physics: const BouncingScrollPhysics(),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (var index = 0; index < items.length; index++) ...[
                    SizedBox(
                      width: cardWidth,
                      child: _NewInProductCard(
                        product: items[index],
                        height: height,
                        compact: compact,
                      ),
                    ),
                    if (index != items.length - 1)
                      const SizedBox(width: _newInProductGap),
                  ],
                ],
              ),
            ),
            Positioned(
              top: 0,
              right: 0,
              bottom: 0,
              child: IgnorePointer(
                child: Container(
                  width: 28,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.centerLeft,
                      end: Alignment.centerRight,
                      colors: [
                        GlameColors.surface2.withValues(alpha: 0),
                        GlameColors.surface2,
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _HomePhotoSelectionBlock extends ConsumerWidget {
  final Future<void> Function() onOpenUpload;
  final Future<void> Function() onOpenGuide;
  final double? viewportHeight;

  const _HomePhotoSelectionBlock({
    required this.onOpenUpload,
    required this.onOpenGuide,
    this.viewportHeight,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final photoSelectionBlock = ref
        .watch(homePhotoSelectionBlockProvider)
        .asData
        ?.value;
    final promoImageUrl = resolveAssetUrl(photoSelectionBlock?['image_url']);
    final adminTitle = '${photoSelectionBlock?['title'] ?? ''}'.trim();
    final adminSubtitle = '${photoSelectionBlock?['subtitle'] ?? ''}'.trim();
    final hasAdminTitle = adminTitle.isNotEmpty;
    final hasAdminSubtitle = adminSubtitle.isNotEmpty;
    final compact = viewportHeight != null;
    final topPadding = compact ? 88.0 : 0.0;
    final bottomPadding = compact ? 18.0 : 36.0;
    final titleSize = compact ? 30.0 : 36.0;
    final bodySize = compact ? 15.0 : 18.0;
    const promoHeight = 640.0;

    if (compact) {
      final backgroundSource =
          (promoImageUrl != null && promoImageUrl.isNotEmpty)
          ? promoImageUrl
          : 'assets/images/home/home_block_3_photo_selection.png';
      return Container(
        color: GlameColors.surface2,
        padding: EdgeInsets.fromLTRB(10, 0, 10, bottomPadding),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: Stack(
                fit: StackFit.expand,
                children: [
                  _HomePhotoSelectionBackground(source: backgroundSource),
                  Positioned.fill(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [
                            Colors.black.withValues(alpha: 0.22),
                            Colors.transparent,
                            Colors.black.withValues(alpha: 0.2),
                          ],
                          stops: const [0.0, 0.42, 1.0],
                        ),
                      ),
                    ),
                  ),
                  Padding(
                    padding: EdgeInsets.fromLTRB(26, topPadding + 8, 26, 28),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (hasAdminTitle)
                          Text(
                            adminTitle,
                            style: const TextStyle(
                              fontSize: 32,
                              fontWeight: FontWeight.w400,
                              height: 1.02,
                              color: GlameColors.surface2,
                            ),
                          ),
                        if (hasAdminTitle && hasAdminSubtitle)
                          const SizedBox(height: 18),
                        if (hasAdminSubtitle)
                          SizedBox(
                            width: 188,
                            child: Text(
                              adminSubtitle,
                              style: TextStyle(
                                fontSize: bodySize - 1,
                                height: 1.55,
                                color: GlameColors.surface2.withValues(
                                  alpha: 0.92,
                                ),
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            const PhotoSelectionInfoCard(compact: true),
            const SizedBox(height: 10),
            _HomePhotoActionButton(
              title: 'Загрузить фото',
              icon: Icons.photo_camera_outlined,
              filled: true,
              onTap: onOpenUpload,
              compact: true,
            ),
            const SizedBox(height: 8),
            _HomePhotoActionButton(
              title: 'Какое фото подойдет',
              icon: Icons.image_outlined,
              filled: false,
              onTap: onOpenGuide,
              compact: true,
            ),
          ],
        ),
      );
    }

    return Container(
      color: GlameColors.surface2,
      padding: EdgeInsets.fromLTRB(
        _homeBlockHorizontalPadding,
        topPadding,
        _homeBlockHorizontalPadding,
        bottomPadding,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (hasAdminTitle)
            Text(
              adminTitle,
              style: TextStyle(
                fontSize: titleSize,
                fontWeight: FontWeight.w400,
                height: 1.02,
                color: GlameColors.textPrimary,
              ),
            ),
          if (hasAdminTitle && hasAdminSubtitle)
            SizedBox(height: compact ? 14 : 18),
          if (hasAdminSubtitle)
            SizedBox(
              width: 310,
              child: Text(
                adminSubtitle,
                style: TextStyle(
                  fontSize: bodySize,
                  height: 1.42,
                  color: GlameColors.textSecondary,
                ),
              ),
            ),
          if (hasAdminTitle || hasAdminSubtitle)
            SizedBox(height: compact ? 18 : 28),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      return PhotoSelectionPromoCard(
                        height: compact ? constraints.maxHeight : promoHeight,
                        title: adminTitle,
                        description: adminSubtitle,
                        imageUrl: promoImageUrl,
                        imageAspectRatio: 2 / 3,
                        useFixedHeightWhenImage: compact,
                        imageAssetPath:
                            'assets/images/home/home_block_3_photo_selection.png',
                      );
                    },
                  ),
                ),
                SizedBox(height: compact ? 10 : 16),
                PhotoSelectionInfoCard(compact: compact),
                SizedBox(height: compact ? 10 : 16),
                _HomePhotoActionButton(
                  title: 'Загрузить фото',
                  icon: Icons.photo_camera_outlined,
                  filled: true,
                  onTap: onOpenUpload,
                  compact: compact,
                ),
                SizedBox(height: compact ? 8 : 14),
                _HomePhotoActionButton(
                  title: 'Какое фото подойдет',
                  icon: Icons.image_outlined,
                  filled: false,
                  onTap: onOpenGuide,
                  compact: compact,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HomePhotoSelectionBackground extends StatelessWidget {
  final String source;

  const _HomePhotoSelectionBackground({required this.source});

  @override
  Widget build(BuildContext context) {
    if (source.startsWith('http://') || source.startsWith('https://')) {
      return CachedNetworkImage(
        imageUrl: source,
        fit: BoxFit.cover,
        alignment: Alignment.topCenter,
        placeholder: (_, _) => Container(color: const Color(0xFF111214)),
        errorWidget: (_, _, _) => Container(color: const Color(0xFF111214)),
      );
    }
    return Image.asset(
      source,
      fit: BoxFit.cover,
      alignment: Alignment.topCenter,
    );
  }
}

class _HomePhotoActionButton extends StatelessWidget {
  final String title;
  final IconData icon;
  final bool filled;
  final Future<void> Function() onTap;
  final bool compact;

  const _HomePhotoActionButton({
    required this.title,
    required this.icon,
    required this.filled,
    required this.onTap,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    final child = Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(
          icon,
          size: compact ? 18 : 22,
          color: filled ? GlameColors.surface2 : GlameColors.textPrimary,
        ),
        SizedBox(width: compact ? 10 : 12),
        Text(
          title,
          style: TextStyle(
            fontSize: compact ? 15 : 20,
            height: 1.05,
            fontWeight: FontWeight.w400,
            color: filled ? GlameColors.surface2 : GlameColors.textPrimary,
          ),
        ),
      ],
    );
    return SizedBox(
      height: compact ? 44 : 58,
      child: filled
          ? Material(
              color: Colors.transparent,
              child: Ink(
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.centerLeft,
                    end: Alignment.centerRight,
                    colors: [
                      Color(0xFF202020),
                      Color(0xFF0F0F10),
                      Color(0xFF262626),
                    ],
                  ),
                ),
                child: InkWell(onTap: onTap, child: child),
              ),
            )
          : OutlinedButton(
              onPressed: onTap,
              style: OutlinedButton.styleFrom(
                side: const BorderSide(color: Color(0xFFD6D6D6)),
              ),
              child: child,
            ),
    );
  }
}

class _NewInDropCard extends StatelessWidget {
  final _NewInDropData? drop;
  final bool loading;
  final Future<void> Function()? onOpen;
  final double height;
  final bool compact;

  const _NewInDropCard({
    required this.drop,
    required this.loading,
    required this.onOpen,
    required this.height,
    required this.compact,
  });

  @override
  Widget build(BuildContext context) {
    final imageUrl = drop?.imageUrl;
    return InkWell(
      onTap: onOpen == null ? null : () => onOpen!(),
      child: Container(
        height: height,
        decoration: BoxDecoration(
          border: Border.all(color: const Color(0xFFD6D6D6)),
        ),
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (imageUrl != null && imageUrl.isNotEmpty)
              CachedNetworkImage(
                imageUrl: imageUrl,
                fit: BoxFit.cover,
                placeholder: (_, _) => Container(color: GlameColors.warmGray),
                errorWidget: (_, _, _) =>
                    Container(color: GlameColors.warmGray),
              )
            else
              Container(color: GlameColors.warmGray),
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      GlameColors.textPrimary.withValues(alpha: 0.12),
                      Colors.transparent,
                      GlameColors.textPrimary.withValues(alpha: 0.55),
                    ],
                    stops: const [0, 0.42, 1],
                  ),
                ),
              ),
            ),
            Positioned(
              left: compact ? 18 : 30,
              bottom: compact ? 20 : 32,
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: compact ? 210 : 230),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'НОВЫЙ ДРОП',
                      style: TextStyle(
                        fontSize: compact ? 11 : 13,
                        height: 1.1,
                        letterSpacing: 1,
                        color: GlameColors.surface2,
                      ),
                    ),
                    SizedBox(height: compact ? 8 : 14),
                    Text(
                      (drop?.title ?? 'Новый дроп').toUpperCase(),
                      style: TextStyle(
                        fontSize: compact ? 24 : 32,
                        height: 0.96,
                        fontWeight: FontWeight.w400,
                        color: GlameColors.surface2,
                      ),
                    ),
                    SizedBox(height: compact ? 8 : 14),
                    Text(
                      drop?.description ??
                          'Кураторская подборка образов GLAME.',
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: compact ? 13 : 17,
                        height: 1.38,
                        color: GlameColors.surface2,
                      ),
                    ),
                    SizedBox(height: compact ? 14 : 26),
                    SizedBox(
                      width: compact ? 176 : 230,
                      height: compact ? 40 : 50,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          border: Border.all(color: GlameColors.surface2),
                        ),
                        child: Center(
                          child: Text(
                            'Смотреть дроп',
                            style: TextStyle(
                              fontSize: compact ? 14 : 17,
                              fontWeight: FontWeight.w400,
                              color: GlameColors.surface2,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            if (loading)
              Positioned(
                top: 16,
                right: 16,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 6,
                  ),
                  color: GlameColors.surface2.withValues(alpha: 0.86),
                  child: const Text(
                    'Загрузка',
                    style: TextStyle(
                      fontSize: 12,
                      color: GlameColors.textPrimary,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _NewInProductCard extends ConsumerWidget {
  final _NewInProductData product;
  final double height;
  final bool compact;

  const _NewInProductCard({
    required this.product,
    required this.height,
    required this.compact,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isFavorite =
        product.id.isNotEmpty &&
        ref.watch(wishlistControllerProvider).contains(product.id);

    return InkWell(
      onTap: product.id.isEmpty
          ? null
          : () => context.push('/product/${product.id}'),
      child: Container(
        height: height,
        decoration: BoxDecoration(
          border: Border.all(color: const Color(0xFFD6D6D6)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              flex: 60,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  product.imageUrl != null
                      ? CachedNetworkImage(
                          imageUrl: product.imageUrl!,
                          fit: BoxFit.cover,
                          placeholder: (_, _) =>
                              Container(color: GlameColors.warmGray),
                          errorWidget: (_, _, _) =>
                              Container(color: GlameColors.warmGray),
                        )
                      : Container(color: GlameColors.warmGray),
                  Positioned(
                    top: compact ? 10 : 12,
                    right: compact ? 10 : 12,
                    child: InkWell(
                      onTap: product.id.isEmpty
                          ? null
                          : () => ref
                                .read(wishlistControllerProvider.notifier)
                                .toggle(product.id),
                      child: SizedBox(
                        width: compact ? 32 : 34,
                        height: compact ? 32 : 34,
                        child: Icon(
                          isFavorite ? Icons.favorite : Icons.favorite_border,
                          size: compact ? 20 : 22,
                          color: GlameColors.surface2,
                          shadows: const [
                            Shadow(
                              color: GlameColors.textPrimary,
                              blurRadius: 2,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Container(height: 1, color: const Color(0xFFD6D6D6)),
            Expanded(
              flex: compact ? 44 : 40,
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  10,
                  compact ? 10 : 12,
                  10,
                  compact ? 10 : 12,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.max,
                  children: [
                    Text(
                      product.brand,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: compact ? 10 : 12,
                        height: 1.1,
                        letterSpacing: 0.9,
                        color: GlameColors.steelGray,
                      ),
                    ),
                    SizedBox(height: compact ? 5 : 8),
                    Text(
                      product.name,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: compact ? 13 : 16,
                        height: 1.2,
                        color: GlameColors.textPrimary,
                      ),
                    ),
                    SizedBox(height: compact ? 5 : 8),
                    Expanded(
                      child: Align(
                        alignment: Alignment.topLeft,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              product.availability,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: compact ? 11 : 13,
                                height: 1.3,
                                color: GlameColors.textSecondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    if (!compact)
                      const SizedBox(height: 0)
                    else
                      const SizedBox(height: 0),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NewInDropData {
  final String lookId;
  final String title;
  final String description;
  final String imageUrl;

  const _NewInDropData({
    required this.lookId,
    required this.title,
    required this.description,
    required this.imageUrl,
  });

  factory _NewInDropData.fromLook(_NewInLookData look) {
    return _NewInDropData(
      lookId: look.id,
      title: look.title,
      description: look.description,
      imageUrl: look.imageUrl ?? '',
    );
  }
}

class _NewInLookData {
  final String id;
  final String tag;
  final String title;
  final String description;
  final String? imageUrl;
  final List<_NewInProductData> products;

  const _NewInLookData({
    required this.id,
    required this.tag,
    required this.title,
    required this.description,
    required this.imageUrl,
    required this.products,
  });
}

class _NewInProductData {
  final String id;
  final String brand;
  final String name;
  final String availability;
  final String? imageUrl;
  final String? priceLabel;

  const _NewInProductData({
    required this.id,
    required this.brand,
    required this.name,
    required this.availability,
    required this.imageUrl,
    this.priceLabel,
  });

  factory _NewInProductData.placeholder(int index) {
    const names = ['Браслет Wave', 'Колье Shell', 'Браслет Orb'];
    return _NewInProductData(
      id: '',
      brand: 'GLAME',
      name: names[index % names.length],
      availability: 'В наличии · доставка по России',
      imageUrl: null,
    );
  }
}

class _HomeSlideData {
  final String? title;
  final String? subtitle;
  final String? backgroundImageUrl;
  final String? imageUrl;
  final _HomeSlideAction? imageAction;
  final String? primaryButtonText;
  final _HomeSlideAction? primaryAction;
  final String? secondaryButtonText;
  final _HomeSlideAction? secondaryAction;

  const _HomeSlideData({
    required this.title,
    required this.subtitle,
    required this.backgroundImageUrl,
    required this.imageUrl,
    required this.imageAction,
    required this.primaryButtonText,
    required this.primaryAction,
    required this.secondaryButtonText,
    required this.secondaryAction,
  });
}

class _HomeSlideAction {
  final String? type;
  final Map<String, dynamic>? payload;
  final String? legacyLink;

  const _HomeSlideAction({this.type, this.payload, this.legacyLink});
}

const _HomeSlideData _fallbackSlide = _HomeSlideData(
  title: 'Стиль внутри',
  subtitle:
      'Украшения, которые собирают образ под ваш стиль, задачу и повод.\nОнлайн — по всей России.',
  backgroundImageUrl: null,
  imageUrl: null,
  imageAction: null,
  primaryButtonText: 'Собрать свой стиль',
  primaryAction: _HomeSlideAction(type: 'selection', legacyLink: '/selection'),
  secondaryButtonText: 'Смотреть украшения',
  secondaryAction: _HomeSlideAction(
    type: 'catalog',
    payload: <String, dynamic>{},
    legacyLink: '/catalog',
  ),
);

const List<_HomeSlideData> _fallbackHeroSlides = <_HomeSlideData>[
  _fallbackSlide,
  _HomeSlideData(
    title: 'Собранный образ',
    subtitle:
        'Украшения складываются в цельный образ, когда форма, масштаб и настроение работают вместе.',
    backgroundImageUrl: null,
    imageUrl: null,
    imageAction: null,
    primaryButtonText: 'Смотреть подборку',
    primaryAction: _HomeSlideAction(legacyLink: '/collections/complete-look'),
    secondaryButtonText: 'Подобрать под меня',
    secondaryAction: _HomeSlideAction(
      type: 'selection',
      legacyLink: '/selection',
    ),
  ),
  _HomeSlideData(
    title: 'Подарок',
    subtitle:
        'Подберите украшение как личный знак внимания: спокойно, точно и без случайности.',
    backgroundImageUrl: null,
    imageUrl: null,
    imageAction: null,
    primaryButtonText: 'Смотреть подарки',
    primaryAction: _HomeSlideAction(legacyLink: '/collections/gift'),
    secondaryButtonText: 'Подобрать подарок',
    secondaryAction: _HomeSlideAction(
      type: 'selection',
      payload: <String, dynamic>{'mode': 'gift'},
      legacyLink: '/selection/gift',
    ),
  ),
  _HomeSlideData(
    title: 'Акцентные украшения',
    subtitle:
        'Один выразительный акцент может собрать образ сильнее, чем лишние детали.',
    backgroundImageUrl: null,
    imageUrl: null,
    imageAction: null,
    primaryButtonText: 'Смотреть акценты',
    primaryAction: _HomeSlideAction(legacyLink: '/collections/accent'),
    secondaryButtonText: 'Подобрать под меня',
    secondaryAction: _HomeSlideAction(
      type: 'selection',
      legacyLink: '/selection',
    ),
  ),
  _HomeSlideData(
    title: 'На отдых',
    subtitle:
        'Легкие линии, свет, движение и украшения, которые не спорят с маршрутом.',
    backgroundImageUrl: null,
    imageUrl: null,
    imageAction: null,
    primaryButtonText: 'Смотреть подборку',
    primaryAction: _HomeSlideAction(legacyLink: '/collections/resort'),
    secondaryButtonText: 'Подобрать под меня',
    secondaryAction: _HomeSlideAction(
      type: 'selection',
      legacyLink: '/selection',
    ),
  ),
  _HomeSlideData(
    title: 'На свадьбу',
    subtitle:
        'Украшения для важного дня: деликатный свет, масштаб и образ без лишней драмы.',
    backgroundImageUrl: null,
    imageUrl: null,
    imageAction: null,
    primaryButtonText: 'Смотреть подборку',
    primaryAction: _HomeSlideAction(legacyLink: '/collections/wedding'),
    secondaryButtonText: 'Подобрать под меня',
    secondaryAction: _HomeSlideAction(
      type: 'selection',
      legacyLink: '/selection',
    ),
  ),
  _HomeSlideData(
    title: 'Ваш стиль не из шаблона',
    subtitle:
        'Начните персональный подбор: по фото, задаче, поводу или вместе со стилистом GLAME.',
    backgroundImageUrl: null,
    imageUrl: null,
    imageAction: null,
    primaryButtonText: 'Начать подбор',
    primaryAction: _HomeSlideAction(
      type: 'selection',
      legacyLink: '/selection',
    ),
    secondaryButtonText: 'Написать стилисту',
    secondaryAction: _HomeSlideAction(type: 'stylist'),
  ),
];
