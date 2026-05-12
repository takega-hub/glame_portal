import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/network/asset_url.dart';
import '../../core/formatters/rub.dart';
import '../../core/theme/glame_theme.dart';
import 'cart_controller.dart';

class CartScreen extends ConsumerWidget {
  const CartScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cart = ref.watch(cartControllerProvider);
    final controller = ref.read(cartControllerProvider.notifier);

    if (cart.loading) {
      return const Scaffold(
        body: SafeArea(
          child: Center(
            child: CircularProgressIndicator(color: GlameColors.gold),
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const GlameHeaderLogo()),
      body: RefreshIndicator(
        color: GlameColors.gold,
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
                color: GlameColors.textPrimary,
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
                color: GlameColors.textSecondary,
              ),
            ),
            const SizedBox(height: 18),
            Container(width: 44, height: 1, color: GlameColors.lightGray),
            const SizedBox(height: 24),
            if (cart.error != null)
              Container(
                margin: const EdgeInsets.only(bottom: 16),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  border: Border.all(color: GlameColors.graphite),
                ),
                child: Text(
                  cart.error!,
                  style: const TextStyle(color: GlameColors.graphite),
                ),
              ),
            if (cart.items.isEmpty)
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 20,
                  vertical: 28,
                ),
                decoration: BoxDecoration(
                  color: GlameColors.surface2,
                  border: Border.all(color: GlameColors.lightGray),
                ),
                child: const Column(
                  children: [
                    Text(
                      'Корзина пуста',
                      style: TextStyle(
                        fontSize: 22,
                        height: 1,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                    SizedBox(height: 10),
                    Text(
                      'Добавьте товары из каталога или раздела образов',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: GlameColors.textSecondary),
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
          color: GlameColors.surface2,
          border: Border.all(color: GlameColors.lightGray),
        ),
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 78,
              height: 96,
              decoration: BoxDecoration(
                color: GlameColors.surface,
                border: Border.all(color: GlameColors.lightGray),
              ),
              child: imageUrl != null
                  ? CachedNetworkImage(
                      imageUrl: imageUrl,
                      fit: BoxFit.cover,
                      placeholder: (context, url) =>
                          Container(color: GlameColors.surface),
                      errorWidget: (context, url, error) =>
                          Container(color: GlameColors.surface),
                    )
                  : Container(color: GlameColors.surface),
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
                    style: Theme.of(
                      context,
                    ).textTheme.titleMedium?.copyWith(height: 1.1),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    formatRubFromKopeks(unit),
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: GlameColors.textSecondary,
                    ),
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      Container(
                        decoration: BoxDecoration(
                          color: GlameColors.textPrimary,
                          border: Border.all(
                            color: Theme.of(context).colorScheme.outline,
                          ),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            IconButton(
                              onPressed: () =>
                                  controller.updateQuantity(id, qty - 1),
                              icon: const Icon(Icons.remove, size: 18),
                              color: Theme.of(context).colorScheme.onSurface,
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
                                    color: GlameColors.lightGray,
                                  ),
                                  right: BorderSide(
                                    color: GlameColors.lightGray,
                                  ),
                                ),
                              ),
                              child: Text(
                                '$qty',
                                style: Theme.of(context).textTheme.bodyMedium
                                    ?.copyWith(fontWeight: FontWeight.w600),
                              ),
                            ),
                            IconButton(
                              onPressed: () =>
                                  controller.updateQuantity(id, qty + 1),
                              icon: const Icon(Icons.add, size: 18),
                              color: Theme.of(context).colorScheme.onSurface,
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
                          foregroundColor: GlameColors.graphite,
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
        color: GlameColors.surface2,
        border: Border.all(color: GlameColors.lightGray),
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
            ).textTheme.titleMedium?.copyWith(color: GlameColors.gold),
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
          child: Text(label, style: Theme.of(context).textTheme.bodyMedium),
        ),
        const SizedBox(width: 12),
        Text(
          value,
          style: valueStyle ?? Theme.of(context).textTheme.bodyMedium,
        ),
      ],
    );
  }
}
