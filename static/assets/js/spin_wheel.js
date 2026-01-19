// Reusable Spin Wheel module
// Usage: window.initSpinWheel({
//   canvasId, legendId, btnId, resultId, couponId,
//   resetIso, countdownIds: { nextId, prizeId },
//   prizesJson, spinUrl, canSpin, csrfToken
// })

(function(){
  function getCookie(name) {
    var m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : null;
  }

  var BGN_PER_EUR = 1.95583;
  function formatDualCurrency(value) {
    var bgn = parseFloat(value);
    if (isNaN(bgn)) return '-';
    var eur = bgn / BGN_PER_EUR;
    var fmt = { minimumFractionDigits: 2, maximumFractionDigits: 2 };
    var eurText = eur.toLocaleString('bg-BG', fmt) + ' €';
    var bgnText = bgn.toLocaleString('bg-BG', fmt) + ' лв.';
    return eurText + ' / ' + bgnText;
  }

  function startCountdown(targetIso, el){
    if (!targetIso || !el) return;
    var end = new Date(targetIso);
    function tick(){
      var now = new Date();
      var diff = Math.max(0, end - now);
      var hrs = Math.floor(diff / 3600000); diff -= hrs*3600000;
      var mins = Math.floor(diff / 60000); diff -= mins*60000;
      var secs = Math.floor(diff / 1000);
      el.textContent = String(hrs).padStart(2,'0')+":"+String(mins).padStart(2,'0')+":"+String(secs).padStart(2,'0');
      if (end - now <= 0) return;
      requestAnimationFrame(function(){ setTimeout(tick, 250); });
    }
    tick();
  }

  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }

  function hexToRgba(hex, alpha) {
    if (!hex) return 'rgba(255,255,255,'+(alpha==null?1:alpha)+')';
    var h = (''+hex).replace('#','');
    if (h.length === 3) h = h.split('').map(function(c){ return c+c; }).join('');
    var r = parseInt(h.substring(0,2), 16);
    var g = parseInt(h.substring(2,4), 16);
    var b = parseInt(h.substring(4,6), 16);
    return 'rgba('+r+','+g+','+b+','+(alpha==null?1:alpha)+')';
  }

  window.initSpinWheel = function(config){
    if (!config) return;
    var canvas = document.getElementById(config.canvasId);
    var ctx = canvas && canvas.getContext ? canvas.getContext('2d') : null;
    var wrapperEl = canvas ? canvas.closest('.wheel-wrapper') : null;
    var legendEl = config.legendId ? document.getElementById(config.legendId) : null;
    var btn = config.btnId ? document.getElementById(config.btnId) : null;
    var resultEl = config.resultId ? document.getElementById(config.resultId) : null;
    var couponEl = config.couponId ? document.getElementById(config.couponId) : null;
    // Milestones UI elements
    var msProgressEl = config.milestoneProgressId ? document.getElementById(config.milestoneProgressId) : null;
    var msLabelEl = config.milestoneLabelId ? document.getElementById(config.milestoneLabelId) : null;
    var msAchievedEl = null; // removed separate achieved list; show codes inline next to legend items
    // Optional center image for hub
    var hubImage = null;
    if (config.centerImageUrl) {
      hubImage = new Image();
      hubImage.onload = function(){
        if (ctx) drawWheelAt(0);
      };
      hubImage.src = config.centerImageUrl;
    }

    if (config.countdownIds) {
      if (config.countdownIds.nextId) startCountdown(config.resetIso, document.getElementById(config.countdownIds.nextId));
      if (config.countdownIds.prizeId) startCountdown(config.resetIso, document.getElementById(config.countdownIds.prizeId));
    }

    var segments;
    try {
      var prizes = Array.isArray(config.prizesJson) ? config.prizesJson : JSON.parse(config.prizesJson || '[]');
      segments = (Array.isArray(prizes) && prizes.length)
        ? prizes.map(function(p){ return { label: p.label, color: p.color || '#ffe082' }; })
        : [
            { label: 'Опитай пак утре', color: '#0074D9' },
            { label: 'Отстъпка 3%', color: '#fff9c4' },
            { label: 'Отстъпка 5%', color: '#ffe082' },
            { label: 'Безплатна доставка', color: '#fff59d' },
            { label: 'Mystery Box', color: '#ffecb3' }
          ];
    } catch(e) {
      segments = [
        { label: 'Опитай пак утре', color: '#0074D9' },
        { label: 'Отстъпка 3%', color: '#fff9c4' },
        { label: 'Отстъпка 5%', color: '#ffe082' },
        { label: 'Безплатна доставка', color: '#fff59d' },
        { label: 'Mystery Box', color: '#ffecb3' }
      ];
    }

    // Milestones data
    var milestones = [];
    var milestoneProgress = { spins: 0, achieved: [] };
    try { milestones = Array.isArray(config.milestonesJson) ? config.milestonesJson : JSON.parse(config.milestonesJson || '[]'); } catch(e) { milestones = []; }
    try { milestoneProgress = typeof config.milestoneProgressJson === 'string' ? JSON.parse(config.milestoneProgressJson || '{}') : (config.milestoneProgressJson || milestoneProgress); } catch(e) {}
    var achievedDetails = [];
    try { achievedDetails = Array.isArray(config.achievedDetailsJson) ? config.achievedDetailsJson : JSON.parse(config.achievedDetailsJson || '[]'); } catch(e) { achievedDetails = []; }

    function updateMilestoneBar(progress){
      if (!msProgressEl && !msLabelEl && !msAchievedEl) return;
      var spins = (progress && typeof progress.spins === 'number') ? progress.spins : 0;
      var ach = (progress && Array.isArray(progress.achieved)) ? progress.achieved.slice() : [];
      ach.sort(function(a,b){ return a-b; });
      // Determine previous and next thresholds (show total spins / next milestone)
      var prev = 0; var next = spins;
      if (Array.isArray(milestones) && milestones.length) {
        var sorted = milestones.slice().sort(function(a,b){
          var A = (typeof a === 'number') ? a : a.threshold_spins;
          var B = (typeof b === 'number') ? b : b.threshold_spins;
          return A - B;
        });
        for (var i=0;i<sorted.length;i++) {
          var t = (typeof sorted[i] === 'number') ? sorted[i] : sorted[i].threshold_spins;
          if (t <= spins) prev = t;
          if (t > spins) { next = t; break; }
        }
        if (next === spins) {
          var last = (typeof sorted[sorted.length - 1] === 'number') ? sorted[sorted.length - 1] : sorted[sorted.length - 1].threshold_spins;
          next = last;
        }
      }
      var base = prev;
      var goal = next;
      var denom = Math.max(1, goal - base);
      var num = Math.max(0, Math.min(spins - base, denom));
      var pct = Math.round((num / denom) * 100);
      if (msProgressEl) msProgressEl.style.width = pct + '%';
      if (msLabelEl) msLabelEl.textContent = spins + ' / ' + goal;
      // No separate achieved list; we will inject achieved ticks/codes inline in legend below
    }
    updateMilestoneBar(milestoneProgress);

    if (legendEl) {
      legendEl.innerHTML = segments.map(function(s){
        return '<li class="mb-1"><span style="display:inline-block;width:12px;height:12px;background:'+s.color+';border:1px solid #ccc;margin-right:6px;"></span>'+s.label+'</li>';
      }).join('');
    }

    var TAU = Math.PI * 2;
    var displayedSize = 320;
    function setupHiDPI(){
      if (!canvas || !ctx) return;
      var dpr = Math.max(1, window.devicePixelRatio || 1);
      var wrapperWidth = (wrapperEl && wrapperEl.clientWidth) ? wrapperEl.clientWidth : 320;
      displayedSize = Math.max(260, Math.min(wrapperWidth, 480));
      canvas.width = Math.floor(displayedSize * dpr);
      canvas.height = Math.floor(displayedSize * dpr);
      canvas.style.width = displayedSize + 'px';
      canvas.style.height = displayedSize + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function drawWheelAt(angle){
      if (!ctx || !canvas) return;
      setupHiDPI();
      var center = displayedSize/2;
      var radius = (displayedSize/2) - 10;
      var slice = TAU / segments.length;
      var m = ctx.getTransform();
      ctx.setTransform(1,0,0,1,0,0);
      ctx.clearRect(0,0,canvas.width,canvas.height);
      ctx.setTransform(m);
      ctx.save();
      ctx.translate(center, center);
      // subtle outer ring
      ctx.lineWidth = Math.max(2, Math.floor(displayedSize * 0.02));
      ctx.strokeStyle = 'rgba(255,255,255,0.65)';
      for (var i=0;i<segments.length;i++){
        var start = i*slice + (angle||0);
        var end = start + slice;
        ctx.beginPath(); ctx.moveTo(0,0); ctx.arc(0,0,radius,start,end); ctx.closePath();
        ctx.fillStyle = hexToRgba(segments[i].color, 0.85); ctx.fill();
        ctx.stroke();
        var mid = start + slice/2;
        ctx.save(); ctx.rotate(mid);
        // Text with slight shadow for readability
        ctx.fillStyle = '#111';
        ctx.shadowColor = 'rgba(255,255,255,0.35)';
        ctx.shadowBlur = 0;
        // dynamic fit: shrink font until the label fits between hub and rim
        var hubForText = Math.max(14, Math.floor(displayedSize * 0.06));
        var innerPad = Math.max(8, Math.floor(displayedSize * 0.02));
        var xEnd = radius - 12;
        var available = Math.max(20, xEnd - (hubForText + innerPad));
        var fs = Math.max(10, Math.floor(displayedSize * 0.042));
        ctx.font = fs+'px Roboto, Arial, sans-serif';
        while (ctx.measureText(segments[i].label).width > available && fs > 10) {
          fs -= 1;
          ctx.font = fs+'px Roboto, Arial, sans-serif';
        }
        ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
        ctx.fillText(segments[i].label, xEnd, 0);
        ctx.restore();
      }
      // soft gloss
      var gloss = ctx.createRadialGradient(0,0, radius*0.1, 0,0, radius);
      gloss.addColorStop(0, 'rgba(255,255,255,0.18)');
      gloss.addColorStop(1, 'rgba(255,255,255,0.02)');
      ctx.beginPath(); ctx.arc(0,0,radius,0,TAU); ctx.closePath();
      ctx.fillStyle = gloss; ctx.fill();

      // center hub circle to smooth segment intersections (optionally draw image)
      var hubR = Math.max(14, Math.floor(displayedSize * 0.06));
      if (hubImage && hubImage.complete) {
        ctx.save();
        ctx.beginPath(); ctx.arc(0,0,hubR,0,TAU); ctx.closePath();
        ctx.clip();
        // white base then slightly smaller image for a visible ring
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(-hubR, -hubR, hubR*2, hubR*2);
        var imgR = Math.floor(hubR * 0.82);
        ctx.drawImage(hubImage, -imgR, -imgR, imgR*2, imgR*2);
        ctx.restore();
      } else {
        ctx.beginPath(); ctx.arc(0,0,hubR,0,TAU); ctx.closePath();
        ctx.fillStyle = '#ffffff';
        ctx.fill();
      }
      ctx.lineWidth = Math.max(2, Math.floor(displayedSize * 0.01));
      ctx.strokeStyle = 'rgba(0,0,0,0.08)';
      ctx.stroke();
      ctx.restore();
    }

    if (canvas) {
      var hubFactor = 0.12; // radius as a fraction of wheel size
      function canSpin(){
        return !!btn && !btn.disabled && config.spinUrl && config.canSpin !== false && !(wrapperEl && wrapperEl.classList.contains('is-spinning'));
      }
      function inHub(e){
        var rect = canvas.getBoundingClientRect();
        var cx = rect.left + rect.width/2;
        var cy = rect.top + rect.height/2;
        var dx = e.clientX - cx;
        var dy = e.clientY - cy;
        var hubR = Math.min(rect.width, rect.height) * hubFactor;
        return (dx*dx + dy*dy) <= (hubR*hubR);
      }
      canvas.addEventListener('mousemove', function(e){ canvas.style.cursor = (canSpin() && inHub(e)) ? 'pointer' : ''; });
      canvas.addEventListener('mouseleave', function(){ canvas.style.cursor = ''; });
      canvas.addEventListener('click', function(e){ if (canSpin() && inHub(e)) { btn && btn.click(); } });
    }

    function animateTo(targetRotation, durationMs, onDone) {
      var start = performance.now();
      var baseRotation = 0;
      function frame(now) {
        var t = Math.min(1, (now - start) / durationMs);
        var eased = easeOutCubic(t);
        var angle = baseRotation + (targetRotation * eased);
        drawWheelAt(angle);
        if (t < 1) requestAnimationFrame(frame); else if (onDone) onDone();
      }
      requestAnimationFrame(frame);
    }

    function spinToLabel(label, onDone){
      if (!ctx) return;
      var idx = Math.max(0, segments.findIndex(function(s){ return s.label === label; }));
      var slice = TAU / segments.length;
      var segmentMid = idx * slice + slice/2;
      var baseTarget = -Math.PI/2 - segmentMid;
      baseTarget += 5 * TAU;
      var jitter = (Math.random()-0.5) * (slice*0.5);
      var finalTarget = baseTarget + jitter;
      animateTo(finalTarget, 5000, onDone);
    }

    if (ctx) {
      drawWheelAt(0);
      window.addEventListener('resize', function(){ drawWheelAt(0); });
    } else {
      var fb = null;
      if (config.fallbackId) fb = document.getElementById(config.fallbackId);
      if (!fb) {
        var computedId = (config.canvasId||'').replace('canvas','wheel-fallback');
        fb = document.getElementById(computedId);
      }
      if (!fb && wrapperEl) {
        fb = wrapperEl.querySelector('#wheel-fallback, .fallback-wheel');
      }
      if (fb) fb.classList.remove('d-none');
    }

    if (btn && config.spinUrl && config.canSpin !== false) {
      btn.addEventListener('click', function(){
        if (btn.disabled) return;
        btn.disabled = true;
        if (wrapperEl) wrapperEl.classList.add('is-spinning');
        if (resultEl) resultEl.textContent = '';
        if (couponEl) couponEl.textContent = '';
        var csrf = config.csrfToken || getCookie('csrftoken') || '';
        fetch(config.spinUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRFToken': csrf },
          body: ''
        }).then(function(res){
            if (!res.ok) {
              if (res.status === 401) {
                return res.json().then(function(j){
                  throw { auth: true, login_url: j && j.login_url, message: (j && j.message) || 'Моля, влезте в профила си.' };
                });
              }
              return res.json().then(function(j){ throw new Error((j && j.message) || 'Грешка при завъртане'); });
            }
            return res.json();
        })
          .then(function(data){
            if (!data.success) throw new Error(data.message || 'Грешка при завъртане');
            spinToLabel(data.label, function(){
              if (wrapperEl) wrapperEl.classList.remove('is-spinning');
              if (resultEl) resultEl.textContent = data.label;
              if (couponEl) {
                if (data.coupon_code) {
                  couponEl.innerHTML = 'Код за отстъпка: <strong>'+data.coupon_code+'</strong> ( -'+data.discount_percent+'% )';
                } else if (data.prize_type === 'free_shipping') {
                  couponEl.textContent = 'Спечели: Безплатна доставка за следваща поръчка.';
                } else if (data.prize_type === 'mystery_box_min_total') {
                  couponEl.textContent = 'Спечели: Mystery Box при поръчка над '+formatDualCurrency(data.min_order_total);
                }
                if (data.milestone) {
                  var m = data.milestone;
                  var extra = ' ';
                  if (m.prize_type === 'discount_percent' && m.coupon_code) {
                    extra = ' Милестон награда ('+m.threshold_spins+' завъртания): -'+m.discount_percent+'% с код <strong>'+m.coupon_code+'</strong>.';
                  } else if (m.prize_type === 'free_shipping') {
                    extra = ' Милестон награда ('+m.threshold_spins+' завъртания): Безплатна доставка.';
                  }
                  var div = document.createElement('div');
                  div.className = 'alert alert-success mt-2';
                  div.innerHTML = '<i class="fas fa-trophy me-1"></i>'+extra;
                  couponEl.appendChild(div);
                }
              }
              // Update milestone progress client-side (assume +1 spin)
              try {
                milestoneProgress.spins = (milestoneProgress.spins || 0) + 1;
                if (data.milestone && data.milestone.threshold_spins) {
                  var t = parseInt(data.milestone.threshold_spins, 10);
                  if (!isNaN(t)) {
                    milestoneProgress.achieved = milestoneProgress.achieved || [];
                    if (milestoneProgress.achieved.indexOf(t) === -1) milestoneProgress.achieved.push(t);
                    // push detail so legend reflects code inline
                    achievedDetails = achievedDetails || [];
                    var exists = achievedDetails.some(function(d){ return parseInt(d.threshold_spins,10) === t; });
                    if (!exists) achievedDetails.push({
                      threshold_spins: t,
                      prize_type: data.milestone.prize_type,
                      discount_percent: data.milestone.discount_percent,
                      coupon_code: data.milestone.coupon_code || null,
                      label: data.milestone.label || ''
                    });
                  }
                }
                updateMilestoneBar(milestoneProgress);
              } catch(e) {}
            });
          })
          .catch(function(err){
            if (wrapperEl) wrapperEl.classList.remove('is-spinning');
            if (err && err.auth && resultEl) {
              var signIn = err.login_url || (config.signInUrl ? (config.signInUrl + '?next=' + encodeURIComponent(window.location.href)) : '#');
              var signUp = config.signUpUrl ? (config.signUpUrl + '?next=' + encodeURIComponent(window.location.pathname)) : '#';
              var msg = err.message || 'Моля, влезте или се регистрирайте, за да завъртите.';
              resultEl.innerHTML = '<span class="spin-auth-prompt">'+ msg +
                ' <a class="btn btn-sm btn-primary ms-2" href="'+signIn+'">Влез</a>'+
                ' <a class="btn btn-sm btn-outline-primary ms-2" href="'+signUp+'">Регистрация</a>';
              return;
            }
            if (resultEl) resultEl.textContent = err && err.message ? err.message : 'Опитай отново утре.';
          })
          .finally(function(){
            if (wrapperEl) wrapperEl.classList.remove('is-spinning');
            btn.disabled = true;
          });
      });
    }
  };
})();


