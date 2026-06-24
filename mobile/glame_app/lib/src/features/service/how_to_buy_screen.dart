import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/network/asset_url.dart';
import '../../core/theme/glame_theme.dart';
import '../customer/customer_cabinet_providers.dart';
import '../customer/stylist_entry.dart';
import '../home/home_providers.dart';

const String _block6FallbackBackgroundAsset =
    'assets/images/home/glame_home_block6_background_underlay.png';

class HomeHowToBuyBlock extends ConsumerWidget {
  final double? viewportHeight;

  const HomeHowToBuyBlock({super.key, this.viewportHeight});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final block = ref.watch(homeHowToBuyBlockProvider).asData?.value;
    final stylistStatus = ref.watch(stylistChatStatusProvider).asData?.value;
    final backgroundSource =
        resolveAssetUrl(block?['background_image_url']) ??
        resolveAssetUrl(block?['image_url']) ??
        _block6FallbackBackgroundAsset;
    final isStylistOnline = stylistStatus?['is_open'] == true;
    final statusText =
        (stylistStatus?['status_text'] as String?)?.trim().isNotEmpty == true
        ? (stylistStatus!['status_text'] as String).trim()
        : (isStylistOnline
              ? 'На связи сейчас · до 20:00 по МСК'
              : 'Сейчас не на связи · с 10:00 по МСК');
    final compact = viewportHeight != null;
    final targetHeight = viewportHeight;
    final topPadding = compact ? 76.0 : 68.0;
    final bottomPadding = compact ? 14.0 : 44.0;
    final actionGap = compact ? 7.0 : 14.0;
    final serviceGap = compact ? 20.0 : 48.0;

    return Container(
      height: targetHeight,
      width: double.infinity,
      color: _Block6Palette.graphite,
      constraints: BoxConstraints(
        minHeight: compact ? (targetHeight ?? 0) : 1010,
      ),
      child: Stack(
        children: [
          Positioned.fill(
            child: _ServiceImageLayer(
              source: backgroundSource,
              fit: BoxFit.cover,
              alignment: Alignment.center,
            ),
          ),
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
                    _Block6Header(compact: compact),
                    SizedBox(height: compact ? 12 : 44),
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
                      onTap: () => context.push('/selection/ai-photo'),
                      compact: compact,
                    ),
                    SizedBox(height: serviceGap),
                    _Block6ServiceZone(compact: compact),
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

  const _Block6Header({this.compact = false});

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
              color: _Block6Palette.white,
              fontWeight: FontWeight.w300,
            ),
          ),
          SizedBox(height: compact ? 12 : 24),
          SizedBox(
            width: compact ? 42 : 52,
            child: Divider(
              height: 1,
              thickness: 1,
              color: _Block6Palette.white,
            ),
          ),
          SizedBox(height: compact ? 14 : 28),
          Text(
            'Онлайн-заказ в GLAME не должен быть покупкой вслепую. Мы поможем выбрать украшение спокойно — до оплаты и во время примерки.',
            style: TextStyle(
              fontSize: compact ? 13.5 : 17,
              height: compact ? 1.32 : 1.38,
              color: _Block6Palette.lightText,
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
            constraints: BoxConstraints(minHeight: compact ? 72 : 104),
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
                  width: compact ? 36 : 56,
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
                SizedBox(width: compact ? 12 : 22),
                Container(
                  width: 1,
                  height: compact ? 42 : 58,
                  color: _Block6Palette.line,
                ),
                SizedBox(width: compact ? 14 : 22),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title.toUpperCase(),
                        style: TextStyle(
                          fontSize: compact ? 15.5 : 20,
                          height: 1.08,
                          letterSpacing: compact ? 0.5 : 0.4,
                          color: _Block6Palette.white,
                          fontWeight: FontWeight.w300,
                        ),
                      ),
                      SizedBox(height: compact ? 5 : 9),
                      Text(
                        text,
                        style: TextStyle(
                          fontSize: compact ? 12.5 : 14,
                          height: compact ? 1.22 : 1.28,
                          color: _Block6Palette.lightText,
                          fontWeight: FontWeight.w300,
                        ),
                      ),
                      if (status != null) ...[
                        SizedBox(height: compact ? 6 : 10),
                        Text(
                          status!,
                          style: TextStyle(
                            fontSize: compact ? 10.5 : 12,
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

class _Block6ServiceZone extends StatelessWidget {
  final bool compact;

  const _Block6ServiceZone({this.compact = false});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              flex: 3,
              child: Text(
                'Чтобы онлайн-покупка\nбыла спокойной',
                style: TextStyle(
                  fontSize: compact ? 18 : 22,
                  height: compact ? 1.08 : 1.12,
                  letterSpacing: 0,
                  color: _Block6Palette.white,
                  fontWeight: FontWeight.w300,
                ),
              ),
            ),
            SizedBox(width: compact ? 8 : 14),
            Expanded(
              flex: 2,
              child: Container(height: 1, color: _Block6Palette.line),
            ),
          ],
        ),
        SizedBox(height: compact ? 10 : 18),
        Container(
          decoration: BoxDecoration(
            color: _Block6Palette.panelBackground,
            border: Border.all(color: _Block6Palette.line, width: 1),
          ),
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: _Block6ServiceTile(
                      number: '01',
                      title: 'ПРИМЕРКА\nПЕРЕД ПОКУПКОЙ',
                      text:
                          'Курьер привозит изделия для примерки: вы выбираете и оплачиваете только то, что подошло, остальное возвращается с курьером.',
                      compact: compact,
                    ),
                  ),
                  _Block6GridDivider.vertical(compact: compact),
                  Expanded(
                    child: _Block6ServiceTile(
                      number: '02',
                      title: 'ДЕТАЛИ\nДО ЗАКАЗА',
                      text:
                          'Уточним размер, длину, застёжку, цвет, фактуру, вес и масштаб изделия.',
                      compact: compact,
                    ),
                  ),
                ],
              ),
              const _Block6GridDivider.horizontal(),
              Row(
                children: [
                  Expanded(
                    child: _Block6ServiceTile(
                      number: '03',
                      title: 'ГАРАНТИЯ\nИ УХОД',
                      text:
                          'Расскажем условия по конкретному изделию и подскажем, как за ним ухаживать.',
                      compact: compact,
                    ),
                  ),
                  _Block6GridDivider.vertical(compact: compact),
                  Expanded(
                    child: _Block6ServiceTile(
                      number: '04',
                      title: 'ПОДДЕРЖКА\nИ КЛУБ СТИЛЬНЫХ',
                      text:
                          'Можно обратиться в GLAME после покупки. Покупки участвуют в программе лояльности.',
                      compact: compact,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _Block6ServiceTile extends StatelessWidget {
  const _Block6ServiceTile({
    required this.number,
    required this.title,
    required this.text,
    this.compact = false,
  });

  final String number;
  final String title;
  final String text;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: compact ? 126 : 190,
      padding: EdgeInsets.fromLTRB(
        compact ? 12 : 22,
        compact ? 12 : 22,
        compact ? 10 : 18,
        compact ? 10 : 18,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            number,
            style: TextStyle(
              fontSize: compact ? 12 : 30,
              height: 1.0,
              color: _Block6Palette.steel,
              fontWeight: FontWeight.w300,
            ),
          ),
          SizedBox(height: compact ? 10 : 18),
          Text(
            title,
            maxLines: 2,
            style: TextStyle(
              fontSize: compact ? 11.5 : 16,
              height: compact ? 1.08 : 1.15,
              letterSpacing: compact ? 0.2 : 0.3,
              color: _Block6Palette.white,
              fontWeight: FontWeight.w300,
            ),
          ),
          SizedBox(height: compact ? 7 : 14),
          Text(
            text,
            maxLines: compact ? 5 : 6,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: compact ? 9.2 : 14,
              height: compact ? 1.16 : 1.28,
              color: _Block6Palette.lightText,
              fontWeight: FontWeight.w300,
            ),
          ),
        ],
      ),
    );
  }
}

class _Block6GridDivider extends StatelessWidget {
  const _Block6GridDivider.horizontal()
    : axis = Axis.horizontal,
      compact = false;
  const _Block6GridDivider.vertical({this.compact = false})
    : axis = Axis.vertical;

  final Axis axis;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: axis == Axis.vertical ? 1 : double.infinity,
      height: axis == Axis.horizontal ? 1 : (compact ? 126 : 190),
      color: _Block6Palette.line,
    );
  }
}

class _Block6Palette {
  static const Color graphite = Color(0xFF222426);
  static const Color panelBackground = Color(0x96292C2F);
  static const Color white = Color(0xFFEFF1F2);
  static const Color lightText = Color(0xFFC7CBCF);
  static const Color steel = Color(0xFF8E9397);
  static const Color line = Color(0xFF5C6064);
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
    final heroTitle = isGiftMode
        ? 'Выберите способ подобрать подарок'
        : 'Выберите способ подбора';
    final heroDescription = isGiftMode
        ? 'Живой стилист поможет подобрать подарок под повод, бюджет и характер получателя. AI-подбор подскажет направление, если хотите начать с фото и стиля.'
        : 'Живой стилист помогает онлайн или в пространстве. AI-подбор подсказывает подходящие линии, форму и масштаб по фото.';
    final stylistActionLabel = isGiftMode
        ? 'Открыть стилиста по подарку'
        : 'Открыть стилиста';
    final stylistDescription = isGiftMode
        ? 'Поможет выбрать подарок, уточнить сценарий и довести выбор до покупки.'
        : 'Онлайн или в пространстве. Поможет подобрать, проверить наличие и довести до покупки.';
    final photoActionLabel = isGiftMode
        ? 'Начать с AI-подбора'
        : 'Запустить AI-подбор';
    final photoDescription = isGiftMode
        ? 'Подбор по фото и стилю поможет быстрее понять, какие украшения подойдут в подарок.'
        : 'Подбор по фото, форме, масштабу и стилю с переходом в уже настроенный сценарий приложения.';
    return Scaffold(
      backgroundColor: GlameColors.coldLightGrey,
      appBar: showAppBar ? const GlameTopAppBar() : null,
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
          children: [
            Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      heroTitle,
                      style: const TextStyle(
                        fontSize: 30,
                        height: 1.08,
                        color: GlameColors.graphite,
                        fontWeight: FontWeight.w300,
                      ),
                    ),
                    const SizedBox(height: 14),
                    Text(
                      heroDescription,
                      style: const TextStyle(
                        fontSize: 15,
                        height: 1.45,
                        color: GlameColors.steelGrey,
                        fontWeight: FontWeight.w300,
                      ),
                    ),
                    const SizedBox(height: 24),
                    _SelectionOptionCard(
                      title: isGiftMode
                          ? 'Живой стилист по подарку'
                          : 'Живой стилист',
                      description: stylistDescription,
                      actionLabel: stylistActionLabel,
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
                    const SizedBox(height: 14),
                    _SelectionOptionCard(
                      title: 'AI-подбор',
                      description: photoDescription,
                      actionLabel: photoActionLabel,
                      onTap: () => context.push(
                        isGiftMode
                            ? '/selection/ai-photo?mode=gift'
                            : '/selection/ai-photo',
                      ),
                    ),
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

class _SelectionOptionCard extends StatelessWidget {
  const _SelectionOptionCard({
    required this.title,
    required this.description,
    required this.actionLabel,
    required this.onTap,
  });

  final String title;
  final String description;
  final String actionLabel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.56),
        border: Border.all(color: GlameColors.lightGray),
      ),
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 22,
              color: GlameColors.graphite,
              fontWeight: FontWeight.w300,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            description,
            style: const TextStyle(
              fontSize: 14,
              height: 1.4,
              color: GlameColors.steelGrey,
              fontWeight: FontWeight.w300,
            ),
          ),
          const SizedBox(height: 16),
          _ServiceActionButton(label: actionLabel, onTap: onTap),
        ],
      ),
    );
  }
}

class _ServiceActionButton extends StatelessWidget {
  const _ServiceActionButton({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Container(
          height: 54,
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          decoration: BoxDecoration(
            border: Border.all(color: GlameColors.graphite),
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                    fontSize: 15,
                    color: GlameColors.graphite,
                    fontWeight: FontWeight.w300,
                  ),
                ),
              ),
              const Text(
                '→',
                style: TextStyle(
                  fontSize: 24,
                  color: GlameColors.graphite,
                  fontWeight: FontWeight.w300,
                ),
              ),
            ],
          ),
        ),
      ),
    );
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
