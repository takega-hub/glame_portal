const state = {
  user: null,
  cart: { items: [], totals: { subtotal: 0 } },
  accessToken: localStorage.getItem("store_access_token"),
  refreshToken: localStorage.getItem("store_refresh_token"),
  otpPhone: "",
  ui: { menuOpen: false, heroSlide: 0 },
};

const app = document.getElementById("app");
const modalRoot = document.getElementById("modal-root");
const authBtn = document.getElementById("auth-btn");
const cartBtn = document.getElementById("cart-btn");
const searchBtn = document.getElementById("search-btn");
const cartCount = document.getElementById("cart-count");
const mainNav = document.getElementById("main-nav");
const menuOpenLink = document.getElementById("menu-open-link");
const sideDrawer = document.getElementById("side-drawer");
const drawerAuthBtn = document.getElementById("drawer-auth-btn");

const API_PREFIX = `${window.__STORE_API_BASE__ || ""}/api`;

const currency = (kopeks) =>
  new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(Number(kopeks || 0) / 100);

function saveTokens(accessToken, refreshToken) {
  state.accessToken = accessToken || null;
  state.refreshToken = refreshToken || null;
  if (accessToken) localStorage.setItem("store_access_token", accessToken);
  else localStorage.removeItem("store_access_token");
  if (refreshToken) localStorage.setItem("store_refresh_token", refreshToken);
  else localStorage.removeItem("store_refresh_token");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function stripHtml(value) {
  return String(value ?? "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function route() {
  const raw = location.hash.replace(/^#/, "") || "/home";
  const [path, queryString] = raw.split("?");
  return { path, query: new URLSearchParams(queryString || "") };
}

function normalizeImageUrl(url) {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  if (url.startsWith("/")) return url;
  return `/${url}`;
}

function parseErrorDetail(text, fallback) {
  try {
    const body = JSON.parse(text);
    return body.detail || fallback;
  } catch (_) {
    return fallback;
  }
}

async function apiFetch(path, options = {}, allowRefresh = true) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.accessToken) headers.Authorization = `Bearer ${state.accessToken}`;
  const response = await fetch(`${API_PREFIX}${path}`, { ...options, headers });

  if (response.status === 401 && allowRefresh && state.refreshToken) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return apiFetch(path, options, false);
  }
  if (!response.ok) {
    const body = await response.text();
    throw new Error(parseErrorDetail(body, `HTTP ${response.status}`));
  }
  if (response.status === 204) return null;
  return response.json();
}

async function refreshAccessToken() {
  if (!state.refreshToken) return false;
  try {
    const resp = await fetch(`${API_PREFIX}/auth/refresh?refresh_token=${encodeURIComponent(state.refreshToken)}`, {
      method: "POST",
    });
    if (!resp.ok) return false;
    const body = await resp.json();
    saveTokens(body.access_token, body.refresh_token);
    return true;
  } catch (_) {
    return false;
  }
}

async function loadUser() {
  if (!state.accessToken) {
    state.user = null;
    return;
  }
  try {
    state.user = await apiFetch("/auth/me");
  } catch (_) {
    state.user = null;
    saveTokens(null, null);
  }
}

async function loadCart() {
  if (!state.accessToken) {
    state.cart = { items: [], totals: { subtotal: 0 } };
    updateAuthUI();
    return;
  }
  try {
    state.cart = await apiFetch("/cart");
  } catch (_) {
    state.cart = { items: [], totals: { subtotal: 0 } };
  }
  updateAuthUI();
}

function updateAuthUI() {
  const count = (state.cart.items || []).reduce((sum, x) => sum + Number(x.quantity || 0), 0);
  cartCount.textContent = String(count);
  authBtn.title = state.user ? "Кабинет (выйти)" : "Кабинет (войти)";
  authBtn.setAttribute("aria-label", state.user ? "Кабинет (выйти)" : "Кабинет (войти)");
  if (drawerAuthBtn) drawerAuthBtn.textContent = state.user ? "Выйти" : "Войти";
}

function setMenuOpen(open) {
  state.ui.menuOpen = !!open;
  mainNav.classList.toggle("is-open", state.ui.menuOpen);
}

function setDrawerOpen(open) {
  if (!sideDrawer) return;
  sideDrawer.classList.toggle("hidden", !open);
  sideDrawer.setAttribute("aria-hidden", open ? "false" : "true");
  document.body.style.overflow = open ? "hidden" : "";
}

function ensureMobileMenuButton() {
  let btn = document.getElementById("menu-toggle-btn");
  if (btn) return;
  btn = document.createElement("button");
  btn.id = "menu-toggle-btn";
  btn.className = "menu-toggle-btn";
  btn.type = "button";
  btn.textContent = "Меню";
  btn.addEventListener("click", () => setDrawerOpen(true));
  const topbarInner = document.querySelector(".topbar-inner");
  topbarInner?.insertBefore(btn, mainNav);
}

function renderProductCard(item) {
  const image = normalizeImageUrl(item.images?.[0] || "");
  const name = escapeHtml(item.name || "Товар");
  return `
    <article class="card">
      <a href="#/product/${item.id}">
        ${image ? `<img class="card-media" src="${escapeHtml(image)}" alt="${name}">` : `<div class="card-media"></div>`}
      </a>
      <div class="card-body">
        <p class="card-name">${name}</p>
        <p class="card-price">${currency(item.price)}</p>
      </div>
    </article>
  `;
}

function renderLookbookCard(item) {
  const image = normalizeImageUrl(item.cover_image_url || "");
  return `
    <article class="lookbook-card">
      ${image ? `<img src="${escapeHtml(image)}" alt="${escapeHtml(item.title)}">` : `<div class="lookbook-ph"></div>`}
      <div class="lookbook-body">
        <p class="lookbook-title">${escapeHtml(item.title || "Lookbook")}</p>
        <p class="muted">${escapeHtml(stripHtml(item.description || ""))}</p>
      </div>
    </article>
  `;
}

function renderInfoCard(title, text) {
  return `<article class="info-card"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p></article>`;
}

async function renderHome() {
  const [banners, featuredResp, sections, lookbooks, promotions, news] = await Promise.all([
    apiFetch("/app/banners?placement=home_hero").catch(() => []),
    apiFetch("/products/paged?skip=0&limit=8&has_images=true").catch(() => ({ items: [] })),
    apiFetch("/catalog-sections/").catch(() => []),
    apiFetch("/app/lookbooks").catch(() => []),
    apiFetch("/app/promotions?active_only=true").catch(() => []),
    apiFetch("/app/news?published_only=true").catch(() => []),
  ]);

  const slides = (banners || []).slice(0, 4);
  const slide = slides[state.ui.heroSlide % Math.max(slides.length, 1)] || null;
  const heroImg = normalizeImageUrl(slide?.image_url || "");
  const heroTitle = slide?.title || "Украшения вне времени";
  const heroSubtitle = "Бесплатная доставка от 10 000 руб.";
  const featured = featuredResp.items || [];
  const categories = (sections || []).slice(0, 8);

  app.innerHTML = `
    <section class="hero" style="${heroImg ? `background-image:url('${escapeHtml(heroImg)}')` : ""}">
      <div class="overlay container">
        <h1 class="hero-title">${escapeHtml(heroTitle)}</h1>
        <p class="hero-sub">${escapeHtml(heroSubtitle)}</p>
        <div class="hero-actions">
          <a class="btn primary" href="#/catalog">Перейти в каталог</a>
          <a class="btn" href="#/about">О бренде</a>
        </div>
      </div>
      ${slides.length > 1 ? `
      <div class="hero-dots">
        ${slides.map((_, i) => `<button type="button" class="hero-dot ${i === state.ui.heroSlide ? "is-active" : ""}" data-hero-dot="${i}"></button>`).join("")}
      </div>` : ""}
    </section>

    <section class="section">
      <div class="container">
        <h2>Категории</h2>
        <div class="categories-row">
          ${categories.map((x) => `<a class="category-pill" href="#/catalog?category=${encodeURIComponent(x.name || "")}">${escapeHtml(x.name || "")}</a>`).join("")}
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <h2>Новинки</h2>
        <div class="grid">${featured.map(renderProductCard).join("")}</div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <h2>Look book</h2>
        <div class="lookbook-grid">${(lookbooks || []).slice(0, 3).map(renderLookbookCard).join("") || `<p class="muted">Раздел в наполнении.</p>`}</div>
      </div>
    </section>

    <section class="section">
      <div class="container info-grid">
        ${renderInfoCard("Доставка", "Бесплатная доставка от 10 000 руб. по России.")}
        ${renderInfoCard("Акции", stripHtml(promotions?.[0]?.title || "Актуальные предложения доступны в каталоге."))}
        ${renderInfoCard("Новости", stripHtml(news?.[0]?.title || "Следите за новыми коллекциями и релизами бренда."))}
      </div>
    </section>
  `;

  document.querySelectorAll("[data-hero-dot]").forEach((el) => {
    el.addEventListener("click", () => {
      state.ui.heroSlide = Number(el.getAttribute("data-hero-dot")) || 0;
      renderHome();
    });
  });
}

async function renderCatalog(query) {
  const search = query.get("q") || "";
  const category = query.get("category") || "";
  const inStock = query.get("in_stock") === "1";
  const categories = await apiFetch("/catalog-sections/").catch(() => []);

  const params = new URLSearchParams({ skip: "0", limit: "48", has_images: "true" });
  if (search) params.set("search", search);
  if (category) params.set("category", category);
  if (inStock) params.set("in_stock", "true");

  const data = await apiFetch(`/products/paged?${params.toString()}`).catch((e) => ({ error: e.message, items: [], total: 0 }));
  if (data.error) {
    app.innerHTML = `<section class="section"><div class="container"><p>${escapeHtml(data.error)}</p></div></section>`;
    return;
  }

  app.innerHTML = `
    <section class="section">
      <div class="container">
        <h2>Каталог</h2>
        <form id="catalog-filter-form" class="catalog-controls">
          <input type="search" name="q" placeholder="Поиск по названию или артикулу" value="${escapeHtml(search)}">
          <select name="category">
            <option value="">Все разделы</option>
            ${(categories || [])
              .map((x) => `<option value="${escapeHtml(x.name)}" ${x.name === category ? "selected" : ""}>${escapeHtml(x.name)}</option>`)
              .join("")}
          </select>
          <label class="check-inline"><input type="checkbox" name="in_stock" ${inStock ? "checked" : ""}> В наличии</label>
          <button class="btn" type="submit">Применить</button>
        </form>
        <p class="muted">Найдено товаров: ${Number(data.total || 0)}</p>
        <div class="grid">${(data.items || []).map(renderProductCard).join("")}</div>
      </div>
    </section>
  `;

  document.getElementById("catalog-filter-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const next = new URLSearchParams();
    const q = String(fd.get("q") || "").trim();
    const c = String(fd.get("category") || "").trim();
    const s = fd.get("in_stock") ? "1" : "";
    if (q) next.set("q", q);
    if (c) next.set("category", c);
    if (s) next.set("in_stock", s);
    location.hash = `#/catalog${next.toString() ? `?${next.toString()}` : ""}`;
  });
}

function renderSpecs(specs) {
  if (!specs || typeof specs !== "object") return "";
  const skip = new Set(["parent_external_id", "Parent_Key", "parent_key"]);
  const rows = Object.entries(specs)
    .filter(([k, v]) => !skip.has(k) && typeof v !== "object" && String(v || "").trim() !== "")
    .slice(0, 12);
  if (!rows.length) return "";
  return `
    <div class="specs-grid">
      ${rows.map(([k, v]) => `<div class="spec-row"><span>${escapeHtml(k)}</span><span>${escapeHtml(v)}</span></div>`).join("")}
    </div>
  `;
}

async function renderProduct(productId) {
  const [product, variantsResp] = await Promise.all([
    apiFetch(`/products/${productId}`).catch(() => null),
    apiFetch(`/products/${productId}/variants`).catch(() => ({ variants: [] })),
  ]);
  if (!product) {
    app.innerHTML = `<section class="section"><div class="container"><p>Товар не найден.</p></div></section>`;
    return;
  }
  const images = (product.images || []).map(normalizeImageUrl);
  const variants = variantsResp.variants || [];
  const mainImage = images[0] || "";

  app.innerHTML = `
    <section class="section">
      <div class="container">
        <div class="crumbs"><a href="#/home">Главная</a> / <a href="#/catalog">Каталог</a> / ${escapeHtml(product.name)}</div>
        <div class="product-layout">
          <div>
            ${mainImage ? `<img id="product-main-image" class="product-image" src="${escapeHtml(mainImage)}" alt="${escapeHtml(product.name)}">` : `<div class="product-image"></div>`}
            <div class="thumbs">
              ${images.map((img, i) => `<button type="button" data-thumb="${i}"><img src="${escapeHtml(img)}" alt=""></button>`).join("")}
            </div>
          </div>
          <div class="stack-md">
            <h2>${escapeHtml(product.name)}</h2>
            <p class="product-price">${currency(product.price)}</p>
            ${product.article ? `<p class="muted">Артикул: ${escapeHtml(product.article)}</p>` : ""}
            <button id="add-to-cart-btn" class="btn primary" type="button">Добавить в корзину</button>
            <a class="btn" href="#/cart">Перейти в корзину</a>
            ${renderSpecs(product.specifications)}
            ${variants.length ? `
              <div>
                <h3>Варианты</h3>
                <div class="stack-sm">
                  ${variants.slice(0, 12).map((v) => `<a class="muted" href="#/product/${v.id}">${escapeHtml(v.name)} - ${currency(v.price)}</a>`).join("")}
                </div>
              </div>` : ""}
            ${product.description ? `<div class="product-description">${product.description}</div>` : ""}
          </div>
        </div>
      </div>
    </section>
  `;

  document.querySelectorAll("[data-thumb]").forEach((el) => {
    el.addEventListener("click", () => {
      const index = Number(el.getAttribute("data-thumb")) || 0;
      const img = images[index];
      if (!img) return;
      const main = document.getElementById("product-main-image");
      if (main) main.setAttribute("src", img);
    });
  });

  document.getElementById("add-to-cart-btn")?.addEventListener("click", async () => {
    if (!state.user) {
      openAuthModal();
      return;
    }
    try {
      await apiFetch("/cart/items", {
        method: "POST",
        body: JSON.stringify({ product_id: product.id, quantity: 1 }),
      });
      await loadCart();
      toast("Товар добавлен в корзину");
    } catch (e) {
      toast(`Не удалось добавить: ${e.message}`);
    }
  });
}

async function renderCart() {
  await loadCart();
  const items = state.cart.items || [];
  app.innerHTML = `
    <section class="section">
      <div class="container">
        <h2>Корзина</h2>
        ${
          !items.length
            ? `<p class="muted">Корзина пуста.</p><a class="btn" href="#/catalog">Перейти в каталог</a>`
            : `
              <div class="cart-list">
                ${items
                  .map((item) => {
                    const img = normalizeImageUrl(item.product?.images?.[0] || "");
                    return `
                      <article class="cart-row">
                        ${img ? `<img src="${escapeHtml(img)}" alt="">` : `<div class="cart-ph"></div>`}
                        <div>
                          <p>${escapeHtml(item.product?.name || "Товар")}</p>
                          <p class="muted">${currency(item.unit_price)}</p>
                        </div>
                        <div class="stack-sm">
                          <div class="qty-row">
                            <button class="btn" data-cart-dec="${item.id}" type="button">−</button>
                            <span>${item.quantity}</span>
                            <button class="btn" data-cart-inc="${item.id}" type="button">+</button>
                          </div>
                          <button class="btn" data-cart-del="${item.id}" type="button">Удалить</button>
                        </div>
                      </article>
                    `;
                  })
                  .join("")}
              </div>
              <div class="cart-summary">
                <p>Итого: <strong>${currency(state.cart.totals?.subtotal || 0)}</strong></p>
                <a class="btn primary" href="#/checkout">Оформить заказ</a>
              </div>
            `
        }
      </div>
    </section>
  `;

  document.querySelectorAll("[data-cart-inc]").forEach((el) => {
    el.addEventListener("click", () => changeCartQty(el.getAttribute("data-cart-inc"), +1));
  });
  document.querySelectorAll("[data-cart-dec]").forEach((el) => {
    el.addEventListener("click", () => changeCartQty(el.getAttribute("data-cart-dec"), -1));
  });
  document.querySelectorAll("[data-cart-del]").forEach((el) => {
    el.addEventListener("click", () => removeCartItem(el.getAttribute("data-cart-del")));
  });
}

async function changeCartQty(itemId, delta) {
  const item = (state.cart.items || []).find((x) => x.id === itemId);
  if (!item) return;
  const nextQty = Math.max(0, Number(item.quantity || 0) + delta);
  try {
    await apiFetch(`/cart/items/${itemId}`, {
      method: "PUT",
      body: JSON.stringify({ quantity: nextQty }),
    });
    renderCart();
  } catch (e) {
    toast(e.message);
  }
}

async function removeCartItem(itemId) {
  try {
    await apiFetch(`/cart/items/${itemId}`, { method: "DELETE" });
    renderCart();
  } catch (e) {
    toast(e.message);
  }
}

async function renderCheckout() {
  if (!state.user) {
    app.innerHTML = `<section class="section"><div class="container"><p>Для оформления заказа нужен вход.</p><button class="btn" id="open-auth-inline">Войти</button></div></section>`;
    document.getElementById("open-auth-inline")?.addEventListener("click", openAuthModal);
    return;
  }
  await loadCart();
  const subtotal = Number(state.cart.totals?.subtotal || 0);
  if (!state.cart.items?.length) {
    app.innerHTML = `<section class="section"><div class="container"><p>Корзина пуста.</p><a class="btn" href="#/catalog">В каталог</a></div></section>`;
    return;
  }
  app.innerHTML = `
    <section class="section">
      <div class="container">
        <h2>Оформление заказа</h2>
        <div class="checkout-grid">
          <form id="checkout-form" class="panel stack-sm">
            <label>Имя<input name="name" type="text" required></label>
            <label>Телефон<input name="phone" type="tel" required></label>
            <label>Город<input name="city" type="text" required></label>
            <label>Адрес<textarea name="address" required></textarea></label>
            <label>Комментарий<textarea name="comment"></textarea></label>
            <label>Способ оплаты
              <select name="payment_method">
                <option value="card">Картой онлайн</option>
                <option value="cod">При получении</option>
              </select>
            </label>
            <button class="btn primary" type="submit">Подтвердить заказ</button>
          </form>
          <aside class="panel stack-sm">
            <h3>Ваш заказ</h3>
            ${(state.cart.items || [])
              .slice(0, 4)
              .map((x) => `<p class="muted">${escapeHtml(x.product?.name || "Товар")} × ${x.quantity}</p>`)
              .join("")}
            <p>Товаров: ${state.cart.items.length}</p>
            <p>Доставка: Бесплатно от 10 000 руб.</p>
            <p><strong>Итого: ${currency(subtotal)}</strong></p>
          </aside>
        </div>
      </div>
    </section>
  `;

  document.getElementById("checkout-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const delivery = {
      city: String(fd.get("city") || ""),
      address: String(fd.get("address") || ""),
      comment: String(fd.get("comment") || ""),
    };
    const contact = {
      name: String(fd.get("name") || ""),
      phone: String(fd.get("phone") || ""),
    };
    const payload = {
      payment_method: String(fd.get("payment_method") || "card"),
      return_url: `${location.origin}${location.pathname}#/home`,
      delivery_amount: subtotal >= 1000000 ? 0 : 50000,
      discount_amount: 0,
      delivery,
      contact,
    };
    try {
      const res = await apiFetch("/checkout", { method: "POST", body: JSON.stringify(payload) });
      if (res.confirmation_url) {
        location.href = res.confirmation_url;
        return;
      }
      toast("Заказ оформлен");
      location.hash = "#/home";
    } catch (err) {
      toast(`Ошибка checkout: ${err.message}`);
    }
  });
}

function renderStaticPage(title, html) {
  app.innerHTML = `<section class="section"><div class="container"><h2>${escapeHtml(title)}</h2><div class="stack-md">${html}</div></div></section>`;
}

function openAuthModal() {
  modalRoot.innerHTML = "";
  const tpl = document.getElementById("auth-modal-template");
  if (!tpl) return;
  modalRoot.appendChild(tpl.content.cloneNode(true));
  const overlay = modalRoot.querySelector(".modal-overlay");
  const authMessage = modalRoot.querySelector("#auth-message");
  const emailLoginForm = modalRoot.querySelector("#email-login-form");
  const smsReqForm = modalRoot.querySelector("#sms-reset-request-form");
  const smsConfirmForm = modalRoot.querySelector("#sms-reset-confirm-form");

  overlay?.addEventListener("click", (e) => {
    if (e.target?.dataset?.close) modalRoot.innerHTML = "";
  });

  emailLoginForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(emailLoginForm);
    const email = String(fd.get("email") || "").trim();
    const password = String(fd.get("password") || "");
    try {
      const form = new URLSearchParams();
      form.set("username", email);
      form.set("password", password);
      const resp = await fetch(`${API_PREFIX}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form.toString(),
      });
      if (!resp.ok) {
        const t = await resp.text();
        throw new Error(parseErrorDetail(t, "Ошибка входа"));
      }
      const token = await resp.json();
      saveTokens(token.access_token, token.refresh_token);
      await loadUser();
      await loadCart();
      modalRoot.innerHTML = "";
      toast("Вход выполнен");
      renderCurrentRoute();
    } catch (err) {
      authMessage.textContent = `Ошибка входа: ${err.message}`;
    }
  });

  smsReqForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    state.otpPhone = String(new FormData(smsReqForm).get("phone") || "");
    if (!state.otpPhone) {
      authMessage.textContent = "Введите телефон.";
      return;
    }
    try {
      await apiFetch("/auth/request-otp", {
        method: "POST",
        body: JSON.stringify({ phone: state.otpPhone }),
      });
      authMessage.textContent = "SMS-код отправлен. Введите код и новый пароль.";
    } catch (err) {
      authMessage.textContent = `Ошибка SMS: ${err.message}`;
    }
  });

  smsConfirmForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(smsConfirmForm);
    const code = String(fd.get("code") || "");
    const newPassword = String(fd.get("new_password") || "");
    if (!state.otpPhone) {
      authMessage.textContent = "Сначала запросите SMS-код.";
      return;
    }
    if (newPassword.length < 6) {
      authMessage.textContent = "Пароль должен быть не короче 6 символов.";
      return;
    }
    try {
      const otpToken = await apiFetch("/auth/login-otp", {
        method: "POST",
        body: JSON.stringify({ phone: state.otpPhone, code }),
      });
      const changeResp = await fetch(`${API_PREFIX}/auth/change-password`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${otpToken.access_token}`,
        },
        body: JSON.stringify({ new_password: newPassword }),
      });
      if (!changeResp.ok) {
        const t = await changeResp.text();
        throw new Error(parseErrorDetail(t, "Не удалось обновить пароль"));
      }
      authMessage.textContent = "Пароль обновлен. Теперь войдите по email и новому паролю.";
    } catch (err) {
      authMessage.textContent = `Ошибка обновления пароля: ${err.message}`;
    }
  });
}

function toast(message) {
  alert(message);
}

async function renderCurrentRoute() {
  const r = route();
  const parts = r.path.split("/").filter(Boolean);
  setMenuOpen(false);
  setDrawerOpen(false);

  if (r.path === "/" || r.path === "/home") return renderHome();
  if (r.path === "/catalog") return renderCatalog(r.query);
  if (r.path === "/looks") return renderStaticPage("Образы", "<p>Lookbook и образы загружаются из раздела главной страницы.</p>");
  if (parts[0] === "product" && parts[1]) return renderProduct(parts[1]);
  if (r.path === "/cart") return renderCart();
  if (r.path === "/checkout") return renderCheckout();

  if (r.path === "/about") {
    return renderStaticPage(
      "О бренде",
      `
      <p>GLAME — стильная бижутерия и украшения в минималистичной эстетике.</p>
      <p>Контент о бренде, доставке и публичной информации синхронизируется по данным glamejewelry.ru.</p>
      <p>Формат витрины: лаконичная подача, удобный каталог, быстрый checkout.</p>
      `
    );
  }
  if (r.path === "/contacts") {
    return renderStaticPage(
      "Контакты",
      `
      <p>Актуальная контактная информация и график работы публикуются на glamejewelry.ru.</p>
      <p>Условия доставки: бесплатно от 10 000 руб.</p>
      `
    );
  }
  return renderStaticPage("Страница не найдена", `<a class="btn" href="#/home">Вернуться на главную</a>`);
}

authBtn?.addEventListener("click", async () => {
  if (state.user) {
    saveTokens(null, null);
    state.user = null;
    await loadCart();
    renderCurrentRoute();
  } else {
    openAuthModal();
  }
});

drawerAuthBtn?.addEventListener("click", async () => {
  if (state.user) {
    saveTokens(null, null);
    state.user = null;
    await loadCart();
    setDrawerOpen(false);
    renderCurrentRoute();
  } else {
    setDrawerOpen(false);
    openAuthModal();
  }
});

cartBtn?.addEventListener("click", () => {
  location.hash = "#/cart";
});

searchBtn?.addEventListener("click", () => {
  location.hash = "#/catalog";
});

menuOpenLink?.addEventListener("click", (e) => {
  e.preventDefault();
  setDrawerOpen(true);
});

window.addEventListener("hashchange", renderCurrentRoute);
window.addEventListener("click", (e) => {
  const link = e.target.closest('a[href^="#/"]');
  if (link) setMenuOpen(false);
  if (e.target?.dataset?.drawerClose) setDrawerOpen(false);
});

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") setDrawerOpen(false);
});

(async function bootstrap() {
  ensureMobileMenuButton();
  await loadUser();
  await loadCart();
  if (!location.hash) location.hash = "#/home";
  renderCurrentRoute();
})();
