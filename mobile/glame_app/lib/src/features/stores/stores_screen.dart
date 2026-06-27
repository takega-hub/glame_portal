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

class HomeSpacesBlock extends ConsumerWidget {
  final double? viewportHeight;

  const HomeSpacesBlock({super.key, this.viewportHeight});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final storesAsync = ref.watch(homeStoresProvider);
    final spaces = storesAsync.maybeWhen(
      data: _parseSpaces,
      orElse: () => _fallbackSpaces,
    );
    final items = spaces.isEmpty ? _fallbackSpaces : spaces;
    final compact = viewportHeight != null;
    final targetHeight = viewportHeight;
    final topBarBottom =
        MediaQuery.of(context).padding.top +
        GlameUi.heroTopOffset +
        GlameUi.heroTopBarHeight;
    final topPadding = compact ? topBarBottom + 26.0 : 70.0;
    final bottomPadding = compact ? 14.0 : 42.0;
    final cardGap = compact ? 8.0 : 26.0;
    final headerHeight = compact ? 50.0 : 110.0;
    final headerGap = compact ? 14.0 : 44.0;
    final cardCount = items.isEmpty ? 1 : items.length;
    final availableHeight =
        (targetHeight ?? 860) -
        topPadding -
        bottomPadding -
        headerHeight -
        headerGap -
        (cardGap * (cardCount - 1));
    final cardHeight = compact
        ? (availableHeight / cardCount).clamp(168.0, 258.0)
        : (availableHeight / cardCount).clamp(300.0, 420.0);

    return Container(
      height: targetHeight,
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
            padding: EdgeInsets.fromLTRB(24, topPadding, 24, bottomPadding),
            child: Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _SpacesHeader(
                      compact: compact,
                      dark: true,
                      cities: items.map((item) => item.city).toList(),
                    ),
                    SizedBox(height: headerGap),
                    for (var i = 0; i < items.length; i++) ...[
                      _HomeSpaceCard(
                        space: items[i],
                        compact: compact,
                        forcedHeight: cardHeight,
                      ),
                      if (i != items.length - 1) SizedBox(height: cardGap),
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
  final bool compact;
  final double? forcedHeight;

  const _HomeSpaceCard({
    required this.space,
    this.compact = false,
    this.forcedHeight,
  });

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
            final homeCard = forcedHeight != null;
            final cardHeight = forcedHeight ?? (narrow ? 406.0 : 392.0);
            final compactCard = compact || cardHeight < 280;
            final citySize = compactCard ? 18.0 : (narrow ? 28.0 : 33.0);
            final addressSize = compactCard ? 10.5 : (narrow ? 14.0 : 16.0);
            final descriptionSize = compactCard ? 9.5 : (narrow ? 13.0 : 15.0);
            final verticalGap = compactCard ? 8.0 : (narrow ? 24.0 : 34.0);
            final textPadding = compactCard
                ? const EdgeInsets.fromLTRB(12, 10, 8, 10)
                : narrow
                ? const EdgeInsets.fromLTRB(20, 24, 14, 22)
                : const EdgeInsets.fromLTRB(28, 32, 18, 28);
            final ctaWidth = compactCard ? 118.0 : (narrow ? 154.0 : 176.0);
            final cardImageUrl = forcedHeight == null
                ? space.cardImageUrl
                : _homeCardImageForSpace(space);

            return SizedBox(
              width: double.infinity,
              height: cardHeight,
              child: Material(
                color: homeCard
                    ? GlameColors.graphite.withValues(alpha: 0.72)
                    : Colors.white.withValues(alpha: 0.72),
                child: Container(
                  decoration: BoxDecoration(
                    border: Border.all(
                      color: homeCard
                          ? GlameColors.borderGray
                          : const Color(0xFFC7C9CB),
                    ),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(
                        flex: compactCard ? 46 : (narrow ? 43 : 39),
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
                                  color: homeCard
                                      ? GlameColors.whiteGlame
                                      : GlameColors.graphite,
                                  fontWeight: FontWeight.w300,
                                ),
                              ),
                              SizedBox(height: verticalGap),
                              Text(
                                copy.cardAddressLines.join('\n'),
                                maxLines: compactCard ? 3 : null,
                                overflow: compactCard
                                    ? TextOverflow.ellipsis
                                    : TextOverflow.visible,
                                style: TextStyle(
                                  fontSize: addressSize,
                                  height: compactCard ? 1.25 : 1.45,
                                  color: homeCard
                                      ? GlameColors.coldLightGray
                                      : GlameColors.graphite,
                                  fontWeight: FontWeight.w300,
                                ),
                              ),
                              SizedBox(
                                height: compactCard ? 10 : (narrow ? 22 : 30),
                              ),
                              if (compactCard) const SizedBox(height: 0),
                              Container(
                                width: compactCard ? 28 : 36,
                                height: 1,
                                color: homeCard
                                    ? GlameColors.borderGray
                                    : GlameColors.graphite,
                              ),
                              const Spacer(),
                              Text(
                                copy.cardDescriptionLines.join('\n'),
                                maxLines: compactCard ? 2 : null,
                                overflow: compactCard
                                    ? TextOverflow.ellipsis
                                    : TextOverflow.visible,
                                style: TextStyle(
                                  fontSize: descriptionSize,
                                  height: compactCard ? 1.22 : 1.35,
                                  color: homeCard
                                      ? GlameColors.steelGray
                                      : GlameColors.graphite,
                                  fontWeight: FontWeight.w300,
                                ),
                              ),
                              SizedBox(
                                height: compactCard ? 8 : (narrow ? 18 : 24),
                              ),
                              SizedBox(
                                width: ctaWidth,
                                child: Container(
                                  height: compactCard ? 28 : (narrow ? 40 : 44),
                                  alignment: Alignment.center,
                                  decoration: BoxDecoration(
                                    border: Border.all(
                                      color: homeCard
                                          ? GlameColors.whiteGlame
                                          : GlameColors.graphite,
                                    ),
                                  ),
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 12,
                                  ),
                                  child: Text(
                                    'Смотреть пространство',
                                    style: TextStyle(
                                      fontSize: compactCard
                                          ? 8.5
                                          : (narrow ? 12 : 13),
                                      height: 1,
                                      color: homeCard
                                          ? GlameColors.whiteGlame
                                          : GlameColors.graphite,
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
                        flex: compactCard ? 54 : (narrow ? 57 : 61),
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

String? _homeCardImageForSpace(_SpaceStoreData space) {
  if (space.slug == 'yalta') {
    return 'assets/images/home/glame_block5_yalta_card_photo.png';
  }
  if (space.slug == 'simferopol') {
    return 'assets/images/home/glame_block5_simferopol_card_photo.png';
  }
  return space.cardImageUrl;
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

  const _SpaceCtaButton({
    required this.label,
    this.filled = false,
    this.onPressed,
    this.palette,
  });

  @override
  Widget build(BuildContext context) {
    final child = Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
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
        Icon(
          Icons.arrow_forward,
          size: 18,
          color: filled
              ? (palette?.filledForeground ?? GlameColors.surface2)
              : GlameColors.textPrimary,
        ),
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
    if (!source.startsWith('http://') && !source.startsWith('https://')) {
      return Image.asset(
        source,
        fit: BoxFit.cover,
        errorBuilder: (_, _, _) => Container(
          color: GlameColors.coldLightGrey,
          alignment: Alignment.center,
          child: const Icon(
            Icons.storefront_outlined,
            color: GlameColors.steelGray,
            size: 30,
          ),
        ),
      );
    }

    return CachedNetworkImage(
      imageUrl: source,
      fit: BoxFit.cover,
      placeholder: (_, _) => const ColoredBox(color: GlameColors.coldLightGrey),
      errorWidget: (_, _, _) => Container(
        color: GlameColors.coldLightGrey,
        alignment: Alignment.center,
        child: const Icon(
          Icons.storefront_outlined,
          color: GlameColors.steelGray,
          size: 30,
        ),
      ),
    );
  }
}

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
  context.go('/catalog?availableIn=${store.slug}');
}

void _trackSpacesEvent(String eventName, [Map<String, Object?>? params]) {
  debugPrint('analytics:$eventName ${params ?? const {}}');
}
