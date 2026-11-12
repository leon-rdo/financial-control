/* Confin: comportamento comum a todas as telas. */
(function () {
  "use strict";

  var finePointer = window.matchMedia("(pointer: fine)").matches;

  function csrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }
  window.confinCsrf = csrf;

  /* ---------- tema ---------- */
  function currentTheme() {
    var t = document.documentElement.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function paintThemeButtons() {
    var dark = currentTheme() === "dark";
    document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
      b.setAttribute("aria-label", dark ? "Usar tema claro" : "Usar tema escuro");
      b.setAttribute("title", dark ? "Usar tema claro" : "Usar tema escuro");
      var sun = b.querySelector("[data-icon-sun]"), moon = b.querySelector("[data-icon-moon]");
      if (sun) sun.hidden = !dark;
      if (moon) moon.hidden = dark;
    });
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-theme-toggle]");
    if (!b) return;
    var next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (err) { /* sem armazenamento: vale só nesta página */ }
    paintThemeButtons();
  });

  /* ---------- avisos ---------- */
  var ICON_OK = '<svg class="icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>';
  var ICON_ERR = '<svg class="icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>';
  function showToast(message, type) {
    var box = document.getElementById("toasts");
    if (!box) return;
    var t = document.createElement("div");
    t.className = "toast" + (type === "error" ? " toast-error" : "");
    t.setAttribute("role", type === "error" ? "alert" : "status");
    t.innerHTML = (type === "error" ? ICON_ERR : ICON_OK) + "<span></span>" +
      '<button type="button" aria-label="Fechar aviso">&#x2715;</button>';
    t.querySelector("span").textContent = message;
    t.querySelector("button").addEventListener("click", function () { t.remove(); });
    box.appendChild(t);
    setTimeout(function () { t.remove(); }, type === "error" ? 6000 : 3200);
  }
  window.showToast = showToast;
  document.body.addEventListener("showToast", function (e) {
    showToast(e.detail.message, e.detail.type);
  });
  document.body.addEventListener("htmx:responseError", function (e) {
    if (e.detail.xhr && e.detail.xhr.status === 409) return; // já vem com aviso próprio
    showToast("Não deu para salvar agora. Confira a conexão e tente de novo.", "error");
  });
  document.body.addEventListener("htmx:sendError", function () {
    showToast("Sem conexão com o servidor. Tente de novo em instantes.", "error");
  });

  /* ---------- Select2 ---------- */
  function initSelects(root, parent) {
    if (!window.jQuery || !jQuery.fn.select2) return;
    jQuery(root).find("select.field").each(function () {
      var $el = jQuery(this);
      if ($el.hasClass("select2-hidden-accessible") || $el.is("[data-native]")) return;
      var multiple = this.multiple;
      if (!multiple && (!finePointer || this.options.length < 8)) return;
      $el.select2({
        width: "100%",
        dropdownParent: parent ? jQuery(parent) : undefined,
        placeholder: multiple ? ($el.data("placeholder") || (parent ? "Nenhuma" : "Todos")) : undefined,
        allowClear: multiple,
        language: { noResults: function () { return "Nada encontrado"; } }
      });
    });
  }
  window.confinInitSelects = initSelects;

  /* ---------- modal ---------- */
  var lastFocus = null;
  function modalEl() { return document.querySelector("#modal-container [data-modal]"); }
  function closeModal() {
    var c = document.getElementById("modal-container");
    if (!c) return;
    if (window.jQuery) jQuery(c).find("select.select2-hidden-accessible").select2("destroy");
    c.innerHTML = "";
    document.documentElement.style.overflow = "";
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
  }
  window.confinCloseModal = closeModal;
  function openedModal() {
    var m = modalEl();
    if (!m) return;
    document.documentElement.style.overflow = "hidden";
    var panel = m.querySelector(".modal-panel");
    initSelects(m, panel);
    var first = m.querySelector("[autofocus], .modal-body input:not([type=hidden]):not([type=checkbox]), .modal-body select, .modal-body textarea");
    if (first && finePointer) first.focus();
    else if (panel) { panel.setAttribute("tabindex", "-1"); panel.focus(); }
  }
  document.body.addEventListener("htmx:beforeRequest", function (e) {
    var t = e.detail.target;
    if (t && t.id === "modal-container" && !modalEl()) lastFocus = document.activeElement;
  });
  document.body.addEventListener("htmx:afterSwap", function (e) {
    if (e.detail.target && e.detail.target.id === "modal-container") openedModal();
    else initSelects(e.detail.target);
  });
  document.body.addEventListener("htmx:afterRequest", function (e) {
    var form = e.detail.elt;
    if (!form || !form.matches || !form.matches("form[data-modal-form]")) return;
    var xhr = e.detail.xhr;
    if (e.detail.successful && xhr && !xhr.getResponseHeader("HX-Retarget")) closeModal();
  });
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-modal-close]")) { e.preventDefault(); closeModal(); }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (document.querySelector(".sub-dialog:not([style*='display: none'])")) return;
    if (modalEl()) { closeModal(); return; }
    closeMenus();
    closeSheet();
  });
  // Mantém o Tab dentro do modal aberto
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Tab") return;
    var m = modalEl();
    if (!m) return;
    var f = Array.prototype.filter.call(
      m.querySelectorAll("a[href], button:not([disabled]), input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea, [tabindex]:not([tabindex='-1'])"),
      function (el) { return el.offsetParent !== null; });
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  /* ---------- confirmação (excluir, confirmar lote, desfazer...) ---------- */
  var onConfirm = null;
  function openConfirm(opts, action) {
    var dlg = document.getElementById("confirm-dialog");
    dlg.querySelector("#confirm-title").textContent = opts.title || "Excluir";
    dlg.querySelector("[data-confirm-text]").textContent = opts.text;
    var yes = dlg.querySelector("[data-confirm-yes]");
    yes.textContent = opts.yes || "Excluir";
    yes.className = "btn " + (opts.danger === false ? "btn-primary" : "btn-danger");
    onConfirm = action;
    dlg.showModal();
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-delete]");
    if (!b) return;
    e.preventDefault();
    var url = b.getAttribute("data-delete"), target = b.getAttribute("data-target");
    var what = b.getAttribute("data-what");
    openConfirm({ title: "Excluir", yes: "Excluir",
                  text: what ? "Excluir " + what + "? Não dá para desfazer." : "Excluir este registro? Não dá para desfazer." },
                function () { if (window.htmx) htmx.ajax("DELETE", url, { target: target, swap: "outerHTML" }); });
  });
  document.addEventListener("submit", function (e) {
    var form = e.target.closest("form[data-confirm]");
    if (!form || form.dataset.confirmed) return;
    e.preventDefault();
    openConfirm({ title: form.getAttribute("data-confirm-title"), text: form.getAttribute("data-confirm"),
                  yes: form.getAttribute("data-confirm-yes"), danger: form.hasAttribute("data-confirm-danger") },
                function () {
                  form.dataset.confirmed = "1";
                  form.querySelectorAll("button[type=submit]").forEach(function (b) { b.disabled = true; });
                  form.submit();
                });
  });
  document.addEventListener("click", function (e) {
    if (!e.target.closest("[data-confirm-yes]")) return;
    document.getElementById("confirm-dialog").close();
    var action = onConfirm;
    onConfirm = null;
    if (action) action();
  });

  /* ---------- menus do topo ---------- */
  function closeMenus(except) {
    document.querySelectorAll("details.nav-group[open]").forEach(function (d) { if (d !== except) d.removeAttribute("open"); });
  }
  document.addEventListener("toggle", function (e) {
    if (e.target.matches && e.target.matches("details.nav-group") && e.target.open) closeMenus(e.target);
  }, true);
  document.addEventListener("click", function (e) {
    if (!e.target.closest("details.nav-group")) closeMenus();
  });

  /* ---------- menu do celular ---------- */
  function closeSheet() {
    var s = document.getElementById("menu-sheet");
    if (s) s.classList.remove("is-open");
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-sheet-open]")) {
      document.getElementById("menu-sheet").classList.add("is-open");
    } else if (e.target.closest("[data-sheet-close]")) {
      closeSheet();
    }
  });

  /* ---------- confirmado / pendente (transações) ---------- */
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-toggle-confirmed]");
    if (!b) return;
    e.preventDefault();
    fetch(b.getAttribute("data-toggle-confirmed"), { method: "POST", headers: { "X-CSRFToken": csrf() } })
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (data) {
        if (b.getAttribute("data-after") === "reload") {
          // No painel, confirmar muda os números da faixa e o "Vem aí": recarrega tudo
          try { sessionStorage.setItem("confin-toast", data.confirmed ? "Lançamento confirmado." : "Lançamento voltou a pendente."); } catch (err) { /* sem armazenamento */ }
          location.reload();
          return;
        }
        b.classList.toggle("status-ok", data.confirmed);
        b.classList.toggle("status-pending", !data.confirmed);
        b.querySelector("span").textContent = data.confirmed ? "Confirmada" : "Pendente";
        b.setAttribute("aria-pressed", data.confirmed ? "true" : "false");
      })
      .catch(function () { showToast("Não deu para mudar o status. Tente de novo.", "error"); });
  });

  /* ---------- cadastro rápido dentro de um formulário ---------- */
  document.addEventListener("alpine:init", function () {
    window.Alpine.data("inlineCreate", function () {
      return {
        kind: null, saving: false, error: "", form: {},
        open: function (kind, defaults) {
          this.kind = kind; this.error = "";
          this.form = Object.assign({ name: "" }, defaults || {});
          var root = this.$root;
          this.$nextTick(function () {
            var first = root.querySelector(".sub-dialog:not([style*='display: none']) [data-inline-first]");
            if (first) first.focus();
          });
        },
        close: function () { this.kind = null; },
        save: function (url, selectId, label) {
          var self = this;
          if (!self.form.name) { self.error = "Informe o nome."; return; }
          self.saving = true; self.error = "";
          fetch(url + "?inline=1", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
            body: JSON.stringify(self.form)
          }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
            .then(function (res) {
              if (!res.ok || !res.d.success) { self.error = res.d.error || "Não deu para criar."; return; }
              var sel = document.getElementById(selectId);
              if (sel) {
                var opt = new Option(res.d.object.name, String(res.d.object.id), true, true);
                sel.appendChild(opt);
                if (window.jQuery) jQuery(sel).trigger("change");
              }
              showToast(label + " criada: " + res.d.object.name + ".");
              self.close();
            })
            .catch(function () { self.error = "Sem conexão. Tente de novo."; })
            .finally(function () { self.saving = false; });
        }
      };
    });
  });

  /* ---------- busca de banco e de CNPJ ---------- */
  document.addEventListener("alpine:init", function () {
    window.Alpine.data("bankPicker", function (url) {
      return {
        banks: [], loading: true, error: "",
        init: function () {
          var self = this;
          fetch(url).then(function (r) { return r.json(); })
            .then(function (d) { if (d.success) self.banks = d.banks; else self.error = d.error || "Não deu para carregar os bancos."; })
            .catch(function () { self.error = "Não deu para carregar a lista de bancos. Preencha à mão."; })
            .finally(function () { self.loading = false; });
        },
        pick: function () {
          var name = this.$refs.pick.value;
          var bank = this.banks.find(function (b) { return b.name === name; });
          if (!bank) return;
          var form = this.$root;
          var n = form.querySelector("input[name=name]"), b = form.querySelector("input[name=bank]");
          if (n && !n.value) n.value = bank.name;
          if (b) b.value = bank.bank;
        }
      };
    });
    window.Alpine.data("cnpjLookup", function (url) {
      return {
        loading: false, error: "", ok: false, digits: 0,
        init: function () {
          var self = this, doc = this.$root.querySelector("input[name=document]");
          if (!doc) return;
          var count = function () { self.digits = doc.value.replace(/\D/g, "").length; };
          doc.addEventListener("input", count); count();
        },
        lookup: function () {
          var self = this, form = this.$root, doc = form.querySelector("input[name=document]");
          var cnpj = doc.value.replace(/\D/g, "");
          if (cnpj.length !== 14) { self.error = "Digite os 14 números do CNPJ."; return; }
          self.loading = true; self.error = ""; self.ok = false;
          fetch(url + "?cnpj=" + cnpj).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
            .then(function (res) {
              if (!res.ok || !res.d.success) { self.error = res.d.error || "Não deu para consultar."; return; }
              var map = { name: res.d.data.name, email: res.d.data.email, phone: res.d.data.phone };
              Object.keys(map).forEach(function (k) { var el = form.querySelector("input[name=" + k + "]"); if (el && map[k]) el.value = map[k]; });
              self.ok = true;
            })
            .catch(function () { self.error = "Sem conexão. Tente de novo."; })
            .finally(function () { self.loading = false; });
        }
      };
    });
  });

  document.addEventListener("DOMContentLoaded", function () {
    paintThemeButtons();
    try {
      var pendingToast = sessionStorage.getItem("confin-toast");
      if (pendingToast) { sessionStorage.removeItem("confin-toast"); showToast(pendingToast); }
    } catch (err) { /* sem armazenamento */ }
    // No celular, os filtros começam fechados (a menos que algum esteja em uso)
    if (window.matchMedia("(max-width: 860px)").matches) {
      document.querySelectorAll("details.filters[data-active='0']").forEach(function (d) { d.removeAttribute("open"); });
    }
    initSelects(document.querySelector("main"));
  });
})();
