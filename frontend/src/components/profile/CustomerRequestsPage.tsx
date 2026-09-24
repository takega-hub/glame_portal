"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { customerRequests, type CustomerRequestDto } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";

const TYPES: Record<string, string> = {
  WAITING_ITEM: "Ожидание изделия",
  WAITING_SIZE: "Ожидание размера",
  WAITING_BRAND: "Ожидание бренда",
  CUSTOM_ORDER: "Индивидуальный заказ",
  REPAIR_CUSTOMER: "Ремонт клиента",
  REPAIR_STORE_STOCK: "Ремонт товара магазина",
  EXCHANGE: "Обмен",
  RETURN: "Возврат",
  SERVICE_CLAIM: "Сервисное обращение",
};
const STATUS: Record<string, string> = {
  WAITING: "В ожидании",
  ORDERED: "Заказан",
  ARRIVED_STORE: "Поступил",
  IN_PROGRESS: "В работе",
  NEW: "Новое",
  UNDER_REVIEW: "На проверке",
  DECISION_READY: "Решение готово",
  IN_REPAIR: "В ремонте",
  READY: "Готово",
  CUSTOMER_NOTIFIED: "Клиент уведомлён",
  PURCHASED: "Купили",
  REFUSED: "Отказ",
  COMPLETED: "Завершено",
  DELIVERED_CLOSED: "Выдано / закрыто",
};
type CustomerRequestDetail = CustomerRequestDto & {
  audit: Array<{
    id: string;
    action: string;
    old_status?: string | null;
    new_status?: string | null;
    comment?: string | null;
    created_at?: string | null;
  }>;
};

function label(map: Record<string, string>, value?: string | null) {
  return map[value || ""] || value || "—";
}
function date(value?: string | null) {
  return value ? new Date(value).toLocaleDateString("ru-RU") : "—";
}
function statusOptions(type: string) {
  if (
    ["WAITING_ITEM", "WAITING_SIZE", "WAITING_BRAND", "CUSTOM_ORDER"].includes(
      type,
    )
  )
    return [
      "WAITING",
      "ORDERED",
      "ARRIVED_STORE",
      "IN_PROGRESS",
      "PURCHASED",
      "REFUSED",
    ];
  if (["EXCHANGE", "RETURN", "SERVICE_CLAIM"].includes(type))
    return [
      "NEW",
      "IN_PROGRESS",
      "UNDER_REVIEW",
      "DECISION_READY",
      "COMPLETED",
    ];
  return type === "REPAIR_CUSTOMER"
    ? [
        "NEW",
        "IN_PROGRESS",
        "IN_REPAIR",
        "READY",
        "CUSTOMER_NOTIFIED",
        "DELIVERED_CLOSED",
      ]
    : ["NEW", "IN_PROGRESS", "IN_REPAIR", "READY", "DELIVERED_CLOSED"];
}

export default function CustomerRequestsPage() {
  const { user } = useAuth();
  const canEditRequestDetails = (user?.role || "").toLowerCase() === "admin";
  const [items, setItems] = useState<CustomerRequestDto[]>([]);
  const [summary, setSummary] = useState({
    open: 0,
    overdue: 0,
    by_type: {} as Record<string, number>,
  });
  const [qualityAlerts, setQualityAlerts] = useState<
    Array<{ sku_or_brand: string; reason: string; count: number }>
  >([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const [clientSearch, setClientSearch] = useState("");
  const [clients, setClients] = useState<
    Array<{
      id: string;
      name: string;
      phone?: string | null;
      city?: string | null;
    }>
  >([]);
  const [selected, setSelected] = useState<CustomerRequestDetail | null>(null);
  const [newPhotos, setNewPhotos] = useState<File[]>([]);
  const [detailPhotos, setDetailPhotos] = useState<File[]>([]);
  const [certificateAmount, setCertificateAmount] = useState("");
  const [certificateResult, setCertificateResult] = useState<{
    number: string;
    amount_rub: number;
    expires_at?: string | null;
    task_id: string;
  } | null>(null);
  const [issuingCertificate, setIssuingCertificate] = useState(false);
  const [form, setForm] = useState({
    client_id: "",
    request_type: "WAITING_ITEM",
    product_name: "",
    sku: "",
    size: "",
    physical_store: "CENTRUM",
    original_comment: "",
    next_action: "Проверить запрос и связаться с клиентом",
    next_action_at: "",
  });
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, dashboard, analytics] = await Promise.all([
        customerRequests.list(filter ? { request_type: filter } : undefined),
        customerRequests.summary(),
        customerRequests.analytics(),
      ]);
      setItems(list.items);
      setSummary(dashboard);
      setQualityAlerts(analytics.quality_alerts);
      setError("");
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Не удалось загрузить обращения");
    } finally {
      setLoading(false);
    }
  }, [filter]);
  useEffect(() => {
    load();
  }, [load]);
  const grouped = useMemo(() => items.filter((x) => !x.closed_at), [items]);
  useEffect(() => {
    const timer = window.setTimeout(async () => {
      if (clientSearch.trim().length < 2) return setClients([]);
      try {
        setClients((await customerRequests.clients(clientSearch)).items);
      } catch {
        setClients([]);
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [clientSearch]);
  function addPhotos(
    files: FileList | null,
    current: File[],
    update: (photos: File[]) => void,
  ) {
    if (!files) return;
    const available = 5 - current.length;
    if (available <= 0) {
      setError("К обращению можно прикрепить не более 5 фотографий");
      return;
    }
    const selectedFiles = Array.from(files)
      .filter(
        (file) =>
          file.type === "image/jpeg" ||
          file.type === "image/png" ||
          file.type === "image/webp",
      )
      .slice(0, available);
    if (selectedFiles.length !== files.length)
      setError("Поддерживаются JPEG, PNG и WebP; максимум 5 фотографий");
    update([...current, ...selectedFiles]);
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      const created = await customerRequests.create({
        ...form,
        client_id: form.client_id || null,
        next_action_at: form.next_action_at || null,
      });
      if (newPhotos.length)
        await customerRequests.uploadPhotos(created.id, newPhotos);
      setAdding(false);
      setNewPhotos([]);
      setForm({
        ...form,
        client_id: "",
        product_name: "",
        sku: "",
        size: "",
        original_comment: "",
        next_action_at: "",
      });
      setClientSearch("");
      await load();
    } catch (e: any) {
      setError(
        e?.response?.data?.detail ||
          "Не удалось создать обращение или прикрепить фотографии",
      );
    }
  }
  async function changeStatus(item: CustomerRequestDto, status: string) {
    try {
      await customerRequests.updateStatus(item.id, {
        status,
        next_action: item.next_action,
      });
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Не удалось обновить статус");
    }
  }
  async function openDetails(id: string) {
    try {
      setSelected(await customerRequests.get(id));
    } catch {
      setError("Не удалось загрузить историю обращения");
    }
  }
  async function saveDetails() {
    if (!selected) return;
    try {
      let updated = await customerRequests.update(selected.id, {
        next_action: selected.next_action,
        next_action_at: selected.next_action_at,
        original_comment: selected.original_comment,
        priority: selected.priority,
        ...(canEditRequestDetails
          ? {
              product_name: selected.product_name,
              sku: selected.sku,
              size: selected.size,
              brand: selected.brand,
              physical_store: selected.physical_store,
            }
          : {}),
      });
      if (detailPhotos.length)
        updated = await customerRequests.uploadPhotos(
          selected.id,
          detailPhotos,
        );
      setDetailPhotos([]);
      setSelected({ ...selected, ...updated });
      await load();
    } catch (e: any) {
      setError(
        e?.response?.data?.detail ||
          "Не удалось сохранить изменения или прикрепить фотографии",
      );
    }
  }
  async function issueCertificate() {
    if (!selected) return;
    const amount = Number(certificateAmount);
    if (!Number.isInteger(amount) || amount <= 0) {
      setError("Укажите сумму сертификата в целых рублях");
      return;
    }
    setIssuingCertificate(true);
    try {
      const result = await customerRequests.issueCompensationCertificate(
        selected.id,
        {
          amount_rub: amount,
        },
      );
      setCertificateResult({
        number: result.certificate.number,
        amount_rub: result.certificate.amount_rub,
        expires_at: result.certificate.expires_at,
        task_id: result.crm_task_id,
      });
      setCertificateAmount("");
      await openDetails(selected.id);
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Не удалось выпустить сертификат");
    } finally {
      setIssuingCertificate(false);
    }
  }
  async function control() {
    try {
      const result = await customerRequests.runControl();
      await load();
      setError(
        result.tasks_created
          ? `Создано задач: ${result.tasks_created}${result.arrivals_matched ? `; найдено поступлений: ${result.arrivals_matched}` : ""}`
          : "Все сроки и поступления уже находятся под контролем.",
      );
    } catch {
      setError("Не удалось запустить контроль сроков");
    }
  }
  return (
    <main className="mx-auto max-w-7xl p-4 md:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-[#a16c44]">AI-МОДУЛЬ GLAME</p>
          <h1 className="text-3xl font-semibold text-[#30251e]">
            Запросы клиентов и сервис
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-[#70645b]">
            Ожидания, индивидуальные заказы, ремонты, обмены и возвраты — всё,
            что GLAME обещал клиенту.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={control}
            className="rounded-xl border border-[#d9cdc2] px-4 py-2.5 text-sm font-semibold"
          >
            Проверить сроки
          </button>
          <button
            onClick={() => setAdding(!adding)}
            className="rounded-xl bg-[#33261f] px-4 py-2.5 text-sm font-semibold text-white"
          >
            + Новое обращение
          </button>
        </div>
      </div>
      <section className="mt-6 grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-[#eadfd5] bg-[#fffdfa] p-5">
          <p className="text-sm text-[#75665a]">Открытые обязательства</p>
          <b className="mt-1 block text-3xl">{summary.open}</b>
        </div>
        <div className="rounded-2xl border border-rose-100 bg-rose-50 p-5">
          <p className="text-sm text-rose-700">Требуют контроля</p>
          <b className="mt-1 block text-3xl text-rose-800">{summary.overdue}</b>
        </div>
        <div className="rounded-2xl border border-[#eadfd5] bg-[#fffdfa] p-5">
          <p className="text-sm text-[#75665a]">В ожидании изделия / размера</p>
          <b className="mt-1 block text-3xl">
            {(summary.by_type.WAITING_ITEM || 0) +
              (summary.by_type.WAITING_SIZE || 0)}
          </b>
        </div>
      </section>
      {adding && (
        <form
          onSubmit={submit}
          className="mt-6 grid gap-3 rounded-2xl border border-[#eadfd5] bg-[#fffdfa] p-5 md:grid-cols-3"
        >
          <div className="relative">
            <input
              required
              placeholder="Найти клиента по имени или телефону"
              value={clientSearch}
              onChange={(e) => {
                setClientSearch(e.target.value);
                setForm({ ...form, client_id: "" });
              }}
              className="w-full rounded-xl border p-2.5"
            />
            {clients.length > 0 && !form.client_id && (
              <div className="absolute z-10 mt-1 w-full rounded-xl border bg-white shadow-lg">
                {clients.map((x) => (
                  <button
                    type="button"
                    key={x.id}
                    onClick={() => {
                      setForm({ ...form, client_id: x.id });
                      setClientSearch(
                        `${x.name}${x.phone ? ` · ${x.phone}` : ""}`,
                      );
                      setClients([]);
                    }}
                    className="block w-full px-3 py-2 text-left text-sm hover:bg-[#faf5ef]"
                  >
                    {x.name} {x.phone ? `· ${x.phone}` : ""}
                  </button>
                ))}
              </div>
            )}
          </div>
          <select
            value={form.request_type}
            onChange={(e) => setForm({ ...form, request_type: e.target.value })}
            className="rounded-xl border p-2.5"
          >
            {Object.entries(TYPES).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
          <input
            required
            placeholder="Изделие"
            value={form.product_name}
            onChange={(e) => setForm({ ...form, product_name: e.target.value })}
            className="rounded-xl border p-2.5"
          />
          <input
            placeholder="SKU / артикул"
            value={form.sku}
            onChange={(e) => setForm({ ...form, sku: e.target.value })}
            className="rounded-xl border p-2.5"
          />
          <input
            placeholder="Размер"
            value={form.size}
            onChange={(e) => setForm({ ...form, size: e.target.value })}
            className="rounded-xl border p-2.5"
          />
          <input
            type="datetime-local"
            value={form.next_action_at}
            onChange={(e) =>
              setForm({ ...form, next_action_at: e.target.value })
            }
            className="rounded-xl border p-2.5"
            title="Срок контроля"
          />
          <select
            value={form.physical_store}
            onChange={(e) =>
              setForm({ ...form, physical_store: e.target.value })
            }
            className="rounded-xl border p-2.5"
          >
            {["CENTRUM", "YALTA", "MRIYA"].map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
          <textarea
            placeholder="Комментарий клиента и детали обещания"
            value={form.original_comment}
            onChange={(e) =>
              setForm({ ...form, original_comment: e.target.value })
            }
            className="min-h-20 rounded-xl border p-2.5 md:col-span-3"
          />
          <div className="rounded-xl border border-dashed border-[#d9cdc2] p-3 text-sm md:col-span-3">
            <label className="cursor-pointer font-medium text-[#5e412e]">
              Прикрепить фотографии ({newPhotos.length}/5)
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                className="sr-only"
                onChange={(e) => {
                  addPhotos(e.target.files, newPhotos, setNewPhotos);
                  e.currentTarget.value = "";
                }}
              />
            </label>
            {newPhotos.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {newPhotos.map((photo, index) => (
                  <span
                    key={`${photo.name}-${index}`}
                    className="rounded-full bg-[#f5eee8] px-2 py-1 text-xs"
                  >
                    {photo.name}
                    <button
                      type="button"
                      className="ml-2 font-bold"
                      onClick={() =>
                        setNewPhotos(newPhotos.filter((_, i) => i !== index))
                      }
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <p className="mt-1 text-xs text-[#8a7c70]">
              JPEG, PNG или WebP, до 15 МБ каждый.
            </p>
          </div>
          <button
            disabled={!form.client_id}
            className="rounded-xl bg-[#33261f] p-2.5 font-semibold text-white disabled:bg-[#aa9d93] md:col-span-3"
          >
            Сохранить
          </button>
        </form>
      )}
      {qualityAlerts.length > 0 && (
        <section className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4">
          <b className="text-amber-950">Повторяющиеся сервисные проблемы</b>
          {qualityAlerts.map((x) => (
            <p
              key={`${x.sku_or_brand}-${x.reason}`}
              className="mt-1 text-sm text-amber-900"
            >
              {x.sku_or_brand}: {x.count} обращ. · {x.reason}
            </p>
          ))}
        </section>
      )}
      <div className="mt-6 flex flex-wrap gap-2">
        <button
          onClick={() => setFilter("")}
          className={`rounded-full px-3 py-1.5 text-sm ${!filter ? "bg-[#33261f] text-white" : "bg-[#f3eee9]"}`}
        >
          Все
        </button>
        {Object.entries(TYPES).map(([v, l]) => (
          <button
            key={v}
            onClick={() => setFilter(v)}
            className={`rounded-full px-3 py-1.5 text-sm ${filter === v ? "bg-[#33261f] text-white" : "bg-[#f3eee9]"}`}
          >
            {l}
          </button>
        ))}
      </div>
      {error && (
        <p className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700">
          {error}
        </p>
      )}
      <section className="mt-4 overflow-hidden rounded-2xl border border-[#eadfd5] bg-white">
        {loading ? (
          <p className="p-6 text-sm text-[#75665a]">Загружаем обращения…</p>
        ) : grouped.length === 0 ? (
          <p className="p-6 text-sm text-[#75665a]">Открытых обращений нет.</p>
        ) : (
          grouped.map((item) => (
            <article
              key={item.id}
              className="grid gap-3 border-b border-[#f0e9e2] p-5 last:border-0 md:grid-cols-[1fr_auto]"
            >
              <div>
                <div className="flex flex-wrap gap-2">
                  <span className="rounded-full bg-[#f5eee8] px-2 py-1 text-xs font-semibold">
                    {label(TYPES, item.request_type)}
                  </span>
                  <span className="rounded-full bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-800">
                    {label(STATUS, item.status)}
                  </span>
                  {item.priority === "high" && (
                    <span className="text-xs font-semibold text-rose-600">
                      Высокий приоритет
                    </span>
                  )}
                </div>
                <button
                  onClick={() => openDetails(item.id)}
                  className="mt-2 text-left font-semibold text-[#30251e] hover:underline"
                >
                  {item.product_name || "Изделие не указано"}{" "}
                  {item.sku ? `· ${item.sku}` : ""}{" "}
                  {item.size ? `· размер ${item.size}` : ""}
                </button>
                <p className="mt-1 text-sm text-[#70645b]">
                  {item.original_comment || "Без комментария"}
                </p>
                <p className="mt-2 text-sm">
                  <b>Следующее действие:</b>{" "}
                  {item.next_action || "Назначить действие"}{" "}
                  {item.next_action_at ? `до ${date(item.next_action_at)}` : ""}
                </p>
                <p className="mt-1 text-xs text-[#8a7c70]">
                  Точка: {item.physical_store || "—"} → CRM:{" "}
                  {item.crm_store || "—"}
                </p>
              </div>
              <select
                value={item.status}
                onChange={(e) => changeStatus(item, e.target.value)}
                className="h-10 rounded-xl border border-[#d9cdc2] bg-white px-3 text-sm"
              >
                {statusOptions(item.request_type).map((value) => (
                  <option key={value} value={value}>
                    {label(STATUS, value)}
                  </option>
                ))}
              </select>
            </article>
          ))
        )}
      </section>
      {selected && (
        <div
          className="fixed inset-0 z-20 bg-black/30 p-4"
          onClick={() => {
            setSelected(null);
            setDetailPhotos([]);
          }}
        >
          <div
            className="mx-auto mt-16 max-w-xl rounded-2xl bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between">
              <h2 className="text-xl font-semibold">Карточка обращения</h2>
              <button
                onClick={() => {
                  setSelected(null);
                  setDetailPhotos([]);
                }}
              >
                ×
              </button>
            </div>
            <p className="mt-2 text-sm text-[#70645b]">
              {selected.product_name} · {label(TYPES, selected.request_type)}
            </p>
            <div className="mt-4 grid gap-3">
              {canEditRequestDetails && (
                <>
                  <p className="text-sm font-semibold text-[#5e412e]">
                    Данные обращения
                  </p>
                  <input
                    value={selected.product_name || ""}
                    onChange={(e) =>
                      setSelected({ ...selected, product_name: e.target.value })
                    }
                    className="rounded-xl border p-2.5"
                    placeholder="Изделие"
                  />
                  <input
                    value={selected.sku || ""}
                    onChange={(e) =>
                      setSelected({ ...selected, sku: e.target.value })
                    }
                    className="rounded-xl border p-2.5"
                    placeholder="SKU / артикул"
                  />
                  <input
                    value={selected.size || ""}
                    onChange={(e) =>
                      setSelected({ ...selected, size: e.target.value })
                    }
                    className="rounded-xl border p-2.5"
                    placeholder="Размер"
                  />
                  <input
                    value={selected.brand || ""}
                    onChange={(e) =>
                      setSelected({ ...selected, brand: e.target.value })
                    }
                    className="rounded-xl border p-2.5"
                    placeholder="Бренд"
                  />
                  <select
                    value={selected.physical_store || ""}
                    onChange={(e) =>
                      setSelected({
                        ...selected,
                        physical_store: e.target.value,
                      })
                    }
                    className="rounded-xl border p-2.5"
                  >
                    <option value="CENTRUM">CENTRUM</option>
                    <option value="YALTA">YALTA</option>
                    <option value="MRIYA">MRIYA</option>
                  </select>
                </>
              )}
              <textarea
                value={selected.original_comment || ""}
                onChange={(e) =>
                  setSelected({ ...selected, original_comment: e.target.value })
                }
                className="min-h-20 rounded-xl border p-2.5"
                placeholder="Комментарий"
              />
              <input
                value={selected.next_action || ""}
                onChange={(e) =>
                  setSelected({ ...selected, next_action: e.target.value })
                }
                className="rounded-xl border p-2.5"
                placeholder="Следующее действие"
              />
              <input
                type="datetime-local"
                value={
                  selected.next_action_at
                    ? selected.next_action_at.slice(0, 16)
                    : ""
                }
                onChange={(e) =>
                  setSelected({
                    ...selected,
                    next_action_at: e.target.value || null,
                  })
                }
                className="rounded-xl border p-2.5"
              />
              <select
                value={selected.priority}
                onChange={(e) =>
                  setSelected({ ...selected, priority: e.target.value })
                }
                className="rounded-xl border p-2.5"
              >
                <option value="low">Низкий приоритет</option>
                <option value="normal">Обычный приоритет</option>
                <option value="high">Высокий приоритет</option>
              </select>
              {canEditRequestDetails && selected.client_id && (
                <div className="rounded-xl border border-[#d9cdc2] bg-[#fffdfa] p-3">
                  <p className="text-sm font-semibold text-[#5e412e]">
                    Денежная компенсация
                  </p>
                  <p className="mt-1 text-xs text-[#8a7c70]">
                    Выпуск создаст активный электронный сертификат и CRM-задачу
                    для уведомления клиента. Автоматической отправки не будет.
                  </p>
                  <div className="mt-3 flex gap-2">
                    <input
                      type="number"
                      min="1"
                      step="1"
                      value={certificateAmount}
                      onChange={(e) => setCertificateAmount(e.target.value)}
                      className="min-w-0 flex-1 rounded-xl border p-2.5"
                      placeholder="Сумма, ₽"
                    />
                    <button
                      type="button"
                      onClick={issueCertificate}
                      disabled={issuingCertificate}
                      className="rounded-xl bg-[#8a633f] px-3 text-sm font-semibold text-white disabled:opacity-50"
                    >
                      {issuingCertificate ? "Выпускаю…" : "Выпустить"}
                    </button>
                  </div>
                  {certificateResult && (
                    <p className="mt-3 rounded-lg bg-emerald-50 p-2 text-xs text-emerald-900">
                      Сертификат {certificateResult.number} на{" "}
                      {certificateResult.amount_rub.toLocaleString("ru-RU")} ₽
                      выпущен. CRM-задача на уведомление создана.
                    </p>
                  )}
                </div>
              )}
              <div className="rounded-xl border border-dashed border-[#d9cdc2] p-3 text-sm">
                <p className="font-medium text-[#5e412e]">
                  Фотографии (
                  {(selected.photo_urls?.length || 0) + detailPhotos.length}/5)
                </p>
                {selected.photo_urls?.length ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {selected.photo_urls.map((url) => (
                      <a key={url} href={url} target="_blank" rel="noreferrer">
                        <img
                          src={url}
                          alt="Фотография обращения"
                          className="h-16 w-16 rounded-lg border object-cover"
                        />
                      </a>
                    ))}
                  </div>
                ) : null}
                <label className="mt-2 inline-block cursor-pointer font-medium text-[#5e412e]">
                  Добавить фото
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    multiple
                    className="sr-only"
                    onChange={(e) => {
                      addPhotos(e.target.files, detailPhotos, setDetailPhotos);
                      e.currentTarget.value = "";
                    }}
                  />
                </label>
                {detailPhotos.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {detailPhotos.map((photo, index) => (
                      <span
                        key={`${photo.name}-${index}`}
                        className="rounded-full bg-[#f5eee8] px-2 py-1 text-xs"
                      >
                        {photo.name}
                        <button
                          type="button"
                          className="ml-2 font-bold"
                          onClick={() =>
                            setDetailPhotos(
                              detailPhotos.filter((_, i) => i !== index),
                            )
                          }
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <button
                onClick={saveDetails}
                className="rounded-xl bg-[#33261f] p-2.5 font-semibold text-white"
              >
                Сохранить данные
              </button>
            </div>
            <div className="mt-5 space-y-3">
              {selected.audit?.map((x) => (
                <div
                  key={x.id}
                  className="border-l-2 border-[#d8b69b] pl-3 text-sm"
                >
                  <b>{x.action}</b>
                  <p>
                    {x.old_status ? `${label(STATUS, x.old_status)} → ` : ""}
                    {label(STATUS, x.new_status)}
                  </p>
                  {x.comment && <p className="text-[#70645b]">{x.comment}</p>}
                  <time className="text-xs text-[#9a8a7d]">
                    {date(x.created_at)}
                  </time>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
