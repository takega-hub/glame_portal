import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/network/asset_url.dart';
import '../../core/theme/glame_theme.dart';
import '../home/home_providers.dart';

class ProfileNewsScreen extends ConsumerStatefulWidget {
  final String? initialNewsId;

  const ProfileNewsScreen({super.key, this.initialNewsId});

  @override
  ConsumerState<ProfileNewsScreen> createState() => _ProfileNewsScreenState();
}

class _ProfileNewsScreenState extends ConsumerState<ProfileNewsScreen> {
  bool _initialNewsOpened = false;

  @override
  Widget build(BuildContext context) {
    final newsAsync = ref.watch(homeNewsProvider);
    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      body: SafeArea(
        child: Column(
          children: [
            _NewsTopBar(
              onBack: () =>
                  context.canPop() ? context.pop() : context.go('/home?tab=4'),
            ),
            Expanded(
              child: newsAsync.when(
                data: (items) {
                  final news = items
                      .whereType<Map>()
                      .map((item) => Map<String, dynamic>.from(item))
                      .toList();
                  final targetId = (widget.initialNewsId ?? '').trim();
                  if (targetId.isNotEmpty && !_initialNewsOpened) {
                    WidgetsBinding.instance.addPostFrameCallback((_) {
                      if (!mounted || _initialNewsOpened) return;
                      for (var i = 0; i < news.length; i++) {
                        if (_newsString(news[i]['id']) == targetId) {
                          _initialNewsOpened = true;
                          Navigator.of(context).push(
                            MaterialPageRoute<void>(
                              builder: (_) => _NewsDetailScreen(
                                item: news[i],
                                number: (i + 1).toString().padLeft(2, '0'),
                              ),
                            ),
                          );
                          return;
                        }
                      }
                      _initialNewsOpened = true;
                    });
                  }
                  if (news.isEmpty) {
                    return const _NewsStateMessage(
                      text: 'Новости появятся здесь позднее.',
                    );
                  }
                  return RefreshIndicator(
                    color: GlameColors.nearBlack,
                    backgroundColor: GlameColors.whiteGlame,
                    onRefresh: () async {
                      ref.invalidate(homeNewsProvider);
                      await ref.read(homeNewsProvider.future);
                    },
                    child: ListView(
                      padding: const EdgeInsets.fromLTRB(0, 34, 0, 34),
                      children: [
                        const Padding(
                          padding: EdgeInsets.symmetric(
                            horizontal: GlameUi.pagePadding,
                          ),
                          child: Text(
                            'Новости',
                            style: TextStyle(
                              color: GlameColors.whiteGlame,
                              fontSize: 28,
                              height: 1.14,
                              fontWeight: FontWeight.w500,
                              letterSpacing: 0,
                            ),
                          ),
                        ),
                        const SizedBox(height: 30),
                        const Divider(height: 1, color: GlameColors.borderGray),
                        for (var i = 0; i < news.length; i++)
                          _NewsListRow(
                            number: (i + 1).toString().padLeft(2, '0'),
                            item: news[i],
                            onTap: () => Navigator.of(context).push(
                              MaterialPageRoute<void>(
                                builder: (_) => _NewsDetailScreen(
                                  item: news[i],
                                  number: (i + 1).toString().padLeft(2, '0'),
                                ),
                              ),
                            ),
                          ),
                      ],
                    ),
                  );
                },
                loading: () => const Center(
                  child: CircularProgressIndicator(
                    color: GlameColors.whiteGlame,
                  ),
                ),
                error: (_, _) => _NewsStateMessage(
                  text: 'Не удалось загрузить новости.',
                  actionLabel: 'Обновить',
                  onAction: () => ref.invalidate(homeNewsProvider),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NewsTopBar extends StatelessWidget {
  final VoidCallback onBack;

  const _NewsTopBar({required this.onBack});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 58,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Positioned(
            left: 4,
            child: IconButton(
              onPressed: onBack,
              icon: const Icon(Icons.arrow_back, size: 23),
              color: GlameColors.whiteGlame,
              tooltip: 'Назад',
            ),
          ),
          const GlameHeaderLogo(height: 24, silver: true),
        ],
      ),
    );
  }
}

class _NewsListRow extends StatelessWidget {
  final String number;
  final Map<String, dynamic> item;
  final VoidCallback onTap;

  const _NewsListRow({
    required this.number,
    required this.item,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final title = _newsString(item['title']) ?? 'Новость GLAME';
    final excerpt = _newsString(item['excerpt'] ?? item['description']);
    final date = _newsDateLabel(item['published_at'] ?? item['updated_at']);
    final imageUrl = resolveAssetUrl(
      item['preview_image_url'] ?? item['cover_image_url'],
    );

    return InkWell(
      onTap: onTap,
      splashColor: GlameColors.whiteGlame.withValues(alpha: 0.06),
      highlightColor: GlameColors.whiteGlame.withValues(alpha: 0.04),
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: GlameUi.pagePadding,
          vertical: 18,
        ),
        decoration: const BoxDecoration(
          border: Border(
            bottom: BorderSide(color: GlameColors.borderGray, width: 1),
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 42,
              child: Text(
                number,
                style: const TextStyle(
                  color: GlameColors.steelGray,
                  fontSize: 12,
                  height: 1,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.2,
                ),
              ),
            ),
            if (imageUrl != null) ...[
              _NewsPreviewImage(url: imageUrl),
              const SizedBox(width: 16),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (date != null) ...[
                    Text(
                      date,
                      style: const TextStyle(
                        color: GlameColors.steelGray,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1.1,
                      ),
                    ),
                    const SizedBox(height: 10),
                  ],
                  Text(
                    title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: GlameColors.whiteGlame,
                      fontSize: 18,
                      height: 1.18,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  if (excerpt != null) ...[
                    const SizedBox(height: 10),
                    Text(
                      _stripHtml(excerpt),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: GlameColors.coldLightGray,
                        fontSize: 13,
                        height: 1.35,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 12),
            const Icon(
              Icons.chevron_right,
              color: GlameColors.coldLightGray,
              size: 26,
            ),
          ],
        ),
      ),
    );
  }
}

class _NewsPreviewImage extends StatelessWidget {
  final String url;

  const _NewsPreviewImage({required this.url});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 74,
      height: 92,
      child: Image.network(
        url,
        fit: BoxFit.cover,
        errorBuilder: (_, _, _) => Container(color: GlameColors.graphite),
        loadingBuilder: (context, child, progress) {
          if (progress == null) return child;
          return Container(color: GlameColors.graphite);
        },
      ),
    );
  }
}

class _NewsDetailScreen extends StatelessWidget {
  final Map<String, dynamic> item;
  final String number;

  const _NewsDetailScreen({required this.item, required this.number});

  @override
  Widget build(BuildContext context) {
    final title = _newsString(item['title']) ?? 'Новость GLAME';
    final body =
        _newsString(item['body']) ??
        _newsString(item['description']) ??
        _newsString(item['excerpt']) ??
        '';
    final date = _newsDateLabel(item['published_at'] ?? item['updated_at']);
    final imageUrl = resolveAssetUrl(
      item['cover_image_url'] ?? item['preview_image_url'],
    );

    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      body: SafeArea(
        child: Column(
          children: [
            _NewsTopBar(onBack: () => Navigator.of(context).maybePop()),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(
                  GlameUi.pagePadding,
                  34,
                  GlameUi.pagePadding,
                  40,
                ),
                children: [
                  Text(
                    number,
                    style: const TextStyle(
                      color: GlameColors.steelGray,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 1.2,
                    ),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    title,
                    style: const TextStyle(
                      color: GlameColors.whiteGlame,
                      fontSize: 30,
                      height: 1.05,
                      fontWeight: FontWeight.w500,
                      letterSpacing: 0,
                    ),
                  ),
                  if (date != null) ...[
                    const SizedBox(height: 18),
                    Text(
                      date,
                      style: const TextStyle(
                        color: GlameColors.steelGray,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1.2,
                      ),
                    ),
                  ],
                  if (imageUrl != null) ...[
                    const SizedBox(height: 28),
                    AspectRatio(
                      aspectRatio: 1,
                      child: Image.network(
                        imageUrl,
                        fit: BoxFit.cover,
                        errorBuilder: (_, _, _) =>
                            Container(color: GlameColors.graphite),
                      ),
                    ),
                  ],
                  const SizedBox(height: 30),
                  Text(
                    _stripHtml(body),
                    style: const TextStyle(
                      color: GlameColors.coldLightGray,
                      fontSize: 16,
                      height: 1.55,
                      letterSpacing: 0,
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

class _NewsStateMessage extends StatelessWidget {
  final String text;
  final String? actionLabel;
  final VoidCallback? onAction;

  const _NewsStateMessage({
    required this.text,
    this.actionLabel,
    this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(GlameUi.pagePadding),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              text,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: GlameColors.coldLightGray,
                fontSize: 15,
                height: 1.4,
              ),
            ),
            if (actionLabel != null && onAction != null) ...[
              const SizedBox(height: 18),
              OutlinedButton(onPressed: onAction, child: Text(actionLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}

String? _newsString(Object? value) {
  if (value == null) return null;
  final text = value.toString().trim();
  return text.isEmpty ? null : text;
}

String? _newsDateLabel(Object? value) {
  final raw = _newsString(value);
  if (raw == null) return null;
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) return raw;
  final local = parsed.toLocal();
  final day = local.day.toString().padLeft(2, '0');
  final month = local.month.toString().padLeft(2, '0');
  final year = local.year.toString();
  return '$day.$month.$year';
}

String _stripHtml(String html) {
  return html
      .replaceAll(RegExp(r'<br\s*/?>', caseSensitive: false), '\n')
      .replaceAll(RegExp(r'</p>', caseSensitive: false), '\n\n')
      .replaceAll(RegExp(r'<[^>]*>'), ' ')
      .replaceAll('&nbsp;', ' ')
      .replaceAll('&amp;', '&')
      .replaceAll('&quot;', '"')
      .replaceAll('&#39;', "'")
      .replaceAll(RegExp(r'[ \t]+'), ' ')
      .replaceAll(RegExp(r'\n\s+'), '\n')
      .trim();
}
