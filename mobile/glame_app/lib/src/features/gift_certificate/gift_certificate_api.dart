import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../auth/auth_controller.dart';

final giftCertificateApiProvider = Provider<GiftCertificateApi>((ref) {
  return GiftCertificateApi(ref.watch(apiClientProvider));
});

class GiftCertificateApi {
  final Dio _dio;

  GiftCertificateApi(ApiClient client) : _dio = client.dio;

  Future<Map<String, dynamic>> purchase({
    required int amountKopeks,
    required String returnUrl,
    required String recipientName,
    required String recipientPhone,
    required String recipientEmail,
    required String message,
    required String senderName,
    required int design,
    DateTime? sendAt,
  }) async {
    final resp = await _dio.post(
      '/gift-certificates/purchase',
      data: {
        'nominal_amount': amountKopeks,
        'return_url': returnUrl,
        'recipient_name': recipientName.trim().isEmpty
            ? null
            : recipientName.trim(),
        'recipient_phone': recipientPhone.trim().isEmpty
            ? null
            : recipientPhone.trim(),
        'recipient_email': recipientEmail.trim().isEmpty
            ? null
            : recipientEmail.trim(),
        'message': message.trim().isEmpty ? null : message.trim(),
        'sender_name': senderName.trim().isEmpty ? null : senderName.trim(),
        'send_at': sendAt?.toIso8601String(),
        'design': design,
        'accent': 0,
        'texture_id': design == 1
            ? 'glame-gift-card-dark'
            : 'glame-gift-card-light',
        'expires_in_days': 365,
      },
    );
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<List<Map<String, dynamic>>> mine() async {
    final resp = await _dio.get('/gift-certificates/my');
    final raw = resp.data;
    if (raw is! List) return const <Map<String, dynamic>>[];
    return raw
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
  }

  Future<Map<String, dynamic>> getPaymentStatus(String orderId) async {
    final resp = await _dio.get('/orders/$orderId/payment-status');
    return Map<String, dynamic>.from(resp.data as Map);
  }
}
