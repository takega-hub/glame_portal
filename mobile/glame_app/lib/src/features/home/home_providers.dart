import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../auth/auth_controller.dart';
import '../looks/looks_providers.dart';
import 'home_api.dart';

const _homeStoresCacheKey = 'glame.home.stores.v1';
const _homeSlidesCachePrefix = 'glame.home.slides.v2.';
const _homeNewLooksCacheKey = 'glame.home.new_looks.v1';
const _bundledStoresAsset = 'assets/data/stores_snapshot.json';

final homeApiProvider = Provider<HomeApi>((ref) {
  return HomeApi(ref.watch(apiClientProvider));
});

final homeHeroBannersProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.watch(homeApiProvider).getBanners(placement: 'home_hero');
});

final homeSlidesProvider = StreamProvider<List<dynamic>>((ref) {
  return _watchHomeSlides(ref.watch(homeApiProvider), 'style_inside');
});

final homePhotoSelectionBlockProvider = StreamProvider<Map<String, dynamic>?>((
  ref,
) {
  return _watchHomeSlideMap(ref.watch(homeApiProvider), 'photo_selection');
});

final homeHowToBuyBlockProvider = StreamProvider<Map<String, dynamic>?>((ref) {
  return _watchHomeSlideMap(ref.watch(homeApiProvider), 'service_how_to_buy');
});

Stream<Map<String, dynamic>?> _watchHomeSlideMap(
  HomeApi api,
  String blockKey,
) async* {
  await for (final slides in _watchHomeSlides(api, blockKey)) {
    yield _firstHomeSlideMap(slides);
  }
}

Stream<List<dynamic>> _watchHomeSlides(HomeApi api, String blockKey) async* {
  final cacheKey = '$_homeSlidesCachePrefix$blockKey';
  final cached = await _readJsonListCache(cacheKey);
  if (cached.isNotEmpty) {
    yield cached;
  }

  try {
    final remote = await api.getHomeSlides(blockKey: blockKey);
    if (remote.isNotEmpty) {
      await _saveJsonListCache(cacheKey, remote);
      if (jsonEncode(remote) != jsonEncode(cached)) {
        yield remote;
      }
    } else if (cached.isEmpty) {
      yield const <dynamic>[];
    }
  } catch (_) {
    if (cached.isEmpty) yield const <dynamic>[];
  }
}

Map<String, dynamic>? _firstHomeSlideMap(List<dynamic> slides) {
  for (final item in slides) {
    if (item is Map) return Map<String, dynamic>.from(item);
  }
  return null;
}

Future<void> _saveJsonListCache(String key, List<dynamic> items) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString(key, jsonEncode(items));
}

Future<List<dynamic>> _readJsonListCache(String key) async {
  final prefs = await SharedPreferences.getInstance();
  final raw = prefs.getString(key);
  if (raw == null || raw.isEmpty) return const <dynamic>[];
  try {
    final decoded = jsonDecode(raw);
    if (decoded is List) return decoded;
  } catch (_) {
    await prefs.remove(key);
  }
  return const <dynamic>[];
}

final homePromotionsProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.watch(homeApiProvider).getPromotions();
});

final homeLookbooksProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.watch(homeApiProvider).getLookbooks();
});

final homeNewsProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.watch(homeApiProvider).getNews();
});

final homeStoresProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.watch(homeStoresRepositoryProvider).getStores();
});

final homeStoresRepositoryProvider = Provider<HomeStoresRepository>((ref) {
  return HomeStoresRepository(ref.watch(homeApiProvider));
});

class HomeStoresRepository {
  final HomeApi _api;

  const HomeStoresRepository(this._api);

  Future<List<dynamic>> getStores() async {
    try {
      final remote = await _api.getStores();
      if (remote.isNotEmpty) {
        await _saveCache(remote);
        return remote;
      }
    } catch (_) {
      // Spaces remain available from local cache or bundled snapshot offline.
    }

    final cached = await _readCache();
    if (cached.isNotEmpty) return cached;

    return _readBundledSnapshot();
  }

  Future<void> _saveCache(List<dynamic> stores) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_homeStoresCacheKey, jsonEncode(stores));
  }

  Future<List<dynamic>> _readCache() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_homeStoresCacheKey);
    if (raw == null || raw.isEmpty) return const <dynamic>[];
    try {
      final decoded = jsonDecode(raw);
      if (decoded is List) return decoded;
    } catch (_) {
      await prefs.remove(_homeStoresCacheKey);
    }
    return const <dynamic>[];
  }

  Future<List<dynamic>> _readBundledSnapshot() async {
    final raw = await rootBundle.loadString(_bundledStoresAsset);
    final decoded = jsonDecode(raw);
    if (decoded is List) return decoded;
    return const <dynamic>[];
  }
}

final homeCatalogSectionsProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.watch(homeApiProvider).getCatalogSections();
});

final productCharacteristicsProvider = FutureProvider<Map<String, dynamic>>((
  ref,
) async {
  return ref.watch(homeApiProvider).getCharacteristicsValues();
});

final homeNewProductsProvider = FutureProvider<List<dynamic>>((ref) async {
  final raw = await ref
      .watch(homeApiProvider)
      .getProductsPaged(skip: 0, limit: 12, inStock: true, hasImages: true);
  final items = raw['items'];
  if (items is List) return items;
  return const <dynamic>[];
});

final homeNewLooksProvider = StreamProvider<List<dynamic>>((ref) async* {
  final cached = await _readJsonListCache(_homeNewLooksCacheKey);
  if (cached.isNotEmpty) {
    yield cached;
  }

  try {
    final remote = await ref
        .watch(looksApiProvider)
        .getFeed(limit: 12, isNew: true);
    if (remote.isNotEmpty) {
      await _saveJsonListCache(_homeNewLooksCacheKey, remote);
      if (jsonEncode(remote) != jsonEncode(cached)) {
        yield remote;
      }
    } else if (cached.isEmpty) {
      yield const <dynamic>[];
    }
  } catch (_) {
    if (cached.isEmpty) yield const <dynamic>[];
  }
});

final homeCategoryPreviewProductsProvider =
    FutureProvider<Map<String, Map<String, dynamic>>>((ref) async {
      const categories = [
        'Кольца',
        'Серьги',
        'Колье',
        'Браслеты',
        'Чокеры',
        'Каффы',
        'NEW',
        'SALE',
      ];
      final api = ref.watch(homeApiProvider);
      final previews = <String, Map<String, dynamic>>{};

      for (final category in categories) {
        final raw = await api.getProductsPaged(
          skip: 0,
          limit: 1,
          category: category,
          inStock: true,
          hasImages: true,
        );
        final items = raw['items'];
        if (items is List && items.isNotEmpty && items.first is Map) {
          previews[category.toLowerCase()] = Map<String, dynamic>.from(
            items.first as Map,
          );
        }
      }

      return previews;
    });
