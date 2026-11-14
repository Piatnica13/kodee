import os
from config import load_environment

load_environment()

bind = os.getenv('GUNICORN_BIND', '0.0.0.0:' + os.getenv('PORT', '5000'))
workers = int(os.getenv('WEB_WORKERS', '2'))
threads = 1
timeout = 60
accesslog = '-'
errorlog = '-'

# The application alone applies forwarded headers after checking the peer CIDR.
forwarded_allow_ips = ''
secure_scheme_headers = {}
