import 'package:dio/dio.dart';

import '../config/env.dart';
import '../storage/token_storage.dart';

class ApiClient {
  final Dio dio;

  ApiClient._(this.dio);

  factory ApiClient({required TokenStorage tokenStorage}) {
    final dio = Dio(
      BaseOptions(
        baseUrl: '${Env.apiBaseUrl}${Env.apiPrefix}',
        connectTimeout: const Duration(seconds: 20),
        receiveTimeout: const Duration(seconds: 20),
        sendTimeout: const Duration(seconds: 20),
        headers: {'Accept': 'application/json'},
      ),
    );

    dio.interceptors.add(
      _AuthInterceptor(dio: dio, tokenStorage: tokenStorage),
    );
    return ApiClient._(dio);
  }
}

class _AuthInterceptor extends Interceptor {
  final Dio dio;
  final TokenStorage tokenStorage;
  bool _refreshing = false;

  _AuthInterceptor({required this.dio, required this.tokenStorage});

  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final pair = await tokenStorage.read();
    if (pair != null) {
      options.headers['Authorization'] = 'Bearer ${pair.accessToken}';
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    final status = err.response?.statusCode;
    final isAuthError = status == 401;
    final isRefreshCall = err.requestOptions.path.contains('/auth/refresh');

    if (!isAuthError || isRefreshCall) {
      handler.next(err);
      return;
    }

    if (_refreshing) {
      handler.next(err);
      return;
    }

    final pair = await tokenStorage.read();
    if (pair == null) {
      handler.next(err);
      return;
    }

    _refreshing = true;
    try {
      final refreshResp = await dio.post(
        '/auth/refresh',
        queryParameters: {'refresh_token': pair.refreshToken},
        options: Options(headers: {'Authorization': null}),
      );
      final accessToken = refreshResp.data['access_token'] as String?;
      final refreshToken = refreshResp.data['refresh_token'] as String?;
      if (accessToken == null || refreshToken == null) {
        await tokenStorage.clear();
        handler.next(err);
        return;
      }
      await tokenStorage.write(
        TokenPair(accessToken: accessToken, refreshToken: refreshToken),
      );

      final req = err.requestOptions;
      final cloned = await dio.request<dynamic>(
        req.path,
        data: req.data,
        queryParameters: req.queryParameters,
        options: Options(
          method: req.method,
          headers: {...req.headers, 'Authorization': 'Bearer $accessToken'},
          contentType: req.contentType,
          responseType: req.responseType,
          followRedirects: req.followRedirects,
          validateStatus: req.validateStatus,
          receiveDataWhenStatusError: req.receiveDataWhenStatusError,
        ),
      );
      handler.resolve(cloned);
    } catch (_) {
      await tokenStorage.clear();
      handler.next(err);
    } finally {
      _refreshing = false;
    }
  }
}
