import 'package:flutter/material.dart';

import '../../core/theme/glame_theme.dart';

class CatalogFiltersDraft {
  final int? priceMin;
  final int? priceMax;
  final String? material;
  final String? pokrytie;
  final String? tipZamka;
  final String? sort;

  const CatalogFiltersDraft({
    required this.priceMin,
    required this.priceMax,
    required this.material,
    required this.pokrytie,
    required this.tipZamka,
    required this.sort,
  });
}

class CatalogFilterSheet extends StatefulWidget {
  final CatalogFiltersDraft initial;
  final Map<String, dynamic> characteristics;

  const CatalogFilterSheet({
    super.key,
    required this.initial,
    required this.characteristics,
  });

  @override
  State<CatalogFilterSheet> createState() => _CatalogFilterSheetState();
}

class _CatalogFilterSheetState extends State<CatalogFilterSheet> {
  late final TextEditingController priceMin;
  late final TextEditingController priceMax;

  String? material;
  String? pokrytie;
  String? tipZamka;
  String? sort;

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
    material = widget.initial.material;
    pokrytie = widget.initial.pokrytie;
    tipZamka = widget.initial.tipZamka;
    sort = widget.initial.sort;
  }

  @override
  void dispose() {
    priceMin.dispose();
    priceMax.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final materialValues = _list(widget.characteristics['Материал']);
    final pokrytieValues = _list(widget.characteristics['Покрытие']);
    final tipZamkaValues = _list(widget.characteristics['Тип замка']);

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Фильтры',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                TextButton(
                  onPressed: () {
                    setState(() {
                      priceMin.text = '';
                      priceMax.text = '';
                      material = null;
                      pokrytie = null;
                      tipZamka = null;
                      sort = null;
                    });
                  },
                  style: TextButton.styleFrom(
                    foregroundColor: GlameColors.textSecondary,
                  ),
                  child: const Text('Сбросить'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: priceMin,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Цена от (₽)'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: priceMax,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Цена до (₽)'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            _Dropdown(
              label: 'Сортировка',
              value: sort,
              items: const [
                _DropdownItem(value: 'newest', label: 'По новизне'),
                _DropdownItem(value: 'price_asc', label: 'По цене (возр.)'),
                _DropdownItem(value: 'price_desc', label: 'По цене (убыв.)'),
              ],
              onChanged: (v) => setState(() => sort = v),
            ),
            const SizedBox(height: 10),
            _Dropdown(
              label: 'Материал',
              value: material,
              items: materialValues
                  .map((x) => _DropdownItem(value: x, label: x))
                  .toList(),
              onChanged: (v) => setState(() => material = v),
            ),
            const SizedBox(height: 10),
            _Dropdown(
              label: 'Покрытие',
              value: pokrytie,
              items: pokrytieValues
                  .map((x) => _DropdownItem(value: x, label: x))
                  .toList(),
              onChanged: (v) => setState(() => pokrytie = v),
            ),
            const SizedBox(height: 10),
            _Dropdown(
              label: 'Тип замка',
              value: tipZamka,
              items: tipZamkaValues
                  .map((x) => _DropdownItem(value: x, label: x))
                  .toList(),
              onChanged: (v) => setState(() => tipZamka = v),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () {
                Navigator.of(context).pop(
                  CatalogFiltersDraft(
                    priceMin: _toKopeks(priceMin.text),
                    priceMax: _toKopeks(priceMax.text),
                    material: _norm(material),
                    pokrytie: _norm(pokrytie),
                    tipZamka: _norm(tipZamka),
                    sort: _norm(sort),
                  ),
                );
              },
              child: const Text('Применить'),
            ),
          ],
        ),
      ),
    );
  }
}

class _DropdownItem {
  final String value;
  final String label;

  const _DropdownItem({required this.value, required this.label});
}

class _Dropdown extends StatelessWidget {
  final String label;
  final String? value;
  final List<_DropdownItem> items;
  final ValueChanged<String?> onChanged;

  const _Dropdown({
    required this.label,
    required this.value,
    required this.items,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<String>(
      key: ValueKey(value),
      initialValue: value,
      decoration: InputDecoration(labelText: label),
      items: [
        const DropdownMenuItem(value: null, child: Text('Любой')),
        ...items.map(
          (x) => DropdownMenuItem(value: x.value, child: Text(x.label)),
        ),
      ],
      onChanged: onChanged,
    );
  }
}

List<String> _list(dynamic v) {
  if (v is List) {
    return v
        .whereType<String>()
        .map((x) => x.trim())
        .where((x) => x.isNotEmpty)
        .toList();
  }
  return const [];
}

String _rub(int kopeks) {
  return (kopeks ~/ 100).toString();
}

int? _toKopeks(String raw) {
  final v = raw.trim();
  if (v.isEmpty) return null;
  final n = int.tryParse(v);
  if (n == null) return null;
  return n * 100;
}

String? _norm(String? v) {
  final s = (v ?? '').trim();
  return s.isEmpty ? null : s;
}
