import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/network/asset_url.dart';
import '../../core/formatters/rub.dart';
import '../../core/theme/glame_theme.dart';
import 'cart_controller.dart';

class CartScreen extends ConsumerWidget {
  final bool showAppBar;

  const CartScreen({super.key, this.showAppBar = true});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cart = ref.watch(cartControllerProvider);
    final controller = ref.read(cartControllerProvider.notifier);

    if (cart.loading) {
      return const Scaffold(
        backgroundColor: GlameColors.nearBlack,
        body: SafeArea(
          child: Center(
            child: CircularProgressIndicator(color: GlameColors.whiteGlame),
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      appBar: showAppBar ? const GlameTopAppBar(dark: true) : null,
      body: RefreshIndicator(
        color: GlameColors.whiteGlame,
        onRefresh: controller.refresh,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
          children: [
            const Text(
              'КОРЗИНА',
              style: TextStyle(
                fontSize: 40,
                height: 0.95,
                fontWeight: FontWeight.w400,
                color: GlameColors.whiteGlame,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              cart.items.isEmpty
                  ? 'Добавьте украшения, чтобы перейти к оформлению'
                  : 'Позиций в заказе: ${cart.items.length}',
              style: const TextStyle(
                fontSize: 15,
                height: 1.35,
                color: GlameColors.coldLightGray,
              ),
            ),
            const SizedBox(height: 18),
            Container(width: 54, height: 1, color: GlameColors.steelGray),
            const SizedBox(height: 24),
            if (cart.error != null)
              Container(
                margin: const EdgeInsets.only(bottom: 16),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: GlameColors.graphite,
                  border: Border.all(color: GlameColors.borderGray),
                ),
                child: Text(
                  cart.error!,
                  style: const TextStyle(color: GlameColors.coldLightGray),
                ),
              ),
            if (cart.items.isEmpty)
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 20,
                  vertical: 28,
                ),
                decoration: BoxDecoration(
                  color: GlameColors.graphite,
                  border: Border.all(color: GlameColors.borderGray),
                ),
                child: const Column(
                  children: [
                    Text(
                      'Корзина пуста',
                      style: TextStyle(
                        fontSize: 22,
                        height: 1,
                        fontWeight: FontWeight.w400,
                        color: GlameColors.whiteGlame,
                      ),
                    ),
                    SizedBox(height: 10),
                    Text(
                      'Добавьте товары из каталога или раздела образов',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: GlameColors.coldLightGray),
                    ),
                  ],
                ),
              )
            else
              ...cart.items.map((x) => _CartItemRow(item: x)),
            const SizedBox(height: 24),
            _Totals(subtotal: cart.subtotal),
            const SizedBox(height: 12),
            FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: GlameColors.whiteGlame,
                foregroundColor: GlameColors.nearBlack,
                shape: const RoundedRectangleBorder(),
              ),
              onPressed: cart.items.isEmpty
                  ? null
                  : () => context.push('/checkout'),
              child: const Text('Оформить заказ'),
            ),
          ],
        ),
      ),
    );
  }
}

class _CartItemRow extends ConsumerWidget {
  final Map<String, dynamic> item;

  const _CartItemRow({required this.item});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(cartControllerProvider.notifier);
    final id = (item['id'] as String?) ?? '';
    final qty = (item['quantity'] as int?) ?? 0;
    final unit = (item['unit_price'] as int?) ?? 0;
    final product = item['product'];
    final p = product is Map
        ? Map<String, dynamic>.from(product)
        : <String, dynamic>{};
    final name = (p['name'] as String?) ?? '';
    final images = p['images'];
    final imageUrl = (images is List && images.isNotEmpty)
        ? resolveAssetUrl(images.first)
        : null;

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Container(
        decoration: BoxDecoration(
          color: GlameColors.graphite,
          border: Border.all(color: GlameColors.borderGray),
        ),
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 78,
              height: 96,
              decoration: BoxDecoration(
                color: GlameColors.nearBlack,
                border: Border.all(color: GlameColors.borderGray),
              ),
              child: imageUrl != null
                  ? CachedNetworkImage(
                      imageUrl: imageUrl,
                      fit: BoxFit.cover,
                      placeholder: (context, url) =>
                          Container(color: GlameColors.nearBlack),
                      errorWidget: (context, url, error) =>
                          Container(color: GlameColors.nearBlack),
                    )
                  : Container(color: GlameColors.nearBlack),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      height: 1.1,
                      color: GlameColors.whiteGlame,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    formatRubFromKopeks(unit),
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: GlameColors.coldLightGray,
                    ),
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      Container(
                        decoration: BoxDecoration(
                          color: GlameColors.nearBlack,
                          border: Border.all(color: GlameColors.borderGray),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            IconButton(
                              onPressed: () =>
                                  controller.updateQuantity(id, qty - 1),
                              icon: const Icon(Icons.remove, size: 18),
                              color: GlameColors.whiteGlame,
                              constraints: const BoxConstraints(
                                minWidth: 36,
                                minHeight: 36,
                              ),
                              padding: EdgeInsets.zero,
                            ),
                            Container(
                              width: 40,
                              height: 36,
                              alignment: Alignment.center,
                              decoration: const BoxDecoration(
                                border: Border(
                                  left: BorderSide(
                                    color: GlameColors.borderGray,
                                  ),
                                  right: BorderSide(
                                    color: GlameColors.borderGray,
                                  ),
                                ),
                              ),
                              child: Text(
                                '$qty',
                                style: Theme.of(context).textTheme.bodyMedium
                                    ?.copyWith(
                                      fontWeight: FontWeight.w600,
                                      color: GlameColors.whiteGlame,
                                    ),
                              ),
                            ),
                            IconButton(
                              onPressed: () =>
                                  controller.updateQuantity(id, qty + 1),
                              icon: const Icon(Icons.add, size: 18),
                              color: GlameColors.whiteGlame,
                              constraints: const BoxConstraints(
                                minWidth: 36,
                                minHeight: 36,
                              ),
                              padding: EdgeInsets.zero,
                            ),
                          ],
                        ),
                      ),
                      const Spacer(),
                      TextButton(
                        onPressed: () => controller.removeItem(id),
                        style: TextButton.styleFrom(
                          foregroundColor: GlameColors.whiteGlame,
                          padding: EdgeInsets.zero,
                        ),
                        child: const Text('Удалить'),
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
}

class _Totals extends StatelessWidget {
  final int subtotal;

  const _Totals({required this.subtotal});

  @override
  Widget build(BuildContext context) {
    final freeFrom = 1000000;
    final delivery = subtotal >= freeFrom ? 0 : 0;
    final total = subtotal + delivery;
    return Container(
      decoration: BoxDecoration(
        color: GlameColors.graphite,
        border: Border.all(color: GlameColors.borderGray),
      ),
      padding: const EdgeInsets.all(14),
      child: Column(
        children: [
          _Row(
            label: 'Стоимость товаров',
            value: formatRubFromKopeks(subtotal),
          ),
          const SizedBox(height: 10),
          _Row(
            label: 'Доставка',
            value: delivery == 0
                ? 'Рассчитаем позже'
                : formatRubFromKopeks(delivery),
          ),
          const SizedBox(height: 10),
          const Divider(height: 1),
          const SizedBox(height: 10),
          _Row(
            label: 'Итого',
            value: formatRubFromKopeks(total),
            valueStyle: Theme.of(
              context,
            ).textTheme.titleMedium?.copyWith(color: GlameColors.whiteGlame),
          ),
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final String label;
  final String value;
  final TextStyle? valueStyle;

  const _Row({required this.label, required this.value, this.valueStyle});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.bodyMedium?.copyWith(color: GlameColors.coldLightGray),
          ),
        ),
        const SizedBox(width: 12),
        Text(
          value,
          style:
              valueStyle ??
              Theme.of(
                context,
              ).textTheme.bodyMedium?.copyWith(color: GlameColors.whiteGlame),
        ),
      ],
    );
  }
}
