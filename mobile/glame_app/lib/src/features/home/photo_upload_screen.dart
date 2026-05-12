import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/formatters/rub.dart';
import '../../core/network/asset_url.dart';
import '../../core/theme/glame_theme.dart';
import '../auth/auth_controller.dart';
import '../customer/stylist_entry.dart';
import 'home_providers.dart';
import 'photo_selection_api.dart';

const String _photoUploadResumeRoute = '/photo-upload?resume=pick';

Future<void> showPhotoGuideSheet(
  BuildContext context, {
  required VoidCallback onPrimaryTap,
  String primaryLabel = 'Выбрать или сделать фото',
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (context) => _PhotoGuideSheet(
      primaryLabel: primaryLabel,
      onPrimaryTap: onPrimaryTap,
    ),
  );
}

Future<void> startPhotoSelectionFlow(BuildContext context) async {
  final container = ProviderScope.containerOf(context, listen: false);
  final auth = container.read(authControllerProvider);
  if (auth.user == null) {
    await _openPhotoAuthGate(context);
    return;
  }
  await _openPhotoSourcePicker(context);
}

Future<void> _openPhotoAuthGate(BuildContext context) async {
  final parentContext = context;
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (sheetContext) => _PhotoAuthGateSheet(
      onLoginTap: () => _openPhotoLogin(sheetContext, parentContext),
      onRegisterTap: () => _openPhotoRegister(sheetContext, parentContext),
      onPhoneTap: () => _openPhotoLogin(sheetContext, parentContext),
    ),
  );
}

Future<void> _openPhotoSourcePicker(BuildContext context) async {
  final parentContext = context;
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (sheetContext) => _PhotoSourcePickerSheet(
      onCameraTap: () =>
          _pickPhotoImage(sheetContext, parentContext, ImageSource.camera),
      onGalleryTap: () =>
          _pickPhotoImage(sheetContext, parentContext, ImageSource.gallery),
      onGuideTap: () {
        Navigator.of(sheetContext).pop();
        showPhotoGuideSheet(
          parentContext,
          onPrimaryTap: () => startPhotoSelectionFlow(parentContext),
        );
      },
    ),
  );
}

Future<void> _openPhotoLogin(
  BuildContext sheetContext,
  BuildContext parentContext,
) async {
  Navigator.of(sheetContext).pop();
  await parentContext.push(
    '/login?next=${Uri.encodeComponent(_photoUploadResumeRoute)}',
  );
}

Future<void> _openPhotoRegister(
  BuildContext sheetContext,
  BuildContext parentContext,
) async {
  Navigator.of(sheetContext).pop();
  await parentContext.push(
    '/auth/register?next=${Uri.encodeComponent(_photoUploadResumeRoute)}',
  );
}

Future<void> _pickPhotoImage(
  BuildContext sheetContext,
  BuildContext parentContext,
  ImageSource source,
) async {
  Navigator.of(sheetContext).pop();
  final picker = ImagePicker();
  final photo = await picker.pickImage(
    source: source,
    imageQuality: 86,
    maxWidth: 1800,
  );
  if (photo == null || !parentContext.mounted) return;
  final bytes = await photo.readAsBytes();
  if (!parentContext.mounted) return;
  parentContext.push(
    '/photo-review',
    extra: PhotoReviewArgs(bytes: bytes, fileName: photo.name),
  );
}

class PhotoUploadScreen extends ConsumerStatefulWidget {
  final bool resumePick;

  const PhotoUploadScreen({super.key, this.resumePick = false});

  @override
  ConsumerState<PhotoUploadScreen> createState() => _PhotoUploadScreenState();
}

class _PhotoUploadScreenState extends ConsumerState<PhotoUploadScreen> {
  bool _resumeHandled = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final isLoggedIn = ref.read(authControllerProvider).user != null;
    if (widget.resumePick && isLoggedIn && !_resumeHandled) {
      _resumeHandled = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        _openPhotoSourcePicker(context);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final isLoggedIn = auth.user != null;
    final photoSelectionBlock = ref.watch(homePhotoSelectionBlockProvider).asData?.value;
    final introImageUrl = resolveAssetUrl(
      photoSelectionBlock?['background_image_url'],
    );

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go('/home');
            }
          },
          icon: const Icon(Icons.arrow_back),
        ),
        title: const GlameHeaderLogo(),
      ),
      body: SafeArea(
        top: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(28, 24, 28, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Подбор по фото',
                style: TextStyle(
                  fontSize: 40,
                  height: 0.98,
                  fontWeight: FontWeight.w400,
                  color: GlameColors.textPrimary,
                ),
              ),
              const SizedBox(height: 14),
              const Text(
                'Загрузите фото, и мы поможем подобрать украшения, которые звучат с Вашей внешностью естественно, точно и без случайных решений.',
                style: TextStyle(
                  fontSize: 18,
                  height: 1.42,
                  color: GlameColors.textSecondary,
                ),
              ),
              const SizedBox(height: 28),
              PhotoSelectionPromoCard(
                height: 500,
                title: 'Ваш стиль\nв фокусе',
                description:
                    'Подбор начинается с Вас: спокойно, деликатно и без случайных решений.',
                imageUrl: introImageUrl,
                imageAspectRatio: 1315 / 1197,
                imageAssetPath: 'assets/images/home/photo_upload_intro.png',
              ),
              const SizedBox(height: 16),
              const PhotoSelectionInfoCard(),
              const SizedBox(height: 16),
              _PhotoPrimaryButton(
                title: 'Выбрать или сделать фото',
                icon: Icons.photo_camera_outlined,
                onTap: _handleChooseOrTakePhoto,
              ),
              const SizedBox(height: 14),
              _PhotoSecondaryButton(
                title: 'Какое фото подойдет',
                icon: Icons.image_outlined,
                onTap: _openGuide,
              ),
              const SizedBox(height: 18),
              Text(
                isLoggedIn
                    ? 'Можно сделать фото или выбрать снимок из галереи.'
                    : 'Загрузка фото доступна после входа в профиль.',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 14,
                  height: 1.35,
                  color: GlameColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _openGuide() async {
    await showPhotoGuideSheet(
      context,
      onPrimaryTap: () => startPhotoSelectionFlow(context),
    );
  }

  Future<void> _handleChooseOrTakePhoto() async {
    await startPhotoSelectionFlow(context);
  }
}

class PhotoReviewArgs {
  final Uint8List bytes;
  final String? fileName;

  const PhotoReviewArgs({required this.bytes, this.fileName});
}

class PhotoAnalysisArgs {
  final Uint8List bytes;
  final String? fileName;

  const PhotoAnalysisArgs({required this.bytes, this.fileName});
}

class PhotoSelectionResultArgs {
  final Uint8List bytes;
  final String? fileName;
  final Map<String, dynamic> analysis;
  final Map<String, dynamic> generation;

  const PhotoSelectionResultArgs({
    required this.bytes,
    required this.analysis,
    required this.generation,
    this.fileName,
  });
}

class PhotoReviewScreen extends StatelessWidget {
  final PhotoReviewArgs? args;

  const PhotoReviewScreen({super.key, this.args});

  @override
  Widget build(BuildContext context) {
    final imageBytes = args?.bytes;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.pop(),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const GlameHeaderLogo(),
      ),
      body: SafeArea(
        top: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(28, 24, 28, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Проверка фото',
                style: TextStyle(
                  fontSize: 40,
                  height: 0.98,
                  fontWeight: FontWeight.w400,
                  color: GlameColors.textPrimary,
                ),
              ),
              const SizedBox(height: 14),
              const Text(
                'Мы проверим качество снимка и подготовим следующий шаг для персонального подбора.',
                style: TextStyle(
                  fontSize: 18,
                  height: 1.42,
                  color: GlameColors.textSecondary,
                ),
              ),
              const SizedBox(height: 28),
              if (imageBytes != null)
                _AdaptivePhotoFrame(
                  referenceBytes: imageBytes,
                  borderColor: const Color(0xFFD6D6D6),
                  image: Image.memory(
                    imageBytes,
                    fit: BoxFit.contain,
                    alignment: Alignment.center,
                  ),
                  overlay: const Positioned.fill(child: _FaceFrameOverlay()),
                )
              else
                Container(
                  height: 440,
                  decoration: BoxDecoration(
                    border: Border.all(color: const Color(0xFFD6D6D6)),
                  ),
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      Container(color: GlameColors.warmGray),
                      const Positioned.fill(child: _FaceFrameOverlay()),
                    ],
                  ),
                ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: const [
                  _ValidationChip(label: 'Лицо видно'),
                  _ValidationChip(label: 'Один человек'),
                  _ValidationChip(label: 'Свет ровный'),
                  _ValidationChip(label: 'Фото подходит'),
                ],
              ),
              const SizedBox(height: 18),
              _PhotoPrimaryButton(
                title: 'Начать анализ',
                onTap: () {
                  if (imageBytes == null) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('Сначала выберите фото для продолжения.'),
                      ),
                    );
                    return;
                  }
                  context.push(
                    '/photo-analysis',
                    extra: PhotoAnalysisArgs(
                      bytes: imageBytes,
                      fileName: args?.fileName,
                    ),
                  );
                },
              ),
              const SizedBox(height: 12),
              _PhotoSecondaryButton(
                title: 'Выбрать другое фото',
                onTap: () => context.pop(),
              ),
              const SizedBox(height: 14),
              TextButton(
                onPressed: () {
                  showPhotoGuideSheet(
                    context,
                    onPrimaryTap: () => context.pop(),
                    primaryLabel: 'Понятно',
                  );
                },
                child: const Text('Какое фото подойдет?'),
              ),
              const SizedBox(height: 6),
              const Text(
                'Фото используется только для подбора украшений и не сохраняется в этом шаге.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 13,
                  height: 1.35,
                  color: GlameColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class PhotoAnalysisScreen extends ConsumerStatefulWidget {
  final PhotoAnalysisArgs? args;

  const PhotoAnalysisScreen({super.key, this.args});

  @override
  ConsumerState<PhotoAnalysisScreen> createState() =>
      _PhotoAnalysisScreenState();
}

class _PhotoAnalysisScreenState extends ConsumerState<PhotoAnalysisScreen> {
  bool _started = false;
  String? _error;
  Map<String, dynamic>? _analysis;
  _PhotoCheckPhase _phase = _PhotoCheckPhase.checking;
  List<_PhotoCheckStatusItem> _statuses = _initialPhotoCheckStatuses();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _runFlow());
  }

  Future<void> _runFlow() async {
    if (_started) return;
    _started = true;

    final args = widget.args;
    if (args == null) {
      setState(() {
        _error = 'Не удалось получить выбранное фото. Попробуйте снова.';
      });
      return;
    }

    final user = ref.read(authControllerProvider).user;
    if (user == null) {
      setState(() {
        _error =
            'Чтобы запустить подбор, войдите в профиль и повторите загрузку фото.';
      });
      return;
    }

    final api = ref.read(photoSelectionApiProvider);

    try {
      setState(() {
        _error = null;
        _analysis = null;
        _phase = _PhotoCheckPhase.checking;
        _statuses = _initialPhotoCheckStatuses();
      });
      final analysis = await api.analyzePhoto(
        bytes: args.bytes,
        fileName: args.fileName ?? 'photo.jpg',
      );

      await _revealPhotoStatuses(_buildPhotoCheckStatuses(analysis));
      if (!mounted) return;
      setState(() {
        _analysis = analysis;
        _phase = analysis['can_continue'] == true
            ? _PhotoCheckPhase.accepted
            : _PhotoCheckPhase.rejected;
      });
    } on DioException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = _photoSelectionErrorMessage(error);
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = 'Не удалось завершить подбор. Попробуйте еще раз.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final args = widget.args;
    final title = _phase == _PhotoCheckPhase.accepted
        ? 'Фото подходит'
        : _phase == _PhotoCheckPhase.rejected
            ? 'Фото пока не подходит'
            : 'Проверяем фото';
    final description = _phase == _PhotoCheckPhase.accepted
        ? 'Снимок подходит для точного подбора.\nТеперь можно перейти к рекомендациям.'
        : _phase == _PhotoCheckPhase.rejected
            ? _photoCheckDescription(_analysis)
            : 'Проверим фото по этапам перед анализом лица.\nСтатусы под снимком показывают реальный результат проверки.';
    final canStart = _analysis != null && _analysis!['can_continue'] == true;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.pop(),
          icon: const Icon(Icons.arrow_back),
        ),
        title: const GlameHeaderLogo(),
      ),
      body: SafeArea(
        top: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(28, 24, 28, 32),
          child: _error != null
              ? _PhotoAnalysisErrorState(
                  message: _error!,
                  onRetry: () {
                    setState(() {
                      _started = false;
                    });
                    _runFlow();
                  },
                  onBack: () => context.pop(),
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        fontSize: 33,
                        height: 1.02,
                        fontWeight: FontWeight.w400,
                        color: GlameColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      description,
                      style: const TextStyle(
                        fontSize: 15,
                        height: 1.45,
                        color: GlameColors.textSecondary,
                      ),
                    ),
                    const SizedBox(height: 18),
                    if (args != null)
                      _AdaptivePhotoFrame(
                        referenceBytes: args.bytes,
                        borderColor: const Color(0xFFD6D6D6),
                        image: Image.memory(
                          args.bytes,
                          fit: BoxFit.contain,
                          alignment: Alignment.center,
                        ),
                        overlay:
                            const Positioned.fill(child: _FaceFrameOverlay()),
                      )
                    else
                      Container(
                        height: 444,
                        decoration: BoxDecoration(
                          border: Border.all(color: const Color(0xFFD6D6D6)),
                        ),
                        child: Stack(
                          fit: StackFit.expand,
                          children: [
                            Container(color: GlameColors.warmGray),
                            const Positioned.fill(child: _FaceFrameOverlay()),
                          ],
                        ),
                      ),
                    const SizedBox(height: 20),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        for (var index = 0; index < _statuses.length; index++) ...[
                          Expanded(
                            child: _PhotoCheckStatusCard(
                              item: _statuses[index],
                            ),
                          ),
                          if (index != _statuses.length - 1)
                            const SizedBox(width: 10),
                        ],
                      ],
                    ),
                    const SizedBox(height: 10),
                    Text(
                      _photoCheckCaption(_phase, _analysis),
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontSize: 14,
                        height: 1.35,
                        color: GlameColors.textSecondary,
                      ),
                    ),
                    const SizedBox(height: 14),
                    if (_phase == _PhotoCheckPhase.checking)
                      Container(
                        height: 58,
                        decoration: const BoxDecoration(
                          color: Color(0xFF7A7A7A),
                        ),
                        child: const Center(
                          child: Text(
                            'Проверяем фото...',
                            style: TextStyle(
                              fontSize: 18,
                              height: 1.05,
                              color: GlameColors.surface2,
                            ),
                          ),
                        ),
                      )
                    else if (canStart)
                      _PhotoPrimaryButton(
                        title: 'Начать подбор',
                        onTap: () {
                          final analysis = _analysis;
                          if (analysis == null || !mounted) return;
                          context.pushReplacement(
                            '/photo-selection-result',
                            extra: PhotoSelectionResultArgs(
                              bytes: args!.bytes,
                              fileName: args.fileName,
                              analysis: analysis,
                              generation: const <String, dynamic>{},
                            ),
                          );
                        },
                      )
                    else
                      _PhotoPrimaryButton(
                        title: 'Выбрать другое фото',
                        onTap: () => context.go(_photoUploadResumeRoute),
                      ),
                    const SizedBox(height: 14),
                    if (_phase == _PhotoCheckPhase.accepted)
                      _PhotoSecondaryButton(
                        title: 'Выбрать другое фото',
                        onTap: () => context.go(_photoUploadResumeRoute),
                      )
                    else if (_phase == _PhotoCheckPhase.rejected)
                      _PhotoSecondaryButton(
                        title: 'Какое фото подойдет',
                        onTap: () {
                          showPhotoGuideSheet(
                            context,
                            onPrimaryTap: () => context.pop(),
                            primaryLabel: 'Понятно',
                          );
                        },
                      )
                    else
                      Container(
                        height: 58,
                        decoration: BoxDecoration(
                          border: Border.all(color: const Color(0xFFD6D6D6)),
                        ),
                        child: const Center(
                          child: Text(
                            'Идёт пошаговая проверка',
                            style: TextStyle(
                              fontSize: 16,
                              height: 1.2,
                              color: GlameColors.textSecondary,
                            ),
                          ),
                        ),
                      ),
                    const SizedBox(height: 14),
                    const Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                          Icons.lock_outline,
                          size: 16,
                          color: GlameColors.textSecondary,
                        ),
                        SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'Фото используется только для подбора и не публикуется.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 13,
                              height: 1.35,
                              color: GlameColors.textSecondary,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
        ),
      ),
    );
  }

  Future<void> _revealPhotoStatuses(
    List<_PhotoCheckStatusItem> finalStatuses,
  ) async {
    final animated = List<_PhotoCheckStatusItem>.from(_initialPhotoCheckStatuses());
    for (var index = 0; index < finalStatuses.length; index++) {
      if (!mounted) return;
      animated[index] = finalStatuses[index].copyWith(
        state: _PhotoCheckStatusState.checking,
      );
      setState(() {
        _statuses = List<_PhotoCheckStatusItem>.from(animated);
      });
      await Future<void>.delayed(const Duration(milliseconds: 260));
      if (!mounted) return;
      animated[index] = finalStatuses[index];
      setState(() {
        _statuses = List<_PhotoCheckStatusItem>.from(animated);
      });
      await Future<void>.delayed(const Duration(milliseconds: 180));
    }
  }
}

enum _PhotoCheckPhase { checking, accepted, rejected }

enum _PhotoCheckStatusState { pending, checking, passed, failed }

class _PhotoCheckStatusItem {
  final String label;
  final IconData icon;
  final _PhotoCheckStatusState state;

  const _PhotoCheckStatusItem({
    required this.label,
    required this.icon,
    required this.state,
  });

  _PhotoCheckStatusItem copyWith({
    String? label,
    IconData? icon,
    _PhotoCheckStatusState? state,
  }) {
    return _PhotoCheckStatusItem(
      label: label ?? this.label,
      icon: icon ?? this.icon,
      state: state ?? this.state,
    );
  }
}

List<_PhotoCheckStatusItem> _initialPhotoCheckStatuses() {
  return const [
    _PhotoCheckStatusItem(
      label: 'Лицо видно',
      icon: Icons.face_retouching_natural_outlined,
      state: _PhotoCheckStatusState.pending,
    ),
    _PhotoCheckStatusItem(
      label: 'Свет подходит',
      icon: Icons.wb_sunny_outlined,
      state: _PhotoCheckStatusState.pending,
    ),
    _PhotoCheckStatusItem(
      label: 'Фото достаточно четкое',
      icon: Icons.center_focus_strong_outlined,
      state: _PhotoCheckStatusState.pending,
    ),
    _PhotoCheckStatusItem(
      label: 'Снимок готов',
      icon: Icons.check_circle_outline,
      state: _PhotoCheckStatusState.pending,
    ),
  ];
}

List<_PhotoCheckStatusItem> _buildPhotoCheckStatuses(
  Map<String, dynamic> analysis,
) {
  final photoQuality = _mapValue(_mapValue(analysis['analysis'])['photoQuality']);
  final faceOk =
      photoQuality['faceDetected'] == true &&
      photoQuality['singlePerson'] == true &&
      photoQuality['faceVisibleLarge'] == true;
  final lightOk = _photoLightIsOk(photoQuality);
  final sharpnessOk = _photoSharpnessIsOk(photoQuality);
  final overallOk = analysis['can_continue'] == true;

  return [
    _initialPhotoCheckStatuses()[0].copyWith(
      state: faceOk
          ? _PhotoCheckStatusState.passed
          : _PhotoCheckStatusState.failed,
    ),
    _initialPhotoCheckStatuses()[1].copyWith(
      state: lightOk
          ? _PhotoCheckStatusState.passed
          : _PhotoCheckStatusState.failed,
    ),
    _initialPhotoCheckStatuses()[2].copyWith(
      state: sharpnessOk
          ? _PhotoCheckStatusState.passed
          : _PhotoCheckStatusState.failed,
    ),
    _initialPhotoCheckStatuses()[3].copyWith(
      state: overallOk
          ? _PhotoCheckStatusState.passed
          : _PhotoCheckStatusState.failed,
    ),
  ];
}

bool _photoLightIsOk(Map<String, dynamic> quality) {
  final value = _stringValue(quality['lightQuality'])?.toLowerCase();
  return value == null || value == 'good' || value == 'medium';
}

bool _photoSharpnessIsOk(Map<String, dynamic> quality) {
  final value = _stringValue(quality['sharpness'])?.toLowerCase();
  return value == null || value == 'good' || value == 'medium';
}

String _photoCheckDescription(Map<String, dynamic>? analysis) {
  final retryHint = _stringValue(analysis?['retry_hint']);
  if (retryHint != null) return retryHint;
  return 'Снимок пока не подходит для точного подбора. Выберите другое фото и повторите проверку.';
}

String _photoCheckCaption(
  _PhotoCheckPhase phase,
  Map<String, dynamic>? analysis,
) {
  switch (phase) {
    case _PhotoCheckPhase.accepted:
      return 'Проверка завершена: фото прошло все этапы перед анализом лица.';
    case _PhotoCheckPhase.rejected:
      return _photoCheckDescription(analysis);
    case _PhotoCheckPhase.checking:
      return 'Проверяем видимость лица, свет, четкость и готовность снимка.';
  }
}

class _PhotoCheckStatusCard extends StatelessWidget {
  final _PhotoCheckStatusItem item;

  const _PhotoCheckStatusCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final trailingIcon = switch (item.state) {
      _PhotoCheckStatusState.passed => Icons.check,
      _PhotoCheckStatusState.failed => Icons.close,
      _PhotoCheckStatusState.checking => Icons.autorenew,
      _PhotoCheckStatusState.pending => Icons.more_horiz,
    };
    final color = switch (item.state) {
      _PhotoCheckStatusState.passed => GlameColors.textPrimary,
      _PhotoCheckStatusState.failed => const Color(0xFF9A6A6A),
      _PhotoCheckStatusState.checking => GlameColors.textPrimary,
      _PhotoCheckStatusState.pending => GlameColors.textSecondary,
    };

    return Container(
      height: 78,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
      decoration: BoxDecoration(
        border: Border.all(color: const Color(0xFFD6D6D6)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(item.icon, size: 18, color: color),
              const Spacer(),
              Icon(trailingIcon, size: 16, color: color),
            ],
          ),
          const SizedBox(height: 10),
          Expanded(
            child: Text(
              item.label,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 12,
                height: 1.15,
                color: color,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class PhotoSelectionResultScreen extends StatelessWidget {
  final PhotoSelectionResultArgs? args;

  const PhotoSelectionResultScreen({super.key, this.args});

  @override
  Widget build(BuildContext context) {
    final result = args;
    final generation = _mapValue(result?.generation);
    final fallbackAnalysis = _mapValue(result?.analysis);
    final generatedAnalysis = _mapValue(generation['photo_analysis']);
    final analysis = generatedAnalysis.isNotEmpty
        ? generatedAnalysis
        : fallbackAnalysis;
    final generatedLook = _mapValue(generation['generated_look']);
    final tryOnResult = _mapValue(generation['try_on_result']);
    final recommendations = _mapValue(analysis['recommendations']);
    final analysisProducts = analysis['recommended_products'];
    final products = _extractPhotoSelectionProducts(
      generatedLook['products'] is List && (generatedLook['products'] as List).isNotEmpty
          ? generatedLook['products']
          : analysisProducts,
    );
    final previewUrl = _resolvePhotoResultPreviewUrl(
      generatedLook: generatedLook,
      tryOnResult: tryOnResult,
    );
    final lookId = _stringValue(generatedLook['id']);
    final lookName = _stringValue(generatedLook['name']) ?? 'Рекомендации по фото';
    final lookDescription = _stringValue(generatedLook['description']);
    final lookStyle =
        _stringValue(analysis['style']) ?? _stringValue(generatedLook['style']);
    final metalColors = _stringList(recommendations['metal_colors']);
    final stoneColors = _stringList(recommendations['stone_colors']);
    final styleHints = _stringList(recommendations['styles']);
    final userFacing = _mapValue(analysis['user_facing']);
    final humanReadable = _mapValue(analysis['human_readable']);
    final humanSummary = _stringValue(humanReadable['summary']);
    final humanAppearance = _stringValue(humanReadable['appearance']);
    final humanFace = _stringValue(humanReadable['face']);
    final humanStyleType = _stringValue(humanReadable['style_type']);
    final humanColorType = _stringValue(humanReadable['color_type']);
    final humanBullets = _stringList(humanReadable['bullets']);
    final analysisSummary = _stringValue(userFacing['summary']);
    final analysisBullets = _stringList(userFacing['bullets']);

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go('/home');
            }
          },
          icon: const Icon(Icons.arrow_back),
        ),
        title: const GlameHeaderLogo(),
      ),
      body: SafeArea(
        top: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(28, 24, 28, 32),
          child: result == null
              ? const _PhotoResultEmptyState()
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      'Ваш подбор',
                      style: TextStyle(
                        fontSize: 40,
                        height: 0.98,
                        fontWeight: FontWeight.w400,
                        color: GlameColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 14),
                    const Text(
                      'Мы собрали направление и украшения, которые будут смотреться естественно и точно.',
                      style: TextStyle(
                        fontSize: 18,
                        height: 1.42,
                        color: GlameColors.textSecondary,
                      ),
                    ),
                    const SizedBox(height: 28),
                    _PhotoResultPreviewCard(
                      imageUrl: previewUrl,
                      fallbackBytes: result.bytes,
                    ),
                    const SizedBox(height: 18),
                    Container(
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(
                        border: Border.all(color: const Color(0xFFD6D6D6)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Направление подбора',
                            style: TextStyle(
                              fontSize: 14,
                              height: 1.2,
                              color: GlameColors.textSecondary,
                            ),
                          ),
                          const SizedBox(height: 10),
                          Text(
                            lookName,
                            style: const TextStyle(
                              fontSize: 28,
                              height: 1.02,
                              fontWeight: FontWeight.w400,
                              color: GlameColors.textPrimary,
                            ),
                          ),
                          if (lookDescription != null) ...[
                            const SizedBox(height: 12),
                            Text(
                              lookDescription,
                              style: const TextStyle(
                                fontSize: 16,
                                height: 1.45,
                                color: GlameColors.textSecondary,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                    if (humanSummary != null) ...[
                      const SizedBox(height: 18),
                      Container(
                        padding: const EdgeInsets.all(18),
                        decoration: BoxDecoration(
                          border: Border.all(color: const Color(0xFFD6D6D6)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Описание внешности',
                              style: TextStyle(
                                fontSize: 14,
                                height: 1.2,
                                color: GlameColors.textSecondary,
                              ),
                            ),
                            const SizedBox(height: 10),
                            Text(
                              humanSummary,
                              style: const TextStyle(
                                fontSize: 18,
                                height: 1.42,
                                color: GlameColors.textPrimary,
                              ),
                            ),
                            if (humanAppearance != null) ...[
                              const SizedBox(height: 12),
                              Text(
                                humanAppearance,
                                style: const TextStyle(
                                  fontSize: 15,
                                  height: 1.45,
                                  color: GlameColors.textSecondary,
                                ),
                              ),
                            ],
                            if (humanFace != null) ...[
                              const SizedBox(height: 10),
                              Text(
                                humanFace,
                                style: const TextStyle(
                                  fontSize: 15,
                                  height: 1.45,
                                  color: GlameColors.textSecondary,
                                ),
                              ),
                            ],
                            if (humanStyleType != null || humanColorType != null) ...[
                              const SizedBox(height: 14),
                              Wrap(
                                spacing: 10,
                                runSpacing: 10,
                                children: [
                                  if (humanStyleType != null)
                                    _PhotoResultChip(label: 'Типаж: $humanStyleType'),
                                  if (humanColorType != null)
                                    _PhotoResultChip(label: 'Цветотип: $humanColorType'),
                                ],
                              ),
                            ],
                            for (final bullet in humanBullets) ...[
                              const SizedBox(height: 10),
                              Text(
                                '• $bullet',
                                style: const TextStyle(
                                  fontSize: 15,
                                  height: 1.4,
                                  color: GlameColors.textSecondary,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ],
                    if (analysisSummary != null) ...[
                      const SizedBox(height: 18),
                      Container(
                        padding: const EdgeInsets.all(18),
                        decoration: BoxDecoration(
                          border: Border.all(color: const Color(0xFFD6D6D6)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Что мы увидели',
                              style: TextStyle(
                                fontSize: 14,
                                height: 1.2,
                                color: GlameColors.textSecondary,
                              ),
                            ),
                            const SizedBox(height: 10),
                            Text(
                              analysisSummary,
                              style: const TextStyle(
                                fontSize: 18,
                                height: 1.42,
                                color: GlameColors.textPrimary,
                              ),
                            ),
                            for (final bullet in analysisBullets) ...[
                              const SizedBox(height: 10),
                              Text(
                                '• $bullet',
                                style: const TextStyle(
                                  fontSize: 15,
                                  height: 1.4,
                                  color: GlameColors.textSecondary,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ],
                    const SizedBox(height: 18),
                    const Text(
                      'Лучше всего Вам подойдут',
                      style: TextStyle(
                        fontSize: 24,
                        height: 1.05,
                        fontWeight: FontWeight.w400,
                        color: GlameColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: [
                        if (lookStyle != null)
                          _PhotoResultChip(label: 'Характер: $lookStyle'),
                        if (styleHints.isNotEmpty)
                          _PhotoResultChip(label: styleHints.join(' • ')),
                        if (metalColors.isNotEmpty)
                          _PhotoResultChip(
                            label: 'Металлы: ${metalColors.join(', ')}',
                          ),
                        if (stoneColors.isNotEmpty)
                          _PhotoResultChip(
                            label: 'Камни: ${stoneColors.join(', ')}',
                          ),
                      ],
                    ),
                    const SizedBox(height: 24),
                    if (products.isNotEmpty) ...[
                      const Text(
                        'Украшения из подборки',
                        style: TextStyle(
                          fontSize: 24,
                          height: 1.05,
                          fontWeight: FontWeight.w400,
                          color: GlameColors.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 14),
                      for (var index = 0; index < products.length; index++) ...[
                        _PhotoResultProductCard(product: products[index]),
                        if (index != products.length - 1)
                          const SizedBox(height: 12),
                      ],
                      const SizedBox(height: 20),
                    ],
                    if (lookId != null) ...[
                      _PhotoPrimaryButton(
                        title: 'Открыть образ',
                        onTap: () => context.push('/look/$lookId'),
                      ),
                      const SizedBox(height: 12),
                    ],
                    _PhotoSecondaryButton(
                      title: 'Написать стилисту',
                      onTap: () => context.push(
                        buildStylistChatRoute(
                          initialMessage:
                              'Хочу продолжить подбор украшений по фото.',
                          source: 'selection_screen',
                          scenario: 'live_stylist',
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    _PhotoSecondaryButton(
                      title: 'Выбрать другое фото',
                      onTap: () => startPhotoSelectionFlow(context),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}

class PhotoSelectionPromoCard extends StatelessWidget {
  final double height;
  final String title;
  final String description;
  final String? imageAssetPath;
  final String? imageUrl;
  final double? imageAspectRatio;
  final bool useFixedHeightWhenImage;

  const PhotoSelectionPromoCard({
    super.key,
    required this.height,
    required this.title,
    required this.description,
    this.imageAssetPath,
    this.imageUrl,
    this.imageAspectRatio,
    this.useFixedHeightWhenImage = false,
  });

  @override
  Widget build(BuildContext context) {
    final resolvedImageUrl = (imageUrl ?? '').trim();
    final resolvedAssetPath = (imageAssetPath ?? '').trim();
    final hasNetworkImage = resolvedImageUrl.isNotEmpty;
    final hasAssetImage = resolvedAssetPath.isNotEmpty;

    if (hasNetworkImage || hasAssetImage) {
      final aspectRatio =
          imageAspectRatio ??
          (hasAssetImage ? _promoImageAspectRatio(resolvedAssetPath) : 1);
      if (useFixedHeightWhenImage) {
        return Container(
          height: height,
          decoration: BoxDecoration(
            border: Border.all(color: const Color(0xFFD6D6D6)),
          ),
          child: hasNetworkImage
              ? CachedNetworkImage(
                  imageUrl: resolvedImageUrl,
                  width: double.infinity,
                  height: double.infinity,
                  fit: BoxFit.contain,
                  alignment: Alignment.topCenter,
                  placeholder: (_, _) =>
                      const ColoredBox(color: Color(0xFFF4F1EC)),
                  errorWidget: (_, _, _) => hasAssetImage
                      ? Image.asset(
                          resolvedAssetPath,
                          width: double.infinity,
                          height: double.infinity,
                          fit: BoxFit.contain,
                          alignment: Alignment.topCenter,
                        )
                      : const ColoredBox(color: Color(0xFFF4F1EC)),
                )
              : Image.asset(
                  resolvedAssetPath,
                  width: double.infinity,
                  height: double.infinity,
                  fit: BoxFit.contain,
                  alignment: Alignment.topCenter,
                ),
        );
      }
      return Container(
        decoration: BoxDecoration(
          border: Border.all(color: const Color(0xFFD6D6D6)),
        ),
        child: AspectRatio(
          aspectRatio: aspectRatio,
          child: hasNetworkImage
              ? CachedNetworkImage(
                  imageUrl: resolvedImageUrl,
                  width: double.infinity,
                  fit: BoxFit.contain,
                  alignment: Alignment.topCenter,
                  placeholder: (_, _) => const ColoredBox(color: Color(0xFFF4F1EC)),
                  errorWidget: (_, _, _) => hasAssetImage
                      ? Image.asset(
                          resolvedAssetPath,
                          width: double.infinity,
                          fit: BoxFit.contain,
                          alignment: Alignment.topCenter,
                        )
                      : const ColoredBox(color: Color(0xFFF4F1EC)),
                )
              : Image.asset(
                  resolvedAssetPath,
                  width: double.infinity,
                  fit: BoxFit.contain,
                  alignment: Alignment.topCenter,
                ),
        ),
      );
    }

    return Container(
      height: height,
      decoration: BoxDecoration(
        border: Border.all(color: const Color(0xFFD6D6D6)),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF1E1E1E), Color(0xFF0F0F10), Color(0xFF272727)],
        ),
      ),
      child: Stack(
        children: [
          Positioned(
            left: 22,
            top: 22,
            child: Container(
              width: 28,
              height: 1,
              color: GlameColors.surface2.withValues(alpha: 0.7),
            ),
          ),
          Positioned(
            right: 22,
            top: 22,
            child: Container(
              width: 28,
              height: 1,
              color: GlameColors.surface2.withValues(alpha: 0.7),
            ),
          ),
          Positioned(
            left: 22,
            top: 22,
            child: Container(
              width: 1,
              height: 28,
              color: GlameColors.surface2.withValues(alpha: 0.7),
            ),
          ),
          Positioned(
            right: 22,
            top: 22,
            child: Container(
              width: 1,
              height: 28,
              color: GlameColors.surface2.withValues(alpha: 0.7),
            ),
          ),
          Positioned(
            left: 22,
            bottom: 22,
            child: Container(
              width: 28,
              height: 1,
              color: GlameColors.surface2.withValues(alpha: 0.7),
            ),
          ),
          Positioned(
            right: 22,
            bottom: 22,
            child: Container(
              width: 28,
              height: 1,
              color: GlameColors.surface2.withValues(alpha: 0.7),
            ),
          ),
          Positioned(
            left: 22,
            bottom: 22,
            child: Container(
              width: 1,
              height: 28,
              color: GlameColors.surface2.withValues(alpha: 0.7),
            ),
          ),
          Positioned(
            right: 22,
            bottom: 22,
            child: Container(
              width: 1,
              height: 28,
              color: GlameColors.surface2.withValues(alpha: 0.7),
            ),
          ),
          Positioned(
            right: 28,
            top: 56,
            bottom: 56,
            child: Container(
              width: 172,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    GlameColors.surface2.withValues(alpha: 0.26),
                    GlameColors.surface2.withValues(alpha: 0.1),
                  ],
                ),
              ),
            ),
          ),
          Positioned(
            left: 28,
            top: 34,
            child: SizedBox(
              width: 200,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontSize: 34,
                      height: 1.02,
                      fontWeight: FontWeight.w400,
                      color: GlameColors.surface2,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    description,
                    style: const TextStyle(
                      fontSize: 17,
                      height: 1.48,
                      color: GlameColors.surface2,
                    ),
                  ),
                ],
              ),
            ),
          ),
          Positioned(
            left: 28,
            right: 28,
            bottom: 30,
            child: Column(
              children: const [
                _VisualFeatureLine(
                  icon: Icons.adjust_outlined,
                  label: 'Ваш стиль',
                ),
                SizedBox(height: 10),
                _VisualFeatureLine(
                  icon: Icons.auto_awesome_outlined,
                  label: 'Образ',
                ),
                SizedBox(height: 10),
                _VisualFeatureLine(
                  icon: Icons.diamond_outlined,
                  label: 'Украшения',
                ),
                SizedBox(height: 10),
                _VisualFeatureLine(
                  icon: Icons.tune_outlined,
                  label: 'Подбор',
                ),
                SizedBox(height: 10),
                _VisualFeatureLine(
                  icon: Icons.favorite_border,
                  label: 'Рекомендации',
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

double _promoImageAspectRatio(String imageAssetPath) {
  switch (imageAssetPath) {
    case 'assets/images/home/home_block_3_photo_selection.png':
      return 2 / 3;
    case 'assets/images/home/photo_upload_intro.png':
      return 1315 / 1197;
    default:
      return 1;
  }
}

class PhotoSelectionInfoCard extends StatelessWidget {
  final bool compact;

  const PhotoSelectionInfoCard({super.key, this.compact = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(compact ? 14 : 18),
      decoration: BoxDecoration(
        border: Border.all(color: const Color(0xFFD6D6D6)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.info_outline,
            size: compact ? 22 : 28,
            color: GlameColors.textPrimary,
          ),
          SizedBox(width: compact ? 10 : 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Сначала посмотрите, какое фото подойдет',
                  style: TextStyle(
                    fontSize: compact ? 15 : 17,
                    height: compact ? 1.12 : 1.2,
                    color: GlameColors.textPrimary,
                  ),
                ),
                SizedBox(height: compact ? 4 : 6),
                Text(
                  'Это поможет получить более точный подбор.',
                  style: TextStyle(
                    fontSize: compact ? 12 : 14,
                    height: compact ? 1.22 : 1.35,
                    color: GlameColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PhotoGuideSheet extends StatelessWidget {
  final String primaryLabel;
  final VoidCallback onPrimaryTap;

  const _PhotoGuideSheet({
    required this.primaryLabel,
    required this.onPrimaryTap,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Container(
        margin: const EdgeInsets.all(16),
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
        decoration: const BoxDecoration(color: GlameColors.surface2),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'Какое фото подойдет',
                    style: TextStyle(
                      fontSize: 24,
                      height: 1.05,
                      color: GlameColors.textPrimary,
                    ),
                  ),
                ),
                IconButton(
                  onPressed: () => Navigator.of(context).pop(),
                  icon: const Icon(Icons.close),
                ),
              ],
            ),
            const Text(
              'Чтобы подбор был точнее, выберите спокойный портрет, где хорошо видно лицо.',
              style: TextStyle(
                fontSize: 16,
                height: 1.4,
                color: GlameColors.textSecondary,
              ),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                border: Border.all(color: const Color(0xFFD6D6D6)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Text(
                    'Пример удачного фото',
                    style: TextStyle(
                      fontSize: 14,
                      color: GlameColors.textPrimary,
                    ),
                  ),
                  SizedBox(height: 10),
                  _GuideExamplePhoto(),
                  SizedBox(height: 14),
                  _GuideRule(label: 'Один человек в кадре'),
                  SizedBox(height: 8),
                  _GuideRule(label: 'Лицо видно крупно'),
                  SizedBox(height: 8),
                  _GuideRule(label: 'Мягкий свет'),
                  SizedBox(height: 8),
                  _GuideRule(label: 'Без очков и сильных фильтров'),
                  SizedBox(height: 8),
                  _GuideRule(label: 'По возможности открыты уши и шея'),
                ],
              ),
            ),
            const SizedBox(height: 14),
            const Row(
              children: [
                Icon(
                  Icons.info_outline,
                  size: 18,
                  color: GlameColors.textSecondary,
                ),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Если фото не подойдет, мы подскажем, как его улучшить.',
                    style: TextStyle(
                      fontSize: 14,
                      height: 1.35,
                      color: GlameColors.textSecondary,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            _PhotoPrimaryButton(
              title: primaryLabel,
              onTap: () {
                Navigator.of(context).pop();
                onPrimaryTap();
              },
            ),
            const SizedBox(height: 10),
            _PhotoSecondaryButton(
              title: 'Закрыть',
              onTap: () => Navigator.of(context).pop(),
            ),
          ],
        ),
      ),
    );
  }
}

class _PhotoSourcePickerSheet extends StatelessWidget {
  final VoidCallback onCameraTap;
  final VoidCallback onGalleryTap;
  final VoidCallback onGuideTap;

  const _PhotoSourcePickerSheet({
    required this.onCameraTap,
    required this.onGalleryTap,
    required this.onGuideTap,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Container(
        margin: const EdgeInsets.all(16),
        padding: const EdgeInsets.fromLTRB(18, 24, 18, 16),
        decoration: const BoxDecoration(color: GlameColors.surface2),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Продолжить с фото',
              style: TextStyle(
                fontSize: 24,
                height: 1.05,
                color: GlameColors.textPrimary,
              ),
            ),
            const SizedBox(height: 12),
            const Text(
              'Выберите, как добавить фото для подбора. Дальше мы проверим, подходит ли снимок для следующего шага.',
              style: TextStyle(
                fontSize: 16,
                height: 1.4,
                color: GlameColors.textSecondary,
              ),
            ),
            const SizedBox(height: 18),
            _PhotoPrimaryButton(
              title: 'Сделать фото',
              icon: Icons.photo_camera_outlined,
              onTap: onCameraTap,
            ),
            const SizedBox(height: 12),
            _PhotoSecondaryButton(
              title: 'Выбрать из галереи',
              icon: Icons.image_outlined,
              onTap: onGalleryTap,
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                border: Border.all(color: const Color(0xFFD6D6D6)),
              ),
              child: InkWell(
                onTap: onGuideTap,
                child: const Row(
                  children: [
                    Icon(
                      Icons.info_outline,
                      size: 24,
                      color: GlameColors.textPrimary,
                    ),
                    SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Какое фото подойдет',
                            style: TextStyle(
                              fontSize: 17,
                              height: 1.2,
                              color: GlameColors.textPrimary,
                            ),
                          ),
                          SizedBox(height: 4),
                          Text(
                            'Короткая инструкция перед загрузкой',
                            style: TextStyle(
                              fontSize: 14,
                              height: 1.35,
                              color: GlameColors.textSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Icon(
                      Icons.chevron_right,
                      size: 22,
                      color: GlameColors.textSecondary,
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Не сейчас'),
            ),
          ],
        ),
      ),
    );
  }
}

class _PhotoAuthGateSheet extends StatelessWidget {
  final VoidCallback onLoginTap;
  final VoidCallback onRegisterTap;
  final VoidCallback onPhoneTap;

  const _PhotoAuthGateSheet({
    required this.onLoginTap,
    required this.onRegisterTap,
    required this.onPhoneTap,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Container(
        margin: const EdgeInsets.all(16),
        padding: const EdgeInsets.fromLTRB(18, 24, 18, 16),
        decoration: const BoxDecoration(color: GlameColors.surface2),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Войдите, чтобы продолжить',
              style: TextStyle(
                fontSize: 24,
                height: 1.05,
                color: GlameColors.textPrimary,
              ),
            ),
            const SizedBox(height: 14),
            const Text(
              'Подбор по фото доступен после входа в профиль. Так мы сможем сохранить результат и собрать персональную подборку именно для Вас.',
              style: TextStyle(
                fontSize: 16,
                height: 1.42,
                color: GlameColors.textSecondary,
              ),
            ),
            const SizedBox(height: 16),
            Container(height: 1, color: const Color(0xFFD6D6D6)),
            const SizedBox(height: 14),
            const Row(
              children: [
                Icon(
                  Icons.autorenew,
                  size: 18,
                  color: GlameColors.textSecondary,
                ),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'После входа Вы сразу вернетесь к загрузке фото.',
                    style: TextStyle(
                      fontSize: 14,
                      height: 1.35,
                      color: GlameColors.textSecondary,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            _PhotoPrimaryButton(title: 'Войти', onTap: onLoginTap),
            const SizedBox(height: 10),
            _PhotoSecondaryButton(
              title: 'Создать аккаунт',
              onTap: onRegisterTap,
            ),
            const SizedBox(height: 10),
            _PhotoSecondaryButton(
              title: 'Продолжить по номеру',
              icon: Icons.smartphone_outlined,
              onTap: onPhoneTap,
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Не сейчас'),
            ),
          ],
        ),
      ),
    );
  }
}

class _GuideExamplePhoto extends StatelessWidget {
  const _GuideExamplePhoto();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: Border.all(color: const Color(0xFFE3DED6)),
      ),
      child: AspectRatio(
        aspectRatio: 4 / 3,
        child: Image.asset(
          'assets/images/home/photo_guide_example.png',
          width: double.infinity,
          fit: BoxFit.contain,
        ),
      ),
    );
  }
}

class _FaceFrameOverlay extends StatelessWidget {
  const _FaceFrameOverlay();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned(
          left: 18,
          top: 18,
          child: _FrameCorner(top: true, left: true),
        ),
        Positioned(
          right: 18,
          top: 18,
          child: _FrameCorner(top: true, left: false),
        ),
        Positioned(
          left: 18,
          bottom: 18,
          child: _FrameCorner(top: false, left: true),
        ),
        Positioned(
          right: 18,
          bottom: 18,
          child: _FrameCorner(top: false, left: false),
        ),
      ],
    );
  }
}

class _FrameCorner extends StatelessWidget {
  final bool top;
  final bool left;

  const _FrameCorner({required this.top, required this.left});

  @override
  Widget build(BuildContext context) {
    final borderColor = GlameColors.surface2.withValues(alpha: 0.85);
    return SizedBox(
      width: 34,
      height: 34,
      child: CustomPaint(
        painter: _CornerPainter(
          borderColor: borderColor,
          top: top,
          left: left,
        ),
      ),
    );
  }
}

class _CornerPainter extends CustomPainter {
  final Color borderColor;
  final bool top;
  final bool left;

  const _CornerPainter({
    required this.borderColor,
    required this.top,
    required this.left,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = borderColor
      ..strokeWidth = 1
      ..style = PaintingStyle.stroke;
    final path = Path();
    if (top && left) {
      path
        ..moveTo(size.width, 0)
        ..lineTo(0, 0)
        ..lineTo(0, size.height);
    } else if (top && !left) {
      path
        ..moveTo(0, 0)
        ..lineTo(size.width, 0)
        ..lineTo(size.width, size.height);
    } else if (!top && left) {
      path
        ..moveTo(0, 0)
        ..lineTo(0, size.height)
        ..lineTo(size.width, size.height);
    } else {
      path
        ..moveTo(size.width, 0)
        ..lineTo(size.width, size.height)
        ..lineTo(0, size.height);
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _CornerPainter oldDelegate) {
    return oldDelegate.borderColor != borderColor ||
        oldDelegate.top != top ||
        oldDelegate.left != left;
  }
}

class _GuideRule extends StatelessWidget {
  final String label;

  const _GuideRule({required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const Icon(
          Icons.check_circle_outline,
          size: 20,
          color: GlameColors.textSecondary,
        ),
        const SizedBox(width: 10),
        Text(
          label,
          style: const TextStyle(
            fontSize: 15,
            height: 1.3,
            color: GlameColors.textPrimary,
          ),
        ),
      ],
    );
  }
}

class _ValidationChip extends StatelessWidget {
  final String label;

  const _ValidationChip({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        border: Border.all(color: const Color(0xFFD6D6D6)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(
            Icons.check,
            size: 16,
            color: GlameColors.textPrimary,
          ),
          const SizedBox(width: 8),
          Text(
            label,
            style: const TextStyle(
              fontSize: 14,
              height: 1.2,
              color: GlameColors.textPrimary,
            ),
          ),
        ],
      ),
    );
  }
}

class _VisualFeatureLine extends StatelessWidget {
  final IconData icon;
  final String label;

  const _VisualFeatureLine({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 118,
          height: 42,
          decoration: BoxDecoration(
            border: Border.all(color: GlameColors.surface2.withValues(alpha: 0.8)),
          ),
          child: Row(
            children: [
              SizedBox(
                width: 42,
                child: Icon(icon, size: 18, color: GlameColors.surface2),
              ),
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                    fontSize: 14,
                    color: GlameColors.surface2,
                  ),
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: Container(
            height: 1,
            margin: const EdgeInsets.only(left: 12),
            color: GlameColors.surface2.withValues(alpha: 0.28),
          ),
        ),
      ],
    );
  }
}

class _PhotoPrimaryButton extends StatelessWidget {
  final String title;
  final IconData? icon;
  final VoidCallback onTap;

  const _PhotoPrimaryButton({
    required this.title,
    required this.onTap,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 58,
      child: Material(
        color: Colors.transparent,
        child: Ink(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.centerLeft,
              end: Alignment.centerRight,
              colors: [Color(0xFF202020), Color(0xFF0F0F10), Color(0xFF262626)],
            ),
          ),
          child: InkWell(
            onTap: onTap,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (icon != null) ...[
                  Icon(icon, size: 22, color: GlameColors.surface2),
                  const SizedBox(width: 12),
                ],
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 20,
                    height: 1.05,
                    fontWeight: FontWeight.w400,
                    color: GlameColors.surface2,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _PhotoSecondaryButton extends StatelessWidget {
  final String title;
  final IconData? icon;
  final VoidCallback onTap;

  const _PhotoSecondaryButton({
    required this.title,
    required this.onTap,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 58,
      child: OutlinedButton(
        onPressed: onTap,
        style: OutlinedButton.styleFrom(
          side: const BorderSide(color: Color(0xFFD6D6D6)),
          padding: const EdgeInsets.symmetric(horizontal: 18),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (icon != null) ...[
              Icon(icon, size: 22, color: GlameColors.textPrimary),
              const SizedBox(width: 12),
            ],
            Text(
              title,
              style: const TextStyle(
                fontSize: 20,
                height: 1.05,
                fontWeight: FontWeight.w400,
                color: GlameColors.textPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PhotoAnalysisErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  final VoidCallback onBack;

  const _PhotoAnalysisErrorState({
    required this.message,
    required this.onRetry,
    required this.onBack,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'Подбор не завершен',
          style: TextStyle(
            fontSize: 40,
            height: 0.98,
            fontWeight: FontWeight.w400,
            color: GlameColors.textPrimary,
          ),
        ),
        const SizedBox(height: 14),
        Text(
          message,
          style: const TextStyle(
            fontSize: 18,
            height: 1.42,
            color: GlameColors.textSecondary,
          ),
        ),
        const SizedBox(height: 24),
        _PhotoPrimaryButton(title: 'Попробовать снова', onTap: onRetry),
        const SizedBox(height: 12),
        _PhotoSecondaryButton(title: 'Вернуться к фото', onTap: onBack),
      ],
    );
  }
}

class _PhotoResultEmptyState extends StatelessWidget {
  const _PhotoResultEmptyState();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Результат пока недоступен',
          style: TextStyle(
            fontSize: 40,
            height: 0.98,
            fontWeight: FontWeight.w400,
            color: GlameColors.textPrimary,
          ),
        ),
        SizedBox(height: 14),
        Text(
          'Попробуйте пройти сценарий подбора по фото заново.',
          style: TextStyle(
            fontSize: 18,
            height: 1.42,
            color: GlameColors.textSecondary,
          ),
        ),
      ],
    );
  }
}

class _PhotoResultPreviewCard extends StatelessWidget {
  final String? imageUrl;
  final Uint8List fallbackBytes;

  const _PhotoResultPreviewCard({
    required this.imageUrl,
    required this.fallbackBytes,
  });

  @override
  Widget build(BuildContext context) {
    return _AdaptivePhotoFrame(
      referenceBytes: fallbackBytes,
      borderColor: const Color(0xFFD6D6D6),
      image: imageUrl != null
          ? CachedNetworkImage(
              imageUrl: imageUrl!,
              fit: BoxFit.contain,
            )
          : Image.memory(fallbackBytes, fit: BoxFit.contain),
      overlay: Positioned(
        left: 16,
        top: 16,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          color: GlameColors.surface2.withValues(alpha: 0.92),
          child: const Text(
            'Визуализация подбора',
            style: TextStyle(
              fontSize: 13,
              height: 1.2,
              color: GlameColors.textPrimary,
            ),
          ),
        ),
      ),
    );
  }
}

class _AdaptivePhotoFrame extends StatefulWidget {
  final Uint8List referenceBytes;
  final Widget image;
  final Widget? overlay;
  final Color borderColor;

  const _AdaptivePhotoFrame({
    required this.referenceBytes,
    required this.image,
    required this.borderColor,
    this.overlay,
  });

  @override
  State<_AdaptivePhotoFrame> createState() => _AdaptivePhotoFrameState();
}

class _AdaptivePhotoFrameState extends State<_AdaptivePhotoFrame> {
  double? _aspectRatio;

  @override
  void initState() {
    super.initState();
    _resolveAspectRatio();
  }

  @override
  void didUpdateWidget(covariant _AdaptivePhotoFrame oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.referenceBytes != widget.referenceBytes) {
      _resolveAspectRatio();
    }
  }

  Future<void> _resolveAspectRatio() async {
    final codec = await ui.instantiateImageCodec(widget.referenceBytes);
    final frame = await codec.getNextFrame();
    final image = frame.image;
    if (!mounted) return;
    setState(() {
      _aspectRatio = image.width / image.height;
    });
  }

  @override
  Widget build(BuildContext context) {
    final aspectRatio = _aspectRatio ?? 1;
    return Container(
      decoration: BoxDecoration(
        border: Border.all(color: widget.borderColor),
      ),
      child: AspectRatio(
        aspectRatio: aspectRatio,
        child: Stack(
          fit: StackFit.expand,
          children: [
            widget.image,
            if (widget.overlay != null) widget.overlay!,
          ],
        ),
      ),
    );
  }
}

class _PhotoResultChip extends StatelessWidget {
  final String label;

  const _PhotoResultChip({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        border: Border.all(color: const Color(0xFFD6D6D6)),
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 14,
          height: 1.3,
          color: GlameColors.textPrimary,
        ),
      ),
    );
  }
}

class _PhotoResultProductCard extends StatelessWidget {
  final _PhotoSelectionProduct product;

  const _PhotoResultProductCard({required this.product});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => context.push('/product/${product.id}'),
      child: Container(
        decoration: BoxDecoration(
          border: Border.all(color: const Color(0xFFD6D6D6)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 120,
              height: 140,
              child: product.imageUrl == null
                  ? Container(color: GlameColors.warmGray)
                  : CachedNetworkImage(
                      imageUrl: product.imageUrl!,
                      fit: BoxFit.cover,
                    ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (product.brand != null) ...[
                      Text(
                        product.brand!,
                        style: const TextStyle(
                          fontSize: 12,
                          height: 1.2,
                          letterSpacing: 0.6,
                          color: GlameColors.textSecondary,
                        ),
                      ),
                      const SizedBox(height: 6),
                    ],
                    Text(
                      product.name,
                      style: const TextStyle(
                        fontSize: 18,
                        height: 1.2,
                        color: GlameColors.textPrimary,
                      ),
                    ),
                    if (product.category != null) ...[
                      const SizedBox(height: 8),
                      Text(
                        product.category!,
                        style: const TextStyle(
                          fontSize: 14,
                          height: 1.35,
                          color: GlameColors.textSecondary,
                        ),
                      ),
                    ],
                    const SizedBox(height: 14),
                    Text(
                      product.priceLabel,
                      style: const TextStyle(
                        fontSize: 16,
                        height: 1.2,
                        color: GlameColors.textPrimary,
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
}

class _PhotoSelectionProduct {
  final String id;
  final String name;
  final String? brand;
  final String? category;
  final String? imageUrl;
  final String priceLabel;

  const _PhotoSelectionProduct({
    required this.id,
    required this.name,
    required this.priceLabel,
    this.brand,
    this.category,
    this.imageUrl,
  });
}

Map<String, dynamic> _mapValue(dynamic value) {
  if (value is Map) {
    return Map<String, dynamic>.from(value);
  }
  return const <String, dynamic>{};
}

String? _stringValue(dynamic value) {
  if (value == null) return null;
  final normalized = value.toString().trim();
  if (normalized.isEmpty) return null;
  return normalized;
}

List<String> _stringList(dynamic value) {
  if (value is! List) return const <String>[];
  return value
      .map(_stringValue)
      .whereType<String>()
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

List<_PhotoSelectionProduct> _extractPhotoSelectionProducts(dynamic value) {
  if (value is! List) return const <_PhotoSelectionProduct>[];

  final result = <_PhotoSelectionProduct>[];
  for (final item in value) {
    final raw = _mapValue(item);
    final id = _stringValue(raw['id']);
    final name = _stringValue(raw['name']);
    if (id == null || name == null) continue;

    result.add(
      _PhotoSelectionProduct(
        id: id,
        name: name,
        brand: _stringValue(raw['brand']),
        category: _stringValue(raw['category']),
        imageUrl: _resolveProductImageUrl(raw),
        priceLabel: _resolveProductPriceLabel(raw['price']),
      ),
    );
  }
  return result;
}

String _resolveProductPriceLabel(dynamic rawPrice) {
  final formatted = formatRubFromKopeks(rawPrice);
  return formatted.isEmpty ? 'Цена уточняется' : formatted;
}

String? _resolveProductImageUrl(Map<String, dynamic> raw) {
  final images = raw['images'];
  if (images is List) {
    for (final item in images) {
      if (item is Map) {
        final resolved =
            resolveAssetUrl(item['url']) ??
            resolveAssetUrl(item['thumbnail_url']) ??
            resolveAssetUrl(item['image_url']);
        if (resolved != null && resolved.isNotEmpty) {
          return resolved;
        }
      } else {
        final resolved = resolveAssetUrl(item);
        if (resolved != null && resolved.isNotEmpty) {
          return resolved;
        }
      }
    }
  }
  return resolveAssetUrl(raw['image_url']);
}

String? _resolvePhotoResultPreviewUrl({
  required Map<String, dynamic> generatedLook,
  required Map<String, dynamic> tryOnResult,
}) {
  final candidates = [
    generatedLook['try_on_image_url'],
    tryOnResult['try_on_image_url'],
    tryOnResult['user_photo_url'],
    generatedLook['image_url'],
  ];
  for (final candidate in candidates) {
    final resolved = resolveAssetUrl(candidate);
    if (resolved != null && resolved.isNotEmpty) {
      return resolved;
    }
  }
  return null;
}

String _photoSelectionErrorMessage(DioException error) {
  final data = error.response?.data;
  if (data is Map) {
    final detail = _stringValue(data['detail']) ?? _stringValue(data['message']);
    if (detail != null) return detail;
  }
  return 'Не удалось выполнить подбор. Попробуйте еще раз.';
}
