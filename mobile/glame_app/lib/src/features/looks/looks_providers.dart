import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import 'looks_api.dart';

final looksApiProvider = Provider<LooksApi>((ref) {
  return LooksApi(ref.watch(apiClientProvider));
});

final looksFeedProvider = FutureProvider<List<dynamic>>((ref) async {
  return ref.watch(looksApiProvider).getAllFeed();
});

final lookByIdProvider = FutureProvider.family<Map<String, dynamic>, String>((
  ref,
  lookId,
) async {
  return ref.watch(looksApiProvider).getLook(lookId);
});
