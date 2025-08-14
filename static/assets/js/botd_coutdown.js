(function() {
    function updateCountdown() {
        var now = new Date();
        var end = new Date(now);
        end.setHours(23, 59, 59, 999);
        var diff = end - now;
        if (diff < 0) diff = 0;

        var hrs = String(Math.floor(diff / 3600000)).padStart(2, '0');
        var mins = String(Math.floor((diff % 3600000) / 60000)).padStart(2, '0');
        var secs = String(Math.floor((diff % 60000) / 1000)).padStart(2, '0');

        var el = document.getElementById('botd-countdown');
        if (el) el.textContent = hrs + ':' + mins + ':' + secs;
    }
    updateCountdown();
    setInterval(updateCountdown, 1000);
})();