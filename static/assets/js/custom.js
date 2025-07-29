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
    // Unified handler for mobile submenu toggling (all levels)
    $(document).on("click", ".nav-menu > li > a, .nav-dropdown > li > a", function (e) {
        if (window.innerWidth <= 992) {
            var $parentLi = $(this).parent();
            var $submenu = $parentLi.children(".nav-dropdown");
            var $indicator = $(this).find(".submenu-indicator");

            if ($submenu.length) {
                e.preventDefault();

                var isOpen = $submenu.is(":visible");
                if (isOpen) {
                    // Closing: close all descendant submenus and reset indicators
                    $submenu.find(".nav-dropdown").slideUp(300);
                    $submenu.find(".submenu-indicator").removeClass("submenu-indicator-up");
                }

                // Toggle current submenu and indicator
                $submenu.slideToggle(300);
                $indicator.toggleClass("submenu-indicator-up");

                // Close sibling submenus at this level and reset their indicators
                $parentLi.siblings().children(".nav-dropdown:visible").slideUp(300);
                $parentLi.siblings().find(".submenu-indicator").removeClass("submenu-indicator-up");
            }
        }
    });
});
