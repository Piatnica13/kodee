import re
import secrets
from flask import g
from jinja2 import BaseLoader


class NonceLoader(BaseLoader):
    """Only scripts written in trusted template source receive a CSP nonce."""
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def get_source(self, environment, template):
        source, filename, uptodate = self.wrapped.get_source(environment, template)
        source = re.sub(r'<script\b(?![^>]*\bnonce=)', '<script nonce="{{ csp_nonce }}"', source, flags=re.I)
        return source, filename, uptodate

    def list_templates(self):
        return self.wrapped.list_templates()


def init_headers(app):
    app.jinja_env.loader = NonceLoader(app.jinja_env.loader)

    @app.before_request
    def nonce():
        g.csp_nonce = secrets.token_urlsafe(24)

    @app.context_processor
    def template_nonce():
        return {'csp_nonce': g.csp_nonce}

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{g.csp_nonce}' https://unpkg.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://www.googletagmanager.com https://mc.yandex.ru https://mc.yandex.com; "
            "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; font-src 'self' data:; "
            "connect-src 'self' https://*.google-analytics.com https://analytics.google.com https://*.analytics.google.com https://*.googletagmanager.com https://stats.g.doubleclick.net https://www.google.com https://mc.yandex.ru https://mc.yandex.com; "
            "frame-src https://mc.yandex.ru https://mc.yandex.com; object-src 'none'; base-uri 'self'; form-action 'self' https://accounts.google.com; frame-ancestors 'none'"
        )
        return response
