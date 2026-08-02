import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/network/asset_url.dart';
import '../../core/theme/glame_theme.dart';
import '../customer/stylist_entry.dart';
import '../home/home_providers.dart';

const String _homeBlock5BackgroundAsset =
    'assets/images/home/glame_home_block5_background_underlay.png';

class HomeSpacesBlock extends ConsumerStatefulWidget {
  final double? viewportHeight;

  const HomeSpacesBlock({super.key, this.viewportHeight});

  @override
  ConsumerState<HomeSpacesBlock> createState() => _HomeSpacesBlockState();
}

class _HomeSpacesBlockState extends ConsumerState<HomeSpacesBlock> {
  late final PageController _pageController;
  Timer? _autoTimer;
  int _currentPage = 0;
  int _slideCount = 0;
  bool _isUserInteracting = false;
  static const _autoDelay = Duration(seconds: 5);

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
  }

  @override
  void dispose() {
    _autoTimer?.cancel();
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final storesAsync = ref.watch(homeStoresProvider);
    final spaces = storesAsync.maybeWhen(
      data: _parseSpaces,
      orElse: () => _fallbackSpaces,
    );
    final items = spaces.isEmpty ? _fallbackSpaces : spaces;
    _syncAutoScroll(items.length);
    final compact = widget.viewportHeight != null;
    final targetHeight = widget.viewportHeight;
    final topBarBottom =
        MediaQuery.of(context).padding.top +
        GlameUi.heroTopOffset +
        GlameUi.heroTopBarHeight;
    final topPadding = compact ? topBarBottom + 20.0 : 74.0;
    final bottomPadding = compact ? 22.0 : 54.0;
    final horizontalPadding = compact ? 22.0 : 32.0;
    final headerGap = compact ? 16.0 : 28.0;
    final viewport = MediaQuery.of(context).size;
    final height = targetHeight ?? viewport.height.clamp(760.0, 920.0);
    final cardHeight = (height - topPadding - bottomPadding - 92 - headerGap)
        .clamp(compact ? 520.0 : 560.0, height);

    return Container(
      height: height,
      width: double.infinity,
      color: GlameColors.nearBlack,
      child: Stack(
        children: [
          Positioned.fill(
            child: IgnorePointer(
              child: Opacity(
                opacity: 0.16,
                child: Image.asset(
                  _homeBlock5BackgroundAsset,
                  fit: BoxFit.cover,
                  alignment: Alignment.topCenter,
                ),
              ),
            ),
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(
              horizontalPadding,
              topPadding,
              horizontalPadding,
              bottomPadding,
            ),
            child: Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 860),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _SpacesHeader(
                      compact: compact,
                      dark: true,
                      cities: items.map((item) => item.city).toList(),
                    ),
                    SizedBox(height: headerGap),
                    Expanded(
                      child: SizedBox(
                        height: cardHeight,
                        child: Stack(
                          fit: StackFit.expand,
                          children: [
                            Listener(
                              onPointerDown: (_) => _pauseAutoScroll(),
                              onPointerUp: (_) => _resumeAutoScroll(),
                              onPointerCancel: (_) => _resumeAutoScroll(),
                              child: PageView.builder(
                                controller: _pageController,
                                itemCount: items.length,
                                onPageChanged: (index) {
                                  if (!mounted) return;
                                  setState(() => _currentPage = index);
                                  _scheduleAutoScroll();
                                },
                                itemBuilder: (context, index) {
                                  return _HomeSpaceSlideCard(
                                    space: items[index],
                                    compact: compact,
                                    pageIndex: index,
                                    pageCount: items.length,
                                  );
                                },
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    if (items.length > 1) ...[
                      const SizedBox(height: 16),
                      _SpacesSliderIndicator(
                        currentIndex: _currentPage.clamp(0, items.length - 1),
                        count: items.length,
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _syncAutoScroll(int count) {
    if (_slideCount == count) return;
    _slideCount = count;
    if (_currentPage >= count && count > 0) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        setState(() => _currentPage = count - 1);
      });
    }
    _scheduleAutoScroll();
  }

  void _scheduleAutoScroll() {
    _autoTimer?.cancel();
    if (_slideCount <= 1 || _isUserInteracting) return;
    _autoTimer = Timer(_autoDelay, () {
      if (!mounted || !_pageController.hasClients) return;
      final next = (_currentPage + 1) % _slideCount;
      _pageController.animateToPage(
        next,
        duration: const Duration(milliseconds: 420),
        curve: Curves.easeOutCubic,
      );
    });
  }

  void _pauseAutoScroll() {
    _isUserInteracting = true;
    _autoTimer?.cancel();
  }

  void _resumeAutoScroll() {
    _isUserInteracting = false;
    _scheduleAutoScroll();
  }
}

class StoresScreen extends ConsumerWidget {
  final bool showAppBar;

  const StoresScreen({super.key, this.showAppBar = true});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final storesAsync = ref.watch(homeStoresProvider);
    return Scaffold(
      backgroundColor: GlameColors.surface2,
      appBar: showAppBar ? const GlameTopAppBar() : null,
      body: SafeArea(
        top: false,
        child: storesAsync.when(
          data: (raw) {
            final spaces = _parseSpaces(raw);
            final items = spaces.isEmpty ? _fallbackSpaces : spaces;
            return RefreshIndicator(
              color: GlameColors.textPrimary,
              onRefresh: () async => ref.refresh(homeStoresProvider.future),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
                children: [
                  const Text(
                    'ПРОСТРАНСТВА GLAME',
                    style: TextStyle(
                      fontSize: 18,
                      letterSpacing: 0.2,
                      color: GlameColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 18),
                  _SpacesHeader(
                    cities: items.map((item) => item.city).toList(),
                  ),
                  const SizedBox(height: 28),
                  for (var i = 0; i < items.length; i++) ...[
                    _HomeSpaceCard(space: items[i]),
                    if (i != items.length - 1) const SizedBox(height: 18),
                  ],
                ],
              ),
            );
          },
          loading: () => const Center(
            child: CircularProgressIndicator(color: GlameColors.textPrimary),
          ),
          error: (_, _) => const _SpacesLoadError(),
        ),
      ),
    );
  }
}

class SpaceDetailScreen extends ConsumerWidget {
  final String slug;

  const SpaceDetailScreen({super.key, required this.slug});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final storesAsync = ref.watch(homeStoresProvider);
    return Scaffold(
      backgroundColor: GlameColors.surface2,
      body: SafeArea(
        child: storesAsync.when(
          data: (raw) {
            final spaces = _parseSpaces(raw);
            final space = spaces.firstWhere(
              (item) => item.slug == slug,
              orElse: () => _fallbackSpaces.firstWhere(
                (item) => item.slug == slug,
                orElse: () => _fallbackSpaces.first,
              ),
            );
            final copy = _copyForSpace(space);
            final palette = _spacePaletteFor(space.slug);
            return ListView(
              padding: EdgeInsets.zero,
              children: [
                _SpaceHero(space: space, copy: copy),
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 760),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Пространство GLAME',
                            style: Theme.of(context).textTheme.titleLarge
                                ?.copyWith(
                                  color: GlameColors.textPrimary,
                                  fontWeight: FontWeight.w400,
                                ),
                          ),
                          const SizedBox(height: 14),
                          Text(
                            copy.detailDescription,
                            style: const TextStyle(
                              fontSize: 16,
                              height: 1.55,
                              color: GlameColors.steelGray,
                            ),
                          ),
                          const SizedBox(height: 28),
                          _SpaceCtaButton(
                            label: 'Построить маршрут',
                            filled: true,
                            palette: palette,
                            onPressed: space.point == null
                                ? null
                                : () => _openMaps(space),
                          ),
                          const SizedBox(height: 12),
                          _SpaceCtaButton(
                            label: 'Написать стилисту',
                            palette: palette,
                            onPressed: () => _openStoreChat(context, space),
                          ),
                          const SizedBox(height: 12),
                          _SpaceCtaButton(
                            label: copy.catalogButtonLabel,
                            palette: palette,
                            onPressed: () => _openCatalog(context, space),
                          ),
                          const SizedBox(height: 34),
                          Text(
                            'Внутри пространства',
                            style: Theme.of(context).textTheme.titleMedium
                                ?.copyWith(
                                  color: GlameColors.textPrimary,
                                  fontWeight: FontWeight.w400,
                                ),
                          ),
                          const SizedBox(height: 14),
                          _SpaceGallery(space: space),
                          const SizedBox(height: 34),
                          Text(
                            'Сервисные смыслы',
                            style: Theme.of(context).textTheme.titleMedium
                                ?.copyWith(
                                  color: GlameColors.textPrimary,
                                  fontWeight: FontWeight.w400,
                                ),
                          ),
                          const SizedBox(height: 14),
                          for (final item in copy.serviceMeanings) ...[
                            _ServiceMeaningTile(item: item, palette: palette),
                            const SizedBox(height: 10),
                          ],
                          const SizedBox(height: 28),
                          _SpaceCtaButton(
                            label: 'Вернуться к пространствам',
                            leadingIcon: Icons.arrow_back,
                            palette: palette,
                            onPressed: () => context.go('/spaces'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            );
          },
          loading: () => const Center(
            child: CircularProgressIndicator(color: GlameColors.textPrimary),
          ),
          error: (_, _) => const _SpacesLoadError(),
        ),
      ),
    );
  }
}

class _SpacesHeader extends StatelessWidget {
  final bool compact;
  final bool dark;
  final List<String>? cities;

  const _SpacesHeader({this.compact = false, this.dark = false, this.cities});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text.rich(
          TextSpan(
            children: [
              TextSpan(text: compact ? 'Пространства ' : 'Пространства\n'),
              TextSpan(
                text: 'GLAME',
                style: TextStyle(letterSpacing: compact ? 0 : 2.6),
              ),
            ],
          ),
          style: TextStyle(
            fontSize: compact ? 20 : 46,
            height: 1.05,
            letterSpacing: 0,
            color: dark ? GlameColors.whiteGlame : GlameColors.graphite,
            fontWeight: FontWeight.w300,
          ),
        ),
        SizedBox(height: compact ? 8 : 22),
        Text(
          _citySummary(cities),
          style: TextStyle(
            fontSize: compact ? 13 : 20,
            height: 1.3,
            color: dark ? GlameColors.steelGray : GlameColors.graphite,
            fontWeight: FontWeight.w300,
          ),
        ),
      ],
    );
  }
}

String _citySummary(List<String>? cities) {
  final unique = <String>[];
  for (final city in cities ?? const <String>[]) {
    final value = city.trim();
    if (value.isNotEmpty && !unique.contains(value)) {
      unique.add(value);
    }
  }
  if (unique.isEmpty) return 'Ялта и Симферополь';
  if (unique.length == 1) return unique.first;
  if (unique.length == 2) return '${unique.first} и ${unique.last}';
  return '${unique.take(unique.length - 1).join(', ')} и ${unique.last}';
}

class _HomeSpaceCard extends StatelessWidget {
  final _SpaceStoreData space;

  const _HomeSpaceCard({required this.space});

  @override
  Widget build(BuildContext context) {
    final copy = _copyForSpace(space);
    return InkWell(
      onTap: () {
        _trackSpacesEvent('home_block5_space_click', {
          'screen': 'home',
          'block': 'spaces_glame',
          'space': space.slug,
          'cta': 'view_space',
        });
        context.push('/spaces/${space.slug}');
      },
      child: Semantics(
        button: true,
        label: 'Смотреть пространство ${copy.cityLabel}',
        child: LayoutBuilder(
          builder: (context, constraints) {
            final narrow = constraints.maxWidth < 560;
            final cardHeight = narrow ? 406.0 : 392.0;
            final citySize = narrow ? 28.0 : 33.0;
            final addressSize = narrow ? 14.0 : 16.0;
            final descriptionSize = narrow ? 13.0 : 15.0;
            final verticalGap = narrow ? 24.0 : 34.0;
            final textPadding = narrow
                ? const EdgeInsets.fromLTRB(20, 24, 14, 22)
                : const EdgeInsets.fromLTRB(28, 32, 18, 28);
            final ctaWidth = narrow ? 154.0 : 176.0;
            final cardImageUrl = space.cardImageUrl;

            return SizedBox(
              width: double.infinity,
              height: cardHeight,
              child: Material(
                color: Colors.white.withValues(alpha: 0.72),
                child: Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: const Color(0xFFC7C9CB)),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(
                        flex: narrow ? 43 : 39,
                        child: Padding(
                          padding: textPadding,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                copy.cityLabel,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: citySize,
                                  height: 1.08,
                                  letterSpacing: 0,
                                  color: GlameColors.graphite,
                                  fontWeight: FontWeight.w300,
                                ),
                              ),
                              SizedBox(height: verticalGap),
                              Text(
                                copy.cardAddressLines.join('\n'),
                                overflow: TextOverflow.visible,
                                style: TextStyle(
                                  fontSize: addressSize,
                                  height: 1.45,
                                  color: GlameColors.graphite,
                                  fontWeight: FontWeight.w300,
                                ),
                              ),
                              SizedBox(height: narrow ? 22 : 30),
                              Container(
                                width: 36,
                                height: 1,
                                color: GlameColors.graphite,
                              ),
                              const Spacer(),
                              Text(
                                copy.cardDescriptionLines.join('\n'),
                                overflow: TextOverflow.visible,
                                style: TextStyle(
                                  fontSize: descriptionSize,
                                  height: 1.35,
                                  color: GlameColors.graphite,
                                  fontWeight: FontWeight.w300,
                                ),
                              ),
                              SizedBox(height: narrow ? 18 : 24),
                              SizedBox(
                                width: ctaWidth,
                                child: Container(
                                  height: narrow ? 40 : 44,
                                  alignment: Alignment.center,
                                  decoration: BoxDecoration(
                                    border: Border.all(
                                      color: GlameColors.graphite,
                                    ),
                                  ),
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 12,
                                  ),
                                  child: Text(
                                    'Смотреть пространство',
                                    style: TextStyle(
                                      fontSize: narrow ? 12 : 13,
                                      height: 1,
                                      color: GlameColors.graphite,
                                      fontWeight: FontWeight.w300,
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      Expanded(
                        flex: narrow ? 57 : 61,
                        child: ClipRect(
                          child: _NetworkStoreImage(url: cardImageUrl),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _HomeSpaceSlideCard extends StatelessWidget {
  final _SpaceStoreData space;
  final bool compact;
  final int pageIndex;
  final int pageCount;

  const _HomeSpaceSlideCard({
    required this.space,
    required this.compact,
    required this.pageIndex,
    required this.pageCount,
  });

  @override
  Widget build(BuildContext context) {
    final copy = _copyForSpace(space);
    final imageUrl = space.heroImageUrl ?? space.cardImageUrl;
    final titleSize = compact ? 44.0 : 58.0;
    final subtitleSize = compact ? 15.0 : 18.0;
    final descriptionSize = compact ? 14.0 : 16.0;
    final contentPadding = compact
        ? const EdgeInsets.fromLTRB(22, 28, 22, 26)
        : const EdgeInsets.fromLTRB(34, 40, 34, 34);

    return Padding(
      padding: EdgeInsets.zero,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () {
            _trackSpacesEvent('home_block5_space_click', {
              'screen': 'home',
              'block': 'spaces_glame',
              'space': space.slug,
              'cta': 'view_space',
            });
            context.push('/spaces/${space.slug}');
          },
          child: Semantics(
            button: true,
            label: 'Смотреть пространство ${copy.cityLabel}',
            child: ClipRect(
              child: Stack(
                fit: StackFit.expand,
                children: [
                  _NetworkStoreImage(url: imageUrl),
                  DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.black.withValues(alpha: 0.12),
                          Colors.black.withValues(alpha: 0.35),
                          Colors.black.withValues(alpha: 0.78),
                        ],
                        stops: const [0, 0.45, 1],
                      ),
                    ),
                  ),
                  Positioned(
                    left: 0,
                    right: 0,
                    bottom: 0,
                    child: Padding(
                      padding: contentPadding,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            '${(pageIndex + 1).toString().padLeft(2, '0')} / ${pageCount.toString().padLeft(2, '0')}',
                            style: TextStyle(
                              fontSize: compact ? 12 : 13,
                              letterSpacing: 1.4,
                              color: Colors.white.withValues(alpha: 0.72),
                              fontWeight: FontWeight.w400,
                            ),
                          ),
                          const SizedBox(height: 12),
                          Text(
                            copy.heroTitle,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: titleSize,
                              height: 0.96,
                              letterSpacing: 0,
                              color: Colors.white,
                              fontWeight: FontWeight.w300,
                            ),
                          ),
                          const SizedBox(height: 14),
                          Text(
                            copy.heroAddressLines.join('\n'),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: subtitleSize,
                              height: 1.28,
                              color: Colors.white.withValues(alpha: 0.88),
                              fontWeight: FontWeight.w300,
                            ),
                          ),
                          const SizedBox(height: 22),
                          Container(
                            width: 58,
                            height: 1,
                            color: Colors.white.withValues(alpha: 0.72),
                          ),
                          const SizedBox(height: 22),
                          ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 470),
                            child: Text(
                              copy.detailDescription,
                              maxLines: compact ? 3 : 4,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: descriptionSize,
                                height: 1.42,
                                color: Colors.white.withValues(alpha: 0.78),
                                fontWeight: FontWeight.w300,
                              ),
                            ),
                          ),
                          const SizedBox(height: 24),
                          Container(
                            height: compact ? 44 : 50,
                            constraints: BoxConstraints(
                              minWidth: compact ? 206 : 240,
                              maxWidth: compact ? 245 : 280,
                            ),
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              border: Border.all(color: Colors.white),
                              color: Colors.black.withValues(alpha: 0.2),
                            ),
                            child: Text(
                              'Смотреть пространство',
                              style: TextStyle(
                                fontSize: compact ? 12 : 13,
                                letterSpacing: 0.5,
                                color: Colors.white,
                                fontWeight: FontWeight.w500,
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
        ),
      ),
    );
  }
}

class _SpacesSliderIndicator extends StatelessWidget {
  final int currentIndex;
  final int count;

  const _SpacesSliderIndicator({
    required this.currentIndex,
    required this.count,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: List.generate(count, (index) {
        final active = index == currentIndex;
        return Expanded(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 220),
            height: active ? 2 : 1,
            margin: EdgeInsets.only(right: index == count - 1 ? 0 : 8),
            color: active
                ? GlameColors.whiteGlame
                : GlameColors.borderGray.withValues(alpha: 0.65),
          ),
        );
      }),
    );
  }
}

class _SpaceHero extends StatelessWidget {
  final _SpaceStoreData space;
  final _SpaceCopy copy;

  const _SpaceHero({required this.space, required this.copy});

  @override
  Widget build(BuildContext context) {
    final palette = _spacePaletteFor(copy.slug);
    return SizedBox(
      height: 420,
      child: Stack(
        fit: StackFit.expand,
        children: [
          _NetworkStoreImage(url: space.heroImageUrl),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [palette.overlayTop, palette.overlayBottom],
              ),
            ),
          ),
          const Positioned(
            left: 0,
            top: 0,
            right: 0,
            child: GlameTopAppBar(transparent: true),
          ),
          Positioned(
            left: 20,
            right: 20,
            bottom: 24,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      copy.heroTitle,
                      style: const TextStyle(
                        fontSize: 36,
                        height: 1.05,
                        color: Colors.white,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      copy.heroSubtitle,
                      style: const TextStyle(
                        fontSize: 18,
                        height: 1.35,
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      copy.heroAddressLines.join('\n'),
                      style: const TextStyle(
                        fontSize: 15,
                        height: 1.45,
                        color: Colors.white,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SpaceGallery extends StatelessWidget {
  final _SpaceStoreData space;

  const _SpaceGallery({required this.space});

  @override
  Widget build(BuildContext context) {
    final images = space.galleryImageUrls;
    final main = _itemAt(images, 0) ?? space.heroImageUrl;
    final second = _itemAt(images, 1) ?? main;
    final third = _itemAt(images, 2) ?? second;

    return Column(
      children: [
        AspectRatio(
          aspectRatio: 1.42,
          child: ClipRect(child: _NetworkStoreImage(url: main)),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: AspectRatio(
                aspectRatio: 1.04,
                child: ClipRect(child: _NetworkStoreImage(url: second)),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: AspectRatio(
                aspectRatio: 1.04,
                child: ClipRect(child: _NetworkStoreImage(url: third)),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _ServiceMeaningTile extends StatelessWidget {
  final _ServiceMeaning item;
  final _SpacePalette? palette;

  const _ServiceMeaningTile({required this.item, this.palette});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: palette?.panelBackground,
        border: Border.all(color: palette?.border ?? GlameColors.lightGray),
      ),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            item.title,
            style: const TextStyle(
              fontSize: 14,
              color: GlameColors.textPrimary,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            item.description,
            style: const TextStyle(
              fontSize: 14,
              height: 1.45,
              color: GlameColors.steelGray,
            ),
          ),
        ],
      ),
    );
  }
}

class _SpaceCtaButton extends StatelessWidget {
  final String label;
  final bool filled;
  final VoidCallback? onPressed;
  final _SpacePalette? palette;
  final IconData? leadingIcon;

  const _SpaceCtaButton({
    required this.label,
    this.filled = false,
    this.onPressed,
    this.palette,
    this.leadingIcon,
  });

  @override
  Widget build(BuildContext context) {
    final iconColor = filled
        ? (palette?.filledForeground ?? GlameColors.surface2)
        : GlameColors.textPrimary;
    final child = Row(
      mainAxisAlignment: leadingIcon == null
          ? MainAxisAlignment.spaceBetween
          : MainAxisAlignment.start,
      children: [
        if (leadingIcon != null) ...[
          Icon(leadingIcon, size: 18, color: iconColor),
          const SizedBox(width: 12),
        ],
        Flexible(
          child: Text(
            label,
            style: TextStyle(
              fontSize: 15,
              color: filled
                  ? (palette?.filledForeground ?? GlameColors.surface2)
                  : GlameColors.textPrimary,
            ),
          ),
        ),
        if (leadingIcon == null)
          Icon(Icons.arrow_forward, size: 18, color: iconColor),
      ],
    );

    return SizedBox(
      width: double.infinity,
      height: 52,
      child: filled
          ? FilledButton(
              onPressed: onPressed,
              style: FilledButton.styleFrom(
                backgroundColor:
                    palette?.filledBackground ?? GlameColors.textPrimary,
                foregroundColor:
                    palette?.filledForeground ?? GlameColors.surface2,
                shape: const RoundedRectangleBorder(),
              ),
              child: child,
            )
          : OutlinedButton(
              onPressed: onPressed,
              style: OutlinedButton.styleFrom(
                side: BorderSide(
                  color: palette?.border ?? GlameColors.lightGray,
                ),
                shape: const RoundedRectangleBorder(),
              ),
              child: child,
            ),
    );
  }
}

class _NetworkStoreImage extends StatelessWidget {
  final String? url;

  const _NetworkStoreImage({required this.url});

  @override
  Widget build(BuildContext context) {
    if (url == null || url!.trim().isEmpty) {
      return Container(
        color: GlameColors.coldLightGrey,
        alignment: Alignment.center,
        child: const Icon(
          Icons.storefront_outlined,
          color: GlameColors.steelGray,
          size: 30,
        ),
      );
    }

    final source = url!.trim();
    final localAsset = _localStoreImageAsset(source);
    if (localAsset != null) {
      return Image.asset(
        localAsset,
        fit: BoxFit.cover,
        errorBuilder: (_, _, _) => _StoreImageFallback(),
      );
    }

    if (!source.startsWith('http://') && !source.startsWith('https://')) {
      return Image.asset(
        source,
        fit: BoxFit.cover,
        errorBuilder: (_, _, _) => _StoreImageFallback(),
      );
    }

    return CachedNetworkImage(
      imageUrl: source,
      fit: BoxFit.cover,
      placeholder: (_, _) => const ColoredBox(color: GlameColors.coldLightGrey),
      errorWidget: (_, _, _) => _StoreImageFallback(),
    );
  }
}

class _StoreImageFallback extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      color: GlameColors.coldLightGrey,
      alignment: Alignment.center,
      child: const Icon(
        Icons.storefront_outlined,
        color: GlameColors.steelGray,
        size: 30,
      ),
    );
  }
}

String? _localStoreImageAsset(String source) {
  final normalized = source.trim();
  if (normalized.startsWith('assets/')) return normalized;
  final uri = Uri.tryParse(normalized);
  final filename = uri == null || uri.pathSegments.isEmpty
      ? normalized.split('/').last
      : uri.pathSegments.last;
  if (_bundledStoreImageNames.contains(filename)) {
    return 'assets/images/stores/$filename';
  }
  return null;
}

const _bundledStoreImageNames = <String>{
  'glame_block5_yalta_card_photo.png',
  'glame_space_yalta_hero_photo.png',
  'glame_space_yalta_gallery_main.png',
  'glame_space_yalta_gallery_01.png',
  'glame_space_yalta_gallery_02.png',
  'glame_block5_simferopol_card_photo.png',
  'glame_space_simferopol_hero_photo.png',
  'glame_space_simferopol_gallery_main.png',
  'glame_space_simferopol_gallery_01.png',
  'glame_space_simferopol_gallery_02.png',
  'b6139bbb015f45229e6d75db6bccb7bb.jpg',
  'c511c671b0d843fd8b99a44a674f5388.png',
};

class _SpacesLoadError extends StatelessWidget {
  const _SpacesLoadError();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Не удалось загрузить пространства GLAME',
              style: TextStyle(color: GlameColors.textPrimary),
            ),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: () => context.go('/home'),
              child: const Text('Вернуться на главную'),
            ),
          ],
        ),
      ),
    );
  }
}

class _SpaceStoreData {
  final int sortOrder;
  final String slug;
  final String city;
  final String title;
  final String address;
  final String? workingHours;
  final String? phone;
  final String? comment;
  final String? stockStoreExternalId;
  final LatLng? point;
  final String? cardImageUrl;
  final String? heroImageUrl;
  final List<String?> galleryImageUrls;

  const _SpaceStoreData({
    required this.sortOrder,
    required this.slug,
    required this.city,
    required this.title,
    required this.address,
    required this.workingHours,
    required this.phone,
    required this.comment,
    required this.stockStoreExternalId,
    required this.point,
    required this.cardImageUrl,
    required this.heroImageUrl,
    required this.galleryImageUrls,
  });
}

class _SpaceCopy {
  final String slug;
  final String cityLabel;
  final List<String> cardAddressLines;
  final List<String> cardDescriptionLines;
  final String heroTitle;
  final String heroSubtitle;
  final List<String> heroAddressLines;
  final String detailDescription;
  final String catalogButtonLabel;
  final List<_ServiceMeaning> serviceMeanings;

  const _SpaceCopy({
    required this.slug,
    required this.cityLabel,
    required this.cardAddressLines,
    required this.cardDescriptionLines,
    required this.heroTitle,
    required this.heroSubtitle,
    required this.heroAddressLines,
    required this.detailDescription,
    required this.catalogButtonLabel,
    required this.serviceMeanings,
  });
}

class _SpacePalette {
  final Color overlayTop;
  final Color overlayBottom;
  final Color border;
  final Color panelBackground;
  final Color filledBackground;
  final Color filledForeground;

  const _SpacePalette({
    required this.overlayTop,
    required this.overlayBottom,
    required this.border,
    required this.panelBackground,
    required this.filledBackground,
    required this.filledForeground,
  });
}

class _ServiceMeaning {
  final String title;
  final String description;

  const _ServiceMeaning(this.title, this.description);
}

const _fallbackSpaces = <_SpaceStoreData>[
  _SpaceStoreData(
    sortOrder: 1,
    slug: 'yalta',
    city: 'Ялта',
    title: 'Ялта',
    address: 'Набережная им. Ленина, 18',
    workingHours: null,
    phone: null,
    comment: null,
    stockStoreExternalId: '3daee4e4-a2ab-11f0-96fc-fa163e4cc04e',
    point: LatLng(44.487622, 34.161089),
    cardImageUrl:
        '/static/app_admin_media/store/glame_block5_yalta_card_photo.png',
    heroImageUrl:
        '/static/app_admin_media/store/glame_space_yalta_hero_photo.png',
    galleryImageUrls: [
      '/static/app_admin_media/store/glame_space_yalta_gallery_main.png',
      '/static/app_admin_media/store/glame_space_yalta_gallery_01.png',
      '/static/app_admin_media/store/glame_space_yalta_gallery_02.png',
    ],
  ),
  _SpaceStoreData(
    sortOrder: 2,
    slug: 'simferopol',
    city: 'Симферополь',
    title: 'Симферополь',
    address: 'ул. Севастопольская, 62',
    workingHours: null,
    phone: null,
    comment: null,
    stockStoreExternalId: '6c3a8322-a2ab-11f0-96fc-fa163e4cc04e',
    point: LatLng(44.938003, 34.093569),
    cardImageUrl:
        '/static/app_admin_media/store/glame_block5_simferopol_card_photo.png',
    heroImageUrl:
        '/static/app_admin_media/store/glame_space_simferopol_hero_photo.png',
    galleryImageUrls: [
      '/static/app_admin_media/store/glame_space_simferopol_gallery_main.png',
      '/static/app_admin_media/store/glame_space_simferopol_gallery_01.png',
      '/static/app_admin_media/store/glame_space_simferopol_gallery_02.png',
    ],
  ),
];

List<_SpaceStoreData> _parseSpaces(List<dynamic> rawItems) {
  final items = rawItems
      .whereType<Map>()
      .map((raw) {
        final item = Map<String, dynamic>.from(raw);
        final city = _stringValue(item['city']);
        final title = _stringValue(item['title']) ?? city;
        final address = _stringValue(item['address']);
        final slug =
            _stringValue(item['slug']) ??
            _spaceSlug(city, title) ??
            _storeIdSlug(item['id']);
        if (city == null || title == null || address == null || slug == null) {
          return null;
        }
        final imageUrls = _orderedImageUrls(item);
        final lat = _doubleValue(item['latitude']);
        final lng = _doubleValue(item['longitude']);
        final card = resolveAssetUrl(
          _stringValue(item['card_image_url']) ?? _itemAt(imageUrls, 0),
        );
        final hero = resolveAssetUrl(
          _stringValue(item['hero_image_url']) ??
              _itemAt(imageUrls, 1) ??
              _itemAt(imageUrls, 0),
        );
        final gallery = _spaceGalleryUrls(item, imageUrls, hero);
        return _SpaceStoreData(
          sortOrder: _intValue(item['sort_order']) ?? 99,
          slug: slug,
          city: city,
          title: title,
          address: address,
          workingHours: _stringValue(item['working_hours']),
          phone: _stringValue(item['phone']),
          comment: _stringValue(item['comment']),
          stockStoreExternalId: _stringValue(item['stock_store_external_id']),
          point: lat == null || lng == null ? null : LatLng(lat, lng),
          cardImageUrl: card,
          heroImageUrl: hero,
          galleryImageUrls: gallery,
        );
      })
      .whereType<_SpaceStoreData>()
      .toList();

  items.sort((a, b) {
    final bySort = a.sortOrder.compareTo(b.sortOrder);
    if (bySort != 0) return bySort;
    return _spaceOrder(a.slug).compareTo(_spaceOrder(b.slug));
  });
  return items;
}

Map<String, dynamic> _spaceItemMap(_SpaceStoreData space) => {
  'space': space.slug,
  'city': space.city,
  'title': space.title,
};

const _spaceCopyBySlug = <String, _SpaceCopy>{
  'yalta': _SpaceCopy(
    slug: 'yalta',
    cityLabel: 'Ялта',
    cardAddressLines: ['Набережная им. Ленина, 18', '(Приморский пляж)'],
    cardDescriptionLines: ['Бутик на берегу.', 'Свет, воздух, море.'],
    heroTitle: 'GLAME Ялта',
    heroSubtitle: 'пространство у моря',
    heroAddressLines: ['Набережная им. Ленина, 18', 'Приморский пляж'],
    detailDescription:
        'Место, где украшения подбирают как часть образа — спокойно, точно и без давления.',
    catalogButtonLabel: 'Смотреть украшения в Ялте',
    serviceMeanings: [
      _ServiceMeaning(
        '01 Подбор',
        'Стилист помогает собрать украшение под образ и настроение.',
      ),
      _ServiceMeaning(
        '02 Примерка',
        'Украшения можно увидеть на себе и почувствовать в реальном свете пространства.',
      ),
      _ServiceMeaning(
        '03 Наличие',
        'Проверяем наличие в магазине и подсказываем, что лучше примерить сразу.',
      ),
    ],
  ),
  'simferopol': _SpaceCopy(
    slug: 'simferopol',
    cityLabel: 'Симферополь',
    cardAddressLines: ['ул. Севастопольская, 62', '(1 этаж)'],
    cardDescriptionLines: [
      'Пространство городского стиля.',
      'Ритм, форма, свет.',
    ],
    heroTitle: 'GLAME Симферополь',
    heroSubtitle: 'пространство городского стиля и ритма',
    heroAddressLines: ['ул. Севастопольская, 62', '(1 этаж)'],
    detailDescription:
        'Ритм города, архитектура и украшения, которые собирают образ.',
    catalogButtonLabel: 'Смотреть украшения в Симферополе',
    serviceMeanings: [
      _ServiceMeaning(
        '01 Подбор',
        'Подбираем украшения под Ваш ритм, стиль и конкретный запрос.',
      ),
      _ServiceMeaning(
        '02 Примерка',
        'Показываем, как серьги, колье и браслеты собирают образ вживую.',
      ),
      _ServiceMeaning(
        '03 Наличие',
        'Уточняем наличие по магазину и быстро ведём к нужным позициям.',
      ),
    ],
  ),
  'mriya': _SpaceCopy(
    slug: 'mriya',
    cityLabel: 'Оползневое',
    cardAddressLines: ['МРИЯ'],
    cardDescriptionLines: ['Пространство GLAME', 'в курортном ритме.'],
    heroTitle: 'GLAME МРИЯ',
    heroSubtitle: 'пространство GLAME в МРИЯ',
    heroAddressLines: ['Оползневое', 'МРИЯ'],
    detailDescription:
        'Пространство GLAME, где можно спокойно примерить украшения, собрать образ и уточнить наличие.',
    catalogButtonLabel: 'Смотреть украшения в GLAME МРИЯ',
    serviceMeanings: [
      _ServiceMeaning(
        '01 Подбор',
        'Стилист помогает подобрать украшения под образ, повод и настроение.',
      ),
      _ServiceMeaning(
        '02 Примерка',
        'Украшения можно увидеть на себе и оценить в реальном свете пространства.',
      ),
      _ServiceMeaning(
        '03 Наличие',
        'Уточняем наличие по магазину и быстро ведём к нужным позициям.',
      ),
    ],
  ),
};

const _spacePaletteBySlug = <String, _SpacePalette>{
  'yalta': _SpacePalette(
    overlayTop: Color(0x26293E52),
    overlayBottom: Color(0x8F1F2F3E),
    border: Color(0xFFD7E1E8),
    panelBackground: Color(0xFFF7FAFC),
    filledBackground: Color(0xFF2F4658),
    filledForeground: Colors.white,
  ),
  'simferopol': _SpacePalette(
    overlayTop: Color(0x1A111316),
    overlayBottom: Color(0xA6131518),
    border: Color(0xFFD8DDE3),
    panelBackground: Color(0xFFF6F7F9),
    filledBackground: Color(0xFF1F2328),
    filledForeground: Colors.white,
  ),
  'mriya': _SpacePalette(
    overlayTop: Color(0x1A111316),
    overlayBottom: Color(0xA6131518),
    border: Color(0xFFD8DDE3),
    panelBackground: Color(0xFFF6F7F9),
    filledBackground: Color(0xFF1F2328),
    filledForeground: Colors.white,
  ),
};

_SpaceCopy _copyForSpace(_SpaceStoreData space) {
  final known = _spaceCopyBySlug[space.slug];
  if (known != null) return known;

  final hours = space.workingHours == null
      ? null
      : 'Часы: ${space.workingHours}';
  return _SpaceCopy(
    slug: space.slug,
    cityLabel: space.city,
    cardAddressLines: [space.address],
    cardDescriptionLines: [
      ?space.comment,
      ?hours,
      if (space.comment == null && hours == null) space.title,
    ],
    heroTitle: space.title,
    heroSubtitle: 'пространство GLAME',
    heroAddressLines: [space.address, ?space.workingHours],
    detailDescription:
        space.comment ??
        'Пространство GLAME, где можно увидеть украшения, примерить их и уточнить наличие у консультанта.',
    catalogButtonLabel: 'Смотреть украшения в ${space.city}',
    serviceMeanings: const [
      _ServiceMeaning(
        '01 Подбор',
        'Стилист помогает собрать украшение под образ, настроение и конкретный запрос.',
      ),
      _ServiceMeaning(
        '02 Примерка',
        'Украшения можно увидеть на себе и почувствовать в реальном свете пространства.',
      ),
      _ServiceMeaning(
        '03 Наличие',
        'Уточняем наличие по магазину и быстро ведём к нужным позициям.',
      ),
    ],
  );
}

_SpacePalette _spacePaletteFor(String slug) {
  return _spacePaletteBySlug[slug] ?? _spacePaletteBySlug.values.first;
}

int _spaceOrder(String slug) {
  switch (slug) {
    case 'yalta':
      return 0;
    case 'simferopol':
      return 1;
    case 'mriya':
      return 2;
    default:
      return 99;
  }
}

List<String> _orderedImageUrls(Map<String, dynamic> raw) {
  final result = <String>[];
  final rawList = raw['image_urls'];
  if (rawList is List) {
    for (final item in rawList) {
      final value = _stringValue(item);
      if (value != null && !result.contains(value)) {
        result.add(value);
      }
    }
  }
  final imageUrl = _stringValue(raw['image_url']);
  if (imageUrl != null && !result.contains(imageUrl)) {
    result.insert(0, imageUrl);
  }
  return result;
}

List<String?> _spaceGalleryUrls(
  Map<String, dynamic> raw,
  List<String> imageUrls,
  String? hero,
) {
  final explicitRaw = raw['gallery_image_urls'];
  if (explicitRaw is List) {
    final explicit = explicitRaw
        .map(_stringValue)
        .whereType<String>()
        .map(resolveAssetUrl)
        .toList();
    if (explicit.isNotEmpty) return explicit;
  }
  if (imageUrls.length > 2) {
    return imageUrls.skip(2).take(3).map(resolveAssetUrl).toList();
  }
  return [hero, hero, hero];
}

String? _spaceSlug(String? city, String? title) {
  final normalized = '${city ?? ''} ${title ?? ''}'.toLowerCase();
  if (normalized.contains('ялт')) return 'yalta';
  if (normalized.contains('симфер')) return 'simferopol';
  if (normalized.contains('мрия') || normalized.contains('оползнев')) {
    return 'mriya';
  }
  return null;
}

String? _storeIdSlug(Object? value) {
  final id = _stringValue(value);
  if (id == null) return null;
  return 'store-${id.replaceAll(RegExp(r'[^a-zA-Z0-9_-]+'), '-')}';
}

String? _stringValue(Object? value) {
  final text = (value as String?)?.trim();
  return text == null || text.isEmpty ? null : text;
}

double? _doubleValue(Object? value) {
  if (value is num) return value.toDouble();
  if (value is String) {
    return double.tryParse(value.replaceAll(',', '.').trim());
  }
  return null;
}

int? _intValue(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value.trim());
  return null;
}

T? _itemAt<T>(List<T> items, int index) {
  if (index < 0 || index >= items.length) return null;
  return items[index];
}

Future<void> _openMaps(_SpaceStoreData store) async {
  final point = store.point;
  if (point == null) return;
  _trackSpacesEvent('space_route_click', _spaceItemMap(store));
  final uri = Uri.parse(
    'https://www.google.com/maps/dir/?api=1&destination=${point.latitude},${point.longitude}&travelmode=driving',
  );
  await launchUrl(uri, mode: LaunchMode.externalApplication);
}

void _openStoreChat(BuildContext context, _SpaceStoreData store) {
  _trackSpacesEvent('space_stylist_click', _spaceItemMap(store));
  final message =
      'Здравствуйте! Хочу написать стилисту по пространству ${store.city} и уточнить примерку и наличие.';
  showStylistContactSheet(
    context,
    initialMessage: message,
    source: 'spaces_screen',
    scenario: 'live_stylist',
  );
}

void _openCatalog(BuildContext context, _SpaceStoreData store) {
  _trackSpacesEvent('space_catalog_click', _spaceItemMap(store));
  final storeId = _stockStoreIdForSpace(store);
  final query = <String, String>{
    'tab': '1',
    'storeId': storeId,
    'storeTitle': _catalogStoreTitle(store),
    'storeSlug': store.slug,
  };
  context.go(Uri(path: '/home', queryParameters: query).toString());
}

void _trackSpacesEvent(String eventName, [Map<String, Object?>? params]) {
  debugPrint('analytics:$eventName ${params ?? const {}}');
}

String _catalogStoreTitle(_SpaceStoreData store) {
  if (store.slug == 'yalta') return 'GLAME Ялта';
  if (store.slug == 'simferopol') return 'GLAME Симферополь';
  return store.title;
}

String _stockStoreIdForSpace(_SpaceStoreData store) {
  final configured = (store.stockStoreExternalId ?? '').trim();
  if (configured.isNotEmpty) return configured;
  switch (store.slug) {
    case 'yalta':
      return '3daee4e4-a2ab-11f0-96fc-fa163e4cc04e';
    case 'simferopol':
      return '6c3a8322-a2ab-11f0-96fc-fa163e4cc04e';
    case 'mriya':
      return 'e1a2ea42-fdc8-11ef-8c0c-fa163e4cc04e';
    default:
      return store.slug;
  }
}
