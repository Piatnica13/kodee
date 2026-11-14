"""Per-application Google OIDC client; importing main is never necessary."""
import hmac
import secrets
import time
from authlib.integrations.flask_client import OAuth
from flask import current_app, session, request, abort
from web.app.security import current_user
from web.app.proxy import canonical_origin_matches


def init_oauth(app):
    registry = OAuth(app)
    registry.register(name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile', 'code_challenge_method': 'S256', 'default_timeout': 10})
    app.extensions['google_oauth'] = registry
    return registry


def google_client():
    if not current_app.config.get('GOOGLE_CLIENT_ID') or not current_app.config.get('GOOGLE_CLIENT_SECRET'):
        abort(503, description='Вход через Google пока не настроен')
    return current_app.extensions['google_oauth'].google


def start_google_flow(link=False):
    if link and not canonical_origin_matches(current_app.config['APP_BASE_URL']):
        abort(400, description='Откройте профиль на основном адресе сайта перед привязкой Google')
    client = google_client()
    user = current_user() if link else None
    if link and user is None:
        abort(401)
    for key in list(session):
        if key.startswith('_state_google_'):
            session.pop(key)
    state = secrets.token_urlsafe(32)
    session['google_flow'] = {'state': state, 'started_at': time.time(), 'link_user_id': user.id if user else None}
    redirect_uri = current_app.config['APP_BASE_URL'] + '/callback'
    return client.authorize_redirect(redirect_uri, state=state)


def finish_google_flow():
    """Authlib checks state, nonce, JWT signature, issuer, audience and expiry."""
    client = google_client()
    flow = session.get('google_flow')
    state = request.args.get('state', '')
    if not isinstance(flow, dict) or not state or not hmac.compare_digest(str(flow.get('state', '')).encode(), state.encode()):
        raise ValueError('Сессия входа через Google устарела. Повторите вход.')
    session.pop('google_flow', None)
    age = time.time() - flow.get('started_at', 0)
    if not 0 <= age <= current_app.config['OAUTH_FLOW_TTL']:
        raise ValueError('Сессия входа через Google устарела. Повторите вход.')
    link_id = flow.get('link_user_id')
    if link_id is not None:
        user = current_user()
        if not user or user.id != link_id:
            raise ValueError('Аккаунт изменился. Повторите привязку из профиля.')
    token = client.authorize_access_token(claims_options={
        'iss': {'essential': True, 'values': ['https://accounts.google.com', 'accounts.google.com']}})
    claims = token.get('userinfo')
    if not token.get('id_token') or not isinstance(claims, dict):
        raise ValueError('Google не вернул подтверждённую информацию об аккаунте')
    if claims.get('email_verified') is not True:
        raise ValueError('Google не подтвердил email этого аккаунта')
    subject = claims.get('sub')
    if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
        raise ValueError('Некорректный идентификатор Google')
    return claims, link_id
