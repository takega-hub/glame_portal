import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/network/asset_url.dart';
import '../../core/theme/glame_theme.dart';
import '../customer/customer_cabinet_providers.dart';
import '../customer/stylist_entry.dart';
import '../home/home_providers.dart';
import '../home/photo_upload_screen.dart';

const String _block6FallbackBackgroundAsset =
    'assets/images/home/glame_home_block6_background_underlay.png';

class HomeHowToBuyBlock extends ConsumerWidget {
  final double? viewportHeight;

  const HomeHowToBuyBlock({super.key, this.viewportHeight});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final block = ref.watch(homeHowToBuyBlockProvider).asData?.value;
    final stylistStatus = ref.watch(stylistChatStatusProvider).asData?.value;
    final backgroundMode = block?['background_mode'] as String?;
    final backgroundColorHex = block?['background_color_hex'];
    final backgroundColor = _block6BackgroundColor(
      backgroundMode == 'color' ? backgroundColorHex : null,
    );
    final textColor =
        _block6TextColor(block?['text_color_hex']) ?? _Block6Palette.darkText;
    final backgroundSource = backgroundColor == null
        ? resolveAssetUrl(block?['background_image_url']) ??
              resolveAssetUrl(block?['image_url']) ??
              _block6FallbackBackgroundAsset
        : null;
    final isStylistOnline = stylistStatus?['is_open'] == true;
    final statusText =
        (stylistStatus?['status_text'] as String?)?.trim().isNotEmpty == true
        ? (stylistStatus!['status_text'] as String).trim()
        : (isStylistOnline
              ? 'На связи сейчас · до 20:00 по МСК'
              : 'Сейчас не на связи · с 10:00 по МСК');
    final compact = viewportHeight != null;
    final targetHeight = viewportHeight;
    final topBarBottom =
        MediaQuery.of(context).padding.top +
        GlameUi.heroTopOffset +
        GlameUi.heroTopBarHeight;
    final topPadding = compact ? topBarBottom + 18.0 : 68.0;
    final bottomPadding = compact ? 10.0 : 44.0;
    final actionGap = compact ? 8.0 : 16.0;

    return Container(
      height: targetHeight,
      width: double.infinity,
      color: backgroundColor ?? _Block6Palette.graphite,
      constraints: BoxConstraints(
        minHeight: compact ? (targetHeight ?? 0) : 1010,
      ),
      child: Stack(
        children: [
          if (backgroundSource != null)
            Positioned.fill(
              child: _ServiceImageLayer(
                source: backgroundSource,
                fit: BoxFit.cover,
                alignment: Alignment.center,
              ),
            ),
          if (backgroundSource != null)
            Positioned.fill(
              child: IgnorePointer(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [
                        Colors.black.withValues(alpha: 0.2),
                        const Color(0xFF101214).withValues(alpha: 0.05),
                        Colors.black.withValues(alpha: 0.36),
                      ],
                      stops: const [0.0, 0.46, 1.0],
                    ),
                  ),
                ),
              ),
            ),
          Padding(
            padding: EdgeInsets.fromLTRB(28, topPadding, 28, bottomPadding),
            child: Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _Block6Header(compact: compact, color: textColor),
                    if (compact) const Spacer(),
                    if (!compact) const SizedBox(height: 44),
                    _Block6ActionPanel(
                      number: '01',
                      title: 'Самостоятельно',
                      text: 'Каталог, бренды и подборки.',
                      onTap: () => context.push('/catalog'),
                      compact: compact,
                    ),
                    SizedBox(height: actionGap),
                    _Block6ActionPanel(
                      number: '02',
                      title: 'С живым стилистом',
                      text: 'Онлайн или в пространстве.',
                      status: statusText,
                      onTap: () => showStylistContactSheet(
                        context,
                        source: 'home_block_6',
                        scenario: 'live_stylist',
                        statusPayload: stylistStatus,
                      ),
                      compact: compact,
                    ),
                    SizedBox(height: actionGap),
                    _Block6ActionPanel(
                      number: '03',
                      title: 'Через AI-подбор',
                      text: 'По фото, форме, масштабу и стилю.',
                      onTap: () => showPhotoUploadSheet(context),
                      compact: compact,
                    ),
                    if (compact) const Spacer(flex: 2),
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

class _Block6Header extends StatelessWidget {
  final bool compact;
  final Color color;

  const _Block6Header({this.compact = false, required this.color});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: compact ? 330 : 350,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Как выбрать\nи купить',
            style: TextStyle(
              fontSize: compact ? 34 : 44,
              height: 1.04,
              letterSpacing: 0,
              color: color,
              fontWeight: FontWeight.w300,
            ),
          ),
          SizedBox(height: compact ? 12 : 24),
          SizedBox(
            width: compact ? 42 : 52,
            child: Divider(
              height: 1,
              thickness: 1,
              color: color,
            ),
          ),
          SizedBox(height: compact ? 14 : 28),
          Text(
            'Онлайн-заказ в GLAME не должен быть покупкой вслепую. Мы поможем выбрать украшение спокойно — до оплаты и во время примерки.',
            style: TextStyle(
              fontSize: compact ? 13.5 : 17,
              height: compact ? 1.32 : 1.38,
              color: color.withValues(alpha: 0.76),
              fontWeight: FontWeight.w300,
            ),
          ),
        ],
      ),
    );
  }
}

class _Block6ActionPanel extends StatelessWidget {
  const _Block6ActionPanel({
    required this.number,
    required this.title,
    required this.text,
    required this.onTap,
    this.status,
    this.compact = false,
  });

  final String number;
  final String title;
  final String text;
  final String? status;
  final VoidCallback onTap;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: title,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          splashColor: _Block6Palette.white.withValues(alpha: 0.05),
          highlightColor: _Block6Palette.white.withValues(alpha: 0.03),
          child: Container(
            constraints: BoxConstraints(minHeight: compact ? 76 : 112),
            padding: EdgeInsets.fromLTRB(
              compact ? 14 : 22,
              compact ? 12 : 22,
              compact ? 14 : 20,
              compact ? 12 : 20,
            ),
            decoration: BoxDecoration(
              color: _Block6Palette.panelBackground,
              border: Border.all(color: _Block6Palette.line, width: 1),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                SizedBox(
                  width: compact ? 42 : 56,
                  child: Center(
                    child: Text(
                      number,
                      style: TextStyle(
                        fontSize: compact ? 22 : 26,
                        height: 1.0,
                        color: _Block6Palette.white,
                        fontWeight: FontWeight.w300,
                      ),
                    ),
                  ),
                ),
                SizedBox(width: compact ? 14 : 22),
                Container(
                  width: 1,
                  height: compact ? 48 : 58,
                  color: _Block6Palette.line,
                ),
                SizedBox(width: compact ? 16 : 22),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title.toUpperCase(),
                        style: TextStyle(
                          fontSize: compact ? 15 : 20,
                          height: 1.08,
                          letterSpacing: compact ? 0.5 : 0.4,
                          color: _Block6Palette.white,
                          fontWeight: FontWeight.w300,
                        ),
                      ),
                      SizedBox(height: compact ? 3 : 9),
                      Text(
                        text,
                        style: TextStyle(
                          fontSize: compact ? 12 : 14,
                          height: compact ? 1.15 : 1.28,
                          color: _Block6Palette.lightText,
                          fontWeight: FontWeight.w300,
                        ),
                      ),
                      if (status != null) ...[
                        SizedBox(height: compact ? 4 : 10),
                        Text(
                          status!,
                          style: TextStyle(
                            fontSize: compact ? 10 : 12,
                            height: 1.15,
                            color: _Block6Palette.steel,
                            fontWeight: FontWeight.w300,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                SizedBox(width: compact ? 6 : 14),
                Text(
                  '→',
                  style: TextStyle(
                    fontSize: compact ? 26 : 28,
                    color: _Block6Palette.white,
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

class _Block6Palette {
  static const Color graphite = Color(0xFF222426);
  static const Color darkText = Color(0xFF242628);
  static const Color panelBackground = Color(0x96292C2F);
  static const Color white = Color(0xFFEFF1F2);
  static const Color lightText = Color(0xFFC7CBCF);
  static const Color steel = Color(0xFF8E9397);
  static const Color line = Color(0xFF5C6064);
}

Color? _block6BackgroundColor(dynamic rawValue) {
  final value = rawValue is String ? rawValue.trim() : '';
  final match = RegExp(r'^#?([0-9A-Fa-f]{6})$').firstMatch(value);
  if (match == null) return null;
  return Color(int.parse('FF${match.group(1)!}', radix: 16));
}

Color? _block6TextColor(dynamic rawValue) {
  final value = rawValue is String ? rawValue.trim() : '';
  final match = RegExp(r'^#?([0-9A-Fa-f]{6})$').firstMatch(value);
  if (match == null) return null;
  return Color(int.parse('FF${match.group(1)!}', radix: 16));
}

class SelectionMethodScreen extends ConsumerWidget {
  final String? mode;
  final bool showAppBar;

  const SelectionMethodScreen({super.key, this.mode, this.showAppBar = true});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final normalizedMode = (mode ?? '').trim().toLowerCase();
    final isGiftMode = normalizedMode == 'gift';
    final stylistStatus = ref.watch(stylistChatStatusProvider).asData?.value;

    final content = _SelectionMethodContent(
      isGiftMode: isGiftMode,
      showAppBar: showAppBar,
      stylistStatus: stylistStatus,
    );
    if (!showAppBar) {
      return ColoredBox(color: GlameColors.nearBlack, child: content);
    }

    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      appBar: showAppBar ? const GlameTopAppBar(dark: true) : null,
      body: content,
    );
  }
}

class _SelectionMethodContent extends StatelessWidget {
  final bool isGiftMode;
  final bool showAppBar;
  final Map<String, dynamic>? stylistStatus;

  const _SelectionMethodContent({
    required this.isGiftMode,
    required this.showAppBar,
    required this.stylistStatus,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: showAppBar,
      bottom: false,
      child: Container(
        width: double.infinity,
        height: double.infinity,
        color: GlameColors.nearBlack,
        child: Padding(
          padding: EdgeInsets.fromLTRB(28, showAppBar ? 24 : 22, 28, 32),
          child: Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 520),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _SelectionHeader(
                    title: isGiftMode ? 'Подобрать подарок' : 'Подбор',
                  ),
                  const SizedBox(height: 20),
                  _SelectionMethodRow(
                    number: '01',
                    title: 'Через AI-подбор',
                    description: isGiftMode
                        ? 'По поводу, стилю и масштабу'
                        : 'По фото, форме и масштабу',
                    onTap: () => showPhotoUploadSheet(context),
                  ),
                  const SizedBox(height: 14),
                  _SelectionMethodRow(
                    number: '02',
                    title: 'С живым стилистом',
                    description: 'Онлайн или в пространстве',
                    onTap: () => showStylistContactSheet(
                      context,
                      initialMessage: isGiftMode
                          ? 'Хочу подобрать подарок с помощью стилиста GLAME.'
                          : null,
                      source: isGiftMode
                          ? 'selection_gift'
                          : 'selection_screen',
                      scenario: 'live_stylist',
                      quickTags: isGiftMode
                          ? const <String>['gift']
                          : const <String>[],
                      statusPayload: stylistStatus,
                    ),
                  ),
                  const SizedBox(height: 22),
                  Expanded(
                    child: _SelectionProcessPanel(isGiftMode: isGiftMode),
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

/*
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: ListView(
              padding: EdgeInsets.fromLTRB(28, showAppBar ? 24 : 22, 28, 32),
              children: [
                const _SelectionHeader(),
                const SizedBox(height: 20),
                _SelectionMethodRow(
                  number: '01',
                  title: 'Через AI-подбор',
                  description: 'По фото, форме и масштабу',
                  onTap: () => context.push(
                    isGiftMode
                        ? '/selection/ai-photo?mode=gift'
                        : '/selection/ai-photo',
                  ),
                ),
                const SizedBox(height: 14),
                _SelectionMethodRow(
                  number: '02',
                  title: 'С живым стилистом',
                  description: 'Онлайн или в пространстве',
                  onTap: () => showStylistContactSheet(
                    context,
                    initialMessage: isGiftMode
                        ? 'Хочу подобрать подарок с помощью стилиста GLAME.'
                        : null,
                    source: isGiftMode ? 'selection_gift' : 'selection_screen',
                    scenario: 'live_stylist',
                    quickTags: isGiftMode
                        ? const <String>['gift']
                        : const <String>[],
                    statusPayload: stylistStatus,
                  ),
                ),
                const SizedBox(height: 14),
                _SelectionMethodRow(
                  number: '03',
                  title: 'Подобрать подарок',
                  description: 'Для особенного момента',
                  onTap: () => context.push('/selection/gift'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
*/

class _SelectionHeader extends StatelessWidget {
  final String title;

  const _SelectionHeader({this.title = 'Подбор'});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontSize: 24,
            height: 1.1,
            color: GlameColors.whiteGlame,
            fontWeight: FontWeight.w400,
          ),
        ),
        const SizedBox(height: 12),
        const Divider(height: 1, thickness: 1, color: GlameColors.borderGray),
      ],
    );
  }
}

class _SelectionMethodRow extends StatelessWidget {
  const _SelectionMethodRow({
    required this.number,
    required this.title,
    required this.description,
    required this.onTap,
  });

  final String number;
  final String title;
  final String description;
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
          splashColor: GlameColors.whiteGlame.withValues(alpha: 0.05),
          highlightColor: GlameColors.whiteGlame.withValues(alpha: 0.03),
          child: Container(
            height: 88,
            decoration: BoxDecoration(
              color: const Color(0xFF18191A),
              border: Border.all(color: const Color(0xFF55585C)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                SizedBox(
                  width: 54,
                  child: Center(
                    child: Text(
                      number,
                      style: const TextStyle(
                        fontSize: 13,
                        color: GlameColors.whiteGlame,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
                Container(width: 1, color: const Color(0xFF55585C)),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(18, 17, 12, 15),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 15,
                            height: 1.15,
                            color: GlameColors.whiteGlame,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          description,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 12,
                            height: 1.25,
                            color: GlameColors.textSecondary,
                            fontWeight: FontWeight.w400,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(
                  width: 48,
                  child: Center(
                    child: Icon(
                      Icons.chevron_right,
                      size: 24,
                      color: GlameColors.whiteGlame,
                    ),
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

class _SelectionProcessPanel extends StatelessWidget {
  final bool isGiftMode;

  const _SelectionProcessPanel({required this.isGiftMode});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFF151617),
        border: Border.all(color: GlameColors.borderGray),
      ),
      child: Stack(
        children: [
          Positioned.fill(
            child: CustomPaint(painter: _SelectionProcessPainter()),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 22, 20, 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Как работает подбор',
                  style: TextStyle(
                    fontSize: 18,
                    height: 1.15,
                    color: GlameColors.whiteGlame,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 18),
                _SelectionProcessStep(
                  number: '01',
                  title: isGiftMode
                      ? 'Опишите повод и получателя'
                      : 'Вы загружаете фото или задачу',
                ),
                const _SelectionProcessStep(
                  number: '02',
                  title: 'Мы считываем форму, масштаб и стиль',
                ),
                const _SelectionProcessStep(
                  number: '03',
                  title: 'Показываем украшения, которые подходят образу',
                ),
                const Spacer(),
                Text(
                  isGiftMode
                      ? 'Подарочный сценарий можно разобрать со стилистом: повод, бюджет и формат вручения.'
                      : 'Можно начать с AI-подбора или сразу передать задачу стилисту.',
                  style: const TextStyle(
                    fontSize: 12,
                    height: 1.35,
                    color: GlameColors.steelGray,
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

class _SelectionProcessStep extends StatelessWidget {
  final String number;
  final String title;

  const _SelectionProcessStep({required this.number, required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 34,
            child: Text(
              number,
              style: const TextStyle(
                fontSize: 11,
                letterSpacing: 0.7,
                color: GlameColors.steelGray,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                fontSize: 14,
                height: 1.25,
                color: GlameColors.whiteGlame,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SelectionProcessPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final linePaint = Paint()
      ..color = GlameColors.borderGray.withValues(alpha: 0.22)
      ..strokeWidth = 1;
    final accentPaint = Paint()
      ..color = GlameColors.gold.withValues(alpha: 0.28)
      ..strokeWidth = 1.2
      ..style = PaintingStyle.stroke;

    for (var y = 34.0; y < size.height; y += 42) {
      canvas.drawLine(
        Offset(size.width * 0.58, y),
        Offset(size.width, y),
        linePaint,
      );
    }

    final path = Path()
      ..moveTo(size.width * 0.58, size.height * 0.28)
      ..quadraticBezierTo(
        size.width * 0.78,
        size.height * 0.14,
        size.width * 0.96,
        size.height * 0.32,
      )
      ..quadraticBezierTo(
        size.width * 0.76,
        size.height * 0.52,
        size.width * 0.92,
        size.height * 0.74,
      );
    canvas.drawPath(path, accentPaint);
    canvas.drawCircle(
      Offset(size.width * 0.84, size.height * 0.42),
      42,
      Paint()
        ..color = GlameColors.whiteGlame.withValues(alpha: 0.025)
        ..style = PaintingStyle.fill,
    );
  }

  @override
  bool shouldRepaint(covariant _SelectionProcessPainter oldDelegate) {
    return false;
  }
}

class _ServiceImageLayer extends StatelessWidget {
  const _ServiceImageLayer({
    required this.source,
    this.fit = BoxFit.cover,
    this.alignment = Alignment.center,
  });

  final String source;
  final BoxFit fit;
  final Alignment alignment;

  @override
  Widget build(BuildContext context) {
    final resolvedSource = resolveAssetUrl(source) ?? source;
    if (resolvedSource.startsWith('http://') ||
        resolvedSource.startsWith('https://')) {
      return CachedNetworkImage(
        imageUrl: resolvedSource,
        fit: fit,
        alignment: alignment,
        placeholder: (_, _) =>
            const ColoredBox(color: GlameColors.coldLightGrey),
        errorWidget: (_, _, _) => _fallbackBox(),
      );
    }

    if (resolvedSource == _block6FallbackBackgroundAsset ||
        resolvedSource.startsWith('assets/')) {
      return Image.asset(resolvedSource, fit: fit, alignment: alignment);
    }

    return _fallbackBox();
  }

  Widget _fallbackBox() {
    return const ColoredBox(color: GlameColors.coldLightGrey);
  }
}
