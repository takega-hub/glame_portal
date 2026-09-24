const CSV_MIME = 'text/csv;charset=utf-8';

function escapeCell(value: unknown): string {
  const text = value == null ? '' : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

export function downloadCsv(filename: string, rows: readonly (readonly unknown[])[]): void {
  const content = `\uFEFF${rows.map((row) => row.map(escapeCell).join(',')).join('\r\n')}`;
  const url = URL.createObjectURL(new Blob([content], { type: CSV_MIME }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function objectRowsToCsvRows(rows: readonly Record<string, unknown>[]): unknown[][] {
  const headers = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ''))];
}
