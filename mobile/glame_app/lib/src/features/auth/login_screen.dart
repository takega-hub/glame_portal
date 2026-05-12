import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/glame_theme.dart';
import 'auth_controller.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _phone = TextEditingController();
  final _password = TextEditingController();

  @override
  void initState() {
    super.initState();
    // Очищаем ошибку при входе на экран
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(authControllerProvider.notifier).clearError();
    });
  }

  @override
  void dispose() {
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
      appBar: AppBar(title: const GlameHeaderLogo()),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'ВХОД',
                style: TextStyle(
                  fontSize: 40,
                  height: 0.95,
                  fontWeight: FontWeight.w400,
                  color: GlameColors.textPrimary,
                ),
              ),
              const SizedBox(height: 10),
              const Text(
                'Вход для покупателей',
                style: TextStyle(
                  fontSize: 15,
                  height: 1.35,
                  color: GlameColors.textSecondary,
                ),
              ),
              const SizedBox(height: 18),
              Container(width: 44, height: 1, color: GlameColors.lightGray),
              const SizedBox(height: 24),
              TextField(
                controller: _phone,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                  labelText: 'Номер телефона',
                  hintText: '+7 900 000-00-00',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _password,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'Пароль',
                  hintText: 'Введите пароль',
                ),
              ),
              const SizedBox(height: 16),
              if (auth.error != null)
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    border: Border.all(color: GlameColors.graphite),
                  ),
                  child: Text(
                    auth.error == 'not_found'
                        ? 'Нет такого пользователя'
                        : auth.error!,
                    style: const TextStyle(color: GlameColors.graphite),
                  ),
                ),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () async {
                    if (_phone.text.trim().isEmpty) {
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
                      await controller.requestOtp(phone: _phone.text.trim());
                      final currentState = ref.read(authControllerProvider);
                      if (currentState.error != null) {
                        return;
                      }

                      if (!context.mounted) return;
                      GoRouter.of(context).push(
                        '/auth/otp?phone=${Uri.encodeComponent(_phone.text.trim())}&next=${Uri.encodeComponent(next ?? '')}',
                      );
                    } catch (_) {}
                  },
                  child: const Text('Войти по SMS'),
                ),
              ),
              const Spacer(),
              FilledButton(
                onPressed: auth.loading
                    ? null
                    : () async {
                        final go = GoRouter.of(context);
                        if (_phone.text.trim().isEmpty ||
                            _password.text.isEmpty) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Введите телефон и пароль'),
                            ),
                          );
                          return;
                        }
                        await controller.login(
                          email: _phone.text.trim(),
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
      ),
    );
  }
}
