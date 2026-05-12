import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

final onboardingControllerProvider =
    StateNotifierProvider<OnboardingController, bool?>((ref) {
      return OnboardingController();
    });

class OnboardingController extends StateNotifier<bool?> {
  static const _key = 'glame_onboarding_seen';

  OnboardingController() : super(null) {
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    state = prefs.getBool(_key) ?? false;
  }

  Future<void> complete() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_key, true);
    state = true;
  }
}
