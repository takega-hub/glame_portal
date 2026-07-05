'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

type CdekSettingsResponse = {
  credentials: {
    base_url: string;
    client_id: string | null;
    client_secret_masked: string | null;
    client_secret_set: boolean;
  };
  settings: Record<string, any>;
  pickup_store_options?: Array<{
    id: string;
    name: string;
    city?: string | null;
    address?: string | null;
    is_active: boolean;
  }>;
};

type CdekOptionsResponse = {
  contract_types: Array<{ value: string; label: string }>;
  measurement_types: Array<{ value: string; label: string }>;
  pricing_modes: Array<{ value: string; label: string; hint?: string }>;
  tariffs: Array<{ code: number; name?: string | null; description?: string | null }>;
};

export default function ShippingAdminPage() {
  const noneValue = '__none__';
  const [cityQuery, setCityQuery] = useState('');
  const [cityResults, setCityResults] = useState<any[]>([]);
  const [cityOpen, setCityOpen] = useState(false);
  const [citySearching, setCitySearching] = useState(false);

  const [officeQuery, setOfficeQuery] = useState('');
  const [officeResults, setOfficeResults] = useState<any[]>([]);
  const [officeOpen, setOfficeOpen] = useState(false);
  const [officeSearching, setOfficeSearching] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<CdekSettingsResponse | null>(null);

  const [displayName, setDisplayName] = useState('СДЭК');
  const [companyName, setCompanyName] = useState('');
  const [companyEmail, setCompanyEmail] = useState('');
  const [companyPhone, setCompanyPhone] = useState('');
  const [packageComment, setPackageComment] = useState('');
  const [contractType, setContractType] = useState('Интернет-магазин');
  const [contractTypeValue, setContractTypeValue] = useState('internet_shop');

  const [tariffPvz, setTariffPvz] = useState('136');
  const [tariffCourier, setTariffCourier] = useState('');
  const [tariffOptions, setTariffOptions] = useState<Array<{ code: number; label: string }>>([]);
  const [senderCityCode, setSenderCityCode] = useState('');
  const [senderCityName, setSenderCityName] = useState('');
  const [senderOfficeCode, setSenderOfficeCode] = useState('');
  const [senderOfficeAddress, setSenderOfficeAddress] = useState('');

  const [dimWeightG, setDimWeightG] = useState('1000');
  const [dimLengthMm, setDimLengthMm] = useState('350');
  const [dimWidthMm, setDimWidthMm] = useState('250');
  const [dimHeightMm, setDimHeightMm] = useState('50');
  const [measurementType, setMeasurementType] = useState<'g_mm' | 'g_cm'>('g_mm');

  const [pricingMode, setPricingMode] = useState('calculator');
  const [markupRub, setMarkupRub] = useState('0');
  const [insuranceEnabled, setInsuranceEnabled] = useState(true);
  const [shipDays, setShipDays] = useState('1');
  const [freeShippingThresholdRub, setFreeShippingThresholdRub] = useState('10000');
  const [disableSubmit, setDisableSubmit] = useState(false);
  const [disabled, setDisabled] = useState(false);
  const [pickupStoreOptions, setPickupStoreOptions] = useState<
    Array<{ id: string; name: string; city?: string | null; address?: string | null; is_active: boolean }>
  >([]);
  const [pickupStoreIds, setPickupStoreIds] = useState<string[]>([]);

  const [options, setOptions] = useState<CdekOptionsResponse | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = (await api.getCdekSettings()) as CdekSettingsResponse;
      setData(res);
      const s = res.settings || {};
      setDisplayName(s.display_name || 'СДЭК');
      setCompanyName(s.company_name || '');
      setCompanyEmail(s.company_email || '');
      setCompanyPhone(s.company_phone || '');
      setPackageComment(s.package_comment || '');
      setContractType(s.contract_type || 'Интернет-магазин');
      setContractTypeValue(s.contract_type === 'Интернет-магазин' ? 'internet_shop' : (s.contract_type || 'internet_shop'));
      setTariffPvz(s.tariff_pvz || '136');
      setTariffCourier(s.tariff_courier || '');
      setSenderCityCode(s.sender_city_code || '');
      setSenderCityName(s.sender_city_name || '');
      setSenderOfficeCode(s.sender_office_code || '');
      setSenderOfficeAddress(s.sender_office_address || '');
      setDimWeightG(String(s.dim_weight_g ?? '1000'));
      setDimLengthMm(String(s.dim_length_mm ?? '350'));
      setDimWidthMm(String(s.dim_width_mm ?? '250'));
      setDimHeightMm(String(s.dim_height_mm ?? '50'));
      setMeasurementType((s.measurement_type || 'g_mm') as any);
      setPricingMode(s.pricing_mode || 'calculator');
      setMarkupRub(String(s.markup_rub ?? '0'));
      setInsuranceEnabled(!!s.insurance_enabled);
      setShipDays(String(s.ship_days ?? '1'));
      setFreeShippingThresholdRub(String(s.free_shipping_threshold_rub ?? '10000'));
      setDisableSubmit(!!s.disable_submit);
      setDisabled(!!s.disabled);
      const options = (res.pickup_store_options || []) as Array<{
        id: string;
        name: string;
        city?: string | null;
        address?: string | null;
        is_active: boolean;
      }>;
      setPickupStoreOptions(options);
      const selectedFromSettings = Array.isArray(s.pickup_store_ids)
        ? s.pickup_store_ids.map((x: any) => String(x))
        : [];
      // Backward-compatible default: if setting wasn't saved yet, select all active.
      setPickupStoreIds(
        selectedFromSettings.length
          ? selectedFromSettings
          : options.map((x) => String(x.id)),
      );
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка загрузки настроек СДЭК');
    } finally {
      setLoading(false);
    }
  };

  const loadOptions = async () => {
    try {
      const res = (await api.getCdekOptions()) as CdekOptionsResponse;
      setOptions(res);
      const tariffs = (res.tariffs || []).map((t) => ({
        code: t.code,
        label: t.name ? `${t.code} — ${t.name}` : String(t.code),
      }));
      setTariffOptions(tariffs);
    } catch {
      setOptions(null);
      setTariffOptions([]);
    }
  };

  useEffect(() => {
    const code = Number(senderCityCode);
    if (!Number.isFinite(code) || code <= 0) {
      setOfficeResults([]);
    }
  }, [senderCityCode]);

  useEffect(() => {
    if (!cityOpen) return;
    const q = (cityQuery || '').trim();
    if (q.length < 2) {
      setCityResults([]);
      return;
    }
    let alive = true;
    const t = setTimeout(async () => {
      setCitySearching(true);
      try {
        const res = await api.searchCdekCities(q, 20);
        if (!alive) return;
        setCityResults(res || []);
      } finally {
        if (alive) setCitySearching(false);
      }
    }, 250);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [cityQuery, cityOpen]);

  useEffect(() => {
    if (!officeOpen) return;
    const code = Number(senderCityCode);
    if (!Number.isFinite(code) || code <= 0) {
      setOfficeResults([]);
      return;
    }
    let alive = true;
    const t = setTimeout(async () => {
      setOfficeSearching(true);
      try {
        const res = await api.searchCdekOffices(code, (officeQuery || '').trim(), 200);
        if (!alive) return;
        setOfficeResults(res || []);
      } finally {
        if (alive) setOfficeSearching(false);
      }
    }, 250);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [officeQuery, officeOpen, senderCityCode]);

  useEffect(() => {
    load();
    loadOptions();
  }, []);

  const onSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.updateCdekSettings({
        display_name: displayName,
        company_name: companyName,
        company_email: companyEmail,
        company_phone: companyPhone,
        package_comment: packageComment,
        contract_type: contractTypeValue,
        tariff_pvz: tariffPvz,
        tariff_courier: tariffCourier.trim() ? tariffCourier.trim() : null,
        sender_city_code: senderCityCode,
        sender_city_name: senderCityName,
        sender_office_code: senderOfficeCode,
        sender_office_address: senderOfficeAddress,
        dim_weight_g: dimWeightG,
        dim_length_mm: dimLengthMm,
        dim_width_mm: dimWidthMm,
        dim_height_mm: dimHeightMm,
        measurement_type: measurementType,
        pricing_mode: pricingMode,
        markup_rub: markupRub,
        insurance_enabled: insuranceEnabled,
        ship_days: shipDays,
        free_shipping_threshold_rub: freeShippingThresholdRub,
        disable_submit: disableSubmit,
        disabled,
        pickup_store_ids: pickupStoreIds,
      });
      await load();
      await loadOptions();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const credentials = data?.credentials;

  return (
    <div className="p-6 space-y-6 bg-white">
      <div>
        <h1 className="text-2xl font-bold text-black">Администрирование доставки</h1>
        <div className="mt-1 text-sm text-gray-700">СДЭК: тарифы, отправитель, габариты, правила бесплатной доставки</div>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-300 bg-red-50 p-4">
          <div className="font-medium text-red-800">Ошибка</div>
          <div className="mt-1 text-sm text-red-700">{error}</div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card className="bg-white border-gray-200">
          <CardHeader>
            <CardTitle className="text-black">Ключи интеграции</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? <div className="text-sm text-gray-700">Загрузка…</div> : null}
            <div className="space-y-3">
              <div>
                <div className="text-xs font-medium text-gray-700 mb-1">Base URL</div>
                <Input value={credentials?.base_url || ''} readOnly className="bg-gray-50" />
              </div>
              <div>
                <div className="text-xs font-medium text-gray-700 mb-1">Client ID (Account)</div>
                <Input value={credentials?.client_id || ''} readOnly className="bg-gray-50" />
              </div>
              <div>
                <div className="text-xs font-medium text-gray-700 mb-1">Client Secret (Secure password)</div>
                <Input value={credentials?.client_secret_masked || (credentials?.client_secret_set ? '***' : '')} readOnly className="bg-gray-50" />
              </div>
              <div className="text-xs text-gray-600">
                Ключи берутся из переменных окружения `CDEK_CLIENT_ID` и `CDEK_CLIENT_SECRET`.
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white border-gray-200">
          <CardHeader>
            <CardTitle className="text-black">Настройки доставки</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div>
                <div className="text-xs font-medium text-gray-700 mb-1">Название в списке</div>
                <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Тариф ПВЗ</div>
                  <Select value={tariffPvz} onValueChange={(v) => setTariffPvz(v)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Выберите тариф" />
                    </SelectTrigger>
                    <SelectContent>
                      {tariffOptions.length ? (
                        tariffOptions.map((t) => (
                          <SelectItem key={t.code} value={String(t.code)}>
                            {t.label}
                          </SelectItem>
                        ))
                      ) : (
                        <SelectItem value={tariffPvz}>{tariffPvz}</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Тариф курьер</div>
                  <Select
                    value={tariffCourier ? tariffCourier : noneValue}
                    onValueChange={(v) => setTariffCourier(v === noneValue ? '' : v)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="(опционально)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={noneValue}>(не задан)</SelectItem>
                      {tariffOptions.map((t) => (
                        <SelectItem key={t.code} value={String(t.code)}>
                          {t.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Город отправителя (code)</div>
                  <Input value={senderCityCode} readOnly placeholder="Выберите город" className="bg-gray-50" />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Город отправителя (название)</div>
                  <div className="relative">
                    <Input
                      value={cityQuery || senderCityName}
                      onChange={(e) => {
                        setCityQuery(e.target.value);
                        setCityOpen(true);
                      }}
                      onFocus={() => setCityOpen(true)}
                      placeholder="Начните вводить: Симферополь"
                    />
                    {cityOpen && (
                      <div className="absolute z-50 mt-1 max-h-80 w-full overflow-auto rounded-md border border-gray-300 bg-white shadow-lg">
                        <div className="px-3 py-2 text-xs text-gray-600 border-b border-gray-200">
                          {citySearching ? 'Поиск…' : cityResults.length ? 'Выберите город' : 'Введите минимум 2 символа'}
                        </div>
                        {cityResults.map((c, idx) => {
                          const title = c.city || c.name || 'Город';
                          const subtitle = [c.country, c.region, c.sub_region].filter(Boolean).join(', ');
                          const code = c.code;
                          return (
                            <button
                              key={`${code}-${idx}`}
                              className="w-full border-b border-gray-100 px-3 py-2 text-left hover:bg-gray-50 focus:bg-gray-50 focus:outline-none"
                              onMouseDown={(e) => e.preventDefault()}
                              onClick={() => {
                                setSenderCityCode(String(code || ''));
                                setSenderCityName(`${title}${subtitle ? ` — ${subtitle}` : ''}`);
                                setCityQuery('');
                                setCityOpen(false);
                                setSenderOfficeCode('');
                                setSenderOfficeAddress('');
                                setOfficeQuery('');
                              }}
                            >
                              <div className="text-sm font-medium text-black">{title}</div>
                              <div className="mt-0.5 text-xs text-gray-600">{subtitle || ''}</div>
                            </button>
                          );
                        })}
                        <div className="flex justify-end border-t border-gray-200 px-3 py-2">
                          <button
                            className="text-xs text-gray-600 hover:text-gray-900"
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={() => {
                              setCityOpen(false);
                              setCityQuery('');
                            }}
                          >
                            Закрыть
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Офис СДЭК (код)</div>
                  <Input value={senderOfficeCode} readOnly placeholder="Выберите офис" className="bg-gray-50" />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Офис СДЭК (адрес)</div>
                  <div className="relative">
                    <Input
                      value={officeQuery || senderOfficeAddress}
                      onChange={(e) => {
                        setOfficeQuery(e.target.value);
                        setOfficeOpen(true);
                      }}
                      onFocus={() => setOfficeOpen(true)}
                      placeholder={senderCityCode ? 'Начните вводить: SMF39 или улица' : 'Сначала выберите город'}
                    />
                    {officeOpen && (
                      <div className="absolute z-50 mt-1 max-h-80 w-full overflow-auto rounded-md border border-gray-300 bg-white shadow-lg">
                        <div className="px-3 py-2 text-xs text-gray-600 border-b border-gray-200">
                          {!senderCityCode
                            ? 'Сначала выберите город'
                            : officeSearching
                              ? 'Поиск…'
                              : officeResults.length
                                ? 'Выберите офис'
                                : 'Нет результатов'}
                        </div>
                        {officeResults.map((p, idx) => {
                          const code = p.code || p.location?.code;
                          const name = p.name || '';
                          const addr = p.location?.address || p.address || '';
                          const title = `${code || ''}${name ? `, ${name}` : ''}`.trim();
                          return (
                            <button
                              key={`${code}-${idx}`}
                              className="w-full border-b border-gray-100 px-3 py-2 text-left hover:bg-gray-50 focus:bg-gray-50 focus:outline-none"
                              onMouseDown={(e) => e.preventDefault()}
                              onClick={() => {
                                setSenderOfficeCode(String(code || ''));
                                setSenderOfficeAddress(addr || title);
                                setOfficeQuery('');
                                setOfficeOpen(false);
                              }}
                            >
                              <div className="text-sm font-medium text-black">{title || 'Офис'}</div>
                              <div className="mt-0.5 text-xs text-gray-600">{addr}</div>
                            </button>
                          );
                        })}
                        <div className="flex justify-end border-t border-gray-200 px-3 py-2">
                          <button
                            className="text-xs text-gray-600 hover:text-gray-900"
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={() => {
                              setOfficeOpen(false);
                              setOfficeQuery('');
                            }}
                          >
                            Закрыть
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-5 gap-3">
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Вес (г)</div>
                  <Input value={dimWeightG} onChange={(e) => setDimWeightG(e.target.value)} />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Длина ({measurementType === 'g_mm' ? 'мм' : 'см'})</div>
                  <Input value={dimLengthMm} onChange={(e) => setDimLengthMm(e.target.value)} />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Ширина ({measurementType === 'g_mm' ? 'мм' : 'см'})</div>
                  <Input value={dimWidthMm} onChange={(e) => setDimWidthMm(e.target.value)} />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Высота ({measurementType === 'g_mm' ? 'мм' : 'см'})</div>
                  <Input value={dimHeightMm} onChange={(e) => setDimHeightMm(e.target.value)} />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Тип измерений</div>
                  <Select value={measurementType} onValueChange={(v) => setMeasurementType(v as any)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Выберите" />
                    </SelectTrigger>
                    <SelectContent>
                      {(options?.measurement_types || [
                        { value: 'g_mm', label: 'г / мм' },
                        { value: 'g_cm', label: 'г / см' },
                      ]).map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Наценка (₽)</div>
                  <Input value={markupRub} onChange={(e) => setMarkupRub(e.target.value)} />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Бесплатная доставка от (₽)</div>
                  <Input value={freeShippingThresholdRub} onChange={(e) => setFreeShippingThresholdRub(e.target.value)} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Дней до отправки</div>
                  <Input value={shipDays} onChange={(e) => setShipDays(e.target.value)} />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Комментарий на упаковке</div>
                  <Input value={packageComment} onChange={(e) => setPackageComment(e.target.value)} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Компания (название)</div>
                  <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Тип договора</div>
                  <Input value={contractType} onChange={(e) => setContractType(e.target.value)} />
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Email компании</div>
                  <Input value={companyEmail} onChange={(e) => setCompanyEmail(e.target.value)} />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Телефон компании</div>
                  <Input value={companyPhone} onChange={(e) => setCompanyPhone(e.target.value)} />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Стоимость</div>
                  <Select value={pricingMode} onValueChange={(v) => setPricingMode(v)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Выберите" />
                    </SelectTrigger>
                    <SelectContent>
                      {(options?.pricing_modes || [
                        { value: 'calculator', label: 'Калькулятор' },
                        { value: 'free', label: 'Бесплатно' },
                        { value: 'fixed', label: 'Фиксированная сумма' },
                      ]).map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <div className="mt-1 text-xs text-gray-600">
                    {pricingMode === 'calculator'
                      ? 'Цена доставки считается по тарифу СДЭК и правилам корзины'
                      : null}
                  </div>
                </div>
                <div className="flex items-center gap-3 pt-6">
                  <input 
                    type="checkbox" 
                    id="insurance" 
                    checked={insuranceEnabled} 
                    onChange={(e) => setInsuranceEnabled(e.target.checked)} 
                    className="h-4 w-4 rounded border-gray-300 text-pink-600 focus:ring-pink-500"
                  />
                  <label htmlFor="insurance" className="text-sm text-gray-700">Учитывать страховку</label>
                </div>
                <div className="flex items-center gap-3 pt-6">
                  <input 
                    type="checkbox" 
                    id="disableSubmit" 
                    checked={disableSubmit} 
                    onChange={(e) => setDisableSubmit(e.target.checked)} 
                    className="h-4 w-4 rounded border-gray-300 text-pink-600 focus:ring-pink-500"
                  />
                  <label htmlFor="disableSubmit" className="text-sm text-gray-700">Не отправлять заказы в СДЭК</label>
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-xs font-medium text-gray-700">Магазины для самовывоза в приложении</div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setPickupStoreIds(pickupStoreOptions.map((x) => String(x.id)))}
                    >
                      Выбрать все
                    </Button>
                    <Button type="button" variant="outline" onClick={() => setPickupStoreIds([])}>
                      Очистить
                    </Button>
                  </div>
                </div>
                <div className="max-h-64 overflow-auto rounded-md border border-gray-200 p-3">
                  {pickupStoreOptions.length === 0 ? (
                    <div className="text-sm text-gray-600">Нет активных магазинов</div>
                  ) : (
                    <div className="space-y-2">
                      {pickupStoreOptions.map((store) => {
                        const checked = pickupStoreIds.includes(String(store.id));
                        const subtitle = [store.city, store.address].filter(Boolean).join(', ');
                        return (
                          <label key={store.id} className="flex items-start gap-2 text-sm text-gray-800">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setPickupStoreIds((prev) =>
                                    prev.includes(String(store.id)) ? prev : [...prev, String(store.id)],
                                  );
                                } else {
                                  setPickupStoreIds((prev) => prev.filter((x) => x !== String(store.id)));
                                }
                              }}
                              className="mt-0.5 h-4 w-4 rounded border-gray-300"
                            />
                            <span>
                              <span className="font-medium text-black">{store.name}</span>
                              {subtitle ? <span className="block text-xs text-gray-600">{subtitle}</span> : null}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
                <div className="mt-1 text-xs text-gray-600">
                  В checkout самовывоза будут доступны только отмеченные магазины.
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-medium text-gray-700 mb-1">Тип договора</div>
                  <Select value={contractTypeValue} onValueChange={(v) => setContractTypeValue(v)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Выберите" />
                    </SelectTrigger>
                    <SelectContent>
                      {(options?.contract_types || [{ value: 'internet_shop', label: 'Интернет-магазин' }]).map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="flex items-center gap-3">
                <input 
                  type="checkbox" 
                  id="disabled" 
                  checked={disabled} 
                  onChange={(e) => setDisabled(e.target.checked)} 
                  className="h-4 w-4 rounded border-gray-300 text-pink-600 focus:ring-pink-500"
                />
                <label htmlFor="disabled" className="text-sm text-gray-700">Отключить доставку</label>
              </div>

              <div className="flex gap-3 pt-2">
                <Button onClick={onSave} disabled={loading || saving}>
                  Сохранить
                </Button>
                <Button variant="outline" onClick={load} disabled={loading || saving}>
                  Обновить
                </Button>
                <Button variant="outline" onClick={loadOptions} disabled={loading || saving}>
                  Обновить списки
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
