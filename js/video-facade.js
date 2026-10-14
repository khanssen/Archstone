/* Click-to-load YouTube player.
   Nothing is requested from YouTube until the visitor presses play, and the
   embed uses youtube-nocookie.com. Without JavaScript the "Watch on YouTube"
   link under each player still works. */
(function () {
  'use strict';

  var posters = new WeakMap();   // player element -> its original poster nodes

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

    // Keep the poster's own nodes so the player can be put back (see reset).
    if (!posters.has(player)) posters.set(player, Array.prototype.slice.call(player.childNodes));
    player.replaceChildren(frame);
    document.dispatchEvent(new CustomEvent('cai:play', { detail: { id: id } }));
    frame.focus();
  }

  // Stop any playing video inside root by putting the original poster nodes
  // back. Removing the iframe is the only reliable way to silence a YouTube
  // embed without loading YouTube's player API. No HTML strings are parsed.
  function reset(root) {
    (root || document).querySelectorAll('.cai-player').forEach(function (player) {
      var nodes = posters.get(player);
      if (nodes && player.querySelector('iframe')) player.replaceChildren.apply(player, nodes);
    });
  }
  window.caiPlayer = { reset: reset };

  document.addEventListener('click', function (e) {
    var button = e.target.closest && e.target.closest('.cai-player__poster');
    if (button) load(button);
  });
})();
