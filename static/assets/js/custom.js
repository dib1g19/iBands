$(function () {
    "use strict";

    // Script Navigation
    !(function (n, e, i, a) {
        (n.navigation = function (t, s) {
            var o = {
                    responsive: !0,
                    mobileBreakpoint: 992,
                    showDuration: 300,
                    hideDuration: 300,
                    showDelayDuration: 0,
                    hideDelayDuration: 0,
                    submenuTrigger: "hover",
                    effect: "fade",
                    submenuIndicator: !0,
                    hideSubWhenGoOut: !0,
                    visibleSubmenusOnMobile: !1,
                    overlay: !0,
                    overlayColor: "rgba(0, 0, 0, 0.5)",
                    hidden: !1,
                    offCanvasSide: "left",
                    onInit: function () {},
                    onShowOffCanvas: function () {},
                    onHideOffCanvas: function () {},
                },
                u = this,
                f = "click.nav touchstart.nav",
                l = "mouseenter.nav",
                c = "mouseleave.nav";
            u.settings = {};
            var t = (n(t), t);
                (u.init = function () {
                    (u.settings = n.extend({}, o, s)),
                        "right" == u.settings.offCanvasSide &&
                            n(t)
                                .find(".nav-menus-wrapper")
                                .addClass("nav-menus-wrapper-right"),
                        u.settings.hidden &&
                            (u.settings.mobileBreakpoint = 99999),
                        v(),
                        n(t).find(".megamenu-tabs").length > 0 && y(),
                        n(e).resize(function () {
                            C();
                        }),
                        s !== a && u.callback("onInit");
                });
            var v = function () {
                n(t)
                    .find("li")
                    .each(function () {
                        n(this).children(".nav-dropdown,.megamenu-panel")
                            .length > 0 &&
                            (n(this)
                                .children(".nav-dropdown,.megamenu-panel"),
                            u.settings.submenuIndicator &&
                                n(this)
                                    .children("a")
                                    .append(
                                        "<span class='submenu-indicator'><span class='submenu-indicator-chevron'></span></span>"
                                    ));
                    });
            };
            (u.showSubmenu = function (e, i) {
                g() > u.settings.mobileBreakpoint
                    "fade" == i
                        ? n(e)
                              .children(".nav-dropdown")
                              .stop(!0, !0)
                              .delay(u.settings.showDelayDuration)
                              .fadeIn(u.settings.showDuration)
                        : n(e)
                              .children(".nav-dropdown")
                              .stop(!0, !0)
                              .delay(u.settings.showDelayDuration)
                              .slideDown(u.settings.showDuration);
            }),
                (u.hideSubmenu = function (e, i) {
                    "fade" == i
                        ? n(e)
                              .find(".nav-dropdown")
                              .stop(!0, !0)
                              .delay(u.settings.hideDelayDuration)
                              .fadeOut(u.settings.hideDuration)
                        : n(e)
                              .find(".nav-dropdown")
                              .stop(!0, !0)
                              .delay(u.settings.hideDelayDuration)
                              .slideUp(u.settings.hideDuration);
                });
            var h = function () {
                    n("body").addClass("no-scroll"),
                        u.settings.overlay &&
                            (n(t).append(
                                "<div class='nav-overlay-panel'></div>"
                            ),
                            n(t)
                                .find(".nav-overlay-panel")
                                .css(
                                    "background-color",
                                    u.settings.overlayColor
                                )
                                .fadeIn(300)
                                .on("click touchstart", function (n) {
                                    u.hideOffcanvas();
                                }));
                },
                p = function () {
                    n("body").removeClass("no-scroll"),
                        u.settings.overlay &&
                            n(t)
                                .find(".nav-overlay-panel")
                                .fadeOut(400, function () {
                                    n(this).remove();
                                });
                };
            (u.showOffcanvas = function () {
                h(),
                    "left" == u.settings.offCanvasSide
                        ? n(t)
                              .find(".nav-menus-wrapper")
                              .css("transition-property", "left")
                              .addClass("nav-menus-wrapper-open")
                        : n(t)
                              .find(".nav-menus-wrapper")
                              .css("transition-property", "right")
                              .addClass("nav-menus-wrapper-open");
            }),
                (u.hideOffcanvas = function () {
                    n(t)
                        .find(".nav-menus-wrapper")
                        .removeClass("nav-menus-wrapper-open")
                        .on(
                            "webkitTransitionEnd moztransitionend transitionend oTransitionEnd",
                            function () {
                                n(t)
                                    .find(".nav-menus-wrapper")
                                    .css("transition-property", "none")
                                    .off();
                            }
                        ),
                        p();
                }),
                (u.toggleOffcanvas = function () {
                    g() <= u.settings.mobileBreakpoint &&
                        (n(t)
                            .find(".nav-menus-wrapper")
                            .hasClass("nav-menus-wrapper-open")
                            ? (u.hideOffcanvas(),
                              s !== a && u.callback("onHideOffCanvas"))
                            : (u.showOffcanvas(),
                              s !== a && u.callback("onShowOffCanvas")));
                });
            var b = function () {
                    n("body").on("click.body touchstart.body", function (e) {
                        0 === n(e.target).closest(".navigation").length &&
                            (n(t).find(".nav-dropdown").fadeOut());
                    });
                },
                g = function () {
                    return (
                        e.innerWidth ||
                        i.documentElement.clientWidth ||
                        i.body.clientWidth
                    );
                },
                w = function () {
                    n(t).find(".nav-menu").find("li, a").off(f).off(l).off(c);
                },
                C = function () {
                    if (g() > u.settings.mobileBreakpoint) {
                        var e = n(t).outerWidth(!0);
                        n(t)
                            .find(".nav-menu")
                            .children("li")
                            .children(".nav-dropdown")
                            .each(function () {
                                n(this).parent().position().left +
                                    n(this).outerWidth() >
                                e
                                    ? n(this).css("right", 0)
                                    : n(this).css("right", "auto");
                            });
                    }
                },
                k = function () {
                    w(),
                        n(t).find(".nav-dropdown").hide(0),
                        navigator.userAgent.match(/Mobi/i) ||
                        navigator.maxTouchPoints > 0 ||
                        "click" == u.settings.submenuTrigger
                            ? n(t)
                                  .find(".nav-menu, .nav-dropdown")
                                  .children("li")
                                  .children("a")
                                  .on(f, function (i) {
                                      if (
                                          (u.hideSubmenu(
                                              n(this)
                                                  .parent("li")
                                                  .siblings("li"),
                                              u.settings.effect
                                          ),
                                          n(this)
                                              .closest(".nav-menu")
                                              .siblings(".nav-menu")
                                              .find(".nav-dropdown")
                                              .fadeOut(u.settings.hideDuration),
                                          n(this).siblings(".nav-dropdown")
                                              .length > 0)
                                      ) {
                                          if (
                                              (i.stopPropagation(),
                                              i.preventDefault(),
                                              "none" ==
                                                  n(this)
                                                      .siblings(".nav-dropdown")
                                                      .css("display"))
                                          )
                                              return (
                                                  u.showSubmenu(
                                                      n(this).parent("li"),
                                                      u.settings.effect
                                                  ),
                                                  C(),
                                                  !1
                                              );
                                          if (
                                              (u.hideSubmenu(
                                                  n(this).parent("li"),
                                                  u.settings.effect
                                              ),
                                              "_blank" ==
                                                  n(this).attr("target") ||
                                                  "blank" ==
                                                      n(this).attr("target"))
                                          )
                                              e.open(n(this).attr("href"));
                                          else {
                                              if (
                                                  "#" == n(this).attr("href") ||
                                                  "" == n(this).attr("href")
                                              )
                                                  return !1;
                                              e.location.href =
                                                  n(this).attr("href");
                                          }
                                      }
                                  })
                            : n(t)
                        u.settings.hideSubWhenGoOut && b();
                },
                D = function () {
                    w(),
                        n(t).find(".nav-dropdown").hide(0),
                        u.settings.visibleSubmenusOnMobile
                            ? n(t).find(".nav-dropdown").show(0)
                            : (n(t).find(".nav-dropdown").hide(0),
                              n(t)
                                  .find(".submenu-indicator")
                                  .removeClass("submenu-indicator-up"),
                              u.settings.submenuIndicator
                                  ? n(t)
                                        .find(".submenu-indicator")
                                        .on(f, function (e) {
                                            return (
                                                e.stopPropagation(),
                                                e.preventDefault(),
                                                u.hideSubmenu(
                                                    n(this)
                                                        .parent("a")
                                                        .parent("li")
                                                        .siblings("li"),
                                                    "slide"
                                                ),
                                                u.hideSubmenu(
                                                    n(this)
                                                        .closest(".nav-menu")
                                                        .siblings(".nav-menu")
                                                        .children("li"),
                                                    "slide"
                                                ),
                                                "none" ==
                                                n(this)
                                                    .parent("a")
                                                    .siblings(".nav-dropdown")
                                                    .css("display")
                                                    ? (n(this).addClass(
                                                          "submenu-indicator-up"
                                                      ),
                                                      n(this)
                                                          .parent("a")
                                                          .parent("li")
                                                          .siblings("li")
                                                          .find(
                                                              ".submenu-indicator"
                                                          )
                                                          .removeClass(
                                                              "submenu-indicator-up"
                                                          ),
                                                      n(this)
                                                          .closest(".nav-menu")
                                                          .siblings(".nav-menu")
                                                          .find(
                                                              ".submenu-indicator"
                                                          )
                                                          .removeClass(
                                                              "submenu-indicator-up"
                                                          ),
                                                      u.showSubmenu(
                                                          n(this)
                                                              .parent("a")
                                                              .parent("li"),
                                                          "slide"
                                                      ),
                                                      !1)
                                                    : (n(this)
                                                          .parent("a")
                                                          .parent("li")
                                                          .find(
                                                              ".submenu-indicator"
                                                          )
                                                          .removeClass(
                                                              "submenu-indicator-up"
                                                          ),
                                                      void u.hideSubmenu(
                                                          n(this)
                                                              .parent("a")
                                                              .parent("li"),
                                                          "slide"
                                                      ))
                                            );
                                        })
                                  : k());
                };
            (u.callback = function (n) {
                s[n] !== a && s[n].call(t);
            }),
                u.init();
                if (window.innerWidth <= u.settings.mobileBreakpoint) {
                    D();
                } else {
                    k();
                }
                $(window).on("resize", function() {
                    if (window.innerWidth <= u.settings.mobileBreakpoint) {
                        D();
                    } else {
                        k();
                    }
                });
        }),
            (n.fn.navigation = function (e) {
                return this.each(function () {
                    if (a === n(this).data("navigation")) {
                        var i = new n.navigation(this, e);
                        n(this).data("navigation", i);
                    }
                });
            });
    })(jQuery, window, document),
        $(document).ready(function () {
            $("#navigation").navigation();
        });

// Recursive hover for all levels of nav-dropdown (desktop only)
if ($(window).width() > 992) {
    var closeTimeout;
    var $navMenu = $("#navigation .nav-menu");

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
        var $wrapper = $(".nav-menus-wrapper");
        var $toggle = $(this);
        var isOpen = $wrapper.hasClass("nav-menus-wrapper-open");

        if (!isOpen) {
            // Opening: animate both at the same time
            $wrapper.addClass("nav-menus-wrapper-open");
            $("body").addClass("no-scroll");
            $toggle.attr("aria-expanded", "true").addClass("active");
        } else {
            // Closing: remove .active immediately so X animates back *with* menu
            $wrapper.removeClass("nav-menus-wrapper-open");
            $("body").removeClass("no-scroll");
            $toggle.attr("aria-expanded", "false").removeClass("active");
        }
    });

    // Click outside nav-menus-wrapper closes the menu (mobile/off-canvas only)
    $(document).on("mousedown touchstart", function (e) {
        var $wrapper = $(".nav-menus-wrapper");
        var $toggle = $(".nav-toggle");
        if (
            $wrapper.hasClass("nav-menus-wrapper-open") &&
            !$(e.target).closest(".nav-menus-wrapper, .nav-toggle").length
        ) {
            $wrapper.removeClass("nav-menus-wrapper-open");
            $("body").removeClass("no-scroll");
            $toggle.attr("aria-expanded", "false").removeClass("active");
        }
    });

});
