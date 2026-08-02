import 'package:flutter/material.dart';

const glameRuPhonePrefix = '+7';

String formatRuPhoneInput(String value) {
  var digits = value.replaceAll(RegExp(r'\D'), '');
  if (digits.startsWith('8')) {
    digits = digits.substring(1);
  }
  if (digits.startsWith('7')) {
    digits = digits.substring(1);
  }
  if (digits.length > 10) {
    digits = digits.substring(0, 10);
  }
  return '$glameRuPhonePrefix$digits';
}

bool isRuPhonePrefixOnly(String value) {
  return formatRuPhoneInput(value) == glameRuPhonePrefix;
}

bool isRuPhoneComplete(String value) {
  final digits = formatRuPhoneInput(value).replaceAll(RegExp(r'\D'), '');
  return digits.length == 11;
}

VoidCallback installRuPhonePrefixFormatter(TextEditingController controller) {
  var updating = false;

  void normalize() {
    if (updating) return;
    final next = formatRuPhoneInput(controller.text);
    if (controller.text == next) return;
    updating = true;
    controller.value = TextEditingValue(
      text: next,
      selection: TextSelection.collapsed(offset: next.length),
    );
    updating = false;
  }

  if (controller.text.trim().isEmpty) {
    controller.text = glameRuPhonePrefix;
  } else {
    normalize();
  }
  controller.addListener(normalize);
  return () => controller.removeListener(normalize);
}
