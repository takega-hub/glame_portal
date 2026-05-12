import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';

class AuthApi {
  final Dio _dio;

  AuthApi(ApiClient client) : _dio = client.dio;

  Future<Map<String, dynamic>> login({
    required String email,
    required String password,
  }) async {
    final form = FormData.fromMap({'username': email, 'password': password});
    final resp = await _dio.post('/auth/login', data: form);
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<void> requestOtp({required String phone}) async {
    await _dio.post('/auth/request-otp', data: {'phone': phone});
  }

  Future<Map<String, dynamic>> loginOtp({
    required String phone,
    required String code,
  }) async {
    final resp = await _dio.post(
      '/auth/login-otp',
      data: {'phone': phone, 'code': code},
    );
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<Map<String, dynamic>> registerPhone({
    required String phone,
    required String password,
    required String fullName,
    String? birthDate,
  }) async {
    final resp = await _dio.post(
      '/auth/register-phone',
      data: {
        'phone': phone,
        'password': password,
        'full_name': fullName,
        'birth_date': ?birthDate,
      },
    );
    return Map<String, dynamic>.from(resp.data as Map);
  }

  Future<void> changePassword({
    required String newPassword,
    String? currentPassword,
  }) async {
    await _dio.post(
      '/auth/change-password',
      data: {
        'new_password': newPassword,
        ...?(currentPassword == null
            ? null
            : {'current_password': currentPassword}),
      },
    );
  }

  Future<Map<String, dynamic>> me() async {
    final resp = await _dio.get('/auth/me');
    return Map<String, dynamic>.from(resp.data as Map);
  }
}
