/*
 * GLAME — certificate payment widget for the existing Tilda t706 cart.
 *
 * Install only after the GLAME API checkout route is deployed and tested in
 * Tilda Preview.  This script does not replace or change the native YooKassa
 * method. It adds a separate "Оплатить с сертификатом" path.
 *
 * Important: no secret, 1C credential or certificate number
 * is persisted in localStorage/cookies or sent to YooKassa. An opaque
 * checkout ID is kept in sessionStorage solely to resume a pending payment.
 */
(function () {
  'use strict';

  var API = 'https://portal.glamejewelry.ru/api';
  var CHECKOUT_STORAGE_KEY = 'glame_tilda_certificate_checkout_id';
  var state = { validation: null, checkoutId: null, pendingConfirmationUrl: null };

  function styles() {
    if (document.getElementById('glame-certificate-payment-styles')) return;
    var style = document.createElement('style');
    style.id = 'glame-certificate-payment-styles';
    style.textContent = '.glame-certificate-payment{margin:20px 0 10px;padding:18px 0;border-top:1px solid #d8d8d8;border-bottom:1px solid #d8d8d8;color:#151515}.glame-certificate-payment__title{font-size:16px;font-weight:600;letter-spacing:.02em}.glame-certificate-payment__fields{display:grid;grid-template-columns:1fr auto;gap:8px;margin-top:12px}.glame-certificate-payment input{min-width:0;height:42px;padding:0 12px;border:1px solid #b7b7b7;border-radius:0;background:#fff;color:#151515;font:14px Arial,sans-serif}.glame-certificate-payment button{min-height:42px;padding:0 16px;border:1px solid #151515;border-radius:0;background:#151515;color:#fff;font:13px Arial,sans-serif;cursor:pointer}.glame-certificate-payment button[disabled]{opacity:.55;cursor:wait}.glame-certificate-payment__message{min-height:18px;margin-top:10px;font-size:13px;line-height:1.4}.glame-certificate-payment__message.is-error{color:#a72626}.glame-certificate-payment__checkout{width:100%;margin-top:12px}@media(max-width:640px){.glame-certificate-payment__fields{grid-template-columns:1fr}.glame-certificate-payment__apply{grid-column:1/-1}}';
    document.head.appendChild(style);
  }

  function kopeks(value) {
    var digits = String(value || '').replace(/[^0-9,.-]/g, '').replace(',', '.');
    var amount = Number(digits);
    return Number.isFinite(amount) ? Math.round(amount * 100) : 0;
  }

  function cartRoot() {
    return document.querySelector('.t706');
  }

  function cartSnapshot() {
    var root = cartRoot();
    var productsRoot = root && root.querySelector('.t706__cartpage-products');
    var rows = productsRoot ? Array.prototype.slice.call(productsRoot.querySelectorAll('.t706__product')) : [];
    var items = rows.map(function (row) {
      var title = (row.querySelector('.t706__product-title') || {}).innerText || '';
      var quantity = Number(((row.querySelector('.t706__product-quantity') || {}).textContent || '1').replace(/\D/g, '')) || 1;
      var amount = kopeks((row.querySelector('.t706__product-amount') || {}).textContent);
      return {
        sku: title.trim().split(/\s+/).pop().slice(0, 64),
        quantity: quantity,
        unit_price: Math.round(amount / quantity),
        is_gift_certificate: /подарочн\w*\s+сертификат/i.test(title)
      };
    });
    var total = kopeks((root && root.querySelector('.t706__cartwin-totalamount') || {}).textContent);
    return { items: items, total: total };
  }

  function digest(value) {
    var bytes = new TextEncoder().encode(value);
    return crypto.subtle.digest('SHA-256', bytes).then(function (hash) {
      return Array.prototype.map.call(new Uint8Array(hash), function (byte) {
        return byte.toString(16).padStart(2, '0');
      }).join('');
    });
  }

  function freshSnapshot() {
    var snapshot = cartSnapshot();
    if (!snapshot.total || !snapshot.items.length) throw new Error('Корзина пуста');
    return digest(JSON.stringify({ total: snapshot.total, items: snapshot.items })).then(function (fingerprint) {
      snapshot.fingerprint = fingerprint;
      return snapshot;
    });
  }

  function checkoutId() {
    if (!state.checkoutId) state.checkoutId = crypto.randomUUID();
    return state.checkoutId;
  }

  function returnUrl(id) {
    var url = new URL(window.location.href);
    url.searchParams.set('glame_certificate_checkout', id);
    url.hash = 'tcart';
    return url.toString();
  }

  function savedCheckoutId() {
    var fromUrl = new URL(window.location.href).searchParams.get('glame_certificate_checkout');
    return fromUrl || window.sessionStorage.getItem(CHECKOUT_STORAGE_KEY) || '';
  }

  function clearSavedCheckout() {
    window.sessionStorage.removeItem(CHECKOUT_STORAGE_KEY);
    var url = new URL(window.location.href);
    if (url.searchParams.has('glame_certificate_checkout')) {
      url.searchParams.delete('glame_certificate_checkout');
      window.history.replaceState({}, '', url.toString());
    }
  }

  function request(path, body, key) {
    return fetch(API + path, {
      method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json', 'Idempotency-Key': key } : {},
      body: body ? JSON.stringify(body) : undefined,
      credentials: 'omit'
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (payload) {
        if (!response.ok) throw new Error(payload.detail || 'Сервис сертификатов временно недоступен');
        return payload;
      });
    });
  }

  function render(root) {
    if (!root || root.querySelector('.glame-certificate-payment')) return;
    var target = root.querySelector('.t706__cartpage-products');
    if (!target) return;
    var panel = document.createElement('section');
    panel.className = 'glame-certificate-payment';
    panel.innerHTML = [
      '<div class="glame-certificate-payment__title">Подарочный сертификат</div>',
      '<div class="glame-certificate-payment__fields">',
      '<input class="glame-certificate-payment__number" inputmode="text" autocomplete="off" placeholder="Номер сертификата">',
      '<button type="button" class="glame-certificate-payment__apply">Применить</button>',
      '</div>',
      '<div class="glame-certificate-payment__message" aria-live="polite"></div>',
      '<button type="button" class="glame-certificate-payment__checkout" hidden>Оплатить с сертификатом</button>'
    ].join('');
    target.parentNode.insertBefore(panel, target.nextSibling);
    bind(panel);
    restorePendingCheckout(panel);
  }

  function message(panel, text, error) {
    var node = panel.querySelector('.glame-certificate-payment__message');
    node.textContent = text || '';
    node.classList.toggle('is-error', Boolean(error));
  }

  function invalidate(panel) {
    state.validation = null;
    state.checkoutId = null;
    state.pendingConfirmationUrl = null;
    panel.querySelector('.glame-certificate-payment__checkout').hidden = true;
  }

  function restorePendingCheckout(panel) {
    var id = savedCheckoutId();
    if (!id) return;
    request('/public/tilda/gift-certificates/checkout/' + encodeURIComponent(id)).then(function (checkout) {
      if (checkout.status === 'reserved' && checkout.payment_required && checkout.confirmation_url) {
        state.checkoutId = id;
        state.pendingConfirmationUrl = checkout.confirmation_url;
        var button = panel.querySelector('.glame-certificate-payment__checkout');
        button.textContent = 'Продолжить оплату';
        button.hidden = false;
        message(panel, 'Сертификат зарезервирован для ожидающей оплаты.');
        return;
      }
      clearSavedCheckout();
    }).catch(function () { clearSavedCheckout(); });
  }

  function bind(panel) {
    panel.querySelector('.glame-certificate-payment__apply').addEventListener('click', function () {
      var number = panel.querySelector('.glame-certificate-payment__number').value.trim();
      if (!number) return message(panel, 'Введите номер сертификата', true);
      var button = this;
      button.disabled = true;
      message(panel, 'Проверяем сертификат…');
      freshSnapshot().then(function (snapshot) {
        return request('/public/tilda/gift-certificates/validate', {
          number: number,
          cart_total: snapshot.total,
          cart_fingerprint: snapshot.fingerprint,
          items: snapshot.items
        }, crypto.randomUUID()).then(function (validation) {
          state.validation = { token: validation.validation_token, snapshot: snapshot, amount: validation.applicable_amount };
          state.checkoutId = null;
          var due = (validation.amount_due / 100).toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
          message(panel, validation.amount_due ? 'Сертификат применён. К оплате: ' + due + ' ₽.' : 'Сертификат покрывает заказ полностью.');
          panel.querySelector('.glame-certificate-payment__checkout').hidden = false;
        });
      }).catch(function (error) {
        invalidate(panel);
        message(panel, error.message, true);
      }).finally(function () { button.disabled = false; });
    });

    panel.querySelector('.glame-certificate-payment__checkout').addEventListener('click', function () {
      if (state.pendingConfirmationUrl) {
        window.location.assign(state.pendingConfirmationUrl);
        return;
      }
      if (!state.validation) return;
      var button = this;
      button.disabled = true;
      freshSnapshot().then(function (snapshot) {
        var validated = state.validation.snapshot;
        if (snapshot.total !== validated.total || snapshot.fingerprint !== validated.fingerprint) {
          invalidate(panel);
          throw new Error('Состав корзины изменился. Проверьте сертификат ещё раз.');
        }
        return request('/public/tilda/gift-certificates/checkout', {
          validation_token: state.validation.token,
          amount: state.validation.amount,
          checkout_id: checkoutId(),
          cart_total: snapshot.total,
          cart_fingerprint: snapshot.fingerprint,
          return_url: returnUrl(checkoutId()),
          items: snapshot.items
        }, checkoutId());
      }).then(function (result) {
        if (result.payment_required && result.confirmation_url) {
          window.sessionStorage.setItem(CHECKOUT_STORAGE_KEY, checkoutId());
          window.location.assign(result.confirmation_url);
          return;
        }
        clearSavedCheckout();
        message(panel, 'Оплата принята. Заказ оформлен.');
        button.hidden = true;
      }).catch(function (error) {
        message(panel, error.message, true);
        button.disabled = false;
      });
    });
  }

  function install() {
    styles();
    var root = cartRoot();
    render(root);
    if (!root) return;
    new MutationObserver(function () { render(root); }).observe(root, { childList: true, subtree: true });
  }

  document.addEventListener('DOMContentLoaded', install);
  if (document.readyState !== 'loading') install();
})();
