"use strict";

const API = "/api/v1";
const state = {
  token: sessionStorage.getItem("stockflow_token"),
  user: null,
  products: [],
  sales: [],
  users: [],
  loading: 0,
};

const roleLabels = {
  owner: "Proprietário",
  admin: "Administrador",
  manager: "Gerente",
  salesperson: "Vendedor",
  viewer: "Consulta",
};

const movementLabels = {
  initial: "Saldo inicial",
  adjustment: "Ajuste",
  sale: "Venda",
  sale_cancellation: "Cancelamento",
};

const pageMetadata = {
  dashboard: ["PAINEL", "Visão geral"],
  products: ["ESTOQUE", "Produtos"],
  sales: ["COMERCIAL", "Vendas"],
  users: ["ACESSOS", "Usuários"],
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function money(value) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(value || 0));
}

function dateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function initials(name) {
  return String(name || "U")
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function can(...roles) {
  return state.user && roles.includes(state.user.role);
}

function setLoading(enabled) {
  state.loading += enabled ? 1 : -1;
  state.loading = Math.max(0, state.loading);
  $("#loading-overlay").classList.toggle("hidden", state.loading === 0);
}

function toast(message, type = "success") {
  const element = document.createElement("div");
  element.className = `toast ${type}`;
  element.textContent = message;
  $("#toast-region").append(element);
  window.setTimeout(() => element.remove(), 4200);
}

function errorMessage(payload, fallback) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail)) {
    return payload.detail.map((item) => item.msg).join(" · ");
  }
  return fallback;
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body && !(options.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API}${path}`, { ...options, headers });
  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && state.token) logout(false);
    throw new Error(errorMessage(payload, `Erro HTTP ${response.status}`));
  }
  return payload;
}

async function publicRequest(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorMessage(payload, `Erro HTTP ${response.status}`));
  return payload;
}

function saveToken(token) {
  state.token = token;
  sessionStorage.setItem("stockflow_token", token);
}

function logout(showMessage = true) {
  state.token = null;
  state.user = null;
  sessionStorage.removeItem("stockflow_token");
  $("#app-shell").classList.add("hidden");
  $("#auth-screen").classList.remove("hidden");
  if (showMessage) toast("Sessão encerrada.");
}

function showAuthTab(tab) {
  const isLogin = tab === "login";
  $("#login-tab").classList.toggle("active", isLogin);
  $("#register-tab").classList.toggle("active", !isLogin);
  $("#login-form").classList.toggle("hidden", !isLogin);
  $("#register-form").classList.toggle("hidden", isLogin);
}

async function authenticate() {
  if (!state.token) return logout(false);
  setLoading(true);
  try {
    state.user = await request("/auth/me");
    $("#auth-screen").classList.add("hidden");
    $("#app-shell").classList.remove("hidden");
    $("#user-name").textContent = state.user.full_name;
    $("#user-role").textContent = roleLabels[state.user.role] || state.user.role;
    $("#user-avatar").textContent = initials(state.user.full_name);
    $("#welcome-title").textContent = `Olá, ${state.user.full_name.split(" ")[0]}!`;
    $("#users-nav").classList.toggle("hidden", !can("owner", "admin"));
    $("#new-product-button").classList.toggle(
      "hidden",
      !can("owner", "admin", "manager"),
    );
    $("#new-sale-button").classList.toggle("hidden", can("viewer"));
    $(".quick-sale").classList.toggle("hidden", can("viewer"));
    await switchView("dashboard");
  } catch (error) {
    logout(false);
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const body = new URLSearchParams({
    username: data.get("email"),
    password: data.get("password"),
  });
  setLoading(true);
  try {
    const token = await publicRequest("/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    saveToken(token.access_token);
    await authenticate();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function handleRegister(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  setLoading(true);
  try {
    const registration = await publicRequest("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    saveToken(registration.access_token);
    toast("Organização criada com sucesso.");
    await authenticate();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function switchView(view) {
  if (view === "users" && !can("owner", "admin")) return;
  $$(".view").forEach((element) => element.classList.remove("active"));
  $$(".nav-item").forEach((element) => {
    element.classList.toggle("active", element.dataset.view === view);
  });
  $(`#view-${view}`).classList.add("active");
  $("#page-kicker").textContent = pageMetadata[view][0];
  $("#page-title").textContent = pageMetadata[view][1];
  $(".sidebar").classList.remove("open");

  setLoading(true);
  try {
    if (view === "dashboard") await loadDashboard();
    if (view === "products") await loadProducts();
    if (view === "sales") await loadSales();
    if (view === "users") await loadUsers();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

function statusPill(status) {
  const completed = status === "completed";
  return `<span class="status ${completed ? "success" : "neutral"}">${completed ? "Concluída" : "Cancelada"}</span>`;
}

function emptyRow(columns, message) {
  return `<tr class="empty-row"><td colspan="${columns}">${escapeHtml(message)}</td></tr>`;
}

async function loadDashboard() {
  const summary = await request("/dashboard/summary");
  $("#metric-products").textContent = summary.active_products;
  $("#metric-stock-units").textContent = `${summary.stock_units} unidades em estoque`;
  $("#metric-low-stock").textContent = summary.low_stock_products;
  $("#metric-inventory-value").textContent = money(summary.inventory_value);
  $("#metric-revenue").textContent = money(summary.sales_revenue);
  $("#metric-sales-count").textContent = `${summary.completed_sales} vendas concluídas`;

  $("#recent-sales-body").innerHTML = summary.recent_sales.length
    ? summary.recent_sales
        .map(
          (sale) => `<tr>
            <td><strong>${escapeHtml(sale.number)}</strong></td>
            <td>${escapeHtml(sale.customer_name || "Consumidor final")}</td>
            <td>${dateTime(sale.created_at)}</td>
            <td>${statusPill(sale.status)}</td>
            <td class="align-right"><strong>${money(sale.total)}</strong></td>
          </tr>`,
        )
        .join("")
    : emptyRow(5, "Nenhuma venda registrada ainda.");
}

async function loadProducts() {
  const search = $("#product-search").value.trim();
  const lowStock = $("#low-stock-filter").checked;
  const query = new URLSearchParams({ limit: "100", offset: "0" });
  if (search) query.set("search", search);
  if (lowStock) query.set("low_stock", "true");
  const page = await request(`/products?${query}`);
  state.products = page.items;
  renderProducts(page.total);
}

function renderProducts(total) {
  const canEdit = can("owner", "admin", "manager");
  const canDelete = can("owner", "admin");
  $("#products-body").innerHTML = state.products.length
    ? state.products
        .map((product) => {
          const low = product.is_low_stock;
          return `<tr>
            <td><div class="cell-title"><strong>${escapeHtml(product.name)}</strong><span>${escapeHtml(product.description || "Sem descrição")}</span></div></td>
            <td>${escapeHtml(product.sku)}</td>
            <td class="align-right">${money(product.price)}</td>
            <td class="align-center"><strong>${product.stock_quantity}</strong> / mín. ${product.minimum_stock}</td>
            <td><span class="status ${low ? "warning" : "success"}">${low ? "Estoque baixo" : "Disponível"}</span></td>
            <td><div class="actions-cell">
              <button class="table-action" data-product-action="movements" data-id="${product.id}">Histórico</button>
              ${canEdit ? `<button class="table-action" data-product-action="stock" data-id="${product.id}">Estoque</button><button class="table-action" data-product-action="edit" data-id="${product.id}">Editar</button>` : ""}
              ${canDelete ? `<button class="table-action danger" data-product-action="delete" data-id="${product.id}">Desativar</button>` : ""}
            </div></td>
          </tr>`;
        })
        .join("")
    : emptyRow(6, "Nenhum produto encontrado.");
  $("#products-pagination").textContent = `${total} produto${total === 1 ? "" : "s"} encontrado${total === 1 ? "" : "s"}`;
}

function openProductDialog(product = null) {
  const form = $("#product-form");
  form.reset();
  form.elements.product_id.value = product?.id || "";
  $("#product-dialog-title").textContent = product ? "Editar produto" : "Novo produto";
  $("#initial-stock-label").classList.toggle("hidden", Boolean(product));
  if (product) {
    form.elements.name.value = product.name;
    form.elements.sku.value = product.sku;
    form.elements.price.value = product.price;
    form.elements.minimum_stock.value = product.minimum_stock;
    form.elements.description.value = product.description || "";
  }
  $("#product-dialog").showModal();
}

async function handleProductSubmit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form));
  const productId = data.product_id;
  delete data.product_id;
  data.price = Number(data.price);
  data.minimum_stock = Number(data.minimum_stock);
  if (productId) delete data.stock_quantity;
  else data.stock_quantity = Number(data.stock_quantity || 0);

  setLoading(true);
  try {
    await request(productId ? `/products/${productId}` : "/products", {
      method: productId ? "PATCH" : "POST",
      body: JSON.stringify(data),
    });
    $("#product-dialog").close();
    toast(productId ? "Produto atualizado." : "Produto cadastrado.");
    await loadProducts();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

function openStockDialog(product) {
  const form = $("#stock-form");
  form.reset();
  form.elements.product_id.value = product.id;
  $("#stock-product-name").textContent = `${product.name} · saldo atual: ${product.stock_quantity}`;
  $("#stock-dialog").showModal();
}

async function handleStockSubmit(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  const productId = data.product_id;
  setLoading(true);
  try {
    await request(`/products/${productId}/stock-adjustments`, {
      method: "POST",
      body: JSON.stringify({ quantity: Number(data.quantity), reason: data.reason }),
    });
    $("#stock-dialog").close();
    toast("Ajuste de estoque registrado.");
    await loadProducts();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function showMovements(product) {
  setLoading(true);
  try {
    const page = await request(`/products/${product.id}/stock-movements?limit=100`);
    $("#info-kicker").textContent = "MOVIMENTAÇÕES";
    $("#info-title").textContent = product.name;
    $("#info-content").innerHTML = page.items.length
      ? `<div class="movement-list">${page.items
          .map(
            (item) => `<div class="movement-item"><strong>${item.quantity_change > 0 ? "+" : ""}${item.quantity_change}</strong><div><strong>${escapeHtml(movementLabels[item.movement_type] || item.movement_type)}</strong><br><span>${escapeHtml(item.reason)}</span></div><span>${dateTime(item.created_at)} · saldo ${item.balance_after}</span></div>`,
          )
          .join("")}</div>`
      : '<p class="muted">Nenhuma movimentação encontrada.</p>';
    $("#info-dialog").showModal();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function handleProductAction(event) {
  const button = event.target.closest("[data-product-action]");
  if (!button) return;
  const product = state.products.find((item) => item.id === button.dataset.id);
  if (!product) return;
  const action = button.dataset.productAction;
  if (action === "edit") return openProductDialog(product);
  if (action === "stock") return openStockDialog(product);
  if (action === "movements") return showMovements(product);
  if (action === "delete") {
    if (!window.confirm(`Desativar o produto “${product.name}”?`)) return;
    setLoading(true);
    try {
      await request(`/products/${product.id}`, { method: "DELETE" });
      toast("Produto desativado.");
      await loadProducts();
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setLoading(false);
    }
  }
}

async function loadSales() {
  const query = new URLSearchParams({ limit: "100", offset: "0" });
  const status = $("#sale-status-filter").value;
  if (status) query.set("status", status);
  const page = await request(`/sales?${query}`);
  state.sales = page.items;
  renderSales();
}

function renderSales() {
  const canCancel = can("owner", "admin", "manager");
  $("#sales-body").innerHTML = state.sales.length
    ? state.sales
        .map(
          (sale) => `<tr>
            <td><strong>${escapeHtml(sale.number)}</strong></td>
            <td>${escapeHtml(sale.customer_name || "Consumidor final")}</td>
            <td>${dateTime(sale.created_at)}</td>
            <td>${sale.items.reduce((sum, item) => sum + item.quantity, 0)}</td>
            <td>${statusPill(sale.status)}</td>
            <td class="align-right"><strong>${money(sale.total)}</strong></td>
            <td><div class="actions-cell"><button class="table-action" data-sale-action="details" data-id="${sale.id}">Detalhes</button>${canCancel && sale.status === "completed" ? `<button class="table-action danger" data-sale-action="cancel" data-id="${sale.id}">Cancelar</button>` : ""}</div></td>
          </tr>`,
        )
        .join("")
    : emptyRow(7, "Nenhuma venda encontrada.");
}

async function ensureProducts() {
  if (state.products.length) return;
  const page = await request("/products?limit=100");
  state.products = page.items;
}

function saleProductOptions() {
  return state.products
    .filter((product) => product.is_active && product.stock_quantity > 0)
    .map(
      (product) => `<option value="${product.id}">${escapeHtml(product.name)} · ${escapeHtml(product.sku)} · ${product.stock_quantity} un. · ${money(product.price)}</option>`,
    )
    .join("");
}

function addSaleItemRow() {
  const row = document.createElement("div");
  row.className = "sale-item-row";
  row.innerHTML = `<label>Produto<select name="product_id" required><option value="">Selecione</option>${saleProductOptions()}</select></label><label>Quantidade<input name="quantity" type="number" min="1" value="1" required></label><button class="icon-button remove-sale-item" type="button" aria-label="Remover item">×</button>`;
  $("#sale-items").append(row);
  updateSaleTotal();
}

async function openSaleDialog() {
  setLoading(true);
  try {
    await ensureProducts();
    if (!state.products.some((product) => product.stock_quantity > 0)) {
      return toast("Cadastre um produto com estoque antes de vender.", "error");
    }
    $("#sale-form").reset();
    $("#sale-items").innerHTML = "";
    addSaleItemRow();
    $("#sale-dialog").showModal();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

function updateSaleTotal() {
  let total = 0;
  $$(".sale-item-row", $("#sale-items")).forEach((row) => {
    const product = state.products.find(
      (item) => item.id === $("select", row).value,
    );
    const quantity = Number($("input", row).value || 0);
    if (product) total += Number(product.price) * quantity;
  });
  $("#sale-total-value").textContent = money(total);
}

async function handleSaleSubmit(event) {
  event.preventDefault();
  const items = $$(".sale-item-row", $("#sale-items")).map((row) => ({
    product_id: $("select", row).value,
    quantity: Number($("input", row).value),
  }));
  const uniqueProducts = new Set(items.map((item) => item.product_id));
  if (uniqueProducts.size !== items.length) {
    return toast("Cada produto pode aparecer apenas uma vez.", "error");
  }
  const customerName = event.currentTarget.elements.customer_name.value.trim();
  setLoading(true);
  try {
    const sale = await request("/sales", {
      method: "POST",
      body: JSON.stringify({ customer_name: customerName || null, items }),
    });
    $("#sale-dialog").close();
    state.products = [];
    toast(`Venda ${sale.number} concluída.`);
    await loadSales();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

function showSaleDetails(sale) {
  $("#info-kicker").textContent = "VENDA";
  $("#info-title").textContent = sale.number;
  $("#info-content").innerHTML = `<p class="muted">${escapeHtml(sale.customer_name || "Consumidor final")} · ${dateTime(sale.created_at)}</p><div class="table-wrap"><table><thead><tr><th>Produto</th><th>Quantidade</th><th class="align-right">Unitário</th><th class="align-right">Subtotal</th></tr></thead><tbody>${sale.items.map((item) => `<tr><td><div class="cell-title"><strong>${escapeHtml(item.product_name)}</strong><span>${escapeHtml(item.sku)}</span></div></td><td>${item.quantity}</td><td class="align-right">${money(item.unit_price)}</td><td class="align-right"><strong>${money(item.subtotal)}</strong></td></tr>`).join("")}</tbody></table></div><div class="sale-total"><span>Status: ${sale.status === "completed" ? "Concluída" : "Cancelada"}</span><strong>${money(sale.total)}</strong></div>`;
  $("#info-dialog").showModal();
}

async function handleSaleAction(event) {
  const button = event.target.closest("[data-sale-action]");
  if (!button) return;
  const sale = state.sales.find((item) => item.id === button.dataset.id);
  if (!sale) return;
  if (button.dataset.saleAction === "details") return showSaleDetails(sale);
  if (!window.confirm(`Cancelar a venda ${sale.number} e devolver o estoque?`)) return;
  setLoading(true);
  try {
    await request(`/sales/${sale.id}/cancel`, { method: "POST" });
    state.products = [];
    toast("Venda cancelada e estoque restaurado.");
    await loadSales();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function loadUsers() {
  const page = await request("/users?limit=100");
  state.users = page.items;
  $("#users-body").innerHTML = state.users.length
    ? state.users
        .map(
          (user) => `<tr><td><div class="cell-title"><strong>${escapeHtml(user.full_name)}</strong><span>${user.id === state.user.id ? "Você" : "Membro da equipe"}</span></div></td><td>${escapeHtml(user.email)}</td><td>${escapeHtml(roleLabels[user.role] || user.role)}</td><td><span class="status ${user.is_active ? "success" : "danger"}">${user.is_active ? "Ativo" : "Inativo"}</span></td><td>${dateTime(user.created_at)}</td><td><div class="actions-cell">${canChangeUser(user) ? `<button class="table-action ${user.is_active ? "danger" : ""}" data-user-action="toggle" data-id="${user.id}">${user.is_active ? "Desativar" : "Reativar"}</button>` : ""}</div></td></tr>`,
        )
        .join("")
    : emptyRow(6, "Nenhum usuário encontrado.");
}

function canChangeUser(user) {
  const level = { viewer: 1, salesperson: 2, manager: 3, admin: 4, owner: 5 };
  return user.id !== state.user.id && level[state.user.role] > level[user.role];
}

function openUserDialog() {
  const roleOptions = can("owner")
    ? ["admin", "manager", "salesperson", "viewer"]
    : ["manager", "salesperson", "viewer"];
  $("#user-form").reset();
  $("#user-form select[name=role]").innerHTML = roleOptions
    .map((role) => `<option value="${role}">${roleLabels[role]}</option>`)
    .join("");
  $("#user-dialog").showModal();
}

async function handleUserSubmit(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  setLoading(true);
  try {
    await request("/users", { method: "POST", body: JSON.stringify(data) });
    $("#user-dialog").close();
    toast("Usuário criado com sucesso.");
    await loadUsers();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function handleUserAction(event) {
  const button = event.target.closest("[data-user-action]");
  if (!button) return;
  const user = state.users.find((item) => item.id === button.dataset.id);
  if (!user) return;
  const action = user.is_active ? "desativar" : "reativar";
  if (!window.confirm(`Deseja ${action} ${user.full_name}?`)) return;
  setLoading(true);
  try {
    await request(`/users/${user.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !user.is_active }),
    });
    toast(`Usuário ${user.is_active ? "desativado" : "reativado"}.`);
    await loadUsers();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

function bindEvents() {
  $("#login-tab").addEventListener("click", () => showAuthTab("login"));
  $("#register-tab").addEventListener("click", () => showAuthTab("register"));
  $("#login-form").addEventListener("submit", handleLogin);
  $("#register-form").addEventListener("submit", handleRegister);
  $("#demo-login").addEventListener("click", () => {
    $("#login-form").elements.email.value = "demo@stockflow.dev";
    $("#login-form").elements.password.value = "Demo@StockFlow123";
    $("#login-form").requestSubmit();
  });
  $("#logout-button").addEventListener("click", () => logout());
  $("#mobile-menu").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
  $$(".nav-item").forEach((button) =>
    button.addEventListener("click", () => switchView(button.dataset.view)),
  );
  $$('[data-go="sales"]').forEach((button) =>
    button.addEventListener("click", () => switchView("sales")),
  );
  $(".quick-sale").addEventListener("click", openSaleDialog);

  $("#new-product-button").addEventListener("click", () => openProductDialog());
  $("#product-form").addEventListener("submit", handleProductSubmit);
  $("#stock-form").addEventListener("submit", handleStockSubmit);
  $("#products-body").addEventListener("click", handleProductAction);
  let productSearchTimer;
  $("#product-search").addEventListener("input", () => {
    window.clearTimeout(productSearchTimer);
    productSearchTimer = window.setTimeout(() => loadProducts().catch((error) => toast(error.message, "error")), 300);
  });
  $("#low-stock-filter").addEventListener("change", () => loadProducts().catch((error) => toast(error.message, "error")));

  $("#new-sale-button").addEventListener("click", openSaleDialog);
  $("#add-sale-item").addEventListener("click", addSaleItemRow);
  $("#sale-items").addEventListener("change", updateSaleTotal);
  $("#sale-items").addEventListener("input", updateSaleTotal);
  $("#sale-items").addEventListener("click", (event) => {
    const remove = event.target.closest(".remove-sale-item");
    if (!remove) return;
    if ($$(".sale-item-row", $("#sale-items")).length === 1) return toast("A venda precisa de ao menos um item.", "error");
    remove.closest(".sale-item-row").remove();
    updateSaleTotal();
  });
  $("#sale-form").addEventListener("submit", handleSaleSubmit);
  $("#sales-body").addEventListener("click", handleSaleAction);
  $("#sale-status-filter").addEventListener("change", () => loadSales().catch((error) => toast(error.message, "error")));

  $("#new-user-button").addEventListener("click", openUserDialog);
  $("#user-form").addEventListener("submit", handleUserSubmit);
  $("#users-body").addEventListener("click", handleUserAction);
  $$(".close-dialog").forEach((button) =>
    button.addEventListener("click", () => button.closest("dialog").close()),
  );
}

bindEvents();
authenticate();
