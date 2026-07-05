import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:cached_network_image/cached_network_image.dart';

import '../../core/formatters/rub.dart';
import '../../core/network/asset_url.dart';
import '../../core/theme/glame_theme.dart';
import '../auth/auth_controller.dart';
import '../customer/customer_cabinet_providers.dart';
import '../customer/stylist_entry.dart';
import '../product/product_providers.dart';
import 'wishlist_controller.dart';

class WishlistScreen extends ConsumerWidget {
  const WishlistScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ids = ref.watch(wishlistControllerProvider).toList()..sort();
    final auth = ref.watch(authControllerProvider);
    final favoriteLooksAsync = ref.watch(customerFavoriteLooksProvider);
    final isLoggedIn = auth.user != null;

    return Scaffold(
      body: SafeArea(
        child: favoriteLooksAsync.when(
          loading: () => const Center(
            child: CircularProgressIndicator(color: GlameColors.gold),
          ),
          error: (_, _) => _WishlistContent(
            productIds: ids,
            favoriteLooks: const [],
            isLoggedIn: isLoggedIn,
            showLooksError: isLoggedIn,
          ),
          data: (favoriteLooks) {
            return _WishlistContent(
              productIds: ids,
              favoriteLooks: favoriteLooks,
              isLoggedIn: isLoggedIn,
              showLooksLoginHint: !isLoggedIn,
            );
          },
        ),
      ),
    );
  }
}

class _WishlistContent extends StatelessWidget {
  final List<String> productIds;
  final List<Map<String, dynamic>> favoriteLooks;
  final bool isLoggedIn;
  final bool showLooksLoginHint;
  final bool showLooksError;

  const _WishlistContent({
    required this.productIds,
    required this.favoriteLooks,
    required this.isLoggedIn,
    this.showLooksLoginHint = false,
    this.showLooksError = false,
  });

  @override
  Widget build(BuildContext context) {
    final looksCount = favoriteLooks.length;
    final productsCount = productIds.length;
    final totalCount = looksCount + productsCount;
    final isEmpty = totalCount == 0 && !showLooksLoginHint && !showLooksError;

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
      children: [
        const Text(
          'ИЗБРАННОЕ',
          style: TextStyle(
            fontSize: 40,
            height: 0.95,
            fontWeight: FontWeight.w400,
            color: GlameColors.textPrimary,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          isEmpty
              ? 'Сохраняйте образы и товары, чтобы быстро вернуться к ним позже'
              : 'Сохранено позиций: $totalCount',
          style: const TextStyle(
            fontSize: 15,
            height: 1.35,
            color: GlameColors.textSecondary,
          ),
        ),
        const SizedBox(height: 18),
        Container(width: 44, height: 1, color: GlameColors.lightGray),
        const SizedBox(height: 24),
        if (productIds.isNotEmpty) ...[
          SizedBox(
            height: 52,
            child: OutlinedButton(
              onPressed: () {
                final targetRoute = buildStylistChatRoute(
                  initialMessage:
                      'Хочу обсудить избранные украшения и подобрать лучшее решение.',
                  source: 'favorites',
                  scenario: 'live_stylist',
                  favoriteProductIds: productIds,
                );
                if (!isLoggedIn) {
                  context.push(
                    '/login?next=${Uri.encodeComponent(targetRoute)}',
                  );
                  return;
                }
                showStylistContactSheet(
                  context,
                  initialMessage:
                      'Хочу обсудить избранные украшения и подобрать лучшее решение.',
                  source: 'favorites',
                  scenario: 'live_stylist',
                  favoriteProductIds: productIds,
                );
              },
              style: OutlinedButton.styleFrom(
                side: const BorderSide(color: GlameColors.lightGray),
              ),
              child: Text(
                isLoggedIn
                    ? 'Обсудить избранное со стилистом'
                    : 'Войти и обсудить избранное',
                style: const TextStyle(
                  fontSize: 16,
                  color: GlameColors.textPrimary,
                ),
              ),
            ),
          ),
          const SizedBox(height: 20),
        ],
        if (isEmpty)
          const _WishlistEmptyState()
        else ...[
          if (favoriteLooks.isNotEmpty ||
              showLooksLoginHint ||
              showLooksError) ...[
            _SectionHeader(title: 'Образы', count: favoriteLooks.length),
            const SizedBox(height: 12),
            if (showLooksError)
              const _SectionHint('Не удалось загрузить избранные образы')
            else if (showLooksLoginHint)
              const _SectionHint(
                'Авторизуйтесь, чтобы видеть сохраненные образы',
              )
            else
              ...favoriteLooks.map(
                (row) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _FavoriteLookTile(row: row),
                ),
              ),
            const SizedBox(height: 20),
          ],
          if (productIds.isNotEmpty) ...[
            _SectionHeader(title: 'Товары', count: productIds.length),
            const SizedBox(height: 12),
            ...productIds.map(
              (id) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: _ProductWishlistDismissible(id: id),
              ),
            ),
          ],
        ],
      ],
    );
  }
}

class _WishlistEmptyState extends StatelessWidget {
  const _WishlistEmptyState();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 28),
      decoration: BoxDecoration(
        color: GlameColors.surface2,
        border: Border.all(color: GlameColors.lightGray),
      ),
      child: const Column(
        children: [
          Text(
            'Пока пусто',
            style: TextStyle(
              fontSize: 22,
              height: 1,
              fontWeight: FontWeight.w400,
            ),
          ),
          SizedBox(height: 10),
          Text(
            'Добавляйте украшения и образы в избранное из каталога, карточек товара и стилист-подборок',
            textAlign: TextAlign.center,
            style: TextStyle(color: GlameColors.textSecondary, height: 1.4),
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  final int count;

  const _SectionHeader({required this.title, required this.count});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title.toUpperCase(),
          style: Theme.of(
            context,
          ).textTheme.titleLarge?.copyWith(fontSize: 28, height: 1),
        ),
        const SizedBox(height: 6),
        Text(
          'Сохранено: $count',
          style: const TextStyle(color: GlameColors.textSecondary),
        ),
      ],
    );
  }
}

class _SectionHint extends StatelessWidget {
  final String text;

  const _SectionHint(this.text);

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: GlameColors.surface2,
        border: Border.all(color: GlameColors.lightGray),
      ),
      child: Text(
        text,
        style: const TextStyle(color: GlameColors.textSecondary),
      ),
    );
  }
}

class _FavoriteLookTile extends ConsumerWidget {
  final Map<String, dynamic> row;

  const _FavoriteLookTile({required this.row});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final name = (row['look_name'] as String?)?.trim();
    final imageUrl = resolveAssetUrl(row['look_image_url']);
    final style = (row['look_style'] as String?)?.trim();
    final mood = (row['look_mood'] as String?)?.trim();
    final description = (row['look_description'] as String?)?.trim();
    final lookId = (row['look_id'] as String?)?.trim() ?? '';
    final savedLookId = (row['id'] as String?)?.trim() ?? '';
    final subtitleParts = <String>[
      if (style != null && style.isNotEmpty) style,
      if (mood != null && mood.isNotEmpty) mood,
    ];

    return InkWell(
      onTap: lookId.isEmpty ? null : () => context.push('/look/$lookId'),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: GlameColors.surface2,
          border: Border.all(color: GlameColors.lightGray),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 84,
              height: 112,
              decoration: BoxDecoration(
                color: GlameColors.surface,
                border: Border.all(color: GlameColors.lightGray),
              ),
              child: imageUrl == null
                  ? const ColoredBox(color: GlameColors.surface)
                  : CachedNetworkImage(
                      imageUrl: imageUrl,
                      fit: BoxFit.cover,
                      errorWidget: (_, _, _) =>
                          const ColoredBox(color: GlameColors.surface),
                    ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name?.isNotEmpty == true ? name! : 'Образ',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  if (subtitleParts.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      subtitleParts.join(' · '),
                      style: const TextStyle(
                        color: GlameColors.textSecondary,
                        fontSize: 12,
                      ),
                    ),
                  ],
                  if (description != null && description.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      description,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: GlameColors.textSecondary,
                        height: 1.25,
                      ),
                    ),
                  ],
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      if (lookId.isNotEmpty)
                        TextButton(
                          onPressed: () => context.push('/look/$lookId'),
                          style: TextButton.styleFrom(padding: EdgeInsets.zero),
                          child: const Text('Подробнее'),
                        ),
                      const Spacer(),
                      IconButton(
                        tooltip: 'Убрать из избранного',
                        onPressed: savedLookId.isEmpty
                            ? null
                            : () => _removeSavedLook(
                                context: context,
                                ref: ref,
                                savedLookId: savedLookId,
                              ),
                        icon: const Icon(
                          Icons.favorite,
                          color: GlameColors.gold,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _removeSavedLook({
    required BuildContext context,
    required WidgetRef ref,
    required String savedLookId,
  }) async {
    try {
      await ref.read(customerCabinetApiProvider).deleteSavedLook(savedLookId);
      ref.invalidate(customerSavedLooksProvider);
      ref.invalidate(customerFavoriteLooksProvider);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Образ удален из избранного')),
      );
    } catch (_) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Не удалось удалить образ из избранного')),
      );
    }
  }
}

class _ProductWishlistDismissible extends ConsumerWidget {
  final String id;

  const _ProductWishlistDismissible({required this.id});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Dismissible(
      key: ValueKey('wish_tile_$id'),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        decoration: BoxDecoration(
          color: GlameColors.warmGray,
          border: Border.all(color: GlameColors.graphite),
        ),
        child: const Icon(Icons.delete_outline, color: GlameColors.graphite),
      ),
      onDismissed: (_) =>
          ref.read(wishlistControllerProvider.notifier).remove(id),
      child: _WishlistTile(id: id),
    );
  }
}

class _WishlistTile extends ConsumerWidget {
  final String id;

  const _WishlistTile({required this.id});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(productProvider(id));
    return InkWell(
      onTap: () => context.push('/product/$id'),
      child: Container(
        color: GlameColors.surface2,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          border: Border.all(color: GlameColors.lightGray),
        ),
        child: async.when(
          loading: () => const SizedBox(
            height: 52,
            child: Align(
              alignment: Alignment.centerLeft,
              child: CircularProgressIndicator(color: GlameColors.gold),
            ),
          ),
          error: (error, stackTrace) => Row(
            children: [
              const Expanded(child: Text('Не удалось загрузить товар')),
              IconButton(
                onPressed: () => ref.invalidate(productProvider(id)),
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
          data: (item) {
            final name = (item['name'] as String?) ?? '';
            final price = item['price'];
            return Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        formatRubFromKopeks(price),
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(color: GlameColors.gold),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: () =>
                      ref.read(wishlistControllerProvider.notifier).toggle(id),
                  icon: const Icon(Icons.favorite, color: GlameColors.gold),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
