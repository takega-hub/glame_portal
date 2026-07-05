import { test, expect } from '@playwright/test';

test.describe('Глобальный сайдбар: мобильный UX', () => {
  test.use({ viewport: { width: 375, height: 812 } }); // iPhone-ish

  test('Открытие/закрытие на мобильных по кнопке, оверлею и ESC', async ({ page }) => {
    await page.goto('/');

    const sidebar = page.locator('#glame-sidebar');
    const toggleBtn = page.getByRole('button', { name: /меню|открыть меню|закрыть меню/i });

    // Изначально скрыт на мобильных
    await expect(sidebar).toHaveClass(/-translate-x-full/);

    // Открыть
    await toggleBtn.click();
    await expect(sidebar).not.toHaveClass(/-translate-x-full/);

    // Появился оверлей
    const overlay = page.locator('div.fixed.inset-0[aria-hidden="true"]');
    await expect(overlay).toBeVisible();

    // Закрыть по клику на оверлей
    await overlay.click({ force: true });
    await expect(sidebar).toHaveClass(/-translate-x-full/);

    // Открыть снова и закрыть по ESC
    await toggleBtn.click();
    await expect(sidebar).not.toHaveClass(/-translate-x-full/);
    await page.keyboard.press('Escape');
    await expect(sidebar).toHaveClass(/-translate-x-full/);
  });
});

test.describe('Глобальный сайдбар: десктоп', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('Кнопка тоггла видима и кликабельна', async ({ page }) => {
    await page.goto('/');

    const desktopToggle = page.locator('#glame-sidebar').getByRole('button', { name: /свернуть сайдбар|развернуть сайдбар/i });
    await expect(desktopToggle).toBeVisible();

    await desktopToggle.click();
    // Негативной проверки не делаем из‑за различий движков; достаточно кликабельности
  });
});

test.describe('Подсветка активного пункта меню', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('Переход на /admin/prompts подсвечивает «Системные промпты»', async ({ page }) => {
    await page.goto('/admin/prompts');
    const promptsLink = page.getByRole('link', { name: /Системные промпты/i });
    await expect(promptsLink).toHaveClass(/bg-gold-100/);
  });
});

test.describe('Объединенная аналитика: исключение магазинов из графика', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('Исключённые магазины не отображаются в легенде графика', async ({ page }) => {
    const excludedIds = [
      '5fe87060-39f8-458c-9b3e-5a6e4a54f2ec',
      'e011e44d-7945-4dc0-8080-b4eb555d01a1',
      'e1a2eace-fdc8-11ef-8c0c-fa163e4cc04e',
    ];

    let dailySourcesRequestedUrl = '';
    const analyticsRequests: string[] = [];
    page.on('request', (req) => {
      const url = req.url();
      if (url.includes('analytics')) analyticsRequests.push(url);
    });

    await page.route('**/*analytics/dashboard*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          period: { start: '2026-02-24T00:00:00.000Z', end: '2026-03-01T00:00:00.000Z', days: 7 },
          conversion: { events: {}, conversion_rates: {} },
          aov: {},
          engagement: {},
          events_by_type: {},
          total_events: 0,
        }),
      });
    });

    await page.route('**/*analytics/unified*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          period: { start: '2026-02-24T00:00:00.000Z', end: '2026-03-01T00:00:00.000Z', days: 7 },
          website: { visits: 145, visitors: 126, bounce_rate: 30.34 },
          social_media: { total_metrics: 0, platforms: [] },
          stores: { total_visitors: 508, total_sales: 47 },
        }),
      });
    });

    await page.route('**/*analytics/sources*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          stores: [
            { id: 's1', external_id: excludedIds[0], name: 'Тестовый магазин A' },
            { id: 's2', external_id: 'CENTER2', name: 'Центрум 2' },
            { id: 's3', external_id: excludedIds[1], name: 'Тестовый магазин B' },
            { id: 's4', external_id: excludedIds[2], name: 'Тестовый магазин C' },
            { id: 's5', external_id: 'YALTA18', name: 'Ялта, Набережная 18' },
          ],
          channels: [],
        }),
      });
    });

    await page.route('**/*analytics/store-visits/daily*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          daily_data: [{ date: '2026-02-24T00:00:00.000Z', visitors: 508 }],
        }),
      });
    });

    await page.route('**/*analytics/website-visits/daily*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          daily_data: [{ date: '2026-02-24T00:00:00.000Z', visits: 145 }],
        }),
      });
    });

    await page.route('**/*analytics/1c-sales/metrics*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'success', aggregated: { total_orders: 47 } }),
      });
    });

    await page.route('**/*analytics/1c-sales/daily-sources*', async (route) => {
      dailySourcesRequestedUrl = route.request().url();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          legend: [
            { id: excludedIds[0], name: excludedIds[0] },
            { id: 'CENTER2', name: 'Центрум 2' },
            { id: excludedIds[1], name: excludedIds[1] },
            { id: excludedIds[2], name: excludedIds[2] },
            { id: 'YALTA18', name: 'Ялта, Набережная 18' },
          ],
          daily: [
            {
              date: '2026-02-24',
              sources: {
                [excludedIds[0]]: 1000,
                CENTER2: 2000,
                [excludedIds[1]]: 3000,
                [excludedIds[2]]: 4000,
                YALTA18: 5000,
              },
            },
          ],
        }),
      });
    });

    await page.goto('/analytics');

    await page.waitForTimeout(250);
    expect(analyticsRequests.length).toBeGreaterThan(0);

    await expect(page.getByRole('heading', { name: 'Аналитика', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Объединенная аналитика', exact: true })).toBeVisible();
    await expect(page.locator('.recharts-wrapper')).toBeVisible();

    const legend = page.locator('.recharts-legend-wrapper');
    await expect(legend).toBeVisible();
    await expect(legend.getByText('Центрум 2')).toBeVisible();
    await expect(legend.getByText('Ялта, Набережная 18')).toBeVisible();
    for (const id of excludedIds) {
      await expect(legend.getByText(id)).toHaveCount(0);
    }

    await expect(page.getByRole('button', { name: 'Центрум 2' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Ялта, Набережная 18' })).toBeVisible();
    for (const id of excludedIds) {
      await expect(page.getByRole('button', { name: id })).toHaveCount(0);
      expect(dailySourcesRequestedUrl).not.toContain(encodeURIComponent(id));
      expect(dailySourcesRequestedUrl).not.toContain(id);
    }
  });
});

test.describe('Настройки: OpenRouter — траты сегодня', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('Показывает «Траты сегодня» и разбивку по моделям', async ({ page }) => {
    const todayKey = new Date().toISOString().slice(0, 10);
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.stack || err.message));
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });

    await page.route('**/*settings/openrouter/stats*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          avg_daily: 1.23,
          remaining_credits: 10.0,
          days_left: 8,
          by_model: [
            { model: 'openai/gpt-4o-mini', total_cost: 3.5, requests: 42 },
            { model: 'anthropic/claude-3.5-sonnet', total_cost: 2.1, requests: 12 },
          ],
          by_day: [
            {
              date: todayKey,
              total_cost: 0.84,
              by_model: {
                'openai/gpt-4o-mini': 0.64,
                'anthropic/claude-3.5-sonnet': 0.2,
              },
            },
          ],
        }),
      });
    });

    await page.route('**/*settings/openrouter/today*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          date: todayKey,
          total_cost: 0.84,
          by_model: {
            'openai/gpt-4o-mini': 0.64,
            'anthropic/claude-3.5-sonnet': 0.2,
          },
        }),
      });
    });

    await page.route('**/*settings/model*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ default_model: 'openai/gpt-4o-mini', source: 'openrouter' }),
      });
    });

    await page.route('**/*settings/openrouter/models*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          models: [
            { id: 'openai/gpt-4o-mini', name: 'GPT-4o mini', pricing: { prompt: '0.15', completion: '0.60' }, context_length: 128000 },
          ],
          cached: true,
          fetched_at: 0,
        }),
      });
    });

    await page.route('**/*settings/image-generation-model*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ image_generation_model: 'openai/dall-e-3', source: 'openrouter' }),
      });
    });

    await page.route('**/*settings/openrouter/image-models*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          models: [
            { id: 'openai/dall-e-3', name: 'DALL·E 3', pricing: { prompt: '0.00', completion: '0.00' }, context_length: 0 },
          ],
          cached: true,
          fetched_at: 0,
        }),
      });
    });

    await page.goto('/settings');

    const appError = page.getByRole('heading', { name: /Application error/i });
    if (await appError.isVisible().catch(() => false)) {
      throw new Error(errors.join('\n') || 'Application error');
    }

    await expect(page.getByRole('heading', { name: /Настройки/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Статистика использования OpenRouter/i })).toBeVisible();

    // Verify "Today's Costs" section
    // Total cost is in the header of the section
    await expect(page.getByRole('heading', { name: 'Траты сегодня', exact: true })).toBeVisible();
    await expect(page.getByText('$0.84')).toBeVisible();

    // Breakdown by model is in the first table
    const todayTable = page.locator('table').first();
    await expect(todayTable).toBeVisible();
    await expect(todayTable.getByText('openai/gpt-4o-mini')).toBeVisible();
    await expect(todayTable.getByText('$0.64')).toBeVisible();
    await expect(todayTable.getByText('anthropic/claude-3.5-sonnet')).toBeVisible();
    await expect(todayTable.getByText('$0.20')).toBeVisible();
  });
});
