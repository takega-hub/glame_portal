import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import '../home/home_api.dart';

class CatalogState {
  final List<Map<String, dynamic>> items;
  final int total;
  final bool loading;
  final String? category;
  final bool hasMore;
  final String? error;
  final bool oneColumn;
  final String? brand;
  final int? priceMin;
  final int? priceMax;
  final String? material;
  final String? vstavka;
  final String? pokrytie;
  final String? razmer;
  final String? tipZamka;
  final String? color;
  final String? sort;
  final String? search;
  final bool inStockOnly;

  const CatalogState({
    required this.items,
    required this.total,
    required this.loading,
    required this.category,
    required this.hasMore,
    required this.error,
    required this.oneColumn,
    required this.brand,
    required this.priceMin,
    required this.priceMax,
    required this.material,
    required this.vstavka,
    required this.pokrytie,
    required this.razmer,
    required this.tipZamka,
    required this.color,
    required this.sort,
    required this.search,
    required this.inStockOnly,
  });

  factory CatalogState.initial() {
    return const CatalogState(
      items: [],
      total: 0,
      loading: false,
      category: null,
      hasMore: true,
      error: null,
      oneColumn: false,
      brand: null,
      priceMin: null,
      priceMax: null,
      material: null,
      vstavka: null,
      pokrytie: null,
      razmer: null,
      tipZamka: null,
      color: null,
      sort: null,
      search: null,
      inStockOnly: false,
    );
  }

  CatalogState copyWith({
    List<Map<String, dynamic>>? items,
    int? total,
    bool? loading,
    String? category,
    bool? hasMore,
    String? error,
    bool? oneColumn,
    String? brand,
    int? priceMin,
    int? priceMax,
    String? material,
    String? vstavka,
    String? pokrytie,
    String? razmer,
    String? tipZamka,
    String? color,
    String? sort,
    String? search,
    bool? inStockOnly,
  }) {
    return CatalogState(
      items: items ?? this.items,
      total: total ?? this.total,
      loading: loading ?? this.loading,
      category: category ?? this.category,
      hasMore: hasMore ?? this.hasMore,
      error: error,
      oneColumn: oneColumn ?? this.oneColumn,
      brand: brand ?? this.brand,
      priceMin: priceMin ?? this.priceMin,
      priceMax: priceMax ?? this.priceMax,
      material: material ?? this.material,
      vstavka: vstavka ?? this.vstavka,
      pokrytie: pokrytie ?? this.pokrytie,
      razmer: razmer ?? this.razmer,
      tipZamka: tipZamka ?? this.tipZamka,
      color: color ?? this.color,
      sort: sort ?? this.sort,
      search: search ?? this.search,
      inStockOnly: inStockOnly ?? this.inStockOnly,
    );
  }
}

final catalogControllerProvider =
    StateNotifierProvider<CatalogController, CatalogState>((ref) {
      return CatalogController(api: HomeApi(ref.watch(apiClientProvider)));
    });

class CatalogController extends StateNotifier<CatalogState> {
  final HomeApi api;

  static const pageSize = 24;

  CatalogController({required this.api}) : super(CatalogState.initial()) {
    refresh();
  }

  Future<void> setCategory(String? category) async {
    final next = (category ?? '').trim();
    state = CatalogState(
      items: [],
      total: 0,
      loading: false,
      category: next.isEmpty ? null : next,
      hasMore: true,
      error: null,
      oneColumn: state.oneColumn,
      brand: state.brand,
      priceMin: state.priceMin,
      priceMax: state.priceMax,
      material: state.material,
      vstavka: state.vstavka,
      pokrytie: state.pokrytie,
      razmer: state.razmer,
      tipZamka: state.tipZamka,
      color: state.color,
      sort: state.sort,
      search: state.search,
      inStockOnly: state.inStockOnly,
    );
    await refresh();
  }

  Future<void> resetAndApply({
    String? category,
    String? search,
    String? brand,
  }) async {
    final nextCategory = (category ?? '').trim();
    final nextSearch = (search ?? '').trim();
    final nextBrand = (brand ?? '').trim();
    state = CatalogState(
      items: [],
      total: 0,
      loading: false,
      category: nextCategory.isEmpty ? null : nextCategory,
      hasMore: true,
      error: null,
      oneColumn: state.oneColumn,
      brand: nextBrand.isEmpty ? null : nextBrand,
      priceMin: null,
      priceMax: null,
      material: null,
      vstavka: null,
      pokrytie: null,
      razmer: null,
      tipZamka: null,
      color: null,
      sort: null,
      search: nextSearch.isEmpty ? null : nextSearch,
      inStockOnly: state.inStockOnly,
    );
    await refresh();
  }

  Future<void> toggleLayout() async {
    state = state.copyWith(oneColumn: !state.oneColumn);
  }

  Future<void> setFilters({
    int? priceMin,
    int? priceMax,
    String? brand,
    String? material,
    String? vstavka,
    String? pokrytie,
    String? razmer,
    String? tipZamka,
    String? color,
    String? sort,
    bool? inStockOnly,
  }) async {
    state = CatalogState(
      items: const [],
      total: 0,
      loading: false,
      category: state.category,
      hasMore: true,
      error: null,
      oneColumn: state.oneColumn,
      brand: _norm(brand),
      priceMin: priceMin,
      priceMax: priceMax,
      material: _norm(material),
      vstavka: _norm(vstavka),
      pokrytie: _norm(pokrytie),
      razmer: _norm(razmer),
      tipZamka: _norm(tipZamka),
      color: _norm(color),
      sort: _norm(sort),
      search: state.search,
      inStockOnly: inStockOnly ?? state.inStockOnly,
    );
    await refresh();
  }

  Future<void> setSearch(String? search) async {
    final next = (search ?? '').trim();
    state = CatalogState(
      items: [],
      total: 0,
      loading: false,
      category: state.category,
      hasMore: true,
      error: null,
      oneColumn: state.oneColumn,
      brand: state.brand,
      priceMin: state.priceMin,
      priceMax: state.priceMax,
      material: state.material,
      vstavka: state.vstavka,
      pokrytie: state.pokrytie,
      razmer: state.razmer,
      tipZamka: state.tipZamka,
      color: state.color,
      sort: state.sort,
      search: next.isEmpty ? null : next,
      inStockOnly: state.inStockOnly,
    );
    await refresh();
  }

  Future<void> setInStockOnly(bool value) async {
    state = state.copyWith(
      inStockOnly: value,
      items: [],
      total: 0,
      hasMore: true,
      error: null,
    );
    await refresh();
  }

  Future<void> refresh() async {
    if (state.loading) return;
    state = state.copyWith(loading: true, error: null);
    try {
      final raw = await api.getProductsPaged(
        skip: 0,
        limit: pageSize,
        category: state.category,
        brand: state.brand,
        search: state.search,
        inStock: state.inStockOnly ? true : null,
        hasImages: true,
        priceMin: state.priceMin,
        priceMax: state.priceMax,
        material: state.material,
        vstavka: state.vstavka,
        pokrytie: state.pokrytie,
        razmer: state.razmer,
        tipZamka: state.tipZamka,
        color: state.color,
        sort: state.sort,
      );
      final itemsRaw = raw['items'];
      final total = raw['total'];
      final items = (itemsRaw is List)
          ? itemsRaw
                .whereType<Map>()
                .map((x) => Map<String, dynamic>.from(x))
                .toList()
          : <Map<String, dynamic>>[];
      final totalInt = total is int
          ? total
          : (total is num ? total.toInt() : items.length);
      state = state.copyWith(
        items: items,
        total: totalInt,
        hasMore: items.length < totalInt,
        loading: false,
      );
    } catch (_) {
      state = state.copyWith(
        loading: false,
        error: 'Не удалось загрузить каталог',
      );
    }
  }

  Future<void> loadMore() async {
    if (state.loading || !state.hasMore) return;
    state = state.copyWith(loading: true, error: null);
    try {
      final raw = await api.getProductsPaged(
        skip: state.items.length,
        limit: pageSize,
        category: state.category,
        brand: state.brand,
        search: state.search,
        inStock: state.inStockOnly ? true : null,
        hasImages: true,
        priceMin: state.priceMin,
        priceMax: state.priceMax,
        material: state.material,
        vstavka: state.vstavka,
        pokrytie: state.pokrytie,
        razmer: state.razmer,
        tipZamka: state.tipZamka,
        color: state.color,
        sort: state.sort,
      );
      final itemsRaw = raw['items'];
      final total = raw['total'];
      final add = (itemsRaw is List)
          ? itemsRaw
                .whereType<Map>()
                .map((x) => Map<String, dynamic>.from(x))
                .toList()
          : <Map<String, dynamic>>[];
      final totalInt = total is int
          ? total
          : (total is num ? total.toInt() : state.total);
      final merged = [...state.items, ...add];
      state = state.copyWith(
        items: merged,
        total: totalInt,
        hasMore: merged.length < totalInt,
        loading: false,
      );
    } catch (_) {
      state = state.copyWith(
        loading: false,
        error: 'Не удалось загрузить ещё товары',
      );
    }
  }
}

String? _norm(String? value) {
  final next = (value ?? '').trim();
  return next.isEmpty ? null : next;
}
