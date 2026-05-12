import '../config/env.dart';
import 'package:flutter/foundation.dart';

String? resolveAssetUrl(dynamic value) {
  if (value == null) return null;

  if (value is String) {
    var raw = value.trim();
    if (raw.length >= 2) {
      final first = raw[0];
      final last = raw[raw.length - 1];
      final isWrapped =
          (first == '"' && last == '"') ||
          (first == '\'' && last == '\'') ||
          (first == '`' && last == '`');
      if (isWrapped) {
        raw = raw.substring(1, raw.length - 1).trim();
      }
    }
    if (raw.isEmpty) return null;
    if (raw.startsWith('assets/') || raw.startsWith('packages/')) {
      return raw;
    }

    try {
      final path = raw.startsWith('/') ? raw : '/$raw';
      final isPublicAsset =
          path.startsWith('/static/') ||
          path.startsWith('/uploads/') ||
          path.startsWith('/look_images/') ||
          path.startsWith('/content_post_images/');

      if (raw.startsWith('http://') || raw.startsWith('https://')) {
        final uri = Uri.tryParse(raw);
        if (uri != null && uri.path.isNotEmpty) {
          final isPublicAbsolute =
              uri.path.startsWith('/static/') ||
              uri.path.startsWith('/uploads/') ||
              uri.path.startsWith('/look_images/') ||
              uri.path.startsWith('/content_post_images/');
          if (kIsWeb && isPublicAbsolute) {
            final targetPath =
                uri.path +
                (uri.hasQuery ? '?${uri.query}' : '') +
                (uri.hasFragment ? '#${uri.fragment}' : '');
            return Uri.parse(Uri.base.origin).resolve(targetPath).toString();
          }
        }
        return raw;
      }

      if (kIsWeb && isPublicAsset) {
        return Uri.parse(Uri.base.origin).resolve(path).toString();
      }

      return Uri.parse(Env.apiBaseUrl).resolve(path).toString();
    } catch (_) {
      return raw;
    }
  }

  return null;
}
