import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import 'cart_api.dart';

class CartState {
  final bool loading;
  final String? error;
  final List<Map<String, dynamic>> items;
  final int subtotal;

  const CartState({
    required this.loading,
    required this.error,
    required this.items,
    required this.subtotal,
  });

  factory CartState.initial() =>
      const CartState(loading: true, error: null, items: [], subtotal: 0);

  CartState copyWith({
    bool? loading,
    String? error,
    List<Map<String, dynamic>>? items,
    int? subtotal,
  }) {
    return CartState(
      loading: loading ?? this.loading,
      error: error,
      items: items ?? this.items,
      subtotal: subtotal ?? this.subtotal,
    );
  }
}

final cartControllerProvider = StateNotifierProvider<CartController, CartState>(
  (ref) {
    return CartController(api: CartApi(ref.watch(apiClientProvider)));
  },
);

class CartController extends StateNotifier<CartState> {
  final CartApi api;

  CartController({required this.api}) : super(CartState.initial()) {
    refresh();
  }

  Future<void> refresh() async {
    state = state.copyWith(loading: true, error: null);
    try {
      final raw = await api.getCart();
      final itemsRaw = raw['items'];
      final totals = raw['totals'];
      final items = (itemsRaw is List)
          ? itemsRaw
                .whereType<Map>()
                .map((x) => Map<String, dynamic>.from(x))
                .toList()
          : <Map<String, dynamic>>[];
      final subtotal = (totals is Map) ? (totals['subtotal'] as int?) ?? 0 : 0;
      state = state.copyWith(loading: false, items: items, subtotal: subtotal);
    } catch (_) {
      state = state.copyWith(
        loading: false,
        error: 'Не удалось загрузить корзину',
      );
    }
  }

  Future<void> addOne(String productId) async {
    try {
      await api.addItem(productId: productId, quantity: 1);
      await refresh();
    } catch (_) {
      state = state.copyWith(error: 'Не удалось добавить товар');
    }
  }

  Future<void> addMany(List<String> productIds) async {
    if (productIds.isEmpty) return;
    try {
      for (final productId in productIds) {
        await api.addItem(productId: productId, quantity: 1);
      }
      await refresh();
    } catch (_) {
      state = state.copyWith(error: 'Не удалось добавить комплект');
    }
  }

  Future<void> updateQuantity(String itemId, int quantity) async {
    if (quantity <= 0) {
      return removeItem(itemId);
    }
    try {
      await api.updateItemQuantity(itemId: itemId, quantity: quantity);
      await refresh();
    } catch (_) {
      state = state.copyWith(error: 'Не удалось обновить количество');
    }
  }

  Future<void> removeItem(String itemId) async {
    try {
      await api.deleteItem(itemId: itemId);
      await refresh();
    } catch (_) {
      state = state.copyWith(error: 'Не удалось удалить позицию');
    }
  }
}
