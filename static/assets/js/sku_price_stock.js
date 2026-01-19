(function () {
  var BGN_PER_EUR = 1.95583;
  function formatDualCurrency(val) {
    var bgn = parseFloat(val);
    if (isNaN(bgn)) { return val; }
    var eur = bgn / BGN_PER_EUR;
    var fmt = { minimumFractionDigits: 2, maximumFractionDigits: 2 };
    var eurText = eur.toLocaleString('bg-BG', fmt) + ' €';
    var bgnText = bgn.toLocaleString('bg-BG', fmt) + ' лв.';
    return eurText + ' / ' + bgnText;
  }

  function recompute(cfg) {
    var saleEl = document.querySelector('.price-sale');
    var regEls = document.querySelectorAll('.price-regular');
    var stockEl = document.querySelector('.stock-indicator');
    var selSize = document.querySelector('input[name="size"]:checked');
    var selModel = document.querySelector('input[name="model"]:checked');
    var sizeVal = selSize ? selSize.value : null;
    var modelVal = selModel ? selModel.value : null;
    var delta = 0;
    var qty = null;

    if (sizeVal && modelVal) {
      var hitBoth = cfg.skuData.find(function (r) { return r.size === sizeVal && r.model === modelVal; });
      if (hitBoth) { delta = hitBoth.delta || 0; qty = hitBoth.qty; }
    }
    if (qty === null && sizeVal) {
      var hitSize = cfg.skuData.find(function (r) { return r.size === sizeVal && r.model === null; });
      if (hitSize) { delta = hitSize.delta || 0; qty = hitSize.qty; }
    }
    if (qty === null && modelVal) {
      var hitModel = cfg.skuData.find(function (r) { return r.size === null && r.model === modelVal; });
      if (hitModel) { delta = hitModel.delta || 0; qty = hitModel.qty; }
    }

    var newRegular = cfg.baseRegular + delta;
    if (cfg.hasSale) {
      var newSale = (cfg.baseSale || 0) + delta;
      if (saleEl) saleEl.textContent = formatDualCurrency(newSale);
      regEls.forEach(function (el) { el.textContent = formatDualCurrency(newRegular); });
    } else {
      regEls.forEach(function (el) { el.textContent = formatDualCurrency(newRegular); });
    }

    if (stockEl && qty !== null) {
      if (qty > 0) {
        stockEl.textContent = 'В наличност';
        stockEl.classList.remove('bg-danger');
        stockEl.classList.add('bg-success');
      } else {
        stockEl.textContent = 'Няма наличност';
        stockEl.classList.remove('bg-success');
        stockEl.classList.add('bg-danger');
      }
    }

    // Update quantity selector to max available for current selection (or max across all)
    var maxForSelection = (qty !== null) ? Math.max(0, parseInt(qty, 10) || 0) : (cfg.maxQty || 0);
    var qtySelect = document.querySelector('select.quantity');
    if (qtySelect) {
      var prev = parseInt(qtySelect.value, 10) || 1;
      var limit = Math.max(0, maxForSelection);
      // Rebuild options 1..limit (or 1 if 0 available)
      var newHtml = '';
      var upper = limit > 0 ? limit : 1;
      for (var i = 1; i <= upper; i++) {
        newHtml += '<option value="' + i + '">' + i + '</option>';
      }
      qtySelect.innerHTML = newHtml;
      // Restore previous selection if still valid, else set 1
      if (limit > 0 && prev >= 1 && prev <= limit) {
        qtySelect.value = String(prev);
        qtySelect.disabled = false;
      } else if (limit > 0) {
        qtySelect.value = String(limit);
        qtySelect.disabled = false;
      } else {
        qtySelect.value = '1';
        qtySelect.disabled = true;
      }
      // Also disable add_to_cart when none available
      var addBtn = document.querySelector('.add_to_cart');
      if (addBtn) {
        if (limit > 0) { addBtn.removeAttribute('disabled'); }
        else { addBtn.setAttribute('disabled', 'disabled'); }
      }
    }
  }

  function init() {
    var cfg = (window.SkuPriceConfig || {});
    if (!cfg || !Array.isArray(cfg.skuData)) return;
    // Precompute max available across all SKUs for initial quantity selector,
    // but honor an explicit maxQty provided by server (e.g., product.stock when no SKUs)
    var computedMax = 0;
    try {
      computedMax = cfg.skuData.reduce(function (acc, r) {
        var q = parseInt(r.qty, 10) || 0; return Math.max(acc, q);
      }, 0);
    } catch (e) { computedMax = 0; }
    if (typeof cfg.maxQty === 'number') {
      cfg.maxQty = Math.max(cfg.maxQty, computedMax);
    } else if (typeof cfg.fallbackMaxQty === 'number') {
      cfg.maxQty = Math.max(cfg.fallbackMaxQty || 0, computedMax);
    } else {
      cfg.maxQty = computedMax;
    }
    var handler = function () { recompute(cfg); };
    document.addEventListener('change', function (ev) {
      if (ev.target && (ev.target.name === 'size' || ev.target.name === 'model')) {
        handler();
      }
    });
    // Initial run
    handler();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();


