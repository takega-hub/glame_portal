"use client";

export type InventoryPeriodPreset = "days" | "week" | "month" | "quarter" | "year" | "custom";

export function PeriodSelect({
  value,
  onChange,
  days,
  onDaysChange,
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
}: {
  value: InventoryPeriodPreset;
  onChange: (value: InventoryPeriodPreset) => void;
  days: number;
  onDaysChange: (days: number) => void;
  startDate: string;
  endDate: string;
  onStartDateChange: (value: string) => void;
  onEndDateChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-col md:flex-row gap-2 md:items-end">
      <div className="w-full md:w-56">
        <label className="text-sm font-medium text-gray-700 mb-1 block">Период</label>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value as InventoryPeriodPreset)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm bg-white"
        >
          <option value="week">Неделя</option>
          <option value="month">Месяц</option>
          <option value="quarter">Квартал</option>
          <option value="year">Год</option>
          <option value="custom">Индивидуальный</option>
          <option value="days">Дней</option>
        </select>
      </div>

      {value === "days" && (
        <div className="w-full md:w-40">
          <label className="text-sm font-medium text-gray-700 mb-1 block">Дней</label>
          <input
            type="number"
            min={1}
            max={365}
            value={days}
            onChange={(e) => onDaysChange(parseInt(e.target.value || "1", 10))}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
          />
        </div>
      )}

      {value === "custom" && (
        <>
          <div className="w-full md:w-44">
            <label className="text-sm font-medium text-gray-700 mb-1 block">С</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => onStartDateChange(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            />
          </div>
          <div className="w-full md:w-44">
            <label className="text-sm font-medium text-gray-700 mb-1 block">По</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => onEndDateChange(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            />
          </div>
        </>
      )}
    </div>
  );
}

