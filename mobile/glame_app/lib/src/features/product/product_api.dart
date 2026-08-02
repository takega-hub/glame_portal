import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';

class ProductApi {
  final Dio _dio;

  ProductApi(ApiClient client) : _dio = client.dio;

  Future<Map<String, dynamic>> getProduct(String id) async {
    final resp = await _dio.get('/products/$id');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> getProductVariants(String id) async {
    final resp = await _dio.get('/products/$id/variants');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<List<dynamic>> getProductLooks(String id) async {
    final resp = await _dio.get('/looks/product/$id');
    return (resp.data as List<dynamic>?) ?? const [];
  }

  Future<List<dynamic>> getProductRecommendations(String id) async {
    final resp = await _dio.get(
      '/products/$id/recommendations',
      queryParameters: const {'limit': 3},
    );
    return (resp.data as List<dynamic>?) ?? const [];
  }

  Future<Map<String, dynamic>> subscribeArrival({
    required String productId,
    required String variantProductId,
    required String email,
  }) async {
    final resp = await _dio.post(
      '/products/$productId/arrival-subscriptions',
      data: {
        'email': email,
        'variant_product_id': variantProductId,
        'source': 'product_card',
      },
    );
    return Map<String, dynamic>.from(resp.data as Map);
  }
}
