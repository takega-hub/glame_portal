import 'package:flutter/material.dart';

import '../theme/glame_theme.dart';

class GlameAuthGate extends StatelessWidget {
  final String eyebrow;
  final String title;
  final String description;
  final String note;
  final IconData noteIcon;
  final VoidCallback onLogin;
  final VoidCallback? onRegister;
  final String loginLabel;
  final String registerLabel;
  final bool dark;
  final bool showTopBar;

  const GlameAuthGate({
    super.key,
    required this.eyebrow,
    required this.title,
    required this.description,
    required this.note,
    required this.onLogin,
    this.onRegister,
    this.noteIcon = Icons.lock_outline,
    this.loginLabel = 'Войти',
    this.registerLabel = 'Создать аккаунт',
    this.dark = true,
    this.showTopBar = false,
  });

  @override
  Widget build(BuildContext context) {
    final background = dark ? GlameColors.nearBlack : GlameColors.surface2;
    final primary = dark ? GlameColors.whiteGlame : GlameColors.textPrimary;
    final secondary = dark
        ? GlameColors.coldLightGray
        : GlameColors.textSecondary;
    final line = dark ? GlameColors.borderGray : GlameColors.lightGray;

    final content = ListView(
      padding: const EdgeInsets.fromLTRB(24, 34, 24, 28),
      children: [
        Text(
          eyebrow.toUpperCase(),
          style: TextStyle(fontSize: 14, letterSpacing: 0.4, color: secondary),
        ),
        const SizedBox(height: 18),
        Text(
          title,
          style: TextStyle(
            fontSize: 32,
            height: 1.05,
            fontWeight: FontWeight.w300,
            color: primary,
          ),
        ),
        const SizedBox(height: 14),
        Text(
          description,
          style: TextStyle(fontSize: 16, height: 1.42, color: secondary),
        ),
        const SizedBox(height: 22),
        Container(height: 1, color: line),
        const SizedBox(height: 16),
        _GlameAuthGateNote(note: note, icon: noteIcon, color: secondary),
        const SizedBox(height: 22),
        SizedBox(
          height: GlameUi.buttonHeight,
          child: FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: dark
                  ? GlameColors.whiteGlame
                  : GlameColors.nearBlack,
              foregroundColor: dark
                  ? GlameColors.nearBlack
                  : GlameColors.whiteGlame,
              shape: const RoundedRectangleBorder(),
            ),
            onPressed: onLogin,
            child: Text(loginLabel),
          ),
        ),
        if (onRegister != null) ...[
          const SizedBox(height: 12),
          SizedBox(
            height: GlameUi.buttonHeight,
            child: OutlinedButton(
              style: OutlinedButton.styleFrom(
                foregroundColor: primary,
                side: BorderSide(color: line),
                shape: const RoundedRectangleBorder(),
              ),
              onPressed: onRegister,
              child: Text(registerLabel),
            ),
          ),
        ],
      ],
    );

    if (!showTopBar) {
      return ColoredBox(
        color: background,
        child: SafeArea(child: content),
      );
    }

    return Scaffold(
      backgroundColor: background,
      appBar: GlameTopAppBar(dark: dark),
      body: SafeArea(child: content),
    );
  }
}

class GlameAuthGateSheet extends StatelessWidget {
  final String title;
  final String description;
  final String note;
  final VoidCallback onLoginTap;
  final VoidCallback? onRegisterTap;
  final VoidCallback? onPhoneTap;

  const GlameAuthGateSheet({
    super.key,
    required this.title,
    required this.description,
    required this.note,
    required this.onLoginTap,
    this.onRegisterTap,
    this.onPhoneTap,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Container(
        margin: const EdgeInsets.all(16),
        padding: const EdgeInsets.fromLTRB(18, 24, 18, 16),
        decoration: const BoxDecoration(color: GlameColors.surface2),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              title,
              style: const TextStyle(
                fontSize: 24,
                height: 1.05,
                color: GlameColors.textPrimary,
              ),
            ),
            const SizedBox(height: 14),
            Text(
              description,
              style: const TextStyle(
                fontSize: 16,
                height: 1.42,
                color: GlameColors.textSecondary,
              ),
            ),
            const SizedBox(height: 16),
            Container(height: 1, color: GlameColors.lightGray),
            const SizedBox(height: 14),
            _GlameAuthGateNote(
              note: note,
              icon: Icons.autorenew,
              color: GlameColors.textSecondary,
            ),
            const SizedBox(height: 18),
            _GlameAuthSheetButton.primary(label: 'Войти', onTap: onLoginTap),
            if (onRegisterTap != null) ...[
              const SizedBox(height: 10),
              _GlameAuthSheetButton.secondary(
                label: 'Создать аккаунт',
                onTap: onRegisterTap!,
              ),
            ],
            if (onPhoneTap != null) ...[
              const SizedBox(height: 10),
              _GlameAuthSheetButton.secondary(
                label: 'Продолжить по номеру',
                icon: Icons.smartphone_outlined,
                onTap: onPhoneTap!,
              ),
            ],
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Не сейчас'),
            ),
          ],
        ),
      ),
    );
  }
}

class _GlameAuthGateNote extends StatelessWidget {
  final String note;
  final IconData icon;
  final Color color;

  const _GlameAuthGateNote({
    required this.note,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            note,
            style: TextStyle(fontSize: 14, height: 1.35, color: color),
          ),
        ),
      ],
    );
  }
}

class _GlameAuthSheetButton extends StatelessWidget {
  final String label;
  final IconData? icon;
  final VoidCallback onTap;
  final bool primary;

  const _GlameAuthSheetButton.primary({
    required this.label,
    required this.onTap,
  }) : icon = null,
       primary = true;

  const _GlameAuthSheetButton.secondary({
    required this.label,
    required this.onTap,
    this.icon,
  }) : primary = false;

  @override
  Widget build(BuildContext context) {
    final child = Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (icon != null) ...[Icon(icon, size: 18), const SizedBox(width: 8)],
        Text(label),
      ],
    );

    if (primary) {
      return SizedBox(
        height: GlameUi.buttonHeight,
        child: FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: GlameColors.nearBlack,
            foregroundColor: GlameColors.whiteGlame,
            shape: const RoundedRectangleBorder(),
          ),
          onPressed: onTap,
          child: child,
        ),
      );
    }

    return SizedBox(
      height: GlameUi.buttonHeight,
      child: OutlinedButton(
        style: OutlinedButton.styleFrom(
          foregroundColor: GlameColors.textPrimary,
          side: const BorderSide(color: GlameColors.lightGray),
          shape: const RoundedRectangleBorder(),
        ),
        onPressed: onTap,
        child: child,
      ),
    );
  }
}
