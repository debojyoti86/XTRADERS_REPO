import os
import sys
import logging
import signal
from streamlit.web.bootstrap import run
from streamlit import config as streamlit_config
from streamlit.web.server import Server
from gevent import monkey
from gevent.pywsgi import WSGIServer

# Patch standard library for gevent compatibility
monkey.patch_all()

# Signal handlers for graceful shutdown
def handle_sigterm(signum, frame):
    logger.info('Received SIGTERM signal, initiating graceful shutdown')
    sys.exit(0)

def handle_sigint(signum, frame):
    logger.info('Received SIGINT signal, initiating graceful shutdown')
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigint)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('xtraders')

# Configure Streamlit for production
def setup_streamlit():
    try:
        # Production-specific settings
        streamlit_config.set_option('server.address', '127.0.0.1')
        streamlit_config.set_option('server.port', int(os.getenv('PORT', 8501)))
        streamlit_config.set_option('server.baseUrlPath', '')
        
        # Security settings
        streamlit_config.set_option('server.enableCORS', False)  # Handled by Nginx
        streamlit_config.set_option('server.enableXsrfProtection', True)
        streamlit_config.set_option('server.enableWebsocketCompression', True)
        
        # Resource limits
        streamlit_config.set_option('server.maxUploadSize', 5)
        streamlit_config.set_option('server.maxMessageSize', 50)
        streamlit_config.set_option('browser.gatherUsageStats', False)
        
        # Cache settings
        streamlit_config.set_option('server.maxCachedMessageAge', 300)  # 5 minutes
        streamlit_config.set_option('server.enableStaticServing', True)
        
        logger.info('Production Streamlit configuration completed successfully')
    except Exception as e:
        logger.error(f'Failed to configure Streamlit: {str(e)}')
        raise

# WSGI application entry point with error handling
def create_app():
    try:
        setup_streamlit()
        main_script_path = os.path.join(os.path.dirname(__file__), 'trading_ui.py')
        server = Server(main_script_path=main_script_path, is_hello=False)
        logger.info('WSGI application created successfully')
        return server.server
    except Exception as e:
        logger.error(f'Failed to create WSGI application: {str(e)}')
        raise

# Create WSGI app instance with proper error handling
try:
    app = create_app()
    logger.info('WSGI application instance created')
except Exception as e:
    logger.error(f'Failed to create WSGI application instance: {str(e)}')
    sys.exit(1)

if __name__ == '__main__':
    try:
        # For development server only
        # Production should use Gunicorn with gunicorn_config.py
        http_server = WSGIServer(
            ('127.0.0.1', int(os.getenv('PORT', 8501))),
            app,
            log=logger
        )
        logger.info(f'Starting development server on port {os.getenv("PORT", 8501)}')
        http_server.serve_forever()
    except Exception as e:
        logger.error(f'Server failed to start: {str(e)}')
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info('Shutting down server')
        sys.exit(0)