import websocket
import threading
import time
import json
import requests
import ssl
from typing import Optional, Dict, Any

class BinancePrivateWebSocket:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.ws: Optional[websocket.WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.keep_alive_thread: Optional[threading.Thread] = None
        self.is_connected = False
        self.listen_key: Optional[str] = None
        self._ws_lock = threading.Lock()
        self.last_heartbeat = time.time()
        self.callbacks = {}
        websocket.enableTrace(True)  # Enable WebSocket debugging

    def _get_listen_key(self) -> bool:
        """Get a valid listenKey from Binance with proper error handling"""
        try:
            headers = {'X-MBX-APIKEY': self.api_key}
            response = requests.post(
                'https://api.binance.com/api/v3/userDataStream',
                headers=headers,
                timeout=10  # Add timeout
            )
            
            if response.status_code == 200:
                self.listen_key = response.json()['listenKey']
                print(f"Successfully obtained listenKey")
                return True
            elif response.status_code == 401:
                print("Authentication failed. Please check your API credentials")
                return False
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 30))
                print(f"Rate limit exceeded. Waiting {retry_after} seconds")
                time.sleep(retry_after)
                return self._get_listen_key()  # Retry after waiting
            else:
                print(f"Failed to get listenKey: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            print("Timeout while getting listenKey. Retrying...")
            time.sleep(5)
            return self._get_listen_key()
        except requests.exceptions.RequestException as e:
            print(f"Network error getting listenKey: {str(e)}")
            return False
        except Exception as e:
            print(f"Unexpected error getting listenKey: {str(e)}")
            return False

    def _keep_listen_key_alive(self):
        """Keep the listenKey alive with periodic pings and proper error handling"""
        while self.is_connected and self.listen_key:
            try:
                time.sleep(30 * 60)  # Ping every 30 minutes
                headers = {'X-MBX-APIKEY': self.api_key}
                response = requests.put(
                    'https://api.binance.com/api/v3/userDataStream',
                    headers=headers,
                    params={'listenKey': self.listen_key},
                    timeout=10  # Add timeout
                )
                
                if response.status_code == 200:
                    print("Successfully refreshed listenKey")
                    self.last_heartbeat = time.time()
                elif response.status_code == 401:
                    print("Authentication failed during listenKey refresh")
                    self._attempt_reconnect()
                elif response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 30))
                    print(f"Rate limit exceeded during refresh. Waiting {retry_after} seconds")
                    time.sleep(retry_after)
                else:
                    print(f"Failed to refresh listenKey: {response.status_code} - {response.text}")
                    self._attempt_reconnect()
                    
            except requests.exceptions.Timeout:
                print("Timeout while refreshing listenKey")
                time.sleep(5)
                continue
            except requests.exceptions.RequestException as e:
                print(f"Network error in keep-alive ping: {str(e)}")
                self._attempt_reconnect()
            except Exception as e:
                print(f"Unexpected error in keep-alive ping: {str(e)}")
                self._attempt_reconnect()

    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            event_type = data.get('e')
            if event_type in self.callbacks:
                self.callbacks[event_type](data)
            else:
                print(f"Received unhandled event type: {event_type}")
        except Exception as e:
            print(f"Error processing message: {str(e)}")

    def _on_error(self, ws, error):
        """Handle WebSocket errors"""
        print(f"WebSocket error: {str(error)}")
        if not self.is_connected:
            self._attempt_reconnect()

    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket connection closure"""
        print(f"WebSocket connection closed: {close_msg}")
        self.is_connected = False
        self._attempt_reconnect()

    def _on_open(self, ws):
        """Handle WebSocket connection opening"""
        print("WebSocket connection established")
        self.is_connected = True
        self.last_heartbeat = time.time()

    def _attempt_reconnect(self, max_retries: int = 5):
        """Attempt to reconnect to WebSocket with improved retry logic and exponential backoff"""
        if not self.is_connected:
            base_delay = 2  # Base delay in seconds
            max_delay = 30  # Maximum delay cap in seconds
            
            for attempt in range(max_retries):
                print(f"Reconnection attempt {attempt + 1}/{max_retries}")
                
                # Calculate delay with exponential backoff
                delay = min(base_delay * (2 ** attempt), max_delay)
                print(f"Waiting {delay} seconds before next attempt")
                time.sleep(delay)
                
                # Close existing connection if any
                if self.ws:
                    try:
                        self.ws.close()
                    except:
                        pass
                    self.ws = None
                
                # Attempt to reconnect
                if self.connect():
                    print("Successfully reconnected")
                    return True
                    
            print(f"Failed to reconnect after {max_retries} attempts")
            return False

    def connect(self) -> bool:
        """Establish WebSocket connection with proper authentication"""
        with self._ws_lock:
            if self.is_connected:
                return True

            if not self._get_listen_key():
                return False

            socket_url = f"wss://stream.binance.com:9443/ws/{self.listen_key}"
            
            # Initialize WebSocket connection
            self.ws = websocket.WebSocketApp(
                socket_url,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open
            )

            # Start WebSocket connection in a separate thread
            self.ws_thread = threading.Thread(
                target=lambda: self.ws.run_forever(
                    ping_interval=20,
                    ping_timeout=10,
                    sslopt={"cert_reqs": ssl.CERT_NONE}
                )
            )
            self.ws_thread.daemon = True
            self.ws_thread.start()

            # Start keep-alive thread
            self.keep_alive_thread = threading.Thread(target=self._keep_listen_key_alive)
            self.keep_alive_thread.daemon = True
            self.keep_alive_thread.start()

            return True

    def disconnect(self):
        """Properly close the WebSocket connection"""
        self.is_connected = False
        if self.ws:
            self.ws.close()

    def register_callback(self, event_type: str, callback):
        """Register a callback for specific event types"""
        self.callbacks[event_type] = callback