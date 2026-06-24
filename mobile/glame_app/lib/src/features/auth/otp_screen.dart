import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/glame_theme.dart';
import 'auth_field.dart';
import 'auth_controller.dart';

class OtpScreen extends ConsumerStatefulWidget {
  final String phone;
  final String? nextRoute;

  const OtpScreen({super.key, required this.phone, this.nextRoute});

  @override
  ConsumerState<OtpScreen> createState() => _OtpScreenState();
}

class _OtpScreenState extends ConsumerState<OtpScreen> {
  final _code = TextEditingController();

  @override
  void dispose() {
    _code.dispose();
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
                'ПОДТВЕРЖДЕНИЕ',
                style: TextStyle(
                  fontSize: 40,
                  height: 0.95,
                  fontWeight: FontWeight.w400,
                  color: GlameColors.textPrimary,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                'Введите код из SMS, отправленный на номер ${widget.phone}',
                style: const TextStyle(
                  fontSize: 15,
                  height: 1.35,
                  color: GlameColors.textSecondary,
                ),
              ),
              const SizedBox(height: 18),
              Container(width: 44, height: 1, color: GlameColors.lightGray),
              const SizedBox(height: 24),
              AuthTextField(
                controller: _code,
                label: 'Код из SMS',
                hintText: 'Введите код',
                keyboardType: TextInputType.number,
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
              const SizedBox(height: 12),
              TextButton(
                onPressed: auth.loading ? null : () => context.pop(),
                style: TextButton.styleFrom(
                  alignment: Alignment.centerLeft,
                  padding: EdgeInsets.zero,
                ),
                child: const Text('Изменить номер'),
              ),
              const Spacer(),
              FilledButton(
                onPressed: auth.loading
                    ? null
                    : () async {
                        final go = GoRouter.of(context);
                        try {
                          final requireChange = await controller.loginOtp(
                            phone: widget.phone,
                            code: _code.text.trim(),
                          );
                          if (!mounted) return;

                          if (requireChange) {
                            // Переход на экран смены пароля
                            go.pushReplacement(
                              '/auth/change-password',
                              extra: widget.nextRoute,
                            );
                          } else {
                            final n = widget.nextRoute;
                            go.go(
                              (n != null && n.isNotEmpty) ? n : '/home?tab=4',
                            );
                          }
                        } catch (_) {}
                      },
                child: auth.loading
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Подтвердить'),
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
