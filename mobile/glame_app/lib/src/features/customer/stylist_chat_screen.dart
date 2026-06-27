import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/network/asset_url.dart';
import '../../core/formatters/rub.dart';
import '../../core/theme/glame_theme.dart';
import '../../core/widgets/glame_auth_gate.dart';
import '../auth/auth_controller.dart';
import '../product/product_providers.dart';
import 'customer_cabinet_providers.dart';

const _chatSurface = Color(0xFF121416);
const _chatSurfaceLow = Color(0xFF1A1C1E);
const _chatSurfaceHigh = Color(0xFF282A2C);
const _chatBorder = Color(0xFF5C6064);
const _chatText = Color(0xFFE2E2E5);
const _chatTextMuted = Color(0xFFC4C7C8);
const _chatTextDim = Color(0xFF8E9192);

class StylistChatScreen extends ConsumerStatefulWidget {
  final String? productId;
  final String? initialMessage;
  final String? source;
  final String? scenario;
  final List<String> quickTags;
  final List<String> favoriteProductIds;

  const StylistChatScreen({
    super.key,
    this.productId,
    this.initialMessage,
    this.source,
    this.scenario,
    this.quickTags = const <String>[],
    this.favoriteProductIds = const <String>[],
  });

  @override
  ConsumerState<StylistChatScreen> createState() => _StylistChatScreenState();
}

class _StylistChatScreenState extends ConsumerState<StylistChatScreen> {
  final controller = TextEditingController();
  final scrollController = ScrollController();
  final picker = ImagePicker();
  Timer? _chatPollingTimer;
  XFile? pickedPhoto;
  bool sending = false;
  bool initialAutoSent = false;
  Map<String, dynamic>? pendingUserMessage;
  bool assistantTyping = false;

  @override
  void initState() {
    super.initState();
    final isLoggedIn = ref.read(authControllerProvider).user != null;
    if (!isLoggedIn) return;
    _startChatPolling();
    final initial = (widget.initialMessage ?? '').trim();
    if (initial.isNotEmpty) {
      controller.text = initial;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || initialAutoSent) return;
        initialAutoSent = true;
        _send();
      });
    } else if ((widget.productId ?? '').isNotEmpty) {
      controller.text = 'Помогите подобрать украшения под меня';
    }
  }

  @override
  void dispose() {
    _chatPollingTimer?.cancel();
    controller.dispose();
    scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    if (auth.user == null) {
      return _StylistChatAuthGate(resumeRoute: _resumeRoute());
    }

    final messagesAsync = ref.watch(stylistChatMessagesProvider);
    final statusAsync = ref.watch(stylistChatStatusProvider);
    final productId = (widget.productId ?? '').trim();
    final productAsync = productId.isEmpty
        ? null
        : ref.watch(productProvider(productId));
    return Scaffold(
      backgroundColor: _chatSurface,
      body: Column(
        children: [
          _StylistChatTopBar(statusAsync: statusAsync),
          if (productAsync != null)
            productAsync.maybeWhen(
              data: (product) => _ChatProductCard(product: product),
              orElse: () => const SizedBox.shrink(),
            ),
          Expanded(
            child: Stack(
              children: [
                const Positioned.fill(child: _ChatBackgroundPattern()),
                Positioned.fill(
                  child: messagesAsync.when(
                    data: (messages) {
                      WidgetsBinding.instance.addPostFrameCallback(
                        (_) => _toBottom(),
                      );
                      final displayMessages = <Map<String, dynamic>>[
                        ...messages,
                        ?pendingUserMessage,
                        if (statusAsync.valueOrNull case final status?)
                          if (((status['stylist_typing'] is Map
                                  ? Map<String, dynamic>.from(
                                      status['stylist_typing'] as Map,
                                    )
                                  : const <String, dynamic>{})['is_typing'] ==
                              true))
                            {
                              'id': '__assistant_typing__',
                              'role': 'assistant',
                              'text': '',
                              'attachments': const [],
                              'payload': {'typing': true},
                            }
                          else if (assistantTyping)
                            {
                              'id': '__assistant_typing__',
                              'role': 'assistant',
                              'text': '',
                              'attachments': const [],
                              'payload': {'typing': true},
                            },
                      ];
                      if (displayMessages.isEmpty) return const _EmptyChat();
                      return ListView.builder(
                        controller: scrollController,
                        padding: const EdgeInsets.fromLTRB(28, 24, 28, 24),
                        itemCount: displayMessages.length + 1,
                        itemBuilder: (context, index) {
                          if (index == 0) return const _ChatDateSeparator();
                          return _MessageBubble(
                            message: displayMessages[index - 1],
                          );
                        },
                      );
                    },
                    loading: () => const Center(
                      child: CircularProgressIndicator(color: _chatText),
                    ),
                    error: (_, _) => const Center(
                      child: Text(
                        'Не удалось загрузить чат',
                        style: TextStyle(color: _chatTextMuted),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          _Composer(
            controller: controller,
            pickedPhoto: pickedPhoto,
            sending: sending,
            quickTags: _composerQuickTags,
            onQuickTag: _applyQuickTag,
            onPick: _pickPhoto,
            onClearPhoto: () => setState(() => pickedPhoto = null),
            onSend: _send,
          ),
        ],
      ),
    );
  }

  Future<void> _pickPhoto() async {
    final photo = await picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 82,
      maxWidth: 1800,
    );
    if (photo == null) return;
    setState(() => pickedPhoto = photo);
  }

  Future<void> _send() async {
    if (ref.read(authControllerProvider).user == null) {
      context.go('/login?next=${Uri.encodeComponent(_resumeRoute())}');
      return;
    }
    final text = controller.text.trim();
    if (text.isEmpty && pickedPhoto == null) return;
    final file = pickedPhoto;
    Uint8List? photoBytes;
    if (file != null) {
      photoBytes = await file.readAsBytes();
    }
    final tempUserMessage = <String, dynamic>{
      'id': '__pending_user__',
      'role': 'user',
      'text': text,
      'attachments': file == null
          ? const <Map<String, dynamic>>[]
          : <Map<String, dynamic>>[
              {
                'type': 'image',
                'bytes': photoBytes,
                'name': file.name,
                'is_local_memory': true,
              },
            ],
      'payload': const <String, dynamic>{'pending': true},
    };
    controller.clear();
    setState(() {
      sending = true;
      pendingUserMessage = tempUserMessage;
      assistantTyping = true;
      pickedPhoto = null;
    });
    try {
      MultipartFile? photo;
      if (file != null && photoBytes != null) {
        photo = MultipartFile.fromBytes(photoBytes, filename: file.name);
      }
      await ref
          .read(customerCabinetApiProvider)
          .sendStylistChatMessage(
            text: text,
            productId: widget.productId,
            photo: photo,
            source: widget.source ?? 'customer_stylist_chat',
            scenario: widget.scenario ?? 'live_stylist',
            quickTags: widget.quickTags,
            favoriteProductIds: widget.favoriteProductIds,
          );
      await _refreshChat(forceStatusRefresh: true);
    } catch (e) {
      if (!mounted) return;
      String message = 'Не удалось отправить сообщение';
      if (e is DioException) {
        final data = e.response?.data;
        if (data is Map && data['detail'] != null) {
          message = data['detail'].toString();
        } else if (data is String && data.trim().isNotEmpty) {
          message = data;
        } else if (e.message != null && e.message!.trim().isNotEmpty) {
          message = e.message!.trim();
        }
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    } finally {
      if (mounted) {
        setState(() {
          sending = false;
          pendingUserMessage = null;
        });
      }
    }
  }

  void _toBottom() {
    if (!scrollController.hasClients) return;
    scrollController.animateTo(
      scrollController.position.maxScrollExtent,
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOut,
    );
  }

  void _startChatPolling() {
    _chatPollingTimer?.cancel();
    _chatPollingTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (!mounted || sending) return;
      unawaited(_refreshChat(forceStatusRefresh: true));
    });
  }

  Future<void> _refreshChat({bool forceStatusRefresh = false}) async {
    ref.invalidate(stylistChatMessagesProvider);
    if (forceStatusRefresh) {
      ref.invalidate(stylistChatStatusProvider);
    }
    try {
      await ref.read(stylistChatMessagesProvider.future);
      if (forceStatusRefresh) {
        await ref.read(stylistChatStatusProvider.future);
      }
    } catch (_) {
      // Ignore background refresh failures and keep the current chat visible.
    }
  }

  String _resumeRoute() {
    final query = <String, String>{};
    void add(String key, String? value) {
      final normalized = (value ?? '').trim();
      if (normalized.isNotEmpty) query[key] = normalized;
    }

    add('product_id', widget.productId);
    add('message', widget.initialMessage);
    add('source', widget.source);
    add('scenario', widget.scenario);
    if (widget.quickTags.isNotEmpty) {
      query['quick_tags'] = widget.quickTags.join(',');
    }
    if (widget.favoriteProductIds.isNotEmpty) {
      query['favorite_ids'] = widget.favoriteProductIds.join(',');
    }
    return Uri(path: '/stylist-chat', queryParameters: query).toString();
  }

  void _applyQuickTag(String value) {
    if (sending) return;
    final normalized = value.trim();
    if (normalized.isEmpty) return;
    final current = controller.text.trim();
    controller.text = current.isEmpty ? normalized : '$current\n$normalized';
    controller.selection = TextSelection.collapsed(
      offset: controller.text.length,
    );
  }
}

const _composerQuickTags = <String>['Для себя', 'В подарок', 'Хочу примерить'];

class _StylistChatTopBar extends StatelessWidget {
  final AsyncValue<Map<String, dynamic>> statusAsync;

  const _StylistChatTopBar({required this.statusAsync});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).padding.top + 56,
      padding: EdgeInsets.only(top: MediaQuery.of(context).padding.top),
      decoration: const BoxDecoration(
        color: _chatSurface,
        border: Border(bottom: BorderSide(color: _chatBorder)),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 56,
            height: 56,
            child: IconButton(
              tooltip: 'Назад',
              onPressed: () {
                if (Navigator.of(context).canPop()) {
                  Navigator.of(context).pop();
                } else {
                  context.go('/home?tab=3');
                }
              },
              icon: const Icon(
                Icons.arrow_back_ios_new,
                color: _chatText,
                size: 24,
              ),
            ),
          ),
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text(
                  'Стилист GLAME',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 24,
                    height: 1,
                    color: _chatText,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 6),
                statusAsync.when(
                  data: (status) => _ChatStatusLine(status: status),
                  loading: () => const _ChatStatusText(
                    text: 'На связи сейчас · до 20:00 по МСК',
                  ),
                  error: (_, _) => const _ChatStatusText(
                    text: 'График стилиста: 10:00-20:00 по МСК',
                  ),
                ),
              ],
            ),
          ),
          SizedBox(
            width: 56,
            height: 56,
            child: IconButton(
              tooltip: 'Меню',
              onPressed: () {},
              icon: const Icon(Icons.more_horiz, color: _chatText, size: 28),
            ),
          ),
        ],
      ),
    );
  }
}

class _ChatStatusLine extends StatelessWidget {
  final Map<String, dynamic> status;

  const _ChatStatusLine({required this.status});

  @override
  Widget build(BuildContext context) {
    final statusText = (status['status_text'] as String?)?.trim();
    final typingRaw = status['stylist_typing'];
    final typing = typingRaw is Map
        ? Map<String, dynamic>.from(typingRaw)
        : const <String, dynamic>{};
    final typingName = (typing['stylist_name'] as String?)?.trim();
    final stylistTyping = typing['is_typing'] == true;
    if (stylistTyping) {
      return _ChatStatusText(
        text: typingName == null || typingName.isEmpty
            ? 'Стилист печатает'
            : '$typingName печатает',
      );
    }
    return _ChatStatusText(
      text: statusText == null || statusText.isEmpty
          ? 'На связи сейчас · до 20:00 по МСК'
          : statusText,
    );
  }
}

class _ChatStatusText extends StatelessWidget {
  final String text;

  const _ChatStatusText({required this.text});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(width: 8, height: 8, color: _chatTextMuted),
        const SizedBox(width: 8),
        Flexible(
          child: Text(
            text.toUpperCase(),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 12,
              height: 1,
              color: _chatTextMuted,
              letterSpacing: 0.7,
            ),
          ),
        ),
      ],
    );
  }
}

class _ChatBackgroundPattern extends StatelessWidget {
  const _ChatBackgroundPattern();

  @override
  Widget build(BuildContext context) {
    return CustomPaint(painter: _ChatBackgroundPatternPainter());
  }
}

class _ChatBackgroundPatternPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawColor(_chatSurface, BlendMode.src);
    final paint = Paint()
      ..color = Colors.white.withValues(alpha: 0.018)
      ..strokeWidth = 1;
    const step = 20.0;
    for (var x = -size.height; x < size.width; x += step) {
      canvas.drawLine(
        Offset(x, size.height),
        Offset(x + size.height, 0),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _ChatDateSeparator extends StatelessWidget {
  const _ChatDateSeparator();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        margin: const EdgeInsets.only(bottom: 24),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
        decoration: BoxDecoration(border: Border.all(color: _chatBorder)),
        child: const Text(
          'СЕГОДНЯ',
          style: TextStyle(
            fontSize: 12,
            color: _chatText,
            letterSpacing: 1,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
    );
  }
}

class _StylistChatAuthGate extends StatelessWidget {
  final String resumeRoute;

  const _StylistChatAuthGate({required this.resumeRoute});

  @override
  Widget build(BuildContext context) {
    return GlameAuthGate(
      eyebrow: 'Стилист GLAME',
      title: 'Войдите, чтобы написать стилисту',
      description:
          'Чат со стилистом доступен после входа. Так мы сохраним историю переписки, подборки и сможем продолжить консультацию с того же места.',
      note: 'После входа Вы вернетесь в чат стилиста.',
      noteIcon: Icons.chat_bubble_outline,
      showTopBar: true,
      onLogin: () =>
          context.go('/login?next=${Uri.encodeComponent(resumeRoute)}'),
      onRegister: () =>
          context.go('/auth/register?next=${Uri.encodeComponent(resumeRoute)}'),
    );
  }
}

class _EmptyChat extends StatelessWidget {
  const _EmptyChat();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
        child: Container(
          width: double.infinity,
          constraints: const BoxConstraints(maxWidth: 520),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
          decoration: BoxDecoration(
            color: _chatSurfaceLow,
            border: Border.all(color: _chatBorder),
          ),
          child: const Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'СТАРТ ДИАЛОГА',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 24,
                  height: 1,
                  fontWeight: FontWeight.w400,
                  color: _chatText,
                ),
              ),
              SizedBox(height: 12),
              Text(
                'Напишите стилисту, что хотите подобрать. Можно приложить фото для более точного подбора.',
                textAlign: TextAlign.center,
                style: TextStyle(color: _chatTextMuted, height: 1.45),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ChatProductCard extends StatelessWidget {
  final Map<String, dynamic> product;

  const _ChatProductCard({required this.product});

  @override
  Widget build(BuildContext context) {
    final images = product['images'];
    final imageUrl = images is List && images.isNotEmpty
        ? resolveAssetUrl(images.first)
        : null;
    return Container(
      margin: const EdgeInsets.fromLTRB(20, 6, 20, 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: _chatSurfaceLow,
        border: Border.all(color: _chatBorder),
      ),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: _chatSurface,
              border: Border.all(color: _chatBorder),
            ),
            child: imageUrl == null
                ? Container(color: GlameColors.surface)
                : CachedNetworkImage(imageUrl: imageUrl, fit: BoxFit.cover),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              ((product['name'] as String?) ?? 'GLAME').toUpperCase(),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 12,
                letterSpacing: .6,
                color: _chatText,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Text(
            formatRubFromKopeks(product['price']),
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: _chatText,
            ),
          ),
        ],
      ),
    );
  }
}

class _MessageBubble extends ConsumerWidget {
  final Map<String, dynamic> message;

  const _MessageBubble({required this.message});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final role = (message['role'] as String?) ?? 'assistant';
    final own = role == 'user';
    final text = (message['text'] as String?)?.trim() ?? '';
    final attachmentsRaw = message['attachments'];
    final attachments = attachmentsRaw is List
        ? attachmentsRaw
              .whereType<Map>()
              .map((x) => Map<String, dynamic>.from(x))
              .toList()
        : <Map<String, dynamic>>[];
    final imageAttachments = attachments.where((item) {
      final type = (item['type'] as String?)?.trim().toLowerCase();
      return type == null || type.isEmpty || type == 'image';
    }).toList();
    final productAttachments = attachments.where((item) {
      final type = (item['type'] as String?)?.trim().toLowerCase();
      return type == 'product';
    }).toList();
    final payloadRaw = message['payload'];
    final payload = payloadRaw is Map<String, dynamic>
        ? payloadRaw
        : payloadRaw is Map
        ? Map<String, dynamic>.from(payloadRaw)
        : const <String, dynamic>{};
    final isTyping = payload['typing'] == true;
    final dialogStepRaw =
        ((payload['dialog_step'] ?? payload['cjm_stage']) as String?)
            ?.trim()
            .toLowerCase();
    final inlineInsertAt = !own ? _findInlineProductsInsertIndex(text) : null;
    final hasInlineProducts =
        !own && inlineInsertAt != null && _messageHasProducts(payload);
    final textBefore = hasInlineProducts
        ? text.substring(0, inlineInsertAt).trimRight()
        : text;
    final textAfter = hasInlineProducts
        ? text.substring(inlineInsertAt).trimLeft()
        : '';

    final bubble = Container(
      constraints: const BoxConstraints(maxWidth: 520),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: own ? _chatSurfaceHigh : _chatSurfaceLow,
        border: Border.all(color: _chatBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!own &&
              dialogStepRaw != null &&
              dialogStepRaw.isNotEmpty &&
              !isTyping)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _DialogStepChip(step: dialogStepRaw),
            ),
          if (imageAttachments.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(bottom: text.isEmpty ? 0 : 10),
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: imageAttachments.map((item) {
                  final isLocalMemory = item['is_local_memory'] == true;
                  final localBytes = isLocalMemory && item['bytes'] is Uint8List
                      ? item['bytes'] as Uint8List
                      : null;
                  final url = isLocalMemory
                      ? null
                      : resolveAssetUrl(item['url']);
                  final hasLocalMemory =
                      localBytes != null && localBytes.isNotEmpty;
                  return GestureDetector(
                    onTap: (url == null && !hasLocalMemory)
                        ? null
                        : () => _openChatImagePreview(
                            context,
                            imageUrl: url,
                            localImageBytes: localBytes,
                            imageName: (item['name'] as String?)?.trim(),
                          ),
                    child: Container(
                      width: 96,
                      height: 96,
                      decoration: BoxDecoration(
                        color: _chatSurface,
                        border: Border.all(color: _chatBorder),
                      ),
                      child: hasLocalMemory
                          ? Image.memory(localBytes, fit: BoxFit.cover)
                          : url == null
                          ? Container(color: _chatSurface)
                          : CachedNetworkImage(
                              imageUrl: url,
                              fit: BoxFit.cover,
                            ),
                    ),
                  );
                }).toList(),
              ),
            ),
          if (productAttachments.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(
                top: imageAttachments.isNotEmpty ? 10 : 0,
              ),
              child: _MessageAttachmentProductsBlock(
                attachments: productAttachments,
              ),
            ),
          if (textBefore.isNotEmpty)
            Text(
              textBefore,
              textAlign: own ? TextAlign.right : TextAlign.left,
              style: const TextStyle(
                height: 1.35,
                color: _chatText,
                fontSize: 16,
              ),
            ),
          if (hasInlineProducts)
            _AssistantProductsBlock(
              message: message,
              showTitle: false,
              compactSpacing: true,
            ),
          if (textAfter.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                textAfter,
                style: const TextStyle(
                  height: 1.35,
                  color: _chatText,
                  fontSize: 16,
                ),
              ),
            ),
          if (isTyping) const _TypingIndicator(),
          if (!own) ...[
            _AssistantInteractiveBlock(message: message),
            _AssistantStoresBlock(message: message),
            _AssistantLooksBlock(message: message),
            if (!hasInlineProducts) _AssistantProductsBlock(message: message),
          ],
        ],
      ),
    );

    final time = _messageTimeLabel(message);
    return Padding(
      padding: const EdgeInsets.only(bottom: 22),
      child: Align(
        alignment: own ? Alignment.centerRight : Alignment.centerLeft,
        child: Column(
          crossAxisAlignment: own
              ? CrossAxisAlignment.end
              : CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                if (!own) ...[
                  const _StylistAvatar(),
                  const SizedBox(width: 12),
                ],
                Flexible(child: bubble),
              ],
            ),
            if (time != null)
              Padding(
                padding: EdgeInsets.only(top: 6, left: own ? 0 : 48),
                child: Text(
                  time,
                  style: const TextStyle(
                    fontSize: 12,
                    color: _chatTextMuted,
                    letterSpacing: 0.4,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _StylistAvatar extends StatelessWidget {
  const _StylistAvatar();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 34,
      height: 34,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: _chatSurfaceHigh,
        border: Border.all(color: _chatBorder),
      ),
      child: const Text(
        'G',
        style: TextStyle(
          color: _chatText,
          fontSize: 14,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

String? _messageTimeLabel(Map<String, dynamic> message) {
  final raw =
      message['created_at'] ??
      message['createdAt'] ??
      message['timestamp'] ??
      message['time'];
  if (raw == null) return null;
  if (raw is String) {
    final parsed = DateTime.tryParse(raw);
    if (parsed != null) {
      final local = parsed.toLocal();
      return '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
    }
    final trimmed = raw.trim();
    return trimmed.isEmpty ? null : trimmed;
  }
  return null;
}

void _openChatImagePreview(
  BuildContext context, {
  String? imageUrl,
  Uint8List? localImageBytes,
  String? imageName,
}) {
  showDialog<void>(
    context: context,
    barrierColor: Colors.black.withValues(alpha: 0.88),
    builder: (ctx) {
      return Dialog(
        insetPadding: const EdgeInsets.all(16),
        backgroundColor: Colors.transparent,
        child: Stack(
          children: [
            Positioned.fill(
              child: InteractiveViewer(
                minScale: 1,
                maxScale: 4,
                child: Center(
                  child: localImageBytes != null && localImageBytes.isNotEmpty
                      ? Image.memory(localImageBytes, fit: BoxFit.contain)
                      : imageUrl == null
                      ? const Center(
                          child: Text(
                            'Не удалось загрузить фото',
                            style: TextStyle(color: Colors.white),
                          ),
                        )
                      : CachedNetworkImage(
                          imageUrl: imageUrl,
                          fit: BoxFit.contain,
                          placeholder: (_, _) =>
                              const Center(child: CircularProgressIndicator()),
                          errorWidget: (_, _, _) => const Center(
                            child: Text(
                              'Не удалось загрузить фото',
                              style: TextStyle(color: Colors.white),
                            ),
                          ),
                        ),
                ),
              ),
            ),
            Positioned(
              top: 12,
              left: 16,
              right: 72,
              child: Text(
                (imageName == null || imageName.isEmpty) ? 'Фото' : imageName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            Positioned(
              top: 0,
              right: 0,
              child: IconButton(
                onPressed: () => Navigator.of(ctx).pop(),
                icon: const Icon(Icons.close, color: Colors.white),
              ),
            ),
          ],
        ),
      );
    },
  );
}

class _MessageAttachmentProductsBlock extends StatelessWidget {
  final List<Map<String, dynamic>> attachments;

  const _MessageAttachmentProductsBlock({required this.attachments});

  @override
  Widget build(BuildContext context) {
    if (attachments.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: attachments
          .map((item) {
            final productId = (item['product_id'] as String?)?.trim() ?? '';
            final imageUrl = resolveAssetUrl(item['image_url']);
            final title =
                ((item['name'] as String?) ??
                        (item['article'] as String?) ??
                        'Украшение')
                    .trim();
            final subtitle =
                [
                      (item['brand'] as String?)?.trim(),
                      (item['category'] as String?)?.trim(),
                      (item['article'] as String?)?.trim(),
                    ]
                    .whereType<String>()
                    .where((value) => value.isNotEmpty)
                    .join(' · ');
            final price = _parsePrice(item['price']);
            return InkWell(
              onTap: productId.isEmpty
                  ? null
                  : () => context.push('/product/$productId'),
              child: Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: _chatSurfaceLow,
                  border: Border.all(color: _chatBorder),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 64,
                      height: 64,
                      decoration: BoxDecoration(
                        color: GlameColors.surface,
                        border: Border.all(color: _chatBorder),
                      ),
                      child: imageUrl == null
                          ? Container(color: GlameColors.surface)
                          : CachedNetworkImage(
                              imageUrl: imageUrl,
                              fit: BoxFit.cover,
                            ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            title,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: _chatText,
                            ),
                          ),
                          if (subtitle.isNotEmpty) ...[
                            const SizedBox(height: 4),
                            Text(
                              subtitle,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 11,
                                color: _chatTextMuted,
                              ),
                            ),
                          ],
                          const SizedBox(height: 6),
                          Text(
                            price <= 0
                                ? 'Цена уточняется'
                                : formatRubFromKopeks(price),
                            style: const TextStyle(
                              fontSize: 12,
                              color: _chatText,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 10),
                    const Icon(
                      Icons.open_in_new,
                      size: 18,
                      color: _chatTextMuted,
                    ),
                  ],
                ),
              ),
            );
          })
          .toList(growable: false),
    );
  }
}

class _DialogStepChip extends StatelessWidget {
  final String step;

  const _DialogStepChip({required this.step});

  @override
  Widget build(BuildContext context) {
    final label = _dialogStepLabel(step);
    if (label == null) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: _chatSurfaceHigh,
        border: Border.all(color: _chatBorder),
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: _chatTextMuted,
        ),
      ),
    );
  }
}

String? _dialogStepLabel(String step) {
  switch (step) {
    case 'inspiration':
      return 'Этап: знакомство';
    case 'consideration':
      return 'Этап: подбор';
    case 'purchase':
      return 'Этап: покупка';
    default:
      return null;
  }
}

bool _messageHasProducts(Map<String, dynamic> payload) {
  final productsRaw = payload['products'];
  if (productsRaw is List && productsRaw.isNotEmpty) return true;
  final looksRaw = payload['looks'];
  if (looksRaw is! List || looksRaw.isEmpty) return false;
  for (final look in looksRaw) {
    if (look is! Map) continue;
    final lookProducts = look['products'];
    if (lookProducts is List && lookProducts.isNotEmpty) return true;
  }
  return false;
}

int? _findInlineProductsInsertIndex(String text) {
  final value = text.trim();
  if (value.isEmpty) return null;
  final patterns = <RegExp>[
    RegExp(r'подобрал[аи]?[^\n.!?]*[.!?]\s*', caseSensitive: false),
    RegExp(r'предлага[юе][^\n.!?]*[.!?]\s*', caseSensitive: false),
    RegExp(r'вот[^\n.!?]*вариант[^\n.!?]*[.!?]\s*', caseSensitive: false),
    RegExp(r'специально для тебя[^\n.!?]*[.!?]\s*', caseSensitive: false),
  ];
  for (final pattern in patterns) {
    final match = pattern.firstMatch(text);
    if (match != null) return match.end;
  }
  return null;
}

class _TypingIndicator extends StatefulWidget {
  const _TypingIndicator();

  @override
  State<_TypingIndicator> createState() => _TypingIndicatorState();
}

class _AssistantInteractiveBlock extends StatelessWidget {
  final Map<String, dynamic> message;

  const _AssistantInteractiveBlock({required this.message});

  @override
  Widget build(BuildContext context) {
    final payloadRaw = message['payload'];
    final payload = payloadRaw is Map<String, dynamic>
        ? payloadRaw
        : payloadRaw is Map
        ? Map<String, dynamic>.from(payloadRaw)
        : const <String, dynamic>{};
    final brands = _extractInteractiveItems(payload['brands']);
    final sections = _extractInteractiveItems(payload['sections']);
    if (brands.isEmpty && sections.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (brands.isNotEmpty)
            _InteractiveChipsRow(
              title: 'Бренды',
              items: brands,
              onTap: (item) => _openInteractiveItem(context, item),
            ),
          if (sections.isNotEmpty)
            _InteractiveChipsRow(
              title: 'Разделы',
              items: sections,
              onTap: (item) => _openInteractiveItem(context, item),
            ),
        ],
      ),
    );
  }
}

class _InteractiveChipsRow extends StatelessWidget {
  final String title;
  final List<_InteractiveItem> items;
  final void Function(_InteractiveItem item) onTap;

  const _InteractiveChipsRow({
    required this.title,
    required this.items,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final visible = items.take(6).toList(growable: false);
    final hasMore = items.length > visible.length;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 12,
              color: GlameColors.textSecondary,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: visible.map((item) {
              final label = item.label;
              if (label.isEmpty) return const SizedBox.shrink();
              return ActionChip(
                label: Text(label),
                onPressed: () => onTap(item),
              );
            }).toList(),
          ),
          if (hasMore)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: TextButton(
                onPressed: () => _showAllInteractiveItems(
                  context: context,
                  title: title,
                  items: items,
                  onTap: onTap,
                ),
                child: const Text('Показать все'),
              ),
            ),
        ],
      ),
    );
  }
}

class _InteractiveItem {
  final String label;
  final String? search;
  final String? category;
  final num score;

  const _InteractiveItem({
    required this.label,
    this.search,
    this.category,
    this.score = 0,
  });
}

List<_InteractiveItem> _extractInteractiveItems(dynamic raw) {
  if (raw is! List || raw.isEmpty) return const <_InteractiveItem>[];
  final result = <_InteractiveItem>[];
  final seen = <String>{};
  for (final item in raw) {
    if (item is! Map) continue;
    final map = Map<String, dynamic>.from(item);
    final label =
        ((map['name'] ?? map['title'] ?? map['label'] ?? map['value'])
                as String?)
            ?.trim() ??
        '';
    if (label.isEmpty) continue;
    final dedupeKey = label.toLowerCase();
    if (!seen.add(dedupeKey)) continue;
    final search = (map['search'] as String?)?.trim();
    final category = (map['category'] as String?)?.trim();
    final score = (map['score'] as num?) ?? 0;
    result.add(
      _InteractiveItem(
        label: label,
        search: search?.isEmpty == true ? null : search,
        category: category?.isEmpty == true ? null : category,
        score: score,
      ),
    );
  }
  result.sort((a, b) {
    final scoreCmp = b.score.compareTo(a.score);
    if (scoreCmp != 0) return scoreCmp;
    return a.label.toLowerCase().compareTo(b.label.toLowerCase());
  });
  return result;
}

void _showAllInteractiveItems({
  required BuildContext context,
  required String title,
  required List<_InteractiveItem> items,
  required void Function(_InteractiveItem item) onTap,
}) {
  showDialog<void>(
    context: context,
    builder: (ctx) {
      return AlertDialog(
        title: Text(title),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: items
                  .map((item) {
                    return ActionChip(
                      label: Text(item.label),
                      onPressed: () {
                        Navigator.of(ctx).pop();
                        onTap(item);
                      },
                    );
                  })
                  .toList(growable: false),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Закрыть'),
          ),
        ],
      );
    },
  );
}

void _openInteractiveItem(BuildContext context, _InteractiveItem item) {
  final category = (item.category ?? '').trim();
  if (category.isNotEmpty) {
    _openCatalogByCategory(context, category);
    return;
  }
  final search = (item.search ?? item.label).trim();
  _openCatalogBySearch(context, search);
}

void _openCatalogBySearch(BuildContext context, String search) {
  final value = search.trim();
  if (value.isEmpty) return;
  final uri = Uri(
    path: '/home',
    queryParameters: {'tab': '1', 'search': value},
  );
  context.push(uri.toString());
}

void _openCatalogByCategory(BuildContext context, String category) {
  final value = category.trim();
  if (value.isEmpty) return;
  final uri = Uri(
    path: '/home',
    queryParameters: {'tab': '1', 'category': value},
  );
  context.push(uri.toString());
}

class _TypingIndicatorState extends State<_TypingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(3, (index) {
          return AnimatedBuilder(
            animation: _controller,
            builder: (context, child) {
              final phase = (_controller.value * 3 - index).clamp(0.0, 1.0);
              final opacity = 0.25 + (phase * 0.75);
              return Opacity(
                opacity: opacity,
                child: Container(
                  margin: const EdgeInsets.only(right: 4),
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(
                    color: _chatTextMuted,
                    shape: BoxShape.circle,
                  ),
                ),
              );
            },
          );
        }),
      ),
    );
  }
}

class _AssistantStoresBlock extends StatelessWidget {
  final Map<String, dynamic> message;

  const _AssistantStoresBlock({required this.message});

  @override
  Widget build(BuildContext context) {
    final payloadRaw = message['payload'];
    final payload = payloadRaw is Map<String, dynamic>
        ? payloadRaw
        : payloadRaw is Map
        ? Map<String, dynamic>.from(payloadRaw)
        : const <String, dynamic>{};
    final shouldShowStores = payload['show_stores'] == true;
    if (!shouldShowStores) return const SizedBox.shrink();

    final stores = _extractStoresFromMessage(message);
    if (stores.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Магазины',
            style: TextStyle(
              fontSize: 12,
              color: GlameColors.textSecondary,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          ...stores.take(3).map((store) {
            final hasPoint = store.latitude != null && store.longitude != null;
            return Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: GlameColors.surface2,
                border: Border.all(color: GlameColors.lightGray),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    store.title,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${store.city}: ${store.address}',
                    style: const TextStyle(
                      fontSize: 12,
                      color: GlameColors.textSecondary,
                    ),
                  ),
                  if (store.workingHours != null &&
                      store.workingHours!.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text(
                        'Часы: ${store.workingHours}',
                        style: const TextStyle(
                          fontSize: 12,
                          color: GlameColors.textSecondary,
                        ),
                      ),
                    ),
                  if (hasPoint) ...[
                    const SizedBox(height: 8),
                    _StoreMiniMap(store: store),
                    const SizedBox(height: 8),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: OutlinedButton.icon(
                        onPressed: () => _openStoreOnMap(store),
                        icon: const Icon(Icons.map_outlined, size: 16),
                        label: const Text('Открыть на карте'),
                      ),
                    ),
                  ],
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

class _StoreItem {
  final String title;
  final String city;
  final String address;
  final String? workingHours;
  final String? phone;
  final double? latitude;
  final double? longitude;

  const _StoreItem({
    required this.title,
    required this.city,
    required this.address,
    this.workingHours,
    this.phone,
    this.latitude,
    this.longitude,
  });
}

class _StoreMiniMap extends StatelessWidget {
  final _StoreItem store;

  const _StoreMiniMap({required this.store});

  @override
  Widget build(BuildContext context) {
    final lat = store.latitude;
    final lng = store.longitude;
    if (lat == null || lng == null) return const SizedBox.shrink();
    final mapUrl = _buildStoreStaticMapUrl(lat: lat, lng: lng);

    return SizedBox(
      height: 160,
      child: Stack(
        fit: StackFit.expand,
        children: [
          Container(
            decoration: BoxDecoration(
              border: Border.all(color: GlameColors.lightGray),
            ),
            child: CachedNetworkImage(
              imageUrl: mapUrl,
              fit: BoxFit.cover,
              placeholder: (_, _) => Container(color: GlameColors.surface),
              errorWidget: (_, _, _) => Container(
                color: GlameColors.surface,
                alignment: Alignment.center,
                child: const Text(
                  'Карта недоступна',
                  style: TextStyle(
                    fontSize: 12,
                    color: GlameColors.textSecondary,
                  ),
                ),
              ),
            ),
          ),
          const Positioned(
            right: 8,
            top: 8,
            child: Icon(Icons.location_on, color: GlameColors.gold, size: 26),
          ),
        ],
      ),
    );
  }
}

String _buildStoreStaticMapUrl({required double lat, required double lng}) {
  final latS = lat.toStringAsFixed(6);
  final lngS = lng.toStringAsFixed(6);
  return 'https://static-maps.yandex.ru/1.x/?ll=$lngS,$latS&z=14&l=map&size=600,260&pt=$lngS,$latS,pm2rdm';
}

List<_StoreItem> _extractStoresFromMessage(Map<String, dynamic> message) {
  final payloadRaw = message['payload'];
  final payload = payloadRaw is Map<String, dynamic>
      ? payloadRaw
      : payloadRaw is Map
      ? Map<String, dynamic>.from(payloadRaw)
      : const <String, dynamic>{};
  final storesRaw = payload['stores'];
  if (storesRaw is! List || storesRaw.isEmpty) return const <_StoreItem>[];
  final stores = <_StoreItem>[];
  for (final raw in storesRaw) {
    if (raw is! Map) continue;
    final item = Map<String, dynamic>.from(raw);
    final title = ((item['title'] as String?) ?? '').trim();
    final city = ((item['city'] as String?) ?? '').trim();
    final address = ((item['address'] as String?) ?? '').trim();
    if (title.isEmpty || city.isEmpty || address.isEmpty) continue;
    stores.add(
      _StoreItem(
        title: title,
        city: city,
        address: address,
        workingHours: (item['working_hours'] as String?)?.trim(),
        phone: (item['phone'] as String?)?.trim(),
        latitude: _asDouble(item['latitude']),
        longitude: _asDouble(item['longitude']),
      ),
    );
  }
  return stores;
}

double? _asDouble(dynamic value) {
  if (value is num) return value.toDouble();
  if (value is String) {
    return double.tryParse(value.trim().replaceAll(',', '.'));
  }
  return null;
}

Future<void> _openStoreOnMap(_StoreItem store) async {
  final lat = store.latitude;
  final lng = store.longitude;
  if (lat == null || lng == null) return;
  final uri = Uri.parse(
    'https://www.google.com/maps/dir/?api=1&destination=$lat,$lng&travelmode=driving',
  );
  await launchUrl(uri, mode: LaunchMode.externalApplication);
}

class _AssistantProductsBlock extends ConsumerStatefulWidget {
  final Map<String, dynamic> message;
  final bool showTitle;
  final bool compactSpacing;

  const _AssistantProductsBlock({
    required this.message,
    this.showTitle = true,
    this.compactSpacing = false,
  });

  @override
  ConsumerState<_AssistantProductsBlock> createState() =>
      _AssistantProductsBlockState();
}

class _AssistantProductsBlockState
    extends ConsumerState<_AssistantProductsBlock> {
  late List<Map<String, dynamic>> _products;
  late String _messageKey;

  @override
  void initState() {
    super.initState();
    _messageKey = _buildMessageKey(widget.message);
    _products = _extractProductsFromMessage(widget.message);
  }

  @override
  void didUpdateWidget(covariant _AssistantProductsBlock oldWidget) {
    super.didUpdateWidget(oldWidget);
    final nextKey = _buildMessageKey(widget.message);
    if (nextKey != _messageKey) {
      _messageKey = nextKey;
      _products = _extractProductsFromMessage(widget.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_products.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: EdgeInsets.only(top: widget.compactSpacing ? 6 : 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (widget.showTitle) ...[
            const Text(
              'Товары',
              style: TextStyle(
                fontSize: 12,
                color: GlameColors.textSecondary,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
          ],
          LayoutBuilder(
            builder: (context, constraints) {
              final crossAxisCount = constraints.maxWidth >= 420 ? 2 : 1;
              return GridView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: _products.take(6).length,
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: crossAxisCount,
                  crossAxisSpacing: 8,
                  mainAxisSpacing: 8,
                  childAspectRatio: crossAxisCount == 2 ? 0.72 : 1.65,
                ),
                itemBuilder: (context, index) {
                  final product = _products[index];
                  final productId = (product['id'] as String?)?.trim() ?? '';
                  final productAsync = productId.isEmpty
                      ? null
                      : ref.watch(productProvider(productId));
                  final effective =
                      productAsync?.maybeWhen(
                        data: (value) => value,
                        orElse: () => product,
                      ) ??
                      product;

                  final imageUrls = _extractImageUrls(effective['images']);
                  final stock = (effective['stock'] as num?)?.toDouble();
                  final inStockFlag = effective['in_stock'];
                  final isOutOfStock = inStockFlag is bool
                      ? !inStockFlag
                      : (stock != null && stock <= 0);
                  final price = _parsePrice(effective['price']);
                  final title = (effective['name'] as String?) ?? 'Украшение';

                  return _AssistantProductVisualCard(
                    productId: productId,
                    title: title,
                    price: price,
                    imageUrls: imageUrls,
                    isOutOfStock: isOutOfStock,
                    onOpen: productId.isEmpty
                        ? null
                        : () => context.push('/product/$productId'),
                    onAddToCart: () async {
                      if (productId.isEmpty) return;
                      try {
                        await ref
                            .read(customerCabinetApiProvider)
                            .addProductToCart(
                              productId: productId,
                              quantity: 1,
                            );
                        if (!context.mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Товар добавлен в корзину'),
                          ),
                        );
                      } catch (_) {
                        if (!context.mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              'Не удалось добавить товар в корзину',
                            ),
                          ),
                        );
                      }
                    },
                    onReplace: isOutOfStock
                        ? () => _replaceInPlace(
                            context: context,
                            index: index,
                            sourceProductId: productId,
                          )
                        : null,
                  );
                },
              );
            },
          ),
        ],
      ),
    );
  }

  Future<void> _replaceInPlace({
    required BuildContext context,
    required int index,
    required String sourceProductId,
  }) async {
    if (sourceProductId.isEmpty) return;
    try {
      final data = await ref
          .read(customerCabinetApiProvider)
          .getStylistReplacements(productId: sourceProductId, limit: 6);
      final productsRaw = data['products'];
      final candidates = productsRaw is List
          ? productsRaw
                .whereType<Map>()
                .map((x) => Map<String, dynamic>.from(x))
                .toList()
          : <Map<String, dynamic>>[];
      Map<String, dynamic>? replacement;
      for (final candidate in candidates) {
        final id = (candidate['id'] as String?) ?? '';
        final inStock =
            candidate['in_stock'] == true ||
            ((candidate['stock'] as num?)?.toDouble() ?? 0) > 0;
        if (id.isNotEmpty && id != sourceProductId && inStock) {
          replacement = candidate;
          break;
        }
      }
      if (replacement == null) {
        if (!context.mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Замены в наличии сейчас не найдено')),
        );
        return;
      }
      if (!mounted) return;
      setState(() {
        if (index >= 0 && index < _products.length) {
          _products[index] = replacement!;
        }
      });
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Товар заменен на аналог в наличии')),
      );
    } catch (_) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Не удалось подобрать замену')),
      );
    }
  }
}

String _buildMessageKey(Map<String, dynamic> message) {
  final id = (message['id'] as String?) ?? '';
  final createdAt = (message['created_at'] as String?) ?? '';
  return '$id|$createdAt';
}

List<Map<String, dynamic>> _extractProductsFromMessage(
  Map<String, dynamic> message,
) {
  final payloadRaw = message['payload'];
  final payload = payloadRaw is Map<String, dynamic>
      ? payloadRaw
      : payloadRaw is Map
      ? Map<String, dynamic>.from(payloadRaw)
      : const <String, dynamic>{};
  final productsRaw = payload['products'];
  var products = productsRaw is List
      ? productsRaw
            .whereType<Map>()
            .map((x) => Map<String, dynamic>.from(x))
            .toList()
      : <Map<String, dynamic>>[];
  if (products.isNotEmpty) return products;

  final looksRaw = payload['looks'];
  final looks = looksRaw is List
      ? looksRaw
            .whereType<Map>()
            .map((x) => Map<String, dynamic>.from(x))
            .toList()
      : const <Map<String, dynamic>>[];
  final merged = <Map<String, dynamic>>[];
  final seen = <String>{};
  for (final look in looks) {
    final lookProductsRaw = look['products'];
    final lookProducts = lookProductsRaw is List
        ? lookProductsRaw
              .whereType<Map>()
              .map((x) => Map<String, dynamic>.from(x))
              .toList()
        : const <Map<String, dynamic>>[];
    for (final product in lookProducts) {
      final id = (product['id'] as String?) ?? '';
      if (id.isEmpty || seen.contains(id)) continue;
      seen.add(id);
      merged.add(product);
    }
  }
  products = merged;
  return products;
}

List<String> _extractImageUrls(dynamic images) {
  if (images is! List || images.isEmpty) return const <String>[];
  final result = <String>[];
  for (final item in images) {
    if (item is String) {
      final resolved = resolveAssetUrl(item);
      if (resolved != null && resolved.isNotEmpty) result.add(resolved);
      continue;
    }
    if (item is Map) {
      final url = item['url'];
      if (url is String) {
        final resolved = resolveAssetUrl(url);
        if (resolved != null && resolved.isNotEmpty) result.add(resolved);
      }
    }
  }
  return result;
}

class _AssistantProductVisualCard extends StatefulWidget {
  final String productId;
  final String title;
  final int price;
  final List<String> imageUrls;
  final bool isOutOfStock;
  final VoidCallback? onOpen;
  final Future<void> Function() onAddToCart;
  final Future<void> Function()? onReplace;

  const _AssistantProductVisualCard({
    required this.productId,
    required this.title,
    required this.price,
    required this.imageUrls,
    required this.isOutOfStock,
    required this.onOpen,
    required this.onAddToCart,
    this.onReplace,
  });

  @override
  State<_AssistantProductVisualCard> createState() =>
      _AssistantProductVisualCardState();
}

class _AssistantProductVisualCardState
    extends State<_AssistantProductVisualCard> {
  late final PageController _controller;
  int _page = 0;

  @override
  void initState() {
    super.initState();
    _controller = PageController();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final hasImages = widget.imageUrls.isNotEmpty;
    final hasManyImages = widget.imageUrls.length > 1;

    return InkWell(
      onTap: widget.onOpen,
      child: Container(
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: GlameColors.surface2,
          border: Border.all(color: GlameColors.lightGray),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Stack(
                children: [
                  Positioned.fill(
                    child: Container(
                      decoration: BoxDecoration(
                        border: Border.all(color: GlameColors.lightGray),
                      ),
                      child: hasImages
                          ? PageView.builder(
                              controller: _controller,
                              itemCount: widget.imageUrls.length,
                              onPageChanged: (value) =>
                                  setState(() => _page = value),
                              itemBuilder: (context, index) =>
                                  CachedNetworkImage(
                                    imageUrl: widget.imageUrls[index],
                                    fit: BoxFit.cover,
                                  ),
                            )
                          : Container(color: GlameColors.surface),
                    ),
                  ),
                  if (hasManyImages)
                    Positioned(
                      right: 6,
                      top: 6,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: GlameColors.textPrimary.withValues(
                            alpha: 0.55,
                          ),
                          border: Border.all(
                            color: GlameColors.surface2.withValues(alpha: 0.24),
                          ),
                        ),
                        child: Text(
                          '${_page + 1}/${widget.imageUrls.length}',
                          style: const TextStyle(
                            fontSize: 10,
                            color: GlameColors.surface2,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
            if (hasManyImages) ...[
              const SizedBox(height: 6),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(
                  widget.imageUrls.length > 5 ? 5 : widget.imageUrls.length,
                  (index) {
                    final active = index == _page;
                    return Container(
                      margin: const EdgeInsets.symmetric(horizontal: 2),
                      width: active ? 12 : 6,
                      height: 6,
                      decoration: BoxDecoration(
                        color: active
                            ? GlameColors.textPrimary
                            : GlameColors.lightGray,
                      ),
                    );
                  },
                ),
              ),
            ],
            const SizedBox(height: 8),
            Text(
              widget.title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 4),
            Text(
              widget.price <= 0
                  ? 'Цена уточняется'
                  : formatRubFromKopeks(widget.price),
              style: const TextStyle(fontSize: 12),
            ),
            if (widget.isOutOfStock)
              const Text(
                'Нет в наличии',
                style: TextStyle(fontSize: 11, color: GlameColors.graphite),
              ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: SizedBox(
                    height: 30,
                    child: OutlinedButton(
                      onPressed: widget.onAddToCart,
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        minimumSize: const Size(0, 30),
                      ),
                      child: const Text('В корзину'),
                    ),
                  ),
                ),
                if (widget.onReplace != null) ...[
                  const SizedBox(width: 6),
                  SizedBox(
                    height: 30,
                    child: OutlinedButton(
                      onPressed: widget.onReplace,
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        minimumSize: const Size(0, 30),
                      ),
                      child: const Text('Замена'),
                    ),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

int _parsePrice(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value.trim()) ?? 0;
  return 0;
}

class _AssistantLooksBlock extends StatelessWidget {
  final Map<String, dynamic> message;

  const _AssistantLooksBlock({required this.message});

  @override
  Widget build(BuildContext context) {
    final payloadRaw = message['payload'];
    final payload = payloadRaw is Map<String, dynamic>
        ? payloadRaw
        : payloadRaw is Map
        ? Map<String, dynamic>.from(payloadRaw)
        : const <String, dynamic>{};
    final looksRaw = payload['looks'];
    final looks = looksRaw is List
        ? looksRaw
              .whereType<Map>()
              .map((x) => Map<String, dynamic>.from(x))
              .toList()
        : const <Map<String, dynamic>>[];
    if (looks.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Образы',
            style: TextStyle(
              fontSize: 12,
              color: GlameColors.textSecondary,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          ...looks.take(2).map((look) {
            final productsRaw = look['products'];
            final products = productsRaw is List
                ? productsRaw
                      .whereType<Map>()
                      .map((x) => Map<String, dynamic>.from(x))
                      .toList()
                : const <Map<String, dynamic>>[];
            final names = products
                .take(3)
                .map((x) => (x['name'] as String?)?.trim() ?? '')
                .where((x) => x.isNotEmpty)
                .toList();
            final imageUrl = resolveAssetUrl(look['image_url']);
            return InkWell(
              onTap: () => _openLookDialog(context, look, products),
              child: Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: GlameColors.surface2,
                  border: Border.all(color: GlameColors.lightGray),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(
                        color: GlameColors.surface,
                        border: Border.all(color: GlameColors.lightGray),
                      ),
                      child: imageUrl == null
                          ? Container(color: GlameColors.surface)
                          : CachedNetworkImage(
                              imageUrl: imageUrl,
                              fit: BoxFit.cover,
                            ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            ((look['name'] as String?) ?? 'Образ').trim(),
                            style: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          if (names.isNotEmpty) ...[
                            const SizedBox(height: 4),
                            Text(
                              names.join(' • '),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 12,
                                color: GlameColors.textSecondary,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            );
          }),
        ],
      ),
    );
  }
}

void _openLookDialog(
  BuildContext context,
  Map<String, dynamic> look,
  List<Map<String, dynamic>> products,
) {
  showDialog<void>(
    context: context,
    builder: (ctx) {
      final imageUrl = resolveAssetUrl(look['image_url']);
      return AlertDialog(
        title: Text(((look['name'] as String?) ?? 'Образ').trim()),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (imageUrl != null) ...[
                  ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: CachedNetworkImage(
                      imageUrl: imageUrl,
                      fit: BoxFit.cover,
                    ),
                  ),
                  const SizedBox(height: 10),
                ],
                if (products.isNotEmpty)
                  ...products.map((product) {
                    final name = (product['name'] as String?) ?? 'Товар';
                    final pid = (product['id'] as String?) ?? '';
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: InkWell(
                        onTap: pid.isEmpty
                            ? null
                            : () {
                                Navigator.of(ctx).pop();
                                context.push('/product/$pid');
                              },
                        child: Text('• $name'),
                      ),
                    );
                  }),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Закрыть'),
          ),
        ],
      );
    },
  );
}

class _Composer extends StatelessWidget {
  final TextEditingController controller;
  final XFile? pickedPhoto;
  final bool sending;
  final List<String> quickTags;
  final ValueChanged<String> onQuickTag;
  final VoidCallback onPick;
  final VoidCallback onClearPhoto;
  final VoidCallback onSend;

  const _Composer({
    required this.controller,
    required this.pickedPhoto,
    required this.sending,
    required this.quickTags,
    required this.onQuickTag,
    required this.onPick,
    required this.onClearPhoto,
    required this.onSend,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Container(
        padding: EdgeInsets.zero,
        decoration: const BoxDecoration(
          color: _chatSurface,
          border: Border(top: BorderSide(color: _chatBorder)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (quickTags.isNotEmpty)
              Container(
                height: 72,
                width: double.infinity,
                decoration: const BoxDecoration(
                  border: Border(bottom: BorderSide(color: _chatBorder)),
                ),
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 28,
                    vertical: 16,
                  ),
                  itemBuilder: (context, index) {
                    final tag = quickTags[index];
                    return InkWell(
                      onTap: sending ? null : () => onQuickTag(tag),
                      child: Container(
                        alignment: Alignment.center,
                        padding: const EdgeInsets.symmetric(horizontal: 22),
                        decoration: BoxDecoration(
                          border: Border.all(color: _chatBorder),
                        ),
                        child: Text(
                          tag.toUpperCase(),
                          style: const TextStyle(
                            fontSize: 12,
                            height: 1,
                            color: _chatText,
                            letterSpacing: 0.8,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    );
                  },
                  separatorBuilder: (_, _) => const SizedBox(width: 12),
                  itemCount: quickTags.length,
                ),
              ),
            if (pickedPhoto != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(28, 12, 28, 0),
                child: Row(
                  children: [
                    const Icon(
                      Icons.image_outlined,
                      size: 18,
                      color: _chatTextMuted,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        pickedPhoto!.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(color: _chatTextMuted),
                      ),
                    ),
                    IconButton(
                      onPressed: onClearPhoto,
                      icon: const Icon(Icons.close, size: 18, color: _chatText),
                    ),
                  ],
                ),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(28, 20, 28, 24),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  SizedBox(
                    width: 56,
                    height: 56,
                    child: OutlinedButton(
                      onPressed: sending ? null : onPick,
                      style: OutlinedButton.styleFrom(
                        foregroundColor: _chatText,
                        disabledForegroundColor: _chatTextDim,
                        padding: EdgeInsets.zero,
                        shape: const RoundedRectangleBorder(),
                        side: const BorderSide(color: _chatBorder),
                      ),
                      child: const Icon(Icons.add, size: 30),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Focus(
                      onKeyEvent: (node, event) {
                        final isEnter =
                            event.logicalKey == LogicalKeyboardKey.enter ||
                            event.logicalKey == LogicalKeyboardKey.numpadEnter;
                        if (event is KeyDownEvent &&
                            isEnter &&
                            !HardwareKeyboard.instance.isShiftPressed) {
                          if (!sending) onSend();
                          return KeyEventResult.handled;
                        }
                        return KeyEventResult.ignored;
                      },
                      child: TextField(
                        controller: controller,
                        minLines: 1,
                        maxLines: 4,
                        style: const TextStyle(color: _chatText, fontSize: 16),
                        cursorColor: _chatText,
                        textInputAction: TextInputAction.send,
                        onSubmitted: (_) {
                          if (!sending) onSend();
                        },
                        decoration: const InputDecoration(
                          hintText: 'Написать сообщение...',
                          hintStyle: TextStyle(color: _chatTextDim),
                          filled: true,
                          fillColor: _chatSurfaceLow,
                          contentPadding: EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 16,
                          ),
                          enabledBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.zero,
                            borderSide: BorderSide(color: _chatBorder),
                          ),
                          focusedBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.zero,
                            borderSide: BorderSide(color: _chatText),
                          ),
                          disabledBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.zero,
                            borderSide: BorderSide(color: _chatBorder),
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  SizedBox(
                    width: 56,
                    height: 56,
                    child: FilledButton(
                      onPressed: sending ? null : onSend,
                      style: FilledButton.styleFrom(
                        backgroundColor: _chatText,
                        foregroundColor: _chatSurface,
                        disabledBackgroundColor: _chatSurfaceHigh,
                        disabledForegroundColor: _chatTextDim,
                        padding: EdgeInsets.zero,
                        shape: const RoundedRectangleBorder(),
                      ),
                      child: sending
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: _chatText,
                              ),
                            )
                          : const Icon(Icons.send, size: 24),
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
