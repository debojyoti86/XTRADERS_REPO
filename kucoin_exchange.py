import json
import time
import hmac
import hashlib
import base64
import websocket
import threading
import ssl
from decimal import Decimal
from typing import List, Dict, Any, Optional
from exchange import ExchangeService, TradingPair, OrderBook, OrderBookEntry
from ccxt.base.errors import AuthenticationError

class KuCoinExchangeService(ExchangeService):
    """KuCoin exchange service implementation"""
    def __init__(self):
        super().__init__()
        self.api_key = None
        self.api_secret = None
        self.api_passphrase = None
        self.base_url = "https://api.kucoin.com"
        self.ws_url = None  # Will be obtained from API
        self.current_subscriptions = set()
        self.ws = None
        self.ws_thread = None
        self.heartbeat_thread = None
        self.last_pong_time = time.time()
        self.heartbeat_interval = 30
        self._reconnect_count = 0
        self.reconnect_delay = 2
        self.max_reconnect_attempts = 3
        self._ws_lock = threading.Lock()
        
    def set_credentials(self, api_key: str, api_secret: str, api_passphrase: str):
        """Set API credentials for authentication"""
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase

    def _get_ws_token(self) -> Optional[str]:
        """Get WebSocket token from KuCoin API"""
        try:
            response = requests.post(f"{self.base_url}/api/v1/bullet-public")
            if response.status_code == 200:
                data = response.json()
                token = data['data']['token']
                ws_endpoints = data['data']['instanceServers']
                if ws_endpoints:
                    self.ws_url = ws_endpoints[0]['endpoint'] + "?token=" + token
                    return token
            return None
        except Exception as e:
            self.notify_error(f"Failed to get WebSocket token: {str(e)}")
            return None

    def connect(self, max_retries: int = 3) -> bool:
        """Connect to KuCoin exchange"""
        with self._ws_lock:
            if self.is_connected:
                return True

            # Get WebSocket token and endpoint
            if not self._get_ws_token():
                return False

            try:
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

                # Start WebSocket connection
                self.ws_thread = threading.Thread(
                    target=lambda: self.ws.run_forever(
                        ping_interval=20,
                        ping_timeout=10,
                        ping_payload='ping',
                        sslopt={
                            "cert_reqs": ssl.CERT_REQUIRED,
                            "check_hostname": True
                        }
                    )
                )
                self.ws_thread.daemon = True
                self.ws_thread.start()

                # Wait for connection
                start_time = time.time()
                while not self.is_connected and time.time() - start_time < 30:
                    time.sleep(0.1)

                return self.is_connected

            except Exception as e:
                self.notify_error(f"Failed to connect: {str(e)}")
                return False

    def disconnect(self) -> bool:
        """Disconnect from KuCoin exchange"""
        try:
            if self.ws:
                self.ws.close()
            self.is_connected = False
            return True
        except Exception as e:
            self.notify_error(f"Error disconnecting: {str(e)}")
            return False

    def get_available_pairs(self) -> List[TradingPair]:
        """Get available trading pairs from KuCoin"""
        try:
            response = requests.get(f"{self.base_url}/api/v1/symbols")
            if response.status_code == 200:
                pairs = []
                for symbol_data in response.json()['data']:
                    pair = TradingPair(symbol_data['symbol'])
                    pair.base_asset = symbol_data['baseCurrency']
                    pair.quote_asset = symbol_data['quoteCurrency']
                    pairs.append(pair)
                return pairs
            return []
        except Exception as e:
            self.notify_error(f"Error getting trading pairs: {str(e)}")
            return []

    def get_orderbook(self, symbol: str) -> Optional[OrderBook]:
        """Get order book for a symbol"""
        try:
            response = requests.get(f"{self.base_url}/api/v1/market/orderbook/level2_20?symbol={symbol}")
            if response.status_code == 200:
                data = response.json()['data']
                book = OrderBook()
                book.symbol = symbol
                book.timestamp = int(time.time() * 1000)

                # Process bids and asks
                bids = [OrderBookEntry(Decimal(price), Decimal(size), 'KuCoin') 
                       for price, size in data['bids']]
                asks = [OrderBookEntry(Decimal(price), Decimal(size), 'KuCoin') 
                       for price, size in data['asks']]

                book.update(bids, asks)
                return book
            return None
        except Exception as e:
            self.notify_error(f"Error getting orderbook: {str(e)}")
            return None

    def get_candles(self, symbol: str, interval: str = '1m', limit: int = 100) -> List[Dict]:
        """Get candlestick data for a symbol"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/market/candles",
                params={
                    'symbol': symbol,
                    'type': interval,
                    'limit': limit
                }
            )
            if response.status_code == 200:
                return response.json()['data']
            return []
        except Exception as e:
            self.notify_error(f"Error getting candles: {str(e)}")
            return []

    def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Get recent trades for a symbol"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/market/histories",
                params={
                    'symbol': symbol,
                    'limit': limit
                }
            )
            if response.status_code == 200:
                return response.json()['data']
            return []
        except Exception as e:
            self.notify_error(f"Error getting recent trades: {str(e)}")
            return []

    def subscribe_to_pair(self, symbol: str) -> bool:
        """Subscribe to market data for a trading pair"""
        try:
            if not self.is_connected:
                return False

            message = {
                'type': 'subscribe',
                'topic': f'/market/ticker:{symbol}',
                'privateChannel': False,
                'response': True
            }
            self.ws.send(json.dumps(message))
            self.current_subscriptions.add(symbol)
            return True
        except Exception as e:
            self.notify_error(f"Error subscribing to {symbol}: {str(e)}")
            return False

    def unsubscribe_from_pair(self, symbol: str) -> bool:
        """Unsubscribe from market data for a trading pair"""
        try:
            if not self.is_connected:
                return False

            message = {
                'type': 'unsubscribe',
                'topic': f'/market/ticker:{symbol}',
                'privateChannel': False,
                'response': True
            }
            self.ws.send(json.dumps(message))
            self.current_subscriptions.discard(symbol)
            return True
        except Exception as e:
            self.notify_error(f"Error unsubscribing from {symbol}: {str(e)}")
            return False

    def _handle_ws_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            if data.get('type') == 'message':
                if 'topic' in data:
                    if data['topic'].startswith('/market/ticker'):
                        symbol = data['topic'].split(':')[1]
                        self._process_ticker_update(symbol, data['data'])
        except Exception as e:
            self.notify_error(f"Error processing message: {str(e)}")

    def _process_ticker_update(self, symbol: str, data: Dict):
        """Process ticker update data"""
        try:
            if symbol in self.trading_pairs:
                pair = self.trading_pairs[symbol]
                pair.last_price = Decimal(str(data['price']))
                pair.volume_24h = Decimal(str(data['volValue']))
                self._notify_price_update(symbol, pair.last_price)
        except Exception as e:
            self.notify_error(f"Error processing ticker update: {str(e)}")