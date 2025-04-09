from decimal import Decimal
from typing import Dict, List, Optional, Any
import time
import json
import threading
import requests
import websocket
import ssl
from dataclasses import dataclass
from datetime import datetime
from ws_connection_manager import WebSocketConnectionManager
from exchange_ws_manager import ExchangeWebSocketManager
from exchange_integrator import ExchangeIntegrator
from models import OrderBook, OrderBookEntry
from exchange import TradingPair

@dataclass
class CandleData:
    timestamp: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    pair: TradingPair

# WebSocket configuration
WS_BASE_URL = 'wss://api.xtraders.com'  # Production WebSocket endpoint
WS_DEV_URL = 'wss://api-dev.xtraders.com'  # Development WebSocket endpoint
WS_HEARTBEAT_INTERVAL = 30  # Increased for better stability
WS_MAX_RECONNECT_ATTEMPTS = 5  # Increased max reconnection attempts
WS_RECONNECT_DELAY = 5  # Base delay between reconnection attempts
WS_CONNECTION_TIMEOUT = 30  # Connection timeout in seconds

# Enhanced SSL configuration
WS_SSL_OPTS = {
    "cert_reqs": ssl.CERT_REQUIRED,  # Require valid certificates
    "check_hostname": True,  # Enable hostname verification
    "ssl_version": ssl.PROTOCOL_TLS,  # Use latest TLS version
    "ciphers": 'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384'
}

def get_ssl_context(ws_hostname: str) -> ssl.SSLContext:
    """Get SSL context for secure WebSocket connection with enhanced security"""
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
            'ECDHE-RSA-CHACHA20-POLY1305'
        )
        
        # Enable security options
        ssl_context.options |= (
            ssl.OP_NO_TLSv1 | 
            ssl.OP_NO_TLSv1_1 | 
            ssl.OP_NO_COMPRESSION |
            ssl.OP_CIPHER_SERVER_PREFERENCE
        )
        
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        
        if not ssl_context:
            raise Exception("Failed to create SSL context")
        return ssl_context
    except Exception as e:
        print(f"Error creating SSL context: {str(e)}")
        raise

class MarketDataService:
    def __init__(self):
        self.exchange_ws_manager = ExchangeWebSocketManager(
            heartbeat_interval=WS_HEARTBEAT_INTERVAL,
            max_reconnect_attempts=WS_MAX_RECONNECT_ATTEMPTS,
            reconnect_delay=WS_RECONNECT_DELAY,
            connection_timeout=WS_CONNECTION_TIMEOUT
        )
        self.exchange_integrator = ExchangeIntegrator()
        self.order_books = {}
        self.candle_data = {}
        self.price_update_handlers = {}
        self.initialized_exchanges = set()
        self._initialized = False
        self._initialization_state = 'not_started'
        self._stream_active = False

    def connect_exchange(self, exchange_name: str, ws_url: str, max_retries: int = 3) -> bool:
        """Connect to a specific exchange's market data service with enhanced SSL and connection handling"""
        try:
            if not self._initialized:
                raise RuntimeError("Market data service not initialized")
                
            if exchange_name in self.initialized_exchanges:
                print(f"Exchange {exchange_name} is already connected")
                return True

            # Configure SSL context with proper certificate verification and modern security settings
            try:
                hostname = ws_url.split('/')[2]  # Extract hostname from ws_url
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
                
                # Enable security options
                ssl_context.options |= (
                    ssl.OP_NO_TLSv1 | 
                    ssl.OP_NO_TLSv1_1 | 
                    ssl.OP_NO_COMPRESSION |
                    ssl.OP_CIPHER_SERVER_PREFERENCE |
                    ssl.OP_SINGLE_DH_USE |
                    ssl.OP_SINGLE_ECDH_USE
                )
                
                ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
                
            except ssl.SSLError as ssl_error:
                print(f"SSL verification error for {exchange_name}: {str(ssl_error)}")
                return False
            except Exception as ssl_error:
                print(f"SSL configuration error for {exchange_name}: {str(ssl_error)}")
                return False

            # Initialize WebSocket connection with enhanced security and monitoring
            callbacks = {
                'on_message': self.on_message,
                'on_error': self.on_error,
                'on_close': self.on_close,
                'on_open': self.on_open,
                'on_ping': self._handle_ping,
                'on_pong': self._handle_pong
            }

            # Configure connection parameters
            connection_params = {
                'exchange_name': exchange_name,
                'callbacks': callbacks,
                'ssl_context': ssl_context,
                'ping_interval': 10,
                'ping_timeout': 5,
                'connection_timeout': 30,
                'reconnect_interval': 5,
                'max_reconnect_attempts': 5
            }

            success = self.exchange_ws_manager.initialize_connection(**connection_params)

            if success:
                self.initialized_exchanges.add(exchange_name)
                print(f"✓ Successfully connected to {exchange_name} with secure WebSocket")
                return True
            else:
                print(f"❌ Failed to connect to {exchange_name}")
                return False

        except Exception as e:
            print(f"❌ Error connecting to {exchange_name}: {str(e)}")
            return False

    def _handle_ping(self, ws, message):
        """Handle ping messages with proper error handling"""
        try:
            ws.send('pong')
        except Exception as e:
            print(f"Error sending pong response: {str(e)}")
            self._handle_connection_error(ws)

    def _handle_pong(self, ws, message):
        """Handle pong messages and update connection health metrics"""
        try:
            # Update last activity timestamp
            if hasattr(ws, 'exchange_name'):
                state = self.exchange_ws_manager.connections.get(ws.exchange_name)
                if state:
                    state['last_activity'] = time.time()
                    state['connection_quality'] = 1.0  # Reset connection quality on successful pong
        except Exception as e:
            print(f"Error handling pong message: {str(e)}")

    def _handle_connection_error(self, ws):
        """Handle connection errors and trigger reconnection if needed"""
        try:
            if hasattr(ws, 'exchange_name'):
                state = self.exchange_ws_manager.connections.get(ws.exchange_name)
                if state:
                    state['connection_quality'] *= 0.8  # Degrade connection quality on error
                    if state['connection_quality'] < 0.5:
                        print(f"Poor connection quality detected for {ws.exchange_name}, initiating reconnection...")
                        self.reconnect(ws.exchange_name)
        except Exception as e:
            print(f"Error handling connection error: {str(e)}")
    def initialize(self, max_retries: int = 3) -> bool:
        """Initialize the market data service with proper state management"""
        try:
            self._initialization_state = 'starting'
            
            # Verify exchange integrator
            if not self.exchange_integrator:
                raise ValueError("Exchange integrator not configured")
            
            # Initialize WebSocket manager
            if not self.exchange_ws_manager:
                raise ValueError("WebSocket manager not configured")
            
            # Clear existing state
            self.order_books.clear()
            self.candle_data.clear()
            self.price_update_handlers.clear()
            self.initialized_exchanges.clear()
            
            # Initialize core components with retry logic
            for attempt in range(max_retries):
                try:
                    self._stream_active = False
                    
                    # Verify WebSocket manager initialization
                    if not self.exchange_ws_manager.verify_initialization():
                        raise RuntimeError("WebSocket manager initialization failed")
                    
                    # Initialize exchange integrator
                    if not self.exchange_integrator.initialize():
                        raise RuntimeError("Exchange integrator initialization failed")
                    
                    self._initialized = True
                    self._initialization_state = 'completed'
                    print("✓ Market data service initialized successfully")
                    return True
                    
                except Exception as retry_error:
                    if attempt < max_retries - 1:
                        print(f"Initialization attempt {attempt + 1} failed: {str(retry_error)}. Retrying...")
                        time.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        raise RuntimeError(f"Failed after {max_retries} attempts: {str(retry_error)}")
            
            return False
            
        except Exception as e:
            self._initialization_state = 'failed'
            print(f"❌ Market data service initialization failed: {str(e)}")
            return False
        
        finally:
            if not self._initialized:
                self._initialization_state = 'failed'
                self._stream_active = False
    
    @property
    def initialized(self) -> bool:
        """Check if market data service is properly initialized"""
        return self._initialized
    
    def verify_stream_active(self) -> bool:
        """Verify if market data stream is active"""
        try:
            return self._stream_active and self._initialized
        except Exception:
            return False
    
    def verify_health(self) -> bool:
        """Verify market data service health"""
        try:
            return (
                self._initialized and
                self.exchange_integrator is not None and
                self.exchange_ws_manager is not None
            )
        except Exception:
            return False
            
    def on_message(self, ws, message):
        try:
            if not message:
                return
            self._stream_active = True
            try:
                data = json.loads(message)
                if not data:
                    return
                
                # Process message with exchange-specific handlers
                if exchange_name in self.price_update_handlers:
                    for handler in self.price_update_handlers[exchange_name]:
                        try:
                            handler(data)
                        except Exception as handler_error:
                            print(f"Error in price update handler for {exchange_name}: {str(handler_error)}")
            except json.JSONDecodeError as json_error:
                print(f"Invalid message format from {exchange_name}: {str(json_error)}")
            except Exception as e:
                print(f"Error processing message from {exchange_name}: {str(e)}")
        except Exception as e:
            print(f"Critical error in message handler: {str(e)}")
            self._stream_active = False

            def on_error(ws, error):
                print(f"WebSocket error for {exchange_name}: {str(error)}")
                if exchange_name in self.initialized_exchanges:
                    self.initialized_exchanges.remove(exchange_name)

            def on_close(ws, close_status_code, close_msg):
                print(f"WebSocket closed for {exchange_name}: {close_msg if close_msg else 'No message'} (code: {close_status_code})")
                if exchange_name in self.initialized_exchanges:
                    self.initialized_exchanges.remove(exchange_name)

            def on_open(ws):
                print(f"WebSocket connection established for {exchange_name}")
                self.initialized_exchanges.add(exchange_name)
                # Initialize exchange-specific streams
                self._subscribe_to_exchange_streams(exchange_name)

            # Initialize WebSocket connection for this exchange
            success = self.exchange_ws_manager.initialize_connection(
                exchange_name=exchange_name,
                ws_url=ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )

            if success:
                print(f"✓ Successfully connected to {exchange_name} market data service")
                return True
            else:
                print(f"❌ Failed to connect to {exchange_name} market data service")
                return False

        except Exception as e:
            print(f"❌ Critical error connecting to {exchange_name} market data service: {str(e)}")
            return False

    def _subscribe_to_exchange_streams(self, exchange_name: str) -> None:
        """Subscribe to market data streams for a specific exchange"""
        # This method will be implemented by each exchange specifically
        pass

    def add_price_update_handler(self, exchange_name: str, handler) -> None:
        """Add a price update handler for a specific exchange
        
        Args:
            exchange_name (str): Name of the exchange to add handler for
            handler (callable): Callback function to handle price updates
        """
        if not callable(handler):
            raise ValueError("Handler must be a callable function")
            
        if exchange_name not in self.price_update_handlers:
            self.price_update_handlers[exchange_name] = []
        self.price_update_handlers[exchange_name].append(handler)

    def remove_price_update_handler(self, exchange_name: str, handler) -> None:
        """Remove a price update handler for a specific exchange"""
        if exchange_name in self.price_update_handlers:
            if handler in self.price_update_handlers[exchange_name]:
                self.price_update_handlers[exchange_name].remove(handler)

    def disconnect_exchange(self, exchange_name: str) -> None:
        """Disconnect from a specific exchange's market data service"""
        if exchange_name in self.initialized_exchanges:
            self.exchange_ws_manager.close_connection(exchange_name)
            self.initialized_exchanges.remove(exchange_name)
            if exchange_name in self.price_update_handlers:
                self.price_update_handlers[exchange_name].clear()

    def disconnect_all(self) -> None:
        """Disconnect from all exchange market data services"""
        self.exchange_ws_manager.close_all_connections()
        self.initialized_exchanges.clear()
        self.price_update_handlers.clear()
    
    def _attempt_reconnect(self):
        """Attempt to reconnect to the market data service"""
        if not self.initialized:
            print("Attempting to reconnect...")
            if self.connect():
                self._reconnect_count = 0
                print("✓ Reconnection successful")
            else:
                print("❌ Reconnection failed")
                self._schedule_reconnect()

    def get_exchange_connection_status(self, exchange_name: str) -> bool:
        """Get the connection status for a specific exchange"""
        return exchange_name in self.initialized_exchanges

    def get_all_connection_statuses(self) -> Dict[str, bool]:
        """Get connection statuses for all exchanges"""
        return {exchange: True for exchange in self.initialized_exchanges}

    def add_price_update_handler(self, exchange_name: str, handler) -> None:
        """Add a price update handler for a specific exchange
        
        Args:
            exchange_name (str): Name of the exchange to add handler for
            handler (callable): Callback function to handle price updates
        """
        if not callable(handler):
            raise ValueError("Handler must be a callable function")
            
        if exchange_name not in self.price_update_handlers:
            self.price_update_handlers[exchange_name] = []
        if handler not in self.price_update_handlers[exchange_name]:
            self.price_update_handlers[exchange_name].append(handler)

    def remove_price_update_handler(self, exchange_name: str, handler) -> None:
        """Remove a price update handler for a specific exchange
        
        Args:
            exchange_name (str): Name of the exchange to remove handler for
            handler (callable): Callback function to remove from handlers
        """
        if exchange_name in self.price_update_handlers:
            if handler in self.price_update_handlers[exchange_name]:
                self.price_update_handlers[exchange_name].remove(handler)

    def connect(self) -> bool:
        """Initialize connections to all supported exchanges"""
        try:
            # Get SSL context for secure connections
            ssl_context = get_ssl_context(WS_BASE_URL.replace('wss://', ''))
            if not ssl_context:
                print("Failed to create SSL context")
                return False

            # Connect to main exchange
            success = self.connect_exchange(
                exchange_name="xtraders",
                ws_url=WS_BASE_URL
            )

            if not success:
                print("Failed to connect to main exchange")
                return False

            return True

        except Exception as e:
            print(f"Error connecting to market data service: {str(e)}")
            return False

    def subscribe_to_candles(self, trading_pair: str) -> bool:
        """Subscribe to candle data for a specific trading pair
        
        Args:
            trading_pair (str): Trading pair to subscribe to (e.g. 'BTC/USDT')
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        try:
            # Validate trading pair format
            if not isinstance(trading_pair, str) or '/' not in trading_pair:
                print(f"Invalid trading pair format: {trading_pair}")
                return False

            # Prepare subscription message
            subscribe_message = {
                "type": "subscribe",
                "channel": "candles",
                "symbol": trading_pair.replace('/', '')
            }

            # Send subscription message through WebSocket
            for exchange_name in self.initialized_exchanges:
                ws = self.exchange_ws_manager.get_connection(exchange_name)
                if ws and ws.sock and ws.sock.connected:
                    ws.send(json.dumps(subscribe_message))
                    print(f"Subscribed to {trading_pair} candles on {exchange_name}")
                    return True
                else:
                    print(f"WebSocket not connected for {exchange_name}")

            print("No active exchange connections available")
            return False

        except Exception as e:
            print(f"Error subscribing to candles for {trading_pair}: {str(e)}")
            return False
