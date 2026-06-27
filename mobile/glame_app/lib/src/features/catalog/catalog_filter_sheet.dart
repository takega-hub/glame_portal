import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../../core/theme/glame_theme.dart';

class CatalogFiltersDraft {
  final int? priceMin;
  final int? priceMax;
  final String? brand;
  final String? material;
  final String? vstavka;
  final String? pokrytie;
  final String? razmer;
  final String? tipZamka;
  final String? color;
  final String? sort;

  const CatalogFiltersDraft({
    required this.priceMin,
    required this.priceMax,
    required this.brand,
    required this.material,
    required this.vstavka,
    required this.pokrytie,
    required this.razmer,
    required this.tipZamka,
    required this.color,
    required this.sort,
  });
}

typedef CatalogFilterCountLoader =
    Future<int> Function(CatalogFiltersDraft draft);

class CatalogFilterSheet extends StatefulWidget {
  final CatalogFiltersDraft initial;
  final Map<String, dynamic> characteristics;
  final CatalogFilterCountLoader? countLoader;

  const CatalogFilterSheet({
    super.key,
    required this.initial,
    required this.characteristics,
    this.countLoader,
  });

  @override
  State<CatalogFilterSheet> createState() => _CatalogFilterSheetState();
}

class _CatalogFilterSheetState extends State<CatalogFilterSheet> {
  late final TextEditingController priceMin;
  late final TextEditingController priceMax;

  String? brand;
  String? material;
  String? vstavka;
  String? pokrytie;
  String? razmer;
  String? tipZamka;
  String? color;
  String? sort;
  Timer? _countDebounce;
  int? _matchingCount;
  bool _loadingCount = false;
  int _countRequestId = 0;

  @override
  void initState() {
    super.initState();
    priceMin = TextEditingController(
      text: widget.initial.priceMin != null
          ? _rub(widget.initial.priceMin!)
          : '',
    );
    priceMax = TextEditingController(
      text: widget.initial.priceMax != null
          ? _rub(widget.initial.priceMax!)
          : '',
    );
    brand = widget.initial.brand;
    material = widget.initial.material;
    vstavka = widget.initial.vstavka;
    pokrytie = widget.initial.pokrytie;
    razmer = widget.initial.razmer;
    tipZamka = widget.initial.tipZamka;
    color = widget.initial.color;
    sort = widget.initial.sort;
    priceMin.addListener(_scheduleCountRefresh);
    priceMax.addListener(_scheduleCountRefresh);
    _scheduleCountRefresh(immediate: true);
  }

  @override
  void dispose() {
    _countDebounce?.cancel();
    priceMin.dispose();
    priceMax.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final brandValues = _characteristicValues(widget.characteristics, 'Бренд');
    final colorValues = _characteristicValues(widget.characteristics, 'Цвет');
    final sizeValues = _characteristicValues(widget.characteristics, 'Размер');
    final insertValues = _characteristicValues(
      widget.characteristics,
      'Вставка',
    );
    final materialValues = _characteristicValues(
      widget.characteristics,
      'Материал',
    );
    final pokrytieValues = _characteristicValues(
      widget.characteristics,
      'Покрытие',
    );
    final tipZamkaValues = _characteristicValues(
      widget.characteristics,
      'Тип замка',
    );

    return SafeArea(
      top: false,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.9,
        ),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: GlameColors.nearBlack,
            border: Border.all(color: GlameColors.borderGray.withAlpha(150)),
            borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
          ),
          child: Column(
            children: [
              _Header(onReset: _reset),
              Expanded(
                child: SingleChildScrollView(
                  padding: EdgeInsets.fromLTRB(
                    16,
                    14,
                    16,
                    16 + MediaQuery.of(context).viewInsets.bottom,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _PriceFields(priceMin: priceMin, priceMax: priceMax),
                      const SizedBox(height: 18),
                      _FilterSection(
                        title: 'Сортировка',
                        children: [
                          _ChoiceRow(
                            label: 'По новизне',
                            selected: sort == 'newest',
                            onTap: () => _toggleSort('newest'),
                          ),
                          _ChoiceRow(
                            label: 'По цене: дешевле',
                            selected: sort == 'price_asc',
                            onTap: () => _toggleSort('price_asc'),
                          ),
                          _ChoiceRow(
                            label: 'По цене: дороже',
                            selected: sort == 'price_desc',
                            onTap: () => _toggleSort('price_desc'),
                          ),
                        ],
                      ),
                      _FilterSection(
                        title: 'Бренд',
                        children: _choiceRows(
                          brandValues,
                          selected: brand,
                          onSelect: (value) {
                            setState(() => brand = value);
                            _scheduleCountRefresh();
                          },
                        ),
                      ),
                      _FilterSection(
                        title: 'Цвет',
                        children: _choiceRows(
                          colorValues,
                          selected: color,
                          onSelect: (value) {
                            setState(() => color = value);
                            _scheduleCountRefresh();
                          },
                        ),
                      ),
                      _FilterSection(
                        title: 'Размер',
                        children: _choiceRows(
                          sizeValues,
                          selected: razmer,
                          onSelect: (value) {
                            setState(() => razmer = value);
                            _scheduleCountRefresh();
                          },
                        ),
                      ),
                      _FilterSection(
                        title: 'Вставка',
                        children: _choiceRows(
                          insertValues,
                          selected: vstavka,
                          onSelect: (value) {
                            setState(() => vstavka = value);
                            _scheduleCountRefresh();
                          },
                        ),
                      ),
                      _FilterSection(
                        title: 'Материал',
                        children: _choiceRows(
                          materialValues,
                          selected: material,
                          onSelect: (value) {
                            setState(() => material = value);
                            _scheduleCountRefresh();
                          },
                        ),
                      ),
                      _FilterSection(
                        title: 'Покрытие',
                        children: _choiceRows(
                          pokrytieValues,
                          selected: pokrytie,
                          onSelect: (value) {
                            setState(() => pokrytie = value);
                            _scheduleCountRefresh();
                          },
                        ),
                      ),
                      _FilterSection(
                        title: 'Тип замка',
                        children: _choiceRows(
                          tipZamkaValues,
                          selected: tipZamka,
                          onSelect: (value) {
                            setState(() => tipZamka = value);
                            _scheduleCountRefresh();
                          },
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 10, 16, 16),
                child: SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: FilledButton(
                    onPressed: _apply,
                    child: Text(_buttonLabel()),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _choiceRows(
    List<String> values, {
    required String? selected,
    required ValueChanged<String?> onSelect,
  }) {
    if (values.isEmpty) {
      return const [
        Padding(
          padding: EdgeInsets.only(bottom: 10),
          child: Text(
            'Нет доступных значений',
            style: TextStyle(fontSize: 13, color: GlameColors.textSecondary),
          ),
        ),
      ];
    }
    return values
        .map(
          (value) => _ChoiceRow(
            label: value,
            selected: selected == value,
            onTap: () => onSelect(selected == value ? null : value),
          ),
        )
        .toList();
  }

  void _toggleSort(String value) {
    setState(() {
      sort = sort == value ? null : value;
    });
    _scheduleCountRefresh();
  }

  void _reset() {
    setState(() {
      priceMin.text = '';
      priceMax.text = '';
      brand = null;
      material = null;
      vstavka = null;
      pokrytie = null;
      razmer = null;
      tipZamka = null;
      color = null;
      sort = null;
    });
    _scheduleCountRefresh();
  }

  void _apply() {
    Navigator.of(context).pop(_draft());
  }

  CatalogFiltersDraft _draft() {
    return CatalogFiltersDraft(
      priceMin: _toKopeks(priceMin.text),
      priceMax: _toKopeks(priceMax.text),
      brand: _norm(brand),
      material: _norm(material),
      vstavka: _norm(vstavka),
      pokrytie: _norm(pokrytie),
      razmer: _norm(razmer),
      tipZamka: _norm(tipZamka),
      color: _norm(color),
      sort: _norm(sort),
    );
  }

  void _scheduleCountRefresh({bool immediate = false}) {
    if (widget.countLoader == null) return;
    _countDebounce?.cancel();
    final delay = immediate ? Duration.zero : const Duration(milliseconds: 350);
    _countDebounce = Timer(delay, _refreshCount);
  }

  Future<void> _refreshCount() async {
    final loader = widget.countLoader;
    if (loader == null) return;
    final requestId = ++_countRequestId;
    setState(() {
      _loadingCount = true;
    });
    try {
      final count = await loader(_draft());
      if (!mounted || requestId != _countRequestId) return;
      setState(() {
        _matchingCount = count;
        _loadingCount = false;
      });
    } catch (_) {
      if (!mounted || requestId != _countRequestId) return;
      setState(() {
        _matchingCount = null;
        _loadingCount = false;
      });
    }
  }

  String _buttonLabel() {
    if (_loadingCount) return 'Считаем товары...';
    final count = _matchingCount;
    if (count == null) return 'Показать товары';
    return 'Показать $count ${_productsWord(count)}';
  }
}

class _Header extends StatelessWidget {
  final VoidCallback onReset;

  const _Header({required this.onReset});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Align(
          alignment: Alignment.center,
          child: Container(
            width: 42,
            height: 3,
            margin: const EdgeInsets.only(top: 12, bottom: 12),
            decoration: BoxDecoration(
              color: GlameColors.borderGray,
              borderRadius: BorderRadius.circular(999),
            ),
          ),
        ),
        SizedBox(
          height: 42,
          child: Row(
            children: [
              IconButton(
                tooltip: 'Закрыть',
                onPressed: () => Navigator.of(context).maybePop(),
                icon: const Icon(Icons.close, size: 20),
                color: GlameColors.whiteGlame,
              ),
              const Expanded(
                child: Text(
                  'Фильтры',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w600,
                    color: GlameColors.whiteGlame,
                  ),
                ),
              ),
              TextButton(
                onPressed: onReset,
                style: TextButton.styleFrom(
                  foregroundColor: GlameColors.textSecondary,
                ),
                child: const Text('Сбросить'),
              ),
            ],
          ),
        ),
        Divider(height: 1, color: GlameColors.borderGray.withAlpha(140)),
      ],
    );
  }
}

class _PriceFields extends StatelessWidget {
  final TextEditingController priceMin;
  final TextEditingController priceMax;

  const _PriceFields({required this.priceMin, required this.priceMax});

  @override
  Widget build(BuildContext context) {
    return _FilterSection(
      title: 'Цена',
      children: [
        Row(
          children: [
            Expanded(
              child: _PriceField(controller: priceMin, hint: 'От'),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _PriceField(controller: priceMax, hint: 'До'),
            ),
          ],
        ),
      ],
    );
  }
}

class _PriceField extends StatelessWidget {
  final TextEditingController controller;
  final String hint;

  const _PriceField({required this.controller, required this.hint});

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      keyboardType: TextInputType.number,
      style: const TextStyle(color: GlameColors.whiteGlame, fontSize: 15),
      decoration: InputDecoration(
        hintText: '$hint, ₽',
        hintStyle: const TextStyle(color: GlameColors.textSecondary),
        filled: true,
        fillColor: GlameColors.surface2,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 12,
        ),
        enabledBorder: const OutlineInputBorder(
          borderRadius: BorderRadius.zero,
          borderSide: BorderSide(color: GlameColors.borderGray),
        ),
        focusedBorder: const OutlineInputBorder(
          borderRadius: BorderRadius.zero,
          borderSide: BorderSide(color: GlameColors.whiteGlame),
        ),
      ),
    );
  }
}

class _FilterSection extends StatelessWidget {
  final String title;
  final List<Widget> children;

  const _FilterSection({required this.title, required this.children});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            title.toUpperCase(),
            style: const TextStyle(
              fontSize: 11,
              letterSpacing: 1,
              color: GlameColors.textSecondary,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 10),
          ...children,
        ],
      ),
    );
  }
}

class _ChoiceRow extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _ChoiceRow({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 11),
        child: Row(
          children: [
            Container(
              width: 16,
              height: 16,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: selected ? GlameColors.whiteGlame : Colors.transparent,
                border: Border.all(color: GlameColors.borderGray),
              ),
              child: selected
                  ? const Icon(
                      Icons.check,
                      size: 12,
                      color: GlameColors.nearBlack,
                    )
                  : null,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                label,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 13,
                  height: 1.2,
                  color: GlameColors.whiteGlame,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

List<String> _list(dynamic v) {
  if (v is List) {
    final values = v
        .whereType<String>()
        .map(_repairMojibake)
        .map((x) => x.trim())
        .where((x) => x.isNotEmpty)
        .toSet()
        .toList();
    values.sort((a, b) => a.toLowerCase().compareTo(b.toLowerCase()));
    return values;
  }
  return const [];
}

List<String> _characteristicValues(
  Map<String, dynamic> characteristics,
  String label,
) {
  final exact = _list(characteristics[label]);
  if (exact.isNotEmpty) return exact;

  for (final entry in characteristics.entries) {
    final key = _repairMojibake(entry.key).trim();
    if (key == label) {
      return _list(entry.value);
    }
  }
  return const [];
}

String _repairMojibake(String value) {
  final canDecodeAsBytes = value.codeUnits.every((unit) => unit <= 255);
  if (!canDecodeAsBytes) return value;
  try {
    final repaired = utf8.decode(value.codeUnits, allowMalformed: false);
    return repaired.runes.any((rune) => rune > 127) ? repaired : value;
  } catch (_) {
    return value;
  }
}

String _rub(int kopeks) {
  return (kopeks ~/ 100).toString();
}

String _productsWord(int count) {
  final lastTwo = count % 100;
  if (lastTwo >= 11 && lastTwo <= 14) return 'товаров';
  return switch (count % 10) {
    1 => 'товар',
    2 || 3 || 4 => 'товара',
    _ => 'товаров',
  };
}

int? _toKopeks(String raw) {
  final normalized = raw.trim().replaceAll(RegExp(r'[^0-9]'), '');
  if (normalized.isEmpty) return null;
  final n = int.tryParse(normalized);
  if (n == null) return null;
  return n * 100;
}

String? _norm(String? v) {
  final s = (v ?? '').trim();
  return s.isEmpty ? null : s;
}
