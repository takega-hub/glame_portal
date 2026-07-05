'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { communication, GenerationHistoryRecord, GenerateMessageRequest } from '@/lib/api';
import * as XLSX from 'xlsx';

type SortBy = 'started_at' | 'completed_at' | 'status' | 'event_type';

export default function GenerationHistoryPanel() {
  const [items, setItems] = useState<GenerationHistoryRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [eventType, setEventType] = useState<string>('');
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sortBy, setSortBy] = useState<SortBy>('started_at');
  const [desc, setDesc] = useState(true);
  const [limit, setLimit] = useState(20);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const lastParamsRef = useRef<string>('');
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [viewId, setViewId] = useState<string | null>(null);
  const [viewLoading, setViewLoading] = useState(false);
  const [viewMessages, setViewMessages] = useState<any[]>([]);
  const [viewError, setViewError] = useState<string | null>(null);

  const [showSendModal, setShowSendModal] = useState(false);
  const [sendDate, setSendDate] = useState('');
  const [sendBusy, setSendBusy] = useState(false);

  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);
  const [editMsgText, setEditMsgText] = useState('');
  const [regeneratingIds, setRegeneratingIds] = useState<Set<string>>(new Set());

  const handleEditMessage = (msg: any) => {
    setEditingMsgId(msg.client_id);
    setEditMsgText(msg.message);
  };

  const handleSaveMessage = async (msg: any) => {
    if (!viewId || !msg.client_id) return;
    try {
      await communication.updateGenerationMessage(viewId, msg.client_id, { message: editMsgText });
      setViewMessages(prev => prev.map(m => 
        m.client_id === msg.client_id ? { ...m, message: editMsgText } : m
      ));
      setEditingMsgId(null);
      setEditMsgText('');
    } catch (e: any) {
      alert('Ошибка сохранения: ' + (e.message || 'Unknown error'));
    }
  };

  const handleCancelEdit = () => {
    setEditingMsgId(null);
    setEditMsgText('');
  };

  const handleRegenerateMessage = async (msg: any) => {
    if (!viewId || !msg.client_id) return;
    
    setRegeneratingIds(prev => {
        const next = new Set(prev);
        next.add(msg.client_id);
        return next;
    });

    try {
      const record = items.find(i => i.id === viewId);
      if (!record) throw new Error('Generation record not found');
      
      const params = record.params || {};
      
      const request: GenerateMessageRequest = {
        client_id: msg.client_id,
        event: {
          type: record.event_type as any,
          brand: params.brand,
          store: msg.store || msg.event_store || params.store, 
          metadata: params.metadata || {}
        }
      };
      
      const newMsg = await communication.generateMessage(request);
      
      // Save the new message to the generation file
      await communication.updateGenerationMessage(viewId, msg.client_id, { 
        message: newMsg.message,
        cta: newMsg.cta
      });
      
      setViewMessages(prev => prev.map(m => 
        m.client_id === msg.client_id ? { 
            ...m, 
            message: newMsg.message, 
            cta: newMsg.cta,
            reason: newMsg.reason,
            segment: newMsg.segment
        } : m
      ));
      
    } catch (e: any) {
      console.error('Regenerate error:', e);
      alert('Ошибка перегенерации: ' + (e.response?.data?.detail || e.message || 'Unknown error'));
    } finally {
      setRegeneratingIds(prev => {
        const next = new Set(prev);
        next.delete(msg.client_id);
        return next;
      });
    }
  };

  const selectedIds = useMemo(() => Object.keys(selected).filter((k) => selected[k]), [selected]);
  const selectedItems = useMemo(() => items.filter(i => selected[i.id]), [items, selected]);

  const load = async (silent?: boolean) => {
    const params = {
      status: status || undefined,
      event_type: eventType || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      search: search || undefined,
      sort_by: sortBy,
      desc,
      limit,
      offset,
    };
    const key = JSON.stringify(params);
    lastParamsRef.current = key;
    if (!silent) {
      setLoading(true);
      setError(null);
    }
    try {
      const res = await communication.listGenerations(params);
      setItems(res.items || []);
      setTotal(res.total || 0);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Ошибка загрузки истории';
      setError(msg);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [status, eventType, search, dateFrom, dateTo, sortBy, desc, limit, offset]);

  useEffect(() => {
    const t = setInterval(() => load(true), 5000);
    return () => clearInterval(t);
  }, []);

  const toggleSelect = (id: string) => {
    setSelected((s) => ({ ...s, [id]: !s[id] }));
  };

  const exportSelected = async () => {
    if (selectedIds.length === 0) return;
    try {
      const blob = await communication.exportGenerations(selectedIds);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `generations_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось экспортировать';
      setError(msg);
    }
  };

  const openDeleteModal = () => {
    if (selectedIds.length === 0) return;
    setShowDeleteModal(true);
  };

  const confirmDelete = async () => {
    setDeleteBusy(true);
    try {
      const res = await communication.deleteGenerationFiles(selectedIds);
      if (Object.keys(res.failed).length > 0) {
        alert(`Удалено: ${res.deleted.length}. Ошибки: ${Object.entries(res.failed).map(([k,v])=>k+': '+v).join('; ')}`);
      } else {
        alert(`Удалено файлов: ${res.deleted.length}`);
      }
      // Снимаем выбор и обновляем список
      setSelected({});
      await load();
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось удалить файлы';
      alert(msg);
    } finally {
      setDeleteBusy(false);
      setShowDeleteModal(false);
    }
  };

  const openResult = async (id: string) => {
    setViewId(id);
    setViewLoading(true);
    setViewError(null);
    setViewMessages([]);
    try {
      const res = await communication.getGenerationResult(id);
      setViewMessages(res.messages || []);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось загрузить результат';
      setViewError(msg);
    } finally {
      setViewLoading(false);
    }
  };

  const closeResult = () => {
    setViewId(null);
    setViewMessages([]);
    setViewError(null);
  };

  const exportViewToXlsx = () => {
    if (viewMessages.length === 0) {
      alert('Нет данных для экспорта');
      return;
    }
    const data = viewMessages.map((m: any) => ({
      'Номер телефона': m.phone || '',
      'Имя': m.name || '',
      'Пол': m.gender === 'male' ? 'Мужской' : m.gender === 'female' ? 'Женский' : '',
      'Сегмент': m.segment || '',
      'Сообщение': m.message || '',
      'CTA': m.cta || '',
      'Статус': m.status === 'sent' ? 'Отправлено' : 'Сгенерировано',
    }));
    const wb = XLSX.utils.book_new();
    const ws = XLSX.utils.json_to_sheet(data);
    ws['!cols'] = [{ wch: 20 }, { wch: 20 }, { wch: 10 }, { wch: 12 }, { wch: 60 }, { wch: 40 }, { wch: 15 }];
    XLSX.utils.book_append_sheet(wb, ws, 'Сообщения');
    const fileName = `messages_${viewId || 'result'}.xlsx`;
    XLSX.writeFile(wb, fileName);
  };

  const openSendModal = () => {
    setSendDate('');
    setShowSendModal(true);
  };

  const confirmSend = async () => {
    if (!viewId) return;
    setSendBusy(true);
    try {
      let isoDate = undefined;
      if (sendDate) {
        isoDate = new Date(sendDate).toISOString();
      }

      await communication.sendGenerationSms(viewId, { 
        date_send: isoDate,
        periodicity: 'one-time'
      });
      alert('Рассылка успешно запланирована');
      setShowSendModal(false);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Ошибка отправки';
      alert(msg);
    } finally {
      setSendBusy(false);
    }
  };

  const pageCount = Math.ceil(Math.max(total, 1) / Math.max(limit, 1));
  const page = Math.floor(offset / Math.max(limit, 1)) + 1;

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">История генераций</h3>
        <div className="flex items-center gap-2">
          <button onClick={() => load()} className="px-3 py-1.5 bg-gray-100 border border-gray-300 rounded hover:bg-gray-200">Обновить</button>
          <button onClick={exportSelected} disabled={selectedIds.length === 0} className="px-3 py-1.5 bg-green-600 text-white rounded disabled:opacity-50">Экспорт</button>
          <button onClick={openDeleteModal} disabled={selectedIds.length === 0} className="px-3 py-1.5 bg-red-600 text-white rounded disabled:opacity-50">Удалить</button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-6 gap-2 mb-3">
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Поиск" className="p-2 border rounded md:col-span-2" />
        <select value={status || ''} onChange={(e) => setStatus(e.target.value || null)} className="p-2 border rounded">
          <option value="">Статус</option>
          <option value="running">running</option>
          <option value="completed">completed</option>
          <option value="failed">failed</option>
        </select>
        <input value={eventType} onChange={(e) => setEventType(e.target.value)} placeholder="Тип" className="p-2 border rounded" />
        <input type="datetime-local" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="p-2 border rounded" />
        <input type="datetime-local" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="p-2 border rounded" />
      </div>

      <div className="flex items-center gap-2 mb-3">
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortBy)} className="p-2 border rounded">
          <option value="started_at">Сортировать по началу</option>
          <option value="completed_at">Сортировать по завершению</option>
          <option value="status">Сортировать по статусу</option>
          <option value="event_type">Сортировать по типу</option>
        </select>
        <label className="flex items-center gap-1 text-sm text-gray-700">
          <input type="checkbox" checked={desc} onChange={(e) => setDesc(e.target.checked)} />
          Убыв.
        </label>
        <select value={limit} onChange={(e) => { setLimit(parseInt(e.target.value || '20', 10)); setOffset(0); }} className="p-2 border rounded">
          <option value="10">10</option>
          <option value="20">20</option>
          <option value="50">50</option>
          <option value="100">100</option>
        </select>
      </div>

      {error && <div className="mb-3 p-3 bg-red-50 border border-red-200 text-red-700 rounded">{error}</div>}
      {loading ? (
        <div className="py-6 text-center text-gray-500">Загрузка…</div>
      ) : items.length === 0 ? (
        <div className="py-6 text-center text-gray-500">Записей нет</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full border divide-y">
            <thead className="bg-gray-50">
              <tr>
                <th className="p-2 text-left"><input type="checkbox" onChange={(e) => {
                  const v = e.target.checked;
                  const next: Record<string, boolean> = {};
                  items.forEach((it) => next[it.id] = v);
                  setSelected(next);
                }} /></th>
                <th className="p-2 text-left">Статус</th>
                <th className="p-2 text-left">Тип</th>
                <th className="p-2 text-left">Сегмент</th>
                <th className="p-2 text-left">Начало</th>
                <th className="p-2 text-left">Завершение</th>
                <th className="p-2 text-right">Всего</th>
                <th className="p-2 text-right">Обработано</th>
                <th className="p-2 text-right">Успех</th>
                <th className="p-2 text-right">Ошибки</th>
                <th className="p-2 text-left">Файл</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id} className="odd:bg-white even:bg-gray-50 hover:bg-pink-50 cursor-pointer" onClick={() => openResult(it.id)}>
                  <td className="p-2"><input type="checkbox" checked={!!selected[it.id]} onChange={() => toggleSelect(it.id)} /></td>
                  <td className="p-2">{it.status}</td>
                  <td className="p-2">{it.event_type}</td>
                  <td className="p-2">{it.segment || '-'}</td>
                  <td className="p-2">{new Date(it.started_at).toLocaleString('ru-RU')}</td>
                  <td className="p-2">{it.completed_at ? new Date(it.completed_at).toLocaleString('ru-RU') : '-'}</td>
                  <td className="p-2 text-right">{it.total}</td>
                  <td className="p-2 text-right">{it.processed}</td>
                  <td className="p-2 text-right">{it.success}</td>
                  <td className="p-2 text-right">{it.errors}</td>
                  <td className="p-2">{it.saved_file ? it.saved_file.split('/').pop() : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center justify-between mt-3">
        <div className="text-sm text-gray-600">Всего: {total}</div>
        <div className="flex items-center gap-2">
          <button disabled={page <= 1} onClick={() => setOffset(Math.max(0, offset - limit))} className="px-3 py-1.5 bg-gray-100 border border-gray-300 rounded disabled:opacity-50">Назад</button>
          <div className="text-sm">{page} / {pageCount || 1}</div>
          <button disabled={page >= pageCount} onClick={() => setOffset(offset + limit)} className="px-3 py-1.5 bg-gray-100 border border-gray-300 rounded disabled:opacity-50">Вперед</button>
        </div>
      </div>

      {showDeleteModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded shadow-lg p-6 w-full max-w-lg">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-lg font-semibold">Подтверждение удаления</h4>
              <button onClick={() => setShowDeleteModal(false)} className="text-gray-500 hover:text-gray-700">✕</button>
            </div>
            <p className="text-sm text-gray-700 mb-2">Будут удалены файлы результатов у выбранных генераций:</p>
            <div className="max-h-48 overflow-y-auto border rounded p-2 text-sm mb-4">
              {selectedItems.map((it) => (
                <div key={it.id} className="flex justify-between py-1 border-b last:border-b-0">
                  <span className="text-gray-700">{it.id}</span>
                  <span className="text-gray-500">{it.saved_file ? it.saved_file.split('/').pop() : '(нет файла)'}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-end gap-2">
              <button onClick={() => setShowDeleteModal(false)} className="px-3 py-1.5 bg-gray-100 border border-gray-300 rounded">Отмена</button>
              <button onClick={confirmDelete} disabled={deleteBusy} className="px-3 py-1.5 bg-red-600 text-white rounded disabled:opacity-50">{deleteBusy ? 'Удаление…' : 'Удалить'}</button>
            </div>
          </div>
        </div>
      )}

      {viewId && (
        <div className="fixed inset-0 bg-black/30 z-40" onClick={closeResult} />
      )}
      {viewId && (
        <div className="fixed right-0 top-0 bottom-0 w-full max-w-2xl bg-white shadow-2xl z-50 flex flex-col">
          <div className="p-4 border-b flex items-center justify-between">
            <h4 className="text-lg font-semibold">Результаты генерации</h4>
            <div className="flex items-center gap-2">
              <button onClick={openSendModal} className="px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700">Отправить</button>
              <button onClick={exportViewToXlsx} className="px-3 py-1.5 bg-green-600 text-white rounded hover:bg-green-700">Экспорт</button>
              <button onClick={closeResult} className="px-3 py-1.5 bg-gray-100 border border-gray-300 rounded hover:bg-gray-200">Закрыть</button>
            </div>
          </div>
          <div className="p-4 overflow-y-auto flex-1">
            {viewLoading ? (
              <div className="text-center text-gray-500 py-8">Загрузка…</div>
            ) : viewError ? (
              <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded">{viewError}</div>
            ) : viewMessages.length === 0 ? (
              <div className="text-gray-500">Сообщений нет</div>
            ) : (
              <div className="space-y-3">
                {viewMessages.map((m: any, idx: number) => (
                  <div key={idx} className={`border rounded p-3 ${m.status === 'sent' ? 'bg-green-50 border-green-200' : 'bg-white'}`}>
                    <div className="flex items-center justify-between text-sm text-gray-600 mb-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{m.name || m.phone || 'Клиент'}</span>
                        {m.status === 'sent' && (
                          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 border border-green-200">
                            Отправлено
                          </span>
                        )}
                      </div>
                      <span className="text-gray-400">ID: {m.client_id?.slice(0, 8) || '-'}</span>
                    </div>
                    <div className="text-xs text-gray-500 mb-2">{m.segment ? `Сегмент ${m.segment}` : ''}</div>
                    
                    {editingMsgId === m.client_id ? (
                        <div className="mt-2">
                            <textarea 
                                value={editMsgText}
                                onChange={(e) => setEditMsgText(e.target.value)}
                                className="w-full p-2 border rounded text-sm focus:ring-pink-500 focus:border-pink-500"
                                rows={4}
                            />
                            <div className="flex gap-2 mt-2 justify-end">
                                <button onClick={handleCancelEdit} className="px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded text-xs">Отмена</button>
                                <button onClick={() => handleSaveMessage(m)} className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs">Сохранить</button>
                            </div>
                        </div>
                    ) : (
                        <>
                           <div className="text-gray-900 whitespace-pre-wrap">{m.message}</div>
                           {m.cta && <div className="mt-2 text-sm text-gray-700">{m.cta}</div>}
                           
                           {m.client_id && !editingMsgId && m.status !== 'sent' && (
                             <div className="mt-3 flex justify-end gap-3 border-t border-gray-100 pt-2">
                               <button 
                                   onClick={() => handleEditMessage(m)} 
                                   className="text-xs font-medium text-blue-600 hover:text-blue-800 flex items-center bg-blue-50 px-2 py-1 rounded hover:bg-blue-100 transition-colors"
                               >
                                   <span className="mr-1">✎</span> Редактировать
                               </button>
                               <button 
                                   onClick={() => handleRegenerateMessage(m)} 
                                   disabled={regeneratingIds.has(m.client_id)}
                                   className="text-xs font-medium text-pink-600 hover:text-pink-800 disabled:opacity-50 flex items-center bg-pink-50 px-2 py-1 rounded hover:bg-pink-100 transition-colors"
                               >
                                   <span className="mr-1">⟳</span> 
                                   {regeneratingIds.has(m.client_id) ? 'Генерация...' : 'Перегенерировать'}
                               </button>
                             </div>
                           )}
                        </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      {showSendModal && (
        <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4">
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-sm">
            <h3 className="text-lg font-semibold mb-4 text-gray-900">Настройка отправки SMS</h3>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">Время отправки (МСК)</label>
              <input 
                type="datetime-local" 
                value={sendDate} 
                onChange={(e) => setSendDate(e.target.value)} 
                className="w-full p-2 border border-gray-300 rounded focus:ring-blue-500 focus:border-blue-500"
              />
              <p className="text-xs text-gray-500 mt-1">Оставьте пустым для мгновенной отправки</p>
            </div>
            
            <div className="flex justify-end gap-3 mt-6">
              <button 
                onClick={() => setShowSendModal(false)} 
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
              >
                Отмена
              </button>
              <button 
                onClick={confirmSend} 
                disabled={sendBusy} 
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
              >
                {sendBusy ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Отправка...
                  </>
                ) : 'Подтвердить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
