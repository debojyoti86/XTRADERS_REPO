import webview
import threading
import streamlit
import sys
import os
import time
import requests
import ssl
import websocket
from trading_app import TradingApplication
from market_data import MarketDataService
from typing import Optional

class DesktopApplication:
    def __init__(self):
        self.app: Optional[TradingApplication] = None
        self.market_data: Optional[MarketDataService] = None
        self.streamlit_process = None
        self.window = None
        self.is_running = False
        self._init_lock = threading.Lock()
        self.max_retries = 3
        self.retry_delay = 2
        self.connection_timeout = 30
        
    def _configure_ssl(self):
        """Configure SSL context for secure WebSocket connections with enhanced security"""
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            ssl_context.check_hostname = True
            ssl_context.load_default_certs()
            
            # Use strong cipher suites with forward secrecy
            ssl_context.set_ciphers(
                'ECDHE-ECDSA-AES256-GCM-SHA384:'
                'ECDHE-RSA-AES256-GCM-SHA384:'
                'ECDHE-ECDSA-CHACHA20-POLY1305:'
                'ECDHE-RSA-CHACHA20-POLY1305:'
                'ECDHE-ECDSA-AES128-GCM-SHA256:'
                'ECDHE-RSA-AES128-GCM-SHA256'
            )
            
            # Disable older protocols and enable security options
            ssl_context.options |= (
                ssl.OP_NO_TLSv1 | 
                ssl.OP_NO_TLSv1_1 | 
                ssl.OP_NO_COMPRESSION |  # Prevent CRIME attack
                ssl.OP_CIPHER_SERVER_PREFERENCE |  # Use server's cipher preferences
                ssl.OP_SINGLE_DH_USE |  # Ensure perfect forward secrecy
                ssl.OP_SINGLE_ECDH_USE  # Ensure perfect forward secrecy for ECDH
            )
            
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2  # Enforce minimum TLS 1.2
            return ssl_context
        except Exception as e:
            print(f"Error configuring SSL: {str(e)}")
            print("Falling back to basic SSL configuration...")
            try:
                return ssl.create_default_context()
            except Exception as fallback_error:
                print(f"Fallback SSL configuration failed: {str(fallback_error)}")
                return None

    def _wait_for_streamlit(self, timeout: int = 30) -> bool:
        """Wait for Streamlit server to be ready with improved error handling"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    'http://127.0.0.1:8502/healthz',
                    timeout=5,
                    verify=True
                )
                if response.status_code == 200:
                    return True
            except requests.exceptions.RequestException as e:
                if time.time() - start_time >= timeout:
                    print(f"Streamlit server startup timeout: {str(e)}")
                    return False
                time.sleep(0.5)
            except Exception as e:
                print(f"Error checking Streamlit status: {str(e)}")
                if time.time() - start_time >= timeout:
                    return False
                time.sleep(0.5)
        return False

    def _run_streamlit(self) -> bool:
        """Run the Streamlit server with improved process management and port handling"""
        import subprocess
        import time
        from port_utils import ensure_port_available, find_available_port, is_port_in_use

        # Default Streamlit port
        port = int(os.environ.get('STREAMLIT_SERVER_PORT', 8502))
        port_range = 100

        # Try to ensure the default port is available with increased attempts
        if not ensure_port_available(port, max_attempts=10):
            # If we can't free up the default port, try to find another one
            new_port = find_available_port(port + 1, port + port_range)
            if new_port:
                print(f"Port {port} is in use. Using port {new_port} instead.")
                port = new_port
                os.environ['STREAMLIT_SERVER_PORT'] = str(port)
                # Add a small delay after port change
                time.sleep(1)
            else:
                print(f"Error: Could not find an available port in range {port+1}-{port+port_range}")
                return False

        # Double check port availability before proceeding
        if is_port_in_use(port):
            print(f"Error: Port {port} is still in use despite attempts to free it")
            return False

        try:
            # Prepare Streamlit command with enhanced configuration
            streamlit_cmd = [
                sys.executable,
                '-m',
                'streamlit',
                'run',
                'trading_ui.py',
                '--server.port', str(port),
                '--server.address', '127.0.0.1',
                '--server.maxUploadSize', '200',
                '--server.maxMessageSize', '200',
                '--server.enableXsrfProtection', 'false',
                '--server.enableCORS', 'true',
                '--browser.serverAddress', '127.0.0.1',
                '--browser.gatherUsageStats', 'false'
            ]

            # Start Streamlit process with enhanced error handling and initialization delay
            self.streamlit_process = subprocess.Popen(
                streamlit_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Add initialization delay to allow server to start properly
            time.sleep(3)

            def monitor_output(pipe, prefix):
                try:
                    for line in pipe:
                        print(f"{prefix}: {line.strip()}")
                except Exception as e:
                    print(f"Error monitoring {prefix}: {str(e)}")

            threading.Thread(
                target=monitor_output,
                args=(self.streamlit_process.stdout, "Streamlit"),
                daemon=True
            ).start()
            
            threading.Thread(
                target=monitor_output,
                args=(self.streamlit_process.stderr, "Streamlit Error"),
                daemon=True
            ).start()

            if self.streamlit_process.poll() is not None:
                print("Error: Failed to start Streamlit server")
                return False
                
            return True
        except Exception as e:
            print(f"Error starting Streamlit server: {str(e)}")
            return False

    def _initialize_services(self) -> bool:
        """Initialize trading application and market data services with retry logic"""
        with self._init_lock:
            try:
                self.app = TradingApplication()
                self.market_data = MarketDataService()

                for attempt in range(self.max_retries):
                    try:
                        if not self.app.initialize():
                            raise Exception("Failed to initialize trading application")

                        # Configure WebSocket SSL
                        ssl_context = self._configure_ssl()
                        if not ssl_context:
                            raise Exception("Failed to configure SSL context")

                        # Ensure WebSocket server is ready
                        time.sleep(1)
                        
                        if not self.market_data.connect():
                            raise Exception("Failed to connect to market data service")

                        return True

                    except Exception as e:
                        if attempt < self.max_retries - 1:
                            print(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {self.retry_delay} seconds...")
                            time.sleep(self.retry_delay)
                        else:
                            print(f"Error: Failed after {self.max_retries} attempts: {str(e)}")
                            return False

            except Exception as e:
                print(f"Error initializing services: {str(e)}")
                return False

    def _create_window(self):
        """Create and configure the desktop window"""
        try:
            self.window = webview.create_window(
                title='XTraders Trading Application',
                url='http://127.0.0.1:8502',
                width=1200,
                height=800,
                resizable=True,
                min_size=(800, 600)
            )
            return True
        except Exception as e:
            print(f"Error creating window: {str(e)}")
            return False

    def start(self, standalone_mode=True):
        """Start the desktop application with enhanced initialization sequence and error handling
        Args:
            standalone_mode (bool): If True, run GUI without trading services
        """
        try:
            self.startup_state = {
                'streamlit_started': False,
                'streamlit_ready': False,
                'services_initialized': False,
                'window_created': False
            }

            # Start Streamlit server with proper error handling
            print("Starting Streamlit server...")
            if not self._run_streamlit():
                print("❌ Failed to start Streamlit server")
                return
            self.startup_state['streamlit_started'] = True

            # Wait for Streamlit server with timeout and health check
            print("Waiting for Streamlit server to be ready...")
            if not self._wait_for_streamlit(self.connection_timeout):
                print("❌ Streamlit server failed to start")
                self.cleanup()
                return
            self.startup_state['streamlit_ready'] = True
            print("✓ Streamlit server is ready")

            # Initialize services with proper sequence
            if not standalone_mode:
                print("Initializing trading services...")
                if not self._initialize_services():
                    print("❌ Failed to initialize trading services")
                    self.cleanup()
                    return
                self.startup_state['services_initialized'] = True
                print("✓ Trading services initialized successfully")

            # Create window with proper error handling
            print("Creating application window...")
            if not self._create_window():
                print("❌ Failed to create window")
                self.cleanup()
                return
            self.startup_state['window_created'] = True
            print("✓ Application window created successfully")

            # Start application
            print("Starting application...")
            self.is_running = True
            webview.start(debug=False)

        except Exception as e:
            print(f"❌ Critical error during startup: {str(e)}")
            self.cleanup()
            raise

        except Exception as e:
            print(f"Error starting application: {str(e)}")
            self.cleanup()

    def cleanup(self):
        """Clean up resources and shut down services"""
        try:
            if self.market_data:
                self.market_data.disconnect()
            if self.app:
                self.app.cleanup()
            if self.streamlit_process:
                self.streamlit_process.terminate()
                self.streamlit_process.wait(timeout=5)
            if self.window:
                self.window.destroy()
            self.is_running = False
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")

def main():
    app = DesktopApplication()
    try:
        app.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        app.cleanup()

if __name__ == '__main__':
    main()