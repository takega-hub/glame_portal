import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/login_screen.dart';
import '../features/auth/register_screen.dart';
import '../features/auth/otp_screen.dart';
import '../features/auth/change_password_screen.dart';
import '../features/home/home_shell.dart';
import '../features/home/photo_upload_screen.dart';
import '../features/brands/brands_screen.dart';
import '../features/customer/stylist_chat_screen.dart';
import '../features/catalog/catalog_screen.dart';
import '../features/product/product_screen.dart';
import '../features/onboarding/onboarding_controller.dart';
import '../features/onboarding/onboarding_screen.dart';
import '../features/profile/clients_screen.dart';
import '../features/checkout/checkout_screen.dart';
import '../features/looks/look_detail_screen.dart';
import '../features/looks/look_builder_screen.dart';
import '../features/looks/looks_screen.dart';
import '../features/looks/user_created_looks_controller.dart';
import '../features/service/how_to_buy_screen.dart';
import '../features/stores/stores_screen.dart';
import '../core/analytics/analytics_service.dart';
import '../core/theme/glame_theme.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final analytics = ref.read(analyticsServiceProvider);

  late final GoRouter router;
  ref.listen(onboardingControllerProvider, (_, next) => router.refresh());

  router = GoRouter(
    initialLocation: '/',
    redirect: (context, state) {
      final onboardingSeen = ref.read(onboardingControllerProvider);
      if (onboardingSeen == null) return null;

      final isOnboarding = state.matchedLocation == '/onboarding';
      if (onboardingSeen == false && !isOnboarding) {
        return '/onboarding';
      }
      if (onboardingSeen == true && isOnboarding) {
        return '/home';
      }

      unawaited(analytics.trackScreen(state.uri.toString()));
      return null;
    },
    routes: [
      GoRoute(path: '/', redirect: (context, state) => '/home'),
      GoRoute(
        path: '/onboarding',
        builder: (context, state) => const OnboardingScreen(),
      ),
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(
        path: '/auth/register',
        builder: (context, state) =>
            RegisterScreen(nextRoute: state.uri.queryParameters['next']),
      ),
      GoRoute(
        path: '/auth/otp',
        builder: (context, state) => OtpScreen(
          phone: state.uri.queryParameters['phone'] ?? '',
          nextRoute: state.uri.queryParameters['next'],
        ),
      ),
      GoRoute(
        path: '/auth/change-password',
        builder: (context, state) =>
            ChangePasswordScreen(nextRoute: state.extra as String?),
      ),
      GoRoute(
        path: '/home',
        builder: (context, state) {
          final tabRaw = state.uri.queryParameters['tab'];
          final tab = int.tryParse(tabRaw ?? '') ?? 0;
          return HomeShell(
            initialTab: tab,
            initialCategory: state.uri.queryParameters['category'],
            initialSearch: state.uri.queryParameters['search'],
            initialLookFilter: state.uri.queryParameters['lookFilter'],
          );
        },
      ),
      GoRoute(
        path: '/catalog',
        builder: (context, state) {
          final brandId = (state.uri.queryParameters['brand'] ?? '').trim();
          final categorySlug = (state.uri.queryParameters['category'] ?? '')
              .trim();
          final typeSlug = (state.uri.queryParameters['type'] ?? '').trim();
          final availableInSlug =
              (state.uri.queryParameters['availableIn'] ?? '').trim();
          final pick = (state.uri.queryParameters['pick'] ?? '').trim();
          return CatalogScreen(
            initialBrand: _catalogBrandNameFromId(brandId),
            initialCategory: _catalogCategoryFromRoute(
              categorySlug: categorySlug,
              typeSlug: typeSlug,
            ),
            initialSearch: _catalogSearchFromRoute(
              brandId: brandId,
              categorySlug: categorySlug,
              typeSlug: typeSlug,
              availableInSlug: availableInSlug,
            ),
            pickLookBase: pick == 'look_base',
          );
        },
      ),
      GoRoute(
        path: '/spaces',
        builder: (context, state) => const HomeShell(initialTab: 10),
      ),
      GoRoute(
        path: '/spaces/:slug',
        builder: (context, state) =>
            SpaceDetailScreen(slug: state.pathParameters['slug'] ?? ''),
      ),
      GoRoute(
        path: '/selection',
        builder: (context, state) =>
            SelectionMethodScreen(mode: state.uri.queryParameters['mode']),
      ),
      GoRoute(
        path: '/selection/gift',
        builder: (context, state) => const SelectionMethodScreen(mode: 'gift'),
      ),
      GoRoute(
        path: '/selection/ai-photo',
        builder: (context, state) => PhotoUploadScreen(
          resumePick: state.uri.queryParameters['resume'] == 'pick',
        ),
      ),
      GoRoute(
        path: '/look-builder',
        builder: (context, state) => LookBuilderScreen(
          initialLook: state.extra is Map
              ? Map<String, dynamic>.from(state.extra as Map)
              : null,
        ),
      ),
      GoRoute(
        path: '/product/:id',
        builder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return ProductScreen(productId: id);
        },
      ),
      GoRoute(
        path: '/checkout',
        builder: (context, state) => const CheckoutScreen(),
      ),
      GoRoute(
        path: '/clients',
        builder: (context, state) => const ClientsScreen(),
      ),
      GoRoute(
        path: '/stylist-chat',
        builder: (context, state) => StylistChatScreen(
          productId: state.uri.queryParameters['product_id'],
          initialMessage: state.uri.queryParameters['message'],
          source: state.uri.queryParameters['source'],
          scenario: state.uri.queryParameters['scenario'],
          quickTags: _csvQueryValues(state.uri.queryParameters['quick_tags']),
          favoriteProductIds: _csvQueryValues(
            state.uri.queryParameters['favorite_ids'],
          ),
        ),
      ),
      GoRoute(
        path: '/look/:id',
        builder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return LookDetailScreen(lookId: id);
        },
      ),
      GoRoute(
        path: '/my-look/:id',
        builder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          final look = ref.read(userCreatedLooksProvider.notifier).findById(id);
          return LookDetailScreen(lookId: id, localLook: look);
        },
      ),
      GoRoute(
        path: '/looks-profile',
        builder: (context, state) => LooksProfileScreen(
          initialFilter: state.uri.queryParameters['lookFilter'],
          initialTab: state.uri.queryParameters['tab'],
        ),
      ),
      GoRoute(
        path: '/photo-upload',
        builder: (context, state) => PhotoUploadScreen(
          resumePick: state.uri.queryParameters['resume'] == 'pick',
        ),
      ),
      GoRoute(
        path: '/brands',
        builder: (context, state) => const BrandsPageScreen(),
      ),
      GoRoute(
        path: '/brand/:id',
        builder: (context, state) =>
            BrandDetailScreen(brandId: state.pathParameters['id'] ?? ''),
      ),
      GoRoute(
        path: '/photo-review',
        builder: (context, state) =>
            PhotoReviewScreen(args: state.extra as PhotoReviewArgs?),
      ),
      GoRoute(
        path: '/photo-analysis',
        builder: (context, state) =>
            PhotoAnalysisScreen(args: state.extra as PhotoAnalysisArgs?),
      ),
      GoRoute(
        path: '/photo-selection-result',
        builder: (context, state) => PhotoSelectionResultScreen(
          args: state.extra as PhotoSelectionResultArgs?,
        ),
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});

String? _catalogBrandNameFromId(String brandId) {
  switch (brandId.trim().toLowerCase()) {
    case 'geometry':
      return 'Geometry';
    case 'magna':
      return 'Magna';
    case 'pearl':
      return 'Pearl';
    case 'crystal':
      return 'Crystal';
    case 'bicolor':
      return 'Bicolor';
    case 'prism-of-elegance':
      return 'Prism Of Elegance';
    case 'unode50':
      return 'UNOde50';
    case 'raganella-princess':
      return 'Raganella Princess';
    case 'island-soul':
      return 'Island Soul';
    case 'agafi':
      return 'AGafi';
    case 'antura':
      return 'Antura';
    case 'kalliope':
      return 'Kalliope';
    case 'wrinkles-of-time':
      return 'Wrinkles of Time';
    case 'claudio-canzian':
      return 'Claudio Canzian';
  }
  return null;
}

String? _catalogCategoryFromRoute({
  required String categorySlug,
  required String typeSlug,
}) {
  switch (categorySlug.trim().toLowerCase()) {
    case 'earrings':
      return 'Серьги';
    case 'ear_cuffs':
      return 'Каффы';
    case 'bracelets':
      return 'Браслеты';
    case 'necklaces':
      return 'Колье';
    case 'brooches':
      return null;
  }
  return null;
}

String? _catalogSearchFromRoute({
  required String brandId,
  required String categorySlug,
  required String typeSlug,
  required String availableInSlug,
}) {
  final brandName = _catalogBrandNameFromId(brandId);
  final tokens = <String>[];
  switch (availableInSlug.trim().toLowerCase()) {
    case 'yalta':
      tokens.add('Ялта');
      break;
    case 'simferopol':
      tokens.add('Симферополь');
      break;
  }
  if (categorySlug.trim().toLowerCase() == 'brooches') {
    tokens.add('брошь');
  }
  switch (typeSlug.trim().toLowerCase()) {
    case 'pendant':
      tokens.add('кулон');
      break;
    case 'choker':
      tokens.add('чокер');
      break;
  }
  if (tokens.isEmpty) return brandName;
  return [
    ...?(brandName == null ? null : [brandName]),
    ...tokens,
  ].join(' ');
}

class GlameApp extends ConsumerWidget {
  const GlameApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      debugShowCheckedModeBanner: false,
      title: 'GLAME.JEWELRY',
      theme: buildGlameTheme(),
      routerConfig: router,
    );
  }
}

List<String> _csvQueryValues(String? value) {
  if (value == null || value.trim().isEmpty) return const <String>[];
  return value
      .split(',')
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}
