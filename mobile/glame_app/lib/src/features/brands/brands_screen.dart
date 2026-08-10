import 'dart:convert';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/network/asset_url.dart';
import '../../core/theme/glame_theme.dart';
import '../../core/widgets/glame_bottom_bar.dart';
import '../auth/auth_controller.dart';
import '../customer/stylist_entry.dart';
import '../home/home_api.dart';
import '../looks/looks_api.dart';

const String _block4BackgroundAsset =
    'assets/images/home/glame_home_block4_open_display_background.png';
const String _block4HomeBlockKey = 'collected_glame';
const String _block4BrandsPageBlockKey = 'collected_glame_brands';
const String _brandsShowcaseBlockKey = 'brands_showcase';
const double _brandsPagePadding = 28;
const String _block4HomeCacheKey = 'glame.home.block4.collected_glame.v1';
const String _brandSlidesCachePrefix = 'glame.brand.slides.v2.';
const String _block4HomeSnapshotAsset =
    'assets/data/home_block4_collected_glame_snapshot.json';

final _brandsApiProvider = Provider<HomeApi>((ref) {
  return HomeApi(ref.watch(apiClientProvider));
});

final _brandsLooksApiProvider = Provider<LooksApi>((ref) {
  return LooksApi(ref.watch(apiClientProvider));
});

final homeCollectedGlameBlockProvider =
    FutureProvider<HomeBlockCollectedGlameData>((ref) async {
      final api = ref.watch(_brandsApiProvider);
      final slide = await _loadHomeBlock4Slide(api);
      final serverImage =
          _nonEmptyString(slide['background_image_url']) ??
          _nonEmptyString(slide['image_url']);
      final imageSource = serverImage ?? _block4BackgroundAsset;
      return HomeBlockCollectedGlameData(
        title: 'Собрано GLAME',
        subtitle: 'Мы отбираем главное. Чтобы вы выбирали свое.',
        ctaLabel: 'Смотреть бренды',
        backgroundImage: imageSource,
        visualImage: imageSource,
        imageCacheVersion:
            _nonEmptyString(slide['updated_at']) ??
            _nonEmptyString(slide['id']),
        useSingleImage: true,
        brandNames: [
          'Geometry',
          'Magna',
          'Pearl',
          'Crystal',
          'Bicolor',
          'Prism Of Elegance',
          'UNOde50',
          'Raganella Princess',
          'Island Soul',
          'AGafi',
          'Antura',
          'Kalliope',
          'Wrinkles of Time',
          'Claudio Canzian',
        ],
      );
    });

String? _nonEmptyString(Object? value) {
  final text = (value as String?)?.trim();
  return text == null || text.isEmpty ? null : text;
}

Future<Map<String, dynamic>> _loadHomeBlock4Slide(HomeApi api) async {
  try {
    final raw = await api.getHomeSlides(blockKey: _block4HomeBlockKey);
    if (raw.isNotEmpty) {
      await _saveHomeBlock4Cache(raw);
      return _firstMap(raw);
    }
  } catch (_) {
    // Keep block 4 available from local cache or bundled snapshot offline.
  }

  final cached = await _readHomeBlock4Cache();
  if (cached.isNotEmpty) return _firstMap(cached);

  final bundled = await _readHomeBlock4Snapshot();
  return _firstMap(bundled);
}

Future<void> _saveHomeBlock4Cache(List<dynamic> slides) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString(_block4HomeCacheKey, jsonEncode(slides));
}

Future<List<dynamic>> _readHomeBlock4Cache() async {
  final prefs = await SharedPreferences.getInstance();
  final raw = prefs.getString(_block4HomeCacheKey);
  if (raw == null || raw.isEmpty) return const <dynamic>[];
  try {
    final decoded = jsonDecode(raw);
    if (decoded is List) return decoded;
  } catch (_) {
    await prefs.remove(_block4HomeCacheKey);
  }
  return const <dynamic>[];
}

Future<List<dynamic>> _readHomeBlock4Snapshot() async {
  final raw = await rootBundle.loadString(_block4HomeSnapshotAsset);
  final decoded = jsonDecode(raw);
  if (decoded is List) return decoded;
  return const <dynamic>[];
}

Map<String, dynamic> _firstMap(List<dynamic> raw) {
  if (raw.isNotEmpty && raw.first is Map) {
    return Map<String, dynamic>.from(raw.first as Map);
  }
  return const <String, dynamic>{};
}

final brandsPageHeroProvider = StreamProvider<BrandsPageHeroData?>((ref) {
  final api = ref.watch(_brandsApiProvider);
  return _watchBrandSlide(_block4BrandsPageBlockKey, api).map((slide) {
    if (slide == null) return null;
    final imageSource = '${slide['image_url'] ?? ''}'.trim();
    if (imageSource.isEmpty) return null;
    final title = '${slide['title'] ?? ''}'.trim();
    final subtitle = '${slide['subtitle'] ?? ''}'.trim();
    return BrandsPageHeroData(
      imageSource: imageSource,
      title: title.isEmpty ? 'Смотреть бренды' : title,
      subtitle: subtitle.isEmpty ? 'Собрано GLAME' : subtitle,
    );
  });
});

Stream<Map<String, dynamic>?> _watchBrandSlide(
  String blockKey,
  HomeApi api,
) async* {
  await for (final slides in _watchBrandSlides(blockKey, api)) {
    yield _firstNullableMap(slides);
  }
}

Stream<List<dynamic>> _watchBrandSlides(String blockKey, HomeApi api) async* {
  final cacheKey = '$_brandSlidesCachePrefix$blockKey';
  final cached = await _readBrandSlidesCache(cacheKey);
  if (cached.isNotEmpty) {
    yield cached;
  }

  try {
    final remote = await api.getHomeSlides(blockKey: blockKey);
    if (remote.isNotEmpty) {
      await _saveBrandSlidesCache(cacheKey, remote);
      if (jsonEncode(remote) != jsonEncode(cached)) {
        yield remote;
      }
    } else if (cached.isEmpty) {
      yield const <dynamic>[];
    }
  } catch (_) {
    if (cached.isEmpty) yield const <dynamic>[];
  }
}

Map<String, dynamic>? _firstNullableMap(List<dynamic> raw) {
  for (final item in raw) {
    if (item is Map) return Map<String, dynamic>.from(item);
  }
  return null;
}

Future<void> _saveBrandSlidesCache(String key, List<dynamic> slides) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString(key, jsonEncode(slides));
}

Future<List<dynamic>> _readBrandSlidesCache(String key) async {
  final prefs = await SharedPreferences.getInstance();
  final raw = prefs.getString(key);
  if (raw == null || raw.isEmpty) return const <dynamic>[];
  try {
    final decoded = jsonDecode(raw);
    if (decoded is List) return decoded;
  } catch (_) {
    await prefs.remove(key);
  }
  return const <dynamic>[];
}

final brandDetailHeroProvider =
    StreamProvider.family<BrandsPageHeroData?, String>((ref, brandId) {
      final api = ref.watch(_brandsApiProvider);
      return _watchBrandSlide(_brandDetailBlockKey(brandId), api).map((slide) {
        if (slide == null) return null;
        final imageSource = '${slide['image_url'] ?? ''}'.trim();
        if (imageSource.isEmpty) return null;
        final title = '${slide['title'] ?? ''}'.trim();
        final subtitle = '${slide['subtitle'] ?? ''}'.trim();
        return BrandsPageHeroData(
          imageSource: imageSource,
          title: title,
          subtitle: subtitle,
        );
      });
    });

final brandFeaturedLooksProvider =
    FutureProvider.family<List<_BrandLookCardData>, String>((
      ref,
      brandId,
    ) async {
      final brand = _brandById(brandId);
      if (brand == null) return const <_BrandLookCardData>[];

      final api = ref.watch(_brandsLooksApiProvider);
      final raw = await api.getAllFeed();
      final looks = raw
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);

      final candidates = looks
          .where((look) => _lookHasBrandProduct(look, brand))
          .map(_BrandLookCardData.fromMap)
          .where((item) => item.id.isNotEmpty)
          .toList(growable: false);

      return candidates.take(6).toList(growable: false);
    });

final brandsShowcaseProvider = StreamProvider<List<_BrandShowcaseCardData>>((
  ref,
) async* {
  final api = ref.watch(_brandsApiProvider);
  await for (final cards in _watchBrandShowcaseCards(api)) {
    yield cards;
  }
});

Stream<List<_BrandShowcaseCardData>> _watchBrandShowcaseCards(
  HomeApi api,
) async* {
  final cacheKeys = [
    _brandsShowcaseBlockKey,
    for (final brand in _allBrands) _brandDetailBlockKey(brand.id),
  ];
  final cachedCards = await _loadBrandShowcaseCardsFromCache(cacheKeys);
  if (cachedCards.isNotEmpty) {
    yield _fillBrandShowcaseCards(cachedCards.take(4).toList(growable: false));
  }

  final remoteCards = <_BrandShowcaseCardData>[];
  List<dynamic> overrideRaw;
  try {
    overrideRaw = await api.getHomeSlides(blockKey: _brandsShowcaseBlockKey);
  } catch (_) {
    if (cachedCards.isEmpty) yield _fallbackBrandShowcaseCards;
    return;
  }
  if (overrideRaw.isNotEmpty) {
    await _saveBrandSlidesCache(
      '$_brandSlidesCachePrefix$_brandsShowcaseBlockKey',
      overrideRaw,
    );
    remoteCards.addAll(
      overrideRaw
          .whereType<Map>()
          .map((item) => _BrandShowcaseCardData.fromMap(item))
          .where((item) => item.title.isNotEmpty)
          .take(4),
    );
  }
  if (remoteCards.isNotEmpty) {
    yield _fillBrandShowcaseCards(remoteCards);
    return;
  }

  final detailCards = <_BrandShowcaseCardData>[];
  for (final brand in _allBrands) {
    final blockKey = _brandDetailBlockKey(brand.id);
    List<dynamic> raw;
    try {
      raw = await api.getHomeSlides(blockKey: blockKey);
    } catch (_) {
      continue;
    }
    if (raw.isNotEmpty) {
      await _saveBrandSlidesCache('$_brandSlidesCachePrefix$blockKey', raw);
    }
    if (raw.isEmpty || raw.first is! Map) continue;
    detailCards.add(
      _BrandShowcaseCardData.fromBrandDetail(
        brand,
        Map<String, dynamic>.from(raw.first as Map),
      ),
    );
  }
  detailCards.sort((a, b) => a.sortOrder.compareTo(b.sortOrder));
  final next = _fillBrandShowcaseCards(
    detailCards.take(4).toList(growable: false),
  );
  if (jsonEncode(next.map((item) => item.cacheSignature).toList()) !=
      jsonEncode(cachedCards.map((item) => item.cacheSignature).toList())) {
    yield next;
  } else if (cachedCards.isEmpty) {
    yield next;
  }
}

Future<List<_BrandShowcaseCardData>> _loadBrandShowcaseCardsFromCache(
  List<String> blockKeys,
) async {
  final cards = <_BrandShowcaseCardData>[];
  for (final blockKey in blockKeys) {
    final cached = await _readBrandSlidesCache(
      '$_brandSlidesCachePrefix$blockKey',
    );
    if (cached.isEmpty) continue;
    if (blockKey == _brandsShowcaseBlockKey) {
      cards.addAll(
        cached
            .whereType<Map>()
            .map((item) => _BrandShowcaseCardData.fromMap(item))
            .where((item) => item.title.isNotEmpty),
      );
      continue;
    }
    final brandId = blockKey.replaceFirst('brand_detail_', '');
    final brand = _brandById(brandId);
    if (brand == null || cached.first is! Map) continue;
    cards.add(
      _BrandShowcaseCardData.fromBrandDetail(
        brand,
        Map<String, dynamic>.from(cached.first as Map),
      ),
    );
  }
  cards.sort((a, b) => a.sortOrder.compareTo(b.sortOrder));
  return cards;
}

List<_BrandShowcaseCardData> _fillBrandShowcaseCards(
  List<_BrandShowcaseCardData> cards,
) {
  final result = <_BrandShowcaseCardData>[...cards];
  final usedIds = result.map((item) => item.brandId).toSet();
  for (final fallback in _fallbackBrandShowcaseCards) {
    if (result.length >= 4) break;
    if (usedIds.contains(fallback.brandId)) continue;
    result.add(fallback);
    usedIds.add(fallback.brandId);
  }
  return result.take(4).toList(growable: false);
}

class HomeBlockCollectedGlameData {
  final String title;
  final String subtitle;
  final String ctaLabel;
  final String? backgroundImage;
  final String visualImage;
  final String? imageCacheVersion;
  final bool useSingleImage;
  final List<String> brandNames;

  const HomeBlockCollectedGlameData({
    required this.title,
    required this.subtitle,
    required this.ctaLabel,
    required this.backgroundImage,
    required this.visualImage,
    required this.imageCacheVersion,
    required this.useSingleImage,
    required this.brandNames,
  });
}

class BrandsPageHeroData {
  final String imageSource;
  final String title;
  final String subtitle;

  const BrandsPageHeroData({
    required this.imageSource,
    required this.title,
    required this.subtitle,
  });
}

class HomeCollectedGlameBlock extends ConsumerStatefulWidget {
  final HomeBlockCollectedGlameData? data;
  final VoidCallback onCtaPressed;
  final double? viewportHeight;

  const HomeCollectedGlameBlock({
    super.key,
    this.data,
    required this.onCtaPressed,
    this.viewportHeight,
  });

  @override
  ConsumerState<HomeCollectedGlameBlock> createState() =>
      _HomeCollectedGlameBlockState();
}

class _HomeCollectedGlameBlockState
    extends ConsumerState<HomeCollectedGlameBlock> {
  bool _viewTracked = false;

  @override
  Widget build(BuildContext context) {
    final showcaseAsync = ref.watch(brandsShowcaseProvider);

    return showcaseAsync.when(
      data: (cards) {
        _trackViewOnce();
        return _HomeBrandsShowcaseSection(
          cards: cards,
          viewportHeight: widget.viewportHeight,
          onCtaPressed: () {
            _trackBlock4Event('home_block4_brands_click');
            widget.onCtaPressed();
          },
        );
      },
      loading: () => _HomeBrandsShowcaseSection(
        cards: _fallbackBrandShowcaseCards,
        viewportHeight: widget.viewportHeight,
        onCtaPressed: widget.onCtaPressed,
      ),
      error: (_, _) => _HomeBrandsShowcaseSection(
        cards: _fallbackBrandShowcaseCards,
        viewportHeight: widget.viewportHeight,
        onCtaPressed: widget.onCtaPressed,
      ),
    );
  }

  void _trackViewOnce() {
    if (_viewTracked) return;
    _viewTracked = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _trackBlock4Event('home_block4_view');
    });
  }

  void _trackBlock4Event(String eventName) {
    debugPrint('analytics:$eventName');
  }
}

class _HomeBrandsShowcaseSection extends StatelessWidget {
  final List<_BrandShowcaseCardData> cards;
  final VoidCallback onCtaPressed;
  final double? viewportHeight;

  const _HomeBrandsShowcaseSection({
    required this.cards,
    required this.onCtaPressed,
    this.viewportHeight,
  });

  @override
  Widget build(BuildContext context) {
    final compact = viewportHeight != null;
    final safeTop = MediaQuery.of(context).padding.top;
    final topPadding = compact
        ? safeTop + GlameUi.heroTopOffset + GlameUi.heroTopBarHeight + 10
        : 58.0;
    final bottomPadding = compact ? 8.0 : 42.0;

    return Container(
      height: viewportHeight,
      width: double.infinity,
      color: GlameColors.whiteGlame,
      child: SingleChildScrollView(
        physics: const ClampingScrollPhysics(),
        padding: EdgeInsets.fromLTRB(
          GlameUi.pagePadding,
          topPadding,
          GlameUi.pagePadding,
          bottomPadding,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Бренды',
              style: TextStyle(
                fontSize: 52,
                height: 0.96,
                letterSpacing: 0,
                fontWeight: FontWeight.w300,
                color: GlameColors.graphite,
              ),
            ),
            const SizedBox(height: 18),
            const Text(
              'Выбирайте бренд по характеру, стилю и настроению.',
              style: TextStyle(
                fontSize: 17,
                height: 1.35,
                color: GlameColors.steelGrey,
                fontWeight: FontWeight.w300,
              ),
            ),
            SizedBox(height: compact ? 8 : 34),
            _BrandsShowcaseGrid(cards: cards, compact: compact),
            SizedBox(height: compact ? 14 : 36),
            _BrandsShowAllButton(onPressed: onCtaPressed, compact: compact),
          ],
        ),
      ),
    );
  }
}

class _CollectedGlameSkeletonBox extends StatelessWidget {
  final double? height;

  const _CollectedGlameSkeletonBox({this.height});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        width: double.infinity,
        height: height,
        decoration: BoxDecoration(
          color: GlameColors.coolLightGray,
          border: Border.all(
            color: GlameColors.coolLightGray,
            width: GlameUi.borderWidth,
          ),
          borderRadius: BorderRadius.circular(GlameUi.radius),
        ),
      ),
    );
  }
}

class _Block4ImageLayer extends StatelessWidget {
  final String source;
  final String? cacheVersion;
  final BoxFit fit;
  final Alignment alignment;

  const _Block4ImageLayer({
    required this.source,
    this.cacheVersion,
    required this.fit,
    required this.alignment,
  });

  @override
  Widget build(BuildContext context) {
    final resolvedSource = resolveAssetUrl(source) ?? source;
    final localAsset = _localBlock4ImageAsset(resolvedSource, cacheVersion);
    if (localAsset != null) {
      return Image.asset(localAsset, fit: fit, alignment: alignment);
    }
    if (resolvedSource.startsWith('http://') ||
        resolvedSource.startsWith('https://')) {
      return CachedNetworkImage(
        imageUrl: resolvedSource,
        cacheKey: _versionedBlock4CacheKey(resolvedSource, cacheVersion),
        fit: fit,
        alignment: alignment,
        placeholder: (context, _) =>
            const ColoredBox(color: GlameColors.coldLightGrey),
        errorWidget: (context, _, _) =>
            const ColoredBox(color: GlameColors.coldLightGrey),
      );
    }
    return Image.asset(resolvedSource, fit: fit, alignment: alignment);
  }
}

String _versionedBlock4CacheKey(String source, String? version) {
  final cleanVersion = version?.trim();
  if (cleanVersion == null || cleanVersion.isEmpty) return source;
  return '$source@$cleanVersion';
}

String? _localBlock4ImageAsset(String source, String? cacheVersion) {
  final uri = Uri.tryParse(source);
  final filename = uri == null || uri.pathSegments.isEmpty
      ? source.split('/').last
      : uri.pathSegments.last;
  final version = cacheVersion?.trim() ?? '';
  return switch (filename) {
    'b7f3d114066344e28bd533691b548718.jpg'
        when version.startsWith('2026-05-09T14:21:11') =>
      'assets/images/home/home_block4_collected_glame_current.jpg',
    _ => null,
  };
}

class BrandsPageScreen extends ConsumerWidget {
  const BrandsPageScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final heroAsync = ref.watch(brandsPageHeroProvider);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _trackEvent('brands_page_view');
    });
    return Scaffold(
      appBar: GlameTopAppBar(
        leadingIcon: Icons.arrow_back,
        leadingTooltip: 'Назад',
        onMenuPressed: () {
          if (context.canPop()) {
            context.pop();
          } else {
            context.go('/brands');
          }
        },
      ),
      bottomNavigationBar: const GlameBottomBar(selectedIndex: 1),
      body: SafeArea(
        top: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            _brandsPagePadding,
            24,
            _brandsPagePadding,
            32,
          ),
          children: [
            heroAsync.when(
              data: (hero) {
                if (hero == null) {
                  return const _AllBrandsHeader();
                }
                return _BrandsPageHeroCard(
                  imageSource: hero.imageSource,
                  title: hero.title,
                  subtitle: hero.subtitle,
                );
              },
              loading: () => const _CollectedGlameSkeletonBox(height: 220),
              error: (_, _) => const _AllBrandsHeader(),
            ),
            const SizedBox(height: 24),
            for (var i = 0; i < _allBrands.length; i++) ...[
              _BrandListRow(brand: _allBrands[i]),
              if (i != _allBrands.length - 1)
                Container(height: 1, color: GlameColors.coldLightGrey),
            ],
          ],
        ),
      ),
    );
  }
}

class _AllBrandsHeader extends StatelessWidget {
  const _AllBrandsHeader();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Смотреть бренды',
          style: TextStyle(
            fontSize: 40,
            height: 0.98,
            fontWeight: FontWeight.w400,
            color: GlameColors.graphite,
          ),
        ),
        SizedBox(height: 14),
        Text(
          'Собрано GLAME',
          style: TextStyle(
            fontSize: 18,
            height: 1.42,
            color: GlameColors.steelGrey,
          ),
        ),
      ],
    );
  }
}

class _BrandsShowcaseGrid extends StatelessWidget {
  final List<_BrandShowcaseCardData> cards;
  final bool compact;

  const _BrandsShowcaseGrid({required this.cards, this.compact = false});

  @override
  Widget build(BuildContext context) {
    final effectiveCards = cards.isEmpty ? _fallbackBrandShowcaseCards : cards;
    return GridView.builder(
      itemCount: effectiveCards.take(4).length,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        crossAxisSpacing: compact ? 10 : 12,
        mainAxisSpacing: compact ? 10 : 12,
        childAspectRatio: compact ? 0.84 : 3 / 4,
      ),
      itemBuilder: (context, index) {
        return _BrandShowcaseCard(card: effectiveCards[index]);
      },
    );
  }
}

class _BrandShowcaseCard extends StatelessWidget {
  final _BrandShowcaseCardData card;

  const _BrandShowcaseCard({required this.card});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () {
        _trackEvent('brand_showcase_card_click', {'brand_id': card.brandId});
        context.push('/brand/${card.brandId}');
      },
      child: ClipRRect(
        borderRadius: BorderRadius.circular(GlameUi.radius),
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (card.imageUrl != null)
              _Block4ImageLayer(
                source: card.imageUrl!,
                cacheVersion: card.imageCacheVersion,
                fit: BoxFit.cover,
                alignment: Alignment.center,
              )
            else
              const ColoredBox(color: GlameColors.coldLightGrey),
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Color.fromRGBO(0, 0, 0, 0.0),
                    Color.fromRGBO(0, 0, 0, 0.08),
                    Color.fromRGBO(0, 0, 0, 0.72),
                  ],
                  stops: [0.0, 0.48, 1.0],
                ),
              ),
            ),
            Positioned(
              left: 15,
              right: 15,
              bottom: 15,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          card.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 20,
                            height: 1.08,
                            letterSpacing: 0,
                            color: GlameColors.whiteGlame,
                            fontWeight: FontWeight.w300,
                          ),
                        ),
                        if (card.subtitle.isNotEmpty) ...[
                          const SizedBox(height: 6),
                          Text(
                            card.subtitle,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 12.5,
                              height: 1.18,
                              letterSpacing: 0,
                              color: GlameColors.whiteGlame,
                              fontWeight: FontWeight.w300,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  const Icon(
                    Icons.arrow_forward,
                    size: 20,
                    color: GlameColors.whiteGlame,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BrandsShowAllButton extends StatelessWidget {
  final VoidCallback onPressed;
  final bool compact;

  const _BrandsShowAllButton({required this.onPressed, this.compact = false});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: compact ? 48 : 58,
      child: OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          foregroundColor: GlameColors.graphite,
          side: const BorderSide(
            color: GlameColors.steelGrey,
            width: GlameUi.borderWidth,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(GlameUi.radius),
          ),
          padding: EdgeInsets.symmetric(horizontal: compact ? 20 : 24),
        ),
        child: const Row(
          children: [
            Expanded(
              child: Text(
                'Смотреть все бренды',
                style: TextStyle(fontSize: 15.5, letterSpacing: 0),
              ),
            ),
            Icon(Icons.arrow_forward, size: 21),
          ],
        ),
      ),
    );
  }
}

class _BrandsPageHeroCard extends StatelessWidget {
  final String imageSource;
  final String title;
  final String subtitle;

  const _BrandsPageHeroCard({
    required this.imageSource,
    required this.title,
    required this.subtitle,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: Border.all(
          color: GlameColors.coldLightGrey,
          width: GlameUi.borderWidth,
        ),
      ),
      child: AspectRatio(
        aspectRatio: 327 / 182,
        child: Stack(
          fit: StackFit.expand,
          children: [
            _Block4ImageLayer(
              source: imageSource,
              fit: BoxFit.cover,
              alignment: Alignment.topCenter,
            ),
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.white.withValues(alpha: 0.0),
                      Colors.white.withValues(alpha: 0.18),
                      GlameColors.coldLightGrey.withValues(alpha: 0.88),
                      GlameColors.coldLightGrey,
                    ],
                    stops: const [0.0, 0.46, 0.8, 1.0],
                  ),
                ),
              ),
            ),
            Positioned(
              left: 22,
              right: 22,
              bottom: 20,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontSize: 32,
                      height: 1.06,
                      letterSpacing: -0.4,
                      color: GlameColors.graphite,
                      fontWeight: FontWeight.w300,
                    ),
                  ),
                  if (subtitle.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text(
                      subtitle,
                      style: const TextStyle(
                        fontSize: 13,
                        height: 1.2,
                        letterSpacing: 0.0,
                        color: GlameColors.steelGrey,
                        fontWeight: FontWeight.w300,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class BrandDetailScreen extends ConsumerWidget {
  final String brandId;

  const BrandDetailScreen({super.key, required this.brandId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final brand = _brandById(brandId);
    if (brand == null) {
      return Scaffold(
        appBar: const GlameTopAppBar(),
        body: const SafeArea(
          top: false,
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              _brandsPagePadding,
              24,
              _brandsPagePadding,
              32,
            ),
            child: Text(
              'Бренд не найден.',
              style: TextStyle(fontSize: 20, color: GlameColors.graphite),
            ),
          ),
        ),
      );
    }

    final heroAsync = ref.watch(brandDetailHeroProvider(brand.id));
    final featuredAsync = ref.watch(brandFeaturedLooksProvider(brand.id));
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _trackEvent('brand_page_view', {'brand_id': brand.id});
    });

    return Scaffold(
      appBar: GlameTopAppBar(
        leadingIcon: Icons.arrow_back,
        leadingTooltip: 'Назад',
        onMenuPressed: () {
          if (context.canPop()) {
            context.pop();
          } else {
            context.go('/brands');
          }
        },
      ),
      bottomNavigationBar: const GlameBottomBar(selectedIndex: 1),
      body: SafeArea(
        top: false,
        child: LayoutBuilder(
          builder: (context, constraints) {
            return ListView(
              padding: EdgeInsets.zero,
              children: [
                SizedBox(
                  height: constraints.maxHeight,
                  child: _BrandFullScreenHero(
                    brand: brand,
                    heroImageSource:
                        heroAsync.valueOrNull?.imageSource ??
                        _block4BackgroundAsset,
                    heroTitle: heroAsync.valueOrNull?.title,
                    heroSubtitle: heroAsync.valueOrNull?.subtitle,
                  ),
                ),
                _BrandDetailBody(brand: brand, featuredAsync: featuredAsync),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _BrandFullScreenHero extends StatelessWidget {
  final _BrandDetailData brand;
  final String heroImageSource;
  final String? heroTitle;
  final String? heroSubtitle;

  const _BrandFullScreenHero({
    required this.brand,
    required this.heroImageSource,
    this.heroTitle,
    this.heroSubtitle,
  });

  @override
  Widget build(BuildContext context) {
    final title = _nonEmptyString(heroTitle) ?? brand.name;
    final adminSubtitle = _nonEmptyString(heroSubtitle);
    final body = adminSubtitle ?? brand.description;
    final showFallbackSignature = adminSubtitle == null;

    return Stack(
      fit: StackFit.expand,
      children: [
        _Block4ImageLayer(
          source: heroImageSource,
          fit: BoxFit.cover,
          alignment: Alignment.center,
        ),
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                Color.fromRGBO(0, 0, 0, 0.08),
                Color.fromRGBO(0, 0, 0, 0.18),
                Color.fromRGBO(0, 0, 0, 0.74),
              ],
              stops: [0.0, 0.48, 1.0],
            ),
          ),
        ),
        Positioned(
          left: _brandsPagePadding,
          right: _brandsPagePadding,
          bottom: 38,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 48,
                  height: 0.95,
                  letterSpacing: 0,
                  color: GlameColors.whiteGlame,
                  fontWeight: FontWeight.w300,
                ),
              ),
              if (showFallbackSignature) ...[
                const SizedBox(height: 14),
                Text(
                  brand.signature,
                  style: const TextStyle(
                    fontSize: 17,
                    height: 1.3,
                    color: GlameColors.coldLightGrey,
                    fontWeight: FontWeight.w300,
                  ),
                ),
              ],
              const SizedBox(height: 14),
              Container(width: 54, height: 1, color: GlameColors.whiteGlame),
              const SizedBox(height: 22),
              Text(
                body,
                maxLines: adminSubtitle == null ? 4 : 6,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 16,
                  height: 1.42,
                  color: GlameColors.whiteGlame,
                  fontWeight: FontWeight.w300,
                ),
              ),
              const SizedBox(height: 24),
              SizedBox(
                height: 52,
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: () {
                    _trackEvent('brand_all_products_click', {
                      'brand_id': brand.id,
                    });
                    _openBrandCatalog(context, brand);
                  },
                  style: OutlinedButton.styleFrom(
                    foregroundColor: GlameColors.whiteGlame,
                    side: const BorderSide(
                      color: GlameColors.whiteGlame,
                      width: GlameUi.borderWidth,
                    ),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(GlameUi.radius),
                    ),
                  ),
                  child: Text(
                    'Смотреть все изделия ${brand.name}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 16),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _BrandDetailBody extends StatelessWidget {
  final _BrandDetailData brand;
  final AsyncValue<List<_BrandLookCardData>> featuredAsync;

  const _BrandDetailBody({required this.brand, required this.featuredAsync});

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: GlameColors.surface2,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          _brandsPagePadding,
          24,
          _brandsPagePadding,
          32,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _BrandDnaStrip(markers: brand.dnaMarkers),
            const SizedBox(height: 28),
            Text(
              'ВЫБОР GLAME В ${brand.name.toUpperCase()}',
              style: const TextStyle(
                fontSize: 13,
                letterSpacing: 2.4,
                color: GlameColors.steelGrey,
              ),
            ),
            const SizedBox(height: 14),
            featuredAsync.when(
              data: (looks) {
                if (looks.isEmpty) {
                  return _BrandEmptyState(brand: brand);
                }
                return _BrandFeaturedLooksGrid(looks: looks);
              },
              loading: () => const _BrandDetailLoadingState(),
              error: (_, _) => _BrandErrorState(brand: brand),
            ),
            const SizedBox(height: 28),
            _BrandUseCasesInfo(items: brand.useCases),
          ],
        ),
      ),
    );
  }
}

class _BrandListRow extends StatelessWidget {
  final _BrandDetailData brand;

  const _BrandListRow({required this.brand});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () {
        _trackEvent('brand_row_click', {'brand_id': brand.id});
        context.push('/brand/${brand.id}');
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 18),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    brand.name,
                    style: const TextStyle(
                      fontSize: 24,
                      height: 1.04,
                      color: GlameColors.graphite,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    brand.signature,
                    style: const TextStyle(
                      fontSize: 15,
                      height: 1.4,
                      color: GlameColors.steelGrey,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            const Icon(
              Icons.arrow_forward_rounded,
              size: 20,
              color: GlameColors.graphite,
            ),
          ],
        ),
      ),
    );
  }
}

class _BrandDnaStrip extends StatelessWidget {
  final List<String> markers;

  const _BrandDnaStrip({required this.markers});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (var index = 0; index < markers.length; index++) ...[
          Expanded(
            child: Container(
              height: 60,
              alignment: Alignment.centerLeft,
              padding: const EdgeInsets.symmetric(horizontal: 14),
              decoration: BoxDecoration(
                border: Border.all(
                  color: GlameColors.coldLightGrey,
                  width: GlameUi.borderWidth,
                ),
              ),
              child: Text(
                markers[index],
                style: const TextStyle(
                  fontSize: 15,
                  height: 1.35,
                  color: GlameColors.graphite,
                ),
              ),
            ),
          ),
          if (index != markers.length - 1) const SizedBox(width: 12),
        ],
      ],
    );
  }
}

class _BrandFeaturedLooksGrid extends StatelessWidget {
  final List<_BrandLookCardData> looks;

  const _BrandFeaturedLooksGrid({required this.looks});

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: looks.length,
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        childAspectRatio: 3 / 4,
      ),
      itemBuilder: (context, index) {
        return _BrandFeaturedLookCard(look: looks[index]);
      },
    );
  }
}

class _BrandFeaturedLookCard extends StatelessWidget {
  final _BrandLookCardData look;

  const _BrandFeaturedLookCard({required this.look});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () {
        _trackEvent('brand_featured_look_click', {
          'brand_id': look.brandId,
          'look_id': look.id,
        });
        context.push('/look/${look.id}');
      },
      child: Container(
        decoration: BoxDecoration(
          border: Border.all(
            color: GlameColors.coldLightGrey,
            width: GlameUi.borderWidth,
          ),
        ),
        clipBehavior: Clip.hardEdge,
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (look.imageUrl == null)
              const ColoredBox(color: GlameColors.coldLightGrey)
            else
              CachedNetworkImage(
                imageUrl: look.imageUrl!,
                width: double.infinity,
                height: double.infinity,
                fit: BoxFit.cover,
                alignment: Alignment.center,
                placeholder: (context, _) =>
                    const ColoredBox(color: GlameColors.coldLightGrey),
                errorWidget: (context, _, _) =>
                    const ColoredBox(color: GlameColors.coldLightGrey),
              ),
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.transparent,
                    Color.fromRGBO(238, 239, 237, 0.28),
                    Color.fromRGBO(238, 239, 237, 0.92),
                  ],
                  stops: [0.48, 0.72, 1.0],
                ),
              ),
            ),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: DecoratedBox(
                decoration: const BoxDecoration(
                  color: Color.fromRGBO(238, 239, 237, 0.9),
                  border: Border(
                    top: BorderSide(color: Color.fromRGBO(255, 255, 255, 0.48)),
                  ),
                ),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        look.name,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 16,
                          height: 1.05,
                          color: GlameColors.textPrimary,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      if (look.productsLabel.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(
                          look.productsLabel,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 11,
                            height: 1.2,
                            letterSpacing: 0.8,
                            color: GlameColors.textSecondary,
                          ),
                        ),
                      ],
                      const SizedBox(height: 8),
                      Text(
                        'Смотреть образ',
                        style: TextStyle(
                          fontSize: 12,
                          height: 1.1,
                          color: GlameColors.textPrimary.withValues(
                            alpha: 0.82,
                          ),
                          decoration: TextDecoration.underline,
                          decorationColor: GlameColors.textPrimary.withValues(
                            alpha: 0.44,
                          ),
                        ),
                      ),
                    ],
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

class _BrandFeaturedProductsSkeleton extends StatelessWidget {
  const _BrandFeaturedProductsSkeleton();

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: 4,
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        childAspectRatio: 0.74,
      ),
      itemBuilder: (context, index) {
        return Container(
          decoration: BoxDecoration(
            border: Border.all(
              color: GlameColors.coldLightGrey,
              width: GlameUi.borderWidth,
            ),
            color: GlameColors.coldLightGrey,
          ),
        );
      },
    );
  }
}

class _BrandDetailLoadingState extends StatelessWidget {
  const _BrandDetailLoadingState();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: const [
        _CollectedGlameSkeletonBox(height: 220),
        SizedBox(height: 16),
        _CollectedGlameSkeletonBox(height: 52),
        SizedBox(height: 14),
        _BrandFeaturedProductsSkeleton(),
      ],
    );
  }
}

class _BrandEmptyState extends StatelessWidget {
  final _BrandDetailData brand;

  const _BrandEmptyState({required this.brand});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        border: Border.all(
          color: GlameColors.coldLightGrey,
          width: GlameUi.borderWidth,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Сейчас изделия бренда ${brand.name} недоступны онлайн.',
            style: const TextStyle(
              fontSize: 16,
              height: 1.4,
              color: GlameColors.graphite,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Напишите стилисту, мы проверим наличие в пространствах.',
            style: TextStyle(
              fontSize: 14,
              height: 1.35,
              color: GlameColors.steelGrey,
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: GlameUi.buttonHeight,
            child: OutlinedButton(
              onPressed: () => showStylistContactSheet(
                context,
                initialMessage:
                    'Хочу уточнить наличие изделий ${brand.name} и подобрать лучший вариант.',
                source: 'brand_page',
                scenario: 'live_stylist',
              ),
              style: OutlinedButton.styleFrom(
                side: const BorderSide(
                  color: GlameColors.coldLightGrey,
                  width: GlameUi.borderWidth,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(GlameUi.radius),
                ),
              ),
              child: const Text('Написать стилисту'),
            ),
          ),
        ],
      ),
    );
  }
}

class _BrandErrorState extends StatelessWidget {
  final _BrandDetailData brand;

  const _BrandErrorState({required this.brand});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        border: Border.all(
          color: GlameColors.coldLightGrey,
          width: GlameUi.borderWidth,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Не удалось загрузить выбор GLAME для ${brand.name}.',
            style: const TextStyle(
              fontSize: 16,
              height: 1.4,
              color: GlameColors.graphite,
            ),
          ),
          const SizedBox(height: 10),
          SizedBox(
            height: GlameUi.buttonHeight,
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => _openBrandCatalog(context, brand),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(
                        color: GlameColors.coldLightGrey,
                        width: GlameUi.borderWidth,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(GlameUi.radius),
                      ),
                    ),
                    child: const Text('Смотреть все изделия'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => showStylistContactSheet(
                      context,
                      initialMessage:
                          'Хочу подобрать украшения ${brand.name} с помощью стилиста.',
                      source: 'brand_page',
                      scenario: 'live_stylist',
                    ),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(
                        color: GlameColors.coldLightGrey,
                        width: GlameUi.borderWidth,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(GlameUi.radius),
                      ),
                    ),
                    child: const Text('Написать стилисту'),
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

class _BrandUseCasesInfo extends StatelessWidget {
  final List<String> items;

  const _BrandUseCasesInfo({required this.items});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'ПОДХОДИТ, ЕСЛИ ХОТИТЕ',
          style: TextStyle(
            fontSize: 13,
            letterSpacing: 2.2,
            color: GlameColors.steelGrey,
          ),
        ),
        const SizedBox(height: 14),
        Container(
          decoration: BoxDecoration(
            border: Border.all(
              color: GlameColors.coldLightGrey,
              width: GlameUi.borderWidth,
            ),
          ),
          child: Column(
            children: [
              for (var index = 0; index < items.length; index++) ...[
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Padding(
                        padding: EdgeInsets.only(top: 2),
                        child: Icon(
                          Icons.check_circle_outline,
                          size: 18,
                          color: GlameColors.steelGrey,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          items[index],
                          style: const TextStyle(
                            fontSize: 15,
                            height: 1.35,
                            color: GlameColors.graphite,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                if (index != items.length - 1)
                  Container(height: 1, color: GlameColors.coldLightGrey),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

String _brandDetailBlockKey(String brandId) => 'brand_detail_$brandId';

void _openBrandCatalog(BuildContext context, _BrandDetailData brand) {
  final uri = Uri(path: '/catalog', queryParameters: {'brand': brand.id});
  context.push(uri.toString());
}

void _trackEvent(String eventName, [Map<String, Object?>? params]) {
  debugPrint('analytics:$eventName ${params ?? const {}}');
}

_BrandDetailData? _brandById(String id) {
  for (final brand in _allBrands) {
    if (brand.id == id) return brand;
  }
  return null;
}

bool _lookHasBrandProduct(Map<String, dynamic> look, _BrandDetailData brand) {
  final raw = look['products'];
  if (raw is! List) return false;
  return raw.whereType<Map>().any((product) {
    final productBrand = _normalizeBrandText('${product['brand'] ?? ''}');
    final specBrand = product['specifications'] is Map
        ? _normalizeBrandText(
            '${(product['specifications'] as Map)['Бренд'] ?? ''}',
          )
        : '';
    final name = _normalizeBrandText('${product['name'] ?? ''}');
    final target = _normalizeBrandText(brand.searchQuery);
    return productBrand == target ||
        specBrand == target ||
        name.contains(target);
  });
}

String _normalizeBrandText(String value) {
  return value
      .trim()
      .toLowerCase()
      .replaceAll('ё', 'е')
      .replaceAll('wrinkles og time', 'wrinkles of time');
}

String? _lookImageUrl(Map<String, dynamic> item) {
  final gallery = item['look_image_urls'];
  if (gallery is List) {
    for (final entry in gallery) {
      final url = _resolveLookImageEntry(entry);
      if (url != null && url.isNotEmpty) return url;
    }
  }
  return resolveAssetUrl(item['look_image_url']) ??
      resolveAssetUrl(item['image_url']) ??
      resolveAssetUrl(item['cover_image_url']) ??
      resolveAssetUrl(item['image']);
}

String? _resolveLookImageEntry(Object? entry) {
  if (entry is Map) {
    return resolveAssetUrl(entry['url']) ??
        resolveAssetUrl(entry['image_url']) ??
        resolveAssetUrl(entry['src']);
  }
  return resolveAssetUrl(entry);
}

List<Map<String, dynamic>> _lookProducts(Map<String, dynamic> look) {
  final raw = look['products'];
  if (raw is! List) return const <Map<String, dynamic>>[];
  return raw
      .whereType<Map>()
      .map((item) => Map<String, dynamic>.from(item))
      .toList(growable: false);
}

class _BrandLookCardData {
  final String id;
  final String name;
  final String brandId;
  final String productsLabel;
  final String? imageUrl;

  const _BrandLookCardData({
    required this.id,
    required this.name,
    required this.brandId,
    required this.productsLabel,
    required this.imageUrl,
  });

  factory _BrandLookCardData.fromMap(Map<String, dynamic> item) {
    final products = _lookProducts(item);
    final productNames = products
        .map((product) => '${product['name'] ?? ''}'.trim())
        .where((name) => name.isNotEmpty)
        .take(2)
        .toList(growable: false);
    return _BrandLookCardData(
      id: '${item['id'] ?? ''}'.trim(),
      name: '${item['name'] ?? item['look_name'] ?? 'Образ GLAME'}'.trim(),
      brandId: '',
      productsLabel: productNames.isEmpty
          ? '${products.length} изделий в образе'
          : productNames.join(' + '),
      imageUrl: _lookImageUrl(item),
    );
  }
}

class _BrandShowcaseCardData {
  final String brandId;
  final String title;
  final String subtitle;
  final String? imageUrl;
  final String? imageCacheVersion;
  final int sortOrder;

  const _BrandShowcaseCardData({
    required this.brandId,
    required this.title,
    required this.subtitle,
    required this.imageUrl,
    required this.imageCacheVersion,
    required this.sortOrder,
  });

  List<Object?> get cacheSignature => [
    brandId,
    title,
    subtitle,
    imageUrl,
    imageCacheVersion,
    sortOrder,
  ];

  factory _BrandShowcaseCardData.fromBrandDetail(
    _BrandDetailData brand,
    Map<String, dynamic> slide,
  ) {
    final title = '${slide['title'] ?? ''}'.trim();
    final subtitle = '${slide['subtitle'] ?? ''}'.trim();
    return _BrandShowcaseCardData(
      brandId: brand.id,
      title: title.isEmpty ? brand.name : title,
      subtitle: subtitle.isEmpty ? brand.signature : subtitle,
      imageUrl:
          resolveAssetUrl(slide['image_url']) ??
          resolveAssetUrl(slide['background_image_url']),
      imageCacheVersion:
          '${slide['updated_at'] ?? slide['id'] ?? ''}'.trim().isEmpty
          ? null
          : '${slide['updated_at'] ?? slide['id']}',
      sortOrder: int.tryParse('${slide['sort_order'] ?? ''}') ?? 0,
    );
  }

  factory _BrandShowcaseCardData.fromMap(Map item) {
    final title = '${item['title'] ?? ''}'.trim();
    final brandId = _brandIdFromSlide(item, title);
    final fallbackBrand = _brandById(brandId);
    return _BrandShowcaseCardData(
      brandId: brandId.isEmpty ? _brandIdFromName(title) : brandId,
      title: title.isEmpty ? (fallbackBrand?.name ?? 'GLAME') : title,
      subtitle: '${item['subtitle'] ?? fallbackBrand?.signature ?? ''}'.trim(),
      imageUrl:
          resolveAssetUrl(item['image_url']) ??
          resolveAssetUrl(item['background_image_url']),
      imageCacheVersion:
          '${item['updated_at'] ?? item['id'] ?? ''}'.trim().isEmpty
          ? null
          : '${item['updated_at'] ?? item['id']}',
      sortOrder: int.tryParse('${item['sort_order'] ?? ''}') ?? 0,
    );
  }
}

String _brandIdFromSlide(Map item, String title) {
  final payload = item['image_action_payload'];
  if (payload is Map) {
    final direct =
        '${payload['brand_id'] ?? payload['brandId'] ?? payload['brand'] ?? ''}'
            .trim();
    if (direct.isNotEmpty) return _brandIdFromName(direct);
  }
  for (final key in [
    'image_action_link',
    'primary_button_link',
    'secondary_button_link',
  ]) {
    final raw = '${item[key] ?? ''}'.trim();
    final match = RegExp(r'/brand/([^/?#]+)').firstMatch(raw);
    if (match != null) return match.group(1) ?? '';
  }
  return _brandIdFromName(title);
}

class _BrandCategoryData {
  final String label;
  final String categorySlug;
  final String? typeSlug;

  const _BrandCategoryData({
    required this.label,
    required this.categorySlug,
    this.typeSlug,
  });
}

String _brandIdFromName(String value) {
  final normalized = value.trim().toLowerCase();
  for (final brand in _allBrands) {
    if (brand.name.toLowerCase() == normalized) return brand.id;
  }
  return normalized.replaceAll(' ', '-');
}

class _BrandDetailData {
  final String id;
  final String name;
  final String signature;
  final String description;
  final String searchQuery;
  final List<String> dnaMarkers;
  final List<_BrandCategoryData> categories;
  final List<String> useCases;
  final List<String> preferredCategoryOrder;

  const _BrandDetailData({
    required this.id,
    required this.name,
    required this.signature,
    required this.description,
    required this.searchQuery,
    required this.dnaMarkers,
    required this.categories,
    required this.useCases,
    required this.preferredCategoryOrder,
  });
}

const _geometryCategories = [
  _BrandCategoryData(label: 'Серьги', categorySlug: 'earrings'),
  _BrandCategoryData(label: 'Каффы', categorySlug: 'ear_cuffs'),
  _BrandCategoryData(
    label: 'Кулоны',
    categorySlug: 'necklaces',
    typeSlug: 'pendant',
  ),
  _BrandCategoryData(
    label: 'Чокеры',
    categorySlug: 'necklaces',
    typeSlug: 'choker',
  ),
  _BrandCategoryData(label: 'Браслеты', categorySlug: 'bracelets'),
  _BrandCategoryData(label: 'Броши', categorySlug: 'brooches'),
];

const _defaultCategories = [
  _BrandCategoryData(label: 'Серьги', categorySlug: 'earrings'),
  _BrandCategoryData(label: 'Каффы', categorySlug: 'ear_cuffs'),
  _BrandCategoryData(label: 'Колье', categorySlug: 'necklaces'),
  _BrandCategoryData(label: 'Браслеты', categorySlug: 'bracelets'),
];

const _defaultOrder = [
  'earrings',
  'ear_cuffs',
  'necklaces:pendant',
  'necklaces:choker',
  'bracelets',
  'brooches',
  'necklaces',
];

const List<_BrandDetailData> _allBrands = [
  _BrandDetailData(
    id: 'geometry',
    name: 'Geometry',
    signature: 'точность вместо случайности',
    description:
        'Чистая линия, спокойная форма и украшения, в которых нет ничего случайного.',
    searchQuery: 'Geometry',
    dnaMarkers: ['чистая линия', 'спокойная форма', 'собранный образ'],
    categories: _geometryCategories,
    useCases: [
      'добавить чистый акцент в повседневный образ',
      'собрать минималистичный и современный образ',
      'выбрать украшение, которое работает всегда',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'magna',
    name: 'Magna',
    signature: 'украшение с внутренней силой',
    description:
        'Форма с характером, спокойный объем и украшения, которые держат образ собранным.',
    searchQuery: 'Magna',
    dnaMarkers: ['внутренняя сила', 'собранная пластика', 'уверенный акцент'],
    categories: _defaultCategories,
    useCases: [
      'добавить в образ внутренний стержень',
      'собрать более уверенную подачу без перегруза',
      'выбрать украшение с характером',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'pearl',
    name: 'Pearl',
    signature: 'свобода быть мягкой',
    description:
        'Линия, которая помогает звучать мягко, но точно, без ощущения излишней хрупкости.',
    searchQuery: 'Pearl',
    dnaMarkers: ['мягкий жест', 'спокойный свет', 'деликатный образ'],
    categories: _defaultCategories,
    useCases: [
      'добавить мягкость без наивности',
      'сделать образ светлее и спокойнее',
      'выбрать деликатный повседневный акцент',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'crystal',
    name: 'Crystal',
    signature: 'сиять без лишней драмы',
    description:
        'Чистое сияние, собранная подача и украшения, которые работают как свет, а не как шум.',
    searchQuery: 'Crystal',
    dnaMarkers: ['чистое сияние', 'ровный блеск', 'собранный свет'],
    categories: _defaultCategories,
    useCases: [
      'добавить свет в вечерний образ',
      'выбрать украшение без визуального шума',
      'оставить эффект, но убрать драму',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'bicolor',
    name: 'Bicolor',
    signature: 'свобода сочетать без ошибки',
    description:
        'Комбинация металлов и спокойный баланс, который делает сочетания уверенными и простыми.',
    searchQuery: 'Bicolor',
    dnaMarkers: ['баланс металлов', 'гибкое сочетание', 'чистый ритм'],
    categories: _defaultCategories,
    useCases: [
      'сочетать металл без сомнений',
      'добавить универсальность в комплект',
      'собрать образ без стилистического конфликта',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'prism-of-elegance',
    name: 'Prism Of Elegance',
    signature: 'сияние с оттенком настроения',
    description:
        'Украшения, которые работают через свет, настроение и собранную декоративность без перегруза.',
    searchQuery: 'Prism Of Elegance',
    dnaMarkers: [
      'свет и настроение',
      'ровная элегантность',
      'деликатный блеск',
    ],
    categories: _defaultCategories,
    useCases: [
      'добавить настроение через блеск',
      'сделать образ более вечерним',
      'оставить элегантность без тяжести',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'unode50',
    name: 'UNOde50',
    signature: 'образ с собственным мнением',
    description:
        'Четкая подача, характерный силуэт и украшения, которые не растворяются в образе.',
    searchQuery: 'UNOde50',
    dnaMarkers: ['характер', 'личный жест', 'сильный контур'],
    categories: _defaultCategories,
    useCases: [
      'добавить образу собственное мнение',
      'сделать акцент главным элементом',
      'выбрать украшение с ярким характером',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'raganella-princess',
    name: 'Raganella Princess',
    signature: 'красота с внутренним бунтом',
    description:
        'Украшения, в которых декоративность остается живой и не превращается в предсказуемый жест.',
    searchQuery: 'Raganella Princess',
    dnaMarkers: ['живой контраст', 'внутренний бунт', 'собранная эмоция'],
    categories: _defaultCategories,
    useCases: [
      'оставить красоту, но убрать банальность',
      'добавить образу свободный жест',
      'собрать чуть более смелую стилистику',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'island-soul',
    name: 'Island Soul',
    signature: 'украшение как личный знак',
    description:
        'Линия для образов, где украшение ощущается как свой знак, а не как случайная деталь.',
    searchQuery: 'Island Soul',
    dnaMarkers: ['личный знак', 'свободный ритм', 'спокойная уникальность'],
    categories: _defaultCategories,
    useCases: [
      'выбрать знак вместо декоративного шума',
      'добавить образу личный смысл',
      'сделать комплект более живым',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'agafi',
    name: 'AGafi',
    signature: 'украшение, которое не повторится',
    description:
        'Редкость, ручное ощущение и предметность, которая работает как личная находка.',
    searchQuery: 'AGafi',
    dnaMarkers: ['редкая находка', 'живая фактура', 'личный выбор'],
    categories: _defaultCategories,
    useCases: [
      'найти неочевидный акцент',
      'собрать образ вокруг редкой вещи',
      'выбрать предметное украшение с историей',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'antura',
    name: 'Antura',
    signature: 'fashion-жест в один штрих',
    description:
        'Быстрый и точный акцент, который собирает образ без сложной стилизации.',
    searchQuery: 'Antura',
    dnaMarkers: ['fashion-жест', 'точный штрих', 'быстрый акцент'],
    categories: _defaultCategories,
    useCases: [
      'добавить модный штрих без усилия',
      'собрать образ одним жестом',
      'оставить акцент легким и современным',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'kalliope',
    name: 'Kalliope',
    signature: 'живая линия вместо правильной',
    description:
        'Пластика и линия, в которых движение важнее идеальной правильности.',
    searchQuery: 'Kalliope',
    dnaMarkers: ['живая линия', 'мягкая пластика', 'свободная форма'],
    categories: _defaultCategories,
    useCases: [
      'сделать образ менее строгим',
      'добавить живую форму в комплект',
      'уйти от слишком правильной геометрии',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'wrinkles-of-time',
    name: 'Wrinkles of Time',
    signature: 'след моря вместо глянца',
    description:
        'Фактура, в которой важны след, глубина и живое ощущение поверхности.',
    searchQuery: 'Wrinkles of Time',
    dnaMarkers: ['след моря', 'живая фактура', 'спокойная глубина'],
    categories: _defaultCategories,
    useCases: [
      'добавить в образ фактуру вместо блеска',
      'сделать акцент более живым',
      'выбрать украшение с природным ощущением',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
  _BrandDetailData(
    id: 'claudio-canzian',
    name: 'Claudio Canzian',
    signature: 'вечер, собранный в украшение',
    description:
        'Линия для более вечернего и собранного настроения без лишней тяжести.',
    searchQuery: 'Claudio Canzian',
    dnaMarkers: ['вечерний жест', 'собранный свет', 'точная элегантность'],
    categories: _defaultCategories,
    useCases: [
      'собрать вечерний образ спокойно и точно',
      'добавить элегантность без перегруза',
      'выбрать украшение для собранного выхода',
    ],
    preferredCategoryOrder: _defaultOrder,
  ),
];

const List<_BrandShowcaseCardData> _fallbackBrandShowcaseCards = [
  _BrandShowcaseCardData(
    brandId: 'unode50',
    title: 'UNOde50',
    subtitle: 'смелые формы и узнаваемый характер',
    imageUrl: _block4BackgroundAsset,
    imageCacheVersion: 'fallback-unode50',
    sortOrder: 10,
  ),
  _BrandShowcaseCardData(
    brandId: 'geometry',
    title: 'Geometry',
    subtitle: 'архитектурные формы и чистые линии',
    imageUrl: _block4BackgroundAsset,
    imageCacheVersion: 'fallback-geometry',
    sortOrder: 20,
  ),
  _BrandShowcaseCardData(
    brandId: 'antura',
    title: 'Antura',
    subtitle: 'ювелирная смола и выразительный цвет',
    imageUrl: _block4BackgroundAsset,
    imageCacheVersion: 'fallback-antura',
    sortOrder: 30,
  ),
  _BrandShowcaseCardData(
    brandId: 'agafi',
    title: 'AGafi',
    subtitle: 'украшения из натуральных камней',
    imageUrl: _block4BackgroundAsset,
    imageCacheVersion: 'fallback-agafi',
    sortOrder: 40,
  ),
];
