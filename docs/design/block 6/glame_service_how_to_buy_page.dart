import 'package:flutter/material.dart';

/// GLAME — service page: "Как купить в GLAME"
///
/// Route: /service/how-to-buy
///
/// Fixed top bar / bottom navigation are not part of this widget.
/// Page follows the agreed first layout:
/// hero -> 3 ways to choose -> 4 purchase steps -> 2 CTAs.
class GlameHowToBuyPage extends StatelessWidget {
  const GlameHowToBuyPage({
    super.key,
    required this.onBack,
    required this.onOpenCatalog,
    required this.onOpenSelection,
    this.backgroundAsset =
        'assets/images/service/glame_service_how_to_buy_constructor_image_no_text.png',
  });

  final VoidCallback onBack;
  final VoidCallback onOpenCatalog;
  final VoidCallback onOpenSelection;
  final String backgroundAsset;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: GlameColors.steelLight,
      body: Stack(
        children: <Widget>[
          Positioned.fill(
            child: Image.asset(
              backgroundAsset,
              fit: BoxFit.cover,
              alignment: Alignment.topCenter,
            ),
          ),
          SafeArea(
            bottom: false,
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(28, 22, 28, 44),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  _PageHeader(onBack: onBack),
                  const SizedBox(height: 40),
                  const _HeroCopy(),
                  const SizedBox(height: 66),
                  const _WaysToChoose(),
                  const SizedBox(height: 56),
                  const _PurchaseSteps(),
                  const SizedBox(height: 52),
                  const _BottomMessage(),
                  const SizedBox(height: 28),
                  Row(
                    children: <Widget>[
                      Expanded(
                        child: _OutlineActionButton(
                          label: 'Перейти в каталог',
                          onTap: onOpenCatalog,
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: _OutlineActionButton(
                          label: 'Подобрать с GLAME',
                          onTap: onOpenSelection,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 42),
                  const Center(
                    child: Text(
                      'GLAME',
                      style: TextStyle(
                        fontFamily: GlameTypography.fontFamily,
                        fontSize: 18,
                        letterSpacing: 2.5,
                        color: GlameColors.steelGrey,
                        fontWeight: FontWeight.w300,
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Center(
                    child: Text(
                      'Украшения, которые остаются с вами.',
                      style: TextStyle(
                        fontFamily: GlameTypography.fontFamily,
                        fontSize: 11,
                        color: GlameColors.steelGrey,
                        fontWeight: FontWeight.w300,
                      ),
                    ),
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

class _PageHeader extends StatelessWidget {
  const _PageHeader({required this.onBack});

  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Semantics(
          button: true,
          label: 'Назад',
          child: GestureDetector(
            onTap: onBack,
            child: const SizedBox(
              width: 44,
              height: 44,
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  '←',
                  style: TextStyle(
                    fontSize: 29,
                    color: GlameColors.graphite,
                    fontWeight: FontWeight.w300,
                  ),
                ),
              ),
            ),
          ),
        ),
        const Expanded(
          child: Center(
            child: Text(
              'GLAME',
              style: TextStyle(
                fontFamily: GlameTypography.fontFamily,
                fontSize: 20,
                letterSpacing: 3.0,
                color: GlameColors.graphite,
                fontWeight: FontWeight.w300,
              ),
            ),
          ),
        ),
        const SizedBox(width: 44),
      ],
    );
  }
}

class _HeroCopy extends StatelessWidget {
  const _HeroCopy();

  @override
  Widget build(BuildContext context) {
    return const SizedBox(
      width: 315,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            'Как купить\nв GLAME',
            style: TextStyle(
              fontFamily: GlameTypography.fontFamily,
              fontSize: 44,
              height: 1.12,
              letterSpacing: -0.6,
              color: GlameColors.graphite,
              fontWeight: FontWeight.w300,
            ),
          ),
          SizedBox(height: 26),
          SizedBox(
            width: 50,
            child: Divider(
              height: 1,
              thickness: 1,
              color: GlameColors.graphite,
            ),
          ),
          SizedBox(height: 28),
          Text(
            'Выберите сами, со стилистом или с помощью AI — GLAME поможет найти украшение под вас и получить его удобным способом.',
            style: TextStyle(
              fontFamily: GlameTypography.fontFamily,
              fontSize: 17,
              height: 1.38,
              color: GlameColors.steelGrey,
              fontWeight: FontWeight.w300,
            ),
          ),
        ],
      ),
    );
  }
}

class _WaysToChoose extends StatelessWidget {
  const _WaysToChoose();

  @override
  Widget build(BuildContext context) {
    return const _OutlinedPanel(
      title: '3 способа выбрать',
      child: Column(
        children: <Widget>[
          _WayRow(
            iconText: '⌕',
            title: 'Самостоятельно',
            text: 'Каталог, бренды и подборки.',
          ),
          _PanelDivider(),
          _WayRow(
            iconText: '♙',
            title: 'С живым стилистом',
            text:
                'Онлайн или в пространстве. Поможет подобрать, проверить наличие и довести до покупки.',
          ),
          _PanelDivider(),
          _WayRow(
            iconText: 'AI',
            title: 'Через AI-подбор',
            text: 'Подбор по фото, форме, масштабу и стилю.',
          ),
        ],
      ),
    );
  }
}

class _WayRow extends StatelessWidget {
  const _WayRow({
    required this.iconText,
    required this.title,
    required this.text,
  });

  final String iconText;
  final String title;
  final String text;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      minHeight: 118,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          SizedBox(
            width: 74,
            child: Center(
              child: Text(
                iconText,
                style: const TextStyle(
                  fontFamily: GlameTypography.fontFamily,
                  fontSize: 24,
                  color: GlameColors.graphite,
                  fontWeight: FontWeight.w300,
                ),
              ),
            ),
          ),
          Container(width: 1, height: 62, color: GlameColors.lineGrey),
          const SizedBox(width: 28),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  title,
                  style: const TextStyle(
                    fontFamily: GlameTypography.fontFamily,
                    fontSize: 22,
                    height: 1.2,
                    color: GlameColors.graphite,
                    fontWeight: FontWeight.w300,
                  ),
                ),
                const SizedBox(height: 9),
                Text(
                  text,
                  style: const TextStyle(
                    fontFamily: GlameTypography.fontFamily,
                    fontSize: 14,
                    height: 1.35,
                    color: GlameColors.steelGrey,
                    fontWeight: FontWeight.w300,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 18),
          const Text(
            '→',
            style: TextStyle(
              fontSize: 27,
              color: GlameColors.graphite,
              fontWeight: FontWeight.w300,
            ),
          ),
          const SizedBox(width: 18),
        ],
      ),
    );
  }
}

class _PurchaseSteps extends StatelessWidget {
  const _PurchaseSteps();

  @override
  Widget build(BuildContext context) {
    return const _OutlinedPanel(
      title: '4 шага покупки',
      child: Column(
        children: <Widget>[
          _StepRow(
            number: '01',
            title: 'Выберите способ подбора',
            text: 'Решите, как вам удобнее подобрать украшение.',
          ),
          _PanelDivider(),
          _StepRow(
            number: '02',
            title: 'Уточните наличие',
            text: 'Мы проверим актуальность и предложим лучшие варианты.',
          ),
          _PanelDivider(),
          _StepRow(
            number: '03',
            title: 'Оформите покупку',
            text: 'Оплатите удобным способом — онлайн или в пространстве GLAME.',
          ),
          _PanelDivider(),
          _StepRow(
            number: '04',
            title: 'Получите заказ',
            text: 'Доставка по России или самовывоз из пространства GLAME.',
          ),
        ],
      ),
    );
  }
}

class _StepRow extends StatelessWidget {
  const _StepRow({
    required this.number,
    required this.title,
    required this.text,
  });

  final String number;
  final String title;
  final String text;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      minHeight: 95,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          SizedBox(
            width: 72,
            child: Text(
              number,
              style: const TextStyle(
                fontFamily: GlameTypography.fontFamily,
                fontSize: 36,
                height: 1,
                color: GlameColors.steelGrey,
                fontWeight: FontWeight.w300,
              ),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  title,
                  style: const TextStyle(
                    fontFamily: GlameTypography.fontFamily,
                    fontSize: 17,
                    height: 1.18,
                    color: GlameColors.graphite,
                    fontWeight: FontWeight.w300,
                  ),
                ),
                const SizedBox(height: 7),
                Text(
                  text,
                  style: const TextStyle(
                    fontFamily: GlameTypography.fontFamily,
                    fontSize: 13,
                    height: 1.25,
                    color: GlameColors.steelGrey,
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

class _OutlinedPanel extends StatelessWidget {
  const _OutlinedPanel({
    required this.title,
    required this.child,
  });

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          title,
          style: const TextStyle(
            fontFamily: GlameTypography.fontFamily,
            fontSize: 22,
            height: 1.2,
            color: GlameColors.graphite,
            fontWeight: FontWeight.w300,
          ),
        ),
        const SizedBox(height: 18),
        Container(
          decoration: BoxDecoration(
            color: GlameColors.white.withOpacity(0.44),
            borderRadius: BorderRadius.zero,
            border: Border.all(color: GlameColors.lineGrey, width: 1),
          ),
          child: child,
        ),
      ],
    );
  }
}

class _PanelDivider extends StatelessWidget {
  const _PanelDivider();

  @override
  Widget build(BuildContext context) {
    return Container(height: 1, color: GlameColors.lineGrey);
  }
}

class _BottomMessage extends StatelessWidget {
  const _BottomMessage();

  @override
  Widget build(BuildContext context) {
    return const Text(
      'Выберите сами или передайте задачу GLAME: живому стилисту онлайн / в пространстве или AI-подбору.',
      style: TextStyle(
        fontFamily: GlameTypography.fontFamily,
        fontSize: 15,
        height: 1.38,
        color: GlameColors.steelGrey,
        fontWeight: FontWeight.w300,
      ),
    );
  }
}

class _OutlineActionButton extends StatelessWidget {
  const _OutlineActionButton({
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
            height: 58,
            padding: const EdgeInsets.symmetric(horizontal: 18),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.zero,
              border: Border.all(color: GlameColors.graphite, width: 1),
            ),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    label,
                    style: const TextStyle(
                      fontFamily: GlameTypography.fontFamily,
                      fontSize: 15,
                      color: GlameColors.graphite,
                      fontWeight: FontWeight.w300,
                    ),
                  ),
                ),
                const Text(
                  '→',
                  style: TextStyle(
                    fontSize: 25,
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

class GlameColors {
  static const Color graphite = Color(0xFF2E3032);
  static const Color steelGrey = Color(0xFF73777A);
  static const Color steelLight = Color(0xFFE3E5E7);
  static const Color white = Color(0xFFF8F9F9);
  static const Color lineGrey = Color(0xFFC7C9CB);
}

class GlameTypography {
  /// Replace with the exact GLAME app font family from pubspec.yaml.
  static const String fontFamily = 'GlameSans';
}
