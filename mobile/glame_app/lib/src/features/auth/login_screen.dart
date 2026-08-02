import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters/phone.dart';
import '../../core/theme/glame_theme.dart';
import 'auth_field.dart';
import 'auth_controller.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _phone = TextEditingController();
  final _password = TextEditingController();
  late final VoidCallback _removePhoneFormatter;

  @override
  void initState() {
    super.initState();
    _removePhoneFormatter = installRuPhonePrefixFormatter(_phone);
    // Очищаем ошибку при входе на экран
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(authControllerProvider.notifier).clearError();
    });
  }

  @override
  void dispose() {
    _removePhoneFormatter();
    _phone.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final controller = ref.read(authControllerProvider.notifier);
    final next = GoRouterState.of(context).uri.queryParameters['next'];

    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      appBar: const GlameTopAppBar(dark: true),
      body: GlamePage(
        dark: true,
        safeTop: false,
        padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const GlameSectionHeader(
              title: 'ВХОД',
              subtitle: 'Вход для покупателей',
              dark: true,
            ),
            const SizedBox(height: 24),
            AuthTextField(
              controller: _phone,
              label: 'Номер телефона',
              hintText: '+7 900 000-00-00',
              keyboardType: TextInputType.phone,
              dark: true,
            ),
            const SizedBox(height: 12),
            AuthTextField(
              controller: _password,
              label: 'Пароль',
              hintText: 'Введите пароль',
              obscureText: true,
              dark: true,
            ),
            const SizedBox(height: 16),
            if (auth.error != null)
              GlamePanel(
                dark: true,
                padding: const EdgeInsets.all(12),
                child: Text(
                  auth.error == 'not_found'
                      ? 'Нет такого пользователя'
                      : auth.error!,
                  style: const TextStyle(color: GlameColors.coldLightGray),
                ),
              ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () async {
                  final phone = formatRuPhoneInput(_phone.text);
                  if (!isRuPhoneComplete(phone)) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text(
                          'Введите номер телефона для получения кода',
                        ),
                      ),
                    );
                    return;
                  }
                  try {
                    await controller.requestOtp(phone: phone);
                    final currentState = ref.read(authControllerProvider);
                    if (currentState.error != null) {
                      return;
                    }

                    if (!context.mounted) return;
                    GoRouter.of(context).push(
                      '/auth/otp?phone=${Uri.encodeComponent(phone)}&next=${Uri.encodeComponent(next ?? '')}',
                    );
                  } catch (_) {}
                },
                style: TextButton.styleFrom(
                  foregroundColor: GlameColors.whiteGlame,
                ),
                child: const Text('Войти по SMS'),
              ),
            ),
            const Spacer(),
            FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: GlameColors.whiteGlame,
                foregroundColor: GlameColors.nearBlack,
                shape: const RoundedRectangleBorder(),
              ),
              onPressed: auth.loading
                  ? null
                  : () async {
                      final go = GoRouter.of(context);
                      final phone = formatRuPhoneInput(_phone.text);
                      if (!isRuPhoneComplete(phone) || _password.text.isEmpty) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Введите телефон и пароль'),
                          ),
                        );
                        return;
                      }
                      await controller.login(
                        email: phone,
                        password: _password.text,
                      );
                      if (!mounted) return;
                      final after = ref.read(authControllerProvider);
                      if (after.user != null) {
                        go.go(
                          (next != null && next.isNotEmpty)
                              ? next
                              : '/home?tab=4',
                        );
                      }
                    },
              child: auth.loading
                  ? const SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Войти'),
            ),
            const SizedBox(height: 12),
            OutlinedButton(
              style: OutlinedButton.styleFrom(
                foregroundColor: GlameColors.whiteGlame,
                side: const BorderSide(color: GlameColors.borderGray),
                shape: const RoundedRectangleBorder(),
              ),
              onPressed: auth.loading
                  ? null
                  : () {
                      GoRouter.of(context).push(
                        '/auth/register?next=${Uri.encodeComponent(next ?? '')}',
                      );
                    },
              child: const Text('Регистрация'),
            ),
          ],
        ),
      ),
    );
  }
}
