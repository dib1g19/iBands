django.jQuery(function($){
    function addCounter(inputSelector, max) {
        $(inputSelector).each(function() {
            var $input = $(this);
            if ($input.length === 0) {
                return;
            }
            $input.after(
                '<small class="char-counter" style="display:block;margin-bottom:10px;color:#666"></small>'
            );
            var $counter = $input.next('.char-counter');
            var updateCounter = function() {
                var len = $input.val().length;
                $counter.text(len + ' / ' + max + ' characters');
            };
            $input.on('input', updateCounter);
            updateCounter();
        });
    }
    addCounter('[id$="meta_title"]', 150);
    addCounter('[id$="meta_description"]', 300);
});