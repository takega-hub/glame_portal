import 'package:flutter/foundation.dart';

class Env {
  static const _defaultApiBaseUrl = 'https://portal.glamejewelry.ru';
  static const _configuredApiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: _defaultApiBaseUrl,
  );

  static String get apiBaseUrl {
    if (kIsWeb && _configuredApiBaseUrl == _defaultApiBaseUrl) {
      // On web default to current origin (e.g. http://5.101.179.47:9092)
      // so local/proxied environments work without TLS/CORS issues.
      return Uri.base.origin;
    }
    return _configuredApiBaseUrl;
  }

  static const apiPrefix = String.fromEnvironment(
    'API_PREFIX',
    defaultValue: '/api',
  );

  static Uri apiUri(String path, [Map<String, dynamic>? query]) {
    final base = Uri.parse(apiBaseUrl);
    final p = path.startsWith('/') ? path : '/$path';
    final fullPath = '$apiPrefix$p';
    return base.replace(
      path: fullPath,
      queryParameters: query?.map((k, v) => MapEntry(k, '$v')),
    );
  }
}
