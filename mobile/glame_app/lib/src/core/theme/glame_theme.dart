import 'package:flutter/material.dart';

class GlameColors {
  // Legacy names are kept so the older dark UI can be converted in-place.
  static const black = Color(0xFFFFFFFF);
  static const white = Color(0xFF111111);
  static const surface = Color(0xFFF7F7F5);
  static const surface2 = Color(0xFFFFFFFF);
  static const lightGray = Color(0xFFE8E5DF);
  static const steelGray = Color(0xFF989898);
  static const coolLightGray = Color(0xFFD2D2D2);
  static const gold = Color(0xFFE0A526);
  static const graphite = Color(0xFF2B2B2A);
  static const steelGrey = Color(0xFF6F7376);
  static const coldLightGrey = Color(0xFFE5E7E8);
  static const textPrimary = Color(0xFF111111);
  static const textSecondary = Color(0xFF6A6863);
  static const warmGray = Color(0xFFF2F0EB);
}

class GlameUi {
  static const double radius = 0;
  static const double borderWidth = 1;
  static const double pagePadding = 28;
  static const double blockGap = 36;
  static const double buttonHeight = 56;
  static const double minTapTarget = 44;
}

class GlameAssets {
  static const logoBlack = 'web/brand_assets/logos/glame_logo black.png';
  static const logoGraph = 'web/brand_assets/logos/glame_logo graph.png';
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
        seedColor: GlameColors.gold,
        brightness: Brightness.light,
      ).copyWith(
        surface: GlameColors.textPrimary,
        onSurface: GlameColors.textPrimary,
        primary: GlameColors.textPrimary,
        onPrimary: GlameColors.surface2,
        secondary: GlameColors.steelGray,
        onSecondary: GlameColors.textPrimary,
        outline: GlameColors.lightGray,
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
        minimumSize: const Size.fromHeight(48),
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
        minimumSize: const Size.fromHeight(48),
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
