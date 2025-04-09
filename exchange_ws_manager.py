import ssl
import time
import json
import threading
import websocket
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

@dataclass
class ExchangeConnectionState:
    connected: bool = False
    last_heartbeat: float = 0
    message_count: int = 0
    error_count: int = 0
    reconnect_count: int = 0
    stream_active: bool = False
    connection_quality: float = 1.0
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    connection_start_time: Optional[float] = None
    next_reconnect_time: Optional[float] = None
    recovery_mode: bool = False

class ExchangeWebSocketManager:
    def __init__(
        self,
        heartbeat_interval: int = 30,
        max_reconnect_attempts: int = 5,
        reconnect_delay: int = 5,
        connection_timeout: int = 30
    ):
        self.connections: Dict[str, Dict[str, Any]] = {}
        self.heartbeat_interval = heartbeat_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.connection_timeout = connection_timeout
        self._ssl_context = self._init_ssl_context()

    def _init_ssl_context(self) -> ssl.SSLContext:
        """Initialize SSL context with enhanced security settings"""
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            
            # Use strong cipher suites with forward secrecy
            ssl_context.set_ciphers(
                'ECDHE-ECDSA-AES256-GCM-SHA384:'
                'ECDHE-RSA-AES256-GCM-SHA384:'
                'ECDHE-ECDSA-CHACHA20-POLY1305:'
                'ECDHE-RSA-CHACHA20-POLY1305'
            )
            
            # Enable security options
            ssl_context.options |= (
                ssl.OP_NO_TLSv1 | 
                ssl.OP_NO_TLSv1_1 | 
                ssl.OP_NO_COMPRESSION |
                ssl.OP_CIPHER_SERVER_PREFERENCE
            )
            
            return ssl_context
        except Exception as e:
            print(f"Error creating SSL context: {str(e)}")
            raise

    def initialize_connection(
        self,
        exchange_name: str,
        ws_url: str,
        on_message: Callable,
        on_error: Callable,
        on_close: Callable,
        on_open: Callable
    ) -> bool:
        """Initialize a new WebSocket connection for a specific exchange"""
        try:
            if exchange_name in self.connections:
                print(f"Connection for {exchange_name} already exists")
                return False

            # Initialize connection state
            self.connections[exchange_name] = {
                'state': ExchangeConnectionState(),
                'ws_url': ws_url,
                'ws': None,
                'callbacks': {
                    'on_message': on_message,
                    'on_error': on_error,
                    'on_close': on_close,
                    'on_open': on_open
                }
            }

            # Create WebSocket connection
            ws = websocket.WebSocketApp(
                ws_url,
                on_message=lambda ws, msg: self._handle_message(exchange_name, msg),
                on_error=lambda ws, err: self._handle_error(exchange_name, err),
                on_close=lambda ws, code, msg: self._handle_close(exchange_name, code, msg),
                on_open=lambda ws: self._handle_open(exchange_name)
            )

            # Store WebSocket instance
            self.connections[exchange_name]['ws'] = ws
            self.connections[exchange_name]['state'].connection_start_time = time.time()

            # Start WebSocket connection in a separate thread
            ws_thread = threading.Thread(
                target=ws.run_forever,
                kwargs={
                    'sslopt': {
                        'cert_reqs': ssl.CERT_REQUIRED,
                        'check_hostname': True,
                        'ssl_version': ssl.PROTOCOL_TLS
                    },
                    'ping_interval': self.heartbeat_interval,
                    'ping_timeout': self.connection_timeout
                }
            )
            ws_thread.daemon = True
            ws_thread.start()

            return True

        except Exception as e:
            print(f"Error initializing connection for {exchange_name}: {str(e)}")
            return False

    def _handle_message(self, exchange_name: str, message: str) -> None:
        """Handle incoming WebSocket messages"""
        if exchange_name not in self.connections:
            return

        conn = self.connections[exchange_name]
        state = conn['state']

        try:
            # Update connection metrics
            state.message_count += 1
            state.last_heartbeat = time.time()
            state.stream_active = True

            # Process message through callback
            if conn['callbacks']['on_message']:
                conn['callbacks']['on_message'](conn['ws'], message)

        except Exception as e:
            print(f"Error processing message for {exchange_name}: {str(e)}")
            state.error_count += 1

    def _handle_error(self, exchange_name: str, error: Any) -> None:
        """Handle WebSocket errors with enhanced recovery strategies"""
        if exchange_name not in self.connections:
            return

        conn = self.connections[exchange_name]
        state = conn['state']
        
        # Update error metrics
        state.connected = False
        state.last_error = str(error)
        state.last_error_time = time.time()
        state.error_count += 1

        # Call error callback
        if conn['callbacks']['on_error']:
            conn['callbacks']['on_error'](conn['ws'], error)

        # Attempt reconnection if appropriate
        if state.reconnect_count < self.max_reconnect_attempts:
            state.reconnect_count += 1
            backoff_time = min(self.reconnect_delay * (2 ** (state.reconnect_count - 1)), 30)
            
            print(f"Scheduling reconnection for {exchange_name} in {backoff_time} seconds")
            threading.Timer(backoff_time, self._attempt_reconnect, args=[exchange_name]).start()
        else:
            print(f"Maximum reconnection attempts reached for {exchange_name}")
            state.recovery_mode = True

    def _handle_close(self, exchange_name: str, close_code: int, close_msg: str) -> None:
        """Handle WebSocket connection closure"""
        if exchange_name not in self.connections:
            return

        conn = self.connections[exchange_name]
        state = conn['state']
        
        # Update connection state
        state.connected = False
        state.stream_active = False

        # Call close callback
        if conn['callbacks']['on_close']:
            conn['callbacks']['on_close'](conn['ws'], close_code, close_msg)

        # Attempt reconnection for abnormal closures
        if close_code != 1000:  # Not a normal closure
            if state.reconnect_count < self.max_reconnect_attempts:
                self._attempt_reconnect(exchange_name)

    def _handle_open(self, exchange_name: str) -> None:
        """Handle WebSocket connection opening"""
        if exchange_name not in self.connections:
            return

        conn = self.connections[exchange_name]
        state = conn['state']
        
        # Update connection state
        state.connected = True
        state.stream_active = True
        state.last_heartbeat = time.time()
        state.reconnect_count = 0
        state.recovery_mode = False

        # Call open callback
        if conn['callbacks']['on_open']:
            conn['callbacks']['on_open'](conn['ws'])

    def _attempt_reconnect(self, exchange_name: str) -> None:
        """Attempt to reconnect to the WebSocket"""
        if exchange_name not in self.connections:
            return

        conn = self.connections[exchange_name]
        state = conn['state']

        try:
            # Close existing connection if any
            if conn['ws']:
                conn['ws'].close()

            # Create new WebSocket connection
            ws = websocket.WebSocketApp(
                conn['ws_url'],
                on_message=lambda ws, msg: self._handle_message(exchange_name, msg),
                on_error=lambda ws, err: self._handle_error(exchange_name, err),
                on_close=lambda ws, code, msg: self._handle_close(exchange_name, code, msg),
                on_open=lambda ws: self._handle_open(exchange_name)
            )

            # Update connection instance
            conn['ws'] = ws
            
            # Start WebSocket connection in a separate thread
            ws_thread = threading.Thread(
                target=ws.run_forever,
                kwargs={
                    'sslopt': {
                        'cert_reqs': ssl.CERT_REQUIRED,
                        'check_hostname': True,
                        'ssl_version': ssl.PROTOCOL_TLS
                    },
                    'ping_interval': self.heartbeat_interval,
                    'ping_timeout': self.connection_timeout
                }
            )
            ws_thread.daemon = True
            ws_thread.start()

        except Exception as e:
            print(f"Error during reconnection for {exchange_name}: {str(e)}")
            state.error_count += 1

    def close_connection(self, exchange_name: str) -> None:
        """Close the WebSocket connection for a specific exchange"""
        if exchange_name not in self.connections:
            return

        try:
            conn = self.connections[exchange_name]
            if conn['ws']:
                conn['ws'].close()
            del self.connections[exchange_name]
        except Exception as e:
            print(f"Error closing connection for {exchange_name}: {str(e)}")

    def close_all_connections(self) -> None:
        """Close all active WebSocket connections"""
        for exchange_name in list(self.connections.keys()):
            self.close_connection(exchange_name)