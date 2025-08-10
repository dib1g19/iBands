document.addEventListener("DOMContentLoaded", function () {
    function addCounter(selector, max) {
        document.querySelectorAll(selector).forEach(function (input) {
            const counter = document.createElement("small");
            counter.className = "char-counter";
            counter.style.cssText = "display:block;margin-bottom:10px;color:#666";
            input.insertAdjacentElement("afterend", counter);

            function updateCounter() {
                const len = input.value.length;
                counter.textContent = `${len} / ${max} characters`;
            }

            input.addEventListener("input", updateCounter);
            updateCounter();
        });
    }

    addCounter('[id$="meta_title"]', 150);
    addCounter('[id$="meta_description"]', 300);
});