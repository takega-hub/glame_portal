import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

/// Shared viewport rules for the web and mobile storefront.
/// Content remains comfortably readable on a large desktop instead of growing
/// to the full browser width, while grids gain columns gradually.
class GlameLayout {
  static const double maxContentWidth = 1440;
  static const double desktopWebCanvasWidth = 1060;

  static double widthOf(BuildContext context) =>
      MediaQuery.sizeOf(context).width;

  static bool isTablet(BuildContext context) => widthOf(context) >= 720;

  static bool isDesktop(BuildContext context) => widthOf(context) >= 1024;

  static bool isWideDesktop(BuildContext context) => widthOf(context) >= 1360;

  /// Native Android/iOS builds keep the persistent tab bar. In a narrow web
  /// browser it takes too much vertical space, while the drawer stays
  /// available for navigation.
  static bool hidesBottomNavInCompactWeb(BuildContext context) =>
      kIsWeb && widthOf(context) < 600;

  /// On wide desktop browsers the storefront is presented as a focused app
  /// canvas rather than an endlessly stretched page. The app itself receives
  /// this same width through a scoped MediaQuery.
  static bool usesDesktopWebCanvas(BuildContext context) =>
      kIsWeb && widthOf(context) > desktopWebCanvasWidth;

  static double horizontalGutter(BuildContext context) {
    final width = widthOf(context);
    if (width >= 1360) return 48;
    if (width >= 720) return 32;
    return 20;
  }

  static int catalogColumns(BuildContext context) {
    final width = widthOf(context);
    if (width >= 1360) return 5;
    if (width >= 1024) return 4;
    if (width >= 720) return 3;
    return 2;
  }
}

class GlameContentWidth extends StatelessWidget {
  final Widget child;
  final double maxWidth;

  const GlameContentWidth({
    super.key,
    required this.child,
    this.maxWidth = GlameLayout.maxContentWidth,
  });

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: child,
      ),
    );
  }
}
