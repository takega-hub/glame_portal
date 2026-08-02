import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/glame_theme.dart';

String buildStylistChatRoute({
  String? productId,
  String? initialMessage,
  String? source,
  String? scenario,
  List<String> quickTags = const <String>[],
  List<String> favoriteProductIds = const <String>[],
}) {
  final query = <String, String>{};
  final cleanProductId = (productId ?? '').trim();
  final cleanMessage = (initialMessage ?? '').trim();
  final cleanSource = (source ?? '').trim();
  final cleanScenario = (scenario ?? '').trim();
  final normalizedTags = quickTags
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
  final normalizedFavoriteIds = favoriteProductIds
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);

  if (cleanProductId.isNotEmpty) query['product_id'] = cleanProductId;
  if (cleanMessage.isNotEmpty) query['message'] = cleanMessage;
  if (cleanSource.isNotEmpty) query['source'] = cleanSource;
  if (cleanScenario.isNotEmpty) query['scenario'] = cleanScenario;
  if (normalizedTags.isNotEmpty) query['quick_tags'] = normalizedTags.join(',');
  if (normalizedFavoriteIds.isNotEmpty) {
    query['favorite_ids'] = normalizedFavoriteIds.join(',');
  }

  return Uri(path: '/stylist-chat', queryParameters: query).toString();
}

String buildStylistMessageFromQuickTags(List<String> quickTags) {
  final labels = quickTags
      .map(stylistQuickTagLabel)
      .whereType<String>()
      .toList(growable: false);
  if (labels.isEmpty) {
    return 'Нужна помощь стилиста GLAME с подбором украшений.';
  }
  return 'Нужна помощь стилиста GLAME: ${labels.join(', ')}.';
}

String? stylistQuickTagLabel(String tag) {
  switch (tag.trim()) {
    case 'for_self':
      return 'для себя';
    case 'gift':
      return 'в подарок';
    case 'look':
      return 'под образ';
    case 'set':
      return 'нужен комплект';
    case 'try_in_space':
      return 'хочу примерить';
  }
  return null;
}

Future<void> showStylistContactSheet(
  BuildContext context, {
  String? productId,
  String? initialMessage,
  String? source,
  String? scenario = 'live_stylist',
  Map<String, dynamic>? statusPayload,
  List<String> quickTags = const <String>[],
  List<String> favoriteProductIds = const <String>[],
}) async {
  final rootContext = context;
  final messageController = TextEditingController(text: initialMessage ?? '');
  final selectedTags = quickTags.toSet();

  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    backgroundColor: GlameColors.surface2,
    shape: const RoundedRectangleBorder(),
    builder: (sheetContext) {
      final status =
          StylistWorkingHoursStatus.fromPayload(statusPayload) ??
          StylistWorkingHoursStatus.nowMoscow();
      return StatefulBuilder(
        builder: (modalContext, setState) {
          final width = MediaQuery.of(modalContext).size.width;
          final compact = width < 420;
          final horizontalPadding = compact ? 18.0 : 24.0;
          final verticalPadding = compact ? 18.0 : 24.0;
          void toggleTag(String tag) {
            setState(() {
              if (!selectedTags.add(tag)) selectedTags.remove(tag);
            });
          }

          void submit() {
            final tags = selectedTags.toList(growable: false);
            final text = messageController.text.trim().isEmpty
                ? buildStylistMessageFromQuickTags(tags)
                : messageController.text.trim();
            Navigator.of(sheetContext).pop();
            if (!rootContext.mounted) return;
            rootContext.push(
              buildStylistChatRoute(
                productId: productId,
                initialMessage: text,
                source: source,
                scenario: scenario,
                quickTags: tags,
                favoriteProductIds: favoriteProductIds,
              ),
            );
          }

          return Padding(
            padding: EdgeInsets.fromLTRB(
              horizontalPadding,
              verticalPadding,
              horizontalPadding,
              MediaQuery.of(modalContext).viewInsets.bottom + verticalPadding,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  status.isOpen ? 'Стилист GLAME' : 'Оставить заявку стилисту',
                  style: TextStyle(
                    fontSize: compact ? 24 : 28,
                    fontWeight: FontWeight.w400,
                    height: 1.05,
                    color: GlameColors.textPrimary,
                  ),
                ),
                SizedBox(height: compact ? 8 : 12),
                Text(
                  status.label,
                  style: TextStyle(
                    fontSize: compact ? 12 : 14,
                    color: GlameColors.textSecondary,
                  ),
                ),
                SizedBox(height: compact ? 12 : 18),
                Text(
                  status.isOpen
                      ? 'Опишите задачу — стилист поможет подобрать украшение онлайн или пригласит в пространство, если нужна примерка.'
                      : 'Стилист GLAME ответит с 10:00 до 20:00 по МСК. Опишите задачу — мы подберем украшения под образ, повод или подарок.',
                  style: TextStyle(
                    fontSize: compact ? 14 : 16,
                    height: 1.35,
                    color: GlameColors.textPrimary,
                  ),
                ),
                SizedBox(height: compact ? 14 : 20),
                TextField(
                  controller: messageController,
                  minLines: compact ? 2 : 3,
                  maxLines: compact ? 4 : 5,
                  style: TextStyle(fontSize: compact ? 13 : 16, height: 1.35),
                  decoration: InputDecoration(
                    labelText: 'Что хотите подобрать?',
                    labelStyle: TextStyle(fontSize: compact ? 12 : null),
                    hintText:
                        'Например: украшение на каждый день, подарок, комплект к образу, серьги под форму лица...',
                    hintStyle: TextStyle(fontSize: compact ? 12 : null),
                  ),
                ),
                SizedBox(height: compact ? 12 : 16),
                Wrap(
                  spacing: compact ? 6 : 8,
                  runSpacing: compact ? 6 : 8,
                  children: [
                    for (final tag in _stylistQuickTags)
                      _StylistQuickTagButton(
                        label: stylistQuickTagLabel(tag) ?? tag,
                        selected: selectedTags.contains(tag),
                        compact: compact,
                        onTap: () => toggleTag(tag),
                      ),
                  ],
                ),
                SizedBox(height: compact ? 16 : 22),
                SizedBox(
                  height: compact ? 48 : GlameUi.buttonHeight,
                  child: FilledButton(
                    onPressed: submit,
                    child: Text(
                      status.isOpen
                          ? 'Связаться со стилистом'
                          : 'Оставить заявку',
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      );
    },
  );

  messageController.dispose();
}

const List<String> _stylistQuickTags = <String>[
  'for_self',
  'gift',
  'look',
  'set',
  'try_in_space',
];

class StylistWorkingHoursStatus {
  final bool isOpen;
  final String label;

  const StylistWorkingHoursStatus({required this.isOpen, required this.label});

  factory StylistWorkingHoursStatus.nowMoscow() {
    final nowMoscow = DateTime.now().toUtc().add(const Duration(hours: 3));
    final minutes = nowMoscow.hour * 60 + nowMoscow.minute;
    const opens = 10 * 60;
    const closes = 20 * 60;
    final isOpen = minutes >= opens && minutes < closes;
    return StylistWorkingHoursStatus(
      isOpen: isOpen,
      label: isOpen
          ? 'На связи сейчас · до 20:00 по МСК'
          : 'Сейчас не на связи · с 10:00 по МСК',
    );
  }

  static StylistWorkingHoursStatus? fromPayload(Map<String, dynamic>? payload) {
    final rawStatus = '${payload?['status'] ?? ''}'.trim().toLowerCase();
    final rawText = '${payload?['status_text'] ?? ''}'.trim();
    final isOpen = rawStatus == 'open' || rawStatus == 'online';
    final isClosed = rawStatus == 'closed' || rawStatus == 'offline';
    if (!isOpen && !isClosed && rawText.isEmpty) {
      return null;
    }
    return StylistWorkingHoursStatus(
      isOpen: isOpen,
      label: rawText.isNotEmpty
          ? rawText
          : isOpen
          ? 'На связи сейчас · до 20:00 по МСК'
          : 'Сейчас не на связи · с 10:00 по МСК',
    );
  }
}

class _StylistQuickTagButton extends StatelessWidget {
  final String label;
  final bool selected;
  final bool compact;
  final VoidCallback onTap;

  const _StylistQuickTagButton({
    required this.label,
    required this.selected,
    this.compact = false,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? GlameColors.textPrimary : Colors.transparent,
      shape: const RoundedRectangleBorder(
        side: BorderSide(color: GlameColors.borderGray),
      ),
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: compact ? 10 : 12,
            vertical: compact ? 8 : 10,
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: compact ? 12 : 14,
              color: selected ? GlameColors.surface2 : GlameColors.textPrimary,
            ),
          ),
        ),
      ),
    );
  }
}
