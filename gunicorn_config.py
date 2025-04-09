import multiprocessing
import os
import ssl

# Server socket configuration
bind = '127.0.0.1:8501'
backlog = 2048

# Worker processes - optimized for production
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'gevent'
worker_connections = 2000
timeout = 60
keepalive = 5

# Process naming
proc_name = 'xtraders_production'

# Enhanced logging configuration
logfile = '/var/log/xtraders/gunicorn.log'
loglevel = 'info'
accesslog = '/var/log/xtraders/access.log'
errorlog = '/var/log/xtraders/error.log'
access_log_format = '%({x-real-ip}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %({x-forwarded-for}i)s'

# Production SSL/TLS Configuration
keyfile = os.getenv('SSL_KEYFILE', '/etc/ssl/private/xtraders.key')
certfile = os.getenv('SSL_CERTFILE', '/etc/ssl/certs/xtraders.crt')
ssl_version = ssl.PROTOCOL_TLS_SERVER
ciphers = 'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384'

# Enhanced security settings
proxy_allow_ips = '127.0.0.1'
proxy_protocol = True
forwarded_allow_ips = '127.0.0.1'
secure_scheme_headers = {
    'X-FORWARDED-PROTOCOL': 'ssl',
    'X-FORWARDED-PROTO': 'https',
    'X-FORWARDED-SSL': 'on'
}

# Production process management
graceful_timeout = 60
max_requests = 2000
max_requests_jitter = 100

# Server mechanics
daemon = True
pidfile = '/var/run/xtraders/gunicorn.pid'
user = 'xtraders'
group = 'xtraders'
umask = 0o007
preload_app = True
reload = False

# Production settings
reload_engine = None
reload_extra_files = []
debug = False
spew = False

# Server hooks with enhanced monitoring
def on_starting(server):
    """Log server startup"""
    server.log.info('Starting XTraders production server')

def when_ready(server):
    """Actions to perform when server is ready"""
    server.log.info('XTraders server is ready to accept connections')

def pre_fork(server, worker):
    """Pre-fork optimizations"""
    server.log.info(f'Pre-forking worker {worker.pid}')

def post_fork(server, worker):
    """Post-fork worker setup"""
    server.log.info(f'Worker {worker.pid} booted successfully')

def pre_request(worker, req):
    """Pre-request logging"""
    worker.log.debug(f"{req.method} {req.path} - {req.remote_addr}")

def post_request(worker, req, environ, resp):
    """Post-request monitoring"""
    worker.log.debug(f"Response status: {resp.status}")

def worker_abort(worker):
    """Handle worker crashes"""
    worker.log.error(f'Worker {worker.pid} aborted')

def on_exit(server):
    """Cleanup on server shutdown"""
    server.log.info('Shutting down XTraders server')