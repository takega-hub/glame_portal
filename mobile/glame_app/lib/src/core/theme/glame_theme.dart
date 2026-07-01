import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class GlameColors {
  static const graphite = Color(0xFF222426);
  static const nearBlack = Color(0xFF111111);
  static const steelGray = Color(0xFF8E9397);
  static const coldLightGray = Color(0xFFC7CBCF);
  static const softGray = Color(0xFFD8DADB);
  static const whiteGlame = Color(0xFFEFF1F2);
  static const borderGray = Color(0xFF5C6064);

  // Legacy aliases are kept while older screens are converted in-place.
  static const black = whiteGlame;
  static const white = nearBlack;
  static const surface = whiteGlame;
  static const surface2 = Color(0xFFFFFFFF);
  static const lightGray = softGray;
  static const coolLightGray = coldLightGray;
  static const gold = steelGray;
  static const steelGrey = steelGray;
  static const coldLightGrey = coldLightGray;
  static const textPrimary = nearBlack;
  static const textSecondary = Color(0xFF5C6064);
  static const warmGray = Color(0xFFF1F2F2);
}

class GlameUi {
  static const double radius = 0;
  static const double borderWidth = 1;
  static const double pagePadding = 28;
  static const double blockGap = 36;
  static const double buttonHeight = 58;
  static const double minTapTarget = 44;
  static const double heroTopBarHeight = 56;
  static const double heroTopOffset = 14;
  static const double mobileBottomNavHeight = 62;
  static const double bottomNavContentAir = 24;
  static const double heroPrimaryButtonWidth = 300;
  static const double heroPrimaryButtonY = 602;
  static const double heroSecondaryButtonY = 676;
  static const double heroSlideIndicatorY = 768;
}

class GlameTextStyles {
  static const display = TextStyle(
    fontSize: 40,
    height: 0.98,
    fontWeight: FontWeight.w300,
    letterSpacing: 0,
  );

  static const sectionTitle = TextStyle(
    fontSize: 28,
    height: 1.08,
    fontWeight: FontWeight.w300,
    letterSpacing: 0,
  );

  static const eyebrow = TextStyle(
    fontSize: 11,
    height: 1.1,
    letterSpacing: 1.4,
    fontWeight: FontWeight.w400,
  );

  static const body = TextStyle(
    fontSize: 15,
    height: 1.45,
    fontWeight: FontWeight.w300,
  );
}

class GlameAssets {
  static const logoBlack = 'assets/images/brand/glame_logo_black.png';
  static const logoGraph = 'assets/images/brand/glame_logo_graph.png';
  static const logoSilver = 'assets/images/brand/glame_logo_silver.png';
  static const sign = 'web/brand_assets/logos/glame_sign.png';
}

class GlameHeaderLogo extends StatelessWidget {
  final double height;
  final bool silver;

  const GlameHeaderLogo({super.key, this.height = 24, this.silver = false});

  @override
  Widget build(BuildContext context) {
    final asset = silver ? GlameAssets.logoSilver : GlameAssets.logoBlack;
    final fallbackColor = silver
        ? GlameColors.whiteGlame
        : GlameColors.textPrimary;

    return SizedBox(
      width: height * 5.15,
      height: height,
      child: Image.asset(
        asset,
        fit: BoxFit.contain,
        alignment: Alignment.center,
        errorBuilder: (_, _, _) => Center(
          child: Text(
            'GLAME',
            style: TextStyle(
              fontSize: height * 0.72,
              letterSpacing: 2.4,
              color: fallbackColor,
            ),
          ),
        ),
      ),
    );
  }
}

class GlamePage extends StatelessWidget {
  final Widget child;
  final bool dark;
  final EdgeInsetsGeometry padding;
  final bool safeTop;

  const GlamePage({
    super.key,
    required this.child,
    this.dark = false,
    this.padding = const EdgeInsets.fromLTRB(20, 24, 20, 28),
    this.safeTop = true,
  });

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: dark ? GlameColors.nearBlack : GlameColors.surface2,
      child: SafeArea(
        top: safeTop,
        child: Padding(padding: padding, child: child),
      ),
    );
  }
}

class GlameSectionHeader extends StatelessWidget {
  final String title;
  final String? eyebrow;
  final String? subtitle;
  final bool dark;

  const GlameSectionHeader({
    super.key,
    required this.title,
    this.eyebrow,
    this.subtitle,
    this.dark = false,
  });

  @override
  Widget build(BuildContext context) {
    final primary = dark ? GlameColors.whiteGlame : GlameColors.textPrimary;
    final secondary = dark
        ? GlameColors.coldLightGray
        : GlameColors.textSecondary;
    final line = dark ? GlameColors.steelGray : GlameColors.borderGray;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (eyebrow != null && eyebrow!.trim().isNotEmpty) ...[
          Text(
            eyebrow!.toUpperCase(),
            style: GlameTextStyles.eyebrow.copyWith(color: secondary),
          ),
          const SizedBox(height: 12),
        ],
        Text(title, style: GlameTextStyles.display.copyWith(color: primary)),
        if (subtitle != null && subtitle!.trim().isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(
            subtitle!,
            style: GlameTextStyles.body.copyWith(color: secondary),
          ),
        ],
        const SizedBox(height: 18),
        Container(width: 54, height: 1, color: line),
      ],
    );
  }
}

class GlamePanel extends StatelessWidget {
  final Widget child;
  final bool dark;
  final EdgeInsetsGeometry padding;
  final Color? color;

  const GlamePanel({
    super.key,
    required this.child,
    this.dark = false,
    this.padding = const EdgeInsets.all(18),
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final border = dark ? GlameColors.borderGray : GlameColors.lightGray;
    final background =
        color ??
        (dark
            ? GlameColors.graphite.withValues(alpha: 0.76)
            : GlameColors.surface2);
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: background,
        border: Border.all(color: border),
      ),
      child: child,
    );
  }
}

class GlameTopAppBar extends StatelessWidget implements PreferredSizeWidget {
  final bool dark;
  final bool transparent;
  final VoidCallback? onMenuPressed;
  final VoidCallback? onLogoPressed;
  final VoidCallback? onCartPressed;
  final VoidCallback? onSearchPressed;
  final IconData? leadingIcon;
  final String? leadingTooltip;
  final double height;

  const GlameTopAppBar({
    super.key,
    this.dark = false,
    this.transparent = false,
    this.onMenuPressed,
    this.onLogoPressed,
    this.onCartPressed,
    this.onSearchPressed,
    this.leadingIcon,
    this.leadingTooltip,
    this.height = 74,
  });

  @override
  Size get preferredSize => Size.fromHeight(height);

  @override
  Widget build(BuildContext context) {
    final foreground = dark || transparent
        ? GlameColors.whiteGlame
        : GlameColors.textPrimary;
    final background = transparent
        ? Colors.transparent
        : (dark ? GlameColors.nearBlack : GlameColors.surface2);
    return Material(
      color: background,
      elevation: 0,
      child: Container(
        height: height,
        padding: const EdgeInsets.symmetric(horizontal: 14),
        child: SafeArea(
          bottom: false,
          child: Stack(
            alignment: Alignment.center,
            children: [
              Positioned(
                left: 0,
                child: _GlameTopIconButton(
                  tooltip: leadingTooltip ?? 'Меню',
                  icon: leadingIcon ?? Icons.menu,
                  color: foreground,
                  onPressed:
                      onMenuPressed ?? () => showGlameNavigationMenu(context),
                ),
              ),
              Center(
                child: InkWell(
                  onTap: onLogoPressed ?? () => context.go('/home'),
                  child: Container(
                    width: 154,
                    height: 38,
                    alignment: Alignment.center,
                    child: GlameHeaderLogo(
                      height: dark || transparent ? 24 : 22,
                      silver: dark || transparent,
                    ),
                  ),
                ),
              ),
              Positioned(
                right: 0,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _GlameTopIconButton(
                      tooltip: 'Корзина',
                      icon: Icons.shopping_bag_outlined,
                      color: foreground,
                      onPressed:
                          onCartPressed ?? () => context.go('/home?tab=11'),
                    ),
                    const SizedBox(width: 4),
                    _GlameTopIconButton(
                      tooltip: 'Поиск',
                      icon: Icons.search,
                      color: foreground,
                      onPressed:
                          onSearchPressed ?? () => context.go('/home?tab=1'),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _GlameTopIconButton extends StatelessWidget {
  final String tooltip;
  final IconData icon;
  final Color color;
  final VoidCallback onPressed;

  const _GlameTopIconButton({
    required this.tooltip,
    required this.icon,
    required this.color,
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
          foregroundColor: color,
          backgroundColor: Colors.transparent,
          shape: const RoundedRectangleBorder(),
        ),
        icon: Icon(icon, size: 23),
      ),
    );
  }
}

Future<void> showGlameNavigationMenu(BuildContext context) {
  final screenWidth = MediaQuery.sizeOf(context).width;
  final panelWidth = screenWidth < 420 ? screenWidth * 0.86 : 360.0;

  return showGeneralDialog<void>(
    context: context,
    barrierDismissible: true,
    barrierLabel: 'Закрыть меню',
    barrierColor: Colors.black.withValues(alpha: 0.34),
    transitionDuration: const Duration(milliseconds: 180),
    pageBuilder: (ctx, _, _) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Material(
          color: GlameColors.nearBlack,
          child: SizedBox(
            width: panelWidth,
            height: double.infinity,
            child: SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(24, 28, 24, 24),
                child: ListView(
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Image.asset(
                            GlameAssets.logoSilver,
                            height: 46,
                            alignment: Alignment.centerLeft,
                            fit: BoxFit.contain,
                          ),
                        ),
                        IconButton(
                          tooltip: 'Закрыть',
                          onPressed: () => Navigator.of(ctx).pop(),
                          style: IconButton.styleFrom(
                            foregroundColor: GlameColors.whiteGlame,
                            backgroundColor: Colors.transparent,
                            shape: const RoundedRectangleBorder(),
                          ),
                          icon: const Icon(Icons.close, size: 22),
                        ),
                      ],
                    ),
                    const SizedBox(height: 28),
                    _GlameMenuRoute('Главная', '/home'),
                    _GlameMenuRoute('Украшения', '/home?tab=1'),
                    _GlameMenuRoute('Мой стиль', '/home?tab=2'),
                    _GlameMenuRoute('Подбор', '/home?tab=3'),
                    _GlameMenuRoute('Профиль', '/home?tab=4'),
                    _GlameMenuRoute('Образы', '/home?tab=5'),
                    const SizedBox(height: 16),
                    _GlameMenuRoute('Новинки', '/home?tab=6'),
                    _GlameMenuRoute('Бренды', '/brands'),
                    _GlameMenuRoute('Пространства', '/spaces'),
                    _GlameMenuRoute('Подарочный сертификат', '/home?tab=8'),
                    const SizedBox(height: 16),
                    _GlameMenuRoute('Корзина', '/home?tab=11'),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
    },
    transitionBuilder: (context, animation, _, child) {
      final curved = CurvedAnimation(parent: animation, curve: Curves.easeOut);
      return SlideTransition(
        position: Tween<Offset>(
          begin: const Offset(-1, 0),
          end: Offset.zero,
        ).animate(curved),
        child: child,
      );
    },
  );
}

class _GlameMenuRoute extends StatelessWidget {
  final String label;
  final String route;

  const _GlameMenuRoute(this.label, this.route);

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () {
        Navigator.of(context).pop();
        context.go(route);
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Text(
          label,
          style: const TextStyle(
            fontSize: 24,
            height: 1.05,
            color: GlameColors.whiteGlame,
          ),
        ),
      ),
    );
  }
}

ThemeData buildGlameTheme() {
  final scheme =
      ColorScheme.fromSeed(
        seedColor: GlameColors.graphite,
        brightness: Brightness.light,
      ).copyWith(
        surface: GlameColors.surface2,
        onSurface: GlameColors.textPrimary,
        primary: GlameColors.textPrimary,
        onPrimary: GlameColors.surface2,
        secondary: GlameColors.steelGray,
        onSecondary: GlameColors.textPrimary,
        outline: GlameColors.borderGray,
        surfaceContainerHighest: GlameColors.surface,
        onSurfaceVariant: GlameColors.textSecondary,
      );

  const baseText = TextTheme(
    headlineMedium: TextStyle(
      fontSize: 28,
      fontWeight: FontWeight.w400,
      letterSpacing: 0,
      color: GlameColors.textPrimary,
    ),
    titleLarge: TextStyle(
      fontSize: 22,
      fontWeight: FontWeight.w400,
      letterSpacing: 0,
      color: GlameColors.textPrimary,
    ),
    titleMedium: TextStyle(
      fontSize: 17,
      fontWeight: FontWeight.w400,
      color: GlameColors.textPrimary,
    ),
    bodyMedium: TextStyle(fontSize: 16, color: GlameColors.textPrimary),
    bodySmall: TextStyle(fontSize: 13, color: GlameColors.textSecondary),
  );

  return ThemeData(
    useMaterial3: true,
    fontFamily: 'Clinica Pro',
    colorScheme: scheme,
    scaffoldBackgroundColor: GlameColors.surface2,
    appBarTheme: const AppBarTheme(
      backgroundColor: GlameColors.surface2,
      foregroundColor: GlameColors.textPrimary,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: true,
      shape: Border(bottom: BorderSide(color: GlameColors.lightGray)),
      titleTextStyle: TextStyle(
        fontFamily: 'Clinica Pro',
        fontSize: 18,
        fontWeight: FontWeight.w400,
        color: GlameColors.textPrimary,
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: GlameColors.surface2,
      indicatorColor: Colors.transparent,
      elevation: 0,
      height: 74,
      surfaceTintColor: Colors.transparent,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      labelTextStyle: WidgetStateProperty.resolveWith((states) {
        final selected = states.contains(WidgetState.selected);
        return TextStyle(
          fontFamily: 'Clinica Pro',
          fontSize: 13,
          fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
          color: selected ? GlameColors.textPrimary : GlameColors.steelGray,
        );
      }),
      iconTheme: WidgetStateProperty.resolveWith((states) {
        final selected = states.contains(WidgetState.selected);
        return IconThemeData(
          color: selected ? GlameColors.textPrimary : GlameColors.steelGray,
        );
      }),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: scheme.primary,
        foregroundColor: scheme.onPrimary,
        shape: const RoundedRectangleBorder(),
        minimumSize: const Size.fromHeight(GlameUi.buttonHeight),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        textStyle: const TextStyle(
          fontFamily: 'Clinica Pro',
          fontSize: 16,
          fontWeight: FontWeight.w400,
          letterSpacing: 0.2,
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: scheme.onSurface,
        side: BorderSide(color: scheme.outline),
        shape: const RoundedRectangleBorder(),
        minimumSize: const Size.fromHeight(GlameUi.buttonHeight),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        textStyle: const TextStyle(
          fontFamily: 'Clinica Pro',
          fontSize: 16,
          fontWeight: FontWeight.w400,
          letterSpacing: 0.2,
        ),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: GlameColors.textPrimary,
        shape: const RoundedRectangleBorder(),
      ),
    ),
    inputDecorationTheme: const InputDecorationTheme(
      filled: true,
      fillColor: GlameColors.surface2,
      contentPadding: EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      isDense: true,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.zero,
        borderSide: BorderSide(color: GlameColors.lightGray),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.zero,
        borderSide: BorderSide(color: GlameColors.textPrimary),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.zero,
        borderSide: BorderSide(color: GlameColors.lightGray),
      ),
      disabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.zero,
        borderSide: BorderSide(color: GlameColors.lightGray),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.zero,
        borderSide: BorderSide(color: GlameColors.graphite),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.zero,
        borderSide: BorderSide(color: GlameColors.graphite),
      ),
      hintStyle: TextStyle(color: GlameColors.steelGray),
      labelStyle: TextStyle(color: GlameColors.textSecondary),
    ),
    checkboxTheme: CheckboxThemeData(
      shape: const RoundedRectangleBorder(),
      side: const BorderSide(color: GlameColors.lightGray),
      fillColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return GlameColors.textPrimary;
        }
        return Colors.transparent;
      }),
      checkColor: WidgetStateProperty.all(GlameColors.textPrimary),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(
        foregroundColor: GlameColors.textPrimary,
        shape: const RoundedRectangleBorder(),
      ),
    ),
    dividerTheme: const DividerThemeData(color: GlameColors.lightGray),
    cardTheme: CardThemeData(
      color: GlameColors.surface2,
      shape: const RoundedRectangleBorder(
        side: BorderSide(color: GlameColors.lightGray),
      ),
      elevation: 0,
    ),
    textTheme: baseText,
  );
}
