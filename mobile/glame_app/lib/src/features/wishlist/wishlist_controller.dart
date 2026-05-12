import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

final wishlistControllerProvider =
    StateNotifierProvider<WishlistController, Set<String>>((ref) {
      return WishlistController();
    });

class WishlistController extends StateNotifier<Set<String>> {
  static const _key = 'glame_wishlist_ids';

  WishlistController() : super(const {}) {
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final list = prefs.getStringList(_key) ?? const <String>[];
    state = list.toSet();
  }

  Future<void> toggle(String productId) async {
    final id = productId.trim();
    if (id.isEmpty) return;
    final next = {...state};
    if (next.contains(id)) {
      next.remove(id);
    } else {
      next.add(id);
    }
    state = next;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_key, next.toList());
  }

  Future<void> remove(String productId) async {
    final id = productId.trim();
    if (id.isEmpty) return;
    if (!state.contains(id)) return;
    final next = {...state}..remove(id);
    state = next;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_key, next.toList());
  }
}
