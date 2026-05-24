import 'package:flutter/material.dart';

class GlameColors {
  static const graphite = Color(0xFF222426);
  static const nearBlack = Color(0xFF0E1012);
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
  static const double mobileBottomNavHeight = 96;
  static const double bottomNavContentAir = 24;
  static const double heroPrimaryButtonWidth = 300;
  static const double heroPrimaryButtonY = 602;
  static const double heroSecondaryButtonY = 676;
  static const double heroSlideIndicatorY = 768;
}

class GlameAssets {
  static const logoBlack = 'web/brand_assets/logos/glame_logo black.png';
  static const logoGraph = 'web/brand_assets/logos/glame_logo graph.png';
  static const logoSilver = 'web/brand_assets/logos/glame_logo silver.png';
  static const sign = 'web/brand_assets/logos/glame_sign.png';
}

class GlameHeaderLogo extends StatelessWidget {
  final double height;

  const GlameHeaderLogo({super.key, this.height = 24});

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      GlameAssets.logoBlack,
      height: height,
      fit: BoxFit.contain,
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
