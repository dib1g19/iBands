(function(){
  function qs(sel){ return document.querySelector(sel); }
  function qsa(sel){ return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  function getParam(name){
    var m = new URLSearchParams(window.location.search);
    return m.get(name);
  }

  var offset = parseInt(getParam('h') || '0', 10) || 0;
  var MAX_ITEMS = 32; // soft cap for appended cards on mobile
  function updateTopButtonVisibility(){
    var loadTop = qs('#botw-load-top');
    if (!loadTop) return;
    var cards = qsa('#botw-history > div');
    loadTop.style.display = (cards.length >= MAX_ITEMS) ? 'inline-block' : 'none';
  }
  // We intentionally do not pass date; history is anchored to latest

  function fetchHistory(newOffset, opts){
    opts = opts || { append: false };
    var params = new URLSearchParams();
    params.set('h', String(newOffset));
    fetch('/band-of-the-week/history?' + params.toString(), { headers: { 'X-Requested-With': 'XMLHttpRequest' }})
      .then(function(r){ return r.json(); })
      .then(function(resp){
        if (!resp.success) return;
        var container = qs('#botw-history');
        if (!container) return;
        if (opts.append) {
          container.insertAdjacentHTML('beforeend', resp.html);
          // Trim if exceeding cap: remove oldest cards from top
          var cards = qsa('#botw-history > div');
          if (cards.length > MAX_ITEMS) {
            var excess = cards.length - MAX_ITEMS;
            for (var i = 0; i < excess; i++) {
              if (cards[i] && cards[i].parentNode === container) container.removeChild(cards[i]);
            }
          }
          updateTopButtonVisibility();
          reapplyHistoryMarkers();
        } else {
          container.style.opacity = '0';
          setTimeout(function(){
            container.innerHTML = resp.html;
            container.style.opacity = '1';
            // Important: update visibility after DOM is replaced
            updateTopButtonVisibility();
            reapplyHistoryMarkers();
          }, 150);
        }
        offset = resp.h;
        var prevBtn = qs('#botw-prev');
        var nextBtn = qs('#botw-next');
        if (prevBtn) prevBtn.disabled = !resp.has_prev;
        if (nextBtn) nextBtn.disabled = !resp.has_next;
        var loadMore = qs('#botw-load-more');
        if (loadMore && !resp.has_next) {
          loadMore.disabled = true;
          loadMore.classList.add('disabled');
        }
      });
  }

  function reapplyHistoryMarkers(){
    var container = qs('#botw-history');
    if (!container) return;
    var selectedISO = container.getAttribute('data-selected-week');
    var currentISO = container.getAttribute('data-current-week');
    var cards = qsa('#botw-history .botw-card');
    cards.forEach(function(card){
      // Determine card week start from href query (?date=YYYY-MM-DD)
      try {
        var link = card.parentElement.querySelector('a[href*="?date="]');
        var m = /[?&]date=([0-9]{4}-[0-9]{2}-[0-9]{2})/.exec(link ? link.getAttribute('href') : '');
        var weekISO = m ? m[1] : null;
        if (!weekISO) return;
        // Selected highlight
        if (selectedISO && weekISO === selectedISO) {
          card.classList.add('botw-selected');
        }
        // Future ribbon (re-add if missing)
        if (currentISO && weekISO > currentISO) {
          if (!card.querySelector('.botw-ribbon')) {
            var rib = document.createElement('div');
            rib.className = 'botw-ribbon';
            rib.textContent = 'Очаквайте скоро';
            card.appendChild(rib);
          }
        }
      } catch (e) {}
    });
  }

  function init(){
    var prev = qs('#botw-prev');
    var next = qs('#botw-next');
    var loadMore = qs('#botw-load-more');
    var loadTop = qs('#botw-load-top');
    if (prev){
      prev.addEventListener('click', function(){ if (!prev.disabled) fetchHistory(Math.max(0, offset - 1), { append: false }); });
    }
    if (next){
      next.addEventListener('click', function(){ if (!next.disabled) fetchHistory(offset + 1, { append: false }); });
    }
    if (loadMore){
      loadMore.addEventListener('click', function(){ fetchHistory(offset + 1, { append: true }); 
      });
    }
    if (loadTop){
      loadTop.addEventListener('click', function(){
        // Optimistically hide the button; it will re-show when needed later
        loadTop.style.display = 'none';
        fetchHistory(0, { append: false });
        var loadMore = qs('#botw-load-more');
        if (loadMore) {
          loadMore.disabled = false;
          loadMore.classList.remove('disabled');
        }
      });
    }
    updateTopButtonVisibility();
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();


