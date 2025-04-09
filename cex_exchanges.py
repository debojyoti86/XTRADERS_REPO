import json
import time
import hmac
import hashlib
import requests
import base64
import websocket
import threading
import ssl
from decimal import Decimal
from typing import List, Dict, Any, Optional
from exchange import ExchangeService, TradingPair, OrderBook, OrderBookEntry
from ccxt.base.errors import AuthenticationError
from kucoin_exchange import KuCoinExchangeService

class BinanceExchangeService(ExchangeService):
    """Binance exchange service implementation"""
    def __init__(self):
        super().__init__()
        self.api_key = None
        self.api_secret = None
        self.base_url = "https://api.binance.com"
        self.ws_url = "wss://stream.binance.com:9443/ws"
        self.current_subscriptions = set()
        self.private_ws = None
        self.ws = None
        self.ws_thread = None
        self.heartbeat_thread = None
        self.last_pong_time = time.time()
        self.heartbeat_interval = 30
        self._reconnect_count = 0
        self.reconnect_delay = 2
        self.max_reconnect_attempts = 3
        self._ws_lock = threading.Lock()
        
    def set_credentials(self, api_key: str, api_secret: str):
        """Set API credentials for authentication"""
        self.api_key = api_key
        self.api_secret = api_secret
        
    def connect(self, max_retries: int = 3) -> bool:
        """Connect to Binance exchange with improved retry logic and WebSocket initialization"""
        with self._ws_lock:
            if not self.api_key or not self.api_secret:
                self.notify_error("API credentials not set")
                return False

            if self.is_connected:
                return True

            retry_count = 0
            base_delay = 2  # Increased base delay

            while retry_count < max_retries:
                try:
                    # Test REST API connection with authenticated request and timeout
                    headers = self._get_auth_headers()
                    response = requests.get(
                        f"{self.base_url}/api/v3/account",
                        headers=headers,
                        timeout=10
                    )

                    if response.status_code == 200:
                        # Initialize private WebSocket connection with retry
                        from binance_private_ws import BinancePrivateWebSocket
                        self.private_ws = BinancePrivateWebSocket(self.api_key, self.api_secret)
                        private_ws_attempts = 0
                        while private_ws_attempts < 3:
                            if self.private_ws.connect():
                                break
                            private_ws_attempts += 1
                            time.sleep(2)
                        
                        if private_ws_attempts == 3:
                            self.notify_error("Failed to establish private WebSocket connection after 3 attempts")
                            return False

                        # Initialize public WebSocket connection with improved error handling
                        try:
                            # Close existing connection if any
                            if self.ws:
                                try:
                                    self.ws.close()
                                except:
                                    pass
                                self.ws = None

                            # Enable trace for debugging
                            websocket.enableTrace(True)
                            
                            self.ws = websocket.WebSocketApp(
                                self.ws_url,
                                on_message=self._handle_ws_message,
                                on_error=self._handle_ws_error,
                                on_close=self._handle_ws_close,
                                on_open=self._handle_ws_open,
                                on_ping=self._handle_ws_ping,
                                on_pong=self._handle_ws_pong
                            )
                            
                            # Start WebSocket connection in a separate thread with improved settings
                            if self.ws_thread and self.ws_thread.is_alive():
                                self.ws_thread.join(timeout=1)

                            # Configure WebSocket with proper SSL settings
                            ssl_opts = {
                                "cert_reqs": ssl.CERT_REQUIRED,
                                "ssl_version": ssl.PROTOCOL_TLS,
                                "check_hostname": True,
                                "ca_certs": ssl.get_default_verify_paths().cafile
                            }

                            self.ws_thread = threading.Thread(
                                target=lambda: self.ws.run_forever(
                                    ping_interval=20,
                                    ping_timeout=10,
                                    ping_payload='ping',
                                    sslopt=ssl_opts
                                )
                            )
                            self.ws_thread.daemon = True
                            self.ws_thread.start()
                            
                            # Initialize heartbeat monitoring with improved timing
                            self.last_pong_time = time.time()
                            if not self.heartbeat_thread or not self.heartbeat_thread.is_alive():
                                if self.heartbeat_thread:
                                    self.heartbeat_thread.join(timeout=1)
                                self.heartbeat_thread = threading.Thread(target=self._monitor_connection)
                                self.heartbeat_thread.daemon = True
                                self.heartbeat_thread.start()
                            
                            # Wait for connection with improved timeout handling
                            start_time = time.time()
                            connection_timeout = 15  # Increased timeout
                            check_interval = 0.2  # More frequent checks
                            
                            while not self.is_connected and time.time() - start_time < connection_timeout:
                                time.sleep(check_interval)
                                
                            if not self.is_connected:
                                self.notify_error(f"WebSocket connection timeout after {connection_timeout} seconds")
                                return False
                                
                            self._reconnect_count = 0
                            self.notify_error("Successfully connected to Binance")
                            return True

                        except Exception as ws_error:
                            self.notify_error(f"WebSocket initialization failed: {str(ws_error)}")
                            return False
                            
                    elif response.status_code == 429:  # Rate limit exceeded
                        retry_after = int(response.headers.get('Retry-After', base_delay))
                        self.notify_error(f"Rate limit exceeded. Waiting {retry_after} seconds before retry")
                        time.sleep(retry_after)
                    elif response.status_code == 418:  # IP ban
                        self.notify_error("IP has been auto-banned for repeated violations")
                        return False
                    elif response.status_code in [401, 403]:  # Auth errors
                        self.notify_error("Authentication failed. Please check your API credentials")
                        return False
                    else:
                        self.notify_error(f"Connection failed: {response.status_code} - {response.text}")

                except requests.exceptions.Timeout:
                    self.notify_error("Connection timeout. Retrying...")
                except requests.exceptions.RequestException as e:
                    self.notify_error(f"Network error: {str(e)}")
                except Exception as e:
                    self.notify_error(f"Unexpected error: {str(e)}")

                # Exponential backoff with jitter
                delay = min(base_delay * (2 ** retry_count) + (time.time() % 1), 30)  # Cap at 30 seconds
                time.sleep(delay)
                retry_count += 1

            self.notify_error(f"Failed to connect after {max_retries} attempts")
            return False

    def _handle_ws_open(self, ws):
        """Handle WebSocket connection open"""
        self.is_connected = True
        self._reconnect_count = 0
        self.notify_error("WebSocket connection established")
        # Subscribe to previous subscriptions if any
        for symbol in self.current_subscriptions:
            self._subscribe_orderbook(symbol)

    def _handle_ws_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket connection close"""
        self.notify_error(f"WebSocket connection closed: {close_msg}")
        self.is_connected = False
        # Attempt to reconnect if not intentionally closed
        if self._reconnect_count < self.max_reconnect_attempts:
            self._reconnect_count += 1
            delay = self.reconnect_delay * (2 ** (self._reconnect_count - 1))
            time.sleep(min(delay, 30))  # Cap maximum delay at 30 seconds
            self.connect()
        else:
            self.notify_error("Max reconnection attempts reached")

    def _handle_ws_error(self, ws, error):
        """Handle WebSocket errors with improved error handling and reconnection logic"""
        error_msg = str(error)
        self.notify_error(f"WebSocket error: {error_msg}")
        
        # Check for specific SSL/TLS errors
        if "SSL" in error_msg or "CERTIFICATE" in error_msg:
            self.notify_error("SSL/TLS verification failed. Checking certificate configuration...")
            try:
                # Verify SSL context
                ssl_context = ssl.create_default_context()
                ssl_context.verify_mode = ssl.CERT_REQUIRED
                ssl_context.check_hostname = True
                
                # Update WebSocket SSL options
                if self.ws:
                    self.ws.sslopt.update({
                        "cert_reqs": ssl.CERT_REQUIRED,
                        "ssl_version": ssl.PROTOCOL_TLS,
                        "check_hostname": True,
                        "ca_certs": ssl.get_default_verify_paths().cafile
                    })
            except Exception as ssl_error:
                self.notify_error(f"SSL configuration error: {str(ssl_error)}")
        
        # Handle connection state
        self.is_connected = False
        
        # Attempt reconnection if appropriate
        if self._reconnect_count < self.max_reconnect_attempts:
            self._reconnect_count += 1
            delay = min(self.reconnect_delay * (2 ** (self._reconnect_count - 1)), 30)
            self.notify_error(f"Attempting reconnection in {delay} seconds (attempt {self._reconnect_count}/{self.max_reconnect_attempts})")
            time.sleep(delay)
            self.connect()
        else:
            self.notify_error("Maximum reconnection attempts reached. Please check your network connection and SSL configuration.")

        self.notify_error(f"WebSocket error: {error}")
        if not self.is_connected:
            self._attempt_reconnect()

    def _handle_ws_ping(self, ws, message):
        """Handle WebSocket ping messages"""
        ws.send('pong')
        self.last_pong_time = time.time()

    def _handle_ws_pong(self, ws, message):
        """Handle WebSocket pong messages"""
        self.last_pong_time = time.time()

    def _monitor_connection(self):
        """Monitor WebSocket connection health"""
        while True:
            if self.is_connected:
                current_time = time.time()
                if current_time - self.last_pong_time > self.heartbeat_interval:
                    self.notify_error("WebSocket connection heartbeat timeout")
                    if self.ws:
                        self.ws.close()
                        self._attempt_reconnect()
            time.sleep(5)  # Check every 5 seconds

    def _attempt_reconnect(self):
        """Attempt to reconnect with exponential backoff"""
        if self._reconnect_count >= self.max_reconnect_attempts:
            self.notify_error("Max reconnection attempts reached")
            return False

        self._reconnect_count += 1
        delay = self.reconnect_delay * (2 ** (self._reconnect_count - 1))
        self.notify_error(f"Attempting to reconnect in {delay} seconds...")
        time.sleep(min(delay, 30))  # Cap maximum delay at 30 seconds

        try:
            if self.ws:
                self.ws.close()
            return self.connect()
        except Exception as e:
            self.notify_error(f"Reconnection failed: {str(e)}")
            return False

            
    def _get_auth_headers(self) -> Dict[str, str]:
        """Generate authenticated request headers"""
        timestamp = int(time.time() * 1000)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            f"timestamp={timestamp}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return {
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/json',
            'timestamp': str(timestamp),
            'signature': signature
        }
        
    def disconnect(self) -> bool:
        """Disconnect from Binance exchange"""
        try:
            if self.private_ws:
                self.private_ws.disconnect()
                self.private_ws = None
            if self.ws:
                self.ws.close()
                self.ws = None
            if self.ws_thread and self.ws_thread.is_alive():
                self.ws_thread.join(timeout=1)
                self.ws_thread = None
            if self.heartbeat_thread and self.heartbeat_thread.is_alive():
                self.heartbeat_thread.join(timeout=1)
                self.heartbeat_thread = None
            self.is_connected = False
            self.current_subscriptions.clear()
            return True
        except Exception as e:
            self.notify_error(f"Failed to disconnect: {str(e)}")
            return False

    def get_available_pairs(self) -> Dict[str, TradingPair]:
        """Get available trading pairs from Binance"""
        try:
            response = requests.get(f"{self.base_url}/api/v3/exchangeInfo")
            response.raise_for_status()
            data = response.json()
            
            pairs = {}
            for symbol_data in data.get('symbols', []):
                if symbol_data.get('status') == 'TRADING':
                    symbol = symbol_data['symbol']
                    base_asset = symbol_data['baseAsset']
                    quote_asset = symbol_data['quoteAsset']
                    formatted_symbol = f"{base_asset}/{quote_asset}"
                    
                    pairs[formatted_symbol] = TradingPair(
                        symbol=formatted_symbol,
                        base_asset=base_asset,
                        quote_asset=quote_asset,
                        min_price=Decimal(str(symbol_data.get('filters', [{}])[0].get('minPrice', '0'))),
                        max_price=Decimal(str(symbol_data.get('filters', [{}])[0].get('maxPrice', '0'))),
                        min_qty=Decimal(str(symbol_data.get('filters', [{}])[1].get('minQty', '0'))),
                        max_qty=Decimal(str(symbol_data.get('filters', [{}])[1].get('maxQty', '0')))
                    )
            return pairs
        except Exception as e:
            self.notify_error(f"Failed to get trading pairs: {str(e)}")
            return {}

    def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent trades for a symbol from Binance"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/trades",
                params={'symbol': symbol.replace('/', ''), 'limit': limit}
            )
            response.raise_for_status()
            trades = response.json()
            
            return [{
                'id': str(trade['id']),
                'price': Decimal(str(trade['price'])),
                'amount': Decimal(str(trade['qty'])),
                'timestamp': trade['time'],
                'side': 'buy' if trade['isBuyerMaker'] else 'sell',
                'symbol': symbol
            } for trade in trades]
        except Exception as e:
            self.notify_error(f"Failed to get recent trades: {str(e)}")
            return []

    def subscribe_to_pair(self, symbol: str) -> bool:
        """Subscribe to updates for a trading pair"""
        try:
            formatted_symbol = symbol.lower().replace('/', '')
            if formatted_symbol not in self.current_subscriptions:
                self.current_subscriptions.add(formatted_symbol)
                if self.ws:
                    subscription = {
                        'method': 'SUBSCRIBE',
                        'params': [
                            f"{formatted_symbol}@trade",
                            f"{formatted_symbol}@depth@100ms"
                        ],
                        'id': int(time.time() * 1000)
                    }
                    self.ws.send(json.dumps(subscription))
            return True
        except Exception as e:
            self.notify_error(f"Failed to subscribe to {symbol}: {str(e)}")
            return False

    def unsubscribe_from_pair(self, symbol: str) -> bool:
        """Unsubscribe from updates for a trading pair"""
        try:
            formatted_symbol = symbol.lower().replace('/', '')
            if formatted_symbol in self.current_subscriptions:
                self.current_subscriptions.remove(formatted_symbol)
                if self.ws:
                    unsubscription = {
                        'method': 'UNSUBSCRIBE',
                        'params': [
                            f"{formatted_symbol}@trade",
                            f"{formatted_symbol}@depth@100ms"
                        ],
                        'id': int(time.time() * 1000)
                    }
                    self.ws.send(json.dumps(unsubscription))
                return True
            return False
        except Exception as e:
            self.notify_error(f"Failed to unsubscribe from {symbol}: {str(e)}")
            return False

    def _handle_ws_message(self, message: str):
        """Handle WebSocket messages"""
        try:
            data = json.loads(message)
            if 'e' in data:  # Event type
                if data['e'] == 'depthUpdate':
                    self._handle_orderbook_update(data)
                elif data['e'] == 'trade':
                    self._handle_trade_update(data)
        except Exception as e:
            self.notify_error(f"Error handling message: {str(e)}")

    def get_candles(self, symbol: str, interval: str = '1m', limit: int = 100) -> List[Dict[str, Any]]:
        """Get historical candle data from Binance"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/klines",
                params={
                    'symbol': symbol.replace('/', ''),
                    'interval': interval,
                    'limit': limit
                }
            )
            response.raise_for_status()
            candles = response.json()
            
            return [{
                'timestamp': candle[0],
                'open_price': Decimal(str(candle[1])),
                'high_price': Decimal(str(candle[2])),
                'low_price': Decimal(str(candle[3])),
                'close_price': Decimal(str(candle[4])),
                'volume': Decimal(str(candle[5])),
                'close_time': candle[6],
                'quote_volume': Decimal(str(candle[7])),
                'trades': candle[8],
                'taker_buy_base_volume': Decimal(str(candle[9])),
                'taker_buy_quote_volume': Decimal(str(candle[10]))
            } for candle in candles]
        except Exception as e:
            self.notify_error(f"Failed to get candles: {str(e)}")
            return []

    def get_orderbook(self, symbol: str, limit: int = 100) -> Optional[OrderBook]:
        """Get current orderbook data from Binance"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/depth",
                params={
                    'symbol': symbol.replace('/', ''),
                    'limit': limit
                }
            )
            response.raise_for_status()
            data = response.json()
            
            bids = [OrderBookEntry(
                price=Decimal(str(bid[0])),
                size=Decimal(str(bid[1]))
            ) for bid in data['bids']]
            
            asks = [OrderBookEntry(
                price=Decimal(str(ask[0])),
                size=Decimal(str(ask[1]))
            ) for ask in data['asks']]
            
            return OrderBook(bids=bids, asks=asks)
        except Exception as e:
            self.notify_error(f"Failed to get orderbook: {str(e)}")
            return None


class KuCoinExchangeService(ExchangeService):
    """KuCoin exchange service implementation"""
    def __init__(self):
        super().__init__()
        self.api_key = None
        self.api_secret = None
        self.api_passphrase = None
        self.base_url = "https://api.kucoin.com"
        self.ws_url = "wss://ws-api.kucoin.com"
        
    def set_credentials(self, api_key: str, api_secret: str, api_passphrase: str):
        """Set API credentials for authentication"""
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        
    def connect(self, max_retries: int = 3) -> bool:
        """Connect to KuCoin exchange"""
        if not all([self.api_key, self.api_secret, self.api_passphrase]):
            self.notify_error("API credentials not set")
            return False
            
        try:
            # Test connection with authenticated request
            headers = self._get_auth_headers('GET', '/api/v1/accounts')
            response = requests.get(f"{self.base_url}/api/v1/accounts", headers=headers)
            if response.status_code == 200:
                self.is_connected = True
                return super().connect()
            else:
                self.notify_error(f"Connection failed: {response.text}")
                return False
        except Exception as e:
            self.notify_error(f"Failed to connect: {str(e)}")
            return False
            
    def _get_auth_headers(self, method: str, endpoint: str, params: str = '') -> Dict[str, str]:
        """Generate authenticated request headers"""
        timestamp = int(time.time() * 1000)
        str_to_sign = f"{timestamp}{method}{endpoint}{params}"
        signature = base64.b64encode(
            hmac.new(
                base64.b64decode(self.api_secret),
                str_to_sign.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()
        
        passphrase = base64.b64encode(
            hmac.new(
                base64.b64decode(self.api_secret),
                self.api_passphrase.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()
        
        return {
            'KC-API-KEY': self.api_key,
            'KC-API-SIGN': signature,
            'KC-API-TIMESTAMP': str(timestamp),
            'KC-API-PASSPHRASE': passphrase,
            'KC-API-KEY-VERSION': '2',
            'Content-Type': 'application/json'
        }
        
    def _handle_ws_message(self, message: str):
        """Handle WebSocket messages"""
        try:
            data = json.loads(message)
            if 'type' in data:
                if data['type'] == 'message':
                    if data['topic'].startswith('/market/level2'):
                        self._handle_orderbook_update(data)
                    elif data['topic'].startswith('/market/match'):
                        self._handle_trade_update(data)
        except Exception as e:
            self.notify_error(f"Error handling message: {str(e)}")


class BitBNSExchangeService(ExchangeService):
    """BitBNS exchange service implementation"""
    def __init__(self):
        super().__init__()
        self.api_key = None
        self.api_secret = None
        self.base_url = "https://api.bitbns.com"
        self.ws_url = "wss://ws.bitbns.com"

    def set_credentials(self, api_key: str, api_secret: str):
        """Set API credentials for authentication"""
        self.api_key = api_key
        self.api_secret = api_secret

    def connect(self, max_retries: int = 3) -> bool:
        """Connect to BitBNS exchange"""
        if not self.api_key or not self.api_secret:
            self.notify_error("API credentials not set")
            return False

        try:
            # Test connection with authenticated request
            headers = self._get_auth_headers('GET', '/api/v2/tickers')
            response = requests.get(f"{self.base_url}/api/v2/tickers", headers=headers)
            if response.status_code == 200:
                self.is_connected = True
                return super().connect()
            else:
                self.notify_error(f"Connection failed: {response.text}")
                return False
        except Exception as e:
            self.notify_error(f"Failed to connect: {str(e)}")
            return False

    def _get_auth_headers(self, method: str, endpoint: str, body: str = '') -> Dict[str, str]:
        """Generate authenticated request headers"""
        timestamp = str(int(time.time() * 1000))
        payload = f"{timestamp}{method}{endpoint}{body}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()

        return {
            'X-BITBNS-APIKEY': self.api_key,
            'X-BITBNS-SIGNATURE': signature,
            'X-BITBNS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json'
        }

    def _handle_ws_message(self, message: str):
        """Handle WebSocket messages"""
        try:
            data = json.loads(message)
            if 'type' in data:
                if data['type'] == 'orderbook':
                    self._handle_orderbook_update(data)
                elif data['type'] == 'trade':
                    self._handle_trade_update(data)
        except Exception as e:
            self.notify_error(f"Error handling message: {str(e)}")