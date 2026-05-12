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
