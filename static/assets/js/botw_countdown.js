(function() {
    function getWeekEnd(now) {
        // Week ends on Sunday 23:59:59.999
        var day = now.getDay(); // 0=Sun ... 6=Sat
        var daysUntilSunday = (7 - day) % 7; // if today is Sun (0), remain 0 days
        var end = new Date(now);
        end.setDate(now.getDate() + daysUntilSunday);
        end.setHours(23, 59, 59, 999);
        return end;
    }

    function isCurrentWeek(weekStartISO) {
        if (!weekStartISO) return true;
        try {
            var ws = new Date(weekStartISO);
            var today = new Date();
            var monday = new Date(today);
            var d = monday.getDay(); // 0=Sun
            var diffToMonday = (d === 0 ? 6 : d - 1);
            monday.setDate(today.getDate() - diffToMonday);
            // Compare year-month-day
            return monday.toISOString().slice(0,10) === ws.toISOString().slice(0,10);
        } catch(e) { return true; }
    }

    function updateCountdown() {
        var now = new Date();
        var end = getWeekEnd(now);
        var diff = end - now;
        if (diff < 0) diff = 0;

        var days = Math.floor(diff / 86400000);
        var hrs = String(Math.floor((diff % 86400000) / 3600000)).padStart(2, '0');
        var mins = String(Math.floor((diff % 3600000) / 60000)).padStart(2, '0');
        var secs = String(Math.floor((diff % 60000) / 1000)).padStart(2, '0');

        var el = document.getElementById('botw-countdown');
        if (el) {
            var weekStartISO = el.getAttribute('data-week-start');
            if (!isCurrentWeek(weekStartISO)) {
                days = 0; hrs = '00'; mins = '00'; secs = '00';
            }
            var dayLabel = '';
            if (days > 0) {
                // Bulgarian pluralization (simple): 1 ден, else дни
                dayLabel = days + ' ' + (days === 1 ? 'ден' : 'дни') + ' ';
            }
            el.textContent = dayLabel + hrs + ':' + mins + ':' + secs;
        }
    }
    updateCountdown();
    setInterval(updateCountdown, 1000);
})();


