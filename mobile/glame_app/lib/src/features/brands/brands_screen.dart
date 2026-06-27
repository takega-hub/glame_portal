import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters/rub.dart';
import '../../core/network/asset_url.dart';
import '../../core/theme/glame_theme.dart';
import '../auth/auth_controller.dart';
import '../customer/stylist_entry.dart';
import '../home/home_api.dart';

const String _block4HeroAsset =
    'assets/images/home/home_block_4_collected_glame.png';
const String _block4BackgroundAsset =
    'assets/images/home/glame_home_block4_open_display_background.png';
const String _block4VisualAsset =
    'assets/images/home/glame_home_block4_visual_image_no_text.png';
const String _block4BrandsPageBlockKey = 'collected_glame_brands';
const double _brandsPagePadding = 28;

final _brandsApiProvider = Provider<HomeApi>((ref) {
  return HomeApi(ref.watch(apiClientProvider));
});

final homeCollectedGlameBlockProvider =
    FutureProvider<HomeBlockCollectedGlameData>((ref) async {
      String? serverImage;
      try {
        final api = ref.watch(_brandsApiProvider);
        final raw = await api.getHomeSlides(
          blockKey: _block4BrandsPageBlockKey,
        );
        final slide = raw.isNotEmpty && raw.first is Map
            ? Map<String, dynamic>.from(raw.first as Map)
            : const <String, dynamic>{};
        serverImage =
            _nonEmptyString(slide['background_image_url']) ??
            _nonEmptyString(slide['image_url']);
      } catch (_) {
        serverImage = null;
      }
      return HomeBlockCollectedGlameData(
        title: 'Собрано GLAME',
        subtitle: 'Мы отбираем главное. Чтобы вы выбирали свое.',
        ctaLabel: 'Смотреть бренды',
        backgroundImage: serverImage ?? _block4BackgroundAsset,
        visualImage: serverImage ?? _block4VisualAsset,
        useSingleImage: serverImage != null,
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

final brandsPageHeroProvider = FutureProvider<BrandsPageHeroData?>((ref) async {
  final api = ref.watch(_brandsApiProvider);
  final raw = await api.getHomeSlides(blockKey: _block4BrandsPageBlockKey);
  final slide = raw.isNotEmpty && raw.first is Map
      ? Map<String, dynamic>.from(raw.first as Map)
      : const <String, dynamic>{};
  final imageSource = '${slide['image_url'] ?? ''}'.trim();
  if (imageSource.isEmpty) {
    return null;
  }
  final title = '${slide['title'] ?? ''}'.trim();
  final subtitle = '${slide['subtitle'] ?? ''}'.trim();
  return BrandsPageHeroData(
    imageSource: imageSource,
    title: title.isEmpty ? 'Смотреть бренды' : title,
    subtitle: subtitle.isEmpty ? 'Собрано GLAME' : subtitle,
  );
});

final brandDetailHeroProvider =
    FutureProvider.family<BrandsPageHeroData?, String>((ref, brandId) async {
      final api = ref.watch(_brandsApiProvider);
      final raw = await api.getHomeSlides(
        blockKey: _brandDetailBlockKey(brandId),
      );
      final slide = raw.isNotEmpty && raw.first is Map
          ? Map<String, dynamic>.from(raw.first as Map)
          : const <String, dynamic>{};
      final imageSource = '${slide['image_url'] ?? ''}'.trim();
      if (imageSource.isEmpty) {
        return null;
      }
      return BrandsPageHeroData(
        imageSource: imageSource,
        title: '',
        subtitle: '',
      );
    });

final brandFeaturedProductsProvider =
    FutureProvider.family<List<_BrandProductCardData>, String>((
      ref,
      brandId,
    ) async {
      final brand = _brandById(brandId);
      if (brand == null) return const <_BrandProductCardData>[];

      final api = ref.watch(_brandsApiProvider);
      final raw = await api.getProductsPaged(
        skip: 0,
        limit: 100,
        search: brand.searchQuery,
        inStock: true,
        hasImages: true,
      );

      final itemsRaw = raw['items'];
      if (itemsRaw is! List) return const <_BrandProductCardData>[];

      final items = itemsRaw
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);

      final candidates = items
          .map(_BrandProductCardData.fromMap)
          .where((item) => item.id.isNotEmpty)
          .where((item) => _matchesBrand(item, brand))
          .toList(growable: false);

      final ordered = _selectFeaturedProducts(candidates, brand);
      return ordered.take(6).toList(growable: false);
    });

class HomeBlockCollectedGlameData {
  final String title;
  final String subtitle;
  final String ctaLabel;
  final String? backgroundImage;
  final String visualImage;
  final bool useSingleImage;
  final List<String> brandNames;

  const HomeBlockCollectedGlameData({
    required this.title,
    required this.subtitle,
    required this.ctaLabel,
    required this.backgroundImage,
    required this.visualImage,
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
    final dataAsync = widget.data == null
        ? ref.watch(homeCollectedGlameBlockProvider)
        : AsyncValue.data(widget.data!);

    return dataAsync.when(
      data: (data) {
        _trackViewOnce();
        return _HomeCollectedGlameBlockContent(
          data: data,
          viewportHeight: widget.viewportHeight,
          onCtaPressed: () {
            _trackBlock4Event('home_block4_brands_click');
            widget.onCtaPressed();
          },
        );
      },
      loading: () => const _HomeCollectedGlameBlockSkeleton(),
      error: (_, _) => const SizedBox.shrink(),
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

class _HomeCollectedGlameBlockContent extends StatelessWidget {
  final HomeBlockCollectedGlameData data;
  final VoidCallback onCtaPressed;
  final double? viewportHeight;

  const _HomeCollectedGlameBlockContent({
    required this.data,
    required this.onCtaPressed,
    this.viewportHeight,
  });

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    final compact = viewportHeight != null;
    final targetHeight = viewportHeight;
    final topBarBottom =
        MediaQuery.of(context).padding.top +
        GlameUi.heroTopOffset +
        GlameUi.heroTopBarHeight;
    final contentWidth = width - (GlameUi.pagePadding * 2);
    final compactBrandSectionHeight = compact ? 270.0 : 0.0;
    final heroHeight = compact
        ? ((targetHeight ?? 760) - compactBrandSectionHeight).clamp(
            360.0,
            520.0,
          )
        : data.useSingleImage
        ? (contentWidth * 1.52).clamp(520.0, 980.0)
        : (contentWidth * 1.5).clamp(430.0, 560.0);
    final heroTopPadding = compact
        ? topBarBottom + 24.0
        : data.useSingleImage
        ? (width < 420 ? 44.0 : 56.0)
        : (width < 420 ? 58.0 : 72.0);
    final titleMaxWidth = contentWidth * (width < 420 ? 0.84 : 0.72);
    final subtitleMaxWidth = contentWidth * (width < 420 ? 0.58 : 0.62);
    final ctaWidth = compact ? 164.0 : (width < 420 ? 168.0 : 205.0);

    return Semantics(
      label: data.title,
      child: Container(
        height: targetHeight,
        width: double.infinity,
        color: GlameColors.graphite,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              height: heroHeight,
              child: Stack(
                children: [
                  if (data.useSingleImage)
                    Positioned.fill(
                      child: _Block4ImageLayer(
                        source: data.visualImage,
                        fit: BoxFit.cover,
                        alignment: Alignment.topCenter,
                      ),
                    ),
                  if (!data.useSingleImage) ...[
                    Positioned.fill(
                      child: _Block4ImageLayer(
                        source: data.backgroundImage ?? _block4BackgroundAsset,
                        fit: BoxFit.cover,
                        alignment: Alignment.center,
                      ),
                    ),
                    Positioned(
                      right: 0,
                      top: 210,
                      bottom: 0,
                      width: width * 0.72,
                      child: IgnorePointer(
                        child: _Block4ImageLayer(
                          source: data.visualImage,
                          fit: BoxFit.cover,
                          alignment: Alignment.centerRight,
                        ),
                      ),
                    ),
                  ],
                  Positioned.fill(
                    child: IgnorePointer(
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.centerLeft,
                            end: Alignment.centerRight,
                            colors: [
                              GlameColors.graphite.withValues(alpha: 0.96),
                              GlameColors.graphite.withValues(alpha: 0.66),
                              GlameColors.graphite.withValues(alpha: 0.16),
                            ],
                            stops: data.useSingleImage
                                ? const [0.0, 0.34, 0.78]
                                : const [0.0, 0.38, 0.78],
                          ),
                        ),
                      ),
                    ),
                  ),
                  Padding(
                    padding: EdgeInsets.fromLTRB(
                      GlameUi.pagePadding,
                      heroTopPadding,
                      GlameUi.pagePadding,
                      28,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        ConstrainedBox(
                          constraints: BoxConstraints(maxWidth: titleMaxWidth),
                          child: Text(
                            data.title,
                            style: TextStyle(
                              fontSize: compact ? 34 : 44,
                              height: 1.06,
                              letterSpacing: 0,
                              color: GlameColors.whiteGlame,
                              fontWeight: FontWeight.w300,
                            ),
                          ),
                        ),
                        SizedBox(height: compact ? 18 : 28),
                        ConstrainedBox(
                          constraints: BoxConstraints(
                            maxWidth: subtitleMaxWidth,
                          ),
                          child: Text(
                            data.subtitle,
                            style: TextStyle(
                              fontSize: compact ? 18 : 23,
                              height: 1.38,
                              letterSpacing: 0,
                              color: GlameColors.steelGray,
                              fontWeight: FontWeight.w300,
                            ),
                          ),
                        ),
                        SizedBox(height: compact ? 20 : 34),
                        SizedBox(
                          height: compact ? 48 : GlameUi.buttonHeight,
                          width: ctaWidth,
                          child: OutlinedButton(
                            onPressed: onCtaPressed,
                            style: OutlinedButton.styleFrom(
                              minimumSize: const Size.fromHeight(
                                GlameUi.minTapTarget,
                              ),
                              side: const BorderSide(
                                color: GlameColors.whiteGlame,
                                width: GlameUi.borderWidth,
                              ),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(
                                  GlameUi.radius,
                                ),
                              ),
                              padding: EdgeInsets.zero,
                            ),
                            child: Text(
                              data.ctaLabel,
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontSize: compact ? 16 : 18,
                                height: 1.0,
                                letterSpacing: 0,
                                color: GlameColors.whiteGlame,
                                fontWeight: FontWeight.w300,
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
            Padding(
              padding: EdgeInsets.fromLTRB(
                GlameUi.pagePadding,
                compact ? 8 : 14,
                GlameUi.pagePadding,
                compact ? 18 : 30,
              ),
              child: _Block4BrandsGrid(
                brands: data.brandNames,
                compact: compact,
                onBrandTap: (brandName) {
                  final brandId = _brandIdFromName(brandName);
                  if (brandId.isEmpty) return;
                  context.push('/brand/$brandId');
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HomeCollectedGlameBlockSkeleton extends StatelessWidget {
  const _HomeCollectedGlameBlockSkeleton();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: GlameColors.surface2,
      padding: const EdgeInsets.fromLTRB(
        _brandsPagePadding,
        0,
        _brandsPagePadding,
        36,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: const [
          _CollectedGlameSkeletonBox(height: 38, width: 240),
          SizedBox(height: 18),
          _CollectedGlameSkeletonBox(height: 52, width: 310),
          SizedBox(height: 28),
          AspectRatio(
            aspectRatio: 941 / 1672,
            child: _CollectedGlameSkeletonBox(),
          ),
          SizedBox(height: 16),
          SizedBox(
            height: GlameUi.buttonHeight,
            child: _CollectedGlameSkeletonBox(),
          ),
          SizedBox(height: 20),
          _CollectedGlameSkeletonBox(height: 92),
        ],
      ),
    );
  }
}

class _CollectedGlameSkeletonBox extends StatelessWidget {
  final double? width;
  final double? height;

  const _CollectedGlameSkeletonBox({this.width, this.height});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        width: width,
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
  final BoxFit fit;
  final Alignment alignment;

  const _Block4ImageLayer({
    required this.source,
    required this.fit,
    required this.alignment,
  });

  @override
  Widget build(BuildContext context) {
    final resolvedSource = resolveAssetUrl(source) ?? source;
    if (resolvedSource.startsWith('http://') ||
        resolvedSource.startsWith('https://')) {
      return CachedNetworkImage(
        imageUrl: resolvedSource,
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

class _Block4BrandsGrid extends StatelessWidget {
  final List<String> brands;
  final ValueChanged<String> onBrandTap;
  final bool compact;

  const _Block4BrandsGrid({
    required this.brands,
    required this.onBrandTap,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    final rows = compact
        ? <List<String>>[
            brands.take(4).toList(growable: false),
            brands.skip(4).take(3).toList(growable: false),
            brands.skip(7).take(3).toList(growable: false),
            brands.skip(10).take(2).toList(growable: false),
            brands.skip(12).take(2).toList(growable: false),
          ]
        : <List<String>>[
            brands.take(5).toList(growable: false),
            brands.skip(5).take(3).toList(growable: false),
            brands.skip(8).take(4).toList(growable: false),
            brands.skip(12).take(2).toList(growable: false),
          ];

    return Column(
      children: [
        for (var i = 0; i < rows.length; i++) ...[
          if (i > 0) const _Block4ThinDivider(),
          SizedBox(
            height: compact ? 58 : 60,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: _buildRowChildren(rows[i]),
            ),
          ),
        ],
      ],
    );
  }

  List<Widget> _buildRowChildren(List<String> row) {
    final children = <Widget>[];
    final itemPadding = EdgeInsets.symmetric(
      horizontal: compact ? 4 : 10,
      vertical: compact ? 6 : 10,
    );
    for (var i = 0; i < row.length; i++) {
      children.add(
        Flexible(
          child: InkWell(
            onTap: () => onBrandTap(row[i]),
            child: Padding(
              padding: itemPadding,
              child: Text(
                row[i],
                textAlign: TextAlign.center,
                softWrap: true,
                style: TextStyle(
                  fontSize: compact ? 12 : 16,
                  height: compact ? 1.12 : 1.15,
                  letterSpacing: 0,
                  color: GlameColors.whiteGlame,
                  fontWeight: FontWeight.w300,
                ),
              ),
            ),
          ),
        ),
      );
      if (i < row.length - 1) {
        children.add(
          Container(width: 1, height: 22, color: GlameColors.borderGray),
        );
      }
    }
    return children;
  }
}

class _Block4ThinDivider extends StatelessWidget {
  const _Block4ThinDivider();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 1,
      color: GlameColors.borderGray.withValues(alpha: 0.85),
    );
  }
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
      appBar: const GlameTopAppBar(),
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
                return _BrandsPageHeroCard(
                  imageSource: hero.imageSource,
                  title: hero.title,
                  subtitle: hero.subtitle,
                );
              },
              loading: () => const _CollectedGlameSkeletonBox(height: 220),
              error: (_, _) => const Column(
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
              ),
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
    final featuredAsync = ref.watch(brandFeaturedProductsProvider(brand.id));
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _trackEvent('brand_page_view', {'brand_id': brand.id});
    });

    return Scaffold(
      appBar: const GlameTopAppBar(),
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
            _BrandHeroCard(
              brand: brand,
              heroImageSource:
                  heroAsync.valueOrNull?.imageSource ?? _block4HeroAsset,
            ),
            const SizedBox(height: 16),
            _BrandDnaStrip(markers: brand.dnaMarkers),
            const SizedBox(height: 16),
            _BrandCategoryBar(brand: brand),
            const SizedBox(height: 24),
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
              data: (products) {
                if (products.isEmpty) {
                  return _BrandEmptyState(brand: brand);
                }
                return _BrandFeaturedProductsGrid(products: products);
              },
              loading: () => const _BrandDetailLoadingState(),
              error: (_, _) => _BrandErrorState(brand: brand),
            ),
            const SizedBox(height: 24),
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

class _BrandHeroCard extends StatelessWidget {
  final _BrandDetailData brand;
  final String heroImageSource;

  const _BrandHeroCard({required this.brand, required this.heroImageSource});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: Border.all(
          color: GlameColors.coldLightGrey,
          width: GlameUi.borderWidth,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            decoration: const BoxDecoration(color: GlameColors.white),
            child: AspectRatio(
              aspectRatio: 941 / 1672,
              child: _Block4ImageLayer(
                source: heroImageSource,
                fit: BoxFit.contain,
                alignment: Alignment.topCenter,
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  brand.name,
                  style: const TextStyle(
                    fontSize: 40,
                    height: 0.98,
                    color: GlameColors.graphite,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  brand.signature,
                  style: const TextStyle(
                    fontSize: 18,
                    height: 1.35,
                    color: GlameColors.steelGrey,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  brand.description,
                  style: const TextStyle(
                    fontSize: 16,
                    height: 1.45,
                    color: GlameColors.graphite,
                  ),
                ),
                const SizedBox(height: 18),
                SizedBox(
                  height: GlameUi.buttonHeight,
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: () {
                      _trackEvent('brand_all_products_click', {
                        'brand_id': brand.id,
                      });
                      _openBrandCatalog(context, brand);
                    },
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size.fromHeight(GlameUi.minTapTarget),
                      side: const BorderSide(
                        color: GlameColors.coldLightGrey,
                        width: GlameUi.borderWidth,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(GlameUi.radius),
                      ),
                    ),
                    child: Text(
                      'Смотреть все изделия ${brand.name}',
                      style: const TextStyle(
                        fontSize: 17,
                        color: GlameColors.graphite,
                      ),
                    ),
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
              padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
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

class _BrandCategoryBar extends StatelessWidget {
  final _BrandDetailData brand;

  const _BrandCategoryBar({required this.brand});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'КАТЕГОРИИ',
          style: TextStyle(
            fontSize: 13,
            letterSpacing: 2.2,
            color: GlameColors.steelGrey,
          ),
        ),
        const SizedBox(height: 14),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (var index = 0; index < brand.categories.length; index++) ...[
                _BrandCategoryChip(item: brand.categories[index], brand: brand),
                if (index != brand.categories.length - 1)
                  const SizedBox(width: 10),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _BrandCategoryChip extends StatelessWidget {
  final _BrandCategoryData item;
  final _BrandDetailData brand;

  const _BrandCategoryChip({required this.item, required this.brand});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () {
        _trackEvent('brand_category_click', {
          'brand_id': brand.id,
          'category': item.categorySlug,
          if (item.typeSlug != null) 'type': item.typeSlug,
        });
        _openBrandCategory(context, brand, item);
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          border: Border.all(
            color: GlameColors.coldLightGrey,
            width: GlameUi.borderWidth,
          ),
        ),
        child: Text(
          item.label,
          style: const TextStyle(
            fontSize: 15,
            height: 1.2,
            color: GlameColors.graphite,
          ),
        ),
      ),
    );
  }
}

class _BrandFeaturedProductsGrid extends StatelessWidget {
  final List<_BrandProductCardData> products;

  const _BrandFeaturedProductsGrid({required this.products});

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: products.length,
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        childAspectRatio: 0.74,
      ),
      itemBuilder: (context, index) {
        return _BrandFeaturedProductCard(product: products[index]);
      },
    );
  }
}

class _BrandFeaturedProductCard extends StatelessWidget {
  final _BrandProductCardData product;

  const _BrandFeaturedProductCard({required this.product});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () {
        _trackEvent('brand_featured_product_click', {
          'brand_id': product.brandId,
          'product_id': product.id,
        });
        context.push('/product/${product.id}');
      },
      child: Container(
        decoration: BoxDecoration(
          border: Border.all(
            color: GlameColors.coldLightGrey,
            width: GlameUi.borderWidth,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AspectRatio(
              aspectRatio: 1.08,
              child: Container(
                width: double.infinity,
                color: GlameColors.coldLightGrey,
                clipBehavior: Clip.hardEdge,
                decoration: const BoxDecoration(
                  color: GlameColors.coldLightGrey,
                ),
                child: product.imageUrl == null
                    ? const ColoredBox(color: GlameColors.coldLightGrey)
                    : CachedNetworkImage(
                        imageUrl: product.imageUrl!,
                        width: double.infinity,
                        height: double.infinity,
                        fit: BoxFit.cover,
                        alignment: Alignment.center,
                        placeholder: (context, _) =>
                            const ColoredBox(color: GlameColors.coldLightGrey),
                        errorWidget: (context, _, _) =>
                            const ColoredBox(color: GlameColors.coldLightGrey),
                      ),
              ),
            ),
            Container(height: 1, color: GlameColors.coldLightGrey),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    product.name,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 15,
                      height: 1.25,
                      color: GlameColors.graphite,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    formatRubFromKopeks(product.price),
                    style: const TextStyle(
                      fontSize: 16,
                      height: 1.2,
                      color: GlameColors.graphite,
                    ),
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

void _openBrandCategory(
  BuildContext context,
  _BrandDetailData brand,
  _BrandCategoryData category,
) {
  final uri = Uri(
    path: '/catalog',
    queryParameters: {
      'brand': brand.id,
      'category': category.categorySlug,
      if (category.typeSlug != null) 'type': category.typeSlug,
    },
  );
  context.push(uri.toString());
}

List<_BrandProductCardData> _selectFeaturedProducts(
  List<_BrandProductCardData> items,
  _BrandDetailData brand,
) {
  final ranked = [...items];
  ranked.sort(
    (a, b) => _featuredProductScore(
      b,
      brand,
    ).compareTo(_featuredProductScore(a, brand)),
  );

  final result = <_BrandProductCardData>[];
  final usedCategories = <String>{};

  for (final item in ranked) {
    final normalized = _normalizeBrandCategory(item);
    if (!usedCategories.contains(normalized)) {
      result.add(item);
      usedCategories.add(normalized);
    }
    if (result.length >= 4) break;
  }

  for (final item in ranked) {
    if (result.any((x) => x.id == item.id)) continue;
    result.add(item);
    if (result.length >= 6) break;
  }

  return result;
}

int _featuredProductScore(_BrandProductCardData item, _BrandDetailData brand) {
  final normalized = _normalizeBrandCategory(item);
  final preferredIndex = brand.preferredCategoryOrder.indexOf(normalized);
  final categoryScore = preferredIndex == -1 ? 0 : (30 - preferredIndex * 3);
  final imageScore = item.imageUrl == null ? 0 : 20;
  final priceScore = item.price > 0 ? 8 : 0;
  final nameScore = item.name.length > 22 ? 4 : 2;
  return categoryScore + imageScore + priceScore + nameScore;
}

bool _matchesBrand(_BrandProductCardData item, _BrandDetailData brand) {
  final haystack = '${item.brand} ${item.name} ${item.category}'.toLowerCase();
  return haystack.contains(brand.searchQuery.toLowerCase());
}

String _normalizeBrandCategory(_BrandProductCardData item) {
  final haystack = '${item.category} ${item.name}'.toLowerCase();
  if (haystack.contains('кафф')) return 'ear_cuffs';
  if (haystack.contains('серьг')) return 'earrings';
  if (haystack.contains('брош')) return 'brooches';
  if (haystack.contains('брасл')) return 'bracelets';
  if (haystack.contains('чокер')) return 'necklaces:choker';
  if (haystack.contains('кулон') || haystack.contains('подвес')) {
    return 'necklaces:pendant';
  }
  if (haystack.contains('колье')) return 'necklaces';
  return 'other';
}

String? _productImageUrl(Map<String, dynamic> item) {
  final imagesRaw = item['images'];
  if (imagesRaw is List) {
    for (final entry in imagesRaw) {
      final url = resolveAssetUrl(entry);
      if (url != null && url.isNotEmpty) return url;
    }
  }
  return resolveAssetUrl(item['image']) ??
      resolveAssetUrl(item['image_url']) ??
      resolveAssetUrl(item['photo']);
}

_BrandDetailData? _brandById(String id) {
  for (final brand in _allBrands) {
    if (brand.id == id) return brand;
  }
  return null;
}

class _BrandProductCardData {
  final String id;
  final String name;
  final String brandId;
  final String brand;
  final String category;
  final int price;
  final String? imageUrl;

  const _BrandProductCardData({
    required this.id,
    required this.name,
    required this.brandId,
    required this.brand,
    required this.category,
    required this.price,
    required this.imageUrl,
  });

  factory _BrandProductCardData.fromMap(Map<String, dynamic> item) {
    final priceRaw = item['price'];
    final price = priceRaw is int
        ? priceRaw
        : (priceRaw is num ? priceRaw.toInt() : 0);
    return _BrandProductCardData(
      id: '${item['id'] ?? ''}'.trim(),
      name: '${item['name'] ?? 'Изделие'}'.trim(),
      brandId: _brandIdFromName('${item['brand'] ?? ''}'.trim()),
      brand: '${item['brand'] ?? ''}'.trim(),
      category: '${item['category'] ?? ''}'.trim(),
      price: price,
      imageUrl: _productImageUrl(item),
    );
  }
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
