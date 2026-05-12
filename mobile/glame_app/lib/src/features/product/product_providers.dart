import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import 'product_api.dart';

final productApiProvider = Provider<ProductApi>((ref) {
  return ProductApi(ref.watch(apiClientProvider));
});

final productProvider = FutureProvider.family<Map<String, dynamic>, String>((
  ref,
  id,
) async {
  return ref.watch(productApiProvider).getProduct(id);
});

final productVariantsProvider =
    FutureProvider.family<Map<String, dynamic>, String>((ref, id) async {
      return ref.watch(productApiProvider).getProductVariants(id);
    });

final productLooksProvider = FutureProvider.family<List<dynamic>, String>((
  ref,
  id,
) async {
  return ref.watch(productApiProvider).getProductLooks(id);
});

final productRecommendationsProvider =
    FutureProvider.family<List<dynamic>, String>((ref, id) async {
      return ref.watch(productApiProvider).getProductRecommendations(id);
    });
