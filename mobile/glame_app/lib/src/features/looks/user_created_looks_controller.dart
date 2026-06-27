import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

final userCreatedLooksProvider =
    StateNotifierProvider<
      UserCreatedLooksController,
      List<Map<String, dynamic>>
    >((ref) {
      return UserCreatedLooksController();
    });

class UserCreatedLooksController
    extends StateNotifier<List<Map<String, dynamic>>> {
  static const _key = 'glame_user_created_looks';

  UserCreatedLooksController() : super(const <Map<String, dynamic>>[]) {
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null || raw.trim().isEmpty) return;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return;
      state = decoded
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
    } catch (_) {
      // Keep the screen usable if an older local cache is malformed.
    }
  }

  Future<void> _persist(List<Map<String, dynamic>> looks) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, jsonEncode(looks));
  }

  Future<void> addLook({
    String? name,
    required String goal,
    required int totalPrice,
    required List<Map<String, dynamic>> products,
  }) async {
    await upsertLook(
      name: name,
      goal: goal,
      totalPrice: totalPrice,
      products: products,
    );
  }

  Future<String?> upsertLook({
    String? id,
    String? name,
    required String goal,
    required int totalPrice,
    required List<Map<String, dynamic>> products,
  }) async {
    if (products.isEmpty) return null;
    final now = DateTime.now();
    final lookId = id?.trim().isNotEmpty == true
        ? id!.trim()
        : 'local-look-${now.microsecondsSinceEpoch}';
    final cover = _productImage(products.first);
    final compactProducts = products
        .map(
          (product) => <String, dynamic>{
            'id': _asString(product['id']),
            'name': _asString(product['name']),
            'category': _asString(product['category']),
            'brand': _asString(product['brand']),
            'article': _asString(product['article']),
            'price': product['price'],
            'image_url': _productImage(product),
            'images': [
              if (_productImage(product) != null)
                {'url': _productImage(product)},
            ],
          },
        )
        .toList(growable: false);
    final lookName = name?.trim().isNotEmpty == true
        ? name!.trim()
        : 'Мой образ: $goal';
    final description = _descriptionFor(goal, compactProducts.length);
    final createdAt = id == null
        ? now.toIso8601String()
        : _asString(findById(lookId)?['created_at']);
    final nextLook = <String, dynamic>{
      'id': lookId,
      'look_id': '',
      'name': lookName,
      'look_name': lookName,
      'image_url': cover,
      'image_urls': [?cover],
      'look_image_url': cover,
      'style': goal,
      'look_style': goal,
      'description': description,
      'look_description': description,
      'total_price': totalPrice,
      'look_total_price': totalPrice,
      'products': compactProducts,
      'is_user_created': true,
      'created_at': createdAt.isEmpty ? now.toIso8601String() : createdAt,
      'updated_at': now.toIso8601String(),
    };
    final next = [
      nextLook,
      ...state.where((look) => _asString(look['id']) != lookId),
    ];
    state = next;
    await _persist(next);
    return lookId;
  }

  Map<String, dynamic>? findById(String id) {
    final normalized = id.trim();
    if (normalized.isEmpty) return null;
    for (final look in state) {
      if (_asString(look['id']) == normalized) {
        return Map<String, dynamic>.from(look);
      }
    }
    return null;
  }
}

String _descriptionFor(String goal, int count) {
  final productLabel = count == 1 ? '1 изделие' : '$count изделия';
  return 'Собранный вами комплект: $goal, $productLabel.';
}

String _asString(dynamic value) {
  return value?.toString().trim() ?? '';
}

String? _productImage(Map<String, dynamic> product) {
  final images = product['images'];
  if (images is List) {
    for (final item in images) {
      if (item is Map) {
        final url = _asString(item['url']);
        if (url.isNotEmpty) return url;
      } else {
        final url = _asString(item);
        if (url.isNotEmpty) return url;
      }
    }
  }
  final imageUrl = _asString(product['image_url']);
  if (imageUrl.isNotEmpty) return imageUrl;
  final image = _asString(product['image']);
  if (image.isNotEmpty) return image;
  return null;
}
