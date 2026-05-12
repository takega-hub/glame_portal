import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';

class LooksApi {
  final Dio _dio;
  static const int pageSize = 50;

  LooksApi(ApiClient client) : _dio = client.dio;

  Future<List<dynamic>> getFeed({
    int skip = 0,
    int limit = pageSize,
    bool? isNew,
  }) async {
    final resp = await _dio.get(
      '/looks/feed',
      queryParameters: {
        'skip': skip,
        'limit': limit,
        ...?isNew == null ? null : {'is_new': isNew},
      },
    );
    return (resp.data as List<dynamic>?) ?? const [];
  }

  Future<List<dynamic>> getAllFeed({bool? isNew}) async {
    final items = <dynamic>[];
    var skip = 0;

    while (true) {
      final page = await getFeed(skip: skip, limit: pageSize, isNew: isNew);
      if (page.isEmpty) break;
      items.addAll(page);
      if (page.length < pageSize) break;
      skip += page.length;
    }

    return items;
  }

  Future<Map<String, dynamic>> toggleLike(String lookId) async {
    final resp = await _dio.post('/looks/feed/$lookId/like');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> toggleFavorite(String lookId) async {
    final resp = await _dio.post('/looks/feed/$lookId/favorite');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> getLook(String lookId) async {
    final resp = await _dio.get('/looks/$lookId');
    return Map<String, dynamic>.from(resp.data as Map);
  }
}
