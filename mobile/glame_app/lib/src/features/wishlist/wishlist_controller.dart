import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../auth/auth_controller.dart';
import '../customer/customer_cabinet_providers.dart';

final wishlistControllerProvider =
    StateNotifierProvider<WishlistController, Set<String>>((ref) {
      return WishlistController(ref);
    });

class WishlistController extends StateNotifier<Set<String>> {
  static const _key = 'glame_wishlist_ids';
  final Ref _ref;

  WishlistController(this._ref) : super(const {}) {
    _ref.listen<AuthState>(authControllerProvider, (previous, next) {
      if (previous?.user == null && next.user != null) {
        _loadServerState(state);
      }
    });
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final list = prefs.getStringList(_key) ?? const <String>[];
    final localIds = list.toSet();
    state = localIds;
    await _loadServerState(localIds);
  }

  Future<void> _loadServerState(Set<String> localIds) async {
    final auth = _ref.read(authControllerProvider);
    if (auth.user == null) return;
    try {
      if (localIds.isNotEmpty) {
        final synced = await _ref
            .read(customerCabinetApiProvider)
            .syncFavoriteProducts(localIds.toList());
        await _applyServerRows(synced);
        return;
      }
      final rows = await _ref
          .read(customerCabinetApiProvider)
          .getFavoriteProducts();
      await _applyServerRows(rows);
    } catch (_) {
      // Local cache remains available when offline or unauthenticated.
    }
  }

  Future<void> _applyServerRows(List<Map<String, dynamic>> rows) async {
    final ids = rows
        .map((row) => (row['product_id'] ?? row['id']).toString().trim())
        .where((id) => id.isNotEmpty)
        .toSet();
    state = ids;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_key, ids.toList());
  }

  Future<void> _persistLocal(Set<String> ids) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_key, ids.toList());
  }

  Future<void> _syncServer(
    Set<String> ids, {
    String? changedId,
    required bool added,
  }) async {
    final auth = _ref.read(authControllerProvider);
    if (auth.user == null) return;
    try {
      final api = _ref.read(customerCabinetApiProvider);
      final rows = changedId == null
          ? await api.syncFavoriteProducts(ids.toList())
          : added
          ? await api.addFavoriteProduct(changedId)
          : await api.deleteFavoriteProduct(changedId);
      await _applyServerRows(rows);
    } catch (_) {
      // Keep optimistic local state; next load will reconcile.
    }
  }

  Future<void> toggle(String productId) async {
    final id = productId.trim();
    if (id.isEmpty) return;
    final next = {...state};
    var added = false;
    if (next.contains(id)) {
      next.remove(id);
    } else {
      next.add(id);
      added = true;
    }
    state = next;
    await _persistLocal(next);
    await _syncServer(next, changedId: id, added: added);
  }

  Future<void> ensureAdded(String productId) async {
    final id = productId.trim();
    if (id.isEmpty || state.contains(id)) return;
    final next = {...state, id};
    state = next;
    await _persistLocal(next);
    await _syncServer(next, changedId: id, added: true);
  }

  Future<void> remove(String productId) async {
    final id = productId.trim();
    if (id.isEmpty) return;
    if (!state.contains(id)) return;
    final next = {...state}..remove(id);
    state = next;
    await _persistLocal(next);
    await _syncServer(next, changedId: id, added: false);
  }
}
