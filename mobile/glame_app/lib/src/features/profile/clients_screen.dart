import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class ClientsScreen extends StatelessWidget {
  const ClientsScreen({super.key});

  static const _items = <String>[
    'Доставка и оплата',
    'Условия возврата',
    'Политика конфиденциальности',
    'Публичная оферта',
    'Рекомендательные технологии',
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      body: SafeArea(
        child: Column(
          children: [
            SizedBox(
              height: 58,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Positioned(
                    left: 14,
                    child: IconButton(
                      onPressed: () => context.canPop()
                          ? context.pop()
                          : context.go('/home?tab=4'),
                      icon: const Icon(Icons.arrow_back, size: 22),
                      color: const Color(0xFF202124),
                      tooltip: 'Назад',
                    ),
                  ),
                  const Text(
                    'Клиентам',
                    style: TextStyle(
                      color: Color(0xFF202124),
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView.separated(
                padding: const EdgeInsets.fromLTRB(28, 36, 28, 24),
                itemCount: _items.length,
                separatorBuilder: (_, _) => const SizedBox(height: 30),
                itemBuilder: (context, index) {
                  return InkWell(
                    onTap: () => _showPlaceholder(context, _items[index]),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Text(
                        _items[index],
                        style: const TextStyle(
                          color: Color(0xFF202124),
                          fontSize: 18,
                          height: 1.25,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showPlaceholder(BuildContext context, String title) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('$title: документ будет добавлен позднее')),
    );
  }
}
