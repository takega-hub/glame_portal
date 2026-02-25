'use client';

import { useState } from 'react';
import { Calendar, momentLocalizer } from 'react-big-calendar';
import moment from 'moment';
import 'react-big-calendar/lib/css/react-big-calendar.css';
import { ContentItemDTO } from '@/lib/api';

const localizer = momentLocalizer(moment);

// Импортируем moment для локализации
import 'moment/locale/ru';
moment.locale('ru');

type CalendarView = 'month' | 'week' | 'day' | 'agenda';

interface CalendarViewProps {
  items: ContentItemDTO[];
  onSelectSlot?: (slotInfo: { start: Date; end: Date }) => void;
  onSelectEvent?: (event: ContentItemDTO) => void;
}

// Цвета для разных статусов
const getStatusColor = (status: string): string => {
  const colors: Record<string, string> = {
    planned: '#3b82f6', // blue
    draft: '#9ca3af', // gray
    ready: '#10b981', // green
    approved: '#8b5cf6', // purple
    scheduled: '#f59e0b', // amber
    published: '#059669', // emerald
    failed: '#ef4444', // red
    cancelled: '#6b7280', // gray
  };
  return colors[status] || '#6b7280';
};

// Цвета для разных каналов
const getChannelColor = (channel: string): string => {
  const colors: Record<string, string> = {
    instagram: '#E4405F',
    website_main: '#3b82f6',
    email: '#f59e0b',
    vk: '#4c75a3',
    telegram: '#0088cc',
  };
  return colors[channel] || '#6b7280';
};

export default function CalendarView({ items, onSelectSlot, onSelectEvent }: CalendarViewProps) {
  // Состояние для текущего вида календаря
  const [currentView, setCurrentView] = useState<CalendarView>('month');
  // Состояние для текущей даты календаря
  const [currentDate, setCurrentDate] = useState<Date>(new Date());

  // Конвертируем слоты в события для календаря
  const events = items.map((item) => {
    const start = new Date(item.scheduled_at);
    // Для событий без длительности используем 1 час
    const end = new Date(start.getTime() + 60 * 60 * 1000);
    
    const statusColor = getStatusColor(item.status);
    const channelColor = getChannelColor(item.channel);
    
    return {
      id: item.id,
      title: item.topic || `${item.channel} - ${item.content_type}`,
      start,
      end,
      resource: item,
      // Используем цвет статуса как основной, но можно комбинировать с каналом
      style: {
        backgroundColor: statusColor,
        borderColor: channelColor,
        borderWidth: '2px',
        color: '#fff',
        borderRadius: '4px',
        padding: '2px 4px',
      },
    };
  });

  const eventStyleGetter = (event: any) => {
    const item = event.resource as ContentItemDTO;
    const statusColor = getStatusColor(item.status);
    const channelColor = getChannelColor(item.channel);
    
    return {
      style: {
        backgroundColor: statusColor,
        borderColor: channelColor,
        borderWidth: '2px',
        color: '#fff',
        borderRadius: '4px',
        padding: '2px 4px',
        fontSize: '12px',
      },
    };
  };

  const handleSelectEvent = (event: any) => {
    if (onSelectEvent && event.resource) {
      onSelectEvent(event.resource);
    }
  };

  const handleSelectSlot = (slotInfo: { start: Date; end: Date }) => {
    if (onSelectSlot) {
      onSelectSlot(slotInfo);
    }
  };

  // Обработчик изменения вида календаря
  const handleViewChange = (view: CalendarView) => {
    setCurrentView(view);
  };

  // Обработчик навигации по датам
  const handleNavigate = (newDate: Date) => {
    setCurrentDate(newDate);
  };

  return (
    <div className="h-[600px] bg-white rounded-lg shadow-md p-4">
      <Calendar
        localizer={localizer}
        events={events}
        startAccessor="start"
        endAccessor="end"
        style={{ height: '100%' }}
        eventPropGetter={eventStyleGetter}
        onSelectEvent={handleSelectEvent}
        onSelectSlot={handleSelectSlot}
        selectable
        view={currentView}
        date={currentDate}
        onView={handleViewChange}
        onNavigate={handleNavigate}
        views={['month', 'week', 'day', 'agenda']}
        messages={{
          next: 'Следующий',
          previous: 'Предыдущий',
          today: 'Сегодня',
          month: 'Месяц',
          week: 'Неделя',
          day: 'День',
          agenda: 'Повестка дня',
          date: 'Дата',
          time: 'Время',
          event: 'Событие',
          noEventsInRange: 'Нет событий в этом диапазоне',
        }}
        culture="ru"
      />
      
      {/* Легенда */}
      <div className="mt-4 flex flex-wrap gap-4 text-xs">
        <div>
          <span className="font-semibold text-gray-700">Статусы:</span>
          <div className="flex flex-wrap gap-2 mt-1">
            {['planned', 'draft', 'ready', 'approved', 'scheduled', 'published', 'failed', 'cancelled'].map((status) => (
              <div key={status} className="flex items-center gap-1">
                <div
                  className="w-3 h-3 rounded"
                  style={{ backgroundColor: getStatusColor(status) }}
                />
                <span className="text-gray-600">{status}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <span className="font-semibold text-gray-700">Каналы (граница):</span>
          <div className="flex flex-wrap gap-2 mt-1">
            {['instagram', 'website_main', 'email', 'vk', 'telegram'].map((channel) => (
              <div key={channel} className="flex items-center gap-1">
                <div
                  className="w-3 h-3 rounded border-2"
                  style={{ borderColor: getChannelColor(channel), backgroundColor: 'transparent' }}
                />
                <span className="text-gray-600">{channel}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
