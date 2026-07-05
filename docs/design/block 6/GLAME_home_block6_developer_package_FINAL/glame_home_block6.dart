import 'package:flutter/material.dart';

/// GLAME — Home Block 6: "Как выбрать и купить"
///
/// Final service/action block of the Home page.
/// No route to /service/how-to-buy.
/// Three action panels are the primary CTAs.
class GlameHomeBlock6 extends StatelessWidget {
  const GlameHomeBlock6({
    super.key,
    required this.onOpenCatalog,
    required this.onOpenLiveStylist,
    required this.onOpenAiSelection,
    required this.isStylistOnline,
    this.backgroundAsset = 'assets/images/home/glame_home_block6_background_underlay.png',
  });

  final VoidCallback onOpenCatalog;
  final VoidCallback onOpenLiveStylist;
  final VoidCallback onOpenAiSelection;
  final bool isStylistOnline;
  final String backgroundAsset;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: GlameColors.graphite,
      width: double.infinity,
      constraints: const BoxConstraints(minHeight: 980),
      child: Stack(
        children: [
          Positioned.fill(
            child: Image.asset(
              backgroundAsset,
              fit: BoxFit.cover,
              alignment: Alignment.center,
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(28, 68, 28, 44),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _BlockHeader(),
                const SizedBox(height: 44),
                _ActionPanel(
                  number: '01',
                  title: 'Самостоятельно',
                  text: 'Каталог, бренды и подборки.',
                  onTap: onOpenCatalog,
                ),
                const SizedBox(height: 14),
                _ActionPanel(
                  number: '02',
                  title: 'С живым стилистом',
                  text: 'Онлайн или в пространстве.',
                  status: isStylistOnline
                      ? 'На связи сейчас · до 20:00 по МСК'
                      : 'Сейчас не на связи · с 10:00 по МСК',
                  onTap: onOpenLiveStylist,
                ),
                const SizedBox(height: 14),
                _ActionPanel(
                  number: '03',
                  title: 'Через AI-подбор',
                  text: 'По фото, форме, масштабу и стилю.',
                  onTap: onOpenAiSelection,
                ),
                const SizedBox(height: 48),
                const _ServiceZone(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _BlockHeader extends StatelessWidget {
  const _BlockHeader();

  @override
  Widget build(BuildContext context) {
    return const SizedBox(
      width: 350,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Как выбрать\nи купить',
            style: TextStyle(
              fontFamily: GlameTypography.fontFamily,
              fontSize: 44,
              height: 1.1,
              letterSpacing: -0.6,
              color: GlameColors.white,
              fontWeight: FontWeight.w300,
            ),
          ),
          SizedBox(height: 24),
          SizedBox(
            width: 52,
            child: Divider(
              height: 1,
              thickness: 1,
              color: GlameColors.white,
            ),
          ),
          SizedBox(height: 28),
          Text(
            'Онлайн-заказ в GLAME не должен быть покупкой вслепую. Мы поможем выбрать украшение спокойно — до оплаты и во время примерки.',
            style: TextStyle(
              fontFamily: GlameTypography.fontFamily,
              fontSize: 17,
              height: 1.38,
              color: GlameColors.lightText,
              fontWeight: FontWeight.w300,
            ),
          ),
        ],
      ),
    );
  }
}

class _ActionPanel extends StatelessWidget {
  const _ActionPanel({
    required this.number,
    required this.title,
    required this.text,
    required this.onTap,
    this.status,
  });

  final String number;
  final String title;
  final String text;
  final String? status;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: title,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          splashColor: GlameColors.white.withOpacity(0.05),
          highlightColor: GlameColors.white.withOpacity(0.03),
          child: Container(
            minHeight: 104,
            padding: const EdgeInsets.fromLTRB(22, 22, 20, 20),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.zero,
              border: Border.all(color: GlameColors.line, width: 1),
            ),
            child: Row(
              children: [
                SizedBox(
                  width: 48,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        number,
                        style: const TextStyle(
                          fontFamily: GlameTypography.fontFamily,
                          fontSize: 14,
                          color: GlameColors.steel,
                          fontWeight: FontWeight.w300,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Container(width: 32, height: 1, color: GlameColors.steel),
                    ],
                  ),
                ),
                const SizedBox(width: 22),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: const TextStyle(
                          fontFamily: GlameTypography.fontFamily,
                          fontSize: 22,
                          height: 1.12,
                          color: GlameColors.white,
                          fontWeight: FontWeight.w300,
                        ),
                      ),
                      const SizedBox(height: 9),
                      Text(
                        text,
                        style: const TextStyle(
                          fontFamily: GlameTypography.fontFamily,
                          fontSize: 14,
                          height: 1.28,
                          color: GlameColors.lightText,
                          fontWeight: FontWeight.w300,
                        ),
                      ),
                      if (status != null) ...[
                        const SizedBox(height: 10),
                        Text(
                          status!,
                          style: const TextStyle(
                            fontFamily: GlameTypography.fontFamily,
                            fontSize: 12,
                            color: GlameColors.steel,
                            fontWeight: FontWeight.w300,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const Text(
                  '→',
                  style: TextStyle(
                    fontSize: 28,
                    color: GlameColors.white,
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

class _ServiceZone extends StatelessWidget {
  const _ServiceZone();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Чтобы онлайн-покупка\nбыла спокойной',
          style: TextStyle(
            fontFamily: GlameTypography.fontFamily,
            fontSize: 27,
            height: 1.12,
            color: GlameColors.white,
            fontWeight: FontWeight.w300,
          ),
        ),
        SizedBox(height: 22),
        Row(
          children: [
            Expanded(
              child: _ServiceTile(
                number: '01',
                title: 'Примерка перед покупкой',
                text:
                    'Курьер привозит изделия для примерки: вы выбираете и оплачиваете только то, что подошло, остальное возвращается с курьером.',
              ),
            ),
            SizedBox(width: 14),
            Expanded(
              child: _ServiceTile(
                number: '02',
                title: 'Детали до заказа',
                text:
                    'Уточним размер, длину, застёжку, цвет, фактуру, вес и масштаб изделия.',
              ),
            ),
          ],
        ),
        SizedBox(height: 14),
        Row(
          children: [
            Expanded(
              child: _ServiceTile(
                number: '03',
                title: 'Гарантия и уход',
                text:
                    'Расскажем условия по конкретному изделию и подскажем, как за ним ухаживать.',
              ),
            ),
            SizedBox(width: 14),
            Expanded(
              child: _ServiceTile(
                number: '04',
                title: 'Поддержка и Клуб стильных',
                text:
                    'Можно обратиться в GLAME после покупки. Покупки участвуют в программе лояльности.',
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _ServiceTile extends StatelessWidget {
  const _ServiceTile({
    required this.number,
    required this.title,
    required this.text,
  });

  final String number;
  final String title;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 158,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.zero,
        border: Border.all(color: GlameColors.line, width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            number,
            style: const TextStyle(
              fontFamily: GlameTypography.fontFamily,
              fontSize: 12,
              color: GlameColors.steel,
              fontWeight: FontWeight.w300,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontFamily: GlameTypography.fontFamily,
              fontSize: 14,
              height: 1.15,
              color: GlameColors.white,
              fontWeight: FontWeight.w300,
            ),
          ),
          const SizedBox(height: 9),
          Expanded(
            child: Text(
              text,
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontFamily: GlameTypography.fontFamily,
                fontSize: 10.5,
                height: 1.25,
                color: GlameColors.lightText,
                fontWeight: FontWeight.w300,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class GlameColors {
  static const Color graphite = Color(0xFF222426);
  static const Color white = Color(0xFFEFF1F2);
  static const Color lightText = Color(0xFFC7CBCF);
  static const Color steel = Color(0xFF8E9397);
  static const Color line = Color(0xFF5C6064);
}

class GlameTypography {
  /// Replace with Clinica Pro in pubspec.yaml.
  static const String fontFamily = 'ClinicaPro';
}
