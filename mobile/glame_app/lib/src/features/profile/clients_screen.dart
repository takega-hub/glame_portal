import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/theme/glame_theme.dart';

class ClientsScreen extends StatefulWidget {
  const ClientsScreen({super.key});

  static const _items = <_ClientInfoItem>[
    _ClientInfoItem(
      '01',
      'Условия покупки и использования приложения',
      assetPath: 'assets/documents/glame_purchase_app_terms.txt',
      originalFileName:
          '01_Условия_покупки_и_использования_приложения_GLAME.docx',
      prefKey: 'clients_doc_purchase_app_terms_read',
    ),
    _ClientInfoItem(
      '02',
      'Политика конфиденциальности',
      assetPath: 'assets/documents/glame_privacy_policy.txt',
      originalFileName: '02_Политика_конфиденциальности_GLAME.docx',
      prefKey: 'clients_doc_privacy_policy_read',
    ),
    _ClientInfoItem(
      '03',
      'Рекомендательные технологии',
      assetPath: 'assets/documents/glame_recommendation_rules.txt',
      originalFileName: '03_Правила_рекомендательных_технологий_GLAME.docx',
      prefKey: 'clients_doc_recommendation_rules_read',
    ),
  ];

  @override
  State<ClientsScreen> createState() => _ClientsScreenState();
}

class _ClientsScreenState extends State<ClientsScreen> {
  final Set<String> _readKeys = <String>{};

  @override
  void initState() {
    super.initState();
    _loadReadState();
  }

  Future<void> _loadReadState() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _readKeys
        ..clear()
        ..addAll(
          ClientsScreen._items
              .where((item) => item.prefKey != null)
              .where((item) => prefs.getBool(item.prefKey!) == true)
              .map((item) => item.prefKey!),
        );
    });
  }

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
                  for (final item in ClientsScreen._items)
                    _ClientInfoRow(
                      item: item,
                      isRead:
                          item.prefKey != null &&
                          _readKeys.contains(item.prefKey),
                      onTap: () => _openItem(context, item),
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

  Future<void> _openItem(BuildContext context, _ClientInfoItem item) async {
    if (item.assetPath == null || item.prefKey == null) {
      _showPlaceholder(context, item.title);
      return;
    }
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => _ClientDocumentScreen(
          item: item,
          initiallyRead: _readKeys.contains(item.prefKey),
          onReadChanged: (value) async {
            final prefs = await SharedPreferences.getInstance();
            await prefs.setBool(item.prefKey!, value);
            if (!mounted) return;
            setState(() {
              if (value) {
                _readKeys.add(item.prefKey!);
              } else {
                _readKeys.remove(item.prefKey!);
              }
            });
          },
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
  final String? assetPath;
  final String? originalFileName;
  final String? prefKey;

  const _ClientInfoItem(
    this.number,
    this.title, {
    this.assetPath,
    this.originalFileName,
    this.prefKey,
  });
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
  final bool isRead;
  final VoidCallback onTap;

  const _ClientInfoRow({
    required this.item,
    required this.isRead,
    required this.onTap,
  });

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
            if (isRead) ...[
              const Icon(
                Icons.check_box,
                color: GlameColors.whiteGlame,
                size: 20,
              ),
              const SizedBox(width: 12),
            ],
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

class _ClientDocumentScreen extends StatefulWidget {
  final _ClientInfoItem item;
  final bool initiallyRead;
  final ValueChanged<bool> onReadChanged;

  const _ClientDocumentScreen({
    required this.item,
    required this.initiallyRead,
    required this.onReadChanged,
  });

  @override
  State<_ClientDocumentScreen> createState() => _ClientDocumentScreenState();
}

class _ClientDocumentScreenState extends State<_ClientDocumentScreen> {
  late bool _read = widget.initiallyRead;
  late final Future<String> _textFuture = rootBundle.loadString(
    widget.item.assetPath!,
  );

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      body: SafeArea(
        child: Column(
          children: [
            _ClientsTopBar(onBack: () => Navigator.of(context).pop()),
            Expanded(
              child: FutureBuilder<String>(
                future: _textFuture,
                builder: (context, snapshot) {
                  if (snapshot.connectionState != ConnectionState.done) {
                    return const Center(
                      child: CircularProgressIndicator(
                        color: GlameColors.whiteGlame,
                      ),
                    );
                  }
                  final text =
                      snapshot.data ?? 'Не удалось загрузить документ.';
                  return ListView(
                    padding: const EdgeInsets.fromLTRB(
                      GlameUi.pagePadding,
                      24,
                      GlameUi.pagePadding,
                      120,
                    ),
                    children: [
                      Text(
                        widget.item.title,
                        style: const TextStyle(
                          color: GlameColors.whiteGlame,
                          fontSize: 25,
                          height: 1.14,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      if ((widget.item.originalFileName ?? '').isNotEmpty) ...[
                        const SizedBox(height: 10),
                        Text(
                          widget.item.originalFileName!,
                          style: const TextStyle(
                            color: GlameColors.coldLightGray,
                            fontSize: 12,
                            height: 1.35,
                          ),
                        ),
                      ],
                      const SizedBox(height: 22),
                      const Divider(height: 1, color: GlameColors.borderGray),
                      const SizedBox(height: 22),
                      Text(
                        text,
                        style: const TextStyle(
                          color: GlameColors.whiteGlame,
                          fontSize: 15,
                          height: 1.48,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                    ],
                  );
                },
              ),
            ),
            Container(
              padding: EdgeInsets.fromLTRB(
                GlameUi.pagePadding,
                12,
                GlameUi.pagePadding,
                12 + MediaQuery.paddingOf(context).bottom,
              ),
              decoration: const BoxDecoration(
                color: GlameColors.nearBlack,
                border: Border(top: BorderSide(color: GlameColors.borderGray)),
              ),
              child: InkWell(
                onTap: () => _setRead(!_read),
                child: Row(
                  children: [
                    Checkbox(
                      value: _read,
                      onChanged: (value) => _setRead(value ?? false),
                      checkColor: GlameColors.nearBlack,
                      activeColor: GlameColors.whiteGlame,
                      side: const BorderSide(color: GlameColors.borderGray),
                    ),
                    const SizedBox(width: 8),
                    const Expanded(
                      child: Text(
                        'Ознакомлен',
                        style: TextStyle(
                          color: GlameColors.whiteGlame,
                          fontSize: 17,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _setRead(bool value) {
    setState(() => _read = value);
    widget.onReadChanged(value);
  }
}

class _SupportPanel extends StatelessWidget {
  const _SupportPanel();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Divider(height: 1, color: GlameColors.borderGray),
        SizedBox(height: 22),
        Text(
          'Email',
          style: TextStyle(
            color: GlameColors.steelGray,
            fontSize: 12,
            height: 1,
            fontWeight: FontWeight.w600,
            letterSpacing: 1.2,
          ),
        ),
        SizedBox(height: 12),
        Text(
          'info@glamejewelry.ru',
          style: TextStyle(
            color: GlameColors.whiteGlame,
            fontSize: 18,
            height: 1.2,
            fontWeight: FontWeight.w400,
          ),
        ),
      ],
    );
  }
}
