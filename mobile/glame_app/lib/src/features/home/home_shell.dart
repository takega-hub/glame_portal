import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:latlong2/latlong.dart';

import '../../core/formatters/rub.dart';
import '../../core/theme/glame_theme.dart';
import '../../core/widgets/glame_auth_gate.dart';
import '../auth/auth_controller.dart';
import '../cart/cart_screen.dart';
import '../catalog/catalog_screen.dart';
import '../customer/customer_cabinet_providers.dart';
import '../customer/stylist_entry.dart';
import '../gift_certificate/gift_certificate_screen.dart';
import '../looks/looks_screen.dart';
import '../stores/stores_screen.dart';
import '../wishlist/wishlist_screen.dart';
import 'home_providers.dart';
import 'home_screen.dart';
import 'photo_upload_screen.dart';

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
    final darkHeader = _usesDarkHeader(index);
    final headerHeight = isDesktop ? 96.0 : (darkHeader ? 88.0 : 74.0);

    final page = index == 3
        ? const SizedBox.shrink()
        : _buildSectionPage(
            context: context,
            index: index,
            isLoggedIn: isLoggedIn,
            email: auth.user?.email,
            onLogout: controller.logout,
          );

    final body = isHeroHome
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
        : Stack(
            children: [
              Positioned.fill(
                child: Column(
                  children: [
                    _GlameHeader(
                      selectedIndex: index,
                      isDesktop: isDesktop,
                      dark: darkHeader,
                      onSelected: _selectTab,
                    ),
                    Expanded(
                      child: ColoredBox(
                        color: index == 3 || index == 8
                            ? GlameColors.nearBlack
                            : GlameColors.surface2,
                        child: page,
                      ),
                    ),
                  ],
                ),
              ),
              if (index == 3)
                Positioned.fill(
                  top: headerHeight,
                  child: _buildSelectionTabPage(context),
                ),
            ],
          );

    return Scaffold(
      key: _scaffoldKey,
      drawer: _GlameDrawer(
        selectedIndex: index,
        onSelected: (i) {
          Navigator.of(context).pop();
          _selectTab(i);
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
      body: body,
      bottomNavigationBar: isDesktop
          ? null
          : _GlameBottomBar(selectedIndex: index, onSelected: _selectTab),
    );
  }

  bool _usesDarkHeader(int tabIndex) {
    return tabIndex == 1 ||
        tabIndex == 2 ||
        tabIndex == 3 ||
        tabIndex == 4 ||
        tabIndex == 5 ||
        tabIndex == 8 ||
        tabIndex == 11;
  }

  void _selectTab(int nextIndex) {
    final nextRoute = nextIndex == 0 ? '/home' : '/home?tab=$nextIndex';
    if (GoRouterState.of(context).uri.toString() == nextRoute) {
      setState(() {
        index = nextIndex;
        catalogCategory = null;
        catalogSearch = null;
        lookFilter = null;
      });
      return;
    }
    context.go(nextRoute);
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
      return _buildSelectionTabPage(context);
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
              dark: true,
            );
    }
    if (index == 5) return LooksScreen(initialFilter: lookFilter);
    if (index == 6) {
      return const CatalogScreen(title: 'НОВИНКИ', initialCategory: 'NEW');
    }
    if (index == 8) {
      return const GiftCertificateScreen();
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

  Widget _buildSelectionTabPage(BuildContext context) {
    final stylistStatus = ref.watch(stylistChatStatusProvider).asData?.value;
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: const Color(0xFF111111),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(28, 22, 28, 32),
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const _SelectionTabHeader(),
                const SizedBox(height: 20),
                _SelectionTabAction(
                  number: '01',
                  title: 'Через AI-подбор',
                  description: 'По фото, форме и масштабу',
                  onTap: () => showPhotoUploadSheet(context),
                ),
                const SizedBox(height: 14),
                _SelectionTabAction(
                  number: '02',
                  title: 'С живым стилистом',
                  description: 'Онлайн или в пространстве',
                  onTap: () => showStylistContactSheet(
                    context,
                    source: 'selection_screen',
                    scenario: 'live_stylist',
                    statusPayload: stylistStatus,
                  ),
                ),
                const SizedBox(height: 14),
                _SelectionTabAction(
                  number: '03',
                  title: 'Подобрать подарок',
                  description: 'Для особенного момента',
                  onTap: () => context.push('/selection/gift'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
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
  final bool dark;
  final ValueChanged<int> onSelected;

  const _GlameHeader({
    required this.selectedIndex,
    required this.isDesktop,
    this.dark = false,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    final height = isDesktop ? 96.0 : (dark ? 88.0 : 74.0);
    return Builder(
      builder: (context) => GlameTopAppBar(
        height: height,
        dark: dark,
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
                child: Container(
                  width: 154,
                  height: 38,
                  alignment: Alignment.center,
                  child: const GlameHeaderLogo(height: 24, silver: true),
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
    final hasBottomInset = MediaQuery.of(context).padding.bottom > 0;
    final bottomAir = hasBottomInset ? 6.0 : 0.0;

    return DecoratedBox(
      decoration: const BoxDecoration(
        color: GlameColors.surface2,
        border: Border(top: BorderSide(color: GlameColors.borderGray)),
      ),
      child: SizedBox(
        height: GlameUi.mobileBottomNavHeight + bottomAir,
        child: Padding(
          padding: EdgeInsets.only(bottom: bottomAir),
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

class _SelectionTabHeader extends StatelessWidget {
  const _SelectionTabHeader();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Подбор',
          style: TextStyle(
            fontSize: 24,
            height: 1.1,
            color: GlameColors.whiteGlame,
            fontWeight: FontWeight.w400,
          ),
        ),
        SizedBox(height: 12),
        Divider(height: 1, thickness: 1, color: GlameColors.borderGray),
      ],
    );
  }
}

class _SelectionTabAction extends StatelessWidget {
  final String number;
  final String title;
  final String description;
  final VoidCallback onTap;

  const _SelectionTabAction({
    required this.number,
    required this.title,
    required this.description,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: title,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          splashColor: GlameColors.whiteGlame.withValues(alpha: 0.05),
          highlightColor: GlameColors.whiteGlame.withValues(alpha: 0.03),
          child: Container(
            height: 88,
            decoration: BoxDecoration(
              color: const Color(0xFF18191A),
              border: Border.all(color: const Color(0xFF55585C)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                SizedBox(
                  width: 54,
                  child: Center(
                    child: Text(
                      number,
                      style: const TextStyle(
                        fontSize: 13,
                        color: GlameColors.whiteGlame,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
                Container(width: 1, color: const Color(0xFF55585C)),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(18, 17, 12, 15),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 15,
                            height: 1.15,
                            color: GlameColors.whiteGlame,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          description,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 12,
                            height: 1.25,
                            color: GlameColors.textSecondary,
                            fontWeight: FontWeight.w400,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(
                  width: 48,
                  child: Center(
                    child: Icon(
                      Icons.chevron_right,
                      size: 24,
                      color: GlameColors.whiteGlame,
                    ),
                  ),
                ),
              ],
            ),
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
            width: 32,
            height: 32,
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
          padding: const EdgeInsets.fromLTRB(24, 22, 24, 24),
          child: ListView(
            children: [
              const _DrawerSectionLabel('Навигация'),
              _DrawerItem('Главная', 0, selectedIndex, onSelected),
              _DrawerItem('Украшения', 1, selectedIndex, onSelected),
              _DrawerItem('Мой стиль', 2, selectedIndex, onSelected),
              _DrawerItem('Подбор', 3, selectedIndex, onSelected),
              _DrawerItem('Профиль', 4, selectedIndex, onSelected),
              _DrawerItem('Образы', 5, selectedIndex, onSelected),
              const SizedBox(height: 20),
              const _DrawerSectionLabel('Витрина'),
              _DrawerItem('Новинки', 6, selectedIndex, onSelected),
              _DrawerRouteItem(
                label: 'Бренды',
                onTap: () {
                  Navigator.of(context).pop();
                  context.go('/brands');
                },
              ),
              _DrawerItem('Пространства', 10, selectedIndex, onSelected),
              _DrawerItem(
                'Подарочный сертификат',
                8,
                selectedIndex,
                onSelected,
              ),
              const SizedBox(height: 24),
              Container(height: 1, color: GlameColors.borderGray),
              const SizedBox(height: 18),
              const _DrawerSectionLabel('Действия'),
              _DrawerItem('Корзина', 11, selectedIndex, onSelected),
              _DrawerRouteItem(
                label: isLoggedIn ? 'Выйти' : 'Войти',
                onTap: isLoggedIn ? onLogout : onLogin,
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
          padding: const EdgeInsets.fromLTRB(28, 40, 28, 28),
          children: [
            profileAsync.when(
              data: (profile) {
                final fullName = (profile['full_name'] as String?)?.trim();
                final phone = (profile['phone'] as String?)?.trim();
                final points =
                    (profile['loyalty_points'] as num?)?.toInt() ?? 0;
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
                final loyalty = loyaltyAsync.maybeWhen(
                  data: (value) => value,
                  orElse: () => const <String, dynamic>{},
                );

                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _ProfileStitchHero(
                      name: displayName,
                      contact: contact,
                      points: points,
                      status: _profileStatusLabel(loyalty),
                      progress: _profileProgressFromLoyalty(loyalty),
                      nextLevelAmount: _profileNextLevelAmount(loyalty),
                    ),
                    const SizedBox(height: 26),
                    _ProfileActionList(
                      actions: [
                        _ProfileAction(
                          label: 'Мои заказы',
                          onTap: () => _showProfileOrdersDialog(context, ref),
                        ),
                        _ProfileAction(
                          label: 'Подарочные сертификаты',
                          onTap: () =>
                              _showProfileGiftCertificatesDialog(context, ref),
                        ),
                        _ProfileAction(
                          label: 'История покупок',
                          onTap: () => _showProfileHistoryDialog(context, ref),
                        ),
                        _ProfileAction(
                          label: 'Избранное',
                          onTap: () => context.go('/home?tab=2'),
                        ),
                        _ProfileAction(
                          label: 'Обращения к стилисту',
                          onTap: () => showStylistContactSheet(
                            context,
                            source: 'profile_screen',
                            scenario: 'live_stylist',
                          ),
                        ),
                        _ProfileAction(
                          label: 'Настройки доставки',
                          onTap: () => _editPreferredDelivery(
                            context: context,
                            ref: ref,
                            currentDelivery: preferredDelivery,
                          ),
                        ),
                        _ProfileAction(
                          label: 'Клиентам',
                          onTap: () => context.push('/clients'),
                        ),
                      ],
                    ),
                    const SizedBox(height: 28),
                    _ProfileLogoutButton(onTap: onLogout),
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
            const SizedBox(height: 12),
          ],
        ),
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
    if (method == 'pvz') method = 'cdek_pvz';

    List<dynamic> rawStores = const [];
    try {
      rawStores = await ref.read(homeApiProvider).getPickupStores();
    } catch (_) {
      rawStores = const [];
    }
    if (!context.mounted) return;

    final apiStoreOptions = _deliveryStoreOptions(rawStores);
    final storeOptions = apiStoreOptions.isEmpty
        ? _fallbackDeliveryStores
        : apiStoreOptions;
    final storesFromFallback = apiStoreOptions.isEmpty;
    final currentStoreId =
        (currentDelivery['store_id'] ?? currentDelivery['storeId'] ?? '')
            .toString()
            .trim();
    final currentStoreName = (currentDelivery['store_name'] ?? '')
        .toString()
        .trim()
        .toLowerCase();
    String? selectedStoreId = _initialDeliveryStoreId(
      stores: storeOptions,
      currentStoreId: currentStoreId,
      currentStoreName: currentStoreName,
    );

    final cityCtrl = TextEditingController(
      text: (currentDelivery['city'] ?? currentDelivery['city_name'] ?? '')
          .toString(),
    );
    Map<String, dynamic>? selectedCdekCity = _deliveryInitialCdekCity(
      currentDelivery,
    );
    Map<String, dynamic>? selectedPvz = _deliveryInitialCdekPvz(
      currentDelivery,
    );
    List<Map<String, dynamic>> cdekPvz = const [];
    bool loadingCdekPvz = false;
    String? cdekError;

    Future<Map<String, dynamic>?> pickCdekCity(
      BuildContext dialogContext,
    ) async {
      final queryController = TextEditingController(
        text: cityCtrl.text.trim().isEmpty ? 'Ялта' : cityCtrl.text.trim(),
      );
      final api = ref.read(homeApiProvider);
      List<Map<String, dynamic>> cities = const [];
      bool loading = false;
      String? error;

      Future<void> runSearch(
        StateSetter modalSetState, [
        String? forced,
      ]) async {
        final query = (forced ?? queryController.text).trim();
        if (query.length < 2) {
          modalSetState(() {
            cities = const [];
            error = 'Введите минимум 2 символа';
          });
          return;
        }
        modalSetState(() {
          loading = true;
          error = null;
        });
        try {
          final result = await api.getCdekCities(query);
          modalSetState(() {
            cities = result;
            if (cities.isEmpty) error = 'Города не найдены';
          });
        } catch (_) {
          modalSetState(() => error = 'Ошибка поиска городов СДЭК');
        } finally {
          modalSetState(() => loading = false);
        }
      }

      try {
        cities = await api.getCdekCities(queryController.text.trim());
        if (cities.isEmpty) error = 'Города не найдены';
      } catch (_) {
        error = 'Ошибка поиска городов СДЭК';
      }
      if (!dialogContext.mounted) {
        queryController.dispose();
        return null;
      }

      final picked = await showModalBottomSheet<Map<String, dynamic>>(
        context: dialogContext,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (sheetContext) => StatefulBuilder(
          builder: (sheetContext, modalSetState) {
            return SafeArea(
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  16,
                  8,
                  16,
                  MediaQuery.of(sheetContext).viewInsets.bottom + 12,
                ),
                child: SizedBox(
                  height: 440,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Text(
                        'Выбор города СДЭК',
                        style: TextStyle(fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 10),
                      TextField(
                        controller: queryController,
                        decoration: const InputDecoration(
                          labelText: 'Введите город',
                          hintText: 'Например, Москва',
                        ),
                        textInputAction: TextInputAction.search,
                        onSubmitted: (value) =>
                            runSearch(modalSetState, value.trim()),
                      ),
                      const SizedBox(height: 8),
                      OutlinedButton.icon(
                        onPressed: loading
                            ? null
                            : () => runSearch(modalSetState),
                        icon: const Icon(Icons.search, size: 18),
                        label: const Text('Найти город'),
                      ),
                      if (loading) ...[
                        const SizedBox(height: 8),
                        const LinearProgressIndicator(),
                      ],
                      if (error != null) ...[
                        const SizedBox(height: 8),
                        Text(error!),
                      ],
                      const SizedBox(height: 8),
                      Expanded(
                        child: ListView.separated(
                          itemCount: cities.length,
                          separatorBuilder: (_, _) => const Divider(height: 1),
                          itemBuilder: (_, i) {
                            final city = cities[i];
                            return ListTile(
                              title: Text(_deliveryCdekCityLabel(city)),
                              subtitle: Text('Код: ${city['code'] ?? '-'}'),
                              onTap: () => Navigator.of(sheetContext).pop(city),
                            );
                          },
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      );
      queryController.dispose();
      return picked;
    }

    Future<bool> loadCdekPvz(StateSetter modalSetState) async {
      final cityCode = _deliveryInt(selectedCdekCity?['code']);
      if (cityCode == null) {
        modalSetState(() {
          cdekError = 'Не удалось определить код города СДЭК';
        });
        return false;
      }
      modalSetState(() {
        loadingCdekPvz = true;
        cdekError = null;
      });
      try {
        final result = await ref.read(homeApiProvider).getCdekPvz(cityCode);
        modalSetState(() {
          cdekPvz = result;
          loadingCdekPvz = false;
          if (result.isEmpty) {
            cdekError = 'Для выбранного города ПВЗ не найдены';
          }
        });
        return result.isNotEmpty;
      } catch (_) {
        modalSetState(() {
          loadingCdekPvz = false;
          cdekError = 'Не удалось загрузить пункты ПВЗ СДЭК';
        });
        return false;
      }
    }

    Future<Map<String, dynamic>?> pickCdekPvzList(
      BuildContext dialogContext,
      StateSetter parentSetState,
    ) async {
      if (selectedCdekCity == null) return null;
      if (cdekPvz.isEmpty) {
        final loaded = await loadCdekPvz(parentSetState);
        if (!loaded || !dialogContext.mounted) return null;
      }

      final queryController = TextEditingController();
      final picked = await showModalBottomSheet<Map<String, dynamic>>(
        context: dialogContext,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (sheetContext) => StatefulBuilder(
          builder: (sheetContext, modalSetState) {
            final query = queryController.text.trim().toLowerCase();
            final filtered = query.isEmpty
                ? cdekPvz
                : cdekPvz
                      .where(
                        (pvz) => _deliveryCdekPvzLabel(
                          pvz,
                        ).toLowerCase().contains(query),
                      )
                      .toList();
            return SafeArea(
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  16,
                  8,
                  16,
                  MediaQuery.of(sheetContext).viewInsets.bottom + 12,
                ),
                child: SizedBox(
                  height: 440,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Text(
                        'Выбор пункта ПВЗ СДЭК',
                        style: TextStyle(fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 10),
                      TextField(
                        controller: queryController,
                        decoration: const InputDecoration(
                          labelText: 'Поиск ПВЗ',
                        ),
                        onChanged: (_) => modalSetState(() {}),
                      ),
                      const SizedBox(height: 8),
                      Expanded(
                        child: filtered.isEmpty
                            ? const Center(
                                child: Text('Пункты выдачи не найдены'),
                              )
                            : ListView.separated(
                                itemCount: filtered.length,
                                separatorBuilder: (_, _) =>
                                    const Divider(height: 1),
                                itemBuilder: (_, i) {
                                  final pvz = filtered[i];
                                  return ListTile(
                                    title: Text(_deliveryCdekPvzLabel(pvz)),
                                    subtitle: Text(
                                      'Код: ${pvz['code'] ?? '-'}',
                                    ),
                                    onTap: () =>
                                        Navigator.of(sheetContext).pop(pvz),
                                  );
                                },
                              ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      );
      queryController.dispose();
      return picked;
    }

    Future<Map<String, dynamic>?> pickCdekPvzMap(
      BuildContext dialogContext,
      StateSetter parentSetState,
    ) async {
      if (selectedCdekCity == null) return null;
      if (cdekPvz.isEmpty) {
        final loaded = await loadCdekPvz(parentSetState);
        if (!loaded || !dialogContext.mounted) return null;
      }
      final points = cdekPvz
          .map((pvz) {
            final point = _deliveryCdekPvzLatLng(pvz);
            if (point == null) return null;
            return (pvz, point);
          })
          .whereType<(Map<String, dynamic>, LatLng)>()
          .toList();
      if (points.isEmpty) {
        parentSetState(() {
          cdekError =
              'Для выбранного города нет координат ПВЗ для отображения карты';
        });
        return null;
      }

      final picked = await showDialog<Map<String, dynamic>>(
        context: dialogContext,
        builder: (mapContext) {
          Map<String, dynamic>? selected = selectedPvz;
          return StatefulBuilder(
            builder: (mapContext, modalSetState) => Dialog(
              insetPadding: const EdgeInsets.all(12),
              child: SizedBox(
                width: 900,
                height: 660,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
                      child: Row(
                        children: [
                          const Expanded(
                            child: Text(
                              'Выбор ПВЗ СДЭК на карте',
                              style: TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ),
                          IconButton(
                            onPressed: () => Navigator.of(mapContext).pop(),
                            icon: const Icon(Icons.close),
                          ),
                        ],
                      ),
                    ),
                    const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 16),
                      child: Text(
                        'Нажмите на маркер, затем подтвердите пункт ниже',
                      ),
                    ),
                    const SizedBox(height: 8),
                    Expanded(
                      child: FlutterMap(
                        options: MapOptions(
                          initialCenter: points.first.$2,
                          initialZoom: 12,
                        ),
                        children: [
                          TileLayer(
                            urlTemplate:
                                'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                            userAgentPackageName: 'ru.glamejewelry.glame_app',
                          ),
                          MarkerLayer(
                            markers: points
                                .map(
                                  (item) => Marker(
                                    point: item.$2,
                                    width: 42,
                                    height: 42,
                                    child: Tooltip(
                                      message: _deliveryCdekPvzLabel(item.$1),
                                      child: GestureDetector(
                                        onTap: () => modalSetState(
                                          () => selected = item.$1,
                                        ),
                                        child: Icon(
                                          Icons.location_on,
                                          color:
                                              selected != null &&
                                                  '${selected!['code']}' ==
                                                      '${item.$1['code']}'
                                              ? GlameColors.graphite
                                              : GlameColors.gold,
                                          size: 34,
                                        ),
                                      ),
                                    ),
                                  ),
                                )
                                .toList(),
                          ),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
                      decoration: BoxDecoration(
                        border: Border(
                          top: BorderSide(color: GlameColors.lightGray),
                        ),
                      ),
                      child: selected == null
                          ? const Text('Выберите маркер ПВЗ на карте')
                          : Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                Text(
                                  _deliveryCdekPvzLabel(selected!),
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  _deliveryCdekPvzAddress(selected!),
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                const SizedBox(height: 10),
                                FilledButton(
                                  onPressed: () =>
                                      Navigator.of(mapContext).pop(selected),
                                  child: const Text('Выбрать это ПВЗ'),
                                ),
                              ],
                            ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      );
      return picked;
    }

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
                    DropdownButtonFormField<String>(
                      initialValue: selectedStoreId,
                      decoration: const InputDecoration(
                        labelText: 'Магазин самовывоза',
                      ),
                      isExpanded: true,
                      items: storeOptions
                          .map(
                            (store) => DropdownMenuItem(
                              value: store.id,
                              child: Text(
                                store.label,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: storeOptions.isEmpty
                          ? null
                          : (value) {
                              modalSetState(() => selectedStoreId = value);
                            },
                    ),
                    if (storeOptions.isEmpty) ...[
                      const SizedBox(height: 8),
                      const Text(
                        'Магазины не загрузились. Проверьте соединение и повторите.',
                      ),
                    ] else if (storesFromFallback) ...[
                      const SizedBox(height: 8),
                      const Text(
                        'Показываем сохраненный список пространств. Данные API обновятся автоматически, когда сервер будет доступен.',
                      ),
                    ],
                  ] else ...[
                    OutlinedButton(
                      onPressed: () async {
                        final picked = await pickCdekCity(ctx);
                        if (picked == null) return;
                        modalSetState(() {
                          selectedCdekCity = picked;
                          cityCtrl.text = _deliveryCdekCityLabel(picked);
                          selectedPvz = null;
                          cdekPvz = const [];
                          cdekError = null;
                        });
                        await loadCdekPvz(modalSetState);
                      },
                      child: Text(
                        selectedCdekCity == null
                            ? 'Выбрать город СДЭК'
                            : 'Город: ${_deliveryCdekCityLabel(selectedCdekCity!)}',
                      ),
                    ),
                    if (selectedCdekCity != null) ...[
                      const SizedBox(height: 8),
                      OutlinedButton(
                        onPressed: loadingCdekPvz
                            ? null
                            : () async {
                                final picked = await pickCdekPvzList(
                                  ctx,
                                  modalSetState,
                                );
                                if (picked == null) return;
                                modalSetState(() {
                                  selectedPvz = picked;
                                  cdekError = null;
                                });
                              },
                        child: Text(
                          selectedPvz == null
                              ? 'Выбрать пункт ПВЗ СДЭК'
                              : 'ПВЗ: ${_deliveryCdekPvzLabel(selectedPvz!)}',
                        ),
                      ),
                      const SizedBox(height: 8),
                      OutlinedButton.icon(
                        onPressed: loadingCdekPvz
                            ? null
                            : () async {
                                final picked = await pickCdekPvzMap(
                                  ctx,
                                  modalSetState,
                                );
                                if (picked == null) return;
                                modalSetState(() {
                                  selectedPvz = picked;
                                  cdekError = null;
                                });
                              },
                        icon: const Icon(Icons.map_outlined, size: 18),
                        label: const Text('Выбрать ПВЗ на карте'),
                      ),
                    ],
                    if (loadingCdekPvz) ...[
                      const SizedBox(height: 8),
                      const LinearProgressIndicator(),
                    ],
                    if (cdekError != null) ...[
                      const SizedBox(height: 8),
                      Text(cdekError!),
                    ],
                  ],
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(false),
                child: const Text('Отмена'),
              ),
              FilledButton(
                onPressed:
                    (method == 'pickup' && selectedStoreId == null) ||
                        (method != 'pickup' &&
                            (selectedCdekCity == null || selectedPvz == null))
                    ? null
                    : () => Navigator.of(ctx).pop(true),
                child: const Text('Сохранить'),
              ),
            ],
          ),
        );
      },
    );

    if (shouldSave != true) {
      cityCtrl.dispose();
      return;
    }

    final selectedStore = _deliveryStoreById(storeOptions, selectedStoreId);
    final delivery = <String, dynamic>{
      ...currentDelivery,
      'method': method == 'pickup' ? 'pickup' : 'cdek',
      'type': method == 'pickup' ? 'pickup' : 'pvz',
      'city': method == 'pickup'
          ? selectedStore?.city ?? ''
          : selectedCdekCity?['city'] ?? selectedCdekCity?['city_name'] ?? '',
      'address': method == 'pickup' ? selectedStore?.address ?? '' : '',
      'comment': '',
    };
    if (method == 'pickup') {
      delivery['store_id'] = selectedStore?.id ?? '';
      delivery['store_name'] = selectedStore?.title ?? '';
      delivery['pvz_name'] = '';
    } else {
      final location = selectedPvz?['location'] is Map
          ? Map<String, dynamic>.from(selectedPvz!['location'] as Map)
          : const <String, dynamic>{};
      delivery['store_id'] = '';
      delivery['store_name'] = '';
      delivery['city_code'] = selectedCdekCity?['code'];
      delivery['pvz_code'] = selectedPvz?['code'];
      delivery['pvz_name'] = selectedPvz?['name'];
      delivery['address'] =
          location['address'] ?? selectedPvz?['address'] ?? '';
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
      cityCtrl.dispose();
    }
  }
}

class _DeliveryStoreOption {
  final String id;
  final String title;
  final String city;
  final String address;

  const _DeliveryStoreOption({
    required this.id,
    required this.title,
    required this.city,
    required this.address,
  });

  String get label {
    final parts = <String>[
      title,
      if (city.toLowerCase() != title.toLowerCase()) city,
      address,
    ].where((part) => part.trim().isNotEmpty).toList();
    return parts.join(' · ');
  }
}

const _fallbackDeliveryStores = <_DeliveryStoreOption>[
  _DeliveryStoreOption(
    id: 'yalta',
    title: 'GLAME Ялта',
    city: 'Ялта',
    address: 'Набережная им. Ленина, 18',
  ),
  _DeliveryStoreOption(
    id: 'simferopol',
    title: 'GLAME Симферополь',
    city: 'Симферополь',
    address: 'ул. Севастопольская, 62',
  ),
  _DeliveryStoreOption(
    id: 'mriya',
    title: 'GLAME МРИЯ',
    city: 'Оползневое',
    address: 'Mriya Resort & SPA',
  ),
];

List<_DeliveryStoreOption> _deliveryStoreOptions(List<dynamic> rawStores) {
  final stores = <_DeliveryStoreOption>[];
  for (final raw in rawStores.whereType<Map>()) {
    final item = Map<String, dynamic>.from(raw);
    final id = _deliveryValue(item['id']) ?? stores.length.toString();
    final city = _deliveryValue(item['city']);
    final title =
        _deliveryValue(item['title']) ?? _deliveryValue(item['name']) ?? city;
    final address = _deliveryValue(item['address']);
    if (title == null || city == null || address == null) continue;
    stores.add(
      _DeliveryStoreOption(id: id, title: title, city: city, address: address),
    );
  }
  return stores;
}

String? _initialDeliveryStoreId({
  required List<_DeliveryStoreOption> stores,
  required String currentStoreId,
  required String currentStoreName,
}) {
  if (stores.isEmpty) return null;
  for (final store in stores) {
    if (currentStoreId.isNotEmpty && store.id == currentStoreId) {
      return store.id;
    }
  }
  for (final store in stores) {
    if (currentStoreName.isNotEmpty &&
        store.title.toLowerCase() == currentStoreName) {
      return store.id;
    }
  }
  return stores.first.id;
}

_DeliveryStoreOption? _deliveryStoreById(
  List<_DeliveryStoreOption> stores,
  String? id,
) {
  for (final store in stores) {
    if (store.id == id) return store;
  }
  return null;
}

String? _deliveryValue(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : text;
}

Map<String, dynamic>? _deliveryInitialCdekCity(
  Map<String, dynamic> currentDelivery,
) {
  final code = currentDelivery['city_code'];
  final city = _deliveryValue(
    currentDelivery['city'] ?? currentDelivery['city_name'],
  );
  if (code == null && city == null) return null;
  final result = <String, dynamic>{};
  if (code != null) result['code'] = code;
  if (city != null) result['city'] = city;
  return result;
}

Map<String, dynamic>? _deliveryInitialCdekPvz(
  Map<String, dynamic> currentDelivery,
) {
  final code = _deliveryValue(
    currentDelivery['pvz_code'] ?? currentDelivery['point_code'],
  );
  final name = _deliveryValue(
    currentDelivery['pvz_name'] ?? currentDelivery['point_name'],
  );
  final address = _deliveryValue(currentDelivery['address']);
  if (code == null && name == null && address == null) return null;
  final result = <String, dynamic>{};
  if (code != null) result['code'] = code;
  if (name != null) result['name'] = name;
  if (address != null) result['address'] = address;
  return result;
}

String _deliveryCdekCityLabel(Map<String, dynamic> city) {
  final title = _deliveryValue(city['city'] ?? city['city_name']) ?? '';
  final region = _deliveryValue(city['region'] ?? city['region_name']);
  if (region == null) return title;
  return '$title, $region';
}

String _deliveryCdekPvzLabel(Map<String, dynamic> pvz) {
  final code = _deliveryValue(pvz['code']);
  final name = _deliveryValue(pvz['name']) ?? code ?? 'ПВЗ';
  final address = _deliveryCdekPvzAddress(pvz);
  if (address == '-') return name;
  return '$name — $address';
}

String _deliveryCdekPvzAddress(Map<String, dynamic> pvz) {
  final location = pvz['location'] is Map
      ? Map<String, dynamic>.from(pvz['location'] as Map)
      : const <String, dynamic>{};
  return _deliveryValue(location['address_full']) ??
      _deliveryValue(location['address']) ??
      _deliveryValue(pvz['address']) ??
      '-';
}

LatLng? _deliveryCdekPvzLatLng(Map<String, dynamic> pvz) {
  final location = pvz['location'] is Map
      ? Map<String, dynamic>.from(pvz['location'] as Map)
      : const <String, dynamic>{};
  final lat = _deliveryDouble(location['latitude'] ?? pvz['latitude']);
  final lng = _deliveryDouble(location['longitude'] ?? pvz['longitude']);
  if (lat == null || lng == null) return null;
  return LatLng(lat, lng);
}

int? _deliveryInt(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  final text = value?.toString().trim();
  if (text == null || text.isEmpty) return null;
  return int.tryParse(text) ??
      double.tryParse(text.replaceAll(',', '.'))?.toInt();
}

double? _deliveryDouble(Object? value) {
  if (value is double) return value;
  if (value is num) return value.toDouble();
  final text = value?.toString().trim();
  if (text == null || text.isEmpty) return null;
  return double.tryParse(text.replaceAll(',', '.'));
}

class _ProfileStitchHero extends StatelessWidget {
  final String name;
  final String contact;
  final int points;
  final String status;
  final double progress;
  final num? nextLevelAmount;

  const _ProfileStitchHero({
    required this.name,
    required this.contact,
    required this.points,
    required this.status,
    required this.progress,
    required this.nextLevelAmount,
  });

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF1A1C1E), GlameColors.nearBlack],
        ),
        border: Border(bottom: BorderSide(color: GlameColors.borderGray)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(0, 0, 0, 32),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              name.toUpperCase(),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 28,
                height: 1.08,
                letterSpacing: 0,
                color: GlameColors.whiteGlame,
                fontWeight: FontWeight.w400,
              ),
            ),
            const SizedBox(height: 14),
            Text(
              contact,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 18,
                height: 1.25,
                color: GlameColors.coldLightGray,
              ),
            ),
            const SizedBox(height: 34),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 20),
              decoration: BoxDecoration(
                color: GlameColors.graphite.withValues(alpha: 0.46),
                border: Border.all(color: GlameColors.borderGray),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Expanded(
                        child: _ProfileLoyaltyValue(
                          label: 'Баланс бонусов',
                          value: _formatCompactNumber(points),
                        ),
                      ),
                      const SizedBox(width: 18),
                      _ProfileLoyaltyValue(
                        label: 'Статус',
                        value: status.toUpperCase(),
                        alignEnd: true,
                      ),
                    ],
                  ),
                  const SizedBox(height: 22),
                  ClipRect(
                    child: LinearProgressIndicator(
                      value: progress.clamp(0, 1),
                      minHeight: 4,
                      backgroundColor: GlameColors.borderGray.withValues(
                        alpha: 0.32,
                      ),
                      color: GlameColors.whiteGlame,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Align(
                    alignment: Alignment.centerRight,
                    child: Text(
                      nextLevelAmount == null
                          ? 'Статус рассчитывается по покупкам'
                          : 'До следующего статуса: ${_formatRub(nextLevelAmount!)}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 11,
                        height: 1.2,
                        color: GlameColors.steelGray,
                        letterSpacing: 0.2,
                      ),
                    ),
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

class _ProfileLoyaltyValue extends StatelessWidget {
  final String label;
  final String value;
  final bool alignEnd;

  const _ProfileLoyaltyValue({
    required this.label,
    required this.value,
    this.alignEnd = false,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: alignEnd
          ? CrossAxisAlignment.end
          : CrossAxisAlignment.start,
      children: [
        Text(
          label.toUpperCase(),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            fontSize: 12,
            height: 1.2,
            letterSpacing: 1.4,
            color: GlameColors.steelGray,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            fontSize: 24,
            height: 1,
            color: GlameColors.whiteGlame,
            fontWeight: FontWeight.w400,
          ),
        ),
      ],
    );
  }
}

class _ProfileAction {
  final String label;
  final VoidCallback onTap;

  const _ProfileAction({required this.label, required this.onTap});
}

class _ProfileActionList extends StatelessWidget {
  final List<_ProfileAction> actions;

  const _ProfileActionList({required this.actions});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border.symmetric(
          horizontal: BorderSide(color: GlameColors.borderGray),
        ),
      ),
      child: CustomPaint(
        painter: _ProfileDotPatternPainter(),
        child: Column(
          children: [
            for (var i = 0; i < actions.length; i++) ...[
              _ProfileActionRow(action: actions[i]),
              if (i != actions.length - 1)
                Container(height: 1, color: GlameColors.borderGray),
            ],
          ],
        ),
      ),
    );
  }
}

class _ProfileActionRow extends StatelessWidget {
  final _ProfileAction action;

  const _ProfileActionRow({required this.action});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: action.onTap,
        child: SizedBox(
          height: 64,
          child: Row(
            children: [
              Expanded(
                child: Text(
                  action.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 18,
                    height: 1.1,
                    color: GlameColors.whiteGlame,
                  ),
                ),
              ),
              const Icon(
                Icons.chevron_right,
                size: 32,
                color: GlameColors.coldLightGray,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ProfileLogoutButton extends StatelessWidget {
  final Future<void> Function() onTap;

  const _ProfileLogoutButton({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 56,
      child: OutlinedButton(
        onPressed: onTap,
        style: OutlinedButton.styleFrom(
          foregroundColor: GlameColors.coldLightGray,
          side: const BorderSide(color: GlameColors.borderGray),
          shape: const RoundedRectangleBorder(),
          textStyle: const TextStyle(
            fontSize: 18,
            letterSpacing: 2.2,
            fontWeight: FontWeight.w400,
          ),
        ),
        child: const Text('ВЫХОД'),
      ),
    );
  }
}

Future<void> _showProfileOrdersDialog(BuildContext context, WidgetRef ref) {
  ref.invalidate(customerOrdersProvider);
  return _showProfileDataDialog(
    context: context,
    title: 'Мои заказы',
    provider: customerOrdersProvider,
    itemBuilder: (order) => _ProfileOrderDialogItem(order: order),
    emptyText: 'У вас пока нет заказов.',
    errorText: 'Не удалось загрузить заказы.',
  );
}

Future<void> _showProfileHistoryDialog(BuildContext context, WidgetRef ref) {
  ref.invalidate(customerPurchaseHistoryProvider);
  return _showProfileDataDialog(
    context: context,
    title: 'История покупок',
    provider: customerPurchaseHistoryProvider,
    itemBuilder: (purchase) => _ProfilePurchaseDialogItem(purchase: purchase),
    emptyText: 'История покупок пока пустая.',
    errorText: 'Не удалось загрузить историю покупок.',
  );
}

Future<void> _showProfileGiftCertificatesDialog(
  BuildContext context,
  WidgetRef ref,
) {
  ref.invalidate(customerGiftCertificatesProvider);
  return _showProfileDataDialog(
    context: context,
    title: 'Сертификаты',
    provider: customerGiftCertificatesProvider,
    itemBuilder: (certificate) =>
        _ProfileGiftCertificateDialogItem(certificate: certificate),
    emptyText: 'У вас пока нет подарочных сертификатов.',
    errorText: 'Не удалось загрузить сертификаты.',
  );
}

Future<void> _showProfileDataDialog({
  required BuildContext context,
  required String title,
  required ProviderListenable<AsyncValue<List<Map<String, dynamic>>>> provider,
  required Widget Function(Map<String, dynamic> item) itemBuilder,
  required String emptyText,
  required String errorText,
}) {
  return showDialog<void>(
    context: context,
    builder: (ctx) => Consumer(
      builder: (ctx, ref, _) {
        final asyncValue = ref.watch(provider);
        return Dialog(
          insetPadding: const EdgeInsets.symmetric(
            horizontal: 18,
            vertical: 28,
          ),
          backgroundColor: GlameColors.nearBlack,
          shape: const RoundedRectangleBorder(),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520, maxHeight: 640),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: GlameColors.nearBlack,
                border: Border.all(color: GlameColors.borderGray),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(18, 16, 8, 10),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            title,
                            style: const TextStyle(
                              fontSize: 24,
                              height: 1.05,
                              color: GlameColors.whiteGlame,
                            ),
                          ),
                        ),
                        IconButton(
                          onPressed: () => Navigator.of(ctx).pop(),
                          icon: const Icon(Icons.close),
                          color: GlameColors.whiteGlame,
                        ),
                      ],
                    ),
                  ),
                  Container(height: 1, color: GlameColors.borderGray),
                  Flexible(
                    child: asyncValue.when(
                      loading: () => const SizedBox(
                        height: 180,
                        child: Center(
                          child: CircularProgressIndicator(
                            color: GlameColors.whiteGlame,
                          ),
                        ),
                      ),
                      error: (_, _) =>
                          _ProfileDialogStateMessage(text: errorText),
                      data: (items) {
                        if (items.isEmpty) {
                          return _ProfileDialogStateMessage(text: emptyText);
                        }
                        return ListView.separated(
                          shrinkWrap: true,
                          padding: const EdgeInsets.fromLTRB(18, 14, 18, 18),
                          itemCount: items.length,
                          separatorBuilder: (_, _) =>
                              const SizedBox(height: 10),
                          itemBuilder: (_, index) => itemBuilder(items[index]),
                        );
                      },
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    ),
  );
}

class _ProfileDialogStateMessage extends StatelessWidget {
  final String text;

  const _ProfileDialogStateMessage({required this.text});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 180,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Text(
            text,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 16,
              height: 1.35,
              color: GlameColors.coldLightGray,
            ),
          ),
        ),
      ),
    );
  }
}

class _ProfileOrderDialogItem extends StatelessWidget {
  final Map<String, dynamic> order;

  const _ProfileOrderDialogItem({required this.order});

  @override
  Widget build(BuildContext context) {
    final id = _profileItemString(order['id'] ?? order['number']) ?? 'заказ';
    final created = _profileDateLabel(
      order['created_at'] ?? order['createdAt'] ?? order['date'],
    );
    final status = _orderStatusLabel(
      _profileItemString(order['order_status'] ?? order['status']) ?? '',
    );
    final payment = _paymentStatusLabel(
      _profileItemString(
        order['payment_status'] ??
            (order['payment'] is Map
                ? (order['payment'] as Map)['status']
                : null),
      ),
    );
    final amount = _profileMoneyValue(
      order['total_amount'] ??
          order['total'] ??
          order['amount'] ??
          order['total_price'],
    );

    return _ProfileDialogItemFrame(
      title: 'Заказ ${_shortId(id)}',
      meta: created,
      value: amount == null ? null : formatRubFromKopeks(amount),
      lines: [
        _ProfileDialogLine(label: 'Статус', value: status),
        _ProfileDialogLine(label: 'Оплата', value: payment),
        ?_deliverySummaryLine(order['delivery']),
      ],
    );
  }
}

class _ProfileGiftCertificateDialogItem extends StatelessWidget {
  final Map<String, dynamic> certificate;

  const _ProfileGiftCertificateDialogItem({required this.certificate});

  @override
  Widget build(BuildContext context) {
    final number =
        _profileItemString(certificate['series'] ?? certificate['number']) ??
        'Сертификат';
    final created = _profileDateLabel(
      certificate['activated_at'] ??
          certificate['created_at'] ??
          certificate['createdAt'],
    );
    final status = _certificateStatusLabel(
      _profileItemString(certificate['status']) ?? '',
    );
    final nominal = _profileMoneyValue(certificate['nominal_amount']);
    final balance = _profileMoneyValue(certificate['balance_amount']);
    final pin = _profileItemString(certificate['pin']);

    return _ProfileDialogItemFrame(
      title: 'Сертификат ${_shortId(number)}',
      meta: created,
      value: nominal == null ? null : formatRubFromKopeks(nominal),
      lines: [
        _ProfileDialogLine(label: 'Статус', value: status),
        _ProfileDialogLine(label: 'Серия', value: number),
        if (balance != null)
          _ProfileDialogLine(
            label: 'Баланс',
            value: formatRubFromKopeks(balance),
          ),
        if (pin != null) _ProfileDialogLine(label: 'PIN', value: pin),
      ],
    );
  }
}

class _ProfilePurchaseDialogItem extends StatelessWidget {
  final Map<String, dynamic> purchase;

  const _ProfilePurchaseDialogItem({required this.purchase});

  @override
  Widget build(BuildContext context) {
    final title =
        _profileItemString(
          purchase['product_name'] ??
              purchase['name'] ??
              purchase['title'] ??
              purchase['brand'],
        ) ??
        'Покупка GLAME';
    final created = _profileDateLabel(
      purchase['purchased_at'] ??
          purchase['created_at'] ??
          purchase['createdAt'] ??
          purchase['date'],
    );
    final amount = _profileMoneyValue(
      purchase['amount'] ??
          purchase['price'] ??
          purchase['total'] ??
          purchase['total_amount'],
    );
    final orderId = _profileItemString(
      purchase['order_id'] ?? purchase['orderId'] ?? purchase['order_number'],
    );

    return _ProfileDialogItemFrame(
      title: title,
      meta: created,
      value: amount == null ? null : _formatRub(amount),
      lines: [
        if (orderId != null)
          _ProfileDialogLine(label: 'Заказ', value: _shortId(orderId)),
        ?_profileItemString(purchase['brand']) == null
            ? null
            : _ProfileDialogLine(
                label: 'Бренд',
                value: _profileItemString(purchase['brand'])!,
              ),
      ],
    );
  }
}

class _ProfileDialogItemFrame extends StatelessWidget {
  final String title;
  final String? meta;
  final String? value;
  final List<_ProfileDialogLine> lines;

  const _ProfileDialogItemFrame({
    required this.title,
    required this.meta,
    required this.value,
    required this.lines,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: GlameColors.graphite.withValues(alpha: 0.55),
        border: Border.all(color: GlameColors.borderGray),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 17,
                    height: 1.15,
                    color: GlameColors.whiteGlame,
                  ),
                ),
              ),
              if (value != null) ...[
                const SizedBox(width: 10),
                Text(
                  value!,
                  style: const TextStyle(
                    fontSize: 16,
                    color: GlameColors.whiteGlame,
                  ),
                ),
              ],
            ],
          ),
          if (meta != null) ...[
            const SizedBox(height: 6),
            Text(
              meta!,
              style: const TextStyle(
                fontSize: 12,
                color: GlameColors.steelGray,
              ),
            ),
          ],
          if (lines.isNotEmpty) ...[
            const SizedBox(height: 12),
            ...lines.map(
              (line) => Padding(
                padding: const EdgeInsets.only(bottom: 5),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 72,
                      child: Text(
                        line.label.toUpperCase(),
                        style: const TextStyle(
                          fontSize: 10,
                          letterSpacing: 1,
                          color: GlameColors.steelGray,
                        ),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        line.value,
                        style: const TextStyle(
                          fontSize: 13,
                          height: 1.25,
                          color: GlameColors.coldLightGray,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _ProfileDialogLine {
  final String label;
  final String value;

  const _ProfileDialogLine({required this.label, required this.value});
}

String? _profileItemString(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : text;
}

String _shortId(String value) {
  final text = value.trim();
  if (text.length <= 8) return '#$text';
  return '#${text.substring(0, 8)}';
}

num? _profileMoneyValue(Object? value) {
  if (value is num) return value;
  if (value is String) {
    return num.tryParse(value.replaceAll(' ', '').replaceAll(',', '.').trim());
  }
  return null;
}

String? _profileDateLabel(Object? value) {
  final raw = _profileItemString(value);
  if (raw == null) return null;
  try {
    final date = DateTime.parse(raw).toLocal();
    final day = date.day.toString().padLeft(2, '0');
    final month = date.month.toString().padLeft(2, '0');
    final year = date.year.toString().padLeft(4, '0');
    return '$day.$month.$year';
  } catch (_) {
    return raw;
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
      return value.isEmpty ? 'Нет данных' : value;
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

String _certificateStatusLabel(String status) {
  switch (status) {
    case 'active':
      return 'Активен';
    case 'pending':
      return 'Ожидает оплаты';
    case 'reserved':
      return 'Зарезервирован';
    case 'redeemed':
      return 'Использован';
    case 'canceled':
      return 'Отменён';
    case 'expired':
      return 'Истёк';
    default:
      return status.isEmpty ? 'Не указан' : status;
  }
}

_ProfileDialogLine? _deliverySummaryLine(Object? value) {
  if (value is! Map) return null;
  final delivery = Map<String, dynamic>.from(value);
  final method = _profileItemString(delivery['method'] ?? delivery['type']);
  final city = _profileItemString(delivery['city'] ?? delivery['city_name']);
  final address = _profileItemString(delivery['address']);
  final store = _profileItemString(delivery['store_name']);
  final pvz = _profileItemString(delivery['pvz_name'] ?? delivery['pvz_code']);
  final label = method == 'pickup' ? 'Самовывоз' : 'СДЭК';
  final parts = [store, pvz, city, address].whereType<String>().toList();
  if (parts.isEmpty) return _ProfileDialogLine(label: 'Доставка', value: label);
  return _ProfileDialogLine(
    label: 'Доставка',
    value: '$label: ${parts.join(', ')}',
  );
}

class _ProfileDotPatternPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = GlameColors.borderGray.withValues(alpha: 0.16)
      ..style = PaintingStyle.fill;
    const step = 24.0;
    for (var y = 10.0; y < size.height; y += step) {
      for (var x = 2.0; x < size.width; x += step) {
        canvas.drawCircle(Offset(x, y), 1, paint);
      }
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
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

String _formatCompactNumber(num value) {
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
  return '$sign${buf.toString()}';
}

String _profileStatusLabel(Map<String, dynamic> loyalty) {
  final direct = _stringFromAny(
    loyalty['status'] ??
        loyalty['level'] ??
        loyalty['current_level'] ??
        loyalty['currentLevel'],
  );
  if (direct != null) return direct;

  final progress = loyalty['level_progress'];
  if (progress is Map) {
    final current = _stringFromAny(
      progress['current_level'] ??
          progress['currentLevel'] ??
          progress['level'] ??
          progress['status'],
    );
    if (current != null) return current;
  }
  return 'GLAME';
}

double _profileProgressFromLoyalty(Map<String, dynamic> loyalty) {
  final progress = loyalty['level_progress'];
  if (progress is Map) {
    final value =
        _doubleFromAny(progress['progress']) ??
        _doubleFromAny(progress['percent']) ??
        _doubleFromAny(progress['ratio']);
    if (value != null) {
      return value > 1 ? value / 100 : value;
    }
  }
  final value =
      _doubleFromAny(loyalty['progress']) ??
      _doubleFromAny(loyalty['level_progress']);
  if (value != null) return value > 1 ? value / 100 : value;
  return 0;
}

num? _profileNextLevelAmount(Map<String, dynamic> loyalty) {
  final progress = loyalty['level_progress'];
  if (progress is Map) {
    return _numFromAny(
      progress['remaining_total'] ??
          progress['remainingTotal'] ??
          progress['amount_left'] ??
          progress['amountLeft'],
    );
  }
  return _numFromAny(loyalty['remaining_total'] ?? loyalty['amount_left']);
}

String? _stringFromAny(Object? value) {
  if (value is Map) {
    return _stringFromAny(
      value['name'] ?? value['title'] ?? value['label'] ?? value['code'],
    );
  }
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : text;
}

num? _numFromAny(Object? value) {
  if (value is num) return value;
  if (value is String) return num.tryParse(value.replaceAll(' ', '').trim());
  return null;
}

double? _doubleFromAny(Object? value) {
  final number = _numFromAny(value);
  return number?.toDouble();
}

class _LoginRequired extends StatelessWidget {
  final String title;
  final String subtitle;
  final VoidCallback onLogin;
  final bool dark;

  const _LoginRequired({
    required this.title,
    required this.subtitle,
    required this.onLogin,
    this.dark = false,
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
      dark: dark,
    );
  }
}
