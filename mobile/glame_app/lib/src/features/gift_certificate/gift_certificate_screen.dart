import 'package:flutter/material.dart';

import '../../core/theme/glame_theme.dart';

class GiftCertificateScreen extends StatefulWidget {
  const GiftCertificateScreen({super.key});

  @override
  State<GiftCertificateScreen> createState() => _GiftCertificateScreenState();
}

class _GiftCertificateScreenState extends State<GiftCertificateScreen> {
  final _phoneController = TextEditingController();
  final _emailController = TextEditingController();
  final _nameController = TextEditingController();
  final _messageController = TextEditingController();
  final _senderController = TextEditingController();
  final _customAmountController = TextEditingController();

  int _step = 0;
  int _amount = 5000;
  int _design = 0;
  int _accent = 0;
  bool _sendLater = false;
  DateTime? _sendAt;

  static const _amounts = [5000, 10000, 20000, 50000];

  @override
  void dispose() {
    _phoneController.dispose();
    _emailController.dispose();
    _nameController.dispose();
    _messageController.dispose();
    _senderController.dispose();
    _customAmountController.dispose();
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
                      0 => 'Дизайн и номинал',
                      1 => 'Кому и когда',
                      _ => 'Оплата',
                    },
                  ),
                  const SizedBox(height: 30),
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 180),
                    child: switch (_step) {
                      0 => _DesignStep(
                        key: const ValueKey('design'),
                        amount: _amount,
                        design: _design,
                        accent: _accent,
                        customAmountController: _customAmountController,
                        onDesignChanged: (value) =>
                            setState(() => _design = value),
                        onAccentChanged: (value) =>
                            setState(() => _accent = value),
                        onAmountChanged: (value) {
                          setState(() {
                            _amount = value;
                            _customAmountController.clear();
                          });
                        },
                        onCustomAmountChanged: _setCustomAmount,
                      ),
                      1 => _RecipientStep(
                        key: const ValueKey('recipient'),
                        amount: _amount,
                        design: _design,
                        accent: _accent,
                        phoneController: _phoneController,
                        emailController: _emailController,
                        nameController: _nameController,
                        messageController: _messageController,
                        senderController: _senderController,
                        sendLater: _sendLater,
                        sendAt: _sendAt,
                        onSendModeChanged: (later) =>
                            setState(() => _sendLater = later),
                        onPickDate: _pickSendDateTime,
                      ),
                      _ => _PaymentStep(
                        key: const ValueKey('payment'),
                        amount: _amount,
                        design: _design,
                        accent: _accent,
                        phone: _phoneController.text,
                        email: _emailController.text,
                        recipientName: _nameController.text,
                        sendLater: _sendLater,
                        sendAt: _sendAt,
                        onEditRecipient: () => setState(() => _step = 1),
                        onEditDesign: () => setState(() => _step = 0),
                      ),
                    },
                  ),
                ],
              ),
            ),
            _BottomActionBar(
              step: _step,
              canGoBack: _step > 0,
              onBack: () => setState(() => _step -= 1),
              onNext: _handlePrimaryAction,
            ),
          ],
        ),
      ),
    );
  }

  void _setCustomAmount(String raw) {
    final digits = raw.replaceAll(RegExp(r'[^0-9]'), '');
    final value = int.tryParse(digits);
    if (value == null) return;
    setState(() => _amount = value.clamp(1000, 500000));
  }

  Future<void> _pickSendDateTime() async {
    final now = DateTime.now();
    final date = await showDatePicker(
      context: context,
      initialDate: _sendAt ?? now.add(const Duration(days: 1)),
      firstDate: now,
      lastDate: now.add(const Duration(days: 365)),
      builder: (context, child) => Theme(
        data: Theme.of(context).copyWith(
          colorScheme: const ColorScheme.dark(
            primary: GlameColors.whiteGlame,
            onPrimary: GlameColors.nearBlack,
            surface: GlameColors.nearBlack,
            onSurface: GlameColors.whiteGlame,
          ),
        ),
        child: child!,
      ),
    );
    if (date == null || !mounted) return;

    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(_sendAt ?? now),
      builder: (context, child) => Theme(
        data: Theme.of(context).copyWith(
          colorScheme: const ColorScheme.dark(
            primary: GlameColors.whiteGlame,
            onPrimary: GlameColors.nearBlack,
            surface: GlameColors.nearBlack,
            onSurface: GlameColors.whiteGlame,
          ),
        ),
        child: child!,
      ),
    );
    if (time == null) return;

    setState(() {
      _sendAt = DateTime(
        date.year,
        date.month,
        date.day,
        time.hour,
        time.minute,
      );
    });
  }

  void _handlePrimaryAction() {
    if (_step == 0) {
      if (_amount < 1000) {
        _showMessage('Минимальный номинал сертификата — 1 000 ₽');
        return;
      }
      setState(() => _step = 1);
      return;
    }

    if (_step == 1) {
      if (_phoneController.text.trim().isEmpty &&
          _emailController.text.trim().isEmpty) {
        _showMessage('Укажите телефон или эл. почту получателя');
        return;
      }
      if (_sendLater && _sendAt == null) {
        _showMessage('Выберите дату и время отправки');
        return;
      }
      setState(() => _step = 2);
      return;
    }

    _showMessage(
      'Оплата сертификата будет подключена после интеграции бэкенда',
    );
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: GlameColors.textPrimary,
      ),
    );
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
            fontFamily: 'Kudry Headline',
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
  final int accent;
  final TextEditingController customAmountController;
  final ValueChanged<int> onDesignChanged;
  final ValueChanged<int> onAccentChanged;
  final ValueChanged<int> onAmountChanged;
  final ValueChanged<String> onCustomAmountChanged;

  const _DesignStep({
    super.key,
    required this.amount,
    required this.design,
    required this.accent,
    required this.customAmountController,
    required this.onDesignChanged,
    required this.onAccentChanged,
    required this.onAmountChanged,
    required this.onCustomAmountChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'Подарочный сертификат',
          style: TextStyle(
            fontFamily: 'Kudry Headline',
            fontSize: 28,
            height: 1.08,
            color: GlameColors.whiteGlame,
          ),
        ),
        const SizedBox(height: 24),
        _CertificatePreview(amount: amount, design: design, accent: accent),
        const SizedBox(height: 34),
        _SegmentTabs(
          labels: const ['Текстура', 'Цвет'],
          selected: accent,
          onChanged: onAccentChanged,
        ),
        const SizedBox(height: 18),
        _DesignGrid(selected: design, mode: accent, onChanged: onDesignChanged),
        const SizedBox(height: 34),
        const Text('ВЫБЕРИТЕ НОМИНАЛ ИЛИ ВВЕДИТЕ СУММУ', style: _labelStyle),
        const SizedBox(height: 16),
        Wrap(
          spacing: 14,
          runSpacing: 14,
          children: _GiftCertificateScreenState._amounts.map((value) {
            return SizedBox(
              width: (MediaQuery.sizeOf(context).width - 70) / 2,
              child: _AmountButton(
                amount: value,
                selected:
                    amount == value && customAmountController.text.isEmpty,
                onTap: () => onAmountChanged(value),
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: 14),
        _DarkTextField(
          controller: customAmountController,
          label: 'Другая сумма',
          keyboardType: TextInputType.number,
          suffix: '₽',
          icon: Icons.edit_outlined,
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
  final int accent;
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
    required this.accent,
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
        _CertificatePreview(
          amount: amount,
          design: design,
          accent: accent,
          compact: true,
        ),
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
  final int accent;
  final String phone;
  final String email;
  final String recipientName;
  final bool sendLater;
  final DateTime? sendAt;
  final VoidCallback onEditRecipient;
  final VoidCallback onEditDesign;

  const _PaymentStep({
    super.key,
    required this.amount,
    required this.design,
    required this.accent,
    required this.phone,
    required this.email,
    required this.recipientName,
    required this.sendLater,
    required this.sendAt,
    required this.onEditRecipient,
    required this.onEditDesign,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'ПОДАРОЧНЫЙ\nСЕРТИФИКАТ',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Kudry Headline',
            fontSize: 31,
            height: 1.12,
            color: GlameColors.whiteGlame,
          ),
        ),
        const SizedBox(height: 28),
        _CertificatePreview(
          amount: amount,
          design: design,
          accent: accent,
          showAmount: false,
          compact: true,
        ),
        const SizedBox(height: 30),
        _SummaryRow(
          label: 'Получатель',
          value: recipientName.trim().isEmpty ? 'Не указано' : recipientName,
          onTap: onEditRecipient,
        ),
        _SummaryRow(
          label: 'Телефон',
          value: phone.trim().isEmpty ? 'Не указан' : phone,
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
          label: 'Дизайн',
          value: 'Вариант ${design + 1}',
          onTap: onEditDesign,
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
        const Center(child: _TermsLink()),
      ],
    );
  }
}

class _CertificatePreview extends StatelessWidget {
  final int amount;
  final int design;
  final int accent;
  final bool compact;
  final bool showAmount;

  const _CertificatePreview({
    required this.amount,
    required this.design,
    required this.accent,
    this.compact = false,
    this.showAmount = true,
  });

  @override
  Widget build(BuildContext context) {
    final gradient =
        _certificateGradients[(design + accent) % _certificateGradients.length];
    return AspectRatio(
      aspectRatio: compact ? 1.72 : 1.58,
      child: Container(
        decoration: BoxDecoration(
          border: Border.all(color: GlameColors.borderGray),
          gradient: gradient,
        ),
        child: Stack(
          fit: StackFit.expand,
          children: [
            CustomPaint(painter: _CertificatePatternPainter(design: design)),
            Center(
              child: Opacity(
                opacity: 0.72,
                child: GlameHeaderLogo(height: compact ? 30 : 38, silver: true),
              ),
            ),
            if (showAmount)
              Positioned(
                right: 24,
                bottom: 24,
                child: Text(
                  _formatRub(amount),
                  style: TextStyle(
                    fontSize: compact ? 20 : 26,
                    color: GlameColors.whiteGlame,
                    shadows: const [
                      Shadow(color: Colors.black54, blurRadius: 8),
                    ],
                  ),
                ),
              ),
            if (!showAmount)
              const Positioned(
                left: 0,
                right: 0,
                bottom: 22,
                child: Text(
                  'ПРЕДПРОСМОТР СЕРТИФИКАТА',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 13,
                    letterSpacing: 1.6,
                    color: GlameColors.whiteGlame,
                    decoration: TextDecoration.underline,
                    decorationColor: GlameColors.whiteGlame,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _DesignGrid extends StatelessWidget {
  final int selected;
  final int mode;
  final ValueChanged<int> onChanged;

  const _DesignGrid({
    required this.selected,
    required this.mode,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      itemCount: 6,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        crossAxisSpacing: 8,
        mainAxisSpacing: 8,
        childAspectRatio: 1,
      ),
      itemBuilder: (context, index) {
        return InkWell(
          onTap: () => onChanged(index),
          child: Container(
            decoration: BoxDecoration(
              border: Border.all(
                width: selected == index ? 2 : 1,
                color: selected == index
                    ? GlameColors.whiteGlame
                    : GlameColors.borderGray,
              ),
              gradient:
                  _certificateGradients[(index + mode) %
                      _certificateGradients.length],
            ),
            child: CustomPaint(
              painter: _CertificatePatternPainter(design: index),
            ),
          ),
        );
      },
    );
  }
}

class _CertificatePatternPainter extends CustomPainter {
  final int design;

  const _CertificatePatternPainter({required this.design});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white.withValues(alpha: 0.07)
      ..strokeWidth = 1;

    if (design % 3 == 0) {
      for (double y = -size.height; y < size.height * 2; y += 22) {
        canvas.drawLine(
          Offset(-10, y),
          Offset(size.width + 30, y + size.height * 0.45),
          paint,
        );
      }
    } else if (design % 3 == 1) {
      for (double x = 0; x < size.width; x += 18) {
        canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
      }
    } else {
      for (double x = 8; x < size.width; x += 30) {
        for (double y = 8; y < size.height; y += 30) {
          canvas.drawCircle(
            Offset(x, y),
            6,
            paint..style = PaintingStyle.stroke,
          );
        }
      }
      paint.style = PaintingStyle.fill;
    }
  }

  @override
  bool shouldRepaint(covariant _CertificatePatternPainter oldDelegate) {
    return oldDelegate.design != design;
  }
}

class _SegmentTabs extends StatelessWidget {
  final List<String> labels;
  final int selected;
  final ValueChanged<int> onChanged;

  const _SegmentTabs({
    required this.labels,
    required this.selected,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: List.generate(labels.length, (index) {
        final isSelected = selected == index;
        return Expanded(
          child: InkWell(
            onTap: () => onChanged(index),
            child: Container(
              height: 46,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: isSelected
                        ? GlameColors.whiteGlame
                        : GlameColors.borderGray,
                    width: isSelected ? 2 : 1,
                  ),
                ),
              ),
              child: Text(
                labels[index],
                style: TextStyle(
                  fontSize: 16,
                  color: isSelected
                      ? GlameColors.whiteGlame
                      : GlameColors.textSecondary,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
        );
      }),
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

class _DarkTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String? hint;
  final String? suffix;
  final IconData? icon;
  final TextInputType? keyboardType;
  final int maxLines;
  final ValueChanged<String>? onChanged;

  const _DarkTextField({
    required this.controller,
    required this.label,
    this.hint,
    this.suffix,
    this.icon,
    this.keyboardType,
    this.maxLines = 1,
    this.onChanged,
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
          onChanged: onChanged,
          style: const TextStyle(color: GlameColors.whiteGlame, fontSize: 18),
          cursorColor: GlameColors.whiteGlame,
          decoration: InputDecoration(
            hintText: hint,
            prefixIcon: icon == null
                ? null
                : Icon(icon, color: GlameColors.textSecondary),
            suffixText: suffix,
            suffixStyle: const TextStyle(color: GlameColors.whiteGlame),
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
  final bool canGoBack;
  final VoidCallback onBack;
  final VoidCallback onNext;

  const _BottomActionBar({
    required this.step,
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
              onPressed: onNext,
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
              child: Text(step == 2 ? 'ПЕРЕЙТИ К ОПЛАТЕ' : 'ПРОДОЛЖИТЬ'),
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

final _certificateGradients = <LinearGradient>[
  const LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF2B2D2F), Color(0xFF090A0B), Color(0xFF5E6366)],
  ),
  const LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF0D171B), Color(0xFF173441), Color(0xFF050707)],
  ),
  const LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [Color(0xFF202020), Color(0xFF050505)],
  ),
  const LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF3A3A38), Color(0xFF111111), Color(0xFF242928)],
  ),
  const LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF14211F), Color(0xFF33433C), Color(0xFF090B0A)],
  ),
  const LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [Color(0xFF4A4E4F), Color(0xFF17191A), Color(0xFF050505)],
  ),
];

String _formatRub(int amount) {
  final text = amount.toString().replaceAllMapped(
    RegExp(r'(\d)(?=(\d{3})+$)'),
    (match) => '${match[1]} ',
  );
  return '$text ₽';
}

String _formatDate(DateTime date) {
  String two(int value) => value.toString().padLeft(2, '0');
  return '${two(date.day)}.${two(date.month)}.${date.year}, ${two(date.hour)}:${two(date.minute)}';
}
