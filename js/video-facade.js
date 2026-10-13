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

    // Keep the poster so the player can be put back (see reset below).
    if (!player.hasAttribute('data-poster')) player.setAttribute('data-poster', player.innerHTML);
    player.replaceChildren(frame);
    document.dispatchEvent(new CustomEvent('cai:play', { detail: { id: id } }));
    frame.focus();
  }

  // Stop any playing video inside root by swapping the poster back in.
  // Removing the iframe is the only reliable way to silence a YouTube embed
  // without loading YouTube's player API.
  function reset(root) {
    (root || document).querySelectorAll('.cai-player[data-poster]').forEach(function (player) {
      if (player.querySelector('iframe')) player.innerHTML = player.getAttribute('data-poster');
    });
  }
  window.caiPlayer = { reset: reset };

  document.addEventListener('click', function (e) {
    var button = e.target.closest && e.target.closest('.cai-player__poster');
    if (button) load(button);
  });
})();
