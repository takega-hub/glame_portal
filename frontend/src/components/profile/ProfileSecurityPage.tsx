'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { adminAccess, adminSystem, api, RoleAccess, StaffUser } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';

export default function ProfileSecurityPage() {
  const router = useRouter();
  const { user, logout, rolePreview, accountPreview, setRolePreview } = useAuth();
  const [roles, setRoles] = useState<RoleAccess[]>([]);
  const [staff, setStaff] = useState<StaffUser[]>([]);
  const [rolesLoading, setRolesLoading] = useState(false);
  const [rolesError, setRolesError] = useState<string | null>(null);
  const [selectedRoleKey, setSelectedRoleKey] = useState('');
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const isRealAdmin = (user?.actual_role || user?.role) === 'admin';
  const canRestartPlatform = user?.role === 'admin' && !user?.is_role_preview;

  useEffect(() => {
    if (!isRealAdmin) return;

    let disposed = false;
    setRolesLoading(true);
    setRolesError(null);
    adminAccess
      .getRoles()
      .then(async (items) => {
        const staffItems = await adminAccess.getStaff();
        if (!disposed) {
          setRoles(items);
          setStaff(staffItems);
        }
      })
      .catch((e: any) => {
        if (!disposed) setRolesError(e.response?.data?.detail || e.message || 'Не удалось загрузить роли.');
      })
      .finally(() => {
        if (!disposed) setRolesLoading(false);
      });

    return () => {
      disposed = true;
    };
  }, [isRealAdmin]);

  useEffect(() => {
    setSelectedRoleKey(rolePreview?.role_key || '');
    setSelectedAccountId(accountPreview?.id || '');
  }, [rolePreview?.role_key, accountPreview?.id]);

  const onChangeRolePreview = (roleKey: string, accountId = '') => {
    if (!roleKey) {
      setRolePreview(null);
      setSelectedRoleKey('');
      setSelectedAccountId('');
      setSuccess('Режим проверки роли выключен. Вы снова видите платформу как администратор.');
      return;
    }

    const selectedRole = roles.find((role) => role.role_key === roleKey);
    if (!selectedRole) return;
    const matchingStaff = staff.filter((person) => person.role === roleKey);
    const selectedAccount = accountId ? matchingStaff.find((person) => person.id === accountId) || null : null;

    setSelectedRoleKey(roleKey);
    setSelectedAccountId(selectedAccount?.id || '');

    if (matchingStaff.length > 0 && !selectedAccount) {
      setRolePreview(selectedRole, null);
      setSuccess(`Выбрана роль ${selectedRole.role_label}. Теперь выберите конкретный аккаунт для проверки персональных данных.`);
      return;
    }

    setRolePreview(selectedRole, selectedAccount);
    setSuccess(
      selectedAccount
        ? `Включена проверка: ${selectedRole.role_label}, аккаунт ${selectedAccount.full_name || selectedAccount.email || selectedAccount.id}.`
        : `Включен режим проверки: ${selectedRole.role_label}. Меню и доступы показаны как для этой роли.`
    );
  };

  const selectedRoleStaff = staff.filter((person) => person.role === selectedRoleKey);

  const onRestartPlatform = async () => {
    const confirmed = window.confirm(
      'Перезагрузить платформу GLAME? Интерфейс может быть недоступен 20–60 секунд.'
    );
    if (!confirmed) return;

    setError(null);
    setSuccess(null);
    setRestarting(true);
    try {
      const response = await adminSystem.restartPlatform();
      setSuccess(response.message || 'Перезагрузка платформы запущена.');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось запустить перезагрузку платформы.');
    } finally {
      setRestarting(false);
    }
  };

  const onChangePassword = async () => {
    setError(null);
    setSuccess(null);

    if (newPassword.length < 6) {
      setError('Новый пароль должен быть не короче 6 символов.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Пароли не совпадают.');
      return;
    }

    setSaving(true);
    try {
      await api.changePassword(currentPassword || null, newPassword);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setSuccess('Пароль успешно изменен.');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось изменить пароль.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f7f3ed] px-4 py-6 md:px-6 md:py-8">
      <div className="mx-auto max-w-6xl overflow-hidden rounded-[28px] border border-[#eadfcd] bg-white shadow-sm">
        <div className="relative overflow-hidden border-b border-[#eadfcd] bg-[radial-gradient(circle_at_top_left,#fff7e6,transparent_34%),linear-gradient(135deg,#fffdf8_0%,#f5efe5_52%,#ffffff_100%)] p-6 md:p-8">
          <div className="absolute right-0 top-0 h-44 w-44 rounded-full bg-gold-200/20 blur-3xl" />
          <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <div className="mb-3 inline-flex rounded-full border border-[#e4d3b6] bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-[#8a6a32]">
                Аккаунт · безопасность
              </div>
              <h1 className="text-3xl font-semibold tracking-tight text-gray-950 md:text-4xl">Профиль</h1>
              <p className="mt-2 text-sm leading-6 text-gray-600 md:text-base">
                Учетная запись администратора, проверка ролей, системные действия и безопасная смена пароля в едином рабочем стиле GLAME.
              </p>
            </div>

            <div className="min-w-[260px] rounded-3xl border border-white/70 bg-white/85 p-4 shadow-sm backdrop-blur">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gray-950 text-lg font-semibold text-white">
                  {(user?.email || user?.phone || 'G').slice(0, 1).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-gray-950">{user?.email || user?.phone || 'Пользователь'}</div>
                  <div className="mt-1 text-xs text-gray-500">Текущий пользователь</div>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2 text-xs">
                <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 font-semibold text-gray-800">
                  Роль: {user?.role_label || user?.role || '—'}
                </span>
                {user?.is_role_preview && user.actual_role && (
                  <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 font-semibold text-amber-900">
                    Проверка роли · real: {user.actual_role}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="relative mt-6 grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-gray-200 bg-white/85 p-4 shadow-sm">
              <div className="text-xs font-medium uppercase tracking-wide text-gray-500">Аккаунт</div>
              <div className="mt-2 text-lg font-semibold text-gray-950">{user?.email || user?.phone || 'Пользователь'}</div>
              <div className="mt-1 text-xs text-gray-500">основная учетная запись</div>
            </div>
            <div className="rounded-2xl border border-amber-100 bg-white/85 p-4 shadow-sm">
              <div className="text-xs font-medium uppercase tracking-wide text-amber-700">Preview</div>
              <div className="mt-2 text-lg font-semibold text-gray-950">{rolePreview ? rolePreview.role_label : 'Выключен'}</div>
              <div className="mt-1 text-xs text-gray-500">режим проверки доступов</div>
            </div>
            <div className="rounded-2xl border border-emerald-100 bg-white/85 p-4 shadow-sm">
              <div className="text-xs font-medium uppercase tracking-wide text-emerald-700">Безопасность</div>
              <div className="mt-2 text-lg font-semibold text-gray-950">Пароль</div>
              <div className="mt-1 text-xs text-gray-500">изменение с подтверждением</div>
            </div>
          </div>
        </div>

        <div className="space-y-5 bg-[#fbfaf7] p-5 md:p-7">
          {error && <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>}
          {success && (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
              {success}
            </div>
          )}

          {isRealAdmin && (
            <section className="overflow-hidden rounded-[24px] border border-[#eadfcd] bg-white shadow-sm">
              <div className="flex flex-col gap-4 border-b border-[#eadfcd] bg-[linear-gradient(135deg,#fffdf8_0%,#fff7e6_100%)] px-5 py-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-2xl">
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a6a32]">Режим администратора</div>
                  <h2 className="mt-2 text-xl font-semibold text-gray-950">Войти как / проверить роль</h2>
                  <p className="mt-2 text-sm leading-6 text-gray-700">
                    Временная проверка меню и доступов без смены реальной учетной записи и токена администратора. Для продавца или управляющего можно выбрать конкретный аккаунт, чтобы увидеть персональные KPI и материалы.
                  </p>
                </div>
                <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 lg:max-w-sm">
                  Это UI-preview для контроля доступов. Реальные действия остаются под текущим администратором.
                </div>
              </div>

              <div className="grid gap-4 p-5 lg:grid-cols-[1fr_1fr]">
                <label htmlFor="profile-role-preview" className="block text-sm font-medium text-gray-800">
                  <span className="mb-2 block">Проверить роль</span>
                  <select
                    id="profile-role-preview"
                    value={selectedRoleKey}
                    onChange={(e) => onChangeRolePreview(e.target.value)}
                    disabled={rolesLoading}
                    className="block w-full rounded-2xl border border-gray-200 bg-[#fbfaf7] px-4 py-3 text-sm text-gray-950 outline-none transition focus:border-[#c8a86a] focus:bg-white focus:ring-2 focus:ring-[#eadfcd] disabled:opacity-60"
                  >
                    <option value="">Администратор — без проверки</option>
                    {roles
                      .filter((role) => role.role_key !== 'admin')
                      .map((role) => (
                        <option key={role.role_key} value={role.role_key}>
                          {role.role_label || role.role_key}
                        </option>
                      ))}
                  </select>
                </label>

                <div>
                  {selectedRoleKey && selectedRoleStaff.length > 0 ? (
                    <label htmlFor="profile-account-preview" className="block text-sm font-medium text-gray-800">
                      <span className="mb-2 block">Конкретный аккаунт</span>
                      <select
                        id="profile-account-preview"
                        value={selectedAccountId}
                        onChange={(e) => onChangeRolePreview(selectedRoleKey, e.target.value)}
                        disabled={rolesLoading}
                        className="block w-full rounded-2xl border border-gray-200 bg-[#fbfaf7] px-4 py-3 text-sm text-gray-950 outline-none transition focus:border-[#c8a86a] focus:bg-white focus:ring-2 focus:ring-[#eadfcd] disabled:opacity-60"
                      >
                        <option value="">Выберите аккаунт</option>
                        {selectedRoleStaff.map((person) => (
                          <option key={person.id} value={person.id}>
                            {person.full_name || person.email || person.id}
                          </option>
                        ))}
                      </select>
                      <span className="mt-2 block text-xs leading-5 text-gray-500">
                        Для продавца/управляющего персональные KPI, магазин, обучение и подсказки завязаны на конкретного сотрудника.
                      </span>
                    </label>
                  ) : (
                    <div className="rounded-2xl border border-dashed border-gray-200 bg-[#fbfaf7] p-4 text-sm text-gray-500">
                      {selectedRoleKey ? 'Для выбранной роли нет отдельных аккаунтов или они еще загружаются.' : 'Выберите роль, чтобы при необходимости открыть выбор конкретного аккаунта.'}
                    </div>
                  )}
                </div>
              </div>

              {(rolesError || rolePreview) && (
                <div className="border-t border-[#eadfcd] p-5">
                  {rolesError && <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{rolesError}</div>}
                  {rolePreview && (
                    <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950">
                      Сейчас включена проверка роли «{rolePreview.role_label}»: доступно разделов — {rolePreview.section_ids.length}.
                      {accountPreview && (
                        <span className="ml-1">
                          Аккаунт: {accountPreview.full_name || accountPreview.email || accountPreview.id}.
                        </span>
                      )}
                      <span className="ml-1">Чтобы вернуться в полный режим администратора, выберите «Администратор — без проверки».</span>
                    </div>
                  )}
                </div>
              )}
            </section>
          )}

          {canRestartPlatform && (
            <section className="overflow-hidden rounded-[24px] border border-red-200 bg-white shadow-sm">
              <div className="flex flex-col gap-4 bg-red-50 px-5 py-5 lg:flex-row lg:items-center lg:justify-between">
                <div className="max-w-2xl">
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-red-700">Системное действие</div>
                  <h2 className="mt-2 text-xl font-semibold text-gray-950">Перезагрузка платформы</h2>
                  <p className="mt-2 text-sm leading-6 text-red-900">
                    Кнопка выполняет <code className="rounded bg-white px-1 py-0.5 text-xs">systemctl restart glame-stack</code>. Используйте после обновления кода или конфигурации.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={onRestartPlatform}
                  disabled={restarting}
                  className="rounded-full bg-red-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-red-700 disabled:opacity-50"
                >
                  {restarting ? 'Запускаю перезагрузку...' : 'Перезагрузка платформы'}
                </button>
              </div>
            </section>
          )}

          <section className="overflow-hidden rounded-[24px] border border-[#eadfcd] bg-white shadow-sm">
            <div className="border-b border-[#eadfcd] bg-[linear-gradient(135deg,#ffffff_0%,#f8f1e6_100%)] px-5 py-5">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#8a6a32]">Безопасность входа</div>
              <h2 className="mt-2 text-xl font-semibold text-gray-950">Смена пароля</h2>
              <p className="mt-2 text-sm text-gray-600">Обновите пароль администратора. Новый пароль должен быть не короче 6 символов.</p>
            </div>

            <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="grid max-w-2xl gap-4">
                <label htmlFor="profile-current-password" className="block text-sm font-medium text-gray-800">
                  <span className="mb-2 block">Текущий пароль</span>
                  <input
                    id="profile-current-password"
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    autoComplete="current-password"
                    className="block w-full rounded-2xl border border-gray-200 bg-[#fbfaf7] px-4 py-3 text-sm text-gray-950 outline-none transition focus:border-[#c8a86a] focus:bg-white focus:ring-2 focus:ring-[#eadfcd]"
                  />
                </label>

                <label htmlFor="profile-new-password" className="block text-sm font-medium text-gray-800">
                  <span className="mb-2 block">Новый пароль</span>
                  <input
                    id="profile-new-password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    autoComplete="new-password"
                    placeholder="Не короче 6 символов"
                    className="block w-full rounded-2xl border border-gray-200 bg-[#fbfaf7] px-4 py-3 text-sm text-gray-950 outline-none transition placeholder:text-gray-400 focus:border-[#c8a86a] focus:bg-white focus:ring-2 focus:ring-[#eadfcd]"
                  />
                </label>

                <label htmlFor="profile-confirm-password" className="block text-sm font-medium text-gray-800">
                  <span className="mb-2 block">Подтверждение нового пароля</span>
                  <input
                    id="profile-confirm-password"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    autoComplete="new-password"
                    className="block w-full rounded-2xl border border-gray-200 bg-[#fbfaf7] px-4 py-3 text-sm text-gray-950 outline-none transition focus:border-[#c8a86a] focus:bg-white focus:ring-2 focus:ring-[#eadfcd]"
                  />
                </label>

                <div className="flex flex-wrap gap-3 pt-1">
                  <button
                    type="button"
                    onClick={onChangePassword}
                    disabled={saving}
                    className="rounded-full bg-gray-950 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#8a6a32] disabled:opacity-50"
                  >
                    {saving ? 'Сохранение...' : 'Изменить пароль'}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      logout();
                      router.push('/login');
                    }}
                    className="rounded-full border border-[#d8c7aa] bg-white px-6 py-3 text-sm font-semibold text-gray-800 transition hover:bg-[#fbfaf7]"
                  >
                    Выйти
                  </button>
                </div>
              </div>

              <div className="rounded-2xl border border-gray-200 bg-[#fbfaf7] p-4 text-sm leading-6 text-gray-600">
                <div className="font-semibold text-gray-950">Рекомендация безопасности</div>
                <ul className="mt-3 list-disc space-y-2 pl-5">
                  <li>Не используйте пароль от почты или личных сервисов.</li>
                  <li>После смены пароля выйдите и проверьте вход заново.</li>
                  <li>Не передавайте админ-доступы продавцам или внешним подрядчикам.</li>
                </ul>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
