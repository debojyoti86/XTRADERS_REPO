import sys
import os
import time
import threading
import ssl
import requests
import websocket
import argparse
import traceback
from desktop_app_v2 import DesktopApplication
from port_utils import ensure_port_available, find_available_port

# WebSocket configuration constants
WS_RECONNECT_DELAY = 5  # seconds
WS_MAX_RECONNECT_ATTEMPTS = 3
WS_CONNECTION_TIMEOUT = 30  # seconds

def configure_ssl():
    """Configure SSL context for secure WebSocket connections with enhanced security"""
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED
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
        print(f"Warning: SSL configuration error: {str(e)}")
        print("Falling back to basic SSL configuration...")
        try:
            return ssl.create_default_context()
        except Exception as fallback_error:
            print(f"Fallback SSL configuration failed: {str(fallback_error)}")
            return None

def check_server_health(url, timeout=5, max_retries=3):
    """Check if a server is healthy and responding with enhanced retry logic and SSL verification"""
    ssl_context = configure_ssl()
    session = requests.Session()
    
    if ssl_context:
        session.verify = True
        session.headers.update({
            'User-Agent': 'XTraders/1.0',
            'Connection': 'keep-alive'
        })
    
    for attempt in range(max_retries):
        try:
            response = session.get(
                url, 
                timeout=timeout,
                verify=True if ssl_context else False
            )
            if response.status_code == 200:
                return True
            print(f"Server health check failed with status code: {response.status_code}")
            
        except requests.exceptions.SSLError as ssl_err:
            print(f"SSL verification failed: {ssl_err}")
            if attempt == max_retries - 1:
                print("Attempting connection without SSL verification...")
                try:
                    response = session.get(url, timeout=timeout, verify=False)
                    return response.status_code == 200
                except requests.exceptions.RequestException:
                    pass
                    
        except requests.exceptions.RequestException as e:
            if attempt == 0:
                print(f"Server health check attempt {attempt+1}/{max_retries} failed: {str(e)}")
        
        if attempt < max_retries - 1:
            retry_delay = min(2 ** attempt, 10)  # Exponential backoff with max 10 seconds
            time.sleep(retry_delay)
    
    return False

def wait_for_server(url, timeout=30, check_interval=1):
    """Wait for server to become available with timeout"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_server_health(url, timeout=2, max_retries=1):
            return True
        time.sleep(check_interval)
    return False

def main():
    """Main entry point for the XTraders GUI application with enhanced WebSocket handling"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='XTraders Trading Application')
    parser.add_argument('--standalone', action='store_true', help='Run in standalone mode (UI only)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--port', type=int, default=8502, help='Port for the Streamlit server')
    parser.add_argument('--port-range', type=int, default=100, help='Range to search for available ports')
    parser.add_argument('--retry', type=int, default=WS_MAX_RECONNECT_ATTEMPTS, 
                        help=f'Maximum connection retry attempts (default: {WS_MAX_RECONNECT_ATTEMPTS})')
    parser.add_argument('--startup-timeout', type=int, default=WS_CONNECTION_TIMEOUT,
                        help=f'Server startup timeout in seconds (default: {WS_CONNECTION_TIMEOUT})')
    args = parser.parse_args()
    
    print("Starting XTraders Trading Application...")
    
    # Configure WebSocket settings
    websocket.enableTrace(args.debug)  # Enable trace only in debug mode
    ssl_context = configure_ssl()
    
    # Initialize the desktop application with improved error handling
    app = DesktopApplication()
    
    try:
        # Start the application with the specified mode
        if args.standalone:
            print("Initializing GUI in standalone mode (UI only)...")
            # Initialize port management with enhanced error handling
            port = args.port
            max_port = port + args.port_range
            
            # Try to ensure port availability with multiple attempts
            if not ensure_port_available(port, max_attempts=5):
                print(f"Attempting to find alternative port in range {port+1}-{max_port}")
                new_port = find_available_port(port + 1, max_port)
                if new_port:
                    print(f"Port {port} is in use. Using port {new_port} instead.")
                    port = new_port
                else:
                    print(f"Error: Could not find an available port in range {port+1}-{max_port}")
                    sys.exit(1)
            
            # Set the port in environment variables for Streamlit
            os.environ['STREAMLIT_SERVER_PORT'] = str(port)
            print(f"Starting standalone mode on port {port}...")
            app.start(standalone_mode=True)
        else:
            print("Initializing GUI with trading services...")
            # Enhanced server initialization with improved port management
            port = args.port
            max_port = port + args.port_range
            
            # Try to ensure port availability with multiple attempts
            if not ensure_port_available(port, max_attempts=5):
                print(f"Attempting to find alternative port in range {port+1}-{max_port}")
                new_port = find_available_port(port + 1, max_port)
                if new_port:
                    print(f"Port {port} is in use. Using port {new_port} instead.")
                    port = new_port
                else:
                    print(f"Error: Could not find an available port in range {port+1}-{max_port}")
                    sys.exit(1)
            
            # Set the port in environment variables for Streamlit
            os.environ['STREAMLIT_SERVER_PORT'] = str(port)
            health_url = f'http://127.0.0.1:{port}/healthz'
            
            # Enhanced server health check and startup sequence
            server_status = check_server_health(health_url)
            if not server_status:
                print("WebSocket server health check failed. Attempting to start server...")
                
                # Try to start the server with configurable timeout
                if not wait_for_server(health_url, timeout=args.startup_timeout):
                    print(f"Warning: Server startup timed out after {args.startup_timeout} seconds.")
                    print("Starting in standalone mode with limited features.")
                    app.start(standalone_mode=True)
                else:
                    print("WebSocket server successfully started. Enabling full features.")
                    app.start(standalone_mode=False)
            else:
                print("WebSocket server is ready. Starting with full features.")
                app.start(standalone_mode=False)
    except KeyboardInterrupt:
        print("\nApplication terminated by user.")
    except Exception as e:
        print(f"Error starting application: {str(e)}")
        if args.debug:
            traceback.print_exc()
        sys.exit(1)
    finally:
        # Ensure proper cleanup on exit
        print("Cleaning up resources...")
        app.cleanup()

if __name__ == '__main__':
    main()