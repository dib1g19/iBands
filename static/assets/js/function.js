$(document).ready(function () {
    const Toast = Swal.mixin({
        toast: true,
        position: "top",
        showConfirmButton: false,
        timer: 2000,
        timerProgressBar: true,
    });
    const BGN_PER_EUR = 1.95583;
    function parseNumber(value) {
        if (value === null || value === undefined) return 0;
        const text = String(value).replace(/\s/g, "").replace(/,/g, "");
        const num = parseFloat(text);
        return isNaN(num) ? 0 : num;
    }
    function formatDualCurrency(value) {
        const bgn = parseNumber(value);
        const eur = bgn / BGN_PER_EUR;
        const fmt = { minimumFractionDigits: 2, maximumFractionDigits: 2 };
        const eurText = eur.toLocaleString("bg-BG", fmt) + " €";
        const bgnText = bgn.toLocaleString("bg-BG", fmt) + " лв.";
        return eurText + " / " + bgnText;
    }
    function generateCartId() {
        // Retrieve the value of "cartId" from local storage and assign it to the variable 'ls_cartId'
        const ls_cartId = localStorage.getItem("cartId");

        // Check if the retrieved value is null (i.e., "cartId" does not exist in local storage)
        if (ls_cartId === null) {
            // Initialize an empty string variable 'cartId' to store the new cart ID
            var cartId = "";

            // Loop 10 times to generate a 10-digit random cart ID
            for (var i = 0; i < 10; i++) {
                // Generate a random number between 0 and 9, convert it to an integer, and append it to 'cartId'
                cartId += Math.floor(Math.random() * 10);
            }

            // Store the newly generated 'cartId' in local storage with the key "cartId"
            localStorage.setItem("cartId", cartId);
        }

        // Return the existing cart ID from local storage if it was found, otherwise return the newly generated 'cartId'
        return ls_cartId || cartId;
    }

    $(document).on("click", ".add_to_cart", function () {
        const button_el = $(this);
        const id = button_el.attr("data-id");
        const qty = $(".quantity").val();
        const size = $("input[name='size']:checked").val();
        const model = $("input[name='model']:checked").val();
        const cart_id = generateCartId();
        // Mystery box extras (if present on page)
        const note = $("#mystery-note").length ? $("#mystery-note").val() : undefined;
        const selectedDevices = $("input[name='mystery_devices[]']:checked, input[name='mystery_devices']:checked").map(function () { return $(this).val(); }).get();

        const payload = {
            id: id,
            qty: qty,
            size: size,
            model: model,
            cart_id: cart_id,
        };
        if (note) payload.note = note;
        if (selectedDevices && selectedDevices.length) payload.mystery_devices = selectedDevices;

        $.ajax({
            url: "/add-to-cart/",
            data: payload,
            success: function (response) {
                console.log(response);
                Toast.fire({
                    icon: "success",
                    html:
                        response.message +
                        '<br><a href="/cart/" class="btn btn-sm btn-primary mt-2 w-100">Виж количката</a>',
                });
                if (typeof gtag === "function") {
                    const gtagData = {
                        "items": [{
                            "id": id,
                            "name": button_el.attr("data-name") || "",
                            "category": button_el.attr("data-category") || "",
                            "price": parseFloat(button_el.attr("data-price")),
                            "quantity": parseInt(qty),
                            "currency": "BGN"
                        }]
                    };
                    gtag('event', 'add_to_cart', gtagData);
                }
                if (typeof fbq === "function") {
                    const fbqData = {
                        content_ids: [id],
                        content_name: button_el.attr("data-name") || "",
                        content_category: button_el.attr("data-category") || "",
                        value: parseFloat(button_el.attr("data-price")),
                        currency: "BGN",
                        contents: [{
                            id: id,
                            quantity: parseInt(qty)
                        }]
                    };
                    fbq('track', 'AddToCart', fbqData);
                }
                $(".total_cart_items").text(response.total_cart_items);
            },
            error: function (xhr, status, error) {
                console.log("Error Status: " + xhr.status); // Logs the status code, e.g., 400
                console.log("Response Text: " + xhr.responseText); // Logs the actual response text (JSON string)
                try {
                    let errorResponse = JSON.parse(xhr.responseText);
                    console.log("Error Message: " + errorResponse.error);
                    Toast.fire({
                        icon: "error",
                        title: errorResponse.error,
                    });
                } catch (e) {
                    console.log("Could not parse JSON response");
                }
                console.log("Error: " + xhr.status + " - " + error);
            },
        });
    });

    $(document).on("click", ".update_cart_qty", function () {
        const button_el = $(this);
        const update_type = button_el.attr("data-update_type");
        // const product_id = button_el.attr("data-product_id"); // removed: not needed
        const item_id = button_el.attr("data-item_id");
        const cart_id = generateCartId();
        var current_qty = parseInt($(".item-qty-" + item_id).val());

        // Default to increment/decrement by 1
        var change_by = update_type === "increase" ? 1 : -1;

        // Prevent decreasing below 1
        if (update_type === "decrease" && current_qty <= 1) {
            return;
        }

        // Optimistically update the input field for UX
        $(".item-qty-" + item_id).val(current_qty + change_by);

        $.ajax({
            url: "/add-to-cart/",
            data: {
                item_id: item_id,
                qty: change_by,
                cart_id: cart_id,
            },
            success: function (response) {
                Toast.fire({
                    icon: "success",
                    title: response.message,
                });
                if (update_type === "increase") {
                    button_el.html('<i class="fas fa-plus fa-xs"></i>');
                } else {
                    button_el.html('<i class="fas fa-minus fa-xs"></i>');
                }
                $(".item-qty-" + item_id).val(response.current_qty);
                $(".item_sub_total_" + item_id).text(formatDualCurrency(response.item_sub_total));
                $(".cart_sub_total").text(formatDualCurrency(response.cart_sub_total));
                var hiddenSub = document.getElementById('cart-order-subtotal');
                if (hiddenSub) {
                    var numeric = (response.cart_sub_total || '0').toString().replace(/\s/g, '').replace(/,/g, '');
                    hiddenSub.setAttribute('data-value', numeric);
                }
                // Update promo free units display if provided
                if (response.promo_free_units_by_item) {
                    try {
                        Object.keys(response.promo_free_units_by_item).forEach(function(key){
                            var free = response.promo_free_units_by_item[key];
                            var el = document.getElementById('promo-free-' + key);
                            if (!el) return;
                            if (free > 0) {
                                el.textContent = "+" + free + " бр. безплатно";
                                el.classList.remove('d-none');
                            } else {
                                el.textContent = "";
                                el.classList.add('d-none');
                            }
                            // If all units of this line are free, show unit price as 0.00 for that line
                            var qtyInput = document.querySelector('.item-qty-' + key);
                            var qtyVal = qtyInput ? parseInt(qtyInput.value) : null;
                            var priceEl = document.getElementById('item-price-' + key);
                            if (priceEl && qtyVal !== null) {
                                if (free >= qtyVal) {
                                    priceEl.textContent = formatDualCurrency(0);
                                } else {
                                    // Restore to unit price text from data attribute
                                    var unit = priceEl.getAttribute('data-unit-price') || '';
                                    if (unit) {
                                        try {
                                            priceEl.textContent = formatDualCurrency(unit);
                                        } catch(e) {
                                            priceEl.textContent = formatDualCurrency(unit);
                                        }
                                    }
                                }
                            }
                        });
                    } catch (e) {}
                }
                try { if (window.FreeShippingWidget) window.FreeShippingWidget.update(75) } catch(e) {}
            },
            error: function (xhr, status, error) {
                // Rollback change if there is an error
                $(".item-qty-" + item_id).val(current_qty);
                try {
                    let errorResponse = JSON.parse(xhr.responseText);
                    console.log("Error Message: " + errorResponse.error);
                    alert(errorResponse.error);
                } catch (e) {
                    console.log("Could not parse JSON response");
                }
                console.log("Error: " + xhr.status + " - " + error);
            },
        });
    });

    $(document).on("click", ".delete_cart_item", function () {
        const button_el = $(this);
        const item_id = button_el.attr("data-item_id");
        const product_id = button_el.attr("data-product_id");
        const cart_id = generateCartId();

        $.ajax({
            url: "/delete-cart-item/",
            data: {
                id: product_id,
                item_id: item_id,
                cart_id: cart_id,
            },
            beforeSend: function () {
                button_el.html('<i class="fas fa-spinner fa-spin"></i>');
            },
            success: function (response) {
                Toast.fire({
                    icon: "success",
                    title: response.message,
                });
                $(".total_cart_items").text(response.total_cart_items);
                $(".cart_sub_total").text(formatDualCurrency(response.cart_sub_total));
                var hiddenSub = document.getElementById('cart-order-subtotal');
                if (hiddenSub) {
                    var numeric = (response.cart_sub_total || '0').toString().replace(/\s/g, '').replace(/,/g, '');
                    hiddenSub.setAttribute('data-value', numeric);
                }
                try { if (window.FreeShippingWidget) window.FreeShippingWidget.update(75) } catch(e) {}
                $(".item_div_" + item_id).addClass("d-none");
            },
            error: function (xhr, status, error) {
                console.log("Error Status: " + xhr.status);
                console.log("Response Text: " + xhr.responseText);
                try {
                    let errorResponse = JSON.parse(xhr.responseText);
                    console.log("Error Message: " + errorResponse.error);
                    alert(errorResponse.error);
                } catch (e) {
                    console.log("Could not parse JSON response");
                }
                console.log("Error: " + xhr.status + " - " + error);
            },
        });
    });

    // Function to gather all current filter values
    function getFilters() {
        let filters = {
            categories: [],
            colors: [],
            prices: "",
            display: "",
            searchFilter: "",
        };
        $(".category-filter:checked").each(function () {
            filters.categories.push($(this).val());
        });
        $(".colors-filter:checked").each(function () {
            filters.colors.push($(this).val());
        });
        filters.display = $("input[name='items-display']:checked").val();
        filters.prices = $("input[name='price-filter']:checked").val();
        filters.searchFilter = $("input[name='search-filter']").val();
        return filters;
    }

    $(document).on(
        "change",
        ".search-filter, .category-filter, .colors-filter, input[name='price-filter'], input[name='items-display']",
        function () {
            let filters = getFilters();
            $.ajax({
                url: "/filter-products/",
                method: "GET",
                data: filters,
                success: function (response) {
                    // Replace product list with the filtered products
                    $("#products-list").html(response.html);
                    $(".product_count").html(response.product_count);
                    if (response.pagination_html !== undefined) {
                        $("#pagination-block").html(response.pagination_html);
                    }
                },
                error: function (error) {
                    console.log("Error fetching filtered products:", error);
                },
            });
        }
    );

    $(document).on("click", ".reset_shop_filter_btn", function () {
        let filters = {
            categories: [],
            rating: [],
            colors: [],
            sizes: [],
            prices: "",
            display: "",
            searchFilter: "",
        };

        $(".category-filter:checked").each(function () {
            $(this).prop("checked", false);
        });
        $(".rating-filter:checked").each(function () {
            $(this).prop("checked", false);
        });
        $(".size-filter:checked").each(function () {
            $(this).prop("checked", false);
        });
        $(".colors-filter:checked").each(function () {
            $(this).prop("checked", false);
        });
        $("input[name='items-display']").each(function () {
            $(this).prop("checked", false);
        });
        $("input[name='price-filter']").each(function () {
            $(this).prop("checked", false);
        });
        $("input[name='search-filter']").val("");

        Toast.fire({ icon: "success", title: "Filter Reset Successfully" });

        $.ajax({
            url: "/filter-products/",
            method: "GET",
            data: filters,
            success: function (response) {
                // Replace product list with the filtered products
                $("#products-list").html(response.html);
                $(".product_count").html(response.product_count);
                if (response.pagination_html !== undefined) {
                    $("#pagination-block").html(response.pagination_html);
                }
            },
            error: function (error) {
                console.log("Error fetching filtered products:", error);
            },
        });
    });

    // Initialize color swatches background from data-hex to avoid template/css linters choking on inline interpolation
    $(".color-swatch").each(function(){
        const hex = $(this).attr("data-hex");
        if (hex) {
            $(this).css("background-color", hex);
        }
    });

    // Pagination click handler for AJAX (only on shop/filtered pages)
    $(document).on("click", ".shop-pagination .page-link", function (e) {
        e.preventDefault();
        var page = null;
        // If the link is disabled or active, do nothing
        if (
            $(this).closest("li").hasClass("disabled") ||
            $(this).closest("li").hasClass("active")
        ) {
            return;
        }
        // Try to extract page number from href or data attribute
        var href = $(this).attr("href");
        if (href) {
            var match = href.match(/page=(\d+)/);
            if (match) {
                page = match[1];
            }
        }
        if (!page) {
            // fallback: try data-page attribute
            page = $(this).data("page");
        }
        if (!page) {
            return;
        }
        var filters = getFilters();
        filters.page = page;
        $.ajax({
            url: "/filter-products/",
            method: "GET",
            data: filters,
            success: function (response) {
                $("#products-list").html(response.html);
                $(".product_count").html(response.product_count);
                if (response.pagination_html !== undefined) {
                    $("#pagination-block").html(response.pagination_html);
                }
            },
            error: function (error) {
                console.log("Error fetching paginated products:", error);
            },
        });
    });

    $(document).on("click", ".add_to_wishlist", function () {
        const button = $(this);
        const product_id = button.attr("data-product_id");

        $.ajax({
            url: `/customer/toggle-wishlist/${product_id}/`,
            success: function (response) {
                if (response.status === "added") {
                    button.html(
                        "<i class='fas fa-heart fs-4 text-danger'></i>"
                    );
                } else if (response.status === "removed") {
                    button.html("<i class='far fa-heart fs-5 text-dark'></i>");
                }
                Toast.fire({
                    icon:
                        response.status === "added"
                            ? "success"
                            : response.status === "removed"
                            ? "info"
                            : "warning",
                    title: response.message,
                });
                if (response.total_wishlist_items !== undefined) {
                    $(".total_wishlist_items").text(
                        response.total_wishlist_items
                    );
                }
            },
        });
    });
    // AJAX coupon form submission for checkout
    $(document).on("submit", "#coupon-form", function (e) {
        e.preventDefault();
        var $form = $(this);
        var couponCode = $form.find('input[name="coupon_code"]').val();
        var actionUrl = $form.attr('action');
        var csrfToken = $form.find('input[name="csrfmiddlewaretoken"]').val();
        var $feedback = $("#coupon-feedback");

        $.ajax({
            url: actionUrl,
            type: "POST",
            data: {
                coupon_code: couponCode,
                csrfmiddlewaretoken: csrfToken
            },
            dataType: "json",
            success: function (data) {
                if (data.success) {
                    $feedback.html('<div class="alert alert-success">' + data.message + '</div>');
                    if (data.summary_html) {
                        $('#order-summary-block').replaceWith(data.summary_html);
                    }
                    if (data.items_html) {
                        $('#order-items-block').replaceWith(data.items_html);
                    }
                    // No reload!
                    if (typeof updateSummaryForPayment === "function") {
                        updateSummaryForPayment();
                    }
                } else {
                    $feedback.html('<div class="alert alert-danger">' + data.message + '</div>');
                }
            },
            error: function () {
                $feedback.html('<div class="alert alert-danger">Възникна грешка при опита за прилагане на купон.</div>');
            }
        });
    });
});
