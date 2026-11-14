"""Forwarded headers are accepted only from configured immediate peers."""
from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import abort, request, redirect


class TrustedProxy:
    def __init__(self, app, networks, public_https=False, **counts):
        self.app = app
        self.public_https = public_https
        self.networks = tuple(ip_network(value.strip(), strict=False) for value in networks)
        self.forwarded_app = ProxyFix(app, **counts)

    def __call__(self, environ, start_response):
        environ = environ.copy()
        if self.public_https:
            environ['wsgi.url_scheme'] = 'https'
        try:
            peer = ip_address(environ.get('REMOTE_ADDR', ''))
            trusted = any(peer in network for network in self.networks)
        except ValueError:
            trusted = False
        if trusted:
            return self.forwarded_app(environ, start_response)
        environ = environ.copy()
        for key in list(environ):
            if key.startswith('HTTP_X_FORWARDED_') or key == 'HTTP_FORWARDED':
                environ.pop(key, None)
        return self.app(environ, start_response)


def canonical_origin_matches(base):
    try:
        expected = urlsplit(base)
        actual = urlsplit(request.scheme + '://' + request.host)
        def port(url):
            return url.port or (443 if url.scheme == 'https' else 80)
        return (actual.scheme, actual.hostname, port(actual)) == (expected.scheme, expected.hostname, port(expected))
    except ValueError:
        return False


def init_proxy(app):
    base = app.config['APP_BASE_URL'].strip().rstrip('/')
    url = urlsplit(base)
    if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {'', '/'}:
        raise ValueError('APP_BASE_URL должен содержать только http(s)://домен[:порт]')
    if url.port is not None and not 1 <= url.port <= 65535:
        raise ValueError('Некорректный порт APP_BASE_URL')
    app.config['APP_BASE_URL'] = base
    if not app.config.get('TRUSTED_HOSTS'):
        app.config['TRUSTED_HOSTS'] = [url.hostname]
    counts = {name: app.config.get('PROXY_' + name.upper(), 0) for name in ('x_for', 'x_proto', 'x_host', 'x_port')}
    if any(type(value) is not int or not 0 <= value <= 10 for value in counts.values()):
        raise ValueError('Число доверенных proxy hops должно быть от 0 до 10')
    if app.config.get('PUBLIC_HTTPS') and counts['x_proto']:
        raise ValueError('PUBLIC_HTTPS требует PROXY_X_PROTO=0: схема задаётся настройкой, а не заголовком')
    app.wsgi_app = TrustedProxy(app.wsgi_app, app.config.get('TRUSTED_PROXY_CIDRS', []), public_https=app.config.get('PUBLIC_HTTPS', False), **counts)

    @app.before_request
    def valid_scheme():
        if request.scheme not in {'http', 'https'}:
            abort(400, description='Некорректная схема запроса')
        auth_paths = {'/login','/register','/profil','/basket','/login/google','/callback'}
        if request.method in {'GET','HEAD'} and request.path in auth_paths and not canonical_origin_matches(base):
            return redirect(base + request.full_path.rstrip('?'), code=302)
