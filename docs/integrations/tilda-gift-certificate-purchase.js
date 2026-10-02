/*
 * GLAME — cart-independent purchase bridge for /gift-certificate.
 *
 * Add this script AFTER the existing gift-certificate page script in the T123
 * block. It intercepts only #gg-buy, calls the GLAME purchase API and redirects
 * to YooKassa. It never creates a Tilda cart item and never changes the normal
 * jewellery checkout.
 */
(function () {
  "use strict";

  var root = document.getElementById("glame-gift-page");
  if (!root || root.dataset.purchaseContractReady === "1") return;
  root.dataset.purchaseContractReady = "1";

  var API = "https://portal.glamejewelry.ru/api";
  var PURCHASE_KEY = "glameGiftPurchase";
  var IDEMPOTENCY_KEY = "glameGiftPurchaseIdempotency";
  var config = null;

  function uuid() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      var v = c === "x" ? r : (r & 3 | 8);
      return v.toString(16);
    });
  }

  function errorNode() {
    return document.getElementById("gg-cart-error");
  }

  function message(text, isError) {
    var node = errorNode();
    if (!node) return;
    node.textContent = text || "";
    node.classList.toggle("is-visible", Boolean(text));
    node.style.color = isError ? "#9f2e2e" : "";
  }

  function showView(number) {
    root.querySelectorAll("[data-gg-view]").forEach(function (view) {
      view.classList.toggle(
        "is-active",
        view.getAttribute("data-gg-view") === String(number)
      );
    });
  }

  function ensureBuyerEmailField() {
    if (document.getElementById("gg-buyer-email")) return;

    var recipientEmail = document.getElementById("gg-recipient-email");
    if (!recipientEmail) return;

    var label = document.createElement("label");
    label.className = "gg-field gg-field--full";
    label.innerHTML = [
      '<span class="gg-field-label">Ваш email для чека</span>',
      '<input class="gg-input" id="gg-buyer-email" type="email"',
      ' autocomplete="email" placeholder="your@email.ru" required>',
      '<span style="display:block;margin-top:7px;font-size:12px;',
      'line-height:1.45;opacity:.62">На этот адрес ЮKassa отправит чек об оплате.</span>'
    ].join("");

    var field = recipientEmail.closest(".gg-field");
    field.parentNode.insertBefore(label, field.nextSibling);

    var recipientRow = document.getElementById("gg-summary-recipient");
    if (recipientRow && !document.getElementById("gg-summary-buyer-email")) {
      var row = document.createElement("div");
      row.className = "gg-summary-row";
      row.innerHTML = [
        '<span class="gg-summary-key">Email для чека</span>',
        '<span class="gg-summary-value" id="gg-summary-buyer-email"></span>'
      ].join("");
      recipientRow.closest(".gg-summary-row").insertAdjacentElement("afterend", row);
    }
  }

  function selectedValue(selector, attribute) {
    var selected = root.querySelector(selector + ".is-active");
    return selected ? selected.getAttribute(attribute) : "";
  }

  function delivery() {
    var selected = root.querySelector('input[name="gg-delivery"]:checked');
    var mode = selected && selected.value === "later" ? "scheduled" : "now";
    var value = (document.getElementById("gg-delivery-date") || {}).value || "";
    return {
      mode: mode,
      send_at: mode === "scheduled" && value ? new Date(value).toISOString() : null
    };
  }

  function amountKopeks() {
    return Math.round(Number(selectedValue("[data-amount]", "data-amount") || 0) * 100);
  }

  function returnUrl() {
    var url = new URL(window.location.href);
    url.searchParams.set("gift_purchase_return", "1");
    url.hash = "gift-certificate-status";
    return url.toString();
  }

  function purchasePayload() {
    return {
      design: selectedValue("[data-design]", "data-design"),
      nominal_amount: amountKopeks(),
      recipient: {
        name: document.getElementById("gg-recipient-name").value.trim(),
        email: document.getElementById("gg-recipient-email").value.trim()
      },
      sender: {
        name: document.getElementById("gg-sender-name").value.trim()
      },
      message: document.getElementById("gg-message").value.trim() || null,
      delivery: delivery(),
      buyer_receipt_contact: {
        email: document.getElementById("gg-buyer-email").value.trim()
      },
      return_url: returnUrl()
    };
  }

  async function request(path, options) {
    var response = await window.fetch(API + path, options || {});
    var payload = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      var error = new Error(payload.detail || "Сервис временно недоступен");
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function friendlyError(error) {
    if (error && error.status === 503) {
      return "Сейчас покупка сертификата временно недоступна. Пожалуйста, попробуйте немного позже.";
    }
    if (error && error.status === 409) {
      return "Этот платёж уже создаётся. Обновите страницу и продолжите прежнюю оплату.";
    }
    if (error && error.status === 422) {
      return "Проверьте данные получателя, email для чека и время отправки.";
    }
    return "Не удалось перейти к оплате. Попробуйте ещё раз.";
  }

  function getIdempotencyKey() {
    var key = window.sessionStorage.getItem(IDEMPOTENCY_KEY);
    if (!key) {
      key = uuid();
      window.sessionStorage.setItem(IDEMPOTENCY_KEY, key);
    }
    return key;
  }

  function resetIdempotencyKey() {
    window.sessionStorage.removeItem(IDEMPOTENCY_KEY);
  }

  async function createPurchase(event) {
    event.preventDefault();
    event.stopImmediatePropagation();

    var button = document.getElementById("gg-buy");
    var form = document.getElementById("gg-recipient-form");
    message("", false);

    if (!form.checkValidity()) {
      form.reportValidity();
      showView(2);
      return;
    }

    var payload = purchasePayload();
    if (!payload.design || !payload.nominal_amount) {
      message("Выберите дизайн и сумму сертификата.", true);
      showView(1);
      return;
    }
    if (config && Array.isArray(config.allowed_amounts) &&
        config.allowed_amounts.indexOf(payload.nominal_amount) === -1) {
      message("Выбранный номинал пока недоступен. Выберите другую сумму.", true);
      return;
    }

    var original = button.textContent;
    button.disabled = true;
    button.textContent = "Создаём оплату…";

    try {
      var result = await request("/public/tilda/gift-certificates/purchases", {
        method: "POST",
        credentials: "omit",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": getIdempotencyKey()
        },
        body: JSON.stringify(payload)
      });

      var confirmationUrl = result.payment && result.payment.confirmation_url;
      if (!result.purchase_id || !result.status_token || !confirmationUrl) {
        throw new Error("Payment response is incomplete");
      }

      window.localStorage.setItem(PURCHASE_KEY, JSON.stringify({
        purchase_id: result.purchase_id,
        status_token: result.status_token
      }));
      window.location.assign(confirmationUrl);
    } catch (error) {
      console.error("[GLAME Gift Certificate Purchase]", error);
      message(friendlyError(error), true);
      button.disabled = false;
      button.textContent = original;
    }
  }

  function statusMessage(status) {
    if (status === "sent") {
      return "Готово. Сертификат уже отправлен получателю.";
    }
    if (status === "scheduled") {
      return "Готово. Сертификат будет отправлен в выбранные дату и время.";
    }
    if (status === "issued") {
      return "Оплата получена. Готовим сертификат к отправке.";
    }
    if (status === "canceled") {
      return "Оплата отменена. Сертификат не создан.";
    }
    if (status === "failed" || status === "paid_pending_issue") {
      return "Оплата получена, но отправка требует проверки. Мы сохранили заказ.";
    }
    return "Проверяем оплату…";
  }

  async function restorePurchase() {
    var url = new URL(window.location.href);
    if (url.searchParams.get("gift_purchase_return") !== "1") return;

    var stored;
    try {
      stored = JSON.parse(window.localStorage.getItem(PURCHASE_KEY) || "null");
    } catch (_) {
      stored = null;
    }
    if (!stored || !stored.purchase_id || !stored.status_token) return;

    showView(3);
    message("Проверяем оплату…", false);

    for (var attempt = 0; attempt < 7; attempt += 1) {
      try {
        var result = await request(
          "/public/tilda/gift-certificates/purchases/" +
            encodeURIComponent(stored.purchase_id),
          {
            method: "GET",
            credentials: "omit",
            headers: { "X-Purchase-Token": stored.status_token }
          }
        );
        message(statusMessage(result.status), result.status === "failed");

        if (["sent", "scheduled", "issued", "canceled", "failed"].indexOf(result.status) !== -1) {
          resetIdempotencyKey();
          return;
        }
      } catch (error) {
        console.error("[GLAME Gift Certificate Status]", error);
        message("Не удалось проверить оплату. Обновите страницу через минуту.", true);
        return;
      }
      await new Promise(function (resolve) { window.setTimeout(resolve, 2000); });
    }
  }

  async function loadConfig() {
    try {
      config = await request("/public/tilda/gift-certificates/purchase-config", {
        method: "GET",
        credentials: "omit"
      });
      root.dataset.purchaseEnabled = config.enabled ? "1" : "0";
    } catch (error) {
      root.dataset.purchaseEnabled = "0";
      console.error("[GLAME Gift Certificate Config]", error);
    }
  }

  ensureBuyerEmailField();

  var form = document.getElementById("gg-recipient-form");
  form.addEventListener("input", resetIdempotencyKey);
  form.addEventListener("change", resetIdempotencyKey);
  form.addEventListener("submit", function () {
    window.setTimeout(function () {
      var node = document.getElementById("gg-summary-buyer-email");
      var input = document.getElementById("gg-buyer-email");
      if (node && input) node.textContent = input.value.trim();
    }, 0);
  });

  document.getElementById("gg-buy").addEventListener("click", createPurchase, true);

  loadConfig();
  restorePurchase();
})();
