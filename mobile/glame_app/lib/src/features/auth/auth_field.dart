import 'package:flutter/material.dart';

import '../../core/theme/glame_theme.dart';

class AuthFieldShell extends StatelessWidget {
  final String label;
  final Widget child;
  final bool dark;

  const AuthFieldShell({
    super.key,
    required this.label,
    required this.child,
    this.dark = false,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 2, bottom: 7),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 14,
              height: 1.1,
              color: dark
                  ? GlameColors.coldLightGray
                  : GlameColors.textSecondary,
            ),
          ),
        ),
        child,
      ],
    );
  }
}

class AuthTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hintText;
  final TextInputType? keyboardType;
  final bool obscureText;
  final bool dark;

  const AuthTextField({
    super.key,
    required this.controller,
    required this.label,
    required this.hintText,
    this.keyboardType,
    this.obscureText = false,
    this.dark = false,
  });

  @override
  Widget build(BuildContext context) {
    return AuthFieldShell(
      label: label,
      dark: dark,
      child: TextField(
        controller: controller,
        keyboardType: keyboardType,
        obscureText: obscureText,
        style: const TextStyle(color: GlameColors.textPrimary),
        decoration: InputDecoration(hintText: hintText),
      ),
    );
  }
}
