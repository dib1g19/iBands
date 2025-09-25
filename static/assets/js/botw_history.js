(function(){
  function qs(sel){ return document.querySelector(sel); }
  function qsa(sel){ return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  function getParam(name){
    var m = new URLSearchParams(window.location.search);
    return m.get(name);
  }

  var offset = parseInt(getParam('h') || '0', 10) || 0;
  // We intentionally do not pass date; history is anchored to latest

  function fetchHistory(newOffset){
    var params = new URLSearchParams();
    params.set('h', String(newOffset));
    fetch('/band-of-the-week/history?' + params.toString(), { headers: { 'X-Requested-With': 'XMLHttpRequest' }})
      .then(function(r){ return r.json(); })
      .then(function(resp){
        if (!resp.success) return;
        var container = qs('#botw-history');
        if (!container) return;
        container.style.opacity = '0';
        setTimeout(function(){
          container.innerHTML = resp.html;
          container.style.opacity = '1';
        }, 150);
        offset = resp.h;
        var prevBtn = qs('#botw-prev');
        var nextBtn = qs('#botw-next');
        if (prevBtn) prevBtn.disabled = !resp.has_prev;
        if (nextBtn) nextBtn.disabled = !resp.has_next;
      });
  }

  function init(){
    var prev = qs('#botw-prev');
    var next = qs('#botw-next');
    if (prev){
      prev.addEventListener('click', function(){ if (!prev.disabled) fetchHistory(Math.max(0, offset - 1)); });
    }
    if (next){
      next.addEventListener('click', function(){ if (!next.disabled) fetchHistory(offset + 1); });
    }
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();


