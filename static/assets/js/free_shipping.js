;(function(){
  function parseNumeric(value) {
    if (value == null) return 0
    if (typeof value === 'number') return value
    var txt = String(value).replace(/[^0-9.,]/g, '').replace(/\s+/g, '')
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

  function update(threshold) {
    var th = typeof threshold === 'number' ? threshold : 75
    var subtotal = getEffectiveSubtotal()
    var progress = Math.max(0, Math.min(100, (subtotal / th) * 100))
    var remaining = Math.max(0, th - subtotal)

    var barElem = document.getElementById('free-ship-bar')
    var textElem = document.getElementById('free-ship-text')

    if (barElem) {
      var pct = Math.round(progress)
      barElem.style.width = pct + '%'
      barElem.setAttribute('aria-valuenow', String(pct))
    }
    if (textElem) {
      if (subtotal >= th) {
        textElem.textContent = 'Поздравления! Безплатна доставка до офис е активна.'
      } else {
        textElem.textContent = 'Още ' + remaining.toFixed(2) + ' лв. до безплатна доставка до офис'
      }
    }
  }

  window.FreeShippingWidget = {
    update: update,
  }
})();


