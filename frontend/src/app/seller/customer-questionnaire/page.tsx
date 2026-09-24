"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";

type FormData = {
  last_name: string;
  first_name: string;
  middle_name: string;
  birth_date: string;
  phone: string;
  city: string;
  discovery_channels: string[];
  discovery_other: string;
  purchase_for: string[];
  contact_channels: string[];
  glame_values: string[];
};

type LoyaltyInfo = {
  level: string;
  bonus_percent: number;
  points: number;
  discount_card_number?: string | null;
};

type CustomerCandidate = {
  id: string;
  full_name: string;
  phone_masked: string;
  city: string;
};

const emptyForm: FormData = {
  last_name: "",
  first_name: "",
  middle_name: "",
  birth_date: "",
  phone: "",
  city: "",
  discovery_channels: [],
  discovery_other: "",
  purchase_for: [],
  contact_channels: [],
  glame_values: [],
};

const discovery = [
  "Проходил(а) мимо",
  "Социальные сети",
  "Отель / курорт",
  "По рекомендации",
  "Яндекс Карты",
  "Уже покупал(а) раньше",
];
const purchaseFor = ["Для себя", "В подарок", "И для себя, и в подарок"];
const contacts = [
  "Telegram",
  "WhatsApp",
  "Instagram",
  "SMS",
  "Звонок",
  "Не хочу получать сообщения",
];
const values = [
  "Необычный дизайн",
  "Большой выбор",
  "Подбор под образ",
  "Помощь стилиста",
  "Атмосфера пространства",
  "Программа лояльности",
];

function formatPhoneInput(phone: string) {
  const subscriber = phone.replace(/\D/g, "").replace(/^7/, "").slice(0, 10);
  const parts = [
    subscriber.slice(0, 3),
    subscriber.slice(3, 6),
    subscriber.slice(6, 8),
    subscriber.slice(8, 10),
  ].filter(Boolean);
  if (!parts.length) return "+7";
  return `+7 ${parts[0]}${parts[1] ? ` ${parts[1]}` : ""}${parts[2] ? `-${parts[2]}` : ""}${parts[3] ? `-${parts[3]}` : ""}`;
}

function phoneFromInput(value: string) {
  // The visible +7 belongs to the field. For a pasted full number or an extra
  // leading digit, keep exactly the last ten subscriber digits.
  let digits = value.replace(/\D/g, "");
  if (digits.startsWith("7")) digits = digits.slice(1);
  if (digits.length > 10) digits = digits.slice(-10);
  return digits ? `7${digits}` : "";
}

function splitFullName(fullName: string) {
  const [lastName = "", firstName = "", ...middleName] = fullName.trim().split(/\s+/);
  return { last_name: lastName, first_name: firstName, middle_name: middleName.join(" ") };
}

function CheckGroup({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const toggle = (value: string) =>
    onChange(
      selected.includes(value)
        ? selected.filter((item) => item !== value)
        : [...selected, value],
    );
  return (
    <fieldset className="border-t border-zinc-300 pt-5">
      <legend className="mb-3 text-lg font-semibold text-zinc-900">
        {label}
      </legend>
      <div className="grid gap-3 sm:grid-cols-2">
        {options.map((option) => (
          <label
            key={option}
            className="flex cursor-pointer items-center gap-3 text-base text-zinc-800"
          >
            <input
              type="checkbox"
              checked={selected.includes(option)}
              onChange={() => toggle(option)}
              className="h-5 w-5 rounded border-zinc-400 accent-zinc-950"
            />
            {option}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function SellerCustomerQuestionnairePage() {
  const router = useRouter();
  const [form, setForm] = useState<FormData>(emptyForm);
  const [view, setView] = useState<"form" | "confirm" | "pin">("form");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [pin, setPin] = useState("");
  const [pinPurpose, setPinPurpose] = useState<"saved" | "cancelled">("saved");
  const [lookupMessage, setLookupMessage] = useState("");
  const [loyaltyInfo, setLoyaltyInfo] = useState<LoyaltyInfo | null>(null);
  const [successMessage, setSuccessMessage] = useState("");
  const [surnameCandidates, setSurnameCandidates] = useState<CustomerCandidate[]>([]);
  const [surnameLookupLoading, setSurnameLookupLoading] = useState(false);
  const [surnameLookupError, setSurnameLookupError] = useState("");
  const skipNextPhoneLookup = useRef<string | null>(null);

  useEffect(() => {
    const blockBack = () =>
      window.history.pushState(null, "", window.location.href);
    window.history.pushState(null, "", window.location.href);
    window.addEventListener("popstate", blockBack);
    return () => window.removeEventListener("popstate", blockBack);
  }, []);

  useEffect(() => {
    if (!/^7\d{10}$/.test(form.phone)) {
      setLookupMessage("");
      setLoyaltyInfo(null);
      return;
    }

    if (skipNextPhoneLookup.current === form.phone) {
      skipNextPhoneLookup.current = null;
      return;
    }

    let cancelled = false;
    const timeout = window.setTimeout(async () => {
      try {
        const response = await apiClient.post(
          "/api/seller/customer-questionnaire/lookup",
          { phone: form.phone },
        );
        if (cancelled) return;
        if (!response.data.found) {
          setLoyaltyInfo(null);
          setLookupMessage(
            "Профиль по этому номеру не найден — будет создан новый покупатель.",
          );
          return;
        }
        const { full_name, ...customer } = response.data.customer;
        setForm((previous) => ({
          ...previous,
          ...customer,
          ...splitFullName(full_name || ""),
          phone: previous.phone,
        }));
        setLoyaltyInfo(response.data.loyalty || null);
        setLookupMessage(
          "Данные покупателя загружены из платформы. Дополните анкету и нажмите «Согласен».",
        );
      } catch {
        if (!cancelled) {
          setLoyaltyInfo(null);
          setLookupMessage(
            "Не удалось загрузить профиль. Анкету можно заполнить вручную.",
          );
        }
      }
    }, 450);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [form.phone]);

  useEffect(() => {
    const lastName = form.last_name.trim();
    // A selected profile already has an exact phone number, so there is no
    // need to leave a namesake list open underneath the loaded questionnaire.
    if (lastName.length < 2 || /^7\d{10}$/.test(form.phone)) {
      setSurnameCandidates([]);
      setSurnameLookupError("");
      setSurnameLookupLoading(false);
      return;
    }

    let cancelled = false;
    const timeout = window.setTimeout(async () => {
      setSurnameLookupLoading(true);
      setSurnameLookupError("");
      try {
        const response = await apiClient.post(
          "/api/seller/customer-questionnaire/lookup-by-last-name",
          { last_name: lastName },
        );
        if (!cancelled) setSurnameCandidates(response.data.customers || []);
      } catch {
        if (!cancelled) {
          setSurnameCandidates([]);
          setSurnameLookupError("Не удалось выполнить поиск по фамилии.");
        }
      } finally {
        if (!cancelled) setSurnameLookupLoading(false);
      }
    }, 350);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [form.last_name, form.phone]);

  const set = <K extends keyof FormData>(key: K, value: FormData[K]) => {
    setSuccessMessage("");
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const selectCustomerBySurname = async (customerId: string) => {
    setSaving(true);
    setError("");
    setSurnameLookupError("");
    try {
      const response = await apiClient.post(
        "/api/seller/customer-questionnaire/lookup-by-id",
        { customer_id: customerId },
      );
      if (!response.data.found) {
        setSurnameLookupError("Профиль не найден. Выполните поиск ещё раз.");
        return;
      }
      const { full_name, ...customer } = response.data.customer;
      // The exact profile has already been loaded, so do not immediately make
      // an identical phone lookup once this state update reaches the effect.
      skipNextPhoneLookup.current = customer.phone;
      setForm((previous) => ({
        ...previous,
        ...customer,
        ...splitFullName(full_name || ""),
      }));
      setLoyaltyInfo(response.data.loyalty || null);
      setSurnameCandidates([]);
      setLookupMessage(
        "Данные покупателя загружены из платформы. Дополните анкету и нажмите «Согласен».",
      );
    } catch {
      setSurnameLookupError("Не удалось загрузить профиль покупателя.");
    } finally {
      setSaving(false);
    }
  };
  const returnToPlatform = () => router.replace("/profile/sellers");
  const payload = (confirm_existing: boolean) => ({
    full_name: [form.last_name, form.first_name, form.middle_name].map((part) => part.trim()).filter(Boolean).join(" "),
    birth_date: form.birth_date || null,
    phone: form.phone,
    city: form.city.trim() || null,
    discovery_channels: form.discovery_channels,
    discovery_other: form.discovery_other.trim() || null,
    purchase_for: form.purchase_for,
    contact_channels: form.contact_channels,
    glame_values: form.glame_values,
    confirm_existing,
  });

  const startSave = async (event: FormEvent) => {
    event.preventDefault();
    if (!/^7\d{10}$/.test(form.phone)) {
      setError("Введите все 10 цифр номера после +7.");
      return;
    }
    if (!form.last_name.trim() || !form.first_name.trim()) {
      setError("Введите фамилию и имя покупателя.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const preview = await apiClient.post(
        "/api/seller/customer-questionnaire/preview",
        payload(false),
      );
      if (preview.data.requires_confirmation) setView("confirm");
      else await save(false);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          "Не удалось проверить номер. Повторите попытку.",
      );
    } finally {
      setSaving(false);
    }
  };

  const save = async (confirmExisting: boolean) => {
    setSaving(true);
    setError("");
    try {
      const response = await apiClient.post(
        "/api/seller/customer-questionnaire/submit",
        payload(confirmExisting),
      );
      // Keep kiosk mode on the questionnaire after a successful submission so
      // the seller can register the next customer without exposing the platform.
      setForm(emptyForm);
      setLookupMessage("");
      setLoyaltyInfo(null);
      const ready = response.data?.platform_ready;
      setSuccessMessage(
        ready?.one_c && ready?.request_picker && ready?.crm
          ? "Анкета сохранена: покупатель создан в 1С и доступен для заявок и CRM. Можно заполнить новую."
          : "Анкета сохранена. Можно заполнить новую.",
      );
      setView("form");
    } catch (err: any) {
      if (err?.response?.status === 409) setView("confirm");
      else
        setError(err?.response?.data?.detail || "Не удалось сохранить анкету.");
    } finally {
      setSaving(false);
    }
  };

  const unlock = (event: FormEvent) => {
    event.preventDefault();
    if (pin === "0107") returnToPlatform();
    else setError("Неверный код продавца");
  };

  const requestCancel = () => {
    setError("");
    setSuccessMessage("");
    setPin("");
    setPinPurpose("cancelled");
    setView("pin");
  };

  if (view === "pin")
    return (
      <main className="min-h-screen bg-[#f8f7f4] px-5 py-10 text-zinc-950">
        <section className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-xl flex-col items-center justify-center text-center">
          <img
            src="/brand/glame-logo-black.png"
            alt="GLAME"
            className="mb-8 h-auto w-52"
          />
          <form onSubmit={unlock} className="w-full">
            <h1 className="text-3xl font-semibold">
              {pinPurpose === "saved" ? "Данные сохранены" : "Анкета отменена"}
            </h1>
            <p className="mt-3 text-zinc-600">
              Введите код продавца, чтобы вернуться к платформе.
            </p>
            <input
              autoFocus
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={4}
              value={pin}
              onChange={(e) => {
                setPin(e.target.value.replace(/\D/g, ""));
                setError("");
              }}
              className="mt-8 w-full rounded-sm border border-zinc-400 bg-white px-5 py-4 text-center text-3xl tracking-[0.6em] outline-none focus:border-zinc-950"
              aria-label="Код продавца"
            />
            {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
            <button className="mt-5 w-full rounded-sm bg-zinc-950 px-6 py-4 text-lg font-semibold text-white">
              Войти
            </button>
          </form>
        </section>
      </main>
    );

  return (
    <main className="min-h-screen bg-[#f8f7f4] px-4 py-7 sm:px-8 sm:py-10">
      <form noValidate onSubmit={startSave} className="mx-auto max-w-3xl">
        <header className="border-b-2 border-zinc-800 pb-6 text-center">
          <img
            src="/brand/glame-logo-black.png"
            alt="GLAME"
            className="mx-auto h-auto w-52"
          />
          <h1 className="mt-3 text-2xl font-semibold tracking-wide">
            АНКЕТА ПОКУПАТЕЛЯ
          </h1>
        </header>
        <div className="space-y-7 py-8">
          <div className="grid gap-5 sm:grid-cols-2">
            <label>
              Фамилия *
              <input
                required
                value={form.last_name}
                onChange={(e) => set("last_name", e.target.value)}
                className="mt-2 w-full border-0 border-b border-zinc-600 bg-transparent px-0 py-2 text-lg outline-none focus:border-zinc-950"
              />
              {(surnameLookupLoading || surnameLookupError || surnameCandidates.length > 0) && (
                <div className="relative z-10">
                  <div className="absolute left-0 right-0 top-1 rounded-sm border border-zinc-300 bg-white p-2 shadow-lg">
                    {surnameLookupLoading && (
                      <p className="px-3 py-2 text-sm text-zinc-600">Ищем покупателя…</p>
                    )}
                    {surnameLookupError && (
                      <p className="px-3 py-2 text-sm text-red-700">{surnameLookupError}</p>
                    )}
                    {!surnameLookupLoading && !surnameLookupError && surnameCandidates.length > 0 && (
                      <>
                        <p className="px-3 pb-1 pt-2 text-xs text-zinc-500">
                          Выберите покупателя — анкета заполнится его данными
                        </p>
                        {surnameCandidates.map((customer) => (
                          <button
                            key={customer.id}
                            type="button"
                            onClick={() => selectCustomerBySurname(customer.id)}
                            disabled={saving}
                            className="flex w-full items-center justify-between gap-3 rounded-sm px-3 py-2 text-left hover:bg-zinc-100 disabled:cursor-wait"
                          >
                            <span className="font-medium text-zinc-900">{customer.full_name}</span>
                            <span className="shrink-0 text-sm text-zinc-600">
                              {customer.phone_masked}{customer.city ? ` · ${customer.city}` : ""}
                            </span>
                          </button>
                        ))}
                      </>
                    )}
                    {!surnameLookupLoading && !surnameLookupError && surnameCandidates.length === 0 && form.last_name.trim().length >= 2 && (
                      <p className="px-3 py-2 text-sm text-zinc-600">Совпадений в базе не найдено.</p>
                    )}
                  </div>
                </div>
              )}
            </label>
            <label>
              Имя *
              <input
                required
                value={form.first_name}
                onChange={(e) => set("first_name", e.target.value)}
                className="mt-2 w-full border-0 border-b border-zinc-600 bg-transparent px-0 py-2 text-lg outline-none focus:border-zinc-950"
              />
            </label>
            <label className="sm:col-span-2">
              Отчество
              <input
                value={form.middle_name}
                onChange={(e) => set("middle_name", e.target.value)}
                className="mt-2 w-full border-0 border-b border-zinc-600 bg-transparent px-0 py-2 text-lg outline-none focus:border-zinc-950"
              />
            </label>
            <label>
              Дата рождения
              <input
                type="date"
                value={form.birth_date}
                onChange={(e) => set("birth_date", e.target.value)}
                className="mt-2 w-full border-0 border-b border-zinc-600 bg-transparent px-0 py-2 text-lg outline-none focus:border-zinc-950"
              />
            </label>
            <label>
              Номер телефона
              <input
                required
                type="tel"
                inputMode="numeric"
                autoComplete="tel-national"
                value={formatPhoneInput(form.phone)}
                onChange={(e) => set("phone", phoneFromInput(e.target.value))}
                aria-label="Номер телефона с кодом +7"
                className="mt-2 w-full border-0 border-b border-zinc-600 bg-transparent px-0 py-2 text-lg outline-none focus:border-zinc-950"
              />
            </label>
            <label className="sm:col-span-2">
              Город проживания
              <input
                value={form.city}
                onChange={(e) => set("city", e.target.value)}
                className="mt-2 w-full border-0 border-b border-zinc-600 bg-transparent px-0 py-2 text-lg outline-none focus:border-zinc-950"
              />
            </label>
          </div>
          {lookupMessage && (
            <p
              role="status"
              className="rounded-sm border border-zinc-300 bg-white/70 px-4 py-3 text-sm text-zinc-700"
            >
              {lookupMessage}
            </p>
          )}
          {successMessage && (
            <p
              role="status"
              className="rounded-sm border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"
            >
              {successMessage}
            </p>
          )}
          <CheckGroup
            label="1. Как Вы узнали о GLAME?"
            options={discovery}
            selected={form.discovery_channels}
            onChange={(value) => set("discovery_channels", value)}
          />
          <label className="block text-base text-zinc-800">
            Другое
            <input
              value={form.discovery_other}
              onChange={(e) => set("discovery_other", e.target.value)}
              className="ml-3 w-[calc(100%-5rem)] border-0 border-b border-zinc-500 bg-transparent px-1 py-1 outline-none focus:border-zinc-950"
            />
          </label>
          <CheckGroup
            label="2. Для кого чаще выбираете украшения?"
            options={purchaseFor}
            selected={form.purchase_for}
            onChange={(value) => set("purchase_for", value)}
          />
          <CheckGroup
            label="3. Где Вам удобно получать новости GLAME?"
            options={contacts}
            selected={form.contact_channels}
            onChange={(value) => set("contact_channels", value)}
          />
          <CheckGroup
            label="4. Что для Вас важно в GLAME?"
            options={values}
            selected={form.glame_values}
            onChange={(value) => set("glame_values", value)}
          />
          <div className="border border-zinc-400 p-5 text-center">
            <div className="font-semibold">
              ПРОГРАММА ЛОЯЛЬНОСТИ GLAME — «КЛУБ СТИЛЬНЫХ»
            </div>
            {loyaltyInfo ? (
              <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                <p>
                  Уровень: <strong>{loyaltyInfo.level}</strong>
                  {" · "}{loyaltyInfo.bonus_percent}% начисления
                </p>
                <p>
                  Бонусный баланс: <strong>{loyaltyInfo.points.toLocaleString("ru-RU")}</strong> баллов
                </p>
                {loyaltyInfo.discount_card_number && (
                  <p className="sm:col-span-2 text-zinc-600">
                    Дисконтная карта: {loyaltyInfo.discount_card_number}
                  </p>
                )}
              </div>
            ) : (
              <p className="mt-2 text-sm text-zinc-600">
                Бонусная программа для клиентов GLAME. Дисконтная карта будет
                создана автоматически.
              </p>
            )}
          </div>
          <p className="text-xs leading-5 text-zinc-600">
            Нажимая «Согласен», покупатель соглашается на обработку персональных
            данных. При выборе канала связи — на получение новостей и
            предложений GLAME.
          </p>
          {error && (
            <p className="rounded-sm bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </p>
          )}
        </div>
        <footer className="sticky bottom-0 -mx-4 flex gap-3 border-t border-zinc-200 bg-[#f8f7f4]/95 px-4 py-4 backdrop-blur sm:-mx-8 sm:px-8">
          <button
            type="button"
            onClick={requestCancel}
            disabled={saving}
            className="flex-1 rounded-sm border border-zinc-600 px-5 py-4 text-lg font-semibold"
          >
            Отмена
          </button>
          <button
            disabled={saving}
            className="flex-1 rounded-sm bg-zinc-950 px-5 py-4 text-lg font-semibold text-white"
          >
            {saving ? "Проверяем…" : "Согласен"}
          </button>
        </footer>
      </form>
      {view === "confirm" && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/50 px-5"
        >
          <div className="w-full max-w-md rounded-sm bg-white p-6 shadow-xl">
            <h2 className="text-xl font-semibold">Номер уже есть в базе</h2>
            <p className="mt-3 leading-6 text-zinc-600">
              Сохранить новые данные покупателя и обновить их в 1С?
            </p>
            {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
            <div className="mt-7 flex gap-3">
              <button
                type="button"
                onClick={() => {
                  setError("");
                  setView("form");
                }}
                disabled={saving}
                className="flex-1 rounded-sm border border-zinc-500 px-4 py-3 font-semibold"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={() => save(true)}
                disabled={saving}
                className="flex-1 rounded-sm bg-zinc-950 px-4 py-3 font-semibold text-white"
              >
                {saving ? "Сохраняем…" : "Сохранить"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
