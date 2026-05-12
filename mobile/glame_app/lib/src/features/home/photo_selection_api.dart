import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../auth/auth_controller.dart';

final photoSelectionApiProvider = Provider<PhotoSelectionApi>((ref) {
  return PhotoSelectionApi(ref.watch(apiClientProvider));
});

class PhotoSelectionApi {
  final Dio _dio;

  PhotoSelectionApi(ApiClient client) : _dio = client.dio;

  Future<Map<String, dynamic>> analyzePhoto({
    required Uint8List bytes,
    String fileName = 'photo.jpg',
  }) async {
    final form = FormData.fromMap({
      'photo': MultipartFile.fromBytes(bytes, filename: fileName),
    });
    final resp = await _dio.post('/look-tryon/analyze', data: form);
    return Map<String, dynamic>.from(resp.data as Map);
  }
}
