import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';

class CheckoutApi {
  final Dio _dio;

  CheckoutApi(ApiClient client) : _dio = client.dio;

  Future<Map<String, dynamic>> checkout({
    required String paymentMethod,
    required int deliveryAmount,
    required int discountAmount,
    required int useBonusPoints,
    required String returnUrl,
    Map<String, dynamic>? delivery,
    Map<String, dynamic>? contact,
  }) async {
    final resp = await _dio.post(
      '/checkout',
      data: {
        'payment_method': paymentMethod,
        'delivery_amount': deliveryAmount,
        'discount_amount': discountAmount,
        'use_bonus_points': useBonusPoints,
        'return_url': returnUrl,
        ...?(delivery == null ? null : {'delivery': delivery}),
        ...?(contact == null ? null : {'contact': contact}),
      },
    );
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> loyalty() async {
    final resp = await _dio.get('/customer/loyalty');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> profile() async {
    final resp = await _dio.get('/customer/profile');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<List<Map<String, dynamic>>> listStores() async {
    final resp = await _dio.get(
      '/stores',
      queryParameters: {'active': true, 'pickup_only': true},
    );
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
  }

  Future<Map<String, dynamic>> cdekOptions() async {
    final resp = await _dio.get('/shipping/cdek/options');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<List<Map<String, dynamic>>> cdekCities(String query) async {
    final resp = await _dio.get(
      '/shipping/cdek/cities',
      queryParameters: {'q': query, 'size': 20},
    );
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
  }

  Future<List<Map<String, dynamic>>> cdekPvz(int cityCode) async {
    final resp = await _dio.get(
      '/shipping/cdek/pvz',
      queryParameters: {'city_code': cityCode, 'size': 200},
    );
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .toList();
  }

  Future<Map<String, dynamic>> cdekCalculate({
    required int fromCityCode,
    required int toCityCode,
    required int weightG,
    required int lengthMm,
    required int widthMm,
    required int heightMm,
    List<int>? tariffCodes,
  }) async {
    final resp = await _dio.post(
      '/shipping/cdek/calculate',
      data: {
        'from_city_code': fromCityCode,
        'to_city_code': toCityCode,
        'packages': [
          {
            'weight': weightG,
            'length': lengthMm,
            'width': widthMm,
            'height': heightMm,
          },
        ],
        ...?(tariffCodes == null ? null : {'tariff_codes': tariffCodes}),
      },
    );
    return Map<String, dynamic>.from(resp.data as Map);
  }
}
