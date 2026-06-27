import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';

class HomeApi {
  final Dio _dio;

  HomeApi(ApiClient client) : _dio = client.dio;

  Future<List<dynamic>> getHomeSlides({
    String blockKey = 'style_inside',
  }) async {
    final resp = await _dio.get(
      '/app/home-slides',
      queryParameters: {'block_key': blockKey},
    );
    return (resp.data as List<dynamic>?) ?? const [];
  }

  Future<List<dynamic>> getBanners({required String placement}) async {
    final resp = await _dio.get(
      '/app/banners',
      queryParameters: {'placement': placement},
    );
    return (resp.data as List<dynamic>?) ?? const [];
  }

  Future<List<dynamic>> getPromotions() async {
    final resp = await _dio.get('/app/promotions');
    return (resp.data as List<dynamic>?) ?? const [];
  }

  Future<List<dynamic>> getLookbooks() async {
    final resp = await _dio.get('/app/lookbooks');
    return (resp.data as List<dynamic>?) ?? const [];
  }

  Future<List<dynamic>> getNews() async {
    final resp = await _dio.get('/app/news');
    return (resp.data as List<dynamic>?) ?? const [];
  }

  Future<List<dynamic>> getStores() async {
    final resp = await _dio.get('/app/stores');
    return (resp.data as List<dynamic>?) ?? const [];
  }

  Future<List<dynamic>> getPickupStores() async {
    final resp = await _dio.get(
      '/stores',
      queryParameters: {'active': true, 'pickup_only': true},
    );
    return (resp.data as List<dynamic>?) ?? const [];
  }

  Future<List<Map<String, dynamic>>> getCdekCities(String query) async {
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

  Future<List<Map<String, dynamic>>> getCdekPvz(int cityCode) async {
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

  Future<Map<String, dynamic>> getProductsPaged({
    required int skip,
    required int limit,
    String? category,
    String? brand,
    String? search,
    bool? inStock,
    bool? hasImages,
    int? priceMin,
    int? priceMax,
    String? sort,
    String? material,
    String? vstavka,
    String? pokrytie,
    String? razmer,
    String? tipZamka,
    String? color,
  }) async {
    final resp = await _dio.get(
      '/products/paged',
      queryParameters: {
        'skip': skip,
        'limit': limit,
        if (category != null && category.isNotEmpty) 'category': category,
        if (brand != null && brand.isNotEmpty) 'brand': brand,
        if (search != null && search.isNotEmpty) 'search': search,
        if (inStock == true) 'in_stock': true,
        ...?(hasImages == null ? null : {'has_images': hasImages}),
        ...?(priceMin != null ? {'price_min': priceMin} : null),
        ...?(priceMax != null ? {'price_max': priceMax} : null),
        if (sort != null && sort.isNotEmpty) 'sort': sort,
        if (material != null && material.isNotEmpty) 'material': material,
        if (vstavka != null && vstavka.isNotEmpty) 'vstavka': vstavka,
        if (pokrytie != null && pokrytie.isNotEmpty) 'pokrytie': pokrytie,
        if (razmer != null && razmer.isNotEmpty) 'razmer': razmer,
        if (tipZamka != null && tipZamka.isNotEmpty) 'tip_zamka': tipZamka,
        if (color != null && color.isNotEmpty) 'color': color,
      },
    );
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> getCharacteristicsValues() async {
    final resp = await _dio.get('/products/characteristics/values');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<List<dynamic>> getCatalogSections() async {
    final resp = await _dio.get('/catalog-sections/');
    return (resp.data as List<dynamic>?) ?? const [];
  }
}
