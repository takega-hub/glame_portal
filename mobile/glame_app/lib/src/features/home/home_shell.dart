import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/network/asset_url.dart';
import '../../core/theme/glame_theme.dart';
import '../../core/widgets/glame_auth_gate.dart';
import '../auth/auth_controller.dart';
import '../cart/cart_screen.dart';
import '../catalog/catalog_screen.dart';
import '../customer/customer_cabinet_providers.dart';
import '../customer/stylist_entry.dart';
import '../looks/looks_screen.dart';
import '../service/how_to_buy_screen.dart';
import '../stores/stores_screen.dart';
import '../wishlist/wishlist_screen.dart';
import 'home_screen.dart';

class HomeShell extends ConsumerStatefulWidget {
  final int initialTab;
  final String? initialCategory;
  final String? initialSearch;
  final String? initialLookFilter;

  const HomeShell({
    super.key,
    this.initialTab = 0,
    this.initialCategory,
    this.initialSearch,
    this.initialLookFilter,
  });

  @override
  ConsumerState<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends ConsumerState<HomeShell> {
  final _scaffoldKey = GlobalKey<ScaffoldState>();
  int index = 0;
  String? catalogCategory;
  String? catalogSearch;
  String? lookFilter;

  @override
  void initState() {
    super.initState();
    index = widget.initialTab.clamp(0, 11);
    catalogCategory = _normalizeCategory(widget.initialCategory);
    catalogSearch = _normalizeSearch(widget.initialSearch);
    lookFilter = _normalizeLookFilter(widget.initialLookFilter);
  }

  @override
  void didUpdateWidget(covariant HomeShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.initialTab != widget.initialTab) {
      setState(() => index = widget.initialTab.clamp(0, 11));
    }
    if (oldWidget.initialCategory != widget.initialCategory) {
      setState(
        () => catalogCategory = _normalizeCategory(widget.initialCategory),
      );
    }
    if (oldWidget.initialSearch != widget.initialSearch) {
      setState(() => catalogSearch = _normalizeSearch(widget.initialSearch));
    }
    if (oldWidget.initialLookFilter != widget.initialLookFilter) {
      setState(
        () => lookFilter = _normalizeLookFilter(widget.initialLookFilter),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final controller = ref.read(authControllerProvider.notifier);
    final isLoggedIn = auth.user != null;
    final width = MediaQuery.of(context).size.width;
    final isDesktop = width >= 900;
    final isHeroHome = index == 0;

    final page = _buildSectionPage(
      context: context,
      index: index,
      isLoggedIn: isLoggedIn,
      email: auth.user?.email,
      onLogout: controller.logout,
    );

    return Scaffold(
      key: _scaffoldKey,
      drawer: _GlameDrawer(
        selectedIndex: index,
        onSelected: (i) {
          Navigator.of(context).pop();
          setState(() {
            index = i;
            catalogCategory = null;
            catalogSearch = null;
          });
        },
        isLoggedIn: isLoggedIn,
        onLogin: () {
          Navigator.of(context).pop();
          context.go('/login?next=${Uri.encodeComponent('/home?tab=4')}');
        },
        onLogout: () async {
          Navigator.of(context).pop();
          await controller.logout();
          setState(() => index = 0);
        },
      ),
      body: isHeroHome
          ? Stack(
              children: [
                Positioned.fill(child: page),
                _HeroTransparentTopBar(
                  onHomeTap: () => setState(() => index = 0),
                  onMenuTap: () => _scaffoldKey.currentState?.openDrawer(),
                  onCartTap: () => setState(() {
                    index = 11;
                    catalogCategory = null;
                    catalogSearch = null;
                    lookFilter = null;
                  }),
                  onSearchTap: () => setState(() {
                    index = 1;
                    catalogCategory = null;
                    catalogSearch = null;
                    lookFilter = null;
                  }),
                ),
              ],
            )
          : Column(
              children: [
                _GlameHeader(
                  selectedIndex: index,
                  isDesktop: isDesktop,
                  onSelected: (i) => setState(() {
                    index = i;
                    catalogCategory = null;
                    catalogSearch = null;
                    lookFilter = null;
                  }),
                ),
                Expanded(child: page),
              ],
            ),
      bottomNavigationBar: isDesktop
          ? null
          : _GlameBottomBar(
              selectedIndex: index,
              onSelected: (i) => setState(() {
                index = i;
                catalogCategory = null;
                catalogSearch = null;
                lookFilter = null;
              }),
            ),
    );
  }

  Widget _buildSectionPage({
    required BuildContext context,
    required int index,
    required bool isLoggedIn,
    required String? email,
    required Future<void> Function() onLogout,
  }) {
    if (index == 0) return const HomeScreen();
    if (index == 1) {
      return CatalogScreen(
        initialCategory: catalogCategory,
        initialSearch: catalogSearch,
      );
    }
    if (index == 2) return const WishlistScreen();
    if (index == 3) {
      return const SelectionMethodScreen(showAppBar: false);
    }
    if (index == 11) {
      return isLoggedIn
          ? const CartScreen(showAppBar: false)
          : _LoginRequired(
              title: 'Корзина',
              subtitle: 'Войдите, чтобы оформить заказ',
              onLogin: () => context.go(
                '/login?next=${Uri.encodeComponent('/home?tab=11')}',
              ),
            );
    }
    if (index == 4) {
      return isLoggedIn
          ? _Profile(email: email, onLogout: onLogout)
          : _LoginRequired(
              title: 'Профиль',
              subtitle: 'Войдите, чтобы открыть личный кабинет',
              onLogin: () => context.go(
                '/login?next=${Uri.encodeComponent('/home?tab=4')}',
              ),
            );
    }
    if (index == 5) return LooksScreen(initialFilter: lookFilter);
    if (index == 6) {
      return const CatalogScreen(title: 'НОВИНКИ', initialCategory: 'NEW');
    }
    if (index == 7) return const CatalogScreen(title: 'КОЛЛЕКЦИИ');
    if (index == 8) {
      return const _StaticInfoScreen(
        title: 'Сертификат',
        body:
            'Подарочный сертификат GLAME — аккуратный способ подарить выбор. Номинал и условия использования уточняются в магазинах и у консультантов.',
      );
    }
    if (index == 9) {
      return const _StaticInfoScreen(
        title: 'Сервис',
        body:
            'Мы помогаем подобрать украшение, оформить заказ, уточнить наличие и условия ухода. Гарантия на украшения GLAME действует 30 дней с момента покупки.',
      );
    }
    if (index == 10) return const StoresScreen(showAppBar: false);
    return const HomeScreen();
  }

  static String? _normalizeCategory(String? category) {
    final next = (category ?? '').trim();
    return next.isEmpty ? null : next;
  }

  static String? _normalizeSearch(String? search) {
    final next = (search ?? '').trim();
    return next.isEmpty ? null : next;
  }

  static String? _normalizeLookFilter(String? filter) {
    final next = (filter ?? '').trim();
    return next.isEmpty ? null : next;
  }
}

class _GlameHeader extends StatelessWidget {
  final int selectedIndex;
  final bool isDesktop;
  final ValueChanged<int> onSelected;

  const _GlameHeader({
    required this.selectedIndex,
    required this.isDesktop,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    final height = isDesktop ? 96.0 : 74.0;
    return Builder(
      builder: (context) => GlameTopAppBar(
        height: height,
        onMenuPressed: () => Scaffold.of(context).openDrawer(),
        onLogoPressed: () => onSelected(0),
        onCartPressed: () => onSelected(11),
        onSearchPressed: () => onSelected(1),
      ),
    );
  }
}

class _HeroTransparentTopBar extends StatelessWidget {
  final VoidCallback onHomeTap;
  final VoidCallback onMenuTap;
  final VoidCallback? onCartTap;
  final VoidCallback? onSearchTap;

  const _HeroTransparentTopBar({
    required this.onHomeTap,
    required this.onMenuTap,
    this.onCartTap,
    this.onSearchTap,
  });

  @override
  Widget build(BuildContext context) {
    final topOffset =
        MediaQuery.of(context).padding.top + GlameUi.heroTopOffset;

    return Positioned(
      top: topOffset,
      left: GlameUi.pagePadding,
      right: GlameUi.pagePadding,
      child: SizedBox(
        height: GlameUi.heroTopBarHeight,
        child: Stack(
          alignment: Alignment.center,
          children: [
            Positioned(
              left: 0,
              child: _HeroTopBarIconButton(
                tooltip: 'Меню',
                icon: Icons.menu,
                onPressed: onMenuTap,
              ),
            ),
            Center(
              child: InkWell(
                onTap: onHomeTap,
                child: Image.asset(
                  GlameAssets.logoSilver,
                  height: 34,
                  fit: BoxFit.contain,
                ),
              ),
            ),
            Positioned(
              right: 0,
              child: Row(
                children: [
                  _HeroTopBarIconButton(
                    tooltip: 'Корзина',
                    icon: Icons.shopping_bag_outlined,
                    onPressed: onCartTap,
                  ),
                  const SizedBox(width: 4),
                  _HeroTopBarIconButton(
                    tooltip: 'Поиск',
                    icon: Icons.search,
                    onPressed: onSearchTap,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HeroTopBarIconButton extends StatelessWidget {
  final String tooltip;
  final IconData icon;
  final VoidCallback? onPressed;

  const _HeroTopBarIconButton({
    required this.tooltip,
    required this.icon,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 44,
      height: 44,
      child: IconButton(
        tooltip: tooltip,
        onPressed: onPressed,
        splashRadius: 22,
        style: IconButton.styleFrom(
          backgroundColor: Colors.transparent,
          foregroundColor: GlameColors.surface2,
          shape: const RoundedRectangleBorder(),
        ),
        icon: Icon(icon, size: 24),
      ),
    );
  }
}

class _GlameBottomBar extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  const _GlameBottomBar({
    required this.selectedIndex,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: GlameColors.surface2,
        border: Border(top: BorderSide(color: GlameColors.borderGray)),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: GlameUi.mobileBottomNavHeight,
          child: Row(
            children: [
              _BottomNavHome(
                selected: selectedIndex == 0,
                onTap: () => onSelected(0),
              ),
              _BottomNavItem(
                label: 'Украшения',
                selected: selectedIndex == 1,
                onTap: () => onSelected(1),
              ),
              _BottomNavItem(
                label: 'Мой стиль',
                selected: selectedIndex == 2,
                onTap: () => onSelected(2),
              ),
              _BottomNavItem(
                label: 'Подбор',
                selected: selectedIndex == 3,
                onTap: () => onSelected(3),
              ),
              _BottomNavItem(
                label: 'Профиль',
                selected: selectedIndex == 4,
                onTap: () => onSelected(4),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BottomNavHome extends StatelessWidget {
  final bool selected;
  final VoidCallback onTap;

  const _BottomNavHome({required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 64,
      child: InkWell(
        onTap: onTap,
        child: Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: Opacity(
              opacity: selected ? 1 : 0.64,
              child: Image.asset(GlameAssets.sign, fit: BoxFit.contain),
            ),
          ),
        ),
      ),
    );
  }
}

class _BottomNavItem extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _BottomNavItem({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        child: Center(
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 12,
              fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
              color: selected
                  ? GlameColors.textPrimary
                  : GlameColors.textSecondary,
            ),
          ),
        ),
      ),
    );
  }
}

class _GlameDrawer extends StatelessWidget {
  final int selectedIndex;
  final bool isLoggedIn;
  final ValueChanged<int> onSelected;
  final VoidCallback onLogin;
  final Future<void> Function() onLogout;

  const _GlameDrawer({
    required this.selectedIndex,
    required this.isLoggedIn,
    required this.onSelected,
    required this.onLogin,
    required this.onLogout,
  });

  @override
  Widget build(BuildContext context) {
    return Drawer(
      backgroundColor: GlameColors.nearBlack,
      shape: const RoundedRectangleBorder(),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 28, 24, 24),
          child: ListView(
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: Image.asset(
                  GlameAssets.logoSilver,
                  height: 46,
                  fit: BoxFit.contain,
                ),
              ),
              const SizedBox(height: 28),
              const _DrawerSectionLabel('Навигация'),
              _DrawerItem('Главная', 0, selectedIndex, onSelected),
              _DrawerItem('Украшения', 1, selectedIndex, onSelected),
              _DrawerItem('Мой стиль', 2, selectedIndex, onSelected),
              _DrawerItem('Подбор', 3, selectedIndex, onSelected),
              _DrawerItem('Профиль', 4, selectedIndex, onSelected),
              const SizedBox(height: 20),
              const _DrawerSectionLabel('Витрина'),
              _DrawerItem('Новинки', 6, selectedIndex, onSelected),
              _DrawerItem('Коллекции', 7, selectedIndex, onSelected),
              _DrawerRouteItem(
                label: 'Бренды',
                onTap: () {
                  Navigator.of(context).pop();
                  context.go('/brands');
                },
              ),
              _DrawerItem('Пространства', 10, selectedIndex, onSelected),
              _DrawerItem('Сервис', 9, selectedIndex, onSelected),
              _DrawerItem('Сертификат', 8, selectedIndex, onSelected),
              const SizedBox(height: 24),
              Container(height: 1, color: GlameColors.borderGray),
              const SizedBox(height: 18),
              const _DrawerSectionLabel('Действия'),
              _DrawerItem('Корзина', 11, selectedIndex, onSelected),
              _DrawerRouteItem(
                label: isLoggedIn ? 'Выйти' : 'Войти',
                onTap: isLoggedIn ? onLogout : onLogin,
              ),
              const SizedBox(height: 40),
              Image.asset(
                GlameAssets.logoSilver,
                height: 22,
                alignment: Alignment.centerLeft,
              ),
              const SizedBox(height: 8),
              const Text(
                'Новости и коллекции в наших соцсетях',
                style: TextStyle(
                  fontSize: 14,
                  height: 1.35,
                  color: GlameColors.coldLightGray,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DrawerSectionLabel extends StatelessWidget {
  final String label;

  const _DrawerSectionLabel(this.label);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        label.toUpperCase(),
        style: const TextStyle(
          fontSize: 10,
          letterSpacing: 1.4,
          color: GlameColors.steelGray,
        ),
      ),
    );
  }
}

class _DrawerItem extends StatelessWidget {
  final String label;
  final int index;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  const _DrawerItem(
    this.label,
    this.index,
    this.selectedIndex,
    this.onSelected,
  );

  @override
  Widget build(BuildContext context) {
    final selected = selectedIndex == index;
    return InkWell(
      onTap: () => onSelected(index),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 24,
            height: 1.05,
            color: selected
                ? GlameColors.whiteGlame
                : GlameColors.coldLightGray,
          ),
        ),
      ),
    );
  }
}

class _DrawerRouteItem extends StatelessWidget {
  final String label;
  final VoidCallback onTap;

  const _DrawerRouteItem({required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: const TextStyle(
                  fontSize: 24,
                  height: 1.05,
                  color: GlameColors.coldLightGray,
                ),
              ),
            ),
            const Icon(
              Icons.chevron_right,
              size: 18,
              color: GlameColors.steelGray,
            ),
          ],
        ),
      ),
    );
  }
}

class _StaticInfoScreen extends StatelessWidget {
  final String title;
  final String body;

  const _StaticInfoScreen({required this.title, required this.body});

  @override
  Widget build(BuildContext context) {
    return GlamePage(
      safeTop: false,
      padding: EdgeInsets.zero,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
        children: [
          GlameSectionHeader(title: title, subtitle: body),
          const SizedBox(height: 28),
          GlamePanel(
            padding: const EdgeInsets.fromLTRB(20, 28, 20, 28),
            color: GlameColors.surface,
            child: Center(
              child: Image.asset(GlameAssets.logoBlack, height: 72),
            ),
          ),
        ],
      ),
    );
  }
}

class _Profile extends ConsumerWidget {
  final String? email;
  final Future<void> Function() onLogout;

  const _Profile({required this.email, required this.onLogout});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profileAsync = ref.watch(customerProfileProvider);
    final loyaltyAsync = ref.watch(customerLoyaltyProvider);
    final ordersAsync = ref.watch(customerOrdersProvider);
    final historyAsync = ref.watch(customerPurchaseHistoryProvider);
    final savedLooksAsync = ref.watch(customerSavedLooksProvider);

    return Theme(
      data: Theme.of(context).copyWith(
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            backgroundColor: GlameColors.whiteGlame,
            foregroundColor: GlameColors.nearBlack,
            shape: const RoundedRectangleBorder(),
          ),
        ),
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
            foregroundColor: GlameColors.whiteGlame,
            side: const BorderSide(color: GlameColors.borderGray),
            shape: const RoundedRectangleBorder(),
          ),
        ),
        textButtonTheme: TextButtonThemeData(
          style: TextButton.styleFrom(
            foregroundColor: GlameColors.whiteGlame,
            shape: const RoundedRectangleBorder(),
          ),
        ),
      ),
      child: GlamePage(
        dark: true,
        safeTop: false,
        padding: EdgeInsets.zero,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 28),
          children: [
            const GlameSectionHeader(
              title: 'ЛИЧНЫЙ\nКАБИНЕТ',
              subtitle:
                  'Покупки, бонусы, сохраненные образы и связь со стилистом',
              dark: true,
            ),
            const SizedBox(height: 24),
            profileAsync.when(
              data: (profile) {
                final fullName = (profile['full_name'] as String?)?.trim();
                final phone = (profile['phone'] as String?)?.trim();
                final points =
                    (profile['loyalty_points'] as num?)?.toInt() ?? 0;
                final totalPurchases =
                    (profile['total_purchases'] as num?)?.toInt() ?? 0;
                final totalSpent = (profile['total_spent'] as num?) ?? 0;
                final averageCheck = (profile['average_check'] as num?) ?? 0;
                final lastPurchaseDate =
                    (profile['last_purchase_date'] as String?)?.trim();
                final preferredDelivery = profile['preferred_delivery'] is Map
                    ? Map<String, dynamic>.from(
                        profile['preferred_delivery'] as Map,
                      )
                    : <String, dynamic>{};
                final displayName = fullName?.isNotEmpty == true
                    ? fullName!
                    : 'Покупатель GLAME';
                final contact = phone?.isNotEmpty == true
                    ? phone!
                    : (email ?? 'Без email');

                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    GlamePanel(
                      dark: true,
                      padding: const EdgeInsets.fromLTRB(18, 18, 18, 20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'ПРОФИЛЬ',
                            style: TextStyle(
                              fontSize: 11,
                              letterSpacing: 1.6,
                              color: GlameColors.steelGray,
                            ),
                          ),
                          const SizedBox(height: 10),
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      displayName,
                                      style: const TextStyle(
                                        fontSize: 30,
                                        height: 1.02,
                                        fontWeight: FontWeight.w400,
                                        color: GlameColors.whiteGlame,
                                      ),
                                    ),
                                    const SizedBox(height: 8),
                                    Text(
                                      contact,
                                      style: const TextStyle(
                                        fontSize: 14,
                                        color: GlameColors.coldLightGray,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  Text(
                                    '$points',
                                    style: const TextStyle(
                                      fontSize: 34,
                                      height: 0.95,
                                      color: GlameColors.whiteGlame,
                                    ),
                                  ),
                                  const SizedBox(height: 6),
                                  const Text(
                                    'БОНУСОВ',
                                    style: TextStyle(
                                      fontSize: 10,
                                      letterSpacing: 1.2,
                                      color: GlameColors.steelGray,
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                          const SizedBox(height: 18),
                          Container(
                            height: 1,
                            color: GlameColors.borderGray.withValues(
                              alpha: 0.7,
                            ),
                          ),
                          const SizedBox(height: 14),
                          Row(
                            children: [
                              Expanded(
                                child: _ProfileInlineStat(
                                  label: 'Покупки',
                                  value: '$totalPurchases',
                                ),
                              ),
                              Expanded(
                                child: _ProfileInlineStat(
                                  label: 'Сумма',
                                  value: _formatRub(totalSpent),
                                ),
                              ),
                              Expanded(
                                child: _ProfileInlineStat(
                                  label: 'Средний чек',
                                  value: _formatRub(averageCheck),
                                ),
                              ),
                            ],
                          ),
                          if (lastPurchaseDate != null &&
                              lastPurchaseDate.isNotEmpty) ...[
                            const SizedBox(height: 12),
                            Text(
                              'Последняя покупка: ${_formatIsoDate(lastPurchaseDate)}',
                              style: const TextStyle(
                                fontSize: 12,
                                color: GlameColors.coldLightGray,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                    const SizedBox(height: 18),
                    _ProfileMetricGrid(
                      children: [
                        _ProfileMetricCard(
                          title: 'Стилист GLAME',
                          value: 'Чат',
                          subtitle: 'Персональный подбор',
                          icon: Icons.support_agent_outlined,
                          onTap: () => showStylistContactSheet(
                            context,
                            source: 'profile_screen',
                            scenario: 'live_stylist',
                          ),
                        ),
                        _ProfileMetricCard(
                          title: 'Избранное',
                          value: 'Сохранить',
                          subtitle: 'Товары и образы',
                          icon: Icons.favorite_border,
                          onTap: () => context.go('/home?tab=2'),
                        ),
                        _ProfileMetricCard(
                          title: 'Доставка',
                          value: _deliveryShortLabel(preferredDelivery),
                          subtitle: _deliverySummary(preferredDelivery),
                          icon: Icons.local_shipping_outlined,
                          onTap: () => _editPreferredDelivery(
                            context: context,
                            ref: ref,
                            currentDelivery: preferredDelivery,
                          ),
                        ),
                        _ProfileMetricCard(
                          title: 'Корзина',
                          value: 'Заказы',
                          subtitle: 'Оформление и оплата',
                          icon: Icons.shopping_bag_outlined,
                          onTap: () => context.go('/home?tab=11'),
                        ),
                      ],
                    ),
                  ],
                );
              },
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: CircularProgressIndicator(color: GlameColors.whiteGlame),
              ),
              error: (_, _) => Text(
                email ?? 'Без email',
                style: const TextStyle(color: GlameColors.coldLightGray),
              ),
            ),
            const SizedBox(height: 20),
            loyaltyAsync.when(
              data: (loyalty) {
                final info = (loyalty['program_info'] is Map)
                    ? Map<String, dynamic>.from(loyalty['program_info'] as Map)
                    : <String, dynamic>{};
                final levelsRaw = info['levels'];
                final levels = levelsRaw is List
                    ? levelsRaw
                          .whereType<Map>()
                          .map((x) => Map<String, dynamic>.from(x))
                          .toList()
                    : <Map<String, dynamic>>[];

                final profile = profileAsync.maybeWhen(
                  data: (x) => x,
                  orElse: () => const <String, dynamic>{},
                );
                final purchases =
                    (profile['total_purchases'] as num?)?.toInt() ?? 0;
                final spent = (profile['total_spent'] as num?)?.toDouble() ?? 0;
                final progressRaw = loyalty['level_progress'];
                final progress = progressRaw is Map
                    ? _progressFromApi(Map<String, dynamic>.from(progressRaw))
                    : _resolveNextLevel(levels, purchases, spent);

                return Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: GlameColors.graphite.withValues(alpha: 0.72),
                    border: Border.all(color: GlameColors.borderGray),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const _ProfileSectionHeading(
                        eyebrow: 'LOYALTY',
                        title: 'Бонусная программа',
                      ),
                      const SizedBox(height: 14),
                      if (progress != null) ...[
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Expanded(
                              child: Text(
                                'До уровня "${progress.nextLevelName}"',
                                style: const TextStyle(
                                  fontSize: 17,
                                  color: GlameColors.whiteGlame,
                                ),
                              ),
                            ),
                            Text(
                              _formatRub(progress.remainingTotal),
                              style: const TextStyle(
                                fontSize: 17,
                                color: GlameColors.whiteGlame,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        LinearProgressIndicator(
                          value: progress.progress.clamp(0, 1),
                          minHeight: 4,
                          backgroundColor: GlameColors.nearBlack,
                          color: GlameColors.whiteGlame,
                        ),
                        const SizedBox(height: 12),
                      ],
                      if (levels.isNotEmpty)
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: levels
                              .map((lvl) => _buildLevelChip(lvl))
                              .toList(growable: false),
                        ),
                    ],
                  ),
                );
              },
              loading: () => const SizedBox.shrink(),
              error: (_, _) => const SizedBox.shrink(),
            ),
            const SizedBox(height: 24),
            const _ProfileSectionHeading(
              eyebrow: 'STYLE',
              title: 'Сохраненные образы',
            ),
            const SizedBox(height: 10),
            savedLooksAsync.when(
              data: (rows) {
                if (rows.isEmpty) {
                  return const _ProfileEmptyPanel(
                    text: 'Пока нет сохраненных образов',
                  );
                }
                return _buildSavedLooksCarousel(
                  context: context,
                  ref: ref,
                  rows: rows,
                );
              },
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: CircularProgressIndicator(color: GlameColors.whiteGlame),
              ),
              error: (_, _) => const Text(
                'Не удалось загрузить сохраненные образы',
                style: TextStyle(color: GlameColors.coldLightGray),
              ),
            ),
            const SizedBox(height: 24),
            const _ProfileSectionHeading(
              eyebrow: 'ORDERS',
              title: 'Мои заказы',
            ),
            const SizedBox(height: 10),
            ordersAsync.when(
              data: (rows) {
                if (rows.isEmpty) {
                  return const _ProfileEmptyPanel(text: 'Заказов пока нет');
                }
                return Column(
                  children: rows
                      .map((row) {
                        final orderId = (row['id'] as String?)?.trim() ?? '';
                        final orderStatus =
                            ((row['order_status'] ?? row['status']) as String?)
                                ?.trim() ??
                            'pending';
                        final amount =
                            (row['total_amount'] as num?)?.toInt() ?? 0;
                        final createdAt =
                            (row['created_at'] as String?)?.trim() ?? '';
                        final payment = row['payment'] is Map
                            ? Map<String, dynamic>.from(row['payment'] as Map)
                            : <String, dynamic>{};
                        final paymentId =
                            (payment['payment_id'] ?? payment['id'] as Object?)
                                ?.toString();
                        final paymentStatus = (payment['status'] as String?)
                            ?.trim();
                        final confirmationUrl =
                            (payment['confirmation_url'] as String?)?.trim();
                        final delivery = row['delivery'] is Map
                            ? Map<String, dynamic>.from(row['delivery'] as Map)
                            : <String, dynamic>{};
                        final canPay =
                            paymentStatus != null &&
                            paymentStatus != 'succeeded' &&
                            confirmationUrl != null &&
                            confirmationUrl.isNotEmpty;
                        final canDelete =
                            (paymentStatus ?? 'pending') != 'succeeded' ||
                            orderStatus == 'shipped';

                        return Container(
                          width: double.infinity,
                          margin: const EdgeInsets.only(bottom: 10),
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: GlameColors.graphite,
                            border: Border.all(color: GlameColors.borderGray),
                            borderRadius: BorderRadius.zero,
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Заказ #${orderId.length > 8 ? orderId.substring(0, 8) : orderId}',
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                  color: GlameColors.whiteGlame,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                '${_formatIsoDate(createdAt)} · ${_formatRub(amount / 100)}',
                                style: const TextStyle(
                                  color: GlameColors.coldLightGray,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                'Статус заказа: ${_orderStatusLabel(orderStatus)}',
                                style: const TextStyle(
                                  color: GlameColors.coldLightGray,
                                ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                'Статус оплаты: ${_paymentStatusLabel(paymentStatus)}',
                                style: const TextStyle(
                                  color: GlameColors.whiteGlame,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                _deliverySummary(delivery),
                                style: const TextStyle(
                                  color: GlameColors.coldLightGray,
                                ),
                              ),
                              if (paymentId != null &&
                                  paymentId.isNotEmpty) ...[
                                const SizedBox(height: 10),
                                Wrap(
                                  spacing: 8,
                                  runSpacing: 8,
                                  children: [
                                    OutlinedButton(
                                      onPressed: () async {
                                        final messenger = ScaffoldMessenger.of(
                                          context,
                                        );
                                        try {
                                          await ref
                                              .read(customerCabinetApiProvider)
                                              .refreshPayment(paymentId);
                                          ref.invalidate(
                                            customerOrdersProvider,
                                          );
                                          messenger.showSnackBar(
                                            const SnackBar(
                                              content: Text(
                                                'Статус оплаты обновлен',
                                              ),
                                            ),
                                          );
                                        } catch (_) {
                                          messenger.showSnackBar(
                                            const SnackBar(
                                              content: Text(
                                                'Не удалось обновить статус оплаты',
                                              ),
                                            ),
                                          );
                                        }
                                      },
                                      child: const Text('Обновить статус'),
                                    ),
                                    if (canPay)
                                      FilledButton(
                                        onPressed: () async {
                                          final uri = Uri.tryParse(
                                            confirmationUrl,
                                          );
                                          if (uri == null) return;
                                          await launchUrl(
                                            uri,
                                            mode:
                                                LaunchMode.externalApplication,
                                          );
                                        },
                                        child: const Text('Оплатить'),
                                      ),
                                  ],
                                ),
                              ],
                              const SizedBox(height: 8),
                              Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  if (canDelete)
                                    OutlinedButton(
                                      onPressed: () => _confirmDeleteOrder(
                                        context: context,
                                        ref: ref,
                                        orderId: orderId,
                                      ),
                                      child: const Text('Удалить заказ'),
                                    ),
                                ],
                              ),
                            ],
                          ),
                        );
                      })
                      .toList(growable: false),
                );
              },
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: CircularProgressIndicator(color: GlameColors.whiteGlame),
              ),
              error: (_, _) => const Text(
                'Не удалось загрузить заказы',
                style: TextStyle(color: GlameColors.coldLightGray),
              ),
            ),
            const SizedBox(height: 24),
            const _ProfileSectionHeading(
              eyebrow: 'HISTORY',
              title: 'История покупок',
            ),
            const SizedBox(height: 10),
            historyAsync.when(
              data: (rows) {
                if (rows.isEmpty) {
                  return const _ProfileEmptyPanel(text: 'Покупок пока нет');
                }
                return Column(
                  children: rows
                      .map((row) {
                        final name = (row['product_name'] as String?)?.trim();
                        final date =
                            (row['purchase_date'] as String?)?.trim() ?? '';
                        final amount = (row['total_amount'] as num?) ?? 0;
                        final quantity =
                            (row['quantity'] as num?)?.toInt() ?? 1;
                        return Container(
                          width: double.infinity,
                          margin: const EdgeInsets.only(bottom: 10),
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: GlameColors.graphite,
                            border: Border.all(color: GlameColors.borderGray),
                            borderRadius: BorderRadius.zero,
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                name?.isNotEmpty == true ? name! : 'Товар',
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                  color: GlameColors.whiteGlame,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                '${_formatIsoDate(date)} · $quantity шт.',
                                style: const TextStyle(
                                  color: GlameColors.coldLightGray,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                _formatRub(amount),
                                style: const TextStyle(
                                  color: GlameColors.whiteGlame,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                        );
                      })
                      .toList(growable: false),
                );
              },
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: CircularProgressIndicator(color: GlameColors.whiteGlame),
              ),
              error: (_, _) => const Text(
                'Не удалось загрузить историю покупок',
                style: TextStyle(color: GlameColors.coldLightGray),
              ),
            ),
            const SizedBox(height: 32),
            OutlinedButton(onPressed: onLogout, child: const Text('Выйти')),
          ],
        ),
      ),
    );
  }

  Widget _buildSavedLooksCarousel({
    required BuildContext context,
    required WidgetRef ref,
    required List<Map<String, dynamic>> rows,
  }) {
    final visibleRows = rows.take(8).toList(growable: false);
    return SizedBox(
      height: 180,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: visibleRows.length,
        separatorBuilder: (_, _) => const SizedBox(width: 10),
        itemBuilder: (context, index) {
          final row = visibleRows[index];
          final name = (row['look_name'] as String?)?.trim();
          final imageUrl = resolveAssetUrl(row['look_image_url']);
          final style = (row['look_style'] as String?)?.trim();
          final mood = (row['look_mood'] as String?)?.trim();
          final notes = (row['notes'] as String?)?.trim();
          final createdAt = (row['created_at'] as String?)?.trim() ?? '';
          final subtitleParts = <String>[
            if (style != null && style.isNotEmpty) style,
            if (mood != null && mood.isNotEmpty) mood,
          ];
          final lookId = (row['look_id'] as String?)?.trim() ?? '';
          final savedLookId = (row['id'] as String?)?.trim() ?? '';

          return InkWell(
            onTap: lookId.isEmpty ? null : () => context.push('/look/$lookId'),
            borderRadius: BorderRadius.zero,
            child: Container(
              width: 236,
              decoration: BoxDecoration(
                color: GlameColors.graphite,
                border: Border.all(color: GlameColors.borderGray),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    height: 92,
                    width: double.infinity,
                    child: imageUrl == null
                        ? Container(color: GlameColors.nearBlack)
                        : Image.network(imageUrl, fit: BoxFit.cover),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name?.isNotEmpty == true ? name! : 'Образ',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            color: GlameColors.whiteGlame,
                          ),
                        ),
                        if (subtitleParts.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text(
                            subtitleParts.join(' · '),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: GlameColors.coldLightGray,
                              fontSize: 12,
                            ),
                          ),
                        ],
                        if (notes != null && notes.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text(
                            notes,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: GlameColors.coldLightGray,
                              fontSize: 12,
                            ),
                          ),
                        ],
                        const SizedBox(height: 4),
                        Text(
                          _formatIsoDate(createdAt),
                          style: const TextStyle(
                            color: GlameColors.steelGray,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Spacer(),
                  Container(
                    height: 1,
                    color: GlameColors.borderGray.withValues(alpha: 0.55),
                  ),
                  SizedBox(
                    height: 38,
                    child: Row(
                      children: [
                        const SizedBox(width: 12),
                        const Expanded(
                          child: Text(
                            'СМОТРЕТЬ',
                            style: TextStyle(
                              fontSize: 10,
                              letterSpacing: 1.1,
                              color: GlameColors.whiteGlame,
                            ),
                          ),
                        ),
                        IconButton(
                          tooltip: 'Удалить из сохраненных',
                          onPressed: savedLookId.isEmpty
                              ? null
                              : () => _confirmDeleteSavedLook(
                                  context: context,
                                  ref: ref,
                                  savedLookId: savedLookId,
                                ),
                          icon: const Icon(
                            Icons.close,
                            size: 18,
                            color: GlameColors.coldLightGray,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildLevelChip(Map<String, dynamic> lvl) {
    final name = (lvl['name'] as String?)?.trim();
    final condition = (lvl['condition'] as String?)?.trim();
    final minPurchases = (lvl['min_purchases'] as num?)?.toInt();
    final minTotal = (lvl['min_total'] as num?)?.toDouble();
    final maxTotal = (lvl['max_total'] as num?)?.toDouble();
    final parts = <String>[];
    if (minPurchases != null && minPurchases > 0) {
      parts.add('от $minPurchases покупок');
    }
    if (condition != null && condition.isNotEmpty) {
      parts.add(condition);
    } else if (minTotal != null && minTotal > 0) {
      if (maxTotal != null) {
        parts.add('${_formatRub(minTotal)} - ${_formatRub(maxTotal)}');
      } else {
        parts.add('от ${_formatRub(minTotal)}');
      }
    }
    final subtitle = parts.join(' · ');
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: GlameColors.graphite,
        border: Border.all(color: GlameColors.borderGray),
        borderRadius: BorderRadius.zero,
      ),
      child: Text(
        subtitle.isEmpty
            ? (name?.isNotEmpty == true ? name! : 'Уровень')
            : '${name ?? 'Уровень'}: $subtitle',
        style: const TextStyle(fontSize: 12, color: GlameColors.coldLightGray),
      ),
    );
  }

  Future<void> _editPreferredDelivery({
    required BuildContext context,
    required WidgetRef ref,
    required Map<String, dynamic> currentDelivery,
  }) async {
    String method =
        (currentDelivery['method'] ?? currentDelivery['type'] ?? 'pickup')
            .toString()
            .trim()
            .toLowerCase();
    if (method == 'cdek') method = 'cdek_pvz';
    if (method != 'pickup' && method != 'cdek_pvz' && method != 'pvz') {
      method = 'pickup';
    }

    final storeCtrl = TextEditingController(
      text: (currentDelivery['store_name'] ?? '').toString(),
    );
    final cityCtrl = TextEditingController(
      text: (currentDelivery['city'] ?? currentDelivery['city_name'] ?? '')
          .toString(),
    );
    final pvzCtrl = TextEditingController(
      text: (currentDelivery['pvz_name'] ?? currentDelivery['pvz_code'] ?? '')
          .toString(),
    );
    final addressCtrl = TextEditingController(
      text: (currentDelivery['address'] ?? '').toString(),
    );
    final commentCtrl = TextEditingController(
      text: (currentDelivery['comment'] ?? '').toString(),
    );

    final shouldSave = await showDialog<bool>(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, modalSetState) => AlertDialog(
            title: const Text('Параметры доставки'),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SegmentedButton<String>(
                    segments: const [
                      ButtonSegment(
                        value: 'pickup',
                        label: Text('Самовывоз'),
                        icon: Icon(Icons.storefront),
                      ),
                      ButtonSegment(
                        value: 'cdek_pvz',
                        label: Text('СДЭК'),
                        icon: Icon(Icons.local_shipping_outlined),
                      ),
                    ],
                    selected: {method == 'pvz' ? 'cdek_pvz' : method},
                    onSelectionChanged: (value) {
                      modalSetState(() => method = value.first);
                    },
                  ),
                  const SizedBox(height: 12),
                  if (method == 'pickup') ...[
                    TextField(
                      controller: storeCtrl,
                      decoration: const InputDecoration(
                        labelText: 'Магазин самовывоза',
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: cityCtrl,
                      decoration: const InputDecoration(labelText: 'Город'),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: addressCtrl,
                      decoration: const InputDecoration(labelText: 'Адрес'),
                    ),
                  ] else ...[
                    TextField(
                      controller: cityCtrl,
                      decoration: const InputDecoration(labelText: 'Город'),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: pvzCtrl,
                      decoration: const InputDecoration(
                        labelText: 'ПВЗ / пункт',
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: addressCtrl,
                      decoration: const InputDecoration(labelText: 'Адрес ПВЗ'),
                    ),
                  ],
                  const SizedBox(height: 8),
                  TextField(
                    controller: commentCtrl,
                    decoration: const InputDecoration(labelText: 'Комментарий'),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(false),
                child: const Text('Отмена'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(ctx).pop(true),
                child: const Text('Сохранить'),
              ),
            ],
          ),
        );
      },
    );

    if (shouldSave != true) {
      storeCtrl.dispose();
      cityCtrl.dispose();
      pvzCtrl.dispose();
      addressCtrl.dispose();
      commentCtrl.dispose();
      return;
    }

    final delivery = <String, dynamic>{
      ...currentDelivery,
      'method': method == 'pickup' ? 'pickup' : 'cdek',
      'type': method == 'pickup' ? 'pickup' : 'pvz',
      'city': cityCtrl.text.trim(),
      'address': addressCtrl.text.trim(),
      'comment': commentCtrl.text.trim(),
    };
    if (method == 'pickup') {
      delivery['store_name'] = storeCtrl.text.trim();
    } else {
      delivery['pvz_name'] = pvzCtrl.text.trim();
    }

    if (!context.mounted) return;
    try {
      await ref
          .read(customerCabinetApiProvider)
          .updateProfile(preferredDelivery: delivery);
      ref.invalidate(customerProfileProvider);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Параметры доставки сохранены')),
      );
    } catch (_) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Не удалось сохранить доставку')),
      );
    } finally {
      storeCtrl.dispose();
      cityCtrl.dispose();
      pvzCtrl.dispose();
      addressCtrl.dispose();
      commentCtrl.dispose();
    }
  }

  Future<void> _confirmDeleteOrder({
    required BuildContext context,
    required WidgetRef ref,
    required String orderId,
  }) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Удалить заказ?'),
        content: const Text(
          'Заказ и связанные данные будут удалены, резерв будет снят.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Удалить'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    if (!context.mounted) return;
    try {
      await ref.read(customerCabinetApiProvider).deleteOrder(orderId);
      ref.invalidate(customerOrdersProvider);
      if (!context.mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Заказ удален')));
    } catch (_) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Не удалось удалить заказ')));
    }
  }

  Future<void> _confirmDeleteSavedLook({
    required BuildContext context,
    required WidgetRef ref,
    required String savedLookId,
  }) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Удалить образ?'),
        content: const Text(
          'Образ будет удален из сохраненных в личном кабинете.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Удалить'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    if (!context.mounted) return;
    try {
      await ref.read(customerCabinetApiProvider).deleteSavedLook(savedLookId);
      ref.invalidate(customerSavedLooksProvider);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Образ удален из сохраненных')),
      );
    } catch (_) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Не удалось удалить образ')));
    }
  }
}

class _ProfileInlineStat extends StatelessWidget {
  final String label;
  final String value;

  const _ProfileInlineStat({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label.toUpperCase(),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            fontSize: 10,
            letterSpacing: 1.1,
            color: GlameColors.steelGray,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 15, color: GlameColors.whiteGlame),
        ),
      ],
    );
  }
}

class _ProfileSectionHeading extends StatelessWidget {
  final String eyebrow;
  final String title;

  const _ProfileSectionHeading({required this.eyebrow, required this.title});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                eyebrow,
                style: const TextStyle(
                  fontSize: 10,
                  letterSpacing: 1.4,
                  color: GlameColors.steelGray,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                title,
                style: const TextStyle(
                  fontSize: 22,
                  height: 1.05,
                  color: GlameColors.whiteGlame,
                ),
              ),
            ],
          ),
        ),
        Container(width: 42, height: 1, color: GlameColors.borderGray),
      ],
    );
  }
}

class _ProfileEmptyPanel extends StatelessWidget {
  final String text;

  const _ProfileEmptyPanel({required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 18),
      decoration: BoxDecoration(
        color: GlameColors.graphite.withValues(alpha: 0.48),
        border: Border.all(color: GlameColors.borderGray),
      ),
      child: Text(
        text,
        style: const TextStyle(color: GlameColors.coldLightGray),
      ),
    );
  }
}

class _ProfileMetricGrid extends StatelessWidget {
  final List<Widget> children;

  const _ProfileMetricGrid({required this.children});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.maxWidth >= 560 ? 4 : 2;
        final gap = 10.0;
        final width = (constraints.maxWidth - gap * (columns - 1)) / columns;
        return Wrap(
          spacing: gap,
          runSpacing: gap,
          children: children
              .map((child) => SizedBox(width: width, child: child))
              .toList(growable: false),
        );
      },
    );
  }
}

class _ProfileMetricCard extends StatelessWidget {
  final String title;
  final String value;
  final String subtitle;
  final IconData icon;
  final VoidCallback? onTap;

  const _ProfileMetricCard({
    required this.title,
    required this.value,
    required this.subtitle,
    required this.icon,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.zero,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: GlameColors.graphite,
          border: Border.all(color: GlameColors.borderGray),
          borderRadius: BorderRadius.zero,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 18, color: GlameColors.coldLightGray),
                const Spacer(),
                if (onTap != null)
                  const Icon(
                    Icons.chevron_right,
                    size: 18,
                    color: GlameColors.steelGray,
                  ),
              ],
            ),
            const SizedBox(height: 14),
            Text(
              title.toUpperCase(),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 10,
                letterSpacing: 1,
                color: GlameColors.steelGray,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w500,
                color: GlameColors.whiteGlame,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              subtitle,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 12,
                height: 1.25,
                color: GlameColors.coldLightGray,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NextLevelProgress {
  final String nextLevelName;
  final double remainingTotal;
  final double progress;

  const _NextLevelProgress({
    required this.nextLevelName,
    required this.remainingTotal,
    required this.progress,
  });
}

_NextLevelProgress? _progressFromApi(Map<String, dynamic> progress) {
  final nextLevelRaw = progress['next_level'];
  if (nextLevelRaw is! Map) return null;

  final nextLevel = Map<String, dynamic>.from(nextLevelRaw);
  final remainingTotal = (progress['remaining_total'] as num?)?.toDouble() ?? 0;
  return _NextLevelProgress(
    nextLevelName: (nextLevel['name'] as String?) ?? 'Следующий уровень',
    remainingTotal: remainingTotal,
    progress: (progress['progress'] as num?)?.toDouble() ?? 0,
  );
}

_NextLevelProgress? _resolveNextLevel(
  List<Map<String, dynamic>> levels,
  int currentPurchases,
  double currentTotalRub,
) {
  if (levels.isEmpty) return null;

  levels.sort((a, b) {
    final at = (a['min_total'] as num?)?.toDouble() ?? 0;
    final bt = (b['min_total'] as num?)?.toDouble() ?? 0;
    return at.compareTo(bt);
  });

  for (final level in levels) {
    final reqPurchases = (level['min_purchases'] as num?)?.toInt() ?? 0;
    final reqTotal = (level['min_total'] as num?)?.toDouble() ?? 0;
    final needP = reqPurchases - currentPurchases;
    final needT = reqTotal - currentTotalRub;
    if (needP > 0 || needT > 0) {
      final pProgress = reqPurchases <= 0
          ? 1.0
          : (currentPurchases / reqPurchases).clamp(0.0, 1.0);
      final tProgress = reqTotal <= 0
          ? 1.0
          : (currentTotalRub / reqTotal).clamp(0.0, 1.0);
      final progress = (pProgress + tProgress) / 2;
      return _NextLevelProgress(
        nextLevelName: (level['name'] as String?) ?? 'Следующий уровень',
        remainingTotal: needT > 0 ? needT : 0,
        progress: progress,
      );
    }
  }
  return null;
}

String _formatRub(num value) {
  final rounded = value.round();
  final s = rounded.abs().toString();
  final buf = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    final posFromEnd = s.length - i;
    buf.write(s[i]);
    if (posFromEnd > 1 && posFromEnd % 3 == 1) {
      buf.write(' ');
    }
  }
  final sign = rounded < 0 ? '-' : '';
  return '$sign${buf.toString()} ₽';
}

String _formatIsoDate(String iso) {
  if (iso.trim().isEmpty) return '';
  try {
    final dt = DateTime.parse(iso).toLocal();
    final y = dt.year.toString().padLeft(4, '0');
    final m = dt.month.toString().padLeft(2, '0');
    final d = dt.day.toString().padLeft(2, '0');
    return '$d.$m.$y';
  } catch (_) {
    return iso;
  }
}

String _orderStatusLabel(String value) {
  switch (value) {
    case 'pending':
      return 'Ожидает обработки';
    case 'payment_pending':
      return 'Ожидает оплаты';
    case 'paid':
      return 'Оплачен';
    case 'shipped':
      return 'Отгружен';
    case 'delivered':
      return 'Доставлен';
    case 'canceled':
      return 'Отменен';
    default:
      return value;
  }
}

String _paymentStatusLabel(String? value) {
  switch (value) {
    case 'pending':
      return 'Ожидает оплаты';
    case 'waiting_for_capture':
      return 'Ожидает подтверждения';
    case 'succeeded':
      return 'Оплачено';
    case 'canceled':
      return 'Отменено';
    case null:
      return 'Нет данных';
    default:
      return value;
  }
}

String _deliverySummary(Map<String, dynamic> delivery) {
  if (delivery.isEmpty) return 'Доставка: не указана';
  final method = (delivery['method'] ?? delivery['type'] ?? '').toString();
  final city = (delivery['city'] ?? delivery['city_name'] ?? '')
      .toString()
      .trim();
  final pvz = (delivery['pvz_name'] ?? delivery['pvz_code'] ?? '')
      .toString()
      .trim();
  final address = (delivery['address'] ?? '').toString().trim();

  final parts = <String>[];
  if (city.isNotEmpty) parts.add(city);
  if (pvz.isNotEmpty) parts.add(pvz);
  if (address.isNotEmpty) parts.add(address);

  final place = parts.isEmpty ? 'не указана' : parts.join(', ');
  if (method == 'pickup') return 'Доставка: самовывоз · $place';
  if (method == 'cdek' || method == 'cdek_pvz' || method == 'pvz') {
    return 'Доставка: СДЭК · $place';
  }
  return 'Доставка: $place';
}

String _deliveryShortLabel(Map<String, dynamic> delivery) {
  if (delivery.isEmpty) return 'Не выбрана';
  final method = (delivery['method'] ?? delivery['type'] ?? '')
      .toString()
      .trim()
      .toLowerCase();
  if (method == 'pickup') return 'Самовывоз';
  if (method == 'cdek' || method == 'cdek_pvz' || method == 'pvz') {
    return 'СДЭК';
  }
  return 'Доставка';
}

class _LoginRequired extends StatelessWidget {
  final String title;
  final String subtitle;
  final VoidCallback onLogin;

  const _LoginRequired({
    required this.title,
    required this.subtitle,
    required this.onLogin,
  });

  @override
  Widget build(BuildContext context) {
    return GlameAuthGate(
      eyebrow: title,
      title: 'Войдите в GLAME',
      description: subtitle,
      note: 'После входа Вы вернетесь к этому разделу.',
      noteIcon: Icons.lock_outline,
      onLogin: onLogin,
      dark: false,
    );
  }
}
