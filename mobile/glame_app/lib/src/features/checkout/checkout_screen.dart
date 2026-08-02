import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/formatters/phone.dart';
import '../../core/theme/glame_theme.dart';
import '../auth/auth_controller.dart';
import '../auth/user.dart' as auth_model;
import '../cart/cart_controller.dart';
import 'checkout_api.dart';

final checkoutApiProvider = Provider<CheckoutApi>((ref) {
  return CheckoutApi(ref.watch(apiClientProvider));
});

class CheckoutScreen extends ConsumerStatefulWidget {
  final int initialStep;
  final bool returnToCartOnAddressBack;

  const CheckoutScreen({
    super.key,
    this.initialStep = 0,
    this.returnToCartOnAddressBack = false,
  });

  @override
  ConsumerState<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends ConsumerState<CheckoutScreen> {
  late int step;

  final name = TextEditingController();
  final phone = TextEditingController();
  final address = TextEditingController();
  final cdekCityQuery = TextEditingController();
  final giftCertificateNumber = TextEditingController();
  final giftCertificatePin = TextEditingController();

  String paymentMethod = 'cod';
  String deliveryMethod = 'pickup'; // pickup | cdek_pvz
  bool submitting = false;
  bool loadingDeliveryData = false;
  bool loadingCdekPvz = false;
  bool loadingLoyalty = true;
  bool loadingGiftCertificates = true;
  bool validatingGiftCertificate = false;
  bool useBonuses = false;
  bool saveDeliveryToProfile = true;
  bool contactPrefilled = false;
  bool deliveryPrefApplied = false;
  late final VoidCallback _removePhoneFormatter;
  Map<String, dynamic>? result;
  String? deliveryError;
  String? loyaltyError;
  String? giftCertificateError;
  String? giftCertificatesError;
  int loyaltyPoints = 0;
  String? _loyaltyUserId;
  String? _giftCertificatesUserId;
  Map<String, dynamic>? giftCertificatePreview;

  Map<String, dynamic>? cdekOptions;
  List<Map<String, dynamic>> pickupStores = const [];
  List<Map<String, dynamic>> deliveryAddresses = const [];
  List<Map<String, dynamic>> giftCertificates = const [];
  Map<String, dynamic>? selectedStore;
  Map<String, dynamic>? selectedCdekCity;
  List<Map<String, dynamic>> cdekCities = const [];
  List<Map<String, dynamic>> cdekPvz = const [];
  Map<String, dynamic>? selectedPvz;
  int? cdekDeliveryAmountKopeks;
  String? cdekTariffTitle;

  @override
  void initState() {
    super.initState();
    step = widget.initialStep.clamp(0, 3);
    _removePhoneFormatter = installRuPhonePrefixFormatter(phone);
    _loadDeliveryData();
  }

  @override
  void dispose() {
    _removePhoneFormatter();
    name.dispose();
    phone.dispose();
    address.dispose();
    cdekCityQuery.dispose();
    giftCertificateNumber.dispose();
    giftCertificatePin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    _syncLoyaltyState(auth.user);
    _prefillContactFromProfile(auth.user);

    final cart = ref.watch(cartControllerProvider);
    final cartController = ref.read(cartControllerProvider.notifier);

    final subtotal = cart.subtotal;
    final promotionDiscountAmount = cart.discountAmount;
    final merchandiseTotal = cart.total > 0 || promotionDiscountAmount > 0
        ? cart.total
        : subtotal;
    final pricingMode = _cdekPricingMode();
    final freeFromRub = _cdekFreeShippingThresholdRub();
    final surchargeRub = _cdekMarkupRub();
    final freeFromKopeks = freeFromRub > 0 ? freeFromRub * 100 : 0;
    final surchargeKopeks = surchargeRub * 100;

    int deliveryAmount;
    if (deliveryMethod == 'pickup') {
      deliveryAmount = 0;
    } else {
      int base;
      if (pricingMode == 'free') {
        base = 0;
      } else if (pricingMode == 'fixed') {
        base = surchargeKopeks;
      } else {
        final rawCdek = cdekDeliveryAmountKopeks ?? 0;
        base = rawCdek + surchargeKopeks;
      }
      deliveryAmount = (freeFromKopeks > 0 && subtotal >= freeFromKopeks)
          ? 0
          : base;
    }
    final totalBeforeBonuses = merchandiseTotal + deliveryAmount;
    final maxBonusPointsByOrder = totalBeforeBonuses ~/ 1000; // 10% заказа
    final bonusPointsToUse = useBonuses
        ? (loyaltyPoints > maxBonusPointsByOrder
              ? maxBonusPointsByOrder
              : loyaltyPoints)
        : 0;
    final bonusDiscountAmount = bonusPointsToUse * 100;
    final payableAfterBonuses = totalBeforeBonuses - bonusDiscountAmount;
    final giftCertificateDiscountAmount = _giftCertificateDiscountAmount(
      payableAfterBonuses,
    );
    final total = payableAfterBonuses - giftCertificateDiscountAmount;

    final steps = const ['Корзина', 'Адрес', 'Оплата', 'Подтверждение'];

    return Scaffold(
      backgroundColor: GlameColors.nearBlack,
      appBar: const GlameTopAppBar(dark: true),
      body: Theme(
        data: Theme.of(context).copyWith(
          filledButtonTheme: FilledButtonThemeData(
            style: FilledButton.styleFrom(
              backgroundColor: GlameColors.whiteGlame,
              foregroundColor: GlameColors.nearBlack,
              shape: const RoundedRectangleBorder(),
            ),
          ),
          outlinedButtonTheme: OutlinedButtonThemeData(
            style: OutlinedButton.styleFrom(
              foregroundColor: GlameColors.whiteGlame,
              side: const BorderSide(color: GlameColors.borderGray),
              shape: const RoundedRectangleBorder(),
            ),
          ),
          textButtonTheme: TextButtonThemeData(
            style: TextButton.styleFrom(
              foregroundColor: GlameColors.whiteGlame,
              shape: const RoundedRectangleBorder(),
            ),
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(20, 24, 20, 0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      'ОФОРМЛЕНИЕ',
                      style: TextStyle(
                        fontSize: 40,
                        height: 0.95,
                        fontWeight: FontWeight.w400,
                        color: GlameColors.whiteGlame,
                      ),
                    ),
                    SizedBox(height: 10),
                    Text(
                      'Проверьте корзину, выберите доставку и подтвердите заказ',
                      style: TextStyle(
                        fontSize: 15,
                        height: 1.35,
                        color: GlameColors.coldLightGray,
                      ),
                    ),
                    SizedBox(height: 18),
                    SizedBox(
                      width: 44,
                      child: Divider(height: 1, color: GlameColors.steelGray),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              _Progress(steps: steps, active: step),
              const Divider(height: 1, color: GlameColors.borderGray),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
                  child: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 180),
                    child: _buildStep(
                      context,
                      auth.user != null,
                      cart,
                      cartController,
                      subtotal,
                      totalBeforeBonuses,
                      deliveryAmount,
                      promotionDiscountAmount,
                      bonusDiscountAmount,
                      giftCertificateDiscountAmount,
                      bonusPointsToUse,
                      total,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStep(
    BuildContext context,
    bool isLoggedIn,
    CartState cart,
    CartController cartController,
    int subtotal,
    int totalBeforeBonuses,
    int deliveryAmount,
    int promotionDiscountAmount,
    int bonusDiscountAmount,
    int giftCertificateDiscountAmount,
    int bonusPointsToUse,
    int total,
  ) {
    if (result != null) {
      final orderId = (result!['order_id'] as String?) ?? '';
      final provider = (result!['provider'] as String?) ?? '';
      final confirmationUrl = (result!['confirmation_url'] as String?);
      return Column(
        key: const ValueKey('done'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _CheckoutStepHeader(
            title: 'Заказ оформлен',
            subtitle: 'Мы сохранили детали заказа и готовы к следующему шагу',
          ),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: GlameColors.surface2,
              border: Border.all(color: GlameColors.lightGray),
            ),
            child: Text('Номер заказа: $orderId'),
          ),
          const SizedBox(height: 10),
          if (provider == 'cod' ||
              provider == 'bonus' ||
              provider == 'gift_certificate')
            Text(
              provider == 'gift_certificate'
                  ? 'Оплачено сертификатом'
                  : provider == 'bonus'
                  ? 'Оплачено бонусами'
                  : 'Оплата при получении',
              style: Theme.of(
                context,
              ).textTheme.titleMedium?.copyWith(color: GlameColors.gold),
            ),
          if (provider == 'yookassa' && confirmationUrl != null)
            OutlinedButton(
              onPressed: () async {
                final uri = Uri.tryParse(confirmationUrl);
                if (uri == null) return;
                await launchUrl(uri, mode: LaunchMode.externalApplication);
              },
              child: const Text('Перейти к оплате'),
            ),
          const Spacer(),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Готово'),
          ),
        ],
      );
    }

    if (step == 0) {
      return Column(
        key: const ValueKey('cart'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _CheckoutStepHeader(
            title: 'Корзина',
            subtitle: 'Позиций: ${cart.items.length}',
          ),
          _Totals(
            subtotal: subtotal,
            deliveryAmount: deliveryAmount,
            promotionDiscountAmount: promotionDiscountAmount,
            bonusDiscountAmount: bonusDiscountAmount,
            giftCertificateDiscountAmount: giftCertificateDiscountAmount,
            total: total,
          ),
          const Spacer(),
          FilledButton(
            onPressed: cart.items.isEmpty
                ? null
                : () => setState(() => step = 1),
            child: const Text('Далее'),
          ),
        ],
      );
    }

    if (step == 1) {
      return Column(
        key: const ValueKey('address'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _CheckoutStepHeader(
            title: 'Доставка',
            subtitle: 'Выберите самовывоз из магазина или пункт СДЭК',
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.only(bottom: 18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _CheckoutTextField(controller: name, label: 'Имя'),
                  const SizedBox(height: 10),
                  _CheckoutTextField(
                    controller: phone,
                    label: 'Телефон',
                    keyboardType: TextInputType.phone,
                  ),
                  const SizedBox(height: 10),
                  if (deliveryAddresses.isNotEmpty) ...[
                    Text(
                      'Сохраненные адреса',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    ...deliveryAddresses.map(
                      (delivery) => Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: _SavedDeliveryOption(
                          title: _deliveryTitle(delivery),
                          subtitle: _deliverySubtitle(delivery),
                          selected:
                              _deliveryIdentityKey(
                                _buildCurrentDeliveryMarker(),
                              ) ==
                              _deliveryIdentityKey(delivery),
                          onTap: () => _applySavedDelivery(delivery),
                        ),
                      ),
                    ),
                    const SizedBox(height: 4),
                  ],
                  const SizedBox(height: 14),
                  Text(
                    'Способ доставки',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  _PaymentOption(
                    title: 'Самовывоз из магазина',
                    subtitle: 'Выбор удобного магазина GLAME',
                    selected: deliveryMethod == 'pickup',
                    onTap: () => setState(() => deliveryMethod = 'pickup'),
                  ),
                  const SizedBox(height: 8),
                  _PaymentOption(
                    title: 'Доставка СДЭК (ПВЗ)',
                    subtitle: 'Выбор пункта выдачи и расчет стоимости',
                    selected: deliveryMethod == 'cdek_pvz',
                    onTap: () => setState(() {
                      deliveryMethod = 'cdek_pvz';
                      // For CDEK flow enforce explicit city -> PVZ selection.
                      selectedPvz = null;
                    }),
                  ),
                  const SizedBox(height: 6),
                  CheckboxListTile(
                    value: saveDeliveryToProfile,
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    controlAffinity: ListTileControlAffinity.leading,
                    title: const Text('Сохранить способ доставки в профиле'),
                    onChanged: isLoggedIn
                        ? (value) => setState(
                            () => saveDeliveryToProfile = value ?? false,
                          )
                        : null,
                  ),
                  if (deliveryMethod == 'pickup') ...[
                    const SizedBox(height: 10),
                    DropdownButtonFormField<String>(
                      initialValue: selectedStore == null
                          ? null
                          : selectedStore!['id'] as String?,
                      isExpanded: true,
                      items: pickupStores
                          .map(
                            (s) => DropdownMenuItem<String>(
                              value: s['id'] as String?,
                              child: Text(
                                _storeLabel(s),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          )
                          .toList(growable: false),
                      onChanged: (id) {
                        setState(() {
                          selectedStore = pickupStores.firstWhere(
                            (s) => s['id'] == id,
                            orElse: () => <String, dynamic>{},
                          );
                          if (selectedStore != null && selectedStore!.isEmpty) {
                            selectedStore = null;
                          }
                        });
                      },
                      decoration: const InputDecoration(
                        labelText: 'Магазин самовывоза',
                      ),
                    ),
                  ] else ...[
                    const SizedBox(height: 10),
                    OutlinedButton(
                      onPressed: _pickCdekCityFromCdekApi,
                      child: Text(
                        selectedCdekCity == null
                            ? 'Выбрать город СДЭК'
                            : 'Город: ${_cityLabel(selectedCdekCity!)} (изменить)',
                      ),
                    ),
                    if (selectedCdekCity != null) ...[
                      const SizedBox(height: 6),
                      Text(
                        'Город: ${_cityLabel(selectedCdekCity!)}',
                        style: const TextStyle(
                          color: GlameColors.textSecondary,
                        ),
                      ),
                    ],
                    const SizedBox(height: 10),
                    if (loadingCdekPvz)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 6),
                        child: LinearProgressIndicator(),
                      ),
                    if (selectedCdekCity == null) ...[
                      const Text(
                        'Сначала выберите город СДЭК',
                        style: TextStyle(color: GlameColors.textSecondary),
                      ),
                    ] else ...[
                      OutlinedButton(
                        onPressed: _pickCdekPvzFromCdekApi,
                        child: Text(
                          selectedPvz == null
                              ? 'Выбрать пункт ПВЗ СДЭК'
                              : 'ПВЗ: ${_pvzLabel(selectedPvz!)} (изменить)',
                        ),
                      ),
                      const SizedBox(height: 8),
                      OutlinedButton.icon(
                        onPressed: _pickCdekPvzOnMap,
                        icon: const Icon(Icons.map_outlined, size: 18),
                        label: const Text('Выбрать ПВЗ на карте'),
                      ),
                    ],
                    if (deliveryMethod == 'cdek_pvz' &&
                        (selectedCdekCity != null) &&
                        (_cdekPricingMode() != 'calculator' ||
                            cdekDeliveryAmountKopeks != null)) ...[
                      const SizedBox(height: 6),
                      Text(
                        'Стоимость СДЭК: ${_rub(deliveryAmount)}${cdekTariffTitle == null ? '' : ' ($cdekTariffTitle)'}',
                        style: const TextStyle(
                          color: GlameColors.textSecondary,
                        ),
                      ),
                    ],
                    const SizedBox(height: 8),
                    _CheckoutTextField(
                      controller: address,
                      label: 'Комментарий к доставке',
                      hintText: 'Необязательно',
                    ),
                  ],
                  if (deliveryError != null) ...[
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        border: Border.all(color: GlameColors.graphite),
                      ),
                      child: Text(
                        deliveryError!,
                        style: const TextStyle(color: GlameColors.graphite),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () {
                    if (widget.returnToCartOnAddressBack) {
                      Navigator.of(context).maybePop();
                      return;
                    }
                    setState(() => step = 0);
                  },
                  child: const Text('Назад'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton(
                  onPressed: () {
                    if (!_isAddressStepComplete()) return;
                    setState(() => step = 2);
                  },
                  child: const Text('Далее'),
                ),
              ),
            ],
          ),
        ],
      );
    }

    if (step == 2) {
      return Column(
        key: const ValueKey('payment'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _CheckoutStepHeader(
            title: 'Оплата',
            subtitle: 'Выберите удобный способ оплаты заказа',
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.only(bottom: 18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _PaymentOption(
                    title: 'Оплата при получении',
                    subtitle: 'Выделяем как приоритетный способ',
                    selected: paymentMethod == 'cod',
                    onTap: () => setState(() => paymentMethod = 'cod'),
                  ),
                  const SizedBox(height: 10),
                  _PaymentOption(
                    title: 'Картой онлайн',
                    subtitle: 'Оплата через YooKassa',
                    selected: paymentMethod == 'card',
                    onTap: () => setState(() => paymentMethod = 'card'),
                  ),
                  const SizedBox(height: 10),
                  _BonusPaymentOption(
                    isLoggedIn: isLoggedIn,
                    loading: loadingLoyalty,
                    error: loyaltyError,
                    loyaltyPoints: loyaltyPoints,
                    bonusPointsToUse: bonusPointsToUse,
                    totalBeforeBonuses: totalBeforeBonuses,
                    selected: useBonuses,
                    onOpenBalance: () => context.go('/home?tab=4'),
                    onLogin: () => context.go(
                      '/login?next=${Uri.encodeComponent('/checkout')}',
                    ),
                    onRegister: () => context.go(
                      '/auth/register?next=${Uri.encodeComponent('/checkout')}',
                    ),
                    onChanged: loyaltyPoints <= 0
                        ? null
                        : (value) => setState(() => useBonuses = value),
                  ),
                  const SizedBox(height: 10),
                  _GiftCertificatePaymentOption(
                    numberController: giftCertificateNumber,
                    pinController: giftCertificatePin,
                    certificates: giftCertificates,
                    loadingCertificates: loadingGiftCertificates,
                    certificatesError: giftCertificatesError,
                    preview: giftCertificatePreview,
                    error: giftCertificateError,
                    loading: validatingGiftCertificate,
                    appliedAmount: giftCertificateDiscountAmount,
                    onSelectCertificate: _selectGiftCertificate,
                    onValidate: _validateGiftCertificate,
                    onClear: () => setState(() {
                      giftCertificatePreview = null;
                      giftCertificateError = null;
                    }),
                  ),
                ],
              ),
            ),
          ),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => setState(() => step = 1),
                  child: const Text('Назад'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton(
                  onPressed: () => setState(() => step = 3),
                  child: const Text('Далее'),
                ),
              ),
            ],
          ),
        ],
      );
    }

    return Column(
      key: const ValueKey('confirm'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _CheckoutStepHeader(
          title: 'Подтверждение',
          subtitle: 'Проверьте данные перед оформлением заказа',
        ),
        _Totals(
          subtotal: subtotal,
          deliveryAmount: deliveryAmount,
          promotionDiscountAmount: promotionDiscountAmount,
          bonusDiscountAmount: bonusDiscountAmount,
          giftCertificateDiscountAmount: giftCertificateDiscountAmount,
          total: total,
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: GlameColors.surface2,
            border: Border.all(color: GlameColors.lightGray),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Имя: ${name.text.trim()}'),
              const SizedBox(height: 6),
              Text('Телефон: ${phone.text.trim()}'),
              const SizedBox(height: 6),
              Text(
                deliveryMethod == 'pickup'
                    ? 'Самовывоз: ${selectedStore == null ? '-' : _storeLabel(selectedStore!)}'
                    : 'СДЭК ПВЗ: ${selectedPvz == null ? '-' : _pvzLabel(selectedPvz!)}',
              ),
              if (deliveryMethod == 'cdek_pvz' &&
                  address.text.trim().isNotEmpty) ...[
                const SizedBox(height: 6),
                Text('Комментарий: ${address.text.trim()}'),
              ],
            ],
          ),
        ),
        const SizedBox(height: 6),
        Text(
          total == 0
              ? giftCertificateDiscountAmount > 0
                    ? 'Оплата: сертификатом'
                    : 'Оплата: бонусами'
              : paymentMethod == 'cod'
              ? 'Оплата: при получении'
              : 'Оплата: картой',
          style: Theme.of(
            context,
          ).textTheme.titleMedium?.copyWith(color: GlameColors.gold),
        ),
        const Spacer(),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: submitting ? null : () => setState(() => step = 2),
                child: const Text('Назад'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton(
                onPressed: submitting || cart.items.isEmpty
                    ? null
                    : () async {
                        final messenger = ScaffoldMessenger.of(context);
                        setState(() => submitting = true);
                        try {
                          final api = ref.read(checkoutApiProvider);
                          final origin = Uri.base.origin;
                          final returnUrl = paymentMethod == 'card'
                              ? '$origin/home?tab=3'
                              : '';
                          final resp = await api.checkout(
                            paymentMethod: paymentMethod,
                            deliveryAmount: deliveryAmount,
                            discountAmount: 0,
                            useBonusPoints: bonusPointsToUse,
                            returnUrl: returnUrl,
                            delivery: _buildDeliveryPayload(cart),
                            contact: {
                              'name': name.text.trim(),
                              'phone': formatRuPhoneInput(phone.text),
                            },
                            giftCertificate: giftCertificateDiscountAmount <= 0
                                ? null
                                : {
                                    'number': giftCertificateNumber.text.trim(),
                                    if (giftCertificatePin.text
                                        .trim()
                                        .isNotEmpty)
                                      'pin': giftCertificatePin.text.trim(),
                                    'amount': giftCertificateDiscountAmount,
                                  },
                          );
                          await cartController.refresh();
                          setState(() => result = resp);
                        } catch (_) {
                          setState(() => submitting = false);
                          messenger.showSnackBar(
                            const SnackBar(
                              content: Text('Не удалось оформить заказ'),
                            ),
                          );
                        }
                      },
                child: submitting
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(
                          color: GlameColors.textPrimary,
                          strokeWidth: 2,
                        ),
                      )
                    : const Text('Подтвердить'),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Future<void> _loadDeliveryData() async {
    setState(() {
      loadingDeliveryData = true;
      deliveryError = null;
    });
    try {
      final api = ref.read(checkoutApiProvider);
      final stores = await api.listStores();
      final options = await api.cdekOptions();
      Map<String, dynamic> profile = const <String, dynamic>{};
      try {
        profile = await api.profile();
      } catch (_) {
        profile = const <String, dynamic>{};
      }
      setState(() {
        pickupStores = stores;
        cdekOptions = options;
        deliveryAddresses = profile['delivery_addresses'] is List
            ? (profile['delivery_addresses'] as List)
                  .whereType<Map>()
                  .map((x) => Map<String, dynamic>.from(x))
                  .toList()
            : const <Map<String, dynamic>>[];
        if (selectedStore == null && stores.isNotEmpty) {
          selectedStore = stores.first;
        }
      });
      final preferred = profile['preferred_delivery'] is Map
          ? Map<String, dynamic>.from(profile['preferred_delivery'] as Map)
          : null;
      if (preferred != null) {
        await _applyPreferredDelivery(preferred);
      }
    } catch (_) {
      setState(() {
        deliveryError = 'Не удалось загрузить настройки доставки';
      });
    } finally {
      if (mounted) {
        setState(() {
          loadingDeliveryData = false;
        });
      }
    }
  }

  int _giftCertificateDiscountAmount(int payableAmount) {
    final preview = giftCertificatePreview;
    if (preview == null || payableAmount <= 0) return 0;
    final balance = _asInt(preview['balance_amount']) ?? 0;
    return balance.clamp(0, payableAmount);
  }

  void _selectGiftCertificate(Map<String, dynamic> certificate) {
    final number = (certificate['number'] ?? certificate['series'] ?? '')
        .toString()
        .trim();
    if (number.isEmpty) return;
    final pin = (certificate['pin'] ?? '').toString().trim();
    setState(() {
      giftCertificateNumber.text = number;
      giftCertificatePin.text = pin;
      giftCertificatePreview = certificate;
      giftCertificateError = null;
    });
  }

  Future<void> _validateGiftCertificate() async {
    final number = giftCertificateNumber.text.trim();
    if (number.isEmpty) {
      setState(() {
        giftCertificatePreview = null;
        giftCertificateError = 'Укажите номер сертификата';
      });
      return;
    }
    setState(() {
      validatingGiftCertificate = true;
      giftCertificateError = null;
    });
    try {
      final api = ref.read(checkoutApiProvider);
      final preview = await api.validateGiftCertificate(
        number: number,
        pin: giftCertificatePin.text.trim(),
      );
      if (!mounted) return;
      setState(() {
        giftCertificatePreview = preview;
        giftCertificateError = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        giftCertificatePreview = null;
        giftCertificateError = 'Сертификат не найден или недоступен';
      });
    } finally {
      if (mounted) {
        setState(() => validatingGiftCertificate = false);
      }
    }
  }

  Future<void> _applyPreferredDelivery(
    Map<String, dynamic> delivery, {
    bool force = false,
  }) async {
    if ((!force && deliveryPrefApplied) || !mounted) return;
    deliveryPrefApplied = true;
    final method = (delivery['method'] ?? delivery['type'] ?? '')
        .toString()
        .trim()
        .toLowerCase();

    if (method == 'pickup') {
      final storeId = (delivery['store_id'] ?? '').toString();
      final storeName = (delivery['store_name'] ?? '').toString().trim();
      final storeAddress = (delivery['address'] ?? '').toString().trim();
      Map<String, dynamic>? matched;
      for (final store in pickupStores) {
        final currentName = (store['name'] ?? '').toString().trim();
        final currentAddress = (store['address'] ?? '').toString().trim();
        final idMatches = storeId.isNotEmpty && '${store['id']}' == storeId;
        final nameMatches =
            storeName.isNotEmpty &&
            currentName.toLowerCase() == storeName.toLowerCase();
        final addressMatches =
            storeAddress.isNotEmpty &&
            currentAddress.toLowerCase() == storeAddress.toLowerCase();
        if (idMatches || nameMatches || addressMatches) {
          matched = store;
          break;
        }
      }
      setState(() {
        deliveryMethod = 'pickup';
        selectedStore = matched ?? selectedStore;
      });
      return;
    }

    if (method == 'cdek' || method == 'cdek_pvz' || method == 'pvz') {
      final cityCode = _asInt(delivery['city_code']);
      final cityName = (delivery['city'] ?? delivery['city_name'] ?? '')
          .toString()
          .trim();
      final pvzCode = (delivery['pvz_code'] ?? '').toString().trim();
      final pvzName = (delivery['pvz_name'] ?? '').toString().trim();
      final pvzAddress = (delivery['address'] ?? '').toString().trim();
      if (cityCode == null) return;

      setState(() {
        deliveryMethod = 'cdek_pvz';
        selectedCdekCity = {'code': cityCode, 'city': cityName};
        cdekCityQuery.text = cityName;
        selectedPvz = {
          'code': pvzCode,
          'name': pvzName,
          'address': pvzAddress,
          'location': {'address': pvzAddress},
        };
        loadingCdekPvz = true;
        cdekDeliveryAmountKopeks = null;
      });
      await _loadCdekPvzAndPrice(keepSelectedPvzCode: pvzCode);
    }
  }

  Future<void> _applySavedDelivery(Map<String, dynamic> delivery) async {
    await _applyPreferredDelivery(delivery, force: true);
    if (!mounted || !_isAddressStepComplete()) return;
    setState(() => step = 2);
  }

  bool _isAddressStepComplete() {
    final nameOk = name.text.trim().isNotEmpty;
    final phoneOk = isRuPhoneComplete(phone.text);
    final pickupOk = deliveryMethod == 'pickup' && selectedStore != null;
    final cdekOk =
        deliveryMethod == 'cdek_pvz' &&
        selectedCdekCity != null &&
        selectedPvz != null &&
        (_cdekPricingMode() != 'calculator' ||
            cdekDeliveryAmountKopeks != null);
    return nameOk && phoneOk && (pickupOk || cdekOk);
  }

  Map<String, dynamic> _buildCurrentDeliveryMarker() {
    if (deliveryMethod == 'pickup') {
      final store = selectedStore ?? const <String, dynamic>{};
      return {
        'method': 'pickup',
        'store_id': store['id'],
        'store_name': store['name'],
        'address': store['address'],
      };
    }
    final pvz = selectedPvz ?? const <String, dynamic>{};
    final location = (pvz['location'] is Map)
        ? Map<String, dynamic>.from(pvz['location'] as Map)
        : const <String, dynamic>{};
    return {
      'method': 'cdek',
      'type': 'pvz',
      'pvz_code': pvz['code'],
      'pvz_name': pvz['name'],
      'address': location['address'] ?? pvz['address'],
    };
  }

  void _prefillContactFromProfile(auth_model.User? user) {
    if (contactPrefilled || user == null) return;
    final profileName = user.fullName?.trim() ?? '';
    final profilePhone = user.phone?.trim() ?? '';
    if (profileName.isEmpty && profilePhone.isEmpty) return;
    contactPrefilled = true;
    if (name.text.trim().isEmpty && profileName.isNotEmpty) {
      name.text = profileName;
    }
    if (isRuPhonePrefixOnly(phone.text) && profilePhone.isNotEmpty) {
      phone.text = formatRuPhoneInput(profilePhone);
    }
  }

  Future<void> _loadLoyalty() async {
    setState(() {
      loadingLoyalty = true;
      loyaltyError = null;
    });
    try {
      final api = ref.read(checkoutApiProvider);
      final loyalty = await api.loyalty();
      if (!mounted) return;
      setState(() {
        loyaltyPoints =
            (loyalty['balance'] as num?)?.toInt() ??
            (loyalty['loyalty_points'] as num?)?.toInt() ??
            0;
        loadingLoyalty = false;
        loyaltyError = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        loyaltyPoints = 0;
        useBonuses = false;
        loadingLoyalty = false;
        loyaltyError = 'Не удалось загрузить бонусы';
      });
    }
  }

  Future<void> _loadGiftCertificates() async {
    setState(() {
      loadingGiftCertificates = true;
      giftCertificatesError = null;
    });
    try {
      final api = ref.read(checkoutApiProvider);
      final items = await api.giftCertificates();
      if (!mounted) return;
      setState(() {
        giftCertificates = items;
        loadingGiftCertificates = false;
        giftCertificatesError = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        giftCertificates = const [];
        loadingGiftCertificates = false;
        giftCertificatesError = 'Не удалось загрузить сертификаты';
      });
    }
  }

  void _syncLoyaltyState(auth_model.User? user) {
    final nextId = user?.id;
    if (_loyaltyUserId == nextId && _giftCertificatesUserId == nextId) return;
    _loyaltyUserId = nextId;
    _giftCertificatesUserId = nextId;
    if (nextId == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        setState(() {
          loyaltyPoints = 0;
          useBonuses = false;
          loadingLoyalty = false;
          loyaltyError = null;
          giftCertificates = const [];
          loadingGiftCertificates = false;
          giftCertificatesError = null;
          giftCertificatePreview = null;
          giftCertificateError = null;
        });
      });
      return;
    }
    _loadLoyalty();
    _loadGiftCertificates();
  }

  Future<void> _pickCdekCityFromCdekApi() async {
    final queryController = TextEditingController(
      text: cdekCityQuery.text.trim().isEmpty
          ? 'Ялта'
          : cdekCityQuery.text.trim(),
    );
    final api = ref.read(checkoutApiProvider);
    List<Map<String, dynamic>> cities = const [];
    bool loading = false;
    String? error;

    // Preload city list immediately so user sees results even if search controls
    // are hidden by theme/css quirks on web.
    try {
      cities = await api.cdekCities(queryController.text.trim());
      if (cities.isEmpty) {
        error = 'Города не найдены';
      }
    } catch (_) {
      error = 'Ошибка поиска городов';
    }
    if (!mounted) {
      queryController.dispose();
      return;
    }

    final picked = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, modalSetState) {
          Future<void> runSearch([String? forcedQuery]) async {
            final q = (forcedQuery ?? queryController.text).trim();
            if (q.length < 2) {
              modalSetState(() {
                error = 'Введите минимум 2 символа';
                cities = const [];
              });
              return;
            }
            modalSetState(() {
              loading = true;
              error = null;
            });
            try {
              final res = await api.cdekCities(q);
              modalSetState(() {
                cities = res;
                if (res.isEmpty) {
                  error = 'Города не найдены';
                }
              });
            } catch (_) {
              modalSetState(() => error = 'Ошибка поиска городов');
            } finally {
              modalSetState(() => loading = false);
            }
          }

          Future<void> askAndSearch() async {
            final localController = TextEditingController(
              text: queryController.text.trim(),
            );
            final q = await showDialog<String>(
              context: ctx,
              builder: (dialogCtx) => AlertDialog(
                title: const Text('Поиск города СДЭК'),
                content: TextField(
                  controller: localController,
                  autofocus: true,
                  decoration: const InputDecoration(
                    labelText: 'Введите город',
                    hintText: 'Например, Москва',
                  ),
                  onSubmitted: (v) => Navigator.of(dialogCtx).pop(v.trim()),
                ),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.of(dialogCtx).pop(),
                    child: const Text('Отмена'),
                  ),
                  FilledButton(
                    onPressed: () => Navigator.of(
                      dialogCtx,
                    ).pop(localController.text.trim()),
                    child: const Text('Найти'),
                  ),
                ],
              ),
            );
            localController.dispose();
            if (q == null || q.trim().length < 2) return;
            queryController.text = q.trim();
            await runSearch(q.trim());
          }

          final bottom = MediaQuery.of(ctx).viewInsets.bottom;
          return SafeArea(
            child: Padding(
              padding: EdgeInsets.fromLTRB(16, 8, 16, bottom + 12),
              child: SizedBox(
                height: 440,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      'Выбор города СДЭК',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 10),
                    OutlinedButton.icon(
                      onPressed: loading ? null : askAndSearch,
                      icon: const Icon(Icons.search, size: 18),
                      label: const Text('Ввести город для поиска'),
                    ),
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: GlameColors.surface2,
                        border: Border.all(color: GlameColors.lightGray),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        'Текущий запрос: ${queryController.text.trim().isEmpty ? '-' : queryController.text.trim()}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: GlameColors.textSecondary,
                        ),
                      ),
                    ),
                    if (loading) ...[
                      const SizedBox(height: 8),
                      const LinearProgressIndicator(),
                    ],
                    if (error != null) ...[
                      const SizedBox(height: 8),
                      Text(
                        error!,
                        style: const TextStyle(color: GlameColors.graphite),
                      ),
                    ],
                    const SizedBox(height: 8),
                    Expanded(
                      child: ListView.separated(
                        itemCount: cities.length,
                        separatorBuilder: (_, _) => const Divider(height: 1),
                        itemBuilder: (_, i) {
                          final c = cities[i];
                          return ListTile(
                            title: Text(_cityLabel(c)),
                            subtitle: Text('Код: ${c['code'] ?? '-'}'),
                            onTap: () => Navigator.of(ctx).pop(c),
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );

    queryController.dispose();
    if (picked == null || !mounted) return;
    setState(() {
      cdekCityQuery.text = _cityLabel(picked);
      selectedCdekCity = picked;
      selectedPvz = null;
      cdekPvz = const [];
      cdekDeliveryAmountKopeks = null;
      cdekTariffTitle = null;
      loadingCdekPvz = true;
      deliveryError = null;
    });
    await _loadCdekPvzAndPrice();
  }

  Future<void> _pickCdekPvzFromCdekApi() async {
    if (selectedCdekCity == null) return;
    final fresh = await _refreshCdekPvzForSelectedCity();
    if (!fresh || !mounted) return;

    final queryController = TextEditingController();
    List<Map<String, dynamic>> list = cdekPvz;
    String? error = list.isEmpty
        ? 'Для выбранного города ПВЗ не найдены'
        : null;

    final picked = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, modalSetState) {
          final q = queryController.text.trim().toLowerCase();
          final filtered = q.isEmpty
              ? list
              : list
                    .where((p) => _pvzLabel(p).toLowerCase().contains(q))
                    .toList();
          return SafeArea(
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                16,
                8,
                16,
                MediaQuery.of(ctx).viewInsets.bottom + 12,
              ),
              child: SizedBox(
                height: 440,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      'Выбор пункта ПВЗ СДЭК',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 10),
                    TextField(
                      controller: queryController,
                      decoration: const InputDecoration(labelText: 'Поиск ПВЗ'),
                      onChanged: (_) => modalSetState(() {}),
                    ),
                    if (error != null) ...[
                      const SizedBox(height: 8),
                      Text(
                        error!,
                        style: const TextStyle(color: GlameColors.graphite),
                      ),
                    ],
                    const SizedBox(height: 8),
                    Expanded(
                      child: filtered.isEmpty
                          ? const Center(
                              child: Text(
                                'Пункты выдачи не найдены',
                                style: TextStyle(
                                  color: GlameColors.textSecondary,
                                ),
                              ),
                            )
                          : ListView.separated(
                              itemCount: filtered.length,
                              separatorBuilder: (_, _) =>
                                  const Divider(height: 1),
                              itemBuilder: (_, i) {
                                final p = filtered[i];
                                return ListTile(
                                  title: Text(_pvzLabel(p)),
                                  subtitle: Text('Код: ${p['code'] ?? '-'}'),
                                  onTap: () => Navigator.of(ctx).pop(p),
                                );
                              },
                            ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );

    queryController.dispose();
    if (picked == null || !mounted) return;
    setState(() {
      selectedPvz = picked;
      error = null;
    });
  }

  Future<void> _pickCdekPvzOnMap() async {
    if (selectedCdekCity == null) return;
    final fresh = await _refreshCdekPvzForSelectedCity();
    if (!fresh || !mounted) return;

    final points = cdekPvz
        .map((p) {
          final ll = _pvzLatLng(p);
          if (ll == null) return null;
          return (p, ll);
        })
        .whereType<(Map<String, dynamic>, LatLng)>()
        .toList();
    if (points.isEmpty) {
      setState(() {
        deliveryError = 'Для выбранного города нет координат ПВЗ для карты';
      });
      return;
    }

    final picked = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) {
        final center = points.first.$2;
        Map<String, dynamic>? selected = selectedPvz;
        return StatefulBuilder(
          builder: (ctx, modalSetState) => Dialog(
            insetPadding: const EdgeInsets.all(12),
            child: SizedBox(
              width: 900,
              height: 660,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
                    child: Row(
                      children: [
                        const Expanded(
                          child: Text(
                            'Выбор ПВЗ СДЭК на карте',
                            style: TextStyle(fontWeight: FontWeight.w600),
                          ),
                        ),
                        IconButton(
                          onPressed: () => Navigator.of(ctx).pop(),
                          icon: const Icon(Icons.close),
                        ),
                      ],
                    ),
                  ),
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                      'Нажмите на маркер, затем подтвердите пункт в карточке снизу',
                      style: TextStyle(color: GlameColors.textSecondary),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Expanded(
                    child: FlutterMap(
                      options: MapOptions(
                        initialCenter: center,
                        initialZoom: 12,
                      ),
                      children: [
                        TileLayer(
                          urlTemplate:
                              'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                          userAgentPackageName: 'ru.glame.app',
                        ),
                        MarkerLayer(
                          markers: points
                              .map(
                                (item) => Marker(
                                  point: item.$2,
                                  width: 42,
                                  height: 42,
                                  child: Tooltip(
                                    message: _pvzLabel(item.$1),
                                    child: GestureDetector(
                                      onTap: () => modalSetState(
                                        () => selected = item.$1,
                                      ),
                                      child: Icon(
                                        Icons.location_on,
                                        color:
                                            (selected != null &&
                                                '${selected!['code']}' ==
                                                    '${item.$1['code']}')
                                            ? GlameColors.graphite
                                            : GlameColors.gold,
                                        size: 34,
                                      ),
                                    ),
                                  ),
                                ),
                              )
                              .toList(),
                        ),
                      ],
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
                    decoration: BoxDecoration(
                      border: Border(
                        top: BorderSide(color: GlameColors.lightGray),
                      ),
                    ),
                    child: selected == null
                        ? const Text(
                            'Выберите маркер ПВЗ на карте',
                            style: TextStyle(color: GlameColors.textSecondary),
                          )
                        : Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Text(
                                _pvzLabel(selected!),
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                ),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                              const SizedBox(height: 4),
                              Text(
                                _pvzAddress(selected!),
                                style: const TextStyle(
                                  color: GlameColors.textSecondary,
                                ),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                              const SizedBox(height: 2),
                              Text(
                                'График: ${_pvzWorkTime(selected!)}',
                                style: const TextStyle(
                                  color: GlameColors.textSecondary,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              const SizedBox(height: 2),
                              Text(
                                'Код: ${selected!['code'] ?? '-'}',
                                style: const TextStyle(
                                  color: GlameColors.textSecondary,
                                ),
                              ),
                              const SizedBox(height: 10),
                              FilledButton(
                                onPressed: () =>
                                    Navigator.of(ctx).pop(selected),
                                child: const Text('Выбрать этот ПВЗ'),
                              ),
                            ],
                          ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );

    if (picked == null || !mounted) return;
    setState(() {
      selectedPvz = picked;
      deliveryError = null;
    });
  }

  Future<bool> _refreshCdekPvzForSelectedCity() async {
    final cityCode = _asInt(selectedCdekCity?['code']);
    if (cityCode == null) {
      setState(() => deliveryError = 'Не удалось определить код города СДЭК');
      return false;
    }
    setState(() {
      loadingCdekPvz = true;
      deliveryError = null;
    });
    try {
      final api = ref.read(checkoutApiProvider);
      final fresh = await api.cdekPvz(cityCode);
      if (!mounted) return false;
      setState(() {
        cdekPvz = fresh;
        loadingCdekPvz = false;
      });
      return true;
    } catch (_) {
      if (!mounted) return false;
      setState(() {
        loadingCdekPvz = false;
        deliveryError = 'Не удалось загрузить пункты ПВЗ СДЭК';
      });
      return false;
    }
  }

  Future<void> _loadCdekPvzAndPrice({String? keepSelectedPvzCode}) async {
    final city = selectedCdekCity;
    if (city == null) return;
    final toCityCode = _asInt(city['code']);
    final sender = (cdekOptions?['sender'] is Map)
        ? Map<String, dynamic>.from(cdekOptions!['sender'] as Map)
        : <String, dynamic>{};
    final package = (cdekOptions?['package'] is Map)
        ? Map<String, dynamic>.from(cdekOptions!['package'] as Map)
        : <String, dynamic>{};
    final tariffs = (cdekOptions?['tariffs'] is Map)
        ? Map<String, dynamic>.from(cdekOptions!['tariffs'] as Map)
        : <String, dynamic>{};

    final fromCityCode = _asInt(sender['city_code']);
    if (toCityCode == null || fromCityCode == null) {
      setState(() {
        loadingCdekPvz = false;
        deliveryError = 'Не настроен город отправителя СДЭК';
      });
      return;
    }

    try {
      final api = ref.read(checkoutApiProvider);
      final pvz = await api.cdekPvz(toCityCode);
      Map<String, dynamic>? preferredPvz;
      if (keepSelectedPvzCode != null && keepSelectedPvzCode.isNotEmpty) {
        for (final point in pvz) {
          if ('${point['code']}' == keepSelectedPvzCode) {
            preferredPvz = point;
            break;
          }
        }
      }
      final pricingMode = _cdekPricingMode();
      if (pricingMode != 'calculator') {
        setState(() {
          cdekPvz = pvz;
          selectedPvz = preferredPvz ?? selectedPvz;
          cdekDeliveryAmountKopeks = pricingMode == 'fixed'
              ? _cdekMarkupRub() * 100
              : 0;
          cdekTariffTitle = pricingMode == 'fixed'
              ? 'Фиксированная стоимость'
              : 'Бесплатная доставка';
          loadingCdekPvz = false;
        });
        return;
      }
      final calc = await api.cdekCalculate(
        fromCityCode: fromCityCode,
        toCityCode: toCityCode,
        weightG: _asInt(package['weight_g']) ?? 1000,
        lengthMm: _asInt(package['length_mm']) ?? 350,
        widthMm: _asInt(package['width_mm']) ?? 250,
        heightMm: _asInt(package['height_mm']) ?? 50,
        tariffCodes: [_asInt(tariffs['pvz']) ?? 136],
      );
      final parsed = _extractCdekDelivery(calc);
      setState(() {
        cdekPvz = pvz;
        selectedPvz = preferredPvz ?? selectedPvz;
        cdekDeliveryAmountKopeks = parsed.$1;
        cdekTariffTitle = parsed.$2;
        loadingCdekPvz = false;
      });
    } catch (_) {
      setState(() {
        loadingCdekPvz = false;
        deliveryError = 'Не удалось рассчитать доставку СДЭК';
      });
    }
  }

  (int?, String?) _extractCdekDelivery(Map<String, dynamic> payload) {
    List<Map<String, dynamic>> tariffs = const [];
    final t1 = payload['tariff_codes'];
    if (t1 is List) {
      tariffs = t1
          .whereType<Map>()
          .map((x) => Map<String, dynamic>.from(x))
          .toList();
    } else {
      final t2 = payload['tariffs'];
      if (t2 is List) {
        tariffs = t2
            .whereType<Map>()
            .map((x) => Map<String, dynamic>.from(x))
            .toList();
      }
    }
    if (tariffs.isEmpty) return (null, null);

    final withSums = tariffs
        .map((t) {
          final raw = t['delivery_sum'] ?? t['total_sum'] ?? t['sum'];
          final rub = (raw is num) ? raw.toDouble() : double.tryParse('$raw');
          return (t, rub);
        })
        .where((x) => x.$2 != null)
        .toList();
    if (withSums.isEmpty) return (null, null);
    withSums.sort((a, b) => a.$2!.compareTo(b.$2!));
    final best = withSums.first;
    final amountKopeks = (best.$2! * 100).round();
    final title = (best.$1['tariff_name'] ?? best.$1['name'] ?? '')
        .toString()
        .trim();
    return (amountKopeks, title.isEmpty ? null : title);
  }

  int? _asInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    final s = '$value'.trim();
    if (s.isEmpty) return null;
    final asInt = int.tryParse(s);
    if (asInt != null) return asInt;
    final asDouble = double.tryParse(s.replaceAll(',', '.'));
    return asDouble?.toInt();
  }

  double? _asDouble(dynamic value) {
    if (value is double) return value;
    if (value is int) return value.toDouble();
    if (value is num) return value.toDouble();
    final s = '$value'.trim();
    if (s.isEmpty) return null;
    return double.tryParse(s.replaceAll(',', '.'));
  }

  Map<String, dynamic> _cdekPricing() {
    if (cdekOptions?['pricing'] is Map) {
      return Map<String, dynamic>.from(cdekOptions!['pricing'] as Map);
    }
    return const <String, dynamic>{};
  }

  String _cdekPricingMode() {
    final pricing = _cdekPricing();
    final raw =
        (pricing['mode'] ?? cdekOptions?['pricing_mode'] ?? 'calculator')
            .toString()
            .trim()
            .toLowerCase();
    if (raw == 'free' || raw == 'fixed' || raw == 'calculator') return raw;
    return 'calculator';
  }

  int _cdekFreeShippingThresholdRub() {
    final pricing = _cdekPricing();
    return _asInt(
          pricing['free_shipping_threshold_rub'] ??
              pricing['free_shipping_from'],
        ) ??
        0;
  }

  int _cdekMarkupRub() {
    final pricing = _cdekPricing();
    return _asInt(pricing['markup_rub'] ?? pricing['surcharge']) ?? 0;
  }

  String _storeLabel(Map<String, dynamic> s) {
    final name = (s['name'] ?? '').toString().trim();
    final city = (s['city'] ?? '').toString().trim();
    final addr = (s['address'] ?? '').toString().trim();
    final parts = [if (city.isNotEmpty) city, if (addr.isNotEmpty) addr];
    if (parts.isEmpty) return name;
    return '$name — ${parts.join(', ')}';
  }

  String _cityLabel(Map<String, dynamic> c) {
    final city = (c['city'] ?? c['city_name'] ?? '').toString().trim();
    final region = (c['region'] ?? c['region_name'] ?? '').toString().trim();
    if (region.isEmpty) return city;
    return '$city, $region';
  }

  String _pvzLabel(Map<String, dynamic> p) {
    final code = (p['code'] ?? '').toString().trim();
    final name = (p['name'] ?? '').toString().trim();
    final location = (p['location'] is Map)
        ? Map<String, dynamic>.from(p['location'] as Map)
        : <String, dynamic>{};
    final addr = (location['address'] ?? p['address'] ?? '').toString().trim();
    final head = name.isNotEmpty ? name : code;
    if (addr.isEmpty) return head;
    return '$head — $addr';
  }

  String _pvzAddress(Map<String, dynamic> p) {
    final location = (p['location'] is Map)
        ? Map<String, dynamic>.from(p['location'] as Map)
        : <String, dynamic>{};
    final full = (location['address_full'] ?? '').toString().trim();
    if (full.isNotEmpty) return full;
    final addr = (location['address'] ?? p['address'] ?? '').toString().trim();
    return addr.isEmpty ? '-' : addr;
  }

  String _pvzWorkTime(Map<String, dynamic> p) {
    final wt = (p['work_time'] ?? '').toString().trim();
    return wt.isEmpty ? 'по графику СДЭК' : wt;
  }

  LatLng? _pvzLatLng(Map<String, dynamic> p) {
    final location = (p['location'] is Map)
        ? Map<String, dynamic>.from(p['location'] as Map)
        : <String, dynamic>{};
    final lat = _asDouble(location['latitude'] ?? p['latitude']);
    final lng = _asDouble(location['longitude'] ?? p['longitude']);
    if (lat == null || lng == null) return null;
    return LatLng(lat, lng);
  }

  Map<String, dynamic> _buildDeliveryPayload(CartState cart) {
    if (deliveryMethod == 'pickup') {
      final store = selectedStore ?? const <String, dynamic>{};
      return {
        'method': 'pickup',
        'type': 'pickup',
        'store_id': store['id'],
        'store_name': store['name'],
        'city': store['city'],
        'address': store['address'],
        'items_count': cart.items.length,
        'save_to_profile': saveDeliveryToProfile,
      };
    }

    final city = selectedCdekCity ?? const <String, dynamic>{};
    final pvz = selectedPvz ?? const <String, dynamic>{};
    final location = (pvz['location'] is Map)
        ? Map<String, dynamic>.from(pvz['location'] as Map)
        : <String, dynamic>{};
    return {
      'method': 'cdek',
      'type': 'pvz',
      'city_code': city['code'],
      'city': city['city'] ?? city['city_name'],
      'pvz_code': pvz['code'],
      'pvz_name': pvz['name'],
      'address': location['address'] ?? pvz['address'],
      'comment': address.text.trim(),
      'tariff': cdekTariffTitle,
      'items_count': cart.items.length,
      'save_to_profile': saveDeliveryToProfile,
    };
  }
}

class _CheckoutTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String? hintText;
  final TextInputType? keyboardType;
  final TextCapitalization textCapitalization;
  final ValueChanged<String>? onChanged;

  const _CheckoutTextField({
    required this.controller,
    required this.label,
    this.hintText,
    this.keyboardType,
    this.textCapitalization = TextCapitalization.none,
    this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _CheckoutFieldLabel(label),
        const SizedBox(height: 6),
        TextField(
          controller: controller,
          keyboardType: keyboardType,
          textCapitalization: textCapitalization,
          onChanged: onChanged,
          style: const TextStyle(
            color: GlameColors.nearBlack,
            fontSize: 16,
            height: 1.2,
          ),
          cursorColor: GlameColors.nearBlack,
          decoration: InputDecoration(
            hintText: hintText,
            hintStyle: const TextStyle(color: GlameColors.steelGray),
            filled: true,
            fillColor: GlameColors.whiteGlame,
            isDense: true,
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 14,
              vertical: 13,
            ),
            border: const OutlineInputBorder(
              borderRadius: BorderRadius.zero,
              borderSide: BorderSide(color: GlameColors.borderGray),
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
        ),
      ],
    );
  }
}

class _CheckoutFieldLabel extends StatelessWidget {
  final String text;

  const _CheckoutFieldLabel(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        color: GlameColors.coldLightGray,
        fontSize: 13,
        height: 1.1,
      ),
    );
  }
}

class _SavedDeliveryOption extends StatelessWidget {
  final String title;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;

  const _SavedDeliveryOption({
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          border: Border.all(
            color: selected ? GlameColors.whiteGlame : GlameColors.borderGray,
          ),
          color: selected ? GlameColors.surface2 : Colors.transparent,
        ),
        child: Row(
          children: [
            Icon(
              selected ? Icons.radio_button_checked : Icons.radio_button_off,
              size: 18,
              color: selected
                  ? GlameColors.whiteGlame
                  : GlameColors.coldLightGray,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 3),
                  Text(
                    subtitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: GlameColors.textSecondary),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

String _deliveryIdentityKey(Map<String, dynamic> delivery) {
  var method = (delivery['method'] ?? delivery['type'] ?? '')
      .toString()
      .trim()
      .toLowerCase();
  if (method == 'cdek') method = 'pvz';
  if (method == 'pickup') {
    return 'pickup:${delivery['store_id'] ?? delivery['store_name'] ?? delivery['address'] ?? ''}';
  }
  return 'pvz:${delivery['pvz_code'] ?? delivery['address'] ?? ''}';
}

String _deliveryTitle(Map<String, dynamic> delivery) {
  final method = (delivery['method'] ?? delivery['type'] ?? '')
      .toString()
      .trim()
      .toLowerCase();
  if (method == 'pickup') {
    return _deliveryString(delivery['store_name']) ?? 'Самовывоз GLAME';
  }
  return _deliveryString(delivery['pvz_name']) ?? 'Пункт выдачи СДЭК';
}

String _deliverySubtitle(Map<String, dynamic> delivery) {
  final city = _deliveryString(delivery['city'] ?? delivery['city_name']);
  final address = _deliveryString(delivery['address']);
  final code = _deliveryString(delivery['pvz_code']);
  final parts = <String>[?city, ?address, if (code != null) 'Код $code'];
  return parts.isEmpty ? 'Адрес не указан' : parts.join(', ');
}

String? _deliveryString(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : text;
}

class _Progress extends StatelessWidget {
  final List<String> steps;
  final int active;

  const _Progress({required this.steps, required this.active});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
      child: Row(
        children: List.generate(steps.length, (i) {
          final on = i <= active;
          return Expanded(
            child: Column(
              children: [
                Container(
                  height: 3,
                  decoration: BoxDecoration(
                    color: on ? GlameColors.whiteGlame : GlameColors.borderGray,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  steps[i],
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: on ? GlameColors.whiteGlame : GlameColors.steelGray,
                    fontWeight: i == active ? FontWeight.w700 : FontWeight.w400,
                  ),
                ),
              ],
            ),
          );
        }),
      ),
    );
  }
}

class _PaymentOption extends StatelessWidget {
  final String title;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;

  const _PaymentOption({
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Ink(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: selected ? GlameColors.graphite : GlameColors.nearBlack,
          border: Border.all(
            color: selected ? GlameColors.whiteGlame : GlameColors.borderGray,
            width: 1.5,
          ),
        ),
        child: Row(
          children: [
            Icon(
              selected ? Icons.check_circle : Icons.circle_outlined,
              color: selected ? GlameColors.whiteGlame : GlameColors.steelGray,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: GlameColors.whiteGlame,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    subtitle,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: GlameColors.coldLightGray,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BonusPaymentOption extends StatelessWidget {
  final bool isLoggedIn;
  final bool loading;
  final String? error;
  final int loyaltyPoints;
  final int bonusPointsToUse;
  final int totalBeforeBonuses;
  final bool selected;
  final VoidCallback onOpenBalance;
  final VoidCallback onLogin;
  final VoidCallback onRegister;
  final ValueChanged<bool>? onChanged;

  const _BonusPaymentOption({
    required this.isLoggedIn,
    required this.loading,
    required this.error,
    required this.loyaltyPoints,
    required this.bonusPointsToUse,
    required this.totalBeforeBonuses,
    required this.selected,
    required this.onOpenBalance,
    required this.onLogin,
    required this.onRegister,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    if (!isLoggedIn) {
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: GlameColors.graphite,
          border: Border.all(color: GlameColors.borderGray),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Войдите, чтобы использовать баланс и получать бонусы',
              style: TextStyle(color: GlameColors.coldLightGray),
            ),
            const SizedBox(height: 10),
            FilledButton(onPressed: onLogin, child: const Text('ВОЙТИ')),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: onRegister,
              child: const Text('СОЗДАТЬ АККАУНТ'),
            ),
          ],
        ),
      );
    }

    final disabled = onChanged == null;
    final maxPointsByOrder = totalBeforeBonuses ~/ 1000;
    final pointsToUse = selected ? bonusPointsToUse : 0;
    final bonusDiscountAmount = pointsToUse * 100;
    final totalAfterBonus = totalBeforeBonuses - bonusDiscountAmount;
    final subtitle = loading
        ? 'Проверяем доступный баланс'
        : error != null
        ? error!
        : loyaltyPoints <= 0
        ? 'Баланс появится после первой покупки'
        : selected
        ? 'Можно списать до 10% заказа'
        : 'Можно списать до 10% заказа';

    return Opacity(
      opacity: disabled && !loading ? 0.62 : 1,
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: selected ? GlameColors.graphite : GlameColors.nearBlack,
          border: Border.all(
            color: selected ? GlameColors.whiteGlame : GlameColors.borderGray,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            InkWell(
              onTap: onOpenBalance,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  children: [
                    Icon(
                      Icons.stars_rounded,
                      color: loyaltyPoints > 0
                          ? GlameColors.whiteGlame
                          : GlameColors.steelGray,
                    ),
                    const SizedBox(width: 8),
                    const Expanded(
                      child: Text(
                        'Баланс GLAME',
                        style: TextStyle(
                          fontWeight: FontWeight.w600,
                          color: GlameColors.whiteGlame,
                        ),
                      ),
                    ),
                    Text(
                      '${loyaltyPoints.clamp(0, 999999)} ₽',
                      style: const TextStyle(color: GlameColors.whiteGlame),
                    ),
                  ],
                ),
              ),
            ),
            const Divider(height: 16, color: GlameColors.borderGray),
            SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              value: selected && !disabled,
              onChanged: loading ? null : onChanged,
              title: const Text('Использовать баланс'),
              subtitle: Text(subtitle),
            ),
            if (!loading && error == null && loyaltyPoints > 0) ...[
              const SizedBox(height: 2),
              _Row(label: 'Списание', value: '-${_rub(bonusDiscountAmount)}'),
              const SizedBox(height: 6),
              _Row(
                label: 'Итого',
                value: _rub(totalAfterBonus),
                valueStyle: const TextStyle(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 4),
              Text(
                'Доступно: $loyaltyPoints бонусов, к списанию сейчас до $maxPointsByOrder',
                style: const TextStyle(
                  fontSize: 12,
                  color: GlameColors.coldLightGray,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _GiftCertificatePaymentOption extends StatelessWidget {
  final TextEditingController numberController;
  final TextEditingController pinController;
  final List<Map<String, dynamic>> certificates;
  final bool loadingCertificates;
  final String? certificatesError;
  final Map<String, dynamic>? preview;
  final String? error;
  final bool loading;
  final int appliedAmount;
  final ValueChanged<Map<String, dynamic>> onSelectCertificate;
  final VoidCallback onValidate;
  final VoidCallback onClear;

  const _GiftCertificatePaymentOption({
    required this.numberController,
    required this.pinController,
    required this.certificates,
    required this.loadingCertificates,
    required this.certificatesError,
    required this.preview,
    required this.error,
    required this.loading,
    required this.appliedAmount,
    required this.onSelectCertificate,
    required this.onValidate,
    required this.onClear,
  });

  @override
  Widget build(BuildContext context) {
    final balance = _jsonInt(preview?['balance_amount']) ?? 0;
    final remainingBalance = (balance - appliedAmount).clamp(0, balance);
    final number = (preview?['number'] ?? '').toString();
    final availableCertificates = certificates.where((certificate) {
      final status = (certificate['status'] ?? '').toString().toLowerCase();
      final certBalance = _jsonInt(certificate['balance_amount']) ?? 0;
      return certBalance > 0 && (status == 'active' || status == 'reserved');
    }).toList();
    final selectedNumber = numberController.text.trim().isEmpty
        ? null
        : numberController.text.trim();

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: preview == null ? GlameColors.nearBlack : GlameColors.graphite,
        border: Border.all(
          color: preview == null
              ? GlameColors.borderGray
              : GlameColors.whiteGlame,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Row(
            children: [
              Icon(Icons.card_giftcard, color: GlameColors.whiteGlame),
              SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Подарочный сертификат',
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    color: GlameColors.whiteGlame,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (loadingCertificates)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: LinearProgressIndicator(minHeight: 2),
            )
          else if (availableCertificates.isNotEmpty) ...[
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const _CheckoutFieldLabel('Выбрать из моих сертификатов'),
                const SizedBox(height: 6),
                DropdownButtonFormField<String>(
                  initialValue:
                      availableCertificates.any(
                        (certificate) =>
                            (certificate['number'] ??
                                    certificate['series'] ??
                                    '')
                                .toString()
                                .trim() ==
                            selectedNumber,
                      )
                      ? selectedNumber
                      : null,
                  decoration: const InputDecoration(
                    filled: true,
                    fillColor: GlameColors.whiteGlame,
                    contentPadding: EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 13,
                    ),
                  ),
                  items: availableCertificates.map((certificate) {
                    final certNumber =
                        (certificate['number'] ?? certificate['series'] ?? '')
                            .toString()
                            .trim();
                    final certBalance =
                        _jsonInt(certificate['balance_amount']) ?? 0;
                    return DropdownMenuItem<String>(
                      value: certNumber,
                      child: Text(
                        '$certNumber · ${_rub(certBalance)}',
                        overflow: TextOverflow.ellipsis,
                      ),
                    );
                  }).toList(),
                  onChanged: (value) {
                    if (value == null) return;
                    for (final certificate in availableCertificates) {
                      final certNumber =
                          (certificate['number'] ?? certificate['series'] ?? '')
                              .toString()
                              .trim();
                      if (certNumber == value) {
                        onSelectCertificate(certificate);
                        break;
                      }
                    }
                  },
                ),
              ],
            ),
            const SizedBox(height: 10),
          ] else if (certificatesError != null) ...[
            Text(
              certificatesError!,
              style: const TextStyle(color: GlameColors.coldLightGray),
            ),
            const SizedBox(height: 10),
          ],
          _CheckoutTextField(
            controller: numberController,
            label: 'Номер сертификата',
            hintText: 'Можно ввести вручную',
            textCapitalization: TextCapitalization.characters,
            onChanged: (_) {
              if (preview != null) onClear();
            },
          ),
          const SizedBox(height: 10),
          _CheckoutTextField(
            controller: pinController,
            label: 'PIN',
            keyboardType: TextInputType.number,
            onChanged: (_) {
              if (preview != null) onClear();
            },
          ),
          if (error != null) ...[
            const SizedBox(height: 10),
            Text(error!, style: const TextStyle(color: GlameColors.gold)),
          ],
          if (preview != null) ...[
            const SizedBox(height: 10),
            _Row(label: 'Сертификат', value: number),
            const SizedBox(height: 6),
            _Row(label: 'Баланс', value: _rub(balance)),
            const SizedBox(height: 6),
            _Row(label: 'К списанию', value: _rub(appliedAmount)),
            const SizedBox(height: 6),
            _Row(label: 'Останется', value: _rub(remainingBalance)),
          ],
          const SizedBox(height: 12),
          OutlinedButton(
            onPressed: loading ? null : onValidate,
            child: loading
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Text(preview == null ? 'Проверить' : 'Обновить'),
          ),
        ],
      ),
    );
  }
}

class _Totals extends StatelessWidget {
  final int subtotal;
  final int deliveryAmount;
  final int promotionDiscountAmount;
  final int bonusDiscountAmount;
  final int giftCertificateDiscountAmount;
  final int total;

  const _Totals({
    required this.subtotal,
    required this.deliveryAmount,
    required this.promotionDiscountAmount,
    required this.bonusDiscountAmount,
    required this.giftCertificateDiscountAmount,
    required this.total,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: GlameColors.graphite,
        border: Border.all(color: GlameColors.borderGray),
      ),
      child: Column(
        children: [
          _Row(label: 'Стоимость товаров', value: _rub(subtotal)),
          if (promotionDiscountAmount > 0) ...[
            const SizedBox(height: 10),
            _Row(label: 'Акция', value: '-${_rub(promotionDiscountAmount)}'),
          ],
          const SizedBox(height: 10),
          _Row(
            label: 'Доставка',
            value: deliveryAmount == 0
                ? 'Бесплатно от 10 000 ₽'
                : _rub(deliveryAmount),
          ),
          if (bonusDiscountAmount > 0) ...[
            const SizedBox(height: 10),
            _Row(label: 'Бонусами', value: '-${_rub(bonusDiscountAmount)}'),
          ],
          if (giftCertificateDiscountAmount > 0) ...[
            const SizedBox(height: 10),
            _Row(
              label: 'Сертификат',
              value: '-${_rub(giftCertificateDiscountAmount)}',
            ),
          ],
          const SizedBox(height: 10),
          const Divider(height: 1, color: GlameColors.borderGray),
          const SizedBox(height: 10),
          _Row(
            label: 'Итого',
            value: _rub(total),
            valueStyle: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: GlameColors.whiteGlame,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class _CheckoutStepHeader extends StatelessWidget {
  final String title;
  final String subtitle;

  const _CheckoutStepHeader({required this.title, required this.subtitle});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            title,
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
              fontSize: 28,
              height: 1,
              color: GlameColors.whiteGlame,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            subtitle,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              fontSize: 14,
              color: GlameColors.coldLightGray,
            ),
          ),
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final String label;
  final String value;
  final TextStyle? valueStyle;

  const _Row({required this.label, required this.value, this.valueStyle});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.bodyMedium?.copyWith(color: GlameColors.coldLightGray),
          ),
        ),
        const SizedBox(width: 12),
        Text(
          value,
          style:
              valueStyle ??
              Theme.of(
                context,
              ).textTheme.bodyMedium?.copyWith(color: GlameColors.whiteGlame),
        ),
      ],
    );
  }
}

String _rub(int kopeks) {
  final rub = (kopeks / 100).toStringAsFixed(0);
  return '$rub ₽';
}

int? _jsonInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
