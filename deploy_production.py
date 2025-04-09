import os
import sys
import subprocess
import signal
import time
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/deployment.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('xtraders_deployment')

# Create necessary directories
def setup_directories():
    directories = ['logs', 'run', 'static']
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
    logger.info('Created necessary directories')

# Process management
class ProcessManager:
    def __init__(self):
        self.processes = {}
        self.is_running = True

    def start_gunicorn(self):
        cmd = [
            sys.executable, '-m', 'gunicorn',
            '--config', 'gunicorn_config.py',
            '--reload',
            'trading_ui:app'
        ]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        self.processes['gunicorn'] = process
        logger.info('Started Gunicorn server')

    def start_nginx(self):
        # In Windows, Nginx is typically started as a service
        # This is a placeholder for the actual Nginx service management
        try:
            subprocess.run(['net', 'start', 'nginx'], check=True)
            logger.info('Started Nginx server')
        except subprocess.CalledProcessError as e:
            logger.error(f'Failed to start Nginx: {e}')

    def stop_all(self):
        self.is_running = False
        # Stop Gunicorn
        if 'gunicorn' in self.processes:
            self.processes['gunicorn'].terminate()
            self.processes['gunicorn'].wait(timeout=5)
            logger.info('Stopped Gunicorn server')

        # Stop Nginx (Windows service)
        try:
            subprocess.run(['net', 'stop', 'nginx'], check=True)
            logger.info('Stopped Nginx server')
        except subprocess.CalledProcessError as e:
            logger.error(f'Failed to stop Nginx: {e}')

    def monitor_processes(self):
        while self.is_running:
            for name, process in self.processes.items():
                if process.poll() is not None:
                    logger.error(f'{name} process died, restarting...')
                    if name == 'gunicorn':
                        self.start_gunicorn()
            time.sleep(5)

def signal_handler(signum, frame):
    logger.info(f'Received signal {signum}')
    if process_manager:
        process_manager.stop_all()
    sys.exit(0)

if __name__ == '__main__':
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Setup directories
        setup_directories()

        # Initialize process manager
        process_manager = ProcessManager()

        # Start servers
        process_manager.start_gunicorn()
        process_manager.start_nginx()

        # Monitor processes
        process_manager.monitor_processes()

    except Exception as e:
        logger.error(f'Deployment failed: {e}')
        if process_manager:
            process_manager.stop_all()
        sys.exit(1)