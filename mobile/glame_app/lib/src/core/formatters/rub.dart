import 'dart:math' as math;

int? _parseInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value.trim());
  return null;
}

String _groupThousands(int value) {
  final s = value.toString();
  if (s.length <= 3) return s;
  final buf = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    final posFromEnd = s.length - i;
    buf.write(s[i]);
    if (posFromEnd > 1 && posFromEnd % 3 == 1) buf.write(' ');
  }
  return buf.toString();
}

String formatRubFromKopeks(dynamic rawKopeks) {
  final kopeks = _parseInt(rawKopeks);
  if (kopeks == null) return '';
  final sign = kopeks < 0 ? '-' : '';
  final abs = kopeks.abs();
  final rub = abs ~/ 100;
  final rubStr = _groupThousands(rub);
  return '$sign$rubStr ₽';
}

int discountedPriceKopeks(int basePriceKopeks, int loyaltyPoints) {
  if (basePriceKopeks <= 0 || loyaltyPoints <= 0) return basePriceKopeks;
  final maxDiscountByRule = (basePriceKopeks * 0.1).round();
  final availableByPoints = loyaltyPoints * 100;
  final discount = math.min(maxDiscountByRule, availableByPoints);
  return math.max(0, basePriceKopeks - discount);
}
