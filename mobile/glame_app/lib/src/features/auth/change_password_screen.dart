import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/glame_theme.dart';
import 'auth_field.dart';
import 'auth_controller.dart';

class ChangePasswordScreen extends ConsumerStatefulWidget {
  final String? nextRoute;

  const ChangePasswordScreen({super.key, this.nextRoute});

  @override
  ConsumerState<ChangePasswordScreen> createState() =>
      _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends ConsumerState<ChangePasswordScreen> {
  final _password = TextEditingController();

  @override
  void dispose() {
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final controller = ref.read(authControllerProvider.notifier);

    return Scaffold(
      appBar: const GlameTopAppBar(),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'НОВЫЙ ПАРОЛЬ',
                style: TextStyle(
                  fontSize: 40,
                  height: 0.95,
                  fontWeight: FontWeight.w400,
                  color: GlameColors.textPrimary,
                ),
              ),
              const SizedBox(height: 10),
              const Text(
                'Установите постоянный пароль для Вашего аккаунта',
                style: TextStyle(
                  fontSize: 15,
                  height: 1.35,
                  color: GlameColors.textSecondary,
                ),
              ),
              const SizedBox(height: 18),
              Container(width: 44, height: 1, color: GlameColors.lightGray),
              const SizedBox(height: 24),
              AuthTextField(
                controller: _password,
                label: 'Новый пароль (от 6 символов)',
                hintText: 'Введите новый пароль',
                obscureText: true,
              ),
              const SizedBox(height: 16),
              if (auth.error != null)
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    border: Border.all(color: GlameColors.graphite),
                  ),
                  child: Text(
                    auth.error!,
                    style: const TextStyle(color: GlameColors.graphite),
                  ),
                ),
              const Spacer(),
              FilledButton(
                onPressed: auth.loading
                    ? null
                    : () async {
                        final go = GoRouter.of(context);
                        if (_password.text.length < 6) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Пароль слишком короткий'),
                            ),
                          );
                          return;
                        }
                        try {
                          await controller.changePassword(
                            newPassword: _password.text,
                          );
                          if (!mounted) return;
                          final n = widget.nextRoute;
                          go.go(
                            (n != null && n.isNotEmpty) ? n : '/home?tab=4',
                          );
                        } catch (_) {}
                      },
                child: auth.loading
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Сохранить и войти'),
              ),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: auth.loading ? null : () => context.pop(),
                child: const Text('Назад'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
