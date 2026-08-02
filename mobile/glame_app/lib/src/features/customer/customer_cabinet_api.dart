import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';

class CustomerCabinetApi {
  final Dio _dio;

  CustomerCabinetApi(ApiClient client) : _dio = client.dio;

  Future<Map<String, dynamic>> getProfile() async {
    final resp = await _dio.get('/customer/profile');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> updateProfile({
    String? fullName,
    String? email,
    Map<String, dynamic>? preferredDelivery,
    List<Map<String, dynamic>>? deliveryAddresses,
  }) async {
    final resp = await _dio.put(
      '/customer/profile',
      data: {
        ?fullName == null ? null : 'full_name': fullName,
        ?email == null ? null : 'email': email,
        ?preferredDelivery == null ? null : 'preferred_delivery':
            preferredDelivery,
        ?deliveryAddresses == null ? null : 'delivery_addresses':
            deliveryAddresses,
      },
    );
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> getLoyalty() async {
    final resp = await _dio.get('/customer/loyalty');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<List<Map<String, dynamic>>> getPurchaseHistory({
    int limit = 20,
    int offset = 0,
  }) async {
    final resp = await _dio.get(
      '/customer/purchase-history',
      queryParameters: {'limit': limit, 'offset': offset},
    );
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
  }

  Future<List<Map<String, dynamic>>> getOrders({
    int limit = 20,
    int skip = 0,
  }) async {
    final resp = await _dio.get(
      '/orders',
      queryParameters: {'limit': limit, 'skip': skip},
    );
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
  }

  Future<List<Map<String, dynamic>>> getGiftCertificates() async {
    final resp = await _dio.get('/gift-certificates/my');
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
  }

  Future<Map<String, dynamic>> getOrderPaymentStatus(String orderId) async {
    final resp = await _dio.get('/orders/$orderId/payment-status');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> refreshPayment(String paymentId) async {
    final resp = await _dio.post('/payments/$paymentId/refresh');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> updateOrderDelivery({
    required String orderId,
    required Map<String, dynamic> delivery,
  }) async {
    final resp = await _dio.put(
      '/orders/$orderId/delivery',
      data: {'delivery': delivery},
    );
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> deleteOrder(String orderId) async {
    final resp = await _dio.delete('/orders/$orderId');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<List<Map<String, dynamic>>> getStylistChatMessages() async {
    final resp = await _dio.get('/customer/stylist-chat/messages');
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
  }

  Future<Map<String, dynamic>> clearStylistChatMessages() async {
    final resp = await _dio.delete('/customer/stylist-chat/messages');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> getStylistChatStatus() async {
    final resp = await _dio.get('/customer/stylist-chat/status');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<List<Map<String, dynamic>>> getSavedLooks({String? saveType}) async {
    final resp = await _dio.get(
      '/customer/saved-looks',
      queryParameters: {
        if (saveType != null && saveType.trim().isNotEmpty)
          'save_type': saveType,
      },
    );
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
  }

  Future<List<Map<String, dynamic>>> getFavoriteProducts() async {
    final resp = await _dio.get('/customer/favorite-products');
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
  }

  Future<List<Map<String, dynamic>>> syncFavoriteProducts(
    List<String> productIds,
  ) async {
    final resp = await _dio.put(
      '/customer/favorite-products',
      data: {'product_ids': productIds, 'source': 'app'},
    );
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
  }

  Future<List<Map<String, dynamic>>> addFavoriteProduct(
    String productId,
  ) async {
    final resp = await _dio.post('/customer/favorite-products/$productId');
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
  }

  Future<List<Map<String, dynamic>>> deleteFavoriteProduct(
    String productId,
  ) async {
    final resp = await _dio.delete('/customer/favorite-products/$productId');
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
  }

  Future<Map<String, dynamic>> deleteSavedLook(String savedLookId) async {
    final resp = await _dio.delete('/customer/saved-looks/$savedLookId');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> upsertGeneratedLook({
    String? id,
    String? name,
    String? goal,
    int? totalPrice,
    required List<Map<String, dynamic>> products,
  }) async {
    final resp = await _dio.post(
      '/customer/saved-looks/generated',
      data: {
        if (id != null && id.trim().isNotEmpty) 'id': id.trim(),
        if (name != null && name.trim().isNotEmpty) 'name': name.trim(),
        if (goal != null && goal.trim().isNotEmpty) 'goal': goal.trim(),
        ?totalPrice == null ? null : 'total_price': totalPrice,
        'products': products,
      },
    );
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> sendStylistChatMessage({
    required String text,
    String? productId,
    MultipartFile? photo,
    String? source,
    String? scenario,
    List<String> quickTags = const <String>[],
    List<String> favoriteProductIds = const <String>[],
  }) async {
    final trimmedText = text.trim();
    final form = FormData.fromMap({
      'text': trimmedText,
      if (productId != null && productId.isNotEmpty) 'product_id': productId,
      if (source != null && source.isNotEmpty) 'source': source,
      if (scenario != null && scenario.isNotEmpty) 'scenario': scenario,
      if (quickTags.isNotEmpty) 'quick_tags': quickTags.join(','),
      if (favoriteProductIds.isNotEmpty)
        'favorite_product_ids': favoriteProductIds.join(','),
      ?photo == null ? null : 'photo': photo,
    });
    final resp = await _dio.post('/customer/stylist-chat/messages', data: form);
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> getStylistReplacements({
    required String productId,
    int limit = 6,
  }) async {
    final resp = await _dio.get(
      '/customer/stylist-chat/replacements/$productId',
      queryParameters: {'limit': limit},
    );
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> addProductToCart({
    required String productId,
    int quantity = 1,
  }) async {
    final resp = await _dio.post(
      '/cart/items',
      data: {'product_id': productId, 'quantity': quantity},
    );
    return Map<String, dynamic>.from(resp.data as Map);
  }
}
