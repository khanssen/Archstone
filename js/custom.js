(function ($) {
  'use strict';

  /* ---------- Preloader ---------- */
  $(window).on('load', function () {
    $('#preloader').delay(350).fadeOut('slow');
    $('body').delay(350).css({ overflow: 'visible' });
  });

  /* ---------- Sticky Header ---------- */
  const $win = $(window);
  const $header = $('.sticky-header');
  $win.on('scroll', function () {
    $header.toggleClass('scroll-on', $win.scrollTop() >= 1);
  });

  /* ---------- Owl Carousels ---------- */
  if ($.fn.owlCarousel) {
    // Home 2
    const $home2 = $('.home-slide-2');
    if ($home2.length) {
      $home2.owlCarousel({
        items: 1,
        nav: false,
        loop: true,
        dots: false,
        smartSpeed: 450,
        autoplay: true,
        animateOut: 'fadeOut',
        navText: [
          "<i class='flaticon-left-arrow'></i>",
          "<i class='flaticon-next-1'></i>"
        ]
      });

      $home2.on('translate.owl.carousel', function () {
        $('.banner-title').removeClass('animated fadeInLeft').css('opacity', '0');
        $('.slide-txt p, .slide-txt span').removeClass('animated fadeInLeft').css('opacity', '0');
        $('.slide-txt .custom-btn').removeClass('animated fadeInDown').css('opacity', '0');
        $('.slide-img').removeClass('animated fadeInUp').css('opacity', '0');
        $('.slide-bg.sb-1').removeClass('animated fadeInLeft').css('opacity', '0');
        $('.slide-bg.sb-2').removeClass('animated fadeInRight').css('opacity', '0');
      });

      $home2.on('translated.owl.carousel', function () {
        $('.banner-title').addClass('animated fadeInLeft').css('opacity', '1');
        $('.slide-txt p, .slide-txt span').addClass('animated fadeInLeft').css('opacity', '1');
        $('.slide-txt .custom-btn').addClass('animated fadeInDown').css('opacity', '1');
        $('.slide-img').addClass('animated fadeInUp').css('opacity', '1'); // fixed: was 0
        $('.slide-bg.sb-1').addClass('animated fadeInLeft').css('opacity', '1');
        $('.slide-bg.sb-2').addClass('animated fadeInRight').css('opacity', '1');
      });
    }

    // Home 3
    const $home3 = $('.banner-slide');
    if ($home3.length) {
      $home3.owlCarousel({
        items: 1,
        nav: true,
        loop: true,
        dots: false,
        autoplay: true,
        smartSpeed: 450,
        animateOut: 'fadeOut',
        navText: [
          "<i class='flaticon-left-arrow'></i>",
          "<i class='flaticon-next-1'></i>"
        ]
      });

      $home3.on('translate.owl.carousel', function () {
        $('.banner-title').removeClass('animated fadeInUp').css('opacity', '0');
        $('.slide-txt p, .slide-txt span').removeClass('animated fadeInLeft').css('opacity', '0');
        $('.slide-txt .custom-btn').removeClass('animated fadeInDown').css('opacity', '0');
        $('.slide-img').removeClass('animated fadeInUp').css('opacity', '0');
      });

      $home3.on('translated.owl.carousel', function () {
        $('.banner-title').addClass('animated fadeInUp').css('opacity', '1');
        $('.slide-txt p, .slide-txt span').addClass('animated fadeInLeft').css('opacity', '1');
        $('.slide-txt .custom-btn').addClass('animated fadeInDown').css('opacity', '1');
        $('.slide-img').addClass('animated fadeInUp').css('opacity', '1'); // fixed
      });
    }

    // “Capabilities” carousel
    const $capabilities = $('.capabilities');
    if ($capabilities.length) {
      $capabilities.owlCarousel({
        margin: 10,
        responsiveClass: true,
        nav: false,
        dots: false,
        loop: true,
        slideTransition: 'linear',
        autoplayTimeout: 4500,
        autoplayHoverPause: true,
        autoplaySpeed: 4500,
        autoplay: true,
        stagePadding: 10,
        responsive: {
          0: {
            items: 1,
            nav: true,
            navText: [
              "<i class='flaticon-right'></i>",
              "<i class='flaticon-right'></i>"
            ]
          },
          600: { items: 3 },
          1000: { items: 4 }
        }
      });
    }

    // Team
    const $team = $('.team-wrap');
    if ($team.length) {
      $team.owlCarousel({
        nav: false,
        dots: false,
        loop: true,
        responsiveClass: true,
        responsive: {
          0: { items: 1, nav: true },
          600: { items: 2 },
          1000: { items: 3 }
        }
      });
    }

    // Quotes
    const $quote = $('.quote-slider');
    if ($quote.length) {
      $quote.owlCarousel({
        nav: false,
        dots: true,
        loop: true,
        autoplay: true,
        center: true,
        responsiveClass: true,
        responsive: {
          0: { items: 1 },
          600: { items: 3 },
          1000: { items: 3 }
        }
      });
    }

    const $quote2 = $('.quote-slider2');
    if ($quote2.length) {
      $quote2.owlCarousel({
        items: 2,
        nav: true,
        navText: [
          "<i class='flaticon-next-1'></i>",
          "<i class='flaticon-previous'></i>"
        ],
        loop: true,
        margin: 40,
        dots: false,
        responsiveClass: true,
        responsive: {
          0: { items: 1 },
          800: { items: 2 },
          1000: { items: 2 }
        }
      });
    }
  }

  /* ---------- WOW ---------- */
  if (typeof WOW === 'function') {
    new WOW({
      offset: 100,
      animateClass: 'animated',
      mobile: true
    }).init();
  }

  /* ---------- CounterUp ---------- */
  if ($.fn.counterUp) {
    $('.counter').counterUp({ delay: 10, time: 1000 });
  }

  /* ---------- Venobox ---------- */
  if ($.fn.venobox) {
    $('.video, .service-video, .bn-video, .faq-popup').venobox({
      share: ['facebook', 'twitter', 'download']
    });
  }

  /* ---------- Isotope ---------- */
  if ($.fn.isotope) {
    const $grid = $('.grid');
    if ($grid.length) {
      $grid.isotope({ itemSelector: '.grid-item', percentPosition: true });
      $('.portfolio-menu').on('click', '.button', function () {
        $grid.isotope({ filter: $(this).attr('data-filter') });
      });
      // Active class toggle
      $('.portfolio-menu').each(function (_, group) {
        const $group = $(group);
        $group.on('click', 'button', function () {
          $group.find('.active').removeClass('active');
          $(this).addClass('active');
        });
      });
    }

    const $masonry = $('.masson-grid');
    if ($masonry.length) {
      $masonry.isotope({
        itemSelector: '.item',
        percentPosition: true,
        masonry: { columnWidth: '.grid-sizer' }
      });
      $('.portfolio-menu.massionary-menu').on('click', '.button', function () {
        $masonry.isotope({ filter: $(this).attr('data-filter') });
      });
    }
  }

  /* ---------- ScrollUp ---------- */
  if ($.scrollUp) {
    $.scrollUp({
      scrollName: 'scrollUp',
      topSpeed: 300,
      animation: 'fade',
      animationInSpeed: 200,
      animationOutSpeed: 200,
      scrollText: ''
    });
  }

  /* ---------- Qty + / - ---------- */
  (function initQty() {
    const $qty = $('.pro-qty');
    if (!$qty.length) return;

    $qty.append('<div class="inc qty-btn">+</div>');
    $qty.append('<div class="dec qty-btn">-</div>');

    $qty.on('click', '.qty-btn', function (e) {
      e.preventDefault();
      const $btn = $(this);
      const $input = $btn.parent().find('input');
      const oldVal = parseFloat($input.val()) || 1;
      const newVal = $btn.hasClass('inc') ? oldVal + 1 : Math.max(1, oldVal - 1);
      $input.val(newVal);
    });
  })();

  /* ---------- jQuery UI: Price Range ---------- */
  if ($.fn.slider && $('#slider-range').length) {
    $('#slider-range').slider({
      range: true,
      min: 0,
      max: 500,
      values: [25, 500],
      slide: function (_e, ui) {
        $('#amount').val('$' + ui.values[0] + ' - $' + ui.values[1]);
      }
    });
    // Initialize display immediately
    const vals = $('#slider-range').slider('values');
    $('#amount').val('$' + vals[0] + ' - $' + vals[1]);
  }

  /* ---------- Checkout Form Toggles ---------- */
  $('#billform-differentswitch').on('change', function () {
    $('.checkout-differentform')[$(this).is(':checked') ? 'slideDown' : 'slideUp']();
  });

  $('.checkout-payment input[type="radio"]').each(function () {
    if ($(this).is(':checked')) {
      $(this).siblings('.pay-option-content').slideDown();
    }
    $(this).siblings('label').on('click', function () {
      $('.checkout-payment input[type="radio"]')
        .prop('checked', false)
        .siblings('.pay-option-content').slideUp();
      $(this).prev('input[type="radio"]')
        .prop('checked', true)
        .siblings('.pay-option-content').slideDown();
    });
  });

  /* ---------- Mailchimp ---------- */
  if ($.fn.ajaxChimp) {
    const $mailchimp = $('.mailchimp-sform');
    if ($mailchimp.length) {
      $mailchimp.ajaxChimp({
        language: 'es',
        callback: mailchimpCallback,
        // Replace with your own Mailchimp post URL:
        url: 'https://facebook.us17.list-manage.com/subscribe/post?u=e8c07b57e07350179b0d6325b&amp;id=437442d4eb'
      });
    }

    function mailchimpCallback(resp) {
      if (resp.result === 'success') {
        $('.subscription-success')
          .html('<i class="fa fa-check"></i><br/>' + resp.msg)
          .fadeIn(1500);
        $('.subscription-error').fadeOut(500);
      } else if (resp.result === 'error') {
        $('.subscription-error')
          .html('<i class="fa fa-times"></i><br/>' + resp.msg)
          .fadeIn(1500);
      }
    }

    $.ajaxChimp.translations.es = {
      submit: 'Submitting...',
      0: 'We have sent you a confirmation email',
      1: 'Please enter a value',
      2: 'An email address must contain a single @',
      3: 'The domain portion of the email address is invalid (the portion after the @: )',
      4: 'The username portion of the email address is invalid (the portion before the @: )',
      5: 'This email address looks fake or invalid. Please enter a real email address'
    };
  }

})(jQuery);
