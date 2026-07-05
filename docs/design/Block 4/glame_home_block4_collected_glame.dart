import 'package:flutter/material.dart';

/// GLAME — Home Block 4: "Собрано GLAME"
///
/// This widget renders only the block content.
/// It must not render the fixed top bar or fixed bottom navigation.
///
/// Required assets:
/// - assets/images/home/glame_home_block4_background_underlay.png
/// - assets/images/home/glame_home_block4_visual_image_no_text.png
class HomeBlockCollectedGlame extends StatelessWidget {
  const HomeBlockCollectedGlame({
    super.key,
    required this.onViewBrands,
    this.backgroundAsset =
        'assets/images/home/glame_home_block4_background_underlay.png',
    this.visualAsset =
        'assets/images/home/glame_home_block4_visual_image_no_text.png',
  });

  final VoidCallback onViewBrands;
  final String backgroundAsset;
  final String visualAsset;

  static const List<String> brands = <String>[
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
  ];

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Собрано GLAME',
      child: Container(
        width: double.infinity,
        constraints: const BoxConstraints(minHeight: 760),
        color: GlameColors.coldLightGrey,
        child: Stack(
          children: <Widget>[
            Positioned.fill(
              child: Image.asset(
                backgroundAsset,
                fit: BoxFit.cover,
                alignment: Alignment.center,
              ),
            ),

            // Visual picture layer. This asset must not include UI text.
            Positioned(
              right: 0,
              top: 260,
              bottom: 260,
              width: MediaQuery.sizeOf(context).width * 0.68,
              child: IgnorePointer(
                child: Image.asset(
                  visualAsset,
                  fit: BoxFit.cover,
                  alignment: Alignment.centerRight,
                ),
              ),
            ),

            // Light fade to keep text readable.
            Positioned.fill(
              child: IgnorePointer(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.centerLeft,
                      end: Alignment.centerRight,
                      colors: <Color>[
                        GlameColors.coldLightGrey.withOpacity(0.96),
                        GlameColors.coldLightGrey.withOpacity(0.76),
                        GlameColors.coldLightGrey.withOpacity(0.08),
                      ],
                      stops: const <double>[0.0, 0.38, 0.78],
                    ),
                  ),
                ),
              ),
            ),

            Padding(
              padding: const EdgeInsets.fromLTRB(28, 86, 28, 30),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const _BlockTitle(),
                  const SizedBox(height: 34),
                  _OutlineButton(
                    label: 'Смотреть бренды',
                    onTap: () {
                      // Analytics example:
                      // analytics.logEvent(
                      //   name: 'home_block4_brands_click',
                      //   parameters: {
                      //     'screen': 'home',
                      //     'block': 'home_collected_glame',
                      //     'cta': 'view_brands',
                      //   },
                      // );
                      onViewBrands();
                    },
                  ),
                  const Spacer(),
                  const _BrandNamesGrid(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BlockTitle extends StatelessWidget {
  const _BlockTitle();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text.rich(
          TextSpan(
            children: <InlineSpan>[
              TextSpan(text: 'Собрано '),
              TextSpan(
                text: 'GLAME',
                style: TextStyle(
                  letterSpacing: 3.0,
                  color: GlameColors.steelGrey,
                ),
              ),
            ],
          ),
          style: TextStyle(
            fontFamily: GlameTypography.fontFamily,
            fontSize: 44,
            height: 1.06,
            letterSpacing: -0.8,
            color: GlameColors.graphite,
            fontWeight: FontWeight.w300,
          ),
        ),
        SizedBox(height: 28),
        Text(
          'Мы отбираем главное.\nЧтобы вы выбирали свое.',
          style: TextStyle(
            fontFamily: GlameTypography.fontFamily,
            fontSize: 23,
            height: 1.38,
            letterSpacing: -0.2,
            color: GlameColors.graphite,
            fontWeight: FontWeight.w300,
          ),
        ),
      ],
    );
  }
}

class _OutlineButton extends StatelessWidget {
  const _OutlineButton({
    required this.label,
    required this.onTap,
  });

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          splashColor: GlameColors.graphite.withOpacity(0.05),
          highlightColor: GlameColors.graphite.withOpacity(0.03),
          child: Container(
            height: 56,
            width: 205,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: Colors.transparent,
              borderRadius: BorderRadius.zero,
              border: Border.all(
                color: GlameColors.graphite,
                width: 1,
              ),
            ),
            child: Text(
              label,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: GlameTypography.fontFamily,
                fontSize: 18,
                height: 1.0,
                letterSpacing: -0.1,
                color: GlameColors.graphite,
                fontWeight: FontWeight.w300,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _BrandNamesGrid extends StatelessWidget {
  const _BrandNamesGrid();

  @override
  Widget build(BuildContext context) {
    final List<List<String>> rows = <List<String>>[
      <String>['Geometry', 'Magna', 'Pearl', 'Crystal', 'Bicolor'],
      <String>['Prism Of Elegance', 'UNOde50', 'Raganella Princess'],
      <String>['Island Soul', 'AGafi', 'Antura', 'Kalliope'],
      <String>['Wrinkles of Time', 'Claudio Canzian'],
    ];

    return Column(
      children: <Widget>[
        for (int i = 0; i < rows.length; i++) ...<Widget>[
          if (i > 0) const _ThinDivider(),
          SizedBox(
            height: 52,
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
    final List<Widget> children = <Widget>[];

    for (int i = 0; i < row.length; i++) {
      children.add(
        Flexible(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            child: Text(
              row[i],
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontFamily: GlameTypography.fontFamily,
                fontSize: 16,
                height: 1.1,
                letterSpacing: -0.1,
                color: GlameColors.graphite,
                fontWeight: FontWeight.w300,
              ),
            ),
          ),
        ),
      );

      if (i < row.length - 1) {
        children.add(
          Container(
            width: 1,
            height: 22,
            color: GlameColors.lineGrey,
          ),
        );
      }
    }

    return children;
  }
}

class _ThinDivider extends StatelessWidget {
  const _ThinDivider();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 1,
      color: GlameColors.lineGrey.withOpacity(0.85),
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
