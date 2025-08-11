$(function () {
    "use strict";

    // Recursive hover for all levels of nav-dropdown (desktop only)
    if ($(window).width() > 992) {
        var closeTimeout;
        var $navMenu = $("#main-nav .nav-menu");

        // First level hover
        $navMenu.children("li").on("mouseenter", function () {
            clearTimeout(closeTimeout);
            $navMenu.children("li").children(".nav-dropdown").hide();
            $(this).children(".nav-dropdown").show();
        });

        // Second level hover
        $navMenu.find(".nav-dropdown > li").on("mouseenter", function () {
            $(this).siblings("li").children(".nav-dropdown").hide();
            $(this).children(".nav-dropdown").show();
        });

        // Third level hover (if you have sub-subcategories)
        $navMenu.find(".nav-dropdown .nav-dropdown > li").on("mouseenter", function () {
            $(this).siblings("li").children(".nav-dropdown").hide();
            $(this).children(".nav-dropdown").show();
        });

        // Hide all submenus when leaving the nav menu
        $navMenu.on("mouseleave", function () {
            closeTimeout = setTimeout(function () {
                $navMenu.find(".nav-dropdown").hide();
            }, 400);
        });

        $navMenu.on("mouseenter", function () {
            if (closeTimeout) {
                clearTimeout(closeTimeout);
                closeTimeout = null;
            }
        });
    }

    // Product Preview
    $(".sp-wrap").smoothproducts();

    // Hamburger menu toggle logic (open/close mobile nav)
    $(document).on("click", ".nav-toggle", function (e) {
        var $wrapper = $(".nav-menu-wrapper");
        var $toggle = $(this);
        var isOpen = $wrapper.hasClass("nav-menu-wrapper-open");

        if (!isOpen) {
            // Opening: animate both at the same time
            $wrapper.addClass("nav-menu-wrapper-open");
            $("body").addClass("no-scroll");
            $toggle.attr("aria-expanded", "true").addClass("active");
        } else {
            // Closing: remove .active immediately so X animates back *with* menu
            $wrapper.removeClass("nav-menu-wrapper-open");
            $("body").removeClass("no-scroll");
            $toggle.attr("aria-expanded", "false").removeClass("active");
        }
    });

    // Click outside nav-menu-wrapper closes the menu (mobile/off-canvas only)
    $(document).on("mousedown touchstart", function (e) {
        var $wrapper = $(".nav-menu-wrapper");
        var $toggle = $(".nav-toggle");
        if (
            $wrapper.hasClass("nav-menu-wrapper-open") &&
            !$(e.target).closest(".nav-menu-wrapper, .nav-toggle").length
        ) {
            $wrapper.removeClass("nav-menu-wrapper-open");
            $("body").removeClass("no-scroll");
            $toggle.attr("aria-expanded", "false").removeClass("active");
        }
    });

    $(document).on('click', '.shop-chevron-toggle, .header-chevron-toggle', function (e) {
        var $clicked = $(this);
        var $button, $chevron, targetId, $submenu;

        // Shop sidebar chevron - works on all screen sizes
        if ($clicked.hasClass('shop-chevron-toggle')) {
            e.preventDefault();
            $button = $clicked;
            $chevron = $button.find('.submenu-indicator-chevron');
            targetId = $button.attr('data-bs-target') || $button.attr('data-target');
            $submenu = $(targetId);
        } else {
            // Header chevron link - only intercept on mobile; on desktop allow normal navigation
            if (window.innerWidth > 992) {
                return; // desktop: use hover and native links
            }
            e.preventDefault();
            $button = $clicked;
            $chevron = $clicked.find('.submenu-indicator');
            $submenu = $clicked.parent().children('.nav-dropdown');
        }

        if ($submenu && $submenu.length) {
            var isOpen = $submenu.is(':visible');

            if (isOpen) {
                // Closing: also collapse descendants and clear indicators
                $submenu.find('.subcategories, .nav-dropdown').slideUp(300);
                $submenu.find('.submenu-indicator-chevron, .submenu-indicator').closest('button, a').removeClass('submenu-indicator-up');
            }

            // Toggle current submenu and rotate indicator
            $submenu.slideToggle(300);
            $chevron.closest('button, a').toggleClass('submenu-indicator-up');

            // Close visible siblings at this level and reset their indicators
            var $parentLi = $button.closest('li');
            $parentLi.siblings().children('.subcategories:visible, .nav-dropdown:visible').slideUp(300);
            $parentLi.siblings().find('.submenu-indicator-chevron, .submenu-indicator').closest('button, a').removeClass('submenu-indicator-up');
        }
    });
});
