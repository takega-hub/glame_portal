import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/formatters/rub.dart';
import '../../core/network/asset_url.dart';
import '../../core/theme/glame_theme.dart';
import '../auth/auth_controller.dart';
import '../cart/cart_controller.dart';
import '../customer/customer_cabinet_providers.dart';
import '../customer/stylist_entry.dart';
import 'looks_providers.dart';

enum _LooksPresentation { editorial, feed, grid }

enum _LooksProfileTab { grid, feed, saved }

const _looksPresentationPrefsKey = 'looks.presentation.mode';
const _looksFollowingPrefsKey = 'looks.grid.following';

ButtonStyle _looksPrimaryButtonStyle({double height = 48, double radius = 16}) {
  return FilledButton.styleFrom(
    backgroundColor: GlameColors.textPrimary,
    foregroundColor: GlameColors.surface2,
    disabledBackgroundColor: GlameColors.lightGray,
    disabledForegroundColor: GlameColors.textSecondary,
    minimumSize: Size.fromHeight(height),
    elevation: 0,
    textStyle: const TextStyle(
      fontSize: 15,
      fontWeight: FontWeight.w500,
      color: GlameColors.surface2,
    ),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius)),
  );
}

ButtonStyle _looksSecondaryButtonStyle({
  double height = 48,
  double radius = 16,
}) {
  return OutlinedButton.styleFrom(
    foregroundColor: GlameColors.textPrimary,
    backgroundColor: GlameColors.surface2,
    side: const BorderSide(color: GlameColors.lightGray),
    minimumSize: Size.fromHeight(height),
    textStyle: const TextStyle(
      fontSize: 15,
      fontWeight: FontWeight.w500,
      color: GlameColors.textPrimary,
    ),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius)),
  );
}

class LooksScreen extends ConsumerStatefulWidget {
  final String? initialFilter;

  const LooksScreen({super.key, this.initialFilter});

  @override
  ConsumerState<LooksScreen> createState() => _LooksScreenState();
}

class _LooksScreenState extends ConsumerState<LooksScreen> {
  String _selectedFilter = 'Все';
  _LooksPresentation _presentation = _LooksPresentation.editorial;
  bool _isFollowing = false;

  @override
  void initState() {
    super.initState();
    final initial = (widget.initialFilter ?? '').trim();
    if (initial.isNotEmpty) {
      _selectedFilter = initial;
    }
    _restorePresentation();
    _restoreFollowing();
  }

  @override
  void didUpdateWidget(covariant LooksScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.initialFilter == widget.initialFilter) return;
    final next = (widget.initialFilter ?? '').trim();
    setState(() {
      _selectedFilter = next.isEmpty ? 'Все' : next;
    });
  }

  @override
  Widget build(BuildContext context) {
    final feed = ref.watch(looksFeedProvider);

    return Scaffold(
      backgroundColor: GlameColors.surface2,
      body: SafeArea(
        top: false,
        child: RefreshIndicator(
          color: GlameColors.textPrimary,
          onRefresh: () async {
            ref.invalidate(looksFeedProvider);
            await ref.read(looksFeedProvider.future);
          },
          child: feed.when(
            loading: () => const _LooksLoadingSkeleton(),
            error: (_, _) => ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 40),
              children: const [
                _LooksHeader(),
                SizedBox(height: 20),
                Text(
                  'Не удалось загрузить раздел образов.',
                  style: TextStyle(color: GlameColors.textSecondary),
                ),
              ],
            ),
            data: (items) {
              final posts = items
                  .whereType<Map>()
                  .map((x) => Map<String, dynamic>.from(x))
                  .toList(growable: false);
              final filters = _lookFilters(posts);
              final activeFilter = filters.contains(_selectedFilter)
                  ? _selectedFilter
                  : 'Все';
              final filteredPosts = activeFilter == 'Все'
                  ? posts
                  : posts
                        .where((post) => _matchesFilter(post, activeFilter))
                        .toList(growable: false);

              return LayoutBuilder(
                builder: (context, constraints) {
                  final isWide = constraints.maxWidth >= 860;
                  final horizontalPadding = isWide ? 28.0 : 16.0;

                  if (_presentation == _LooksPresentation.feed) {
                    return _LooksFeedScroll(
                      countLabel: _looksCountLabel(filteredPosts.length),
                      averagePriceLabel: _averageLookPriceLabel(filteredPosts),
                      presentation: _presentation,
                      onPresentationChanged: _setPresentation,
                      filters: filters,
                      activeFilter: activeFilter,
                      onFilterSelected: (label) {
                        setState(() => _selectedFilter = label);
                      },
                      posts: filteredPosts,
                      maxWidth: constraints.maxWidth,
                      horizontalPadding: horizontalPadding,
                      onOpenProfile: _openLooksProfile,
                    );
                  }

                  return ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: EdgeInsets.fromLTRB(
                      horizontalPadding,
                      10,
                      horizontalPadding,
                      144,
                    ),
                    children: [
                      _LooksHeader(
                        countLabel: _looksCountLabel(filteredPosts.length),
                        averagePriceLabel: _averageLookPriceLabel(
                          filteredPosts,
                        ),
                        presentation: _presentation,
                        onPresentationChanged: (value) {
                          _setPresentation(value);
                        },
                      ),
                      if (filters.length > 1) ...[
                        const SizedBox(height: 20),
                        SizedBox(
                          height: 42,
                          child: ListView.separated(
                            scrollDirection: Axis.horizontal,
                            itemCount: filters.length,
                            separatorBuilder: (_, _) =>
                                const SizedBox(width: 10),
                            itemBuilder: (context, index) {
                              final label = filters[index];
                              final selected = label == activeFilter;
                              return ChoiceChip(
                                selected: selected,
                                onSelected: (_) {
                                  setState(() => _selectedFilter = label);
                                },
                                showCheckmark: false,
                                label: Text(label),
                                labelStyle: TextStyle(
                                  fontSize: 13,
                                  color: selected
                                      ? GlameColors.surface2
                                      : GlameColors.textSecondary,
                                ),
                                backgroundColor: GlameColors.surface2,
                                selectedColor: GlameColors.textPrimary,
                                side: BorderSide(
                                  color: selected
                                      ? GlameColors.textPrimary
                                      : GlameColors.lightGray,
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(999),
                                ),
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 12,
                                ),
                              );
                            },
                          ),
                        ),
                      ],
                      const SizedBox(height: 18),
                      AnimatedSwitcher(
                        duration: const Duration(milliseconds: 260),
                        switchInCurve: Curves.easeOutCubic,
                        switchOutCurve: Curves.easeInCubic,
                        child: _LooksPresentationBody(
                          key: ValueKey(
                            '${_presentation.name}:$activeFilter:${filteredPosts.length}',
                          ),
                          presentation: _presentation,
                          posts: filteredPosts,
                          maxWidth: constraints.maxWidth,
                          activeFilter: activeFilter,
                          isFollowing: _isFollowing,
                          onHighlightTap: _handleHighlightTap,
                          onToggleFollowing: _toggleFollowing,
                          onMessageTap: _openStylistChat,
                          onInviteTap: _inviteToLooksProfile,
                          onOpenProfile: _openLooksProfile,
                        ),
                      ),
                    ],
                  );
                },
              );
            },
          ),
        ),
      ),
    );
  }

  Future<void> _restorePresentation() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString(_looksPresentationPrefsKey);
    final parsed = _parseLooksPresentation(stored);
    if (!mounted || parsed == null || parsed == _presentation) return;
    setState(() => _presentation = parsed);
  }

  Future<void> _restoreFollowing() async {
    final prefs = await SharedPreferences.getInstance();
    final following = prefs.getBool(_looksFollowingPrefsKey) ?? false;
    if (!mounted || following == _isFollowing) return;
    setState(() => _isFollowing = following);
  }

  Future<void> _setPresentation(_LooksPresentation value) async {
    if (value == _presentation) return;
    setState(() => _presentation = value);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_looksPresentationPrefsKey, value.name);
  }

  void _handleHighlightTap(String label) {
    setState(() {
      _selectedFilter = label;
    });
  }

  Future<void> _toggleFollowing() async {
    final next = !_isFollowing;
    setState(() => _isFollowing = next);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_looksFollowingPrefsKey, next);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          next
              ? 'Вы подписались на подборки GLAME'
              : 'Подписка на подборки GLAME отключена',
        ),
      ),
    );
  }

  void _openStylistChat() {
    context.push(
      buildStylistChatRoute(source: 'looks_feed', scenario: 'live_stylist'),
    );
  }

  Future<void> _inviteToLooksProfile() async {
    await Clipboard.setData(
      const ClipboardData(text: 'https://app.glamejewelry.ru/#/home?tab=5'),
    );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Ссылка на профиль образов скопирована')),
    );
  }

  void _openLooksProfile() {
    context.push(
      _looksProfileUrl(
        filter: _selectedFilter,
        tab: _presentation == _LooksPresentation.feed
            ? _LooksProfileTab.feed
            : _LooksProfileTab.grid,
      ),
    );
  }
}

class _LooksPresentationBody extends StatelessWidget {
  final _LooksPresentation presentation;
  final List<Map<String, dynamic>> posts;
  final double maxWidth;
  final String activeFilter;
  final bool isFollowing;
  final ValueChanged<String> onHighlightTap;
  final Future<void> Function() onToggleFollowing;
  final VoidCallback onMessageTap;
  final Future<void> Function() onInviteTap;
  final VoidCallback onOpenProfile;

  const _LooksPresentationBody({
    super.key,
    required this.presentation,
    required this.posts,
    required this.maxWidth,
    required this.activeFilter,
    required this.isFollowing,
    required this.onHighlightTap,
    required this.onToggleFollowing,
    required this.onMessageTap,
    required this.onInviteTap,
    required this.onOpenProfile,
  });

  @override
  Widget build(BuildContext context) {
    if (posts.isEmpty) {
      return const Padding(
        padding: EdgeInsets.only(top: 18),
        child: Text(
          'Для этого фильтра пока нет опубликованных образов.',
          style: TextStyle(color: GlameColors.textSecondary),
        ),
      );
    }

    if (presentation == _LooksPresentation.editorial) {
      return Column(
        children: posts
            .map(
              (post) => Padding(
                padding: const EdgeInsets.only(bottom: 20),
                child: _LookEditorialCard(post: post),
              ),
            )
            .toList(growable: false),
      );
    }

    return _LookGrid(
      posts: posts,
      maxWidth: maxWidth,
      activeFilter: activeFilter,
      isFollowing: isFollowing,
      onHighlightTap: onHighlightTap,
      onToggleFollowing: onToggleFollowing,
      onMessageTap: onMessageTap,
      onInviteTap: onInviteTap,
      onOpenProfile: onOpenProfile,
    );
  }
}

class LooksProfileScreen extends ConsumerStatefulWidget {
  final String? initialFilter;
  final String? initialTab;

  const LooksProfileScreen({super.key, this.initialFilter, this.initialTab});

  @override
  ConsumerState<LooksProfileScreen> createState() => _LooksProfileScreenState();
}

class _LooksProfileScreenState extends ConsumerState<LooksProfileScreen> {
  String _selectedFilter = 'Все';
  bool _isFollowing = false;
  _LooksProfileTab _selectedTab = _LooksProfileTab.grid;

  @override
  void initState() {
    super.initState();
    final initial = (widget.initialFilter ?? '').trim();
    if (initial.isNotEmpty) {
      _selectedFilter = initial;
    }
    final tab = _parseLooksProfileTab(widget.initialTab);
    if (tab != null) {
      _selectedTab = tab;
    }
    _restoreFollowing();
  }

  Future<void> _restoreFollowing() async {
    final prefs = await SharedPreferences.getInstance();
    final following = prefs.getBool(_looksFollowingPrefsKey) ?? false;
    if (!mounted || following == _isFollowing) return;
    setState(() => _isFollowing = following);
  }

  Future<void> _toggleFollowing() async {
    final next = !_isFollowing;
    setState(() => _isFollowing = next);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_looksFollowingPrefsKey, next);
  }

  void _openStylistChat() {
    context.push(
      buildStylistChatRoute(source: 'looks_profile', scenario: 'live_stylist'),
    );
  }

  void _syncProfileRoute() {
    context.replace(
      _looksProfileUrl(filter: _selectedFilter, tab: _selectedTab),
    );
  }

  Future<void> _inviteToLooksProfile() async {
    await Clipboard.setData(
      ClipboardData(
        text: _looksProfileUrl(filter: _selectedFilter, tab: _selectedTab),
      ),
    );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Ссылка на профиль образов скопирована')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final feed = ref.watch(looksFeedProvider);

    return Scaffold(
      backgroundColor: GlameColors.surface2,
      appBar: AppBar(
        backgroundColor: GlameColors.surface2,
        elevation: 0,
        titleSpacing: 8,
        title: Row(
          children: [
            Container(
              width: 28,
              height: 28,
              decoration: const BoxDecoration(
                color: GlameColors.textPrimary,
                shape: BoxShape.circle,
              ),
              alignment: Alignment.center,
              child: const Text(
                'GL',
                style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                  color: GlameColors.surface2,
                ),
              ),
            ),
            const SizedBox(width: 10),
            const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'glame_official',
                  style: TextStyle(
                    fontSize: 16,
                    color: GlameColors.textPrimary,
                  ),
                ),
                Text(
                  'Looks profile',
                  style: TextStyle(
                    fontSize: 11,
                    color: GlameColors.textSecondary,
                  ),
                ),
              ],
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Скопировать deeplink',
            onPressed: _inviteToLooksProfile,
            icon: const Icon(
              Icons.ios_share_outlined,
              color: GlameColors.textPrimary,
            ),
          ),
        ],
        titleTextStyle: const TextStyle(
          fontSize: 16,
          color: GlameColors.textPrimary,
        ),
      ),
      body: RefreshIndicator(
        color: GlameColors.textPrimary,
        onRefresh: () async {
          ref.invalidate(looksFeedProvider);
          await ref.read(looksFeedProvider.future);
        },
        child: feed.when(
          loading: () => const _LooksLoadingSkeleton(),
          error: (_, _) => const Center(
            child: Text(
              'Не удалось загрузить профиль образов.',
              style: TextStyle(color: GlameColors.textSecondary),
            ),
          ),
          data: (items) {
            final allPosts = items
                .whereType<Map>()
                .map((x) => Map<String, dynamic>.from(x))
                .toList(growable: false);
            final filters = _lookFilters(allPosts);
            final activeFilter = filters.contains(_selectedFilter)
                ? _selectedFilter
                : 'Все';
            final filteredPosts = activeFilter == 'Все'
                ? allPosts
                : allPosts
                      .where((post) => _matchesFilter(post, activeFilter))
                      .toList(growable: false);
            final savedPosts = allPosts
                .where((post) => post['favorited_by_me'] == true)
                .toList(growable: false);

            return LayoutBuilder(
              builder: (context, constraints) {
                final horizontalPadding = constraints.maxWidth >= 860
                    ? 28.0
                    : 16.0;
                return CustomScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  slivers: [
                    SliverPadding(
                      padding: EdgeInsets.fromLTRB(
                        horizontalPadding,
                        8,
                        horizontalPadding,
                        0,
                      ),
                      sliver: SliverToBoxAdapter(
                        child: _LookGridProfileHeader(
                          posts: allPosts,
                          isWide: constraints.maxWidth >= 860,
                          isFollowing: _isFollowing,
                          onToggleFollowing: _toggleFollowing,
                          onMessageTap: _openStylistChat,
                          onInviteTap: _inviteToLooksProfile,
                          onOpenProfile: () {},
                        ),
                      ),
                    ),
                    SliverPadding(
                      padding: EdgeInsets.fromLTRB(
                        horizontalPadding,
                        18,
                        horizontalPadding,
                        0,
                      ),
                      sliver: SliverToBoxAdapter(
                        child: _LookGridHighlights(
                          posts: allPosts,
                          activeFilter: activeFilter,
                          onTap: (label) {
                            setState(() => _selectedFilter = label);
                            _syncProfileRoute();
                          },
                        ),
                      ),
                    ),
                    SliverPadding(
                      padding: EdgeInsets.fromLTRB(
                        horizontalPadding,
                        18,
                        horizontalPadding,
                        0,
                      ),
                      sliver: SliverPersistentHeader(
                        pinned: true,
                        delegate: _PinnedBoxHeaderDelegate(
                          height: 102,
                          child: _LooksProfilePinnedHeader(
                            activeFilter: activeFilter,
                            selectedTab: _selectedTab,
                            counts: {
                              _LooksProfileTab.grid: filteredPosts.length,
                              _LooksProfileTab.feed: filteredPosts.length,
                              _LooksProfileTab.saved: savedPosts.length,
                            },
                            onTabChanged: (tab) {
                              setState(() => _selectedTab = tab);
                              _syncProfileRoute();
                            },
                          ),
                        ),
                      ),
                    ),
                    SliverPadding(
                      padding: EdgeInsets.fromLTRB(
                        horizontalPadding,
                        12,
                        horizontalPadding,
                        144,
                      ),
                      sliver: _buildProfileContentSliver(
                        posts: filteredPosts,
                        allPosts: allPosts,
                        maxWidth: constraints.maxWidth,
                      ),
                    ),
                  ],
                );
              },
            );
          },
        ),
      ),
    );
  }

  Widget _buildProfileContentSliver({
    required List<Map<String, dynamic>> posts,
    required List<Map<String, dynamic>> allPosts,
    required double maxWidth,
  }) {
    switch (_selectedTab) {
      case _LooksProfileTab.grid:
        final columns = _looksGridColumnCount(maxWidth);
        final gap = maxWidth >= 860 ? 14.0 : 8.0;
        return posts.isEmpty
            ? const SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.only(top: 18),
                  child: Text(
                    'Для этого фильтра пока нет опубликованных образов.',
                    style: TextStyle(color: GlameColors.textSecondary),
                  ),
                ),
              )
            : SliverGrid(
                delegate: SliverChildBuilderDelegate(
                  (context, index) => _LookGridTile(post: posts[index]),
                  childCount: posts.length,
                ),
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: columns,
                  mainAxisSpacing: gap,
                  crossAxisSpacing: gap,
                  childAspectRatio: 1,
                ),
              );
      case _LooksProfileTab.feed:
        final isWide = maxWidth >= 860;
        return posts.isEmpty
            ? const SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.only(top: 18),
                  child: Text(
                    'Для этого фильтра пока нет опубликованных образов.',
                    style: TextStyle(color: GlameColors.textSecondary),
                  ),
                ),
              )
            : SliverList.separated(
                itemCount: posts.length,
                separatorBuilder: (_, _) => const SizedBox(height: 20),
                itemBuilder: (context, index) => Align(
                  alignment: Alignment.topLeft,
                  child: ConstrainedBox(
                    constraints: BoxConstraints(
                      maxWidth: isWide ? 620 : double.infinity,
                    ),
                    child: _LookInstagramCard(post: posts[index]),
                  ),
                ),
              );
      case _LooksProfileTab.saved:
        final savedPosts = allPosts
            .where((post) => post['favorited_by_me'] == true)
            .toList(growable: false);
        if (savedPosts.isEmpty) {
          return const SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.only(top: 18),
              child: Text(
                'Сохранённые образы появятся после добавления в избранное.',
                style: TextStyle(color: GlameColors.textSecondary),
              ),
            ),
          );
        }
        final columns = _looksGridColumnCount(maxWidth);
        final gap = maxWidth >= 860 ? 14.0 : 8.0;
        return SliverGrid(
          delegate: SliverChildBuilderDelegate(
            (context, index) => _LookGridTile(post: savedPosts[index]),
            childCount: savedPosts.length,
          ),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            mainAxisSpacing: gap,
            crossAxisSpacing: gap,
            childAspectRatio: 1,
          ),
        );
    }
  }
}

class _LooksFeedScroll extends StatelessWidget {
  final String countLabel;
  final String averagePriceLabel;
  final _LooksPresentation presentation;
  final ValueChanged<_LooksPresentation> onPresentationChanged;
  final List<String> filters;
  final String activeFilter;
  final ValueChanged<String> onFilterSelected;
  final List<Map<String, dynamic>> posts;
  final double maxWidth;
  final double horizontalPadding;
  final VoidCallback onOpenProfile;

  const _LooksFeedScroll({
    required this.countLabel,
    required this.averagePriceLabel,
    required this.presentation,
    required this.onPresentationChanged,
    required this.filters,
    required this.activeFilter,
    required this.onFilterSelected,
    required this.posts,
    required this.maxWidth,
    required this.horizontalPadding,
    required this.onOpenProfile,
  });

  @override
  Widget build(BuildContext context) {
    final isWide = maxWidth >= 860;
    return CustomScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: [
        SliverPadding(
          padding: EdgeInsets.fromLTRB(
            horizontalPadding,
            10,
            horizontalPadding,
            0,
          ),
          sliver: SliverToBoxAdapter(
            child: _LooksHeader(
              countLabel: countLabel,
              averagePriceLabel: averagePriceLabel,
              presentation: presentation,
              onPresentationChanged: onPresentationChanged,
            ),
          ),
        ),
        if (filters.length > 1)
          SliverPadding(
            padding: EdgeInsets.fromLTRB(
              horizontalPadding,
              20,
              horizontalPadding,
              0,
            ),
            sliver: SliverToBoxAdapter(
              child: SizedBox(
                height: 42,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: filters.length,
                  separatorBuilder: (_, _) => const SizedBox(width: 10),
                  itemBuilder: (context, index) {
                    final label = filters[index];
                    final selected = label == activeFilter;
                    return ChoiceChip(
                      selected: selected,
                      onSelected: (_) => onFilterSelected(label),
                      showCheckmark: false,
                      label: Text(label),
                      labelStyle: TextStyle(
                        fontSize: 13,
                        color: selected
                            ? GlameColors.surface2
                            : GlameColors.textSecondary,
                      ),
                      backgroundColor: GlameColors.surface2,
                      selectedColor: GlameColors.textPrimary,
                      side: BorderSide(
                        color: selected
                            ? GlameColors.textPrimary
                            : GlameColors.lightGray,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(999),
                      ),
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                    );
                  },
                ),
              ),
            ),
          ),
        SliverPadding(
          padding: EdgeInsets.fromLTRB(
            horizontalPadding,
            18,
            horizontalPadding,
            0,
          ),
          sliver: SliverPersistentHeader(
            pinned: true,
            delegate: _PinnedBoxHeaderDelegate(
              height: 60,
              child: _LookFeedHeaderStrip(onTap: onOpenProfile),
            ),
          ),
        ),
        SliverPadding(
          padding: EdgeInsets.fromLTRB(
            horizontalPadding,
            16,
            horizontalPadding,
            144,
          ),
          sliver: posts.isEmpty
              ? const SliverToBoxAdapter(
                  child: Padding(
                    padding: EdgeInsets.only(top: 18),
                    child: Text(
                      'Для этого фильтра пока нет опубликованных образов.',
                      style: TextStyle(color: GlameColors.textSecondary),
                    ),
                  ),
                )
              : SliverList.separated(
                  itemCount: posts.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 20),
                  itemBuilder: (context, index) => Align(
                    alignment: Alignment.topLeft,
                    child: ConstrainedBox(
                      constraints: BoxConstraints(
                        maxWidth: isWide ? 620 : double.infinity,
                      ),
                      child: _LookInstagramCard(post: posts[index]),
                    ),
                  ),
                ),
        ),
      ],
    );
  }
}

class _PinnedBoxHeaderDelegate extends SliverPersistentHeaderDelegate {
  final double height;
  final Widget child;

  const _PinnedBoxHeaderDelegate({required this.height, required this.child});

  @override
  double get minExtent => height;

  @override
  double get maxExtent => height;

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    return ColoredBox(
      color: GlameColors.surface2,
      child: Padding(padding: const EdgeInsets.only(bottom: 8), child: child),
    );
  }

  @override
  bool shouldRebuild(covariant _PinnedBoxHeaderDelegate oldDelegate) {
    return oldDelegate.height != height || oldDelegate.child != child;
  }
}

class _LooksHeader extends StatelessWidget {
  final String? countLabel;
  final String? averagePriceLabel;
  final _LooksPresentation? presentation;
  final ValueChanged<_LooksPresentation>? onPresentationChanged;

  const _LooksHeader({
    this.countLabel,
    this.averagePriceLabel,
    this.presentation,
    this.onPresentationChanged,
  });

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    final titleSize = width >= 860 ? 62.0 : 52.0;
    final summary = [
      if (countLabel != null && countLabel!.isNotEmpty) countLabel!,
      if (averagePriceLabel != null && averagePriceLabel!.isNotEmpty)
        averagePriceLabel!,
    ].join('  •  ');

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Образы',
          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
            fontSize: titleSize,
            height: 0.92,
            fontWeight: FontWeight.w400,
          ),
        ),
        const SizedBox(height: 10),
        const Text(
          'Подборки под Ваш стиль',
          style: TextStyle(
            fontSize: 17,
            height: 1.3,
            color: GlameColors.textSecondary,
          ),
        ),
        const SizedBox(height: 18),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            if (summary.isNotEmpty)
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 9,
                ),
                decoration: BoxDecoration(
                  color: GlameColors.surface,
                  border: Border.all(color: GlameColors.lightGray),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  summary,
                  style: const TextStyle(
                    fontSize: 12,
                    color: GlameColors.textSecondary,
                  ),
                ),
              ),
            if (presentation != null && onPresentationChanged != null)
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 360),
                child: SegmentedButton<_LooksPresentation>(
                  showSelectedIcon: false,
                  segments: const [
                    ButtonSegment(
                      value: _LooksPresentation.editorial,
                      label: Text('Каталог'),
                      icon: Icon(Icons.dashboard_outlined, size: 18),
                    ),
                    ButtonSegment(
                      value: _LooksPresentation.feed,
                      label: Text('Лента'),
                      icon: Icon(Icons.view_agenda_outlined, size: 18),
                    ),
                    ButtonSegment(
                      value: _LooksPresentation.grid,
                      label: Text('Сетка'),
                      icon: Icon(Icons.grid_on_outlined, size: 18),
                    ),
                  ],
                  selected: {presentation!},
                  onSelectionChanged: (value) {
                    final next = value.firstOrNull;
                    if (next != null) onPresentationChanged!(next);
                  },
                  style: ButtonStyle(
                    side: WidgetStateProperty.all(
                      const BorderSide(color: GlameColors.lightGray),
                    ),
                    shape: WidgetStateProperty.all(
                      RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(999),
                      ),
                    ),
                    foregroundColor: WidgetStateProperty.resolveWith((states) {
                      return states.contains(WidgetState.selected)
                          ? GlameColors.surface2
                          : GlameColors.textSecondary;
                    }),
                    backgroundColor: WidgetStateProperty.resolveWith((states) {
                      return states.contains(WidgetState.selected)
                          ? GlameColors.textPrimary
                          : GlameColors.surface2;
                    }),
                    textStyle: WidgetStateProperty.all(
                      const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }
}

class _LooksLoadingSkeleton extends StatelessWidget {
  const _LooksLoadingSkeleton();

  @override
  Widget build(BuildContext context) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 120),
      children: const [
        _LooksHeaderSkeleton(),
        SizedBox(height: 20),
        _LooksChipsSkeleton(),
        SizedBox(height: 18),
        _LooksCardSkeleton(),
        SizedBox(height: 20),
        _LooksCardSkeleton(),
      ],
    );
  }
}

class _LooksHeaderSkeleton extends StatelessWidget {
  const _LooksHeaderSkeleton();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SkeletonBox(width: 180, height: 52),
        SizedBox(height: 12),
        _SkeletonBox(width: 220, height: 18),
        SizedBox(height: 18),
        Row(children: [_SkeletonBox(width: 180, height: 34, radius: 999)]),
      ],
    );
  }
}

class _LooksChipsSkeleton extends StatelessWidget {
  const _LooksChipsSkeleton();

  @override
  Widget build(BuildContext context) {
    return const SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          _SkeletonBox(width: 64, height: 38, radius: 999),
          SizedBox(width: 10),
          _SkeletonBox(width: 124, height: 38, radius: 999),
          SizedBox(width: 10),
          _SkeletonBox(width: 96, height: 38, radius: 999),
          SizedBox(width: 10),
          _SkeletonBox(width: 108, height: 38, radius: 999),
        ],
      ),
    );
  }
}

class _LooksCardSkeleton extends StatelessWidget {
  const _LooksCardSkeleton();

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    final compact = width < 560;

    return Container(
      decoration: BoxDecoration(
        color: GlameColors.surface2,
        border: Border.all(color: GlameColors.lightGray),
        borderRadius: BorderRadius.circular(26),
      ),
      padding: const EdgeInsets.all(14),
      child: compact
          ? const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                AspectRatio(aspectRatio: 1.45, child: _SkeletonBox()),
                SizedBox(height: 14),
                _SkeletonBox(width: 160, height: 22),
                SizedBox(height: 10),
                _SkeletonBox(width: 210, height: 14),
                SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(child: _SkeletonBox(height: 92, radius: 14)),
                    SizedBox(width: 10),
                    Expanded(child: _SkeletonBox(height: 92, radius: 14)),
                    SizedBox(width: 10),
                    Expanded(child: _SkeletonBox(height: 92, radius: 14)),
                  ],
                ),
                SizedBox(height: 14),
                _SkeletonBox(height: 48, radius: 16),
              ],
            )
          : const Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  flex: 4,
                  child: AspectRatio(aspectRatio: 0.82, child: _SkeletonBox()),
                ),
                SizedBox(width: 14),
                Expanded(
                  flex: 6,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _SkeletonBox(width: 220, height: 24),
                      SizedBox(height: 10),
                      _SkeletonBox(width: 190, height: 14),
                      SizedBox(height: 18),
                      Row(
                        children: [
                          Expanded(child: _SkeletonBox(height: 92, radius: 14)),
                          SizedBox(width: 10),
                          Expanded(child: _SkeletonBox(height: 92, radius: 14)),
                          SizedBox(width: 10),
                          Expanded(child: _SkeletonBox(height: 92, radius: 14)),
                        ],
                      ),
                      SizedBox(height: 16),
                      _SkeletonBox(height: 48, radius: 16),
                    ],
                  ),
                ),
              ],
            ),
    );
  }
}

class _SkeletonBox extends StatefulWidget {
  final double? width;
  final double height;
  final double radius;

  const _SkeletonBox({this.width, this.height = 16, this.radius = 18});

  @override
  State<_SkeletonBox> createState() => _SkeletonBoxState();
}

class _SkeletonBoxState extends State<_SkeletonBox>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final shimmerX = (_controller.value * 2) - 1;
        return ShaderMask(
          shaderCallback: (bounds) {
            return LinearGradient(
              begin: Alignment(-1.4 + shimmerX, -0.2),
              end: Alignment(-0.4 + shimmerX, 0.2),
              colors: [
                GlameColors.lightGray.withValues(alpha: 0.66),
                GlameColors.surface.withValues(alpha: 0.95),
                GlameColors.lightGray.withValues(alpha: 0.66),
              ],
              stops: const [0.15, 0.5, 0.85],
            ).createShader(bounds);
          },
          blendMode: BlendMode.srcATop,
          child: child,
        );
      },
      child: Container(
        width: widget.width,
        height: widget.height,
        decoration: BoxDecoration(
          color: GlameColors.lightGray.withValues(alpha: 0.78),
          borderRadius: BorderRadius.circular(widget.radius),
        ),
      ),
    );
  }
}

class _LookEditorialCard extends ConsumerStatefulWidget {
  final Map<String, dynamic> post;

  const _LookEditorialCard({required this.post});

  @override
  ConsumerState<_LookEditorialCard> createState() => _LookEditorialCardState();
}

class _LookEditorialCardState extends ConsumerState<_LookEditorialCard> {
  bool _busy = false;
  late bool _favorited;
  late int _favoriteCount;

  @override
  void initState() {
    super.initState();
    _favorited = widget.post['favorited_by_me'] == true;
    _favoriteCount = _asInt(widget.post['favorite_count']);
  }

  @override
  Widget build(BuildContext context) {
    final products = _products(widget.post);
    final title = _asString(widget.post['name']).isEmpty
        ? 'Образ GLAME'
        : _asString(widget.post['name']);
    final description = _lookDescription(widget.post);
    final tag = _primaryLookTag(widget.post);
    final totalPrice = _lookTotalKopeks(widget.post);
    final image = _lookCover(widget.post);

    return InkWell(
      onTap: _openDetails,
      borderRadius: BorderRadius.circular(26),
      child: Container(
        decoration: BoxDecoration(
          color: GlameColors.surface2,
          border: Border.all(color: GlameColors.lightGray),
          borderRadius: BorderRadius.circular(26),
          boxShadow: [
            BoxShadow(
              color: GlameColors.textPrimary.withValues(alpha: 0.04),
              blurRadius: 18,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(26),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final isCompact = constraints.maxWidth < 560;
              final imageFlex = isCompact ? 42 : 38;
              final contentFlex = isCompact ? 58 : 62;
              final cardHeight = isCompact ? 314.0 : 330.0;

              return SizedBox(
                height: cardHeight,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(
                      flex: imageFlex,
                      child: _LookCoverTile(
                        imageUrl: image,
                        tag: tag,
                        favorited: _favorited,
                        busy: _busy,
                        onToggleFavorite: _toggleFavorite,
                      ),
                    ),
                    Expanded(
                      flex: contentFlex,
                      child: Padding(
                        padding: EdgeInsets.fromLTRB(
                          isCompact ? 14 : 18,
                          isCompact ? 14 : 18,
                          isCompact ? 14 : 18,
                          isCompact ? 14 : 18,
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        title,
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                        style: TextStyle(
                                          fontSize: isCompact ? 18 : 22,
                                          fontWeight: FontWeight.w400,
                                          height: 1,
                                          color: GlameColors.textPrimary,
                                        ),
                                      ),
                                      if (description.isNotEmpty) ...[
                                        const SizedBox(height: 8),
                                        Text(
                                          description,
                                          maxLines: 2,
                                          overflow: TextOverflow.ellipsis,
                                          style: TextStyle(
                                            fontSize: isCompact ? 13 : 14,
                                            height: 1.35,
                                            color: GlameColors.textSecondary,
                                          ),
                                        ),
                                      ],
                                    ],
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Column(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  children: [
                                    Text(
                                      _piecesLabel(products.length),
                                      style: const TextStyle(
                                        fontSize: 12,
                                        color: GlameColors.textSecondary,
                                      ),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      formatRubFromKopeks(totalPrice),
                                      style: TextStyle(
                                        fontSize: isCompact ? 18 : 20,
                                        fontWeight: FontWeight.w400,
                                        color: GlameColors.textPrimary,
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                            const Spacer(),
                            _LookProductsRow(products: products),
                            const SizedBox(height: 14),
                            Container(
                              decoration: BoxDecoration(
                                border: Border.all(
                                  color: GlameColors.lightGray,
                                ),
                                borderRadius: BorderRadius.circular(16),
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: FilledButton(
                                      onPressed: _busy ? null : _collectLook,
                                      style: _looksPrimaryButtonStyle(),
                                      child: const Text('Собрать образ'),
                                    ),
                                  ),
                                  Expanded(
                                    child: InkWell(
                                      onTap: _openDetails,
                                      borderRadius: BorderRadius.circular(16),
                                      child: Container(
                                        height: 48,
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 16,
                                        ),
                                        decoration: const BoxDecoration(
                                          border: Border(
                                            left: BorderSide(
                                              color: GlameColors.lightGray,
                                            ),
                                          ),
                                        ),
                                        child: const Row(
                                          mainAxisAlignment:
                                              MainAxisAlignment.center,
                                          children: [
                                            Text(
                                              'Подробнее',
                                              style: TextStyle(
                                                color:
                                                    GlameColors.textSecondary,
                                              ),
                                            ),
                                            SizedBox(width: 6),
                                            Icon(
                                              Icons.arrow_forward,
                                              size: 18,
                                              color: GlameColors.textPrimary,
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            if (_favoriteCount > 0) ...[
                              const SizedBox(height: 8),
                              Text(
                                'Сохранений: $_favoriteCount',
                                style: const TextStyle(
                                  fontSize: 12,
                                  color: GlameColors.textSecondary,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }

  Future<void> _collectLook() async {
    final lookId = _asString(widget.post['id']);
    final productIds = _productIds(widget.post);
    if (productIds.isEmpty) {
      _showSnack('В этом образе пока нет товаров для корзины');
      return;
    }

    final auth = ref.read(authControllerProvider);
    if (auth.user == null) {
      if (!mounted) return;
      context.go('/login?next=${Uri.encodeComponent('/home?tab=5')}');
      return;
    }

    setState(() => _busy = true);
    try {
      await ref.read(cartControllerProvider.notifier).addMany(productIds);
      if (!mounted) return;
      final cartState = ref.read(cartControllerProvider);
      if (cartState.error != null) {
        _showSnack(cartState.error!);
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            lookId.isEmpty
                ? 'Образ добавлен в корзину'
                : 'Образ добавлен в корзину: ${productIds.length} поз.',
          ),
          backgroundColor: GlameColors.textPrimary,
          duration: const Duration(seconds: 2),
          action: SnackBarAction(
            label: 'ПЕРЕЙТИ',
            textColor: GlameColors.gold,
            onPressed: () => context.go('/home?tab=3'),
          ),
        ),
      );
    } catch (_) {
      _showSnack('Не удалось добавить образ в корзину');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _toggleFavorite() async {
    final id = _asString(widget.post['id']);
    if (id.isEmpty) return;
    setState(() => _busy = true);
    try {
      final result = await ref.read(looksApiProvider).toggleFavorite(id);
      if (!mounted) return;
      setState(() {
        _favorited = result['favorited'] == true;
        _favoriteCount = _asInt(result['favorite_count']);
      });
      ref.invalidate(customerSavedLooksProvider);
      ref.invalidate(customerFavoriteLooksProvider);
    } catch (_) {
      _showSnack('Войдите, чтобы сохранять образы');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _openDetails() {
    final id = _asString(widget.post['id']);
    if (id.isEmpty) return;
    context.push('/look/$id');
  }

  void _showSnack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }
}

class _LookInstagramCard extends ConsumerStatefulWidget {
  final Map<String, dynamic> post;

  const _LookInstagramCard({required this.post});

  @override
  ConsumerState<_LookInstagramCard> createState() => _LookInstagramCardState();
}

class _LookInstagramCardState extends ConsumerState<_LookInstagramCard> {
  final PageController _pageController = PageController();
  bool _busy = false;
  int _pageIndex = 0;
  bool _showTapHeart = false;
  late bool _favorited;
  late bool _liked;
  late int _favoriteCount;
  late int _likeCount;

  @override
  void initState() {
    super.initState();
    _favorited = widget.post['favorited_by_me'] == true;
    _liked = widget.post['liked_by_me'] == true;
    _favoriteCount = _asInt(widget.post['favorite_count']);
    _likeCount = _asInt(widget.post['like_count']);
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final gallery = _lookGalleryUrls(widget.post);
    final images = gallery.isEmpty ? const <String?>[null] : gallery;
    final title = titleOrFallback(widget.post);
    final caption = _instagramCaption(widget.post);
    final tag = _primaryLookTag(widget.post);
    final products = _products(widget.post);
    final totalPrice = _lookTotalKopeks(widget.post);
    final canGoBack = context.canPop();
    final heroPrefix =
        'feed-${_asString(widget.post['id']).isEmpty ? title : _asString(widget.post['id'])}';

    return Container(
      decoration: BoxDecoration(
        color: GlameColors.surface2,
        border: Border.all(color: GlameColors.lightGray),
        borderRadius: BorderRadius.circular(26),
        boxShadow: [
          BoxShadow(
            color: GlameColors.textPrimary.withValues(alpha: 0.04),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(26),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
              child: Row(
                children: [
                  Container(
                    width: 38,
                    height: 38,
                    decoration: const BoxDecoration(
                      color: GlameColors.textPrimary,
                      shape: BoxShape.circle,
                    ),
                    alignment: Alignment.center,
                    child: const Text(
                      'GL',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: GlameColors.surface2,
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            const Flexible(
                              child: Text(
                                'glame_official',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: GlameColors.textPrimary,
                                ),
                              ),
                            ),
                            if (widget.post['is_new'] == true) ...[
                              const SizedBox(width: 8),
                              Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 8,
                                  vertical: 3,
                                ),
                                decoration: BoxDecoration(
                                  border: Border.all(
                                    color: GlameColors.textPrimary,
                                  ),
                                  borderRadius: BorderRadius.circular(999),
                                ),
                                child: const Text(
                                  'Новинка',
                                  style: TextStyle(
                                    fontSize: 10,
                                    color: GlameColors.textPrimary,
                                  ),
                                ),
                              ),
                            ],
                          ],
                        ),
                        const SizedBox(height: 2),
                        Text(
                          tag,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 12,
                            color: GlameColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: _busy ? null : _openDetails,
                    icon: const Icon(Icons.more_horiz),
                  ),
                ],
              ),
            ),
            GestureDetector(
              onTap: () => _openMediaViewer(images, heroPrefix: heroPrefix),
              onDoubleTap: _handleDoubleTapLike,
              child: AspectRatio(
                aspectRatio: 1,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    PageView.builder(
                      controller: _pageController,
                      itemCount: images.length,
                      onPageChanged: (value) {
                        setState(() => _pageIndex = value);
                      },
                      itemBuilder: (context, index) {
                        final imageUrl = images[index];
                        if (imageUrl == null) {
                          return const ColoredBox(color: GlameColors.surface);
                        }
                        return Hero(
                          tag: '$heroPrefix:$index',
                          child: CachedNetworkImage(
                            imageUrl: imageUrl,
                            fit: BoxFit.cover,
                            placeholder: (_, _) =>
                                const ColoredBox(color: GlameColors.surface),
                            errorWidget: (_, _, _) =>
                                const ColoredBox(color: GlameColors.surface),
                          ),
                        );
                      },
                    ),
                    if (images.length > 1)
                      Positioned(
                        right: 12,
                        top: 12,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 4,
                          ),
                          decoration: BoxDecoration(
                            color: GlameColors.textPrimary.withValues(
                              alpha: 0.58,
                            ),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Text(
                            '${_pageIndex + 1}/${images.length}',
                            style: const TextStyle(
                              fontSize: 11,
                              color: GlameColors.surface2,
                            ),
                          ),
                        ),
                      ),
                    Positioned(
                      left: 12,
                      bottom: 12,
                      child: _MediaViewerBadge(
                        onTap: () {
                          HapticFeedback.selectionClick();
                          _openMediaViewer(images, heroPrefix: heroPrefix);
                        },
                      ),
                    ),
                    IgnorePointer(
                      child: Center(
                        child: AnimatedScale(
                          duration: const Duration(milliseconds: 180),
                          scale: _showTapHeart ? 1 : 0.72,
                          child: AnimatedOpacity(
                            duration: const Duration(milliseconds: 180),
                            opacity: _showTapHeart ? 1 : 0,
                            child: const Icon(
                              Icons.favorite,
                              color: Colors.white,
                              size: 92,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      _FeedActionIcon(
                        icon: _liked ? Icons.favorite : Icons.favorite_border,
                        color: _liked
                            ? Colors.redAccent
                            : GlameColors.textPrimary,
                        onTap: _busy ? null : _toggleLike,
                      ),
                      const SizedBox(width: 14),
                      _FeedActionIcon(
                        icon: Icons.send_outlined,
                        onTap: _busy ? null : _shareLook,
                      ),
                      const Spacer(),
                      _FeedActionIcon(
                        icon: _favorited
                            ? Icons.bookmark
                            : Icons.bookmark_border,
                        onTap: _busy ? null : _toggleFavorite,
                      ),
                    ],
                  ),
                  if (images.length > 1) ...[
                    const SizedBox(height: 10),
                    Center(
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: List.generate(images.length, (index) {
                          final selected = index == _pageIndex;
                          return AnimatedContainer(
                            duration: const Duration(milliseconds: 180),
                            margin: const EdgeInsets.symmetric(horizontal: 3),
                            width: selected ? 16 : 6,
                            height: 6,
                            decoration: BoxDecoration(
                              color: selected
                                  ? GlameColors.textPrimary
                                  : GlameColors.lightGray,
                              borderRadius: BorderRadius.circular(999),
                            ),
                          );
                        }),
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  Text(
                    _likeCount > 0
                        ? '$_likeCount отметок “нравится”'
                        : 'Новый образ для Вашей ленты',
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: GlameColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 8),
                  RichText(
                    text: TextSpan(
                      style: const TextStyle(
                        fontFamily: 'Clinica Pro',
                        fontSize: 13,
                        height: 1.4,
                        color: GlameColors.textPrimary,
                      ),
                      children: [
                        const TextSpan(
                          text: 'glame_official ',
                          style: TextStyle(fontWeight: FontWeight.w600),
                        ),
                        TextSpan(text: caption),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    title,
                    style: const TextStyle(
                      fontSize: 12,
                      color: GlameColors.textSecondary,
                    ),
                  ),
                  if (products.isNotEmpty) ...[
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        const Text(
                          'Товары в образе',
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: GlameColors.textPrimary,
                          ),
                        ),
                        const Spacer(),
                        Text(
                          _favoriteCount > 0
                              ? '$_favoriteCount сохранений'
                              : _piecesLabel(products.length),
                          style: const TextStyle(
                            fontSize: 12,
                            color: GlameColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      height: 174,
                      child: ListView.separated(
                        scrollDirection: Axis.horizontal,
                        itemCount: products.length,
                        separatorBuilder: (_, _) => const SizedBox(width: 10),
                        itemBuilder: (context, index) =>
                            _LookFeedProductCard(product: products[index]),
                      ),
                    ),
                  ],
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Стоимость образа',
                              style: TextStyle(
                                fontSize: 12,
                                color: GlameColors.textSecondary,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              formatRubFromKopeks(totalPrice),
                              style: const TextStyle(
                                fontSize: 20,
                                color: GlameColors.textPrimary,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: FilledButton(
                          onPressed: _busy ? null : _openDetails,
                          style: _looksPrimaryButtonStyle(),
                          child: Text(
                            canGoBack ? 'Открыть образ' : 'Смотреть образ',
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _toggleLike() async {
    final id = _asString(widget.post['id']);
    if (id.isEmpty) return;
    setState(() => _busy = true);
    try {
      final result = await ref.read(looksApiProvider).toggleLike(id);
      if (!mounted) return;
      setState(() {
        _liked = result['liked'] == true;
        _likeCount = _asInt(result['like_count']);
      });
    } catch (_) {
      _showSnack('Войдите, чтобы ставить отметки “нравится”');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _toggleFavorite() async {
    final id = _asString(widget.post['id']);
    if (id.isEmpty) return;
    setState(() => _busy = true);
    try {
      final result = await ref.read(looksApiProvider).toggleFavorite(id);
      if (!mounted) return;
      setState(() {
        _favorited = result['favorited'] == true;
        _favoriteCount = _asInt(result['favorite_count']);
      });
      ref.invalidate(customerSavedLooksProvider);
      ref.invalidate(customerFavoriteLooksProvider);
    } catch (_) {
      _showSnack('Войдите, чтобы сохранять образы');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _shareLook() async {
    final id = _asString(widget.post['id']);
    if (id.isEmpty) return;
    await Clipboard.setData(
      ClipboardData(text: 'https://app.glamejewelry.ru/#/look/$id'),
    );
    _showSnack('Ссылка на образ скопирована');
  }

  void _openDetails() {
    final id = _asString(widget.post['id']);
    if (id.isEmpty) return;
    context.push('/look/$id');
  }

  Future<void> _handleDoubleTapLike() async {
    if (_busy) return;
    HapticFeedback.lightImpact();
    setState(() => _showTapHeart = true);
    if (!_liked) {
      await _toggleLike();
    }
    if (!mounted) return;
    await Future<void>.delayed(const Duration(milliseconds: 420));
    if (!mounted) return;
    setState(() => _showTapHeart = false);
  }

  void _openMediaViewer(List<String?> images, {required String heroPrefix}) {
    final urls = images.whereType<String>().where((x) => x.isNotEmpty).toList();
    if (urls.isEmpty) {
      _openDetails();
      return;
    }
    _showLookMediaViewer(
      context,
      images: urls,
      initialIndex: _pageIndex.clamp(0, urls.length - 1),
      title: titleOrFallback(widget.post),
      heroPrefix: heroPrefix,
    );
  }

  void _showSnack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }
}

class _LookGrid extends StatelessWidget {
  final List<Map<String, dynamic>> posts;
  final double maxWidth;
  final String activeFilter;
  final bool isFollowing;
  final ValueChanged<String> onHighlightTap;
  final Future<void> Function() onToggleFollowing;
  final VoidCallback onMessageTap;
  final Future<void> Function() onInviteTap;
  final VoidCallback onOpenProfile;

  const _LookGrid({
    required this.posts,
    required this.maxWidth,
    required this.activeFilter,
    required this.isFollowing,
    required this.onHighlightTap,
    required this.onToggleFollowing,
    required this.onMessageTap,
    required this.onInviteTap,
    required this.onOpenProfile,
  });

  @override
  Widget build(BuildContext context) {
    final columns = _looksGridColumnCount(maxWidth);
    final gap = maxWidth >= 860 ? 14.0 : 8.0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _LookGridProfileHeader(
          posts: posts,
          isWide: maxWidth >= 860,
          isFollowing: isFollowing,
          onToggleFollowing: onToggleFollowing,
          onMessageTap: onMessageTap,
          onInviteTap: onInviteTap,
          onOpenProfile: onOpenProfile,
        ),
        const SizedBox(height: 18),
        _LookGridHighlights(
          posts: posts,
          activeFilter: activeFilter,
          onTap: onHighlightTap,
        ),
        const SizedBox(height: 18),
        const _LookGridTabs(),
        const SizedBox(height: 12),
        GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: posts.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            mainAxisSpacing: gap,
            crossAxisSpacing: gap,
            childAspectRatio: 1,
          ),
          itemBuilder: (context, index) => _LookGridTile(post: posts[index]),
        ),
      ],
    );
  }
}

class _LookGridProfileHeader extends StatelessWidget {
  final List<Map<String, dynamic>> posts;
  final bool isWide;
  final bool isFollowing;
  final Future<void> Function() onToggleFollowing;
  final VoidCallback onMessageTap;
  final Future<void> Function() onInviteTap;
  final VoidCallback onOpenProfile;

  const _LookGridProfileHeader({
    required this.posts,
    required this.isWide,
    required this.isFollowing,
    required this.onToggleFollowing,
    required this.onMessageTap,
    required this.onInviteTap,
    required this.onOpenProfile,
  });

  @override
  Widget build(BuildContext context) {
    final totalLikes = posts.fold<int>(
      0,
      (sum, post) => sum + _asInt(post['like_count']),
    );
    final totalSaves = posts.fold<int>(
      0,
      (sum, post) => sum + _asInt(post['favorite_count']),
    );
    final filteredStyles = posts
        .expand(_lookLabels)
        .where((label) => label != 'Все')
        .toSet()
        .toList(growable: false);
    final subtitle = filteredStyles.isEmpty
        ? 'Редакция образов GLAME'
        : filteredStyles.take(3).join(' · ');

    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
        isWide ? 20 : 14,
        isWide ? 20 : 14,
        isWide ? 20 : 14,
        isWide ? 18 : 14,
      ),
      decoration: BoxDecoration(
        color: GlameColors.surface2,
        border: Border.all(color: GlameColors.lightGray),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: isWide ? 88 : 74,
                height: isWide ? 88 : 74,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: GlameColors.lightGray),
                  gradient: const LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      Color(0xFFF1F1EE),
                      Color(0xFFD8D5CE),
                      Color(0xFFF8F7F3),
                    ],
                  ),
                ),
                child: Center(
                  child: Container(
                    width: isWide ? 74 : 62,
                    height: isWide ? 74 : 62,
                    decoration: const BoxDecoration(
                      color: GlameColors.textPrimary,
                      shape: BoxShape.circle,
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      'GL',
                      style: TextStyle(
                        fontSize: isWide ? 22 : 18,
                        fontWeight: FontWeight.w600,
                        color: GlameColors.surface2,
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 18),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Expanded(
                          child: Text(
                            'glame_official',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w400,
                              color: GlameColors.textPrimary,
                            ),
                          ),
                        ),
                        InkWell(
                          onTap: onOpenProfile,
                          borderRadius: BorderRadius.circular(999),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 6,
                            ),
                            decoration: BoxDecoration(
                              color: GlameColors.surface2,
                              border: Border.all(color: GlameColors.lightGray),
                              borderRadius: BorderRadius.circular(999),
                            ),
                            child: const Text(
                              'Профиль',
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w500,
                                color: GlameColors.textPrimary,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      subtitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 13,
                        height: 1.3,
                        color: GlameColors.textSecondary,
                      ),
                    ),
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        _ProfileMetric(
                          value: '${posts.length}',
                          label: 'поста',
                        ),
                        const SizedBox(width: 22),
                        _ProfileMetric(
                          value: _compactCount(totalLikes),
                          label: 'лайков',
                        ),
                        const SizedBox(width: 22),
                        _ProfileMetric(
                          value: _compactCount(totalSaves),
                          label: 'сохранений',
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Text(
            'GLAME Jewelry',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: GlameColors.textPrimary,
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'Образы и подборки под Ваш стиль. Сетка повторяет привычный формат Instagram-профиля.',
            style: TextStyle(
              fontSize: 12,
              height: 1.35,
              color: GlameColors.textSecondary,
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: FilledButton(
                  onPressed: onToggleFollowing,
                  style: _looksPrimaryButtonStyle(height: 40, radius: 12),
                  child: Text(isFollowing ? 'Вы подписаны' : 'Подписаться'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton(
                  onPressed: onMessageTap,
                  style: _looksSecondaryButtonStyle(height: 40, radius: 12),
                  child: const Text('Написать'),
                ),
              ),
              const SizedBox(width: 8),
              SizedBox(
                width: 44,
                height: 40,
                child: OutlinedButton(
                  onPressed: onInviteTap,
                  style: _looksSecondaryButtonStyle(
                    height: 40,
                    radius: 12,
                  ).copyWith(padding: WidgetStateProperty.all(EdgeInsets.zero)),
                  child: const Icon(
                    Icons.person_add_alt_1_outlined,
                    size: 18,
                    color: GlameColors.textPrimary,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _LookFeedHeaderStrip extends StatelessWidget {
  final VoidCallback onTap;

  const _LookFeedHeaderStrip({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: Container(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
          decoration: BoxDecoration(
            color: GlameColors.surface2,
            border: Border.all(color: GlameColors.lightGray),
            borderRadius: BorderRadius.circular(18),
            boxShadow: [
              BoxShadow(
                color: GlameColors.textPrimary.withValues(alpha: 0.03),
                blurRadius: 10,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Row(
            children: [
              Container(
                width: 34,
                height: 34,
                decoration: const BoxDecoration(
                  color: GlameColors.textPrimary,
                  shape: BoxShape.circle,
                ),
                alignment: Alignment.center,
                child: const Text(
                  'GL',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: GlameColors.surface2,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'glame_official',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: GlameColors.textPrimary,
                      ),
                    ),
                    SizedBox(height: 2),
                    Text(
                      'Лента образов',
                      style: TextStyle(
                        fontSize: 11,
                        color: GlameColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: GlameColors.surface,
                  border: Border.all(color: GlameColors.lightGray),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.push_pin_outlined,
                      size: 14,
                      color: GlameColors.textSecondary,
                    ),
                    SizedBox(width: 6),
                    Text(
                      'Feed',
                      style: TextStyle(
                        fontSize: 11,
                        color: GlameColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LooksProfilePinnedHeader extends StatelessWidget {
  final String activeFilter;
  final _LooksProfileTab selectedTab;
  final Map<_LooksProfileTab, int> counts;
  final ValueChanged<_LooksProfileTab> onTabChanged;

  const _LooksProfilePinnedHeader({
    required this.activeFilter,
    required this.selectedTab,
    required this.counts,
    required this.onTabChanged,
  });

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: GlameColors.surface2,
      child: Column(
        children: [
          Container(
            height: 42,
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.symmetric(horizontal: 12),
            decoration: BoxDecoration(
              color: GlameColors.surface2,
              border: Border.all(color: GlameColors.lightGray),
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: GlameColors.textPrimary.withValues(alpha: 0.03),
                  blurRadius: 8,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            child: Row(
              children: [
                Container(
                  width: 24,
                  height: 24,
                  decoration: const BoxDecoration(
                    color: GlameColors.textPrimary,
                    shape: BoxShape.circle,
                  ),
                  alignment: Alignment.center,
                  child: const Text(
                    'GL',
                    style: TextStyle(
                      fontSize: 9,
                      fontWeight: FontWeight.w600,
                      color: GlameColors.surface2,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    'glame_official',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: GlameColors.textPrimary,
                    ),
                  ),
                ),
                if (activeFilter != 'Все')
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 5,
                    ),
                    decoration: BoxDecoration(
                      color: GlameColors.surface,
                      border: Border.all(color: GlameColors.lightGray),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Text(
                      activeFilter,
                      style: const TextStyle(
                        fontSize: 10,
                        color: GlameColors.textSecondary,
                      ),
                    ),
                  ),
              ],
            ),
          ),
          _LookGridTabs(
            selectedTab: selectedTab,
            counts: counts,
            onTabChanged: (tab) {
              HapticFeedback.selectionClick();
              onTabChanged(tab);
            },
          ),
        ],
      ),
    );
  }
}

class _LookGridHighlights extends StatelessWidget {
  final List<Map<String, dynamic>> posts;
  final String activeFilter;
  final ValueChanged<String> onTap;

  const _LookGridHighlights({
    required this.posts,
    required this.activeFilter,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final items = _highlightLabels(posts);
    if (items.isEmpty) return const SizedBox.shrink();

    return SizedBox(
      height: 102,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: items.length,
        separatorBuilder: (_, _) => const SizedBox(width: 16),
        itemBuilder: (context, index) => _HighlightBubble(
          label: items[index],
          coverUrl: _highlightCoverUrl(posts, items[index]),
          accentIndex: index,
          selected: items[index] == activeFilter,
          onTap: () {
            HapticFeedback.selectionClick();
            onTap(items[index]);
            _showLookStoriesViewer(
              context,
              posts: posts
                  .where((post) => _matchesFilter(post, items[index]))
                  .toList(),
              title: items[index],
            );
          },
        ),
      ),
    );
  }
}

class _HighlightBubble extends StatelessWidget {
  final String label;
  final String? coverUrl;
  final int accentIndex;
  final bool selected;
  final VoidCallback onTap;

  const _HighlightBubble({
    required this.label,
    required this.coverUrl,
    required this.accentIndex,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final gradients = [
      const [Color(0xFFF6F5F1), Color(0xFFD8D4CB), Color(0xFFF1EFE9)],
      const [Color(0xFFF2F2F0), Color(0xFFCBC6BD), Color(0xFFEFECE4)],
      const [Color(0xFFF7F6F2), Color(0xFFD4D0C7), Color(0xFFF6F4EF)],
    ];
    final colors = gradients[accentIndex % gradients.length];

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(18),
      child: SizedBox(
        width: 76,
        child: Column(
          children: [
            Container(
              width: 74,
              height: 74,
              padding: const EdgeInsets.all(3),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: colors,
                ),
              ),
              child: Container(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: selected
                        ? GlameColors.textPrimary
                        : GlameColors.surface2,
                    width: selected ? 2.5 : 2,
                  ),
                  color: GlameColors.surface,
                ),
                clipBehavior: Clip.antiAlias,
                alignment: Alignment.center,
                child: coverUrl == null
                    ? Text(
                        label.characters.first.toUpperCase(),
                        style: const TextStyle(
                          fontSize: 20,
                          color: GlameColors.textPrimary,
                        ),
                      )
                    : Stack(
                        fit: StackFit.expand,
                        children: [
                          CachedNetworkImage(
                            imageUrl: coverUrl!,
                            fit: BoxFit.cover,
                            errorWidget: (_, _, _) =>
                                const ColoredBox(color: GlameColors.surface),
                          ),
                          DecoratedBox(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                                colors: [
                                  Colors.transparent,
                                  GlameColors.textPrimary.withValues(
                                    alpha: 0.16,
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 11,
                color: selected
                    ? GlameColors.textPrimary
                    : GlameColors.textSecondary,
                fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProfileMetric extends StatelessWidget {
  final String value;
  final String label;

  const _ProfileMetric({required this.value, required this.label});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          value,
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: GlameColors.textPrimary,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: const TextStyle(
            fontSize: 11,
            color: GlameColors.textSecondary,
          ),
        ),
      ],
    );
  }
}

class _LookGridTabs extends StatelessWidget {
  final _LooksProfileTab selectedTab;
  final ValueChanged<_LooksProfileTab>? onTabChanged;
  final Map<_LooksProfileTab, int> counts;

  const _LookGridTabs({
    this.selectedTab = _LooksProfileTab.grid,
    this.onTabChanged,
    this.counts = const {},
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        border: Border(
          top: BorderSide(color: GlameColors.lightGray),
          bottom: BorderSide(color: GlameColors.lightGray),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: _GridTabItem(
              icon: Icons.grid_on_outlined,
              selected: selectedTab == _LooksProfileTab.grid,
              label: _compactCount(counts[_LooksProfileTab.grid] ?? 0),
              onTap: onTabChanged == null
                  ? null
                  : () => onTabChanged!(_LooksProfileTab.grid),
            ),
          ),
          Expanded(
            child: _GridTabItem(
              icon: Icons.video_collection_outlined,
              selected: selectedTab == _LooksProfileTab.feed,
              label: _compactCount(counts[_LooksProfileTab.feed] ?? 0),
              onTap: onTabChanged == null
                  ? null
                  : () => onTabChanged!(_LooksProfileTab.feed),
            ),
          ),
          Expanded(
            child: _GridTabItem(
              icon: Icons.bookmark_border,
              selected: selectedTab == _LooksProfileTab.saved,
              label: _compactCount(counts[_LooksProfileTab.saved] ?? 0),
              onTap: onTabChanged == null
                  ? null
                  : () => onTabChanged!(_LooksProfileTab.saved),
            ),
          ),
        ],
      ),
    );
  }
}

class _GridTabItem extends StatelessWidget {
  final IconData icon;
  final bool selected;
  final VoidCallback? onTap;
  final String label;

  const _GridTabItem({
    required this.icon,
    required this.label,
    this.selected = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        height: 42,
        decoration: BoxDecoration(
          border: selected
              ? const Border(
                  top: BorderSide(color: GlameColors.textPrimary, width: 1.5),
                )
              : null,
        ),
        alignment: Alignment.center,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 20,
              color: selected
                  ? GlameColors.textPrimary
                  : GlameColors.textSecondary,
            ),
            const SizedBox(width: 8),
            Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                color: selected
                    ? GlameColors.textPrimary
                    : GlameColors.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LookGridTile extends StatelessWidget {
  final Map<String, dynamic> post;

  const _LookGridTile({required this.post});

  @override
  Widget build(BuildContext context) {
    final id = _asString(post['id']);
    final image = _lookCover(post);
    final gallery = _lookGalleryUrls(post);
    final mediaCount = _lookGalleryUrls(post).length;
    final tag = _primaryLookTag(post);
    final totalPrice = _lookTotalKopeks(post);
    final heroPrefix = 'grid-${id.isEmpty ? titleOrFallback(post) : id}';

    return InkWell(
      onTap: id.isEmpty ? null : () => context.push('/look/$id'),
      borderRadius: BorderRadius.circular(18),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(18),
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (image == null)
              const ColoredBox(color: GlameColors.surface)
            else
              Hero(
                tag: '$heroPrefix:0',
                child: CachedNetworkImage(
                  imageUrl: image,
                  fit: BoxFit.cover,
                  errorWidget: (_, _, _) =>
                      const ColoredBox(color: GlameColors.surface),
                ),
              ),
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.transparent,
                      GlameColors.textPrimary.withValues(alpha: 0.06),
                      GlameColors.textPrimary.withValues(alpha: 0.55),
                    ],
                  ),
                ),
              ),
            ),
            Positioned(
              left: 8,
              top: 8,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: GlameColors.surface2.withValues(alpha: 0.9),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  tag,
                  style: const TextStyle(
                    fontSize: 10,
                    color: GlameColors.textPrimary,
                  ),
                ),
              ),
            ),
            if (mediaCount > 1)
              Positioned(
                right: 8,
                top: 8,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: GlameColors.textPrimary.withValues(alpha: 0.72),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    '$mediaCount фото',
                    style: const TextStyle(
                      fontSize: 10,
                      color: GlameColors.surface2,
                    ),
                  ),
                ),
              ),
            if ((gallery.isNotEmpty) || image != null)
              Positioned(
                right: 8,
                bottom: 8,
                child: _MediaViewerBadge(
                  onTap: () => _showLookMediaViewer(
                    context,
                    images: gallery.isNotEmpty ? gallery : [image!],
                    title: titleOrFallback(post),
                    heroPrefix: heroPrefix,
                  ),
                ),
              ),
            Positioned(
              left: 10,
              right: 10,
              bottom: 10,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    _asString(post['name']).isEmpty
                        ? 'Образ GLAME'
                        : _asString(post['name']),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 13,
                      height: 1.1,
                      color: GlameColors.surface2,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    formatRubFromKopeks(totalPrice),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 11,
                      color: GlameColors.surface2,
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

class _FeedActionIcon extends StatelessWidget {
  final IconData icon;
  final Color? color;
  final VoidCallback? onTap;

  const _FeedActionIcon({required this.icon, this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(999),
      child: Padding(
        padding: const EdgeInsets.all(2),
        child: Icon(icon, size: 24, color: color ?? GlameColors.textPrimary),
      ),
    );
  }
}

class _LookCoverTile extends StatelessWidget {
  final String? imageUrl;
  final String tag;
  final bool favorited;
  final bool busy;
  final Future<void> Function() onToggleFavorite;

  const _LookCoverTile({
    required this.imageUrl,
    required this.tag,
    required this.favorited,
    required this.busy,
    required this.onToggleFavorite,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        Positioned.fill(
          child: imageUrl == null
              ? const ColoredBox(color: GlameColors.surface)
              : CachedNetworkImage(
                  imageUrl: imageUrl!,
                  fit: BoxFit.cover,
                  errorWidget: (_, _, _) =>
                      const ColoredBox(color: GlameColors.surface),
                ),
        ),
        Positioned(
          left: 12,
          top: 12,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: GlameColors.textPrimary.withValues(alpha: 0.76),
              borderRadius: BorderRadius.circular(999),
            ),
            child: Text(
              tag.toUpperCase(),
              style: const TextStyle(
                color: GlameColors.surface2,
                fontSize: 10,
                letterSpacing: 0.5,
              ),
            ),
          ),
        ),
        Positioned(
          right: 10,
          top: 10,
          child: IconButton(
            tooltip: favorited ? 'Убрать из сохраненных' : 'Сохранить образ',
            onPressed: busy ? null : onToggleFavorite,
            style: IconButton.styleFrom(
              backgroundColor: GlameColors.surface2.withValues(alpha: 0.9),
              minimumSize: const Size(36, 36),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(999),
              ),
            ),
            icon: Icon(
              favorited ? Icons.bookmark : Icons.bookmark_border,
              color: GlameColors.textPrimary,
              size: 18,
            ),
          ),
        ),
      ],
    );
  }
}

class _LookProductsRow extends StatelessWidget {
  final List<Map<String, dynamic>> products;

  const _LookProductsRow({required this.products});

  @override
  Widget build(BuildContext context) {
    final visibleProducts = products.take(4).toList(growable: false);
    if (visibleProducts.isEmpty) {
      return const Text(
        'Товары в образе появятся после публикации комплекта.',
        style: TextStyle(color: GlameColors.textSecondary),
      );
    }

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < visibleProducts.length; i++) ...[
          Expanded(child: _LookProductTile(product: visibleProducts[i])),
          if (i != visibleProducts.length - 1) const SizedBox(width: 10),
        ],
      ],
    );
  }
}

class _LookProductTile extends StatelessWidget {
  final Map<String, dynamic> product;

  const _LookProductTile({required this.product});

  @override
  Widget build(BuildContext context) {
    final id = _asString(product['id']);
    final image = _firstImage(product['images']);
    final price = formatRubFromKopeks(product['price']);
    final option = _productOptionLabel(product);
    final stockLabel = _availabilityLabel(product);

    return InkWell(
      onTap: id.isEmpty ? null : () => context.push('/product/$id'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 0.9,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(14),
              child: image == null
                  ? const ColoredBox(color: GlameColors.surface)
                  : CachedNetworkImage(
                      imageUrl: image,
                      fit: BoxFit.cover,
                      errorWidget: (_, _, _) =>
                          const ColoredBox(color: GlameColors.surface),
                    ),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            price.isEmpty ? '—' : price,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w400),
          ),
          const SizedBox(height: 6),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 7),
            decoration: BoxDecoration(
              color: GlameColors.surface,
              border: Border.all(color: GlameColors.lightGray),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(
              option,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 11,
                color: GlameColors.textSecondary,
              ),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            stockLabel,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 11,
              color: GlameColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

class _LookFeedProductCard extends StatelessWidget {
  final Map<String, dynamic> product;

  const _LookFeedProductCard({required this.product});

  @override
  Widget build(BuildContext context) {
    final id = _asString(product['id']);
    final image = _firstImage(product['images']);
    final title = _asString(product['name']).isEmpty
        ? 'Украшение'
        : _asString(product['name']);
    final price = formatRubFromKopeks(product['price']);

    return InkWell(
      onTap: id.isEmpty ? null : () => context.push('/product/$id'),
      borderRadius: BorderRadius.circular(18),
      child: Container(
        width: 138,
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: GlameColors.surface2,
          border: Border.all(color: GlameColors.lightGray),
          borderRadius: BorderRadius.circular(18),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AspectRatio(
              aspectRatio: 1,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: image == null
                    ? const ColoredBox(color: GlameColors.surface)
                    : CachedNetworkImage(
                        imageUrl: image,
                        fit: BoxFit.cover,
                        errorWidget: (_, _, _) =>
                            const ColoredBox(color: GlameColors.surface),
                      ),
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: Text(
                title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 12,
                  height: 1.25,
                  color: GlameColors.textPrimary,
                ),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              price,
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: GlameColors.textPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MediaViewerBadge extends StatelessWidget {
  final VoidCallback onTap;

  const _MediaViewerBadge({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
          decoration: BoxDecoration(
            color: GlameColors.surface2.withValues(alpha: 0.92),
            border: Border.all(color: GlameColors.lightGray),
            borderRadius: BorderRadius.circular(999),
          ),
          child: const Icon(
            Icons.fullscreen,
            size: 16,
            color: GlameColors.textPrimary,
          ),
        ),
      ),
    );
  }
}

class _LookMediaViewer extends StatefulWidget {
  final List<String> images;
  final int initialIndex;
  final String? title;
  final String? heroPrefix;

  const _LookMediaViewer({
    required this.images,
    required this.initialIndex,
    this.title,
    this.heroPrefix,
  });

  @override
  State<_LookMediaViewer> createState() => _LookMediaViewerState();
}

class _LookMediaViewerState extends State<_LookMediaViewer> {
  late final PageController _controller;
  late int _currentIndex;
  double _dragOffsetY = 0;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex.clamp(0, widget.images.length - 1);
    _controller = PageController(initialPage: _currentIndex);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final dragProgress = (_dragOffsetY.abs() / 280).clamp(0.0, 1.0);
    return Scaffold(
      backgroundColor: Colors.black.withValues(
        alpha: 1 - (dragProgress * 0.45),
      ),
      body: GestureDetector(
        onVerticalDragUpdate: (details) {
          setState(() => _dragOffsetY += details.delta.dy);
        },
        onVerticalDragEnd: (details) {
          final velocity = details.primaryVelocity ?? 0;
          if (_dragOffsetY.abs() > 140 || velocity.abs() > 900) {
            Navigator.of(context).pop();
            return;
          }
          setState(() => _dragOffsetY = 0);
        },
        child: SafeArea(
          child: Transform.translate(
            offset: Offset(0, _dragOffsetY),
            child: Stack(
              children: [
                PageView.builder(
                  controller: _controller,
                  itemCount: widget.images.length,
                  onPageChanged: (value) {
                    setState(() => _currentIndex = value);
                  },
                  itemBuilder: (context, index) {
                    final imageChild = CachedNetworkImage(
                      imageUrl: widget.images[index],
                      fit: BoxFit.contain,
                      errorWidget: (_, _, _) => const ColoredBox(
                        color: Colors.black,
                        child: Center(
                          child: Icon(
                            Icons.broken_image_outlined,
                            color: Colors.white54,
                            size: 42,
                          ),
                        ),
                      ),
                    );
                    return InteractiveViewer(
                      minScale: 1,
                      maxScale: 4,
                      child: Center(
                        child: widget.heroPrefix == null
                            ? imageChild
                            : Hero(
                                tag: '${widget.heroPrefix}:$index',
                                child: imageChild,
                              ),
                      ),
                    );
                  },
                ),
                Positioned(
                  left: 12,
                  right: 12,
                  top: 8,
                  child: Row(
                    children: [
                      IconButton(
                        onPressed: () => Navigator.of(context).pop(),
                        icon: const Icon(Icons.close, color: Colors.white),
                      ),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if ((widget.title ?? '').trim().isNotEmpty)
                              Text(
                                widget.title!,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  fontSize: 14,
                                  color: Colors.white,
                                ),
                              ),
                            Text(
                              '${_currentIndex + 1} / ${widget.images.length}',
                              style: const TextStyle(
                                fontSize: 11,
                                color: Colors.white70,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
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

class _LookStoriesViewer extends StatefulWidget {
  final List<Map<String, dynamic>> posts;
  final String title;

  const _LookStoriesViewer({required this.posts, required this.title});

  @override
  State<_LookStoriesViewer> createState() => _LookStoriesViewerState();
}

class _LookStoriesViewerState extends State<_LookStoriesViewer>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  int _currentIndex = 0;

  @override
  void initState() {
    super.initState();
    _controller =
        AnimationController(
            vsync: this,
            duration: const Duration(milliseconds: 2800),
          )
          ..addStatusListener((status) {
            if (status != AnimationStatus.completed) return;
            if (_currentIndex >= widget.posts.length - 1) {
              Navigator.of(context).pop();
              return;
            }
            setState(() => _currentIndex += 1);
            _controller
              ..reset()
              ..forward();
          })
          ..forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _next() {
    if (_currentIndex >= widget.posts.length - 1) {
      Navigator.of(context).pop();
      return;
    }
    setState(() => _currentIndex += 1);
    _controller
      ..reset()
      ..forward();
  }

  void _previous() {
    if (_currentIndex <= 0) {
      _controller
        ..reset()
        ..forward();
      return;
    }
    setState(() => _currentIndex -= 1);
    _controller
      ..reset()
      ..forward();
  }

  @override
  Widget build(BuildContext context) {
    final post = widget.posts[_currentIndex];
    final image = _lookCover(post);
    final storyTitle = titleOrFallback(post);
    final subtitle = _lookDescription(post);

    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (image == null)
              const ColoredBox(color: Colors.black)
            else
              CachedNetworkImage(
                imageUrl: image,
                fit: BoxFit.cover,
                errorWidget: (_, _, _) => const ColoredBox(color: Colors.black),
              ),
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.black.withValues(alpha: 0.52),
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.58),
                  ],
                ),
              ),
            ),
            Positioned(
              left: 12,
              right: 12,
              top: 8,
              child: Column(
                children: [
                  AnimatedBuilder(
                    animation: _controller,
                    builder: (context, _) {
                      return Row(
                        children: List.generate(widget.posts.length, (index) {
                          final value = index < _currentIndex
                              ? 1.0
                              : index == _currentIndex
                              ? _controller.value
                              : 0.0;
                          return Expanded(
                            child: Padding(
                              padding: EdgeInsets.only(
                                right: index == widget.posts.length - 1 ? 0 : 4,
                              ),
                              child: ClipRRect(
                                borderRadius: BorderRadius.circular(999),
                                child: LinearProgressIndicator(
                                  minHeight: 3,
                                  value: value,
                                  backgroundColor: Colors.white24,
                                  valueColor:
                                      const AlwaysStoppedAnimation<Color>(
                                        Colors.white,
                                      ),
                                ),
                              ),
                            ),
                          );
                        }),
                      );
                    },
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Container(
                        width: 30,
                        height: 30,
                        decoration: const BoxDecoration(
                          color: Colors.white,
                          shape: BoxShape.circle,
                        ),
                        alignment: Alignment.center,
                        child: const Text(
                          'GL',
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: Colors.black,
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              widget.title,
                              style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: Colors.white,
                              ),
                            ),
                            Text(
                              storyTitle,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 11,
                                color: Colors.white70,
                              ),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        onPressed: () => Navigator.of(context).pop(),
                        icon: const Icon(Icons.close, color: Colors.white),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            Positioned(
              left: 18,
              right: 18,
              bottom: 34,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    storyTitle,
                    style: const TextStyle(fontSize: 22, color: Colors.white),
                  ),
                  if (subtitle.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      subtitle,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 13,
                        height: 1.35,
                        color: Colors.white70,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            Row(
              children: [
                Expanded(
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: _previous,
                  ),
                ),
                Expanded(
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: _next,
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

List<Map<String, dynamic>> _mediaItems(Map<String, dynamic> post) {
  final raw = post['media_items'];
  if (raw is List) {
    return raw
        .whereType<Map>()
        .map((x) => Map<String, dynamic>.from(x))
        .where((x) => _asString(x['url']).isNotEmpty)
        .toList(growable: false);
  }

  final image = _asString(post['image_url']);
  if (image.isNotEmpty) {
    return [
      {'type': 'image', 'url': image},
    ];
  }
  return const [];
}

List<String> _lookGalleryUrls(Map<String, dynamic> post) {
  final result = <String>[];
  final seen = <String>{};

  void add(dynamic value) {
    final url = _resolveLookImageItem(value);
    if (url == null || url.isEmpty) return;
    if (seen.add(url)) result.add(url);
  }

  final rawImageUrls = post['image_urls'];
  if (rawImageUrls is List) {
    for (final item in rawImageUrls) {
      add(item);
    }
  }

  final rawMedia = post['media_items'];
  if (rawMedia is List) {
    for (final item in rawMedia) {
      add(item);
    }
  }

  add(post['image_url']);
  return result;
}

String? _lookCover(Map<String, dynamic> post) {
  final fromImageUrls = _selectedLookImageFromList(
    post['image_urls'],
    preferredIndex: _asNullableInt(post['current_image_index']),
  );
  if (fromImageUrls != null) return fromImageUrls;

  final imageUrl = resolveAssetUrl(post['image_url']);
  if (imageUrl != null && imageUrl.isNotEmpty) return imageUrl;

  final media = _mediaItems(post);
  if (media.isNotEmpty) {
    final first = media.first;
    return resolveAssetUrl(first['thumbnail_url']) ??
        resolveAssetUrl(first['url']);
  }
  return null;
}

String _lookDescription(Map<String, dynamic> post) {
  final description = _asString(post['description']);
  if (description.isNotEmpty) return description;
  final caption = _asString(post['caption']);
  if (caption.isNotEmpty) return caption;
  final labels = _lookLabels(post).where((x) => x != 'Все').toList();
  if (labels.isEmpty) return '';
  return labels.take(2).join(' · ');
}

String _instagramCaption(Map<String, dynamic> post) {
  final caption = _asString(post['caption']);
  if (caption.isNotEmpty) return caption;
  final description = _lookDescription(post);
  if (description.isNotEmpty) return description;
  final title = titleOrFallback(post);
  if (title.isNotEmpty) return title;
  return 'Новый образ GLAME для Вашего настроения.';
}

String titleOrFallback(Map<String, dynamic> post) {
  final title = _asString(post['name']);
  if (title.isNotEmpty) return title;
  return 'Образ GLAME';
}

String _primaryLookTag(Map<String, dynamic> post) {
  final labels = _lookLabels(post).where((x) => x != 'Все').toList();
  if (labels.isNotEmpty) return labels.first;
  return 'Образ';
}

List<String> _lookFilters(List<Map<String, dynamic>> posts) {
  final filters = <String>['Все'];
  final seen = <String>{'все'};

  for (final post in posts) {
    for (final label in _lookLabels(post)) {
      final key = label.trim().toLowerCase();
      if (key.isEmpty || seen.contains(key)) continue;
      seen.add(key);
      filters.add(label);
    }
  }

  return filters;
}

List<String> _lookLabels(Map<String, dynamic> post) {
  final result = <String>[];

  void add(dynamic value) {
    if (value is List) {
      for (final item in value) {
        add(item);
      }
      return;
    }

    final text = _asString(value);
    if (text.isEmpty) return;
    if (result.any((item) => item.toLowerCase() == text.toLowerCase())) return;
    result.add(text);
  }

  add(post['style']);
  add(post['mood']);
  add(post['style_values']);
  add(post['mood_values']);
  add(post['style_dna']);
  add(post['style_dna_values']);
  add(post['radical']);
  add(post['radical_values']);
  if (post['is_new'] == true) {
    add('Новинка');
  }
  return result;
}

bool _matchesFilter(Map<String, dynamic> post, String filter) {
  final normalized = filter.trim().toLowerCase();
  if (normalized.isEmpty || normalized == 'все') return true;
  return _lookLabels(
    post,
  ).any((label) => label.trim().toLowerCase() == normalized);
}

int _lookTotalKopeks(Map<String, dynamic> post) {
  return _products(post).fold<int>(0, (sum, product) {
    return sum + _asInt(product['price']);
  });
}

List<String> _productIds(Map<String, dynamic> post) {
  return _products(post)
      .map((product) => _asString(product['id']))
      .where((id) => id.isNotEmpty)
      .toList(growable: false);
}

String _looksCountLabel(int count) {
  if (count == 1) return '1 образ';
  if (count >= 2 && count <= 4) return '$count образа';
  return '$count образов';
}

int _looksGridColumnCount(double width) {
  if (width >= 1200) return 5;
  if (width >= 900) return 4;
  return 3;
}

_LooksPresentation? _parseLooksPresentation(String? raw) {
  if (raw == null || raw.isEmpty) return null;
  for (final value in _LooksPresentation.values) {
    if (value.name == raw) return value;
  }
  return null;
}

_LooksProfileTab? _parseLooksProfileTab(String? raw) {
  if (raw == null || raw.isEmpty) return null;
  for (final value in _LooksProfileTab.values) {
    if (value.name == raw) return value;
  }
  return null;
}

String _looksProfileUrl({
  required String filter,
  required _LooksProfileTab tab,
}) {
  final params = <String, String>{'tab': tab.name};
  if (filter.trim().isNotEmpty && filter.trim() != 'Все') {
    params['lookFilter'] = filter.trim();
  }
  return Uri(path: '/looks-profile', queryParameters: params).toString();
}

String _compactCount(int value) {
  if (value >= 1000000) {
    final short = (value / 1000000).toStringAsFixed(
      value % 1000000 == 0 ? 0 : 1,
    );
    return '${short.replaceAll('.0', '')}M';
  }
  if (value >= 1000) {
    final short = (value / 1000).toStringAsFixed(value % 1000 == 0 ? 0 : 1);
    return '${short.replaceAll('.0', '')}K';
  }
  return '$value';
}

List<String> _highlightLabels(List<Map<String, dynamic>> posts) {
  final labels = posts
      .expand(_lookLabels)
      .where((label) => label != 'Все')
      .toSet()
      .toList(growable: false);
  if (labels.isNotEmpty) return labels.take(6).toList(growable: false);
  return const ['Новое', 'День', 'Вечер', 'Акцент'];
}

String? _highlightCoverUrl(List<Map<String, dynamic>> posts, String label) {
  for (final post in posts) {
    if (_matchesFilter(post, label)) {
      final cover = _lookCover(post);
      if (cover != null && cover.isNotEmpty) return cover;
    }
  }
  return null;
}

Future<void> _showLookMediaViewer(
  BuildContext context, {
  required List<String> images,
  int initialIndex = 0,
  String? title,
  String? heroPrefix,
}) {
  if (images.isEmpty) return Future.value();
  return Navigator.of(context).push(
    PageRouteBuilder<void>(
      opaque: false,
      barrierColor: Colors.black.withValues(alpha: 0.96),
      pageBuilder: (context, animation, secondaryAnimation) => _LookMediaViewer(
        images: images,
        initialIndex: initialIndex,
        title: title,
        heroPrefix: heroPrefix,
      ),
      transitionsBuilder: (context, animation, secondaryAnimation, child) {
        return FadeTransition(opacity: animation, child: child);
      },
    ),
  );
}

Future<void> _showLookStoriesViewer(
  BuildContext context, {
  required List<Map<String, dynamic>> posts,
  required String title,
}) {
  if (posts.isEmpty) return Future.value();
  return Navigator.of(context).push(
    PageRouteBuilder<void>(
      opaque: false,
      barrierColor: Colors.black,
      pageBuilder: (context, animation, secondaryAnimation) =>
          _LookStoriesViewer(posts: posts, title: title),
      transitionsBuilder: (context, animation, secondaryAnimation, child) {
        return FadeTransition(opacity: animation, child: child);
      },
    ),
  );
}

String _averageLookPriceLabel(List<Map<String, dynamic>> posts) {
  if (posts.isEmpty) return '';
  final totals = posts.map(_lookTotalKopeks).where((x) => x > 0).toList();
  if (totals.isEmpty) return '';
  final average = totals.reduce((a, b) => a + b) ~/ totals.length;
  return 'средняя стоимость ${formatRubFromKopeks(average)}';
}

String _piecesLabel(int count) {
  if (count == 1) return '1 украшение';
  if (count >= 2 && count <= 4) return '$count украшения';
  return '$count украшений';
}

String _productOptionLabel(Map<String, dynamic> product) {
  final specsRaw = product['specifications'];
  if (specsRaw is Map) {
    final specs = Map<String, dynamic>.from(specsRaw);
    final preferredKeys = [
      'размер',
      'size',
      'длина',
      'length',
      'диаметр',
      'diameter',
      'ширина',
      'weight',
      'вес',
      'материал',
      'material',
      'tip_zamka',
      'тип замка',
    ];

    for (final key in preferredKeys) {
      for (final entry in specs.entries) {
        final entryKey = entry.key.toLowerCase();
        if (!entryKey.contains(key)) continue;
        final value = _asString(entry.value);
        if (value.isNotEmpty) return value;
      }
    }
  }

  final article = _asString(product['article']);
  if (article.isNotEmpty) return article;

  final externalCode = _asString(product['external_code']);
  if (externalCode.isNotEmpty) return externalCode;

  final category = _asString(product['category']);
  if (category.isNotEmpty) return category;

  return 'Подбор';
}

String _availabilityLabel(Map<String, dynamic> product) {
  final stock = product['stock'];
  if (stock is num) {
    if (stock > 0) return 'В наличии';
    return 'Под заказ';
  }
  return 'В наличии';
}

List<Map<String, dynamic>> _products(Map<String, dynamic> post) {
  final raw = post['products'];
  if (raw is! List) return const [];
  return raw
      .whereType<Map>()
      .map((x) => Map<String, dynamic>.from(x))
      .toList(growable: false);
}

String? _firstImage(dynamic raw) {
  if (raw is! List || raw.isEmpty) return null;
  for (final value in raw) {
    final url = resolveAssetUrl(value is Map ? value['url'] : value);
    if (url != null && url.isNotEmpty) return url;
  }
  return null;
}

String _asString(dynamic value) {
  if (value == null) return '';
  if (value is String) return value.trim();
  return '$value'.trim();
}

int _asInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value) ?? 0;
  return 0;
}

int? _asNullableInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}

String? _selectedLookImageFromList(dynamic raw, {int? preferredIndex}) {
  if (raw is! List || raw.isEmpty) return null;

  if (preferredIndex != null &&
      preferredIndex >= 0 &&
      preferredIndex < raw.length) {
    final selected = _resolveLookImageItem(raw[preferredIndex]);
    if (selected != null && selected.isNotEmpty) return selected;
  }

  for (final item in raw) {
    final url = _resolveLookImageItem(item);
    if (url != null && url.isNotEmpty) return url;
  }
  return null;
}

String? _resolveLookImageItem(dynamic item) {
  if (item is Map) {
    return resolveAssetUrl(item['url']) ??
        resolveAssetUrl(item['thumbnail_url']) ??
        resolveAssetUrl(item['image_url']);
  }
  return resolveAssetUrl(item);
}
