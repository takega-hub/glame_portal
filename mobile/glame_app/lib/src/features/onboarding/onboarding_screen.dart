import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/glame_theme.dart';
import 'onboarding_controller.dart';

class OnboardingScreen extends ConsumerStatefulWidget {
  const OnboardingScreen({super.key});

  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  final controller = PageController();
  int page = 0;

  final pages = const [
    _OnboardingPage(
      title: 'Тройной контроль качества',
      subtitle:
          'Каждое изделие проходит несколько этапов проверки перед тем, как попасть к вам.',
      icon: Icons.verified_outlined,
    ),
    _OnboardingPage(
      title: 'Ручная работа',
      subtitle: 'Гипоаллергенные сплавы и внимание к деталям в каждой линии.',
      icon: Icons.handyman_outlined,
    ),
    _OnboardingPage(
      title: 'Расширенная гарантия',
      subtitle: 'Мы уверены в качестве и поддерживаем вас после покупки.',
      icon: Icons.shield_outlined,
    ),
    _OnboardingPage(
      title: 'Программа лояльности',
      subtitle: 'Бонусы и привилегии для постоянных клиентов.',
      icon: Icons.star_border,
    ),
  ];

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final last = page == pages.length - 1;
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
          child: Column(
            children: [
              Row(
                children: [
                  const Expanded(
                    child: Text(
                      'GLAME',
                      style: TextStyle(
                        fontSize: 14,
                        letterSpacing: 0.4,
                        color: GlameColors.textSecondary,
                      ),
                    ),
                  ),
                  Text(
                    '${page + 1}/${pages.length}',
                    style: const TextStyle(
                      fontSize: 13,
                      color: GlameColors.textSecondary,
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Spacer(),
                  TextButton(
                    onPressed: () async {
                      await ref
                          .read(onboardingControllerProvider.notifier)
                          .complete();
                    },
                    style: TextButton.styleFrom(
                      foregroundColor: GlameColors.textSecondary,
                    ),
                    child: const Text('Пропустить'),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              Container(
                alignment: Alignment.centerLeft,
                child: Container(
                  width: 44,
                  height: 1,
                  color: GlameColors.lightGray,
                ),
              ),
              const SizedBox(height: 20),
              Expanded(
                child: PageView.builder(
                  controller: controller,
                  itemCount: pages.length,
                  onPageChanged: (i) => setState(() => page = i),
                  itemBuilder: (context, i) => pages[i],
                ),
              ),
              const SizedBox(height: 18),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(pages.length, (i) {
                  final active = i == page;
                  return AnimatedContainer(
                    duration: const Duration(milliseconds: 180),
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    height: 6,
                    width: active ? 24 : 8,
                    decoration: BoxDecoration(
                      color: active
                          ? GlameColors.textPrimary
                          : GlameColors.textSecondary.withAlpha(120),
                      border: Border.all(
                        color: active
                            ? GlameColors.textPrimary
                            : Colors.transparent,
                      ),
                    ),
                  );
                }),
              ),
              const SizedBox(height: 18),
              FilledButton(
                onPressed: () async {
                  if (!last) {
                    await controller.nextPage(
                      duration: const Duration(milliseconds: 220),
                      curve: Curves.easeOut,
                    );
                    return;
                  }
                  await ref
                      .read(onboardingControllerProvider.notifier)
                      .complete();
                },
                child: Text(last ? 'Начать' : 'Далее'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _OnboardingPage extends StatelessWidget {
  final String title;
  final String subtitle;
  final IconData icon;

  const _OnboardingPage({
    required this.title,
    required this.subtitle,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(22, 28, 22, 28),
          decoration: BoxDecoration(
            color: GlameColors.surface2,
            border: Border.all(color: GlameColors.lightGray),
          ),
          child: Column(
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: Icon(icon, color: GlameColors.gold, size: 34),
              ),
              const SizedBox(height: 28),
              Text(
                title.toUpperCase(),
                textAlign: TextAlign.left,
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontSize: 34,
                  height: 0.95,
                ),
              ),
              const SizedBox(height: 16),
              Text(
                subtitle,
                textAlign: TextAlign.left,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: GlameColors.textSecondary,
                  height: 1.45,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
