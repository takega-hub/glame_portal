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
import '../looks/user_created_looks_controller.dart';
import '../product/product_providers.dart';
import 'wishlist_controller.dart';

class WishlistScreen extends ConsumerWidget {
  const WishlistScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ids = ref.watch(wishlistControllerProvider).toList()..sort();
    final auth = ref.watch(authControllerProvider);
    final favoriteLooksAsync = ref.watch(customerFavoriteLooksProvider);
    final userCreatedLooks = ref.watch(userCreatedLooksProvider);
    final isLoggedIn = auth.user != null;

    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      body: SafeArea(
        child: favoriteLooksAsync.when(
          loading: () => const Center(
            child: CircularProgressIndicator(color: GlameColors.whiteGlame),
          ),
          error: (_, _) => _WishlistContent(
            productIds: ids,
            favoriteLooks: userCreatedLooks,
            isLoggedIn: isLoggedIn,
            userName: auth.user?.fullName,
            showLooksError: isLoggedIn,
          ),
          data: (favoriteLooks) {
            final visibleLooks = [...userCreatedLooks, ...favoriteLooks];
            return _WishlistContent(
              productIds: ids,
              favoriteLooks: visibleLooks,
              isLoggedIn: isLoggedIn,
              userName: auth.user?.fullName,
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
  final String? userName;
  final bool showLooksLoginHint;
  final bool showLooksError;

  const _WishlistContent({
    required this.productIds,
    required this.favoriteLooks,
    required this.isLoggedIn,
    required this.userName,
    this.showLooksLoginHint = false,
    this.showLooksError = false,
  });

  @override
  Widget build(BuildContext context) {
    final displayName = (userName ?? '').trim();
    final greeting = displayName.isEmpty
        ? 'Добро пожаловать в ваше личное пространство.'
        : '${displayName.split(RegExp(r'\\s+')).first}, добро пожаловать в ваше личное пространство.';
    final visibleProductIds = productIds.take(4).toList(growable: false);
    final visibleLooks = favoriteLooks.take(8).toList(growable: false);

    return ListView(
      padding: const EdgeInsets.fromLTRB(18, 24, 18, 28),
      children: [
        const Text(
          'Мой стиль',
          style: TextStyle(
            fontSize: 34,
            height: 1,
            fontWeight: FontWeight.w500,
            color: GlameColors.whiteGlame,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          greeting,
          style: const TextStyle(
            fontSize: 13,
            height: 1.35,
            color: GlameColors.coldLightGray,
          ),
        ),
        const SizedBox(height: 22),
        FilledButton(
          onPressed: () {
            final targetRoute = buildStylistChatRoute(
              initialMessage:
                  'Хочу обсудить избранные украшения и собрать образ со стилистом GLAME.',
              source: 'my_style',
              scenario: 'live_stylist',
              favoriteProductIds: productIds,
            );
            if (!isLoggedIn) {
              context.push('/login?next=${Uri.encodeComponent(targetRoute)}');
              return;
            }
            showStylistContactSheet(
              context,
              initialMessage:
                  'Хочу обсудить избранные украшения и собрать образ со стилистом GLAME.',
              source: 'my_style',
              scenario: 'live_stylist',
              favoriteProductIds: productIds,
            );
          },
          style: FilledButton.styleFrom(
            minimumSize: const Size.fromHeight(32),
            backgroundColor: GlameColors.whiteGlame,
            foregroundColor: GlameColors.nearBlack,
            shape: const RoundedRectangleBorder(),
            padding: EdgeInsets.zero,
          ),
          child: const Text(
            'ОБСУДИТЬ СО СТИЛИСТОМ',
            style: TextStyle(fontSize: 10, letterSpacing: 0.8),
          ),
        ),
        const SizedBox(height: 8),
        OutlinedButton(
          onPressed: () => context.push('/look-builder'),
          style: OutlinedButton.styleFrom(
            minimumSize: const Size.fromHeight(32),
            foregroundColor: GlameColors.whiteGlame,
            side: const BorderSide(color: GlameColors.whiteGlame),
            shape: const RoundedRectangleBorder(),
            padding: EdgeInsets.zero,
          ),
          child: const Text(
            'СОЗДАТЬ СВОЙ ОБРАЗ',
            style: TextStyle(fontSize: 10, letterSpacing: 0.8),
          ),
        ),
        const SizedBox(height: 34),
        _MyStyleSectionHeader(
          title: 'Избранные товары',
          actionLabel: productIds.length > visibleProductIds.length
              ? 'ПОКАЗАТЬ ВСЕ'
              : null,
          onActionTap: productIds.length > visibleProductIds.length
              ? () => context.go('/home?tab=1')
              : null,
        ),
        const SizedBox(height: 14),
        if (visibleProductIds.isEmpty)
          const _MyStyleHint(
            'Сохраняйте украшения из каталога, чтобы собрать личную витрину.',
          )
        else
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: visibleProductIds.length,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              mainAxisSpacing: 1,
              crossAxisSpacing: 1,
              childAspectRatio: 0.58,
            ),
            itemBuilder: (context, index) =>
                _MyStyleProductCard(id: visibleProductIds[index]),
          ),
        const SizedBox(height: 34),
        _MyStyleSectionHeader(
          title: 'Сохраненные образы',
          actionLabel: favoriteLooks.length > visibleLooks.length
              ? '${visibleLooks.length}/${favoriteLooks.length}'
              : null,
        ),
        const SizedBox(height: 14),
        if (showLooksError && visibleLooks.isEmpty)
          const _MyStyleHint('Не удалось загрузить сохраненные образы.')
        else if (showLooksLoginHint && visibleLooks.isEmpty)
          const _MyStyleHint('Войдите, чтобы видеть сохраненные образы.')
        else if (visibleLooks.isEmpty)
          const _MyStyleHint(
            'Сохраняйте образы GLAME, чтобы вернуться к ним позже.',
          )
        else
          SizedBox(
            height: 250,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: visibleLooks.length,
              separatorBuilder: (_, _) => const SizedBox(width: 10),
              itemBuilder: (context, index) =>
                  _MyStyleLookCard(row: visibleLooks[index]),
            ),
          ),
        const SizedBox(height: 34),
        const _MyStyleSectionHeader(title: 'Рекомендации'),
        const SizedBox(height: 14),
        InkWell(
          onTap: () => context.go('/home?tab=3'),
          child: Container(
            height: 74,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            decoration: BoxDecoration(
              color: const Color(0xFF1A1C1E),
              border: Border.all(color: GlameColors.borderGray),
            ),
            child: const Row(
              children: [
                Icon(
                  Icons.auto_awesome_outlined,
                  color: GlameColors.whiteGlame,
                  size: 22,
                ),
                SizedBox(width: 14),
                Expanded(
                  child: Text(
                    'Подобрать украшения под ваш стиль',
                    style: TextStyle(
                      fontSize: 15,
                      height: 1.2,
                      color: GlameColors.whiteGlame,
                    ),
                  ),
                ),
                Icon(Icons.arrow_forward, color: GlameColors.whiteGlame),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _MyStyleSectionHeader extends StatelessWidget {
  final String title;
  final String? actionLabel;
  final VoidCallback? onActionTap;

  const _MyStyleSectionHeader({
    required this.title,
    this.actionLabel,
    this.onActionTap,
  });

  @override
  Widget build(BuildContext context) {
    final displayTitle = title.contains('РЎРѕС') && title.contains('РѕР±СЂ')
        ? 'Собранные образы'
        : title;
    return Container(
      padding: const EdgeInsets.only(top: 18),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: GlameColors.borderGray)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              displayTitle,
              style: const TextStyle(
                fontSize: 17,
                height: 1.1,
                color: GlameColors.whiteGlame,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          if (actionLabel != null)
            InkWell(
              onTap: onActionTap,
              child: Text(
                actionLabel!,
                style: const TextStyle(
                  fontSize: 9,
                  letterSpacing: 0.9,
                  color: GlameColors.whiteGlame,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _MyStyleHint extends StatelessWidget {
  final String text;

  const _MyStyleHint(this.text);

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1C1E),
        border: Border.all(color: GlameColors.borderGray),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 13,
          height: 1.35,
          color: GlameColors.coldLightGray,
        ),
      ),
    );
  }
}

class _MyStyleProductCard extends ConsumerWidget {
  final String id;

  const _MyStyleProductCard({required this.id});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(productProvider(id));
    return InkWell(
      onTap: () => context.push('/product/$id'),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: const Color(0xFF1A1C1E),
          border: Border.all(color: GlameColors.borderGray),
        ),
        child: async.when(
          loading: () => const Center(
            child: CircularProgressIndicator(
              color: GlameColors.whiteGlame,
              strokeWidth: 2,
            ),
          ),
          error: (_, _) => const Center(
            child: Icon(Icons.refresh, color: GlameColors.whiteGlame),
          ),
          data: (item) {
            final name = (item['name'] as String?)?.trim() ?? '';
            final price = formatRubFromKopeks(item['price']);
            final images = item['images'];
            final imageUrl = images is List && images.isNotEmpty
                ? resolveAssetUrl(images.first)
                : null;
            final brand = ((item['brand'] as String?) ?? '').trim();
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      if (imageUrl == null)
                        const ColoredBox(color: GlameColors.nearBlack)
                      else
                        CachedNetworkImage(
                          imageUrl: imageUrl,
                          fit: BoxFit.cover,
                          errorWidget: (_, _, _) =>
                              const ColoredBox(color: GlameColors.nearBlack),
                        ),
                      Positioned(
                        top: 8,
                        right: 8,
                        child: InkWell(
                          onTap: () => ref
                              .read(wishlistControllerProvider.notifier)
                              .toggle(id),
                          child: Container(
                            width: 26,
                            height: 26,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: GlameColors.nearBlack.withValues(
                                alpha: 0.72,
                              ),
                              border: Border.all(color: GlameColors.borderGray),
                            ),
                            child: const Icon(
                              Icons.favorite,
                              size: 15,
                              color: GlameColors.whiteGlame,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.fromLTRB(10, 9, 10, 10),
                  decoration: const BoxDecoration(
                    border: Border(
                      top: BorderSide(color: GlameColors.borderGray),
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name.isEmpty ? 'Украшение GLAME' : name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 11,
                          height: 1.15,
                          color: GlameColors.whiteGlame,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        price,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 11,
                          color: GlameColors.whiteGlame,
                        ),
                      ),
                      if (brand.isNotEmpty) ...[
                        const SizedBox(height: 4),
                        Text(
                          brand,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 9,
                            color: GlameColors.coldLightGray,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _MyStyleLookCard extends StatelessWidget {
  final Map<String, dynamic> row;

  const _MyStyleLookCard({required this.row});

  @override
  Widget build(BuildContext context) {
    final name = (row['look_name'] as String?)?.trim();
    final imageUrl = resolveAssetUrl(row['look_image_url']);
    final lookId = (row['look_id'] as String?)?.trim() ?? '';
    final localLookId = (row['id'] as String?)?.trim() ?? '';
    final isUserCreated = row['is_user_created'] == true;
    final label = (name?.isNotEmpty == true ? name! : 'Look').toUpperCase();
    final route = isUserCreated && localLookId.isNotEmpty
        ? '/my-look/$localLookId'
        : lookId.isNotEmpty
        ? '/look/$lookId'
        : null;

    return SizedBox(
      width: 170,
      child: InkWell(
        onTap: route == null ? null : () => context.push(route),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: const Color(0xFF1A1C1E),
            border: Border.all(color: GlameColors.borderGray),
          ),
          child: Stack(
            fit: StackFit.expand,
            children: [
              if (imageUrl == null)
                const ColoredBox(color: GlameColors.nearBlack)
              else
                CachedNetworkImage(
                  imageUrl: imageUrl,
                  fit: BoxFit.cover,
                  color: Colors.black.withValues(alpha: 0.24),
                  colorBlendMode: BlendMode.darken,
                  errorWidget: (_, _, _) =>
                      const ColoredBox(color: GlameColors.nearBlack),
                ),
              Positioned(
                left: 10,
                right: 10,
                bottom: 10,
                child: Row(
                  children: [
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 7,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: GlameColors.nearBlack.withValues(alpha: 0.72),
                          border: Border.all(color: GlameColors.borderGray),
                        ),
                        child: Text(
                          label,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 9,
                            letterSpacing: 0.4,
                            color: GlameColors.whiteGlame,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                    if (route != null) ...[
                      const SizedBox(width: 8),
                      const Icon(
                        Icons.arrow_outward,
                        size: 16,
                        color: GlameColors.whiteGlame,
                      ),
                    ],
                  ],
                ),
              ),
              if (isUserCreated)
                Positioned(
                  left: 10,
                  top: 10,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: GlameColors.nearBlack.withValues(alpha: 0.72),
                      border: Border.all(color: GlameColors.borderGray),
                    ),
                    child: const Text(
                      'СОЗДАНО ВАМИ',
                      style: TextStyle(
                        fontSize: 8,
                        letterSpacing: 0.6,
                        fontWeight: FontWeight.w700,
                        color: GlameColors.whiteGlame,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class WishlistContentLegacy extends StatelessWidget {
  final List<String> productIds;
  final List<Map<String, dynamic>> favoriteLooks;
  final bool isLoggedIn;
  final String? userName;
  final bool showLooksLoginHint;
  final bool showLooksError;

  const WishlistContentLegacy({
    super.key,
    required this.productIds,
    required this.favoriteLooks,
    required this.isLoggedIn,
    required this.userName,
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
      padding: const EdgeInsets.fromLTRB(20, 28, 20, 28),
      children: [
        const Text(
          'ИЗБРАННОЕ',
          style: TextStyle(
            fontSize: 40,
            height: 0.95,
            fontWeight: FontWeight.w400,
            color: GlameColors.whiteGlame,
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
            color: GlameColors.coldLightGray,
          ),
        ),
        const SizedBox(height: 18),
        Container(width: 54, height: 1, color: GlameColors.steelGray),
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
                foregroundColor: GlameColors.whiteGlame,
                side: const BorderSide(color: GlameColors.borderGray),
                shape: const RoundedRectangleBorder(),
              ),
              child: Text(
                isLoggedIn
                    ? 'Обсудить избранное со стилистом'
                    : 'Войти и обсудить избранное',
                style: const TextStyle(
                  fontSize: 16,
                  color: GlameColors.whiteGlame,
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
        color: GlameColors.graphite,
        border: Border.all(color: GlameColors.borderGray),
      ),
      child: const Column(
        children: [
          Text(
            'Пока пусто',
            style: TextStyle(
              fontSize: 22,
              height: 1,
              fontWeight: FontWeight.w400,
              color: GlameColors.whiteGlame,
            ),
          ),
          SizedBox(height: 10),
          Text(
            'Добавляйте украшения и образы в избранное из каталога, карточек товара и стилист-подборок',
            textAlign: TextAlign.center,
            style: TextStyle(color: GlameColors.coldLightGray, height: 1.4),
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
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
            fontSize: 28,
            height: 1,
            color: GlameColors.whiteGlame,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'Сохранено: $count',
          style: const TextStyle(color: GlameColors.coldLightGray),
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
        color: GlameColors.graphite,
        border: Border.all(color: GlameColors.borderGray),
      ),
      child: Text(
        text,
        style: const TextStyle(color: GlameColors.coldLightGray),
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
          color: GlameColors.graphite,
          border: Border.all(color: GlameColors.borderGray),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 84,
              height: 112,
              decoration: BoxDecoration(
                color: GlameColors.nearBlack,
                border: Border.all(color: GlameColors.borderGray),
              ),
              child: imageUrl == null
                  ? const ColoredBox(color: GlameColors.nearBlack)
                  : CachedNetworkImage(
                      imageUrl: imageUrl,
                      fit: BoxFit.cover,
                      errorWidget: (_, _, _) =>
                          const ColoredBox(color: GlameColors.nearBlack),
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
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: GlameColors.whiteGlame,
                    ),
                  ),
                  if (subtitleParts.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      subtitleParts.join(' · '),
                      style: const TextStyle(
                        color: GlameColors.coldLightGray,
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
                        color: GlameColors.coldLightGray,
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
                          style: TextButton.styleFrom(
                            foregroundColor: GlameColors.whiteGlame,
                            padding: EdgeInsets.zero,
                          ),
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
                          Icons.favorite_border,
                          color: GlameColors.whiteGlame,
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
          color: GlameColors.graphite,
          border: Border.all(color: GlameColors.borderGray),
        ),
        child: const Icon(Icons.delete_outline, color: GlameColors.whiteGlame),
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
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: GlameColors.graphite,
          border: Border.all(color: GlameColors.borderGray),
        ),
        child: async.when(
          loading: () => const SizedBox(
            height: 52,
            child: Align(
              alignment: Alignment.centerLeft,
              child: CircularProgressIndicator(color: GlameColors.whiteGlame),
            ),
          ),
          error: (error, stackTrace) => Row(
            children: [
              const Expanded(
                child: Text(
                  'Не удалось загрузить товар',
                  style: TextStyle(color: GlameColors.coldLightGray),
                ),
              ),
              IconButton(
                onPressed: () => ref.invalidate(productProvider(id)),
                icon: const Icon(Icons.refresh, color: GlameColors.whiteGlame),
              ),
            ],
          ),
          data: (item) {
            final name = (item['name'] as String?) ?? '';
            final price = item['price'];
            final images = item['images'];
            final imageUrl = images is List && images.isNotEmpty
                ? resolveAssetUrl(images.first)
                : null;
            final brand = ((item['brand'] as String?) ?? '').trim();
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 82,
                  height: 110,
                  decoration: BoxDecoration(
                    color: GlameColors.nearBlack,
                    border: Border.all(color: GlameColors.borderGray),
                  ),
                  child: imageUrl == null
                      ? const ColoredBox(color: GlameColors.nearBlack)
                      : CachedNetworkImage(
                          imageUrl: imageUrl,
                          fit: BoxFit.cover,
                          errorWidget: (_, _, _) =>
                              const ColoredBox(color: GlameColors.nearBlack),
                        ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (brand.isNotEmpty) ...[
                        Text(
                          brand.toUpperCase(),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 10,
                            letterSpacing: 0.8,
                            color: GlameColors.steelGray,
                          ),
                        ),
                        const SizedBox(height: 6),
                      ],
                      Text(
                        name,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(color: GlameColors.whiteGlame),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        formatRubFromKopeks(price),
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(color: GlameColors.coldLightGray),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: () =>
                      ref.read(wishlistControllerProvider.notifier).toggle(id),
                  icon: const Icon(
                    Icons.favorite_border,
                    color: GlameColors.whiteGlame,
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
