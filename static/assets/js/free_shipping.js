;(function(){
  function formatDualCurrency(value) {
    var eur = parseFloat(value)
    if (isNaN(eur)) return '-'
    var fmt = { minimumFractionDigits: 2, maximumFractionDigits: 2 }
    return eur.toLocaleString('bg-BG', fmt) + ' €'
  }
  function extractCurrencyValue(raw) {
    var match = String(raw).match(/([0-9.,]+)\s*€/i)
    if (!match) return null
    return match[1]
  }
  function parseNumeric(value) {
    if (value == null) return 0
    if (typeof value === 'number') return value
    var raw = String(value)
    var extracted = extractCurrencyValue(raw)
    var txt = extracted != null ? extracted : raw
    txt = String(txt).replace(/[^0-9.,]/g, '').replace(/\s+/g, '')
    // Replace comma with dot if dot absent
    if (txt.indexOf('.') === -1 && txt.indexOf(',') !== -1) {
      txt = txt.replace(',', '.')
    } else if (txt.indexOf('.') !== -1 && txt.indexOf(',') !== -1) {
      // Remove thousand separators
      txt = txt.replace(/,/g, '')
    }
    var n = parseFloat(txt)
    return isNaN(n) ? 0 : n
  }

  function getEffectiveSubtotal() {
    // Checkout page hidden spans
    var subElem = document.getElementById('backend-order-subtotal')
    var savedElem = document.getElementById('backend-order-saved')
    if (subElem) {
      var subtotal = parseNumeric(subElem.dataset && subElem.dataset.value)
      var saved = parseNumeric(savedElem && savedElem.dataset && savedElem.dataset.value)
      return Math.max(0, subtotal - saved)
    }
    // Cart page hidden span
    var cartSub = document.getElementById('cart-order-subtotal')
    if (cartSub) {
      return parseNumeric(cartSub.dataset && cartSub.dataset.value)
    }
    // Fallback: try .cart_sub_total text
    var cartText = document.querySelector('.cart_sub_total')
    if (cartText) return parseNumeric(cartText.textContent)
    return 0
  }

  function rulesSource() {
    return document.getElementById('free-ship-box')
  }

  function prizeReminder() {
    var source = rulesSource()
    if (!source || !source.dataset.prizeMinimums) return null
    var minimums
    try { minimums = JSON.parse(source.dataset.prizeMinimums) } catch (e) { return null }
    if (!Array.isArray(minimums) || !minimums.length) return null
    if (minimums.indexOf(null) !== -1) return { minimum: null }
    var nums = minimums.map(Number).filter(function (n) { return !isNaN(n) })
    if (!nums.length) return null
    nums.sort(function (a, b) { return a - b })
    return { minimum: nums[0] }
  }

  function officeThreshold() {
    var source = rulesSource()
    var parsed = source ? parseFloat(source.dataset.officeThreshold) : NaN
    return isNaN(parsed) ? 40 : parsed
  }

  function prizeApplies() {
    var prize = prizeReminder()
    if (!prize) return false
    return prize.minimum == null || getEffectiveSubtotal() >= prize.minimum
  }

  function update() {
    var prize = prizeReminder()
    var subtotal = getEffectiveSubtotal()
    var th = prize ? (prize.minimum == null ? 0 : prize.minimum) : officeThreshold()
    var progress = th <= 0 ? 100 : Math.max(0, Math.min(100, (subtotal / th) * 100))
    var remaining = Math.max(0, th - subtotal)

    var barElem = document.getElementById('free-ship-bar')
    var textElem = document.getElementById('free-ship-text')

    if (barElem) {
      var pct = Math.round(progress)
      barElem.style.width = pct + '%'
      barElem.setAttribute('aria-valuenow', String(pct))
    }
    if (textElem) {
      if (prize && (prize.minimum == null || subtotal >= prize.minimum)) {
        textElem.textContent = 'Имаш награда: безплатна доставка до офис или автомат.'
      } else if (prize) {
        textElem.textContent = 'Имаш награда: безплатна доставка до офис или автомат. Още ' + formatDualCurrency(remaining) + ' до нея.'
      } else if (subtotal >= th) {
        textElem.textContent = 'Поздравления! Безплатна доставка до офис или автомат е активна.'
      } else {
        textElem.textContent = 'Още ' + formatDualCurrency(remaining) + ' до безплатна доставка до офис или автомат'
      }
    }
  }

  window.FreeShippingWidget = {
    update: update,
    goods: getEffectiveSubtotal,
    officeThreshold: officeThreshold,
    prizeApplies: prizeApplies,
  }
})();


