import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../features/auth/auth_controller.dart';
import '../network/api_client.dart';

final analyticsServiceProvider = Provider<AnalyticsService>((ref) {
  return AnalyticsService(ref.watch(apiClientProvider));
});

class AnalyticsService {
  AnalyticsService(this._client);

  static const _sessionKey = 'glame_analytics_session_id';
  static const _flushDelay = Duration(milliseconds: 250);
  static const _dedupeWindow = Duration(seconds: 2);

  final ApiClient _client;
  final List<Map<String, dynamic>> _queue = <Map<String, dynamic>>[];
  final Map<String, DateTime> _recentEvents = <String, DateTime>{};

  bool _flushing = false;
  Timer? _flushTimer;
  String? _sessionId;
  String? _lastScreen;

  Future<void> trackScreen(String screen, {Map<String, dynamic>? data}) async {
    final normalized = screen.trim().isEmpty ? '/' : screen.trim();
    if (_lastScreen == normalized) return;
    _lastScreen = normalized;

    await trackEvent(
      'page_view',
      channel: 'mobile_app',
      eventData: {
        'page_url': normalized,
        'screen': normalized,
        'platform': defaultTargetPlatform.name,
        'timestamp': DateTime.now().toIso8601String(),
        ...?data,
      },
      dedupeKey: 'page_view:$normalized',
    );
  }

  Future<void> trackTap(
    String label, {
    String? screen,
    Map<String, dynamic>? data,
  }) async {
    await trackEvent(
      'ui_click',
      channel: 'mobile_app',
      eventData: {
        'label': label,
        ...?screen == null ? null : {'page_url': screen},
        'platform': defaultTargetPlatform.name,
        'timestamp': DateTime.now().toIso8601String(),
        ...?data,
      },
      dedupeKey: 'ui_click:${screen ?? ''}:$label',
    );
  }

  Future<void> trackProductView(
    String productId, {
    Map<String, dynamic>? data,
  }) async {
    await trackEvent(
      'product_click',
      productId: productId,
      channel: 'mobile_app',
      eventData: {
        'page_url': '/product/$productId',
        'source': 'product_screen',
        'timestamp': DateTime.now().toIso8601String(),
        ...?data,
      },
      dedupeKey: 'product_click:$productId',
    );
  }

  Future<void> trackLookView(
    String lookId, {
    Map<String, dynamic>? data,
  }) async {
    await trackEvent(
      'look_view',
      lookId: lookId,
      channel: 'mobile_app',
      eventData: {
        'page_url': '/look/$lookId',
        'source': 'look_detail_screen',
        'timestamp': DateTime.now().toIso8601String(),
        ...?data,
      },
      dedupeKey: 'look_view:$lookId',
    );
  }

  Future<void> trackEvent(
    String eventType, {
    String channel = 'mobile_app',
    Map<String, dynamic>? eventData,
    String? productId,
    String? lookId,
    String? contentItemId,
    String? dedupeKey,
  }) async {
    final key = dedupeKey ?? '$eventType:${eventData?['page_url'] ?? ''}';
    final now = DateTime.now();
    final previous = _recentEvents[key];
    if (previous != null && now.difference(previous) < _dedupeWindow) return;
    _recentEvents[key] = now;

    final sessionId = await _getSessionId();
    _queue.add({
      'session_id': sessionId,
      'event_type': eventType,
      'event_data': eventData ?? const <String, dynamic>{},
      'channel': channel,
      if (_isUuid(productId)) 'product_id': productId,
      if (_isUuid(lookId)) 'look_id': lookId,
      if (_isUuid(contentItemId)) 'content_item_id': contentItemId,
    });
    if (_queue.length > 100) {
      _queue.removeRange(0, _queue.length - 100);
    }
    _scheduleFlush();
  }

  void _scheduleFlush() {
    _flushTimer ??= Timer(_flushDelay, () {
      _flushTimer = null;
      unawaited(_flush());
    });
  }

  Future<void> _flush() async {
    if (_flushing) return;
    _flushing = true;
    try {
      while (_queue.isNotEmpty) {
        final event = _queue.removeAt(0);
        try {
          await _client.dio.post('/analytics/track', data: event);
        } catch (_) {
          break;
        }
      }
    } finally {
      _flushing = false;
      if (_queue.isNotEmpty) _scheduleFlush();
    }
  }

  Future<String> _getSessionId() async {
    final cached = _sessionId;
    if (_isUuid(cached)) return cached!;

    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString(_sessionKey);
    if (_isUuid(stored)) {
      _sessionId = stored;
      return stored!;
    }

    final created = _createUuidV4();
    await prefs.setString(_sessionKey, created);
    _sessionId = created;
    return created;
  }
}

bool _isUuid(String? value) {
  if (value == null) return false;
  return RegExp(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    caseSensitive: false,
  ).hasMatch(value);
}

String _createUuidV4() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}
