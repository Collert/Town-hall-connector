/* Town Hall heartbeat: tells your server (which tells Town Hall) that this person is still
 * working. Loaded by {% townhall_heartbeat %}. The first heartbeat starts their shift; when
 * heartbeats stop for 5 minutes, Town Hall ends it at the last one.
 *
 * Events: window "townhall:heartbeat" (detail = the server's answer).
 * API: window.TownHallHeartbeat.beat() sends one now; .endShift() ends the shift and stops.
 */
(function () {
    'use strict';
    var script = document.currentScript;
    if (!script || window.TownHallHeartbeat) return;

    var url = script.dataset.url;
    var endUrl = script.dataset.endUrl;
    var csrf = script.dataset.csrf;
    var interval = Math.max(10, parseInt(script.dataset.interval, 10) || 60) * 1000;
    var idle = (parseInt(script.dataset.idle, 10) || 0) * 60000;
    var lastBeat = 0;
    var lastActivity = Date.now();
    var stopped = false;

    function post(target) {
        return fetch(target, {
            method: 'POST',
            credentials: 'same-origin',
            keepalive: true,
            headers: {'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest'}
        }).then(function (response) {
            return response.headers.get('content-type') && response.headers.get('content-type').indexOf('json') !== -1
                ? response.json() : {ok: false, stop: response.status === 403};
        });
    }

    function idleNow() {
        return idle && Date.now() - lastActivity > idle;
    }

    function beat() {
        if (stopped || idleNow()) return;
        lastBeat = Date.now();
        post(url).then(function (answer) {
            if (answer && answer.stop) stopped = true;
            window.dispatchEvent(new CustomEvent('townhall:heartbeat', {detail: answer}));
        }).catch(function () { /* offline for a moment: the next beat tries again */ });
    }

    function endShift() {
        stopped = true;
        return post(endUrl);
    }

    beat();
    setInterval(beat, interval);

    // Background tabs may be throttled: catch up as soon as the tab is looked at again
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && Date.now() - lastBeat >= interval / 2) beat();
    });

    if (idle) {
        ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart'].forEach(function (name) {
            window.addEventListener(name, function () {
                var wasIdle = idleNow();
                lastActivity = Date.now();
                if (wasIdle) beat();
            }, {passive: true});
        });
    }

    window.TownHallHeartbeat = {beat: beat, endShift: endShift};
})();
