import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_controller.dart';
import 'customer_cabinet_api.dart';

final customerCabinetApiProvider = Provider<CustomerCabinetApi>((ref) {
  return CustomerCabinetApi(ref.watch(apiClientProvider));
});

final customerProfileProvider = FutureProvider<Map<String, dynamic>>((
  ref,
) async {
  return ref.watch(customerCabinetApiProvider).getProfile();
});

final customerLoyaltyProvider = FutureProvider<Map<String, dynamic>>((
  ref,
) async {
  return ref.watch(customerCabinetApiProvider).getLoyalty();
});

final customerPurchaseHistoryProvider =
    FutureProvider<List<Map<String, dynamic>>>((ref) async {
      return ref
          .watch(customerCabinetApiProvider)
          .getPurchaseHistory(limit: 20);
    });

final customerOrdersProvider = FutureProvider<List<Map<String, dynamic>>>((
  ref,
) async {
  final api = ref.watch(customerCabinetApiProvider);
  final orders = await api.getOrders(limit: 20, skip: 0);
  if (orders.isEmpty) return const <Map<String, dynamic>>[];

  final withStatuses = await Future.wait(
    orders.map((order) async {
      final id = (order['id'] as String?)?.trim();
      if (id == null || id.isEmpty) return order;
      try {
        final status = await api.getOrderPaymentStatus(id);
        return {
          ...order,
          'payment_status_payload': status,
          'payment': status['payment'],
          'order_status': status['order_status'] ?? order['status'],
        };
      } catch (_) {
        return order;
      }
    }),
  );
  return withStatuses;
});

final stylistChatMessagesProvider = FutureProvider<List<Map<String, dynamic>>>((
  ref,
) async {
  final auth = ref.watch(authControllerProvider);
  if (auth.user == null) return const <Map<String, dynamic>>[];
  return ref.watch(customerCabinetApiProvider).getStylistChatMessages();
});

final stylistChatStatusProvider = FutureProvider<Map<String, dynamic>>((
  ref,
) async {
  final auth = ref.watch(authControllerProvider);
  if (auth.user == null) {
    return const <String, dynamic>{
      'status_text': 'График стилиста: 10:00-20:00 по МСК',
    };
  }
  return ref.watch(customerCabinetApiProvider).getStylistChatStatus();
});

final customerSavedLooksProvider = FutureProvider<List<Map<String, dynamic>>>((
  ref,
) async {
  return ref.watch(customerCabinetApiProvider).getSavedLooks();
});

final customerFavoriteLooksProvider =
    FutureProvider<List<Map<String, dynamic>>>((ref) async {
      final auth = ref.watch(authControllerProvider);
      if (auth.user == null) return const <Map<String, dynamic>>[];
      return ref
          .watch(customerCabinetApiProvider)
          .getSavedLooks(saveType: 'favorite');
    });
