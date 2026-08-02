import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/formatters/phone.dart';
import '../../core/theme/glame_theme.dart';
import '../auth/auth_controller.dart';
import '../customer/customer_cabinet_providers.dart';
import 'gift_certificate_api.dart';

class GiftCertificateScreen extends ConsumerStatefulWidget {
  const GiftCertificateScreen({super.key});

  @override
  ConsumerState<GiftCertificateScreen> createState() =>
      _GiftCertificateScreenState();
}

class _GiftCertificateScreenState extends ConsumerState<GiftCertificateScreen> {
  final _phoneController = TextEditingController();
  final _emailController = TextEditingController();
  final _nameController = TextEditingController();
  final _messageController = TextEditingController();
  final _senderController = TextEditingController();
  final _amountController = TextEditingController(text: '5 000');

  late final VoidCallback _removePhoneFormatter;

  int _step = 0;
  int _amount = 5000;
  int _design = 0;
  bool _sendLater = false;
  bool _submitting = false;
  bool _checkingPayment = false;
  DateTime? _sendAt;
  Map<String, dynamic>? _purchaseResult;

  static const _amounts = [3000, 5000, 10000, 20000];
  static const _minAmount = 1000;
  static const _maxAmount = 100000;

  @override
  void initState() {
    super.initState();
    _removePhoneFormatter = installRuPhonePrefixFormatter(_phoneController);
  }

  @override
  void dispose() {
    _removePhoneFormatter();
    _phoneController.dispose();
    _emailController.dispose();
    _nameController.dispose();
    _messageController.dispose();
    _senderController.dispose();
    _amountController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: GlameColors.nearBlack,
      child: SafeArea(
        top: false,
        bottom: false,
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(28, 28, 28, 28),
                children: [
                  _StepHeader(
                    step: _step,
                    title: switch (_step) {
                      0 => 'Номинал',
                      1 => 'Кому и когда',
                      _ => 'Оплата',
                    },
                  ),
                  const SizedBox(height: 30),
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 180),
                    child: switch (_step) {
                      0 => _DesignStep(
                        key: const ValueKey('amount'),
                        amount: _amount,
                        design: _design,
                        amountController: _amountController,
                        onAmountChanged: (value) =>
                            _setAmount(value, syncInput: true),
                        onCustomAmountChanged: _setCustomAmount,
                        onDesignChanged: (value) =>
                            setState(() => _design = value),
                      ),
                      1 => _RecipientStep(
                        key: const ValueKey('recipient'),
                        amount: _amount,
                        design: _design,
                        phoneController: _phoneController,
                        emailController: _emailController,
                        nameController: _nameController,
                        messageController: _messageController,
                        senderController: _senderController,
                        sendLater: _sendLater,
                        sendAt: _sendAt,
                        onSendModeChanged: (later) {
                          setState(() => _sendLater = later);
                          if (later && _sendAt == null) {
                            _pickSendDateTime();
                          }
                        },
                        onPickDate: _pickSendDateTime,
                      ),
                      _ => _PaymentStep(
                        key: const ValueKey('payment'),
                        amount: _amount,
                        design: _design,
                        phone: _phoneController.text,
                        email: _emailController.text,
                        recipientName: _nameController.text,
                        sendLater: _sendLater,
                        sendAt: _sendAt,
                        purchaseResult: _purchaseResult,
                        checkingPayment: _checkingPayment,
                        onEditRecipient: () => setState(() => _step = 1),
                        onEditAmount: () => setState(() => _step = 0),
                        onCheckPayment: () => _checkPaymentStatus(),
                      ),
                    },
                  ),
                ],
              ),
            ),
            _BottomActionBar(
              step: _step,
              submitting: _submitting,
              canGoBack: _step > 0,
              onBack: _submitting ? () {} : () => setState(() => _step -= 1),
              onNext: _handlePrimaryAction,
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _pickSendDateTime() async {
    final now = DateTime.now();
    final initial = _sendAt ?? now.add(const Duration(hours: 2));
    var selectedDate = DateTime(initial.year, initial.month, initial.day);
    var selectedHour = initial.hour;
    var selectedMinute = (initial.minute / 5).round() * 5;
    if (selectedMinute >= 60) {
      selectedMinute = 0;
      selectedHour = (selectedHour + 1) % 24;
    }

    final result = await showModalBottomSheet<DateTime>(
      context: context,
      isScrollControlled: true,
      backgroundColor: GlameColors.nearBlack,
      barrierColor: Colors.black.withValues(alpha: 0.62),
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            final candidate = DateTime(
              selectedDate.year,
              selectedDate.month,
              selectedDate.day,
              selectedHour,
              selectedMinute,
            );
            final isPast = candidate.isBefore(now);

            return SafeArea(
              top: false,
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  22,
                  18,
                  22,
                  18 + MediaQuery.viewInsetsOf(context).bottom,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        const Expanded(
                          child: Text(
                            'Дата и время отправки',
                            style: TextStyle(
                              color: GlameColors.whiteGlame,
                              fontSize: 22,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                        IconButton(
                          onPressed: () => Navigator.pop(sheetContext),
                          icon: const Icon(
                            Icons.close,
                            color: GlameColors.whiteGlame,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Theme(
                      data: Theme.of(context).copyWith(
                        colorScheme: const ColorScheme.dark(
                          primary: GlameColors.whiteGlame,
                          onPrimary: GlameColors.nearBlack,
                          surface: GlameColors.nearBlack,
                          onSurface: GlameColors.whiteGlame,
                        ),
                        textButtonTheme: TextButtonThemeData(
                          style: TextButton.styleFrom(
                            foregroundColor: GlameColors.whiteGlame,
                          ),
                        ),
                      ),
                      child: CalendarDatePicker(
                        initialDate: selectedDate.isBefore(now)
                            ? DateTime(now.year, now.month, now.day)
                            : selectedDate,
                        firstDate: DateTime(now.year, now.month, now.day),
                        lastDate: now.add(const Duration(days: 365)),
                        onDateChanged: (date) {
                          setSheetState(() {
                            selectedDate = DateTime(
                              date.year,
                              date.month,
                              date.day,
                            );
                          });
                        },
                      ),
                    ),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        Expanded(
                          child: _TimeSelect(
                            label: 'Час',
                            value: selectedHour,
                            values: List.generate(24, (index) => index),
                            onChanged: (value) =>
                                setSheetState(() => selectedHour = value),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: _TimeSelect(
                            label: 'Минуты',
                            value: selectedMinute,
                            values: List.generate(12, (index) => index * 5),
                            onChanged: (value) =>
                                setSheetState(() => selectedMinute = value),
                          ),
                        ),
                      ],
                    ),
                    if (isPast) ...[
                      const SizedBox(height: 12),
                      const Text(
                        'Выберите время позже текущего.',
                        style: TextStyle(
                          color: GlameColors.textSecondary,
                          fontSize: 13,
                        ),
                      ),
                    ],
                    const SizedBox(height: 18),
                    FilledButton(
                      onPressed: isPast
                          ? null
                          : () => Navigator.pop(sheetContext, candidate),
                      style: FilledButton.styleFrom(
                        minimumSize: const Size.fromHeight(54),
                        backgroundColor: GlameColors.whiteGlame,
                        disabledBackgroundColor: GlameColors.borderGray,
                        foregroundColor: GlameColors.nearBlack,
                        shape: const RoundedRectangleBorder(),
                      ),
                      child: const Text('СОХРАНИТЬ'),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );

    if (result == null || !mounted) return;
    setState(() => _sendAt = result);
  }

  void _handlePrimaryAction() {
    if (_submitting) return;
    if (_step == 0) {
      if (_amount < _minAmount) {
        _showMessage('Минимальная сумма сертификата ${_formatRub(_minAmount)}');
        return;
      }
      if (_amount > _maxAmount) {
        _showMessage(
          'Максимальная сумма сертификата ${_formatRub(_maxAmount)}',
        );
        return;
      }
      setState(() => _step = 1);
      return;
    }

    if (_step == 1) {
      final recipientPhone = formatRuPhoneInput(_phoneController.text);
      final hasPhone = !isRuPhonePrefixOnly(recipientPhone);
      if (!hasPhone && _emailController.text.trim().isEmpty) {
        _showMessage('Укажите телефон или эл. почту получателя');
        return;
      }
      if (hasPhone && !isRuPhoneComplete(recipientPhone)) {
        _showMessage('Введите корректный номер телефона получателя');
        return;
      }
      if (_sendLater && _sendAt == null) {
        _showMessage('Выберите дату и время отправки');
        return;
      }
      setState(() => _step = 2);
      return;
    }

    if (_purchaseResult != null) {
      _openPaymentUrl(_purchaseResult!);
      return;
    }

    _purchaseCertificate();
  }

  Future<void> _purchaseCertificate() async {
    if (ref.read(authControllerProvider).user == null) {
      _showMessage('Войдите, чтобы купить сертификат');
      context.go('/login?next=${Uri.encodeComponent('/home?tab=8')}');
      return;
    }

    setState(() => _submitting = true);
    try {
      final api = ref.read(giftCertificateApiProvider);
      final origin = Uri.base.origin;
      final recipientPhone = formatRuPhoneInput(_phoneController.text);
      final resp = await api.purchase(
        amountKopeks: _amount * 100,
        returnUrl: origin,
        recipientName: _nameController.text,
        recipientPhone: isRuPhonePrefixOnly(recipientPhone)
            ? ''
            : recipientPhone,
        recipientEmail: _emailController.text,
        message: _messageController.text,
        senderName: _senderController.text,
        design: _design,
        sendAt: _sendLater ? _sendAt : null,
      );
      if (!mounted) return;
      setState(() => _purchaseResult = resp);

      await _openPaymentUrl(resp);
      _schedulePaymentChecks();
      _showMessage(
        'Серия сертификата создана в 1С. После оплаты сертификат станет активным.',
      );
    } catch (_) {
      if (!mounted) return;
      _showMessage('Не удалось создать оплату сертификата');
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  Future<void> _openPaymentUrl(Map<String, dynamic> result) async {
    final confirmationUrl = (result['confirmation_url'] ?? '').toString();
    final uri = Uri.tryParse(confirmationUrl);
    if (uri == null) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  void _schedulePaymentChecks() {
    for (final delay in const [
      Duration(seconds: 3),
      Duration(seconds: 8),
      Duration(seconds: 15),
    ]) {
      Future<void>.delayed(delay, () {
        if (!mounted || _purchaseResult == null) return;
        _checkPaymentStatus(silent: true);
      });
    }
  }

  Future<void> _checkPaymentStatus({bool silent = false}) async {
    final result = _purchaseResult;
    final orderId = (result?['order_id'] ?? '').toString();
    if (orderId.isEmpty || _checkingPayment) return;

    setState(() => _checkingPayment = true);
    try {
      final api = ref.read(giftCertificateApiProvider);
      final status = await api.getPaymentStatus(orderId);
      final payment = status['payment'] is Map
          ? Map<String, dynamic>.from(status['payment'] as Map)
          : const <String, dynamic>{};
      final paymentStatus = (payment['status'] ?? '').toString();
      if (!mounted) return;
      setState(() {
        _purchaseResult = {
          ...?result,
          'order_status': status['order_status'],
          'payment': payment,
          'payment_status': paymentStatus,
        };
      });
      if (paymentStatus == 'succeeded') {
        ref.invalidate(customerGiftCertificatesProvider);
        if (!silent) {
          _showMessage('Оплата подтверждена. Сертификат активирован.');
        }
      } else if (!silent) {
        _showMessage('Оплата пока не подтверждена.');
      }
    } catch (_) {
      if (mounted && !silent) {
        _showMessage('Не удалось проверить оплату');
      }
    } finally {
      if (mounted) {
        setState(() => _checkingPayment = false);
      }
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: GlameColors.textPrimary,
      ),
    );
  }

  void _setAmount(int value, {required bool syncInput}) {
    setState(() => _amount = value);
    if (!syncInput) return;
    final nextText = _formatAmountInput(value);
    _amountController.value = TextEditingValue(
      text: nextText,
      selection: TextSelection.collapsed(offset: nextText.length),
    );
  }

  void _setCustomAmount(String value) {
    final amount = _parseAmountInput(value);
    setState(() => _amount = amount);
  }
}

class _StepHeader extends StatelessWidget {
  final int step;
  final String title;

  const _StepHeader({required this.step, required this.title});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          'ШАГ ${step + 1} ИЗ 3',
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontSize: 12,
            letterSpacing: 2.4,
            color: GlameColors.textSecondary,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 12),
        Text(
          title,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontFamily: 'Clinica Pro',
            fontSize: 25,
            height: 1.05,
            color: GlameColors.whiteGlame,
          ),
        ),
        const SizedBox(height: 18),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List.generate(3, (index) {
            return Container(
              width: 42,
              height: 3,
              margin: const EdgeInsets.symmetric(horizontal: 3),
              color: index <= step
                  ? GlameColors.whiteGlame
                  : GlameColors.borderGray,
            );
          }),
        ),
      ],
    );
  }
}

class _DesignStep extends StatelessWidget {
  final int amount;
  final int design;
  final TextEditingController amountController;
  final ValueChanged<int> onAmountChanged;
  final ValueChanged<String> onCustomAmountChanged;
  final ValueChanged<int> onDesignChanged;

  const _DesignStep({
    super.key,
    required this.amount,
    required this.design,
    required this.amountController,
    required this.onAmountChanged,
    required this.onCustomAmountChanged,
    required this.onDesignChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'Подарочный сертификат',
          style: TextStyle(
            fontFamily: 'Clinica Pro',
            fontSize: 28,
            height: 1.08,
            color: GlameColors.whiteGlame,
          ),
        ),
        const SizedBox(height: 24),
        _CertificatePreview(amount: amount, design: design),
        const SizedBox(height: 34),
        const Text('ВЫБЕРИТЕ ДИЗАЙН', style: _labelStyle),
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: _DesignButton(
                title: 'Светлый',
                asset:
                    'assets/images/gift_certificate/glame_gift_certificate_template_01.png',
                selected: design == 0,
                onTap: () => onDesignChanged(0),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: _DesignButton(
                title: 'Темный',
                asset:
                    'assets/images/gift_certificate/glame_gift_certificate_template_02.png',
                selected: design == 1,
                onTap: () => onDesignChanged(1),
              ),
            ),
          ],
        ),
        const SizedBox(height: 30),
        const Text('ВЫБЕРИТЕ НОМИНАЛ', style: _labelStyle),
        const SizedBox(height: 16),
        Wrap(
          spacing: 14,
          runSpacing: 14,
          children: _GiftCertificateScreenState._amounts.map((value) {
            return SizedBox(
              width: (MediaQuery.sizeOf(context).width - 70) / 2,
              child: _AmountButton(
                amount: value,
                selected: amount == value,
                onTap: () => onAmountChanged(value),
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: 18),
        _CustomAmountField(
          controller: amountController,
          selected: !_GiftCertificateScreenState._amounts.contains(amount),
          onChanged: onCustomAmountChanged,
        ),
        const SizedBox(height: 30),
        const Center(child: _TermsLink()),
      ],
    );
  }
}

class _RecipientStep extends StatelessWidget {
  final int amount;
  final int design;
  final TextEditingController phoneController;
  final TextEditingController emailController;
  final TextEditingController nameController;
  final TextEditingController messageController;
  final TextEditingController senderController;
  final bool sendLater;
  final DateTime? sendAt;
  final ValueChanged<bool> onSendModeChanged;
  final VoidCallback onPickDate;

  const _RecipientStep({
    super.key,
    required this.amount,
    required this.design,
    required this.phoneController,
    required this.emailController,
    required this.nameController,
    required this.messageController,
    required this.senderController,
    required this.sendLater,
    required this.sendAt,
    required this.onSendModeChanged,
    required this.onPickDate,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _CertificatePreview(amount: amount, design: design, compact: true),
        const SizedBox(height: 34),
        _DarkTextField(
          controller: phoneController,
          label: 'Номер телефона получателя',
          hint: '+7 ___ ___ __ __',
          keyboardType: TextInputType.phone,
        ),
        const SizedBox(height: 20),
        _DarkTextField(
          controller: emailController,
          label: 'Эл. почта получателя',
          hint: 'example@mail.com',
          keyboardType: TextInputType.emailAddress,
        ),
        const SizedBox(height: 20),
        _DarkTextField(
          controller: nameController,
          label: 'Имя получателя',
          hint: 'Введите имя',
        ),
        const SizedBox(height: 20),
        _DarkTextField(
          controller: messageController,
          label: 'Текст поздравления',
          hint: 'Ваше сообщение здесь...',
          maxLines: 4,
        ),
        const SizedBox(height: 20),
        _DarkTextField(
          controller: senderController,
          label: 'От кого',
          hint: 'Ваше имя',
        ),
        const SizedBox(height: 30),
        const Text('КОГДА ОТПРАВИТЬ', style: _labelStyle),
        const SizedBox(height: 14),
        _CheckRow(
          label: 'Сразу после покупки',
          selected: !sendLater,
          onTap: () => onSendModeChanged(false),
        ),
        const SizedBox(height: 12),
        _CheckRow(
          label: 'Указать дату и время',
          selected: sendLater,
          onTap: () => onSendModeChanged(true),
        ),
        if (sendLater) ...[
          const SizedBox(height: 14),
          _OutlineAction(
            label: sendAt == null
                ? 'Выбрать дату и время'
                : _formatDate(sendAt!),
            icon: Icons.schedule_outlined,
            onTap: onPickDate,
          ),
        ],
      ],
    );
  }
}

class _PaymentStep extends StatelessWidget {
  final int amount;
  final int design;
  final String phone;
  final String email;
  final String recipientName;
  final bool sendLater;
  final DateTime? sendAt;
  final Map<String, dynamic>? purchaseResult;
  final bool checkingPayment;
  final VoidCallback onEditRecipient;
  final VoidCallback onEditAmount;
  final VoidCallback onCheckPayment;

  const _PaymentStep({
    super.key,
    required this.amount,
    required this.design,
    required this.phone,
    required this.email,
    required this.recipientName,
    required this.sendLater,
    required this.sendAt,
    required this.purchaseResult,
    required this.checkingPayment,
    required this.onEditRecipient,
    required this.onEditAmount,
    required this.onCheckPayment,
  });

  @override
  Widget build(BuildContext context) {
    final certificate = purchaseResult?['certificate'] is Map
        ? Map<String, dynamic>.from(purchaseResult!['certificate'] as Map)
        : const <String, dynamic>{};
    final series = (certificate['series'] ?? certificate['number'] ?? '')
        .toString();
    final normalizedPhone = formatRuPhoneInput(phone);
    final phoneValue = isRuPhonePrefixOnly(normalizedPhone)
        ? 'Не указан'
        : normalizedPhone;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'ПОДАРОЧНЫЙ\nСЕРТИФИКАТ',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Clinica Pro',
            fontSize: 31,
            height: 1.12,
            color: GlameColors.whiteGlame,
          ),
        ),
        const SizedBox(height: 28),
        _CertificatePreview(
          amount: amount,
          design: design,
          compact: true,
          series: series.isEmpty ? null : series,
        ),
        const SizedBox(height: 30),
        _SummaryRow(
          label: 'Получатель',
          value: recipientName.trim().isEmpty ? 'Не указано' : recipientName,
          onTap: onEditRecipient,
        ),
        _SummaryRow(
          label: 'Телефон',
          value: phoneValue,
          onTap: onEditRecipient,
        ),
        _SummaryRow(
          label: 'Эл. почта',
          value: email.trim().isEmpty ? 'Не указана' : email,
          onTap: onEditRecipient,
        ),
        _SummaryRow(
          label: 'Дата отправки',
          value: sendLater && sendAt != null
              ? _formatDate(sendAt!)
              : 'Сразу после покупки',
          onTap: onEditRecipient,
        ),
        _SummaryRow(
          label: 'Макет',
          value: design == 1 ? 'Темный GLAME' : 'Светлый GLAME',
          onTap: onEditAmount,
        ),
        const SizedBox(height: 24),
        Row(
          children: [
            const Expanded(
              child: Text(
                'ИТОГО',
                style: TextStyle(
                  fontSize: 16,
                  letterSpacing: 5,
                  color: GlameColors.textSecondary,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            Text(
              _formatRub(amount),
              style: const TextStyle(
                fontSize: 45,
                height: 1,
                color: GlameColors.whiteGlame,
              ),
            ),
          ],
        ),
        const SizedBox(height: 28),
        if (purchaseResult != null) ...[
          _PurchaseResultCard(
            result: purchaseResult!,
            checkingPayment: checkingPayment,
            onCheckPayment: onCheckPayment,
          ),
          const SizedBox(height: 24),
        ],
        const Center(child: _TermsLink()),
      ],
    );
  }
}

class _PurchaseResultCard extends StatelessWidget {
  final Map<String, dynamic> result;
  final bool checkingPayment;
  final VoidCallback onCheckPayment;

  const _PurchaseResultCard({
    required this.result,
    required this.checkingPayment,
    required this.onCheckPayment,
  });

  @override
  Widget build(BuildContext context) {
    final certificate = result['certificate'] is Map
        ? Map<String, dynamic>.from(result['certificate'] as Map)
        : const <String, dynamic>{};
    final series = (certificate['series'] ?? certificate['number'] ?? '')
        .toString();
    final number = (certificate['number'] ?? series).toString();
    final onecSeriesRef = (certificate['onec_series_ref_key'] ?? '').toString();
    final pin = (result['pin'] ?? certificate['pin'] ?? '').toString();
    final confirmationUrl = (result['confirmation_url'] ?? '').toString();
    final payment = result['payment'] is Map
        ? Map<String, dynamic>.from(result['payment'] as Map)
        : const <String, dynamic>{};
    final paymentStatus = (result['payment_status'] ?? payment['status'] ?? '')
        .toString();
    final isPaid = paymentStatus == 'succeeded';

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: GlameColors.graphite,
        border: Border.all(color: GlameColors.borderGray),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'СЕРТИФИКАТ СОЗДАН',
            style: TextStyle(
              color: GlameColors.whiteGlame,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.6,
            ),
          ),
          const SizedBox(height: 12),
          if (series.isNotEmpty) _ResultLine(label: 'Серия', value: series),
          if (number.isNotEmpty && number != series) ...[
            const SizedBox(height: 8),
            _ResultLine(label: 'Номер', value: number),
          ],
          if (pin.isNotEmpty) ...[
            const SizedBox(height: 8),
            _ResultLine(label: 'PIN', value: pin),
          ],
          if (onecSeriesRef.isNotEmpty) ...[
            const SizedBox(height: 8),
            _ResultLine(label: '1С', value: onecSeriesRef),
          ],
          if (paymentStatus.isNotEmpty) ...[
            const SizedBox(height: 8),
            _ResultLine(
              label: 'Оплата',
              value: _paymentStatusText(paymentStatus),
            ),
          ],
          const SizedBox(height: 12),
          Text(
            isPaid
                ? 'Оплата подтверждена. Сертификат активен, серия отмечена в 1С как проданная.'
                : 'После оплаты сертификат станет активным, а серия будет отмечена в 1С как проданная. При покупке в магазине продавец проводит сертификат по серии.',
            style: const TextStyle(
              color: GlameColors.coldLightGray,
              height: 1.35,
            ),
          ),
          if (!isPaid && confirmationUrl.isNotEmpty) ...[
            const SizedBox(height: 14),
            OutlinedButton(
              onPressed: () async {
                final uri = Uri.tryParse(confirmationUrl);
                if (uri == null) return;
                await launchUrl(uri, mode: LaunchMode.externalApplication);
              },
              child: const Text('ПЕРЕЙТИ К ОПЛАТЕ'),
            ),
          ],
          const SizedBox(height: 10),
          OutlinedButton(
            onPressed: checkingPayment ? null : onCheckPayment,
            child: checkingPayment
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('ПРОВЕРИТЬ ОПЛАТУ'),
          ),
        ],
      ),
    );
  }
}

class _ResultLine extends StatelessWidget {
  final String label;
  final String value;

  const _ResultLine({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        SizedBox(
          width: 72,
          child: Text(label.toUpperCase(), style: _labelStyle),
        ),
        Expanded(
          child: SelectableText(
            value,
            style: const TextStyle(
              color: GlameColors.whiteGlame,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ],
    );
  }
}

class _CertificatePreview extends StatelessWidget {
  static const _templateAssets = [
    'assets/images/gift_certificate/glame_gift_certificate_template_01.png',
    'assets/images/gift_certificate/glame_gift_certificate_template_02.png',
  ];

  final int amount;
  final int design;
  final bool compact;
  final String? series;

  const _CertificatePreview({
    required this.amount,
    required this.design,
    this.compact = false,
    this.series,
  });

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 590 / 417,
      child: Container(
        decoration: BoxDecoration(color: GlameColors.whiteGlame),
        clipBehavior: Clip.hardEdge,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final width = constraints.maxWidth;
            final height = constraints.maxHeight;
            final hasSeries = series != null && series!.isNotEmpty;
            final isDark = design == 1;
            final textColor = isDark
                ? GlameColors.whiteGlame
                : const Color(0xFF707173);
            final asset = _templateAssets[design.clamp(0, 1).toInt()];

            return Stack(
              fit: StackFit.expand,
              children: [
                Image.asset(
                  asset,
                  fit: BoxFit.cover,
                  errorBuilder: (_, _, _) =>
                      const ColoredBox(color: GlameColors.whiteGlame),
                ),
                Positioned(
                  left: width * 0.08,
                  right: width * 0.08,
                  top: height * 0.28,
                  height: height * 0.41,
                  child: FittedBox(
                    fit: BoxFit.contain,
                    child: Text(
                      amount.toString(),
                      style: TextStyle(
                        fontFamily: 'Clinica Pro',
                        color: textColor,
                        fontWeight: FontWeight.w400,
                        letterSpacing: 0,
                      ),
                    ),
                  ),
                ),
                if (hasSeries)
                  Positioned(
                    left: width * 0.22,
                    right: width * 0.22,
                    top: height * 0.77,
                    child: Text(
                      'СЕРИЯ ${series!}',
                      textAlign: TextAlign.center,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: compact ? 9 : 11,
                        letterSpacing: 0.7,
                        color: textColor,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _DesignButton extends StatelessWidget {
  final String title;
  final String asset;
  final bool selected;
  final VoidCallback onTap;

  const _DesignButton({
    required this.title,
    required this.asset,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Ink(
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: selected ? GlameColors.graphite : GlameColors.nearBlack,
          border: Border.all(
            color: selected ? GlameColors.whiteGlame : GlameColors.borderGray,
            width: selected ? 1.5 : 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            AspectRatio(
              aspectRatio: 590 / 417,
              child: ClipRect(
                child: Image.asset(
                  asset,
                  fit: BoxFit.cover,
                  errorBuilder: (_, _, _) =>
                      const ColoredBox(color: GlameColors.graphite),
                ),
              ),
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Icon(
                  selected ? Icons.check_circle : Icons.circle_outlined,
                  color: selected
                      ? GlameColors.whiteGlame
                      : GlameColors.steelGray,
                  size: 18,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: GlameColors.whiteGlame,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _AmountButton extends StatelessWidget {
  final int amount;
  final bool selected;
  final VoidCallback onTap;

  const _AmountButton({
    required this.amount,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        height: 70,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: selected ? GlameColors.whiteGlame : Colors.transparent,
          border: Border.all(
            color: selected ? GlameColors.whiteGlame : GlameColors.borderGray,
          ),
        ),
        child: Text(
          _formatRub(amount),
          style: TextStyle(
            fontSize: 16,
            letterSpacing: 1.1,
            color: selected ? GlameColors.nearBlack : GlameColors.whiteGlame,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}

class _CustomAmountField extends StatelessWidget {
  final TextEditingController controller;
  final bool selected;
  final ValueChanged<String> onChanged;

  const _CustomAmountField({
    required this.controller,
    required this.selected,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text('ИЛИ ВВЕДИТЕ СВОЮ СУММУ', style: _labelStyle),
        const SizedBox(height: 10),
        TextField(
          controller: controller,
          keyboardType: TextInputType.number,
          inputFormatters: [_RubAmountInputFormatter()],
          onChanged: onChanged,
          style: const TextStyle(
            color: GlameColors.whiteGlame,
            fontSize: 24,
            letterSpacing: 0,
            fontWeight: FontWeight.w700,
          ),
          cursorColor: GlameColors.whiteGlame,
          decoration: InputDecoration(
            suffixText: '₽',
            suffixStyle: const TextStyle(
              color: GlameColors.whiteGlame,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
            hintText: 'Например, 7 500',
            filled: false,
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 18,
              vertical: 18,
            ),
            hintStyle: const TextStyle(
              color: GlameColors.textSecondary,
              fontSize: 18,
              fontWeight: FontWeight.w400,
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.zero,
              borderSide: BorderSide(
                color: selected
                    ? GlameColors.whiteGlame
                    : GlameColors.borderGray,
              ),
            ),
            focusedBorder: const OutlineInputBorder(
              borderRadius: BorderRadius.zero,
              borderSide: BorderSide(color: GlameColors.whiteGlame),
            ),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'От ${_formatRub(_GiftCertificateScreenState._minAmount)} до ${_formatRub(_GiftCertificateScreenState._maxAmount)}',
          style: const TextStyle(
            color: GlameColors.textSecondary,
            fontSize: 12,
            height: 1.25,
          ),
        ),
      ],
    );
  }
}

class _DarkTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String? hint;
  final TextInputType? keyboardType;
  final int maxLines;

  const _DarkTextField({
    required this.controller,
    required this.label,
    this.hint,
    this.keyboardType,
    this.maxLines = 1,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(label.toUpperCase(), style: _labelStyle),
        const SizedBox(height: 10),
        TextField(
          controller: controller,
          keyboardType: keyboardType,
          maxLines: maxLines,
          style: const TextStyle(color: GlameColors.whiteGlame, fontSize: 18),
          cursorColor: GlameColors.whiteGlame,
          decoration: InputDecoration(
            hintText: hint,
            filled: false,
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 18,
              vertical: 18,
            ),
            hintStyle: const TextStyle(color: GlameColors.textSecondary),
            enabledBorder: const OutlineInputBorder(
              borderRadius: BorderRadius.zero,
              borderSide: BorderSide(color: GlameColors.borderGray),
            ),
            focusedBorder: const OutlineInputBorder(
              borderRadius: BorderRadius.zero,
              borderSide: BorderSide(color: GlameColors.whiteGlame),
            ),
          ),
        ),
      ],
    );
  }
}

class _CheckRow extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _CheckRow({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Row(
        children: [
          Container(
            width: 24,
            height: 24,
            decoration: BoxDecoration(
              border: Border.all(color: GlameColors.borderGray),
            ),
            child: selected
                ? const Icon(
                    Icons.check,
                    size: 17,
                    color: GlameColors.whiteGlame,
                  )
                : null,
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 17,
                color: GlameColors.whiteGlame,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _OutlineAction extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;

  const _OutlineAction({
    required this.label,
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: onTap,
      icon: Icon(icon, size: 18),
      label: Text(label),
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        foregroundColor: GlameColors.whiteGlame,
        side: const BorderSide(color: GlameColors.borderGray),
        shape: const RoundedRectangleBorder(),
      ),
    );
  }
}

class _TimeSelect extends StatelessWidget {
  final String label;
  final int value;
  final List<int> values;
  final ValueChanged<int> onChanged;

  const _TimeSelect({
    required this.label,
    required this.value,
    required this.values,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<int>(
      initialValue: value,
      dropdownColor: GlameColors.nearBlack,
      iconEnabledColor: GlameColors.whiteGlame,
      decoration: InputDecoration(
        labelText: label.toUpperCase(),
        labelStyle: _labelStyle,
        enabledBorder: const OutlineInputBorder(
          borderRadius: BorderRadius.zero,
          borderSide: BorderSide(color: GlameColors.borderGray),
        ),
        focusedBorder: const OutlineInputBorder(
          borderRadius: BorderRadius.zero,
          borderSide: BorderSide(color: GlameColors.whiteGlame),
        ),
      ),
      style: const TextStyle(color: GlameColors.whiteGlame, fontSize: 18),
      items: values
          .map(
            (item) => DropdownMenuItem<int>(
              value: item,
              child: Text(item.toString().padLeft(2, '0')),
            ),
          )
          .toList(growable: false),
      onChanged: (next) {
        if (next != null) onChanged(next);
      },
    );
  }
}

class _SummaryRow extends StatelessWidget {
  final String label;
  final String value;
  final VoidCallback onTap;

  const _SummaryRow({
    required this.label,
    required this.value,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 22),
        decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: GlameColors.borderGray)),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label.toUpperCase(), style: _labelStyle),
                  const SizedBox(height: 8),
                  Text(
                    value,
                    style: const TextStyle(
                      fontSize: 19,
                      color: GlameColors.whiteGlame,
                    ),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right, color: GlameColors.textSecondary),
          ],
        ),
      ),
    );
  }
}

class _TermsLink extends StatelessWidget {
  const _TermsLink();

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Условия использования будут добавлены позже'),
        ),
      ),
      child: const Text(
        'Условия использования',
        style: TextStyle(
          fontSize: 14,
          color: GlameColors.textSecondary,
          decoration: TextDecoration.underline,
          decorationColor: GlameColors.textSecondary,
        ),
      ),
    );
  }
}

class _BottomActionBar extends StatelessWidget {
  final int step;
  final bool submitting;
  final bool canGoBack;
  final VoidCallback onBack;
  final VoidCallback onNext;

  const _BottomActionBar({
    required this.step,
    required this.submitting,
    required this.canGoBack,
    required this.onBack,
    required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        28,
        14,
        28,
        14 + MediaQuery.paddingOf(context).bottom,
      ),
      decoration: const BoxDecoration(
        color: GlameColors.nearBlack,
        border: Border(top: BorderSide(color: GlameColors.borderGray)),
      ),
      child: Row(
        children: [
          if (canGoBack) ...[
            SizedBox(
              width: 54,
              height: 54,
              child: OutlinedButton(
                onPressed: onBack,
                style: OutlinedButton.styleFrom(
                  foregroundColor: GlameColors.whiteGlame,
                  side: const BorderSide(color: GlameColors.borderGray),
                  shape: const RoundedRectangleBorder(),
                  padding: EdgeInsets.zero,
                ),
                child: const Icon(Icons.arrow_back, size: 20),
              ),
            ),
            const SizedBox(width: 12),
          ],
          Expanded(
            child: FilledButton(
              onPressed: submitting ? null : onNext,
              style: FilledButton.styleFrom(
                minimumSize: const Size.fromHeight(54),
                backgroundColor: GlameColors.whiteGlame,
                foregroundColor: GlameColors.nearBlack,
                shape: const RoundedRectangleBorder(),
                textStyle: const TextStyle(
                  fontSize: 13,
                  letterSpacing: 4,
                  fontWeight: FontWeight.w700,
                ),
              ),
              child: submitting
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(step == 2 ? 'ПЕРЕЙТИ К ОПЛАТЕ' : 'ПРОДОЛЖИТЬ'),
            ),
          ),
        ],
      ),
    );
  }
}

const _labelStyle = TextStyle(
  fontSize: 13,
  letterSpacing: 1.6,
  color: GlameColors.textSecondary,
  fontWeight: FontWeight.w700,
);

String _formatRub(int amount) {
  final text = amount.toString().replaceAllMapped(
    RegExp(r'(\d)(?=(\d{3})+$)'),
    (match) => '${match[1]} ',
  );
  return '$text ₽';
}

String _formatAmountInput(int amount) {
  return amount.toString().replaceAllMapped(
    RegExp(r'(\d)(?=(\d{3})+$)'),
    (match) => '${match[1]} ',
  );
}

int _parseAmountInput(String value) {
  final digits = value.replaceAll(RegExp(r'\D'), '');
  if (digits.isEmpty) return 0;
  return int.tryParse(digits) ?? 0;
}

String _formatDate(DateTime date) {
  String two(int value) => value.toString().padLeft(2, '0');
  return '${two(date.day)}.${two(date.month)}.${date.year}, ${two(date.hour)}:${two(date.minute)}';
}

String _paymentStatusText(String status) {
  switch (status) {
    case 'succeeded':
      return 'Оплачено';
    case 'canceled':
      return 'Отменено';
    case 'pending':
      return 'Ожидает оплаты';
    case 'waiting_for_capture':
      return 'Ожидает подтверждения';
    default:
      return status.isEmpty ? 'Неизвестно' : status;
  }
}

class _RubAmountInputFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    final amount = _parseAmountInput(newValue.text);
    final text = amount <= 0 ? '' : _formatAmountInput(amount);
    return TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
  }
}
