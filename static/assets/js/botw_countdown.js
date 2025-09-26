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

    function formatYMDLocal(d) {
        var y = d.getFullYear();
        var m = String(d.getMonth() + 1).padStart(2, '0');
        var da = String(d.getDate()).padStart(2, '0');
        return y + '-' + m + '-' + da;
    }

    function isCurrentWeek(weekStartISO) {
        if (!weekStartISO) return true;
        try {
            // Parse as local date to avoid UTC shifting
            var parts = weekStartISO.split('-');
            var ws = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
            var today = new Date();
            var monday = new Date(today);
            var d = monday.getDay(); // 0=Sun
            var diffToMonday = (d === 0 ? 6 : d - 1);
            monday.setDate(today.getDate() - diffToMonday);
            return formatYMDLocal(monday) === formatYMDLocal(ws);
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


