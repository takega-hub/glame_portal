import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import '../looks/looks_providers.dart';
import 'home_api.dart';

final homeApiProvider = Provider<HomeApi>((ref) {
  return HomeApi(ref.watch(apiClientProvider));
});

final homeHeroBannersProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.watch(homeApiProvider).getBanners(placement: 'home_hero');
});

final homeSlidesProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.watch(homeApiProvider).getHomeSlides(blockKey: 'style_inside');
});

final homePhotoSelectionBlockProvider = FutureProvider<Map<String, dynamic>?>((
  ref,
) async {
  final raw = await ref
      .watch(homeApiProvider)
      .getHomeSlides(blockKey: 'photo_selection');
  for (final item in raw) {
    if (item is Map) {
      return Map<String, dynamic>.from(item);
    }
  }
  return null;
});

final homeHowToBuyBlockProvider = FutureProvider<Map<String, dynamic>?>((
  ref,
) async {
  final raw = await ref
      .watch(homeApiProvider)
      .getHomeSlides(blockKey: 'service_how_to_buy');
  for (final item in raw) {
    if (item is Map) {
      return Map<String, dynamic>.from(item);
    }
  }
  return null;
});

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
  return ref.watch(homeApiProvider).getStores();
});

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

final homeNewLooksProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.watch(looksApiProvider).getFeed(limit: 12, isNew: true);
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
