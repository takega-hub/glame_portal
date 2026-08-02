import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../theme/glame_theme.dart';

class GlameBottomBar extends StatelessWidget {
  final int selectedIndex;

  const GlameBottomBar({super.key, required this.selectedIndex});

  @override
  Widget build(BuildContext context) {
    final hasBottomInset = MediaQuery.of(context).padding.bottom > 0;
    final bottomAir = hasBottomInset ? 4.0 : 0.0;

    void openTab(int index) {
      context.go(index == 0 ? '/home' : '/home?tab=$index');
    }

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
              _BottomNavItem(
                semanticsLabel: 'Главная',
                label: '',
                icon: const _BottomNavGlameSign(),
                selected: selectedIndex == 0,
                onTap: () => openTab(0),
              ),
              _BottomNavItem(
                semanticsLabel: 'Украшения',
                label: 'Украшения',
                icon: const _BottomNavRingIcon(),
                selected: selectedIndex == 1,
                onTap: () => openTab(1),
              ),
              _BottomNavItem(
                semanticsLabel: 'Мой стиль',
                label: 'Мой стиль',
                icon: const _BottomNavSparkleIcon(),
                selected: selectedIndex == 2,
                onTap: () => openTab(2),
              ),
              _BottomNavItem(
                semanticsLabel: 'Подбор',
                label: 'Подбор',
                icon: const _BottomNavSelectionIcon(),
                selected: selectedIndex == 3,
                onTap: () => openTab(3),
              ),
              _BottomNavItem(
                semanticsLabel: 'Профиль',
                label: 'Профиль',
                icon: const _BottomNavProfileIcon(),
                selected: selectedIndex == 4,
                onTap: () => openTab(4),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BottomNavItem extends StatelessWidget {
  final String semanticsLabel;
  final String label;
  final Widget icon;
  final bool selected;
  final VoidCallback onTap;

  const _BottomNavItem({
    required this.semanticsLabel,
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Semantics(
        button: true,
        selected: selected,
        label: semanticsLabel,
        child: Tooltip(
          message: semanticsLabel,
          child: InkWell(
            onTap: onTap,
            child: Center(
              child: SizedBox(
                width: double.infinity,
                height: 58,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Positioned(
                      bottom: label.isEmpty ? 0 : 1,
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 160),
                        curve: Curves.easeOut,
                        width: selected ? 52 : 0,
                        height: 2,
                        decoration: BoxDecoration(
                          color: GlameColors.textPrimary,
                          borderRadius: BorderRadius.circular(99),
                        ),
                      ),
                    ),
                    Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        IconTheme(
                          data: IconThemeData(
                            size: label.isEmpty
                                ? selected
                                      ? 38
                                      : 36
                                : selected
                                ? 25
                                : 24,
                            color: selected
                                ? GlameColors.textPrimary
                                : GlameColors.textSecondary,
                          ),
                          child: AnimatedOpacity(
                            duration: const Duration(milliseconds: 160),
                            opacity: selected ? 1 : 0.68,
                            child: icon,
                          ),
                        ),
                        if (label.isNotEmpty) ...[
                          const SizedBox(height: 5),
                          Text(
                            label,
                            maxLines: 1,
                            softWrap: false,
                            style: TextStyle(
                              fontSize: 11,
                              height: 1,
                              letterSpacing: 0,
                              color: selected
                                  ? GlameColors.textPrimary
                                  : GlameColors.textSecondary,
                              fontWeight: selected
                                  ? FontWeight.w500
                                  : FontWeight.w400,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _BottomNavGlameSign extends StatelessWidget {
  const _BottomNavGlameSign();

  @override
  Widget build(BuildContext context) {
    final iconTheme = IconTheme.of(context);
    final size = iconTheme.size ?? 23;
    return SizedBox(
      width: size,
      height: size,
      child: Image.asset(
        'assets/icons/glame_sign.png',
        fit: BoxFit.contain,
        filterQuality: FilterQuality.high,
      ),
    );
  }
}

class _BottomNavRingIcon extends StatelessWidget {
  const _BottomNavRingIcon();

  @override
  Widget build(BuildContext context) {
    return _BottomNavPaintedIcon(
      painterBuilder: (color) => _RingIconPainter(color),
    );
  }
}

class _BottomNavSparkleIcon extends StatelessWidget {
  const _BottomNavSparkleIcon();

  @override
  Widget build(BuildContext context) {
    return _BottomNavPaintedIcon(
      painterBuilder: (color) => _SparkleIconPainter(color),
    );
  }
}

class _BottomNavSelectionIcon extends StatelessWidget {
  const _BottomNavSelectionIcon();

  @override
  Widget build(BuildContext context) {
    return _BottomNavPaintedIcon(
      painterBuilder: (color) => _SelectionIconPainter(color),
    );
  }
}

class _BottomNavProfileIcon extends StatelessWidget {
  const _BottomNavProfileIcon();

  @override
  Widget build(BuildContext context) {
    return _BottomNavPaintedIcon(
      painterBuilder: (color) => _ProfileIconPainter(color),
    );
  }
}

class _BottomNavPaintedIcon extends StatelessWidget {
  final CustomPainter Function(Color color) painterBuilder;

  const _BottomNavPaintedIcon({required this.painterBuilder});

  @override
  Widget build(BuildContext context) {
    final iconTheme = IconTheme.of(context);
    final color = iconTheme.color ?? GlameColors.textSecondary;
    final size = iconTheme.size ?? 28;
    return SizedBox.square(
      dimension: size,
      child: CustomPaint(painter: painterBuilder(color)),
    );
  }
}

class _RingIconPainter extends CustomPainter {
  final Color color;

  const _RingIconPainter(this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = size.width * 0.075
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    canvas.drawCircle(size.center(Offset.zero), size.width * 0.33, stroke);
  }

  @override
  bool shouldRepaint(covariant _RingIconPainter oldDelegate) {
    return oldDelegate.color != color;
  }
}

class _SparkleIconPainter extends CustomPainter {
  final Color color;

  const _SparkleIconPainter(this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = size.width * 0.07
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final path = ui.Path()
      ..moveTo(size.width * 0.5, size.height * 0.08)
      ..lineTo(size.width * 0.62, size.height * 0.38)
      ..lineTo(size.width * 0.92, size.height * 0.5)
      ..lineTo(size.width * 0.62, size.height * 0.62)
      ..lineTo(size.width * 0.5, size.height * 0.92)
      ..lineTo(size.width * 0.38, size.height * 0.62)
      ..lineTo(size.width * 0.08, size.height * 0.5)
      ..lineTo(size.width * 0.38, size.height * 0.38)
      ..close();
    canvas.drawPath(path, stroke);
  }

  @override
  bool shouldRepaint(covariant _SparkleIconPainter oldDelegate) {
    return oldDelegate.color != color;
  }
}

class _SelectionIconPainter extends CustomPainter {
  final Color color;

  const _SelectionIconPainter(this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = size.width * 0.075
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    canvas.drawLine(
      Offset(size.width * 0.18, size.height * 0.26),
      Offset(size.width * 0.82, size.height * 0.26),
      stroke,
    );
    canvas.drawLine(
      Offset(size.width * 0.3, size.height * 0.5),
      Offset(size.width * 0.7, size.height * 0.5),
      stroke,
    );
    canvas.drawLine(
      Offset(size.width * 0.5, size.height * 0.5),
      Offset(size.width * 0.5, size.height * 0.82),
      stroke,
    );
  }

  @override
  bool shouldRepaint(covariant _SelectionIconPainter oldDelegate) {
    return oldDelegate.color != color;
  }
}

class _ProfileIconPainter extends CustomPainter {
  final Color color;

  const _ProfileIconPainter(this.color);

  @override
  void paint(Canvas canvas, Size size) {
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = size.width * 0.075
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    canvas.drawCircle(
      Offset(size.width * 0.5, size.height * 0.32),
      size.width * 0.22,
      stroke,
    );
    canvas.drawArc(
      Rect.fromCenter(
        center: Offset(size.width * 0.5, size.height * 0.84),
        width: size.width * 0.78,
        height: size.height * 0.52,
      ),
      3.58,
      2.26,
      false,
      stroke,
    );
  }

  @override
  bool shouldRepaint(covariant _ProfileIconPainter oldDelegate) {
    return oldDelegate.color != color;
  }
}
