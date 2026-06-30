import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/glame_theme.dart';

class ClientsScreen extends StatelessWidget {
  const ClientsScreen({super.key});

  static const _items = <_ClientInfoItem>[
    _ClientInfoItem('01', 'Доставка и оплата'),
    _ClientInfoItem('02', 'Условия возврата'),
    _ClientInfoItem('03', 'Политика конфиденциальности'),
    _ClientInfoItem('04', 'Публичная оферта'),
    _ClientInfoItem('05', 'Рекомендательные технологии'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      body: SafeArea(
        child: Column(
          children: [
            _ClientsTopBar(
              onBack: () =>
                  context.canPop() ? context.pop() : context.go('/home?tab=4'),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(0, 34, 0, 34),
                children: [
                  const Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: GlameUi.pagePadding,
                    ),
                    child: Text(
                      'Клиентам',
                      style: TextStyle(
                        color: GlameColors.whiteGlame,
                        fontSize: 28,
                        height: 1.14,
                        fontWeight: FontWeight.w500,
                        letterSpacing: 0,
                      ),
                    ),
                  ),
                  const SizedBox(height: 30),
                  const Divider(height: 1, color: GlameColors.borderGray),
                  for (final item in _items)
                    _ClientInfoRow(
                      item: item,
                      onTap: () => _showPlaceholder(context, item.title),
                    ),
                  const SizedBox(height: 48),
                  const Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: GlameUi.pagePadding,
                    ),
                    child: _SupportPanel(),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showPlaceholder(BuildContext context, String title) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('$title: документ будет добавлен позднее'),
        backgroundColor: GlameColors.graphite,
      ),
    );
  }
}

class _ClientInfoItem {
  final String number;
  final String title;

  const _ClientInfoItem(this.number, this.title);
}

class _ClientsTopBar extends StatelessWidget {
  final VoidCallback onBack;

  const _ClientsTopBar({required this.onBack});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 58,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Positioned(
            left: 4,
            child: IconButton(
              onPressed: onBack,
              icon: const Icon(Icons.arrow_back, size: 23),
              color: GlameColors.whiteGlame,
              tooltip: 'Назад',
            ),
          ),
          const GlameHeaderLogo(height: 24, silver: true),
        ],
      ),
    );
  }
}

class _ClientInfoRow extends StatelessWidget {
  final _ClientInfoItem item;
  final VoidCallback onTap;

  const _ClientInfoRow({required this.item, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      splashColor: GlameColors.whiteGlame.withValues(alpha: 0.06),
      highlightColor: GlameColors.whiteGlame.withValues(alpha: 0.04),
      child: Container(
        constraints: const BoxConstraints(minHeight: 76),
        padding: const EdgeInsets.symmetric(horizontal: GlameUi.pagePadding),
        decoration: const BoxDecoration(
          border: Border(
            bottom: BorderSide(color: GlameColors.borderGray, width: 1),
          ),
        ),
        child: Row(
          children: [
            SizedBox(
              width: 42,
              child: Text(
                item.number,
                style: const TextStyle(
                  color: GlameColors.steelGray,
                  fontSize: 12,
                  height: 1,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.2,
                ),
              ),
            ),
            Expanded(
              child: Text(
                item.title,
                style: const TextStyle(
                  color: GlameColors.whiteGlame,
                  fontSize: 18,
                  height: 1.25,
                  fontWeight: FontWeight.w400,
                ),
              ),
            ),
            const SizedBox(width: 14),
            const Icon(
              Icons.chevron_right,
              color: GlameColors.coldLightGray,
              size: 26,
            ),
          ],
        ),
      ),
    );
  }
}

class _SupportPanel extends StatelessWidget {
  const _SupportPanel();

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Divider(height: 1, color: GlameColors.borderGray),
        const SizedBox(height: 22),
        const Text(
          'CONTACT & SUPPORT',
          style: TextStyle(
            color: GlameColors.coldLightGray,
            fontSize: 11,
            height: 1,
            fontWeight: FontWeight.w600,
            letterSpacing: 2.2,
          ),
        ),
        const SizedBox(height: 22),
        Row(
          children: const [
            Expanded(
              child: _SupportTile(number: '01', title: 'WHATSAPP'),
            ),
            SizedBox(width: 1),
            Expanded(
              child: _SupportTile(number: '02', title: 'TELEGRAM'),
            ),
          ],
        ),
      ],
    );
  }
}

class _SupportTile extends StatelessWidget {
  final String number;
  final String title;

  const _SupportTile({required this.number, required this.title});

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 1,
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: GlameColors.nearBlack,
          border: Border.all(color: GlameColors.borderGray, width: 1),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              number,
              style: const TextStyle(
                color: GlameColors.steelGray,
                fontSize: 12,
                fontWeight: FontWeight.w600,
                letterSpacing: 1.1,
              ),
            ),
            const Spacer(),
            Text(
              title,
              style: const TextStyle(
                color: GlameColors.whiteGlame,
                fontSize: 14,
                fontWeight: FontWeight.w500,
                letterSpacing: 0.6,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
