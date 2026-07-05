import 'package:flutter/material.dart';

/// GLAME — Home Block 5: "Пространства GLAME"
///
/// This file contains:
/// 1. HomeBlockSpacesGlame — block for the Home page.
/// 2. GlameSpacePage — reusable page template for Yalta / Simferopol.
///
/// The fixed top bar and bottom navigation are NOT rendered here.

class HomeBlockSpacesGlame extends StatelessWidget {
  const HomeBlockSpacesGlame({
    super.key,
    required this.onOpenYalta,
    required this.onOpenSimferopol,
    this.backgroundAsset =
        'assets/images/home/glame_home_block5_background_underlay.png',
    this.yaltaPhotoAsset =
        'assets/images/home/glame_block5_yalta_card_photo.png',
    this.simferopolPhotoAsset =
        'assets/images/home/glame_block5_simferopol_card_photo.png',
  });

  final VoidCallback onOpenYalta;
  final VoidCallback onOpenSimferopol;

  final String backgroundAsset;
  final String yaltaPhotoAsset;
  final String simferopolPhotoAsset;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: GlameColors.coldLightGrey,
      width: double.infinity,
      child: Stack(
        children: <Widget>[
          Positioned.fill(
            child: Image.asset(
              backgroundAsset,
              fit: BoxFit.cover,
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 70, 24, 42),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const _SpacesHeader(),
                const SizedBox(height: 44),
                _SpaceCard(
                  city: 'Ялта',
                  addressLines: const <String>[
                    'Набережная',
                    'им. Ленина, 18',
                    '(Приморский пляж)',
                  ],
                  descriptionLines: const <String>[
                    'Бутик на берегу.',
                    'Свет, воздух, море.',
                  ],
                  imageAsset: yaltaPhotoAsset,
                  onTap: onOpenYalta,
                ),
                const SizedBox(height: 26),
                _SpaceCard(
                  city: 'Симферополь',
                  addressLines: const <String>[
                    'ул. Севастопольская, 62',
                    '(1 этаж)',
                  ],
                  descriptionLines: const <String>[
                    'Пространство',
                    'городского стиля.',
                    'Ритм, форма, свет.',
                  ],
                  imageAsset: simferopolPhotoAsset,
                  onTap: onOpenSimferopol,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SpacesHeader extends StatelessWidget {
  const _SpacesHeader();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text.rich(
          TextSpan(
            children: <InlineSpan>[
              TextSpan(text: 'Пространства\n'),
              TextSpan(
                text: 'GLAME',
                style: TextStyle(
                  letterSpacing: 3.0,
                ),
              ),
            ],
          ),
          style: TextStyle(
            fontFamily: GlameTypography.fontFamily,
            fontSize: 46,
            height: 1.05,
            letterSpacing: -0.8,
            color: GlameColors.graphite,
            fontWeight: FontWeight.w300,
          ),
        ),
        SizedBox(height: 22),
        Text(
          'Ялта и Симферополь',
          style: TextStyle(
            fontFamily: GlameTypography.fontFamily,
            fontSize: 20,
            height: 1.3,
            color: GlameColors.graphite,
            fontWeight: FontWeight.w300,
          ),
        ),
      ],
    );
  }
}

class _SpaceCard extends StatelessWidget {
  const _SpaceCard({
    required this.city,
    required this.addressLines,
    required this.descriptionLines,
    required this.imageAsset,
    required this.onTap,
  });

  final String city;
  final List<String> addressLines;
  final List<String> descriptionLines;
  final String imageAsset;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: 'Смотреть пространство $city',
      child: Material(
        color: GlameColors.white.withOpacity(0.72),
        child: InkWell(
          onTap: onTap,
          splashColor: GlameColors.graphite.withOpacity(0.04),
          highlightColor: GlameColors.graphite.withOpacity(0.02),
          child: Container(
            height: 292,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.zero,
              border: Border.all(color: GlameColors.lineGrey, width: 1),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Expanded(
                  flex: 36,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(28, 32, 18, 28),
                    child: _CardTextColumn(
                      city: city,
                      addressLines: addressLines,
                      descriptionLines: descriptionLines,
                    ),
                  ),
                ),
                Expanded(
                  flex: 64,
                  child: Image.asset(
                    imageAsset,
                    fit: BoxFit.cover,
                    alignment: Alignment.center,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _CardTextColumn extends StatelessWidget {
  const _CardTextColumn({
    required this.city,
    required this.addressLines,
    required this.descriptionLines,
  });

  final String city;
  final List<String> addressLines;
  final List<String> descriptionLines;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          city,
          style: const TextStyle(
            fontFamily: GlameTypography.fontFamily,
            fontSize: 33,
            height: 1.08,
            letterSpacing: -0.6,
            color: GlameColors.graphite,
            fontWeight: FontWeight.w300,
          ),
        ),
        const SizedBox(height: 34),
        Text(
          addressLines.join('\n'),
          style: const TextStyle(
            fontFamily: GlameTypography.fontFamily,
            fontSize: 16,
            height: 1.45,
            color: GlameColors.graphite,
            fontWeight: FontWeight.w300,
          ),
        ),
        const SizedBox(height: 30),
        Container(width: 36, height: 1, color: GlameColors.graphite),
        const Spacer(),
        Text(
          descriptionLines.join('\n'),
          style: const TextStyle(
            fontFamily: GlameTypography.fontFamily,
            fontSize: 15,
            height: 1.35,
            color: GlameColors.graphite,
            fontWeight: FontWeight.w300,
          ),
        ),
        const SizedBox(height: 24),
        _SmallOutlineButton(label: 'Смотреть пространство'),
      ],
    );
  }
}

class _SmallOutlineButton extends StatelessWidget {
  const _SmallOutlineButton({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 44,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.zero,
        border: Border.all(color: GlameColors.graphite, width: 1),
      ),
      child: Text(
        label,
        textAlign: TextAlign.center,
        style: const TextStyle(
          fontFamily: GlameTypography.fontFamily,
          fontSize: 13,
          height: 1,
          color: GlameColors.graphite,
          fontWeight: FontWeight.w300,
        ),
      ),
    );
  }
}

/// Data model for a GLAME space page.
class GlameSpaceData {
  const GlameSpaceData({
    required this.id,
    required this.heroTitle,
    required this.heroSubtitle,
    required this.address,
    required this.description,
    required this.catalogLabel,
    required this.heroPhotoAsset,
    required this.galleryMainAsset,
    required this.galleryAsset01,
    required this.galleryAsset02,
  });

  final String id;
  final String heroTitle;
  final String heroSubtitle;
  final String address;
  final String description;
  final String catalogLabel;

  final String heroPhotoAsset;
  final String galleryMainAsset;
  final String galleryAsset01;
  final String galleryAsset02;
}

class GlameSpaces {
  static const GlameSpaceData yalta = GlameSpaceData(
    id: 'yalta',
    heroTitle: 'GLAME Ялта',
    heroSubtitle: 'пространство у моря',
    address: 'Набережная им. Ленина, 18\nПриморский пляж',
    description:
        'Место, где украшения подбирают как часть образа — спокойно, точно и без давления.',
    catalogLabel: 'Смотреть украшения в Ялте',
    heroPhotoAsset: 'assets/images/spaces/glame_space_yalta_hero_photo.png',
    galleryMainAsset: 'assets/images/spaces/glame_space_yalta_gallery_main.png',
    galleryAsset01: 'assets/images/spaces/glame_space_yalta_gallery_01.png',
    galleryAsset02: 'assets/images/spaces/glame_space_yalta_gallery_02.png',
  );

  static const GlameSpaceData simferopol = GlameSpaceData(
    id: 'simferopol',
    heroTitle: 'GLAME Симферополь',
    heroSubtitle: 'пространство городского стиля и ритма',
    address: 'ул. Севастопольская, 62 (1 этаж)',
    description:
        'Ритм города, архитектура и украшения, которые собирают образ.',
    catalogLabel: 'Смотреть украшения в Симферополе',
    heroPhotoAsset:
        'assets/images/spaces/glame_space_simferopol_hero_photo.png',
    galleryMainAsset:
        'assets/images/spaces/glame_space_simferopol_gallery_main.png',
    galleryAsset01:
        'assets/images/spaces/glame_space_simferopol_gallery_01.png',
    galleryAsset02:
        'assets/images/spaces/glame_space_simferopol_gallery_02.png',
  );
}

class GlameSpacePage extends StatelessWidget {
  const GlameSpacePage({
    super.key,
    required this.data,
    required this.onBuildRoute,
    required this.onWriteStylist,
    required this.onOpenCatalog,
    required this.onBackToSpaces,
  });

  final GlameSpaceData data;
  final VoidCallback onBuildRoute;
  final VoidCallback onWriteStylist;
  final VoidCallback onOpenCatalog;
  final VoidCallback onBackToSpaces;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: GlameColors.coldLightGrey,
      child: SingleChildScrollView(
        child: Column(
          children: <Widget>[
            _SpaceHero(data: data),
            Padding(
              padding: const EdgeInsets.fromLTRB(28, 42, 28, 36),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const Text(
                    'Пространство GLAME',
                    style: TextStyle(
                      fontFamily: GlameTypography.fontFamily,
                      fontSize: 36,
                      height: 1.08,
                      letterSpacing: 1.4,
                      color: GlameColors.graphite,
                      fontWeight: FontWeight.w300,
                    ),
                  ),
                  const SizedBox(height: 22),
                  Text(
                    data.description,
                    style: const TextStyle(
                      fontFamily: GlameTypography.fontFamily,
                      fontSize: 20,
                      height: 1.35,
                      color: GlameColors.steelGrey,
                      fontWeight: FontWeight.w300,
                    ),
                  ),
                  const SizedBox(height: 28),
                  Row(
                    children: <Widget>[
                      Expanded(
                        child: _SpaceActionButton(
                          label: 'Построить маршрут',
                          onTap: onBuildRoute,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: _SpaceActionButton(
                          label: 'Написать стилисту',
                          onTap: onWriteStylist,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  _SpaceActionButton(
                    label: data.catalogLabel,
                    onTap: onOpenCatalog,
                    fullWidth: true,
                  ),
                  const SizedBox(height: 38),
                  const Text(
                    'Внутри пространства',
                    style: TextStyle(
                      fontFamily: GlameTypography.fontFamily,
                      fontSize: 29,
                      height: 1.1,
                      color: GlameColors.graphite,
                      fontWeight: FontWeight.w300,
                    ),
                  ),
                  const SizedBox(height: 18),
                  _SpaceGallery(data: data),
                  const SizedBox(height: 28),
                  const _SpaceServiceTriplet(),
                  const SizedBox(height: 28),
                  _SpaceActionButton(
                    label: 'Вернуться к пространствам',
                    onTap: onBackToSpaces,
                    fullWidth: true,
                    showArrow: false,
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

class _SpaceHero extends StatelessWidget {
  const _SpaceHero({required this.data});

  final GlameSpaceData data;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 305,
      width: double.infinity,
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          Image.asset(data.heroPhotoAsset, fit: BoxFit.cover),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.centerLeft,
                end: Alignment.centerRight,
                colors: <Color>[
                  GlameColors.graphite.withOpacity(0.68),
                  GlameColors.graphite.withOpacity(0.32),
                  Colors.transparent,
                ],
              ),
            ),
          ),
          Positioned(
            left: 28,
            right: 28,
            bottom: 32,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  data.heroTitle,
                  style: const TextStyle(
                    fontFamily: GlameTypography.fontFamily,
                    fontSize: 34,
                    height: 1.0,
                    letterSpacing: 2.2,
                    color: GlameColors.white,
                    fontWeight: FontWeight.w300,
                  ),
                ),
                const SizedBox(height: 14),
                Text(
                  data.heroSubtitle,
                  style: const TextStyle(
                    fontFamily: GlameTypography.fontFamily,
                    fontSize: 18,
                    color: GlameColors.white,
                    fontWeight: FontWeight.w300,
                  ),
                ),
                const SizedBox(height: 18),
                Container(width: 42, height: 1, color: GlameColors.white),
                const SizedBox(height: 18),
                Text(
                  data.address,
                  style: const TextStyle(
                    fontFamily: GlameTypography.fontFamily,
                    fontSize: 18,
                    height: 1.28,
                    color: GlameColors.white,
                    fontWeight: FontWeight.w300,
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

class _SpaceActionButton extends StatelessWidget {
  const _SpaceActionButton({
    required this.label,
    required this.onTap,
    this.fullWidth = false,
    this.showArrow = true,
  });

  final String label;
  final VoidCallback onTap;
  final bool fullWidth;
  final bool showArrow;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          child: Container(
            height: 56,
            width: fullWidth ? double.infinity : null,
            padding: const EdgeInsets.symmetric(horizontal: 22),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.zero,
              border: Border.all(color: GlameColors.graphite, width: 1),
            ),
            child: Row(
              mainAxisAlignment: showArrow
                  ? MainAxisAlignment.spaceBetween
                  : MainAxisAlignment.center,
              children: <Widget>[
                Flexible(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontFamily: GlameTypography.fontFamily,
                      fontSize: 17,
                      color: GlameColors.graphite,
                      fontWeight: FontWeight.w300,
                    ),
                  ),
                ),
                if (showArrow)
                  const Text(
                    '→',
                    style: TextStyle(
                      fontSize: 26,
                      color: GlameColors.graphite,
                      fontWeight: FontWeight.w300,
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SpaceGallery extends StatelessWidget {
  const _SpaceGallery({required this.data});

  final GlameSpaceData data;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Expanded(
          flex: 58,
          child: AspectRatio(
            aspectRatio: 1.10,
            child: Image.asset(data.galleryMainAsset, fit: BoxFit.cover),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          flex: 42,
          child: Column(
            children: <Widget>[
              AspectRatio(
                aspectRatio: 1.70,
                child: Image.asset(data.galleryAsset01, fit: BoxFit.cover),
              ),
              const SizedBox(height: 10),
              AspectRatio(
                aspectRatio: 1.70,
                child: Image.asset(data.galleryAsset02, fit: BoxFit.cover),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _SpaceServiceTriplet extends StatelessWidget {
  const _SpaceServiceTriplet();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Container(height: 1, color: GlameColors.lineGrey),
        const SizedBox(height: 22),
        const Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Expanded(
              child: _ServiceItem(
                number: '01',
                title: 'Подбор',
                text: 'Стилист помогает\nсобрать образ целиком.',
              ),
            ),
            _VerticalDivider(),
            Expanded(
              child: _ServiceItem(
                number: '02',
                title: 'Примерка',
                text: 'Украшения можно увидеть\nвживую и почувствовать\nмасштаб.',
              ),
            ),
            _VerticalDivider(),
            Expanded(
              child: _ServiceItem(
                number: '03',
                title: 'Наличие',
                text: 'Каталог помогает проверить,\nчто доступно в городе.',
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _ServiceItem extends StatelessWidget {
  const _ServiceItem({
    required this.number,
    required this.title,
    required this.text,
  });

  final String number;
  final String title;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            number,
            style: const TextStyle(
              fontFamily: GlameTypography.fontFamily,
              fontSize: 14,
              color: GlameColors.steelGrey,
              fontWeight: FontWeight.w300,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            title,
            style: const TextStyle(
              fontFamily: GlameTypography.fontFamily,
              fontSize: 21,
              color: GlameColors.graphite,
              fontWeight: FontWeight.w300,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            text,
            style: const TextStyle(
              fontFamily: GlameTypography.fontFamily,
              fontSize: 13,
              height: 1.2,
              color: GlameColors.steelGrey,
              fontWeight: FontWeight.w300,
            ),
          ),
        ],
      ),
    );
  }
}

class _VerticalDivider extends StatelessWidget {
  const _VerticalDivider();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 1,
      height: 92,
      margin: const EdgeInsets.symmetric(horizontal: 12),
      color: GlameColors.lineGrey,
    );
  }
}

class GlameColors {
  static const Color graphite = Color(0xFF2E3032);
  static const Color steelGrey = Color(0xFF73777A);
  static const Color coldLightGrey = Color(0xFFD9DCDE);
  static const Color white = Color(0xFFF8F9F9);
  static const Color lineGrey = Color(0xFFC7C9CB);
}

class GlameTypography {
  /// Replace with the exact GLAME app font family from pubspec.yaml.
  static const String fontFamily = 'GlameSans';
}
