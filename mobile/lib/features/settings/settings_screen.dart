// Settings screen — minimal scaffold hosting:
//
//   * Legal links (Privacy / Terms / Support) — App Store Connect
//     metadata requires these URLs anyway; surfacing them in-app is
//     best practice + helps reviewer-account auditors.
//   * Sign out (mirrors the dashboard overflow path; one of two
//     places the user can sign out from).
//   * Delete account — App Store Guideline 5.1.1(v) + Play Store
//     equivalent. Destructive ConfirmDialog → DELETE /v1/users/me →
//     local session_id wipe → /login.
//
// Routed at /settings from app_router.dart; entry from the dashboard
// overflow menu's "Settings" item.

import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/login/login_providers.dart';
import 'package:agent_playground/shared/confirm_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  static const _privacyUrl = 'https://solvr.dev/privacy';
  static const _termsUrl = 'https://solvr.dev/terms';
  static const _supportEmail = 'support@solvr.dev';

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          'Settings',
          style: SolvrTextStyles.mono(
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.symmetric(vertical: 8),
        children: [
          _SectionHeader(label: 'Legal'),
          _SettingsTile(
            label: 'Privacy Policy',
            onTap: () => _launchHttps(context, _privacyUrl),
          ),
          _SettingsTile(
            label: 'Terms of Service',
            onTap: () => _launchHttps(context, _termsUrl),
          ),
          _SettingsTile(
            label: 'Support',
            subtitle: _supportEmail,
            onTap: () => _launchMailto(context, _supportEmail),
          ),
          const SizedBox(height: 24),
          _SectionHeader(label: 'Account'),
          _SettingsTile(
            label: 'Sign out',
            onTap: () => _confirmSignOut(context, ref),
          ),
          _SettingsTile(
            label: 'Delete account',
            destructive: true,
            onTap: () => _confirmDeleteAccount(context, ref),
          ),
        ],
      ),
    );
  }

  Future<void> _launchHttps(BuildContext context, String url) async {
    final uri = Uri.parse(url);
    // Mirror bubble_widget.dart's https/http allow-list posture (D-46).
    if (uri.scheme != 'https' && uri.scheme != 'http') return;
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not open $url')),
      );
    }
  }

  Future<void> _launchMailto(BuildContext context, String email) async {
    final uri = Uri(scheme: 'mailto', path: email);
    final ok = await launchUrl(uri);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not open mail app — write to $email')),
      );
    }
  }

  Future<void> _confirmSignOut(BuildContext context, WidgetRef ref) async {
    final result = await ConfirmDialog.show(
      context,
      title: 'Sign out of Solvr Labs?',
      confirmLabel: 'Sign out',
    );
    if (result != ConfirmDialogResult.confirm) return;
    await ref.read(authServiceProvider).signOut();
    ref.read(showSignedOutBannerProvider.notifier).state = false;
    if (context.mounted) context.go('/login');
  }

  Future<void> _confirmDeleteAccount(
    BuildContext context,
    WidgetRef ref,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    final result = await ConfirmDialog.show(
      context,
      title: 'Delete your account?',
      body:
          'This permanently deletes your account, all agents, chat history, '
          'usage records, and credit balance. This cannot be undone.',
      confirmLabel: 'Delete account',
    );
    if (result != ConfirmDialogResult.confirm) return;

    final api = ref.read(apiClientProvider);
    final r = await api.deleteMe();
    if (!context.mounted) return;
    switch (r) {
      case Ok():
        // Server already cleared the cookie. Wipe local session_id +
        // sign out of Google so the next sign-in flow starts clean.
        await ref.read(authServiceProvider).signOut();
        ref.read(showSignedOutBannerProvider.notifier).state = false;
        if (!context.mounted) return;
        context.go('/login');
      case Err(:final error):
        messenger.showSnackBar(
          SnackBar(content: Text('Could not delete account: ${error.message}')),
        );
    }
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: Text(
        label.toUpperCase(),
        style: SolvrTextStyles.mono(
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ).copyWith(
          color: SolvrColors.mutedForeground,
          letterSpacing: 0.8,
        ),
      ),
    );
  }
}

class _SettingsTile extends StatelessWidget {
  const _SettingsTile({
    required this.label,
    required this.onTap,
    this.subtitle,
    this.destructive = false,
  });

  final String label;
  final String? subtitle;
  final VoidCallback onTap;
  final bool destructive;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: const BoxDecoration(
          border: Border(
            bottom: BorderSide(color: SolvrColors.border),
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    label,
                    style: SolvrTextStyles.mono(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ).copyWith(
                      color: destructive
                          ? SolvrColors.destructive
                          : SolvrColors.foreground,
                    ),
                  ),
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      subtitle!,
                      style: SolvrTextStyles.mono(fontSize: 11).copyWith(
                        color: SolvrColors.mutedForeground,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (!destructive)
              const Icon(
                Icons.chevron_right,
                color: SolvrColors.mutedForeground,
              ),
          ],
        ),
      ),
    );
  }
}
