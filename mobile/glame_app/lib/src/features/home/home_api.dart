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
    String? pokrytie,
    String? tipZamka,
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
        if (pokrytie != null && pokrytie.isNotEmpty) 'pokrytie': pokrytie,
        if (tipZamka != null && tipZamka.isNotEmpty) 'tip_zamka': tipZamka,
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
