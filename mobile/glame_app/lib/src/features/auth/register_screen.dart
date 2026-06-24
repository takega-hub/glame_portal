import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/glame_theme.dart';
import 'auth_field.dart';
import 'auth_controller.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  final String? nextRoute;

  const RegisterScreen({super.key, this.nextRoute});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _phone = TextEditingController();
  final _password = TextEditingController();
  final _fullName = TextEditingController();
  DateTime? _birthDate;

  String? get _formattedBirthDate {
    final value = _birthDate;
    if (value == null) return null;
    return '${value.day.toString().padLeft(2, '0')}.${value.month.toString().padLeft(2, '0')}.${value.year}';
  }

  @override
  void dispose() {
    _phone.dispose();
    _password.dispose();
    _fullName.dispose();
    super.dispose();
  }

  Future<void> _selectDate(BuildContext context) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _birthDate ?? DateTime(2000),
      firstDate: DateTime(1900),
      lastDate: DateTime.now(),
    );
    if (picked != null && picked != _birthDate) {
      setState(() {
        _birthDate = picked;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final controller = ref.read(authControllerProvider.notifier);

    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      appBar: const GlameTopAppBar(dark: true),
      body: GlamePage(
        dark: true,
        safeTop: false,
        padding: EdgeInsets.zero,
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const GlameSectionHeader(
                title: 'РЕГИСТРАЦИЯ',
                subtitle:
                    'Создайте аккаунт, чтобы сохранять покупки и получать бонусы',
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
                controller: _fullName,
                label: 'Как к Вам обращаться',
                hintText: 'Имя и фамилия',
                dark: true,
              ),
              const SizedBox(height: 12),
              GestureDetector(
                onTap: () => _selectDate(context),
                child: AuthFieldShell(
                  label: 'Дата рождения (не обязательно)',
                  dark: true,
                  child: InputDecorator(
                    decoration: const InputDecoration(),
                    child: Text(
                      _formattedBirthDate ?? 'Выберите дату',
                      style: TextStyle(
                        color: _birthDate == null
                            ? GlameColors.steelGray
                            : GlameColors.textPrimary,
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              AuthTextField(
                controller: _password,
                label: 'Пароль (от 6 символов)',
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
                    auth.error!,
                    style: const TextStyle(color: GlameColors.coldLightGray),
                  ),
                ),
              const SizedBox(height: 24),
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
                        if (_fullName.text.trim().isEmpty) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Введите Ваше имя')),
                          );
                          return;
                        }
                        if (_password.text.length < 6) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Пароль слишком короткий'),
                            ),
                          );
                          return;
                        }
                        try {
                          await controller.registerPhone(
                            phone: _phone.text.trim(),
                            password: _password.text,
                            fullName: _fullName.text.trim(),
                            birthDate: _birthDate
                                ?.toIso8601String()
                                .split('T')
                                .first,
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
                    : const Text('Создать аккаунт'),
              ),
              const SizedBox(height: 12),
              OutlinedButton(
                style: OutlinedButton.styleFrom(
                  foregroundColor: GlameColors.whiteGlame,
                  side: const BorderSide(color: GlameColors.borderGray),
                  shape: const RoundedRectangleBorder(),
                ),
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
