"""Bounded recovery-failure notifications from the Pi, independent of Grafana."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from native_ups_guard import decision


def problems(state, now):
    alerts = []
    if decision(state.get('status'), 0) == 'unknown':
        state.setdefault('unknownSince', now)
        if now - state['unknownSince'] >= 60:
            alerts.append('UPS readings unavailable for at least 60 seconds')
    else:
        state.pop('unknownSince', None)
    for name, row in sorted(state.get('pending', {}).items()):
        if row.get('held'):
            alerts.append(f'{name}: shutdown completion needs reconciliation')
        elif row.get('attempts', 0) >= 5 and name not in state.get('reachable', []):
            alerts.append(f'{name}: five wake attempts exhausted')
    event = state.get('cascade', {})
    if event.get('error') and not event.get('recovered'):
        alerts.append('NAS shutdown command outcome needs reconciliation')
    if ('ben-server' in state.get('pending', {}) and not state.get('nasReady')
            and state.get('onlineSince') is not None
            and now - state['onlineSince'] >= 600):
        alerts.append('Server recovery is waiting for NAS storage readiness')
    return alerts


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def notify(state, now):
    """No notifications without explicit configuration; retry at most every 5m.

    Call with monotonic time. Reset notification timers on process restart.
    Never include webhook credentials or exception text in state or journals.
    """
    issues = problems(state, now)
    url = os.environ.get('UPS_RECOVERY_WEBHOOK', '')
    state['notificationConfigured'] = bool(url)
    if not issues or not url:
        state.pop('notificationLastIssues', None)
        return
    last = state.get('notificationLastAttempt')
    if last is not None and now - last < 300:
        return
    if issues == state.get('notificationLastIssues'):
        return
    state['notificationLastAttempt'] = now
    try:
        parsed = urllib.parse.urlparse(url)
        if (parsed.scheme != 'https' or parsed.hostname != 'discord.com'
                or parsed.port not in {None, 443} or parsed.username or parsed.password
                or not parsed.path.startswith('/api/webhooks/')):
            raise ValueError('Invalid notification endpoint')
        body = json.dumps({'content': 'UPS recovery needs attention:\n' + '\n'.join(issues),
                           'allowed_mentions': {'parse': []}}).encode()
        request = urllib.request.Request(url, data=body, method='POST',
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=5) as response:
            if not 200 <= response.status < 300:
                raise ValueError('Notification rejected')
        state['notificationLastIssues'] = issues
        state.pop('notificationError', None)
    except (OSError, ValueError, urllib.error.URLError):
        state['notificationError'] = 'Delivery failed; retry after five minutes'


def reset_timers(state):
    for field in ('unknownSince', 'notificationLastAttempt', 'notificationLastIssues'):
        state.pop(field, None)
