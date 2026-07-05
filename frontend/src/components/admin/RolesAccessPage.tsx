'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { adminAccess, AdminSection, RoleAccess, StaffUser } from '@/lib/api';

const ROLE_ORDER = ['admin', 'marketer', 'manager', 'seller'];
const ROLE_LABELS: Record<string, string> = {
  admin: 'Админ',
  marketer: 'Маркетолог',
  manager: 'Управляющий',
  seller: 'Продавец',
};

export default function RolesAccessPage() {
  const [sections, setSections] = useState<AdminSection[]>([]);
  const [roles, setRoles] = useState<RoleAccess[]>([]);
  const [staff, setStaff] = useState<StaffUser[]>([]);
  const [selectedRole, setSelectedRole] = useState('marketer');
  const [draftSections, setDraftSections] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingStaffId, setDeletingStaffId] = useState<string | null>(null);
  const [staffForm, setStaffForm] = useState({
    email: '',
    password: '',
    full_name: '',
    role: 'seller',
  });

  const sectionsByGroup = useMemo(() => {
    return sections.reduce<Record<string, AdminSection[]>>((acc, section) => {
      acc[section.group] = acc[section.group] || [];
      acc[section.group].push(section);
      return acc;
    }, {});
  }, [sections]);

  const selected = roles.find((role) => role.role_key === selectedRole);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextSections, nextRoles, nextStaff] = await Promise.all([
        adminAccess.getSections(),
        adminAccess.getRoles(),
        adminAccess.getStaff(),
      ]);
      setSections(nextSections);
      setRoles(nextRoles);
      setStaff(nextStaff);
      const current = nextRoles.find((role) => role.role_key === selectedRole) || nextRoles[1] || nextRoles[0];
      setSelectedRole(current?.role_key || 'marketer');
      setDraftSections(current?.section_ids || []);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось загрузить настройки доступа');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const role = roles.find((item) => item.role_key === selectedRole);
    if (role) setDraftSections(role.section_ids);
  }, [selectedRole, roles]);

  const toggleSection = (sectionId: string) => {
    if (selectedRole === 'admin') return;
    setDraftSections((current) =>
      current.includes(sectionId)
        ? current.filter((item) => item !== sectionId)
        : [...current, sectionId]
    );
  };

  const saveRole = async () => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await adminAccess.updateRole(selectedRole, draftSections);
      setRoles((current) => current.map((role) => (role.role_key === updated.role_key ? updated : role)));
      setDraftSections(updated.section_ids);
      setMessage('Доступы роли сохранены');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось сохранить роль');
    } finally {
      setSaving(false);
    }
  };

  const createStaff = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await adminAccess.createStaff(staffForm);
      setStaffForm({ email: '', password: '', full_name: '', role: 'seller' });
      setMessage('Сотрудник добавлен');
      const nextStaff = await adminAccess.getStaff();
      setStaff(nextStaff);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось добавить сотрудника');
    } finally {
      setSaving(false);
    }
  };

  const updateStaffRole = async (user: StaffUser, role: string) => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await adminAccess.updateStaff(user.id, { role });
      setStaff((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setMessage('Роль сотрудника обновлена');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось обновить сотрудника');
    } finally {
      setSaving(false);
    }
  };

  const deleteStaff = async (user: StaffUser) => {
    const label = user.email || user.full_name || 'этого сотрудника';
    const confirmed = window.confirm(`Удалить сотрудника ${label}? Это действие нельзя отменить.`);
    if (!confirmed) return;

    setDeletingStaffId(user.id);
    setError(null);
    setMessage(null);
    try {
      await adminAccess.deleteStaff(user.id);
      setStaff((current) => current.filter((item) => item.id !== user.id));
      setMessage('Сотрудник удалён');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Не удалось удалить сотрудника');
    } finally {
      setDeletingStaffId(null);
    }
  };

  if (loading) {
    return <div className="p-6 text-sm text-gray-500">Загрузка...</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Роли и доступы</h1>
        <div className="mt-1 text-sm text-gray-600">Настройка разделов портала и сотрудников.</div>
      </div>

      {error && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
      {message && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {message}
        </div>
      )}

      <section className="rounded-md border border-gray-200 bg-white">
        <div className="border-b border-gray-200 p-4">
          <h2 className="text-lg font-semibold text-gray-900">Разделы по ролям</h2>
        </div>
        <div className="grid gap-0 md:grid-cols-[240px_1fr]">
          <div className="border-b border-gray-200 p-3 md:border-b-0 md:border-r">
            {ROLE_ORDER.map((roleKey) => {
              const role = roles.find((item) => item.role_key === roleKey);
              return (
                <button
                  key={roleKey}
                  type="button"
                  onClick={() => setSelectedRole(roleKey)}
                  className={`mb-1 flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm ${
                    selectedRole === roleKey ? 'bg-pink-50 text-pink-700' : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <span>{role?.role_label || ROLE_LABELS[roleKey]}</span>
                  <span className="text-xs text-gray-400">{role?.section_ids.length || 0}</span>
                </button>
              );
            })}
          </div>
          <div className="p-4">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <div className="font-medium text-gray-900">{selected?.role_label || ROLE_LABELS[selectedRole]}</div>
                <div className="text-sm text-gray-500">
                  {selectedRole === 'admin' ? 'Админу всегда доступны все разделы.' : 'Отметьте доступные разделы.'}
                </div>
              </div>
              <button
                type="button"
                onClick={saveRole}
                disabled={saving || selectedRole === 'admin'}
                className="rounded-md bg-pink-600 px-4 py-2 text-sm font-medium text-white hover:bg-pink-700 disabled:opacity-50"
              >
                Сохранить
              </button>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {Object.entries(sectionsByGroup).map(([group, groupSections]) => (
                <div key={group} className="rounded-md border border-gray-200 p-3">
                  <div className="mb-2 text-sm font-semibold text-gray-700">{group}</div>
                  <div className="space-y-2">
                    {groupSections.map((section) => (
                      <label key={section.id} className="flex items-start gap-2 text-sm text-gray-700">
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4 rounded border-gray-300 text-pink-600"
                          checked={selectedRole === 'admin' || draftSections.includes(section.id)}
                          disabled={selectedRole === 'admin'}
                          onChange={() => toggleSection(section.id)}
                        />
                        <span>
                          <span className="block font-medium text-gray-900">{section.name}</span>
                          <span className="block text-xs text-gray-500">{section.href}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-md border border-gray-200 bg-white">
        <div className="border-b border-gray-200 p-4">
          <h2 className="text-lg font-semibold text-gray-900">Сотрудники</h2>
        </div>
        <form onSubmit={createStaff} className="grid gap-3 border-b border-gray-200 p-4 md:grid-cols-5">
          <input
            type="email"
            required
            value={staffForm.email}
            onChange={(e) => setStaffForm((form) => ({ ...form, email: e.target.value }))}
            placeholder="email"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
          <input
            type="text"
            value={staffForm.full_name}
            onChange={(e) => setStaffForm((form) => ({ ...form, full_name: e.target.value }))}
            placeholder="имя"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
          <input
            type="password"
            required
            minLength={6}
            value={staffForm.password}
            onChange={(e) => setStaffForm((form) => ({ ...form, password: e.target.value }))}
            placeholder="пароль"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
          <select
            value={staffForm.role}
            onChange={(e) => setStaffForm((form) => ({ ...form, role: e.target.value }))}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          >
            {ROLE_ORDER.map((roleKey) => (
              <option key={roleKey} value={roleKey}>
                {ROLE_LABELS[roleKey]}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={saving}
            className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
          >
            Добавить
          </button>
        </form>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-3">Сотрудник</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Роль</th>
                <th className="px-4 py-3 text-right">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {staff.map((user) => (
                <tr key={user.id}>
                  <td className="px-4 py-3 text-gray-900">{user.full_name || 'Без имени'}</td>
                  <td className="px-4 py-3 text-gray-600">{user.email}</td>
                  <td className="px-4 py-3">
                    <select
                      value={user.role || 'seller'}
                      onChange={(e) => updateStaffRole(user, e.target.value)}
                      disabled={saving || deletingStaffId === user.id}
                      className="rounded-md border border-gray-300 px-3 py-2 text-sm disabled:opacity-50"
                    >
                      {ROLE_ORDER.map((roleKey) => (
                        <option key={roleKey} value={roleKey}>
                          {ROLE_LABELS[roleKey]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => deleteStaff(user)}
                      disabled={deletingStaffId === user.id || saving}
                      className="rounded-md border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                      title={`Удалить ${user.email || user.full_name || 'сотрудника'}`}
                    >
                      {deletingStaffId === user.id ? 'Удаление...' : 'Удалить'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
