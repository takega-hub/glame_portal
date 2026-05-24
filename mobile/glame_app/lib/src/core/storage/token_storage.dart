import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

class TokenPair {
  final String accessToken;
  final String refreshToken;

  const TokenPair({required this.accessToken, required this.refreshToken});
}

class TokenStorage {
  static const _accessKey = 'glame_access_token';
  static const _refreshKey = 'glame_refresh_token';

  final FlutterSecureStorage _storage;

  const TokenStorage(this._storage);

  Future<TokenPair?> read() async {
    final access = await _readValue(_accessKey);
    final refresh = await _readValue(_refreshKey);
    if (access == null || access.isEmpty || refresh == null || refresh.isEmpty) {
      return null;
    }
    return TokenPair(accessToken: access, refreshToken: refresh);
  }

  Future<void> write(TokenPair pair) async {
    // Best effort secure storage first (native/mobile).
    // On web over non-secure context this may throw, so we keep SharedPreferences fallback.
    try {
      await _storage.write(key: _accessKey, value: pair.accessToken);
      await _storage.write(key: _refreshKey, value: pair.refreshToken);
    } catch (_) {}

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_accessKey, pair.accessToken);
    await prefs.setString(_refreshKey, pair.refreshToken);
  }

  Future<void> clear() async {
    try {
      await _storage.delete(key: _accessKey);
      await _storage.delete(key: _refreshKey);
    } catch (_) {}

    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_accessKey);
    await prefs.remove(_refreshKey);
  }

  Future<String?> _readValue(String key) async {
    try {
      final value = await _storage.read(key: key);
      if (value != null && value.isNotEmpty) return value;
    } catch (_) {}

    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(key);
  }
}
