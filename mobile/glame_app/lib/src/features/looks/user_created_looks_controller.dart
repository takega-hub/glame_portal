import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../auth/auth_controller.dart';
import '../customer/customer_cabinet_providers.dart';

final userCreatedLooksProvider =
    StateNotifierProvider<
      UserCreatedLooksController,
      List<Map<String, dynamic>>
    >((ref) {
      ref.watch(authControllerProvider);
      return UserCreatedLooksController(ref);
    });

class UserCreatedLooksController
    extends StateNotifier<List<Map<String, dynamic>>> {
  static const _key = 'glame_user_created_looks';
  final Ref _ref;

  UserCreatedLooksController(this._ref)
    : super(const <Map<String, dynamic>>[]) {
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw != null && raw.trim().isNotEmpty) {
      try {
        final decoded = jsonDecode(raw);
        if (decoded is List) {
          state = decoded
              .whereType<Map>()
              .map((item) => Map<String, dynamic>.from(item))
              .toList(growable: false);
        }
      } catch (_) {
        // Keep the screen usable if an older local cache is malformed.
      }
    }
    await _syncFromServer();
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
    await _syncLookToServer(nextLook);
    return lookId;
  }

  Future<void> _syncFromServer() async {
    final auth = _ref.read(authControllerProvider);
    if (auth.user == null) return;
    try {
      final rows = await _ref
          .read(customerCabinetApiProvider)
          .getSavedLooks(saveType: 'generated');
      final serverLooks = rows
          .map(_normalizeServerLook)
          .whereType<Map<String, dynamic>>()
          .toList(growable: false);
      if (serverLooks.isEmpty) return;
      final serverIds = serverLooks
          .map((look) => _asString(look['id']))
          .toSet();
      final localOnly = state
          .where((look) => !serverIds.contains(_asString(look['id'])))
          .toList(growable: false);
      final next = [...serverLooks, ...localOnly];
      state = next;
      await _persist(next);
    } catch (_) {
      // Server sync is best-effort; local looks should remain available offline.
    }
  }

  Future<void> _syncLookToServer(Map<String, dynamic> look) async {
    final auth = _ref.read(authControllerProvider);
    if (auth.user == null) return;
    final rawProducts = look['products'];
    if (rawProducts is! List || rawProducts.isEmpty) return;
    final products = rawProducts
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
    if (products.isEmpty) return;

    final apiProducts = <Map<String, dynamic>>[];
    for (var i = 0; i < products.length; i++) {
      final product = products[i];
      final productId = _asString(product['id']);
      if (productId.isEmpty) continue;
      final imageUrl = _productImage(product);
      apiProducts.add({
        'id': productId,
        'role': i == 0 ? 'base' : 'accent',
        if (imageUrl != null && imageUrl.isNotEmpty)
          'selected_image_url': imageUrl,
      });
    }
    if (apiProducts.isEmpty) return;

    try {
      final serverId = _asString(look['look_id']).isNotEmpty
          ? _asString(look['look_id'])
          : _asString(look['id']);
      final response = await _ref
          .read(customerCabinetApiProvider)
          .upsertGeneratedLook(
            id: serverId,
            name: _asString(look['look_name'] ?? look['name']),
            goal: _asString(look['look_style'] ?? look['style']),
            totalPrice: _asInt(look['look_total_price'] ?? look['total_price']),
            products: apiProducts,
          );
      final serverLook = _normalizeServerLook(response);
      if (serverLook == null) return;
      final previousId = _asString(look['id']);
      final nextId = _asString(serverLook['id']);
      final next = [
        serverLook,
        ...state.where((item) {
          final itemId = _asString(item['id']);
          return itemId != previousId && itemId != nextId;
        }),
      ];
      state = next;
      await _persist(next);
      _ref.invalidate(customerSavedLooksProvider);
      _ref.invalidate(customerFavoriteLooksProvider);
    } catch (_) {
      // Local save succeeded; backend sync can be retried on the next edit/save.
    }
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

int? _asInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value.trim());
  return null;
}

Map<String, dynamic>? _normalizeServerLook(Map<String, dynamic> row) {
  final lookId = _asString(row['look_id']);
  if (lookId.isEmpty) return null;
  final name = _asString(row['look_name'] ?? row['name']);
  final style = _asString(row['look_style'] ?? row['style']);
  final description = _asString(row['look_description'] ?? row['description']);
  final products = (row['products'] is List)
      ? (row['products'] as List)
            .whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item))
            .toList(growable: false)
      : const <Map<String, dynamic>>[];
  final imageUrls = row['look_image_urls'] is List
      ? row['look_image_urls']
      : [
          if (_asString(row['look_image_url']).isNotEmpty)
            {'url': _asString(row['look_image_url'])},
        ];

  return {
    ...row,
    'id': lookId,
    'saved_look_id': _asString(row['id']),
    'look_id': lookId,
    'name': name,
    'look_name': name,
    'image_url': _asString(row['look_image_url']),
    'image_urls': imageUrls,
    'look_image_url': _asString(row['look_image_url']),
    'style': style,
    'look_style': style,
    'description': description,
    'look_description': description,
    'total_price': row['total_price'],
    'look_total_price': row['total_price'],
    'products': products,
    'is_user_created': true,
  };
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
