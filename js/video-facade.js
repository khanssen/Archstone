/* Click-to-load YouTube player.
   Nothing is requested from YouTube until the visitor presses play, and the
   embed uses youtube-nocookie.com. Without JavaScript the "Watch on YouTube"
   link under each player still works. */
(function () {
  'use strict';

  function load(button) {
    var player = button.closest('.cai-player');
    var id = player && player.getAttribute('data-video-id');
    if (!id || !/^[A-Za-z0-9_-]{11}$/.test(id)) return;

    var frame = document.createElement('iframe');
    frame.src = 'https://www.youtube-nocookie.com/embed/' + id + '?autoplay=1&rel=0';
    frame.title = player.getAttribute('data-title') || 'Video';
    frame.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
    frame.referrerPolicy = 'strict-origin-when-cross-origin';
    frame.allowFullscreen = true;

    player.replaceChildren(frame);
    frame.focus();
  }

  document.addEventListener('click', function (e) {
    var button = e.target.closest && e.target.closest('.cai-player__poster');
    if (button) load(button);
  });
})();
