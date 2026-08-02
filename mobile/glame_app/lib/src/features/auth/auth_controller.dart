import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:dio/dio.dart';

import '../../core/network/api_client.dart';
import '../../core/storage/token_storage.dart';
import 'auth_api.dart';
import 'user.dart';

class AuthState {
  final User? user;
  final bool loading;
  final String? error;

  const AuthState({required this.user, required this.loading, this.error});

  factory AuthState.initial() => const AuthState(user: null, loading: true);

  static const Object _unset = Object();

  AuthState copyWith({
    Object? user = _unset,
    bool? loading,
    Object? error = _unset,
  }) {
    return AuthState(
      user: identical(user, _unset) ? this.user : user as User?,
      loading: loading ?? this.loading,
      error: identical(error, _unset) ? this.error : error as String?,
    );
  }
}

final _secureStorageProvider = Provider<FlutterSecureStorage>((ref) {
  return const FlutterSecureStorage();
});

final tokenStorageProvider = Provider<TokenStorage>((ref) {
  return TokenStorage(ref.watch(_secureStorageProvider));
});

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(tokenStorage: ref.watch(tokenStorageProvider));
});

final authApiProvider = Provider<AuthApi>((ref) {
  return AuthApi(ref.watch(apiClientProvider));
});

final authControllerProvider = StateNotifierProvider<AuthController, AuthState>(
  (ref) {
    return AuthController(
      authApi: ref.watch(authApiProvider),
      tokenStorage: ref.watch(tokenStorageProvider),
    );
  },
);

class AuthController extends StateNotifier<AuthState> {
  final AuthApi authApi;
  final TokenStorage tokenStorage;

  AuthController({required this.authApi, required this.tokenStorage})
    : super(AuthState.initial()) {
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    try {
      final pair = await tokenStorage.read();
      if (pair == null) {
        state = state.copyWith(user: null, loading: false);
        return;
      }
      final raw = await authApi.me();
      state = AuthState(user: User.fromJson(raw), loading: false);
    } catch (_) {
      await tokenStorage.clear();
      state = state.copyWith(user: null, loading: false);
    }
  }

  Future<void> login({required String email, required String password}) async {
    state = state.copyWith(loading: true, error: null);
    try {
      final token = await authApi.login(email: email, password: password);
      final accessToken = token['access_token'] as String?;
      final refreshToken = token['refresh_token'] as String?;
      if (accessToken == null || refreshToken == null) {
        state = state.copyWith(
          loading: false,
          error: 'Некорректный ответ авторизации',
        );
        return;
      }
      await tokenStorage.write(
        TokenPair(accessToken: accessToken, refreshToken: refreshToken),
      );
      final raw = await authApi.me();
      state = AuthState(user: User.fromJson(raw), loading: false);
    } catch (e) {
      state = state.copyWith(loading: false, error: 'Ошибка входа');
      rethrow;
    }
  }

  Future<void> requestOtp({required String phone}) async {
    state = state.copyWith(loading: true, error: null);
    try {
      await authApi.requestOtp(phone: phone);
      state = state.copyWith(loading: false, error: null);
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) {
        state = state.copyWith(loading: false, error: 'not_found');
        rethrow;
      }
      state = state.copyWith(loading: false, error: 'Ошибка запроса кода');
      rethrow;
    } catch (e) {
      // Это может быть FormatException: SyntaxError: Unexpected end of JSON input
      // Если сервер вернул пустой ответ или ответ не JSON (а Dio пытается его распарсить)
      // В любом случае считаем, что запрос прошел, если нет DioException с ошибкой
      state = state.copyWith(loading: false, error: null);
    }
  }

  void clearError() {
    if (state.error != null) {
      state = state.copyWith(error: null);
    }
  }

  Future<bool> loginOtp({required String phone, required String code}) async {
    state = state.copyWith(loading: true, error: null);
    try {
      final token = await authApi.loginOtp(phone: phone, code: code);
      final accessToken = token['access_token'] as String?;
      final refreshToken = token['refresh_token'] as String?;
      final requirePasswordChange =
          token['require_password_change'] as bool? ?? false;

      if (accessToken == null || refreshToken == null) {
        state = state.copyWith(
          loading: false,
          error: 'Некорректный ответ авторизации',
        );
        return false;
      }
      await tokenStorage.write(
        TokenPair(accessToken: accessToken, refreshToken: refreshToken),
      );
      final raw = await authApi.me();
      state = AuthState(user: User.fromJson(raw), loading: false);
      return requirePasswordChange;
    } catch (e) {
      state = state.copyWith(
        loading: false,
        error: 'Неверный код или ошибка входа',
      );
      rethrow;
    }
  }

  Future<void> registerPhone({
    required String phone,
    required String password,
    required String fullName,
    String? birthDate,
    String? referralCode,
  }) async {
    state = state.copyWith(loading: true, error: null);
    try {
      await authApi.registerPhone(
        phone: phone,
        password: password,
        fullName: fullName,
        birthDate: birthDate,
        referralCode: referralCode,
      );
      // After registration, auto-login
      await login(email: phone, password: password);
    } on DioException catch (e) {
      final detail = e.response?.data is Map
          ? (e.response?.data as Map)['detail']?.toString()
          : null;
      state = state.copyWith(
        loading: false,
        error: detail == 'Phone already registered'
            ? 'Телефон уже зарегистрирован. Войдите в аккаунт.'
            : detail == 'Invalid referral code'
            ? 'Реферальный код не найден или неактивен.'
            : detail ?? 'Ошибка регистрации',
      );
      rethrow;
    } catch (e) {
      state = state.copyWith(loading: false, error: 'Ошибка регистрации');
      rethrow;
    }
  }

  Future<void> changePassword({
    required String newPassword,
    String? currentPassword,
  }) async {
    state = state.copyWith(loading: true, error: null);
    try {
      await authApi.changePassword(
        newPassword: newPassword,
        currentPassword: currentPassword,
      );
      state = state.copyWith(loading: false);
    } catch (e) {
      state = state.copyWith(loading: false, error: 'Ошибка смены пароля');
      rethrow;
    }
  }

  Future<void> logout() async {
    await tokenStorage.clear();
    state = state.copyWith(user: null, loading: false);
  }
}
