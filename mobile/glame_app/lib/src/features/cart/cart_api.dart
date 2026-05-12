import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';

class CartApi {
  final Dio _dio;

  CartApi(ApiClient client) : _dio = client.dio;

  Future<Map<String, dynamic>> getCart() async {
    final resp = await _dio.get('/cart');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<void> addItem({
    required String productId,
    required int quantity,
  }) async {
    await _dio.post(
      '/cart/items',
      data: {'product_id': productId, 'quantity': quantity},
    );
  }

  Future<void> updateItemQuantity({
    required String itemId,
    required int quantity,
  }) async {
    await _dio.put('/cart/items/$itemId', data: {'quantity': quantity});
  }

  Future<void> deleteItem({required String itemId}) async {
    await _dio.delete('/cart/items/$itemId');
  }
}
