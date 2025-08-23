;(function(){
  function relocateFreeShip(){
    var box = document.getElementById('free-ship-box');
    var coupon = document.getElementById('coupon-box');
    var anchor = document.getElementById('free-ship-anchor');
    if (!box || !coupon || !anchor) return;
    var isSmall = window.matchMedia('(max-width: 991.98px)').matches;
    if (isSmall) {
      coupon.parentNode.insertBefore(box, coupon);
    } else {
      if (anchor.parentNode) anchor.parentNode.insertBefore(box, anchor.nextSibling);
    }
  }

  function relocateCardAlert(){
    var alert = document.getElementById('payment-card-alert');
    var paymentAnchor = document.getElementById('payment-alert-anchor');
    var sidebarAnchor = document.getElementById('sidebar-card-alert-anchor');
    if (!alert || !paymentAnchor || !sidebarAnchor) return;
    var isSmall = window.matchMedia('(max-width: 991.98px)').matches;
    if (isSmall) {
      paymentAnchor.parentNode.insertBefore(alert, paymentAnchor.nextSibling);
    } else {
      if (sidebarAnchor.parentNode) sidebarAnchor.parentNode.insertBefore(alert, sidebarAnchor.nextSibling);
    }
  }

  function init(){
    relocateFreeShip();
    relocateCardAlert();
  }

  window.addEventListener('resize', init);
  document.addEventListener('DOMContentLoaded', init);
})();


