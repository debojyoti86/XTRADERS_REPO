import webview
import threading
import streamlit
import sys
import os
import time
import requests
from trading_app import TradingApplication
from market_data import MarketDataService

def wait_for_streamlit(timeout=30):
    """Wait for Streamlit server to be ready"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get('http://127.0.0.1:8502/healthz')
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            time.sleep(0.5)
    return False

def run_streamlit():
    """Run the Streamlit server in a separate thread"""
    import subprocess
    try:
        process = subprocess.Popen([
            sys.executable, '-m', 'streamlit', 'run',
            'trading_ui.py',
            '--server.port', '8502',
            '--server.address', '127.0.0.1',
            '--server.headless', 'true',
            '--server.enableWebsocketCompression', 'false',
            '--server.enableXsrfProtection', 'false',
            '--server.enableCORS', 'false',
            '--browser.gatherUsageStats', 'false'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        
        # Start threads to monitor output in real-time
        def monitor_output(pipe, prefix):
            for line in pipe:
                print(f"{prefix}: {line.strip()}")
        
        threading.Thread(target=monitor_output, args=(process.stdout, "Streamlit"), daemon=True).start()
        threading.Thread(target=monitor_output, args=(process.stderr, "Streamlit Error"), daemon=True).start()
        
        # Check if process started successfully
        if process.poll() is not None:
            print("Error: Failed to start Streamlit server")
            return False
        return True
    except Exception as e:
        print(f"Error starting Streamlit server: {str(e)}")
        return False

def create_window():
    """Create the desktop window using PyWebView"""
    # Initialize trading application and market data service
    app = TradingApplication()
    market_data = MarketDataService()
    
    # Initialize services with retry logic
    max_retries = 3
    retry_delay = 2
    
    # Start the Streamlit server first to ensure WebSocket endpoint is available
    streamlit_thread = threading.Thread(target=run_streamlit, daemon=True)
    streamlit_thread.start()
    
    # Wait for Streamlit server to be ready
    if not wait_for_streamlit():
        print("Error: Streamlit server failed to start")
        sys.exit(1)
    
    # Now initialize services after Streamlit server is ready
    for attempt in range(max_retries):
        try:
            if not app.initialize():
                raise Exception("Failed to initialize trading application")
            
            # Ensure WebSocket server is ready before connecting market data service
            time.sleep(1)  # Give WebSocket server time to fully initialize
            if not market_data.connect():
                raise Exception("Failed to connect to market data service")
            
            break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print(f"Error: Failed after {max_retries} attempts: {str(e)}")
                sys.exit(1)
    
    # Start the Streamlit server in a separate thread
    streamlit_thread = threading.Thread(target=run_streamlit, daemon=True)
    streamlit_thread.start()
    
    # Wait for Streamlit server to be ready
    if not wait_for_streamlit():
        print("Error: Streamlit server failed to start")
        sys.exit(1)
    
    # Create a desktop window
    webview.create_window(
        title='XTraders Trading Application',
        url='http://127.0.0.1:8502',
        width=1200,
        height=800,
        resizable=True,
        min_size=(800, 600)
    )
    
    # Start the desktop application
    webview.start(debug=False)

if __name__ == '__main__':
    create_window()