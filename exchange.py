import json
import time
import hmac
import hashlib
import requests
import websocket
import threading
import ssl
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List, Dict, Any, Optional, Callable
import ccxt

class TradingPair:
    """Represents a trading pair (e.g., BTC/USDT)"""
    def __init__(self, symbol):
        self.symbol = symbol
        self.id = None
        self.base_asset = symbol.split('/')[0] if '/' in symbol else ''
        self.quote_asset = symbol.split('/')[1] if '/' in symbol else ''
        self.last_price = Decimal('0')
        self.price_change_24h = Decimal('0')
        self.volume_24h = Decimal('0')
        self.high_24h = Decimal('0')
        self.low_24h = Decimal('0')
    
    def __str__(self):
        return f"TradingPair(symbol='{self.symbol}', last_price={self.last_price})"


class OrderBookEntry:
    """Represents an entry in the order book"""
    def __init__(self, price, size, exchange):
        if price < 0 or size < 0:
            raise ValueError("Price and size must be non-negative")
        if exchange is None:
            raise ValueError("Exchange cannot be null")
            
        self.price = Decimal(str(price))
        self.size = Decimal(str(size))
        self.exchange = exchange
    
    @staticmethod
    def from_string(price, size, exchange):
        return OrderBookEntry(
            Decimal(price),
            Decimal(size),
            exchange
        )
    
    def __str__(self):
        return f"OrderBookEntry(price={self.price}, size={self.size}, exchange='{self.exchange}')"


class OrderBook:
    """Represents an order book with bids and asks"""
    def __init__(self, max_depth=20):
        self.bids = []  # List of OrderBookEntry objects (buy orders)
        self.asks = []  # List of OrderBookEntry objects (sell orders)
        self.timestamp = 0
        self.max_depth = max_depth
        self.last_update_id = 0
        self.symbol = None
    
    def update(self, bids, asks, timestamp=None, update_id=None):
        """Update the order book with new bids and asks"""
        if update_id and update_id <= self.last_update_id:
            return  # Skip outdated updates
            
        # Convert incoming data to OrderBookEntry objects if needed
        processed_bids = []
        processed_asks = []
        
        for bid in bids:
            if isinstance(bid, list):
                price, size = bid[:2]
                entry = OrderBookEntry(price, size, 'exchange')
            else:
                entry = bid
            if entry.size > 0:  # Only add non-zero sizes
                processed_bids.append(entry)
                
        for ask in asks:
            if isinstance(ask, list):
                price, size = ask[:2]
                entry = OrderBookEntry(price, size, 'exchange')
            else:
                entry = ask
            if entry.size > 0:  # Only add non-zero sizes
                processed_asks.append(entry)
        
        # Sort bids in descending order (highest price first)
        processed_bids.sort(key=lambda x: x.price, reverse=True)
        # Sort asks in ascending order (lowest price first)
        processed_asks.sort(key=lambda x: x.price)
        
        # Maintain maximum depth
        self.bids = processed_bids[:self.max_depth]
        self.asks = processed_asks[:self.max_depth]
        
        self.timestamp = timestamp or int(time.time() * 1000)
        if update_id:
            self.last_update_id = update_id
    
    def get_best_bid(self) -> Optional[OrderBookEntry]:
        """Get the highest bid"""
        return self.bids[0] if self.bids else None

    def get_best_ask(self) -> Optional[OrderBookEntry]:
        """Get the lowest ask"""
        return self.asks[0] if self.asks else None

    def get_mid_price(self):
        """Get the mid price between best bid and best ask"""
        if not self.bids or not self.asks:
            return Decimal('0')
        
        best_bid = self.bids[0].price if self.bids else Decimal('0')
        best_ask = self.asks[0].price if self.asks else Decimal('0')
        
        if best_bid == Decimal('0') or best_ask == Decimal('0'):
            return Decimal('0')
            
        return (best_bid + best_ask) / Decimal('2')
    
    def get_spread(self):
        """Get the spread between best bid and best ask"""
        if not self.bids or not self.asks:
            return Decimal('0')
            
        best_bid = self.bids[0].price if self.bids else Decimal('0')
        best_ask = self.asks[0].price if self.asks else Decimal('0')
        
        if best_bid == Decimal('0') or best_ask == Decimal('0'):
            return Decimal('0')
            
        return best_ask - best_bid
    
    def get_volume(self, levels=None):
        """Get the total volume for the specified number of price levels"""
        if levels is None:
            levels = self.max_depth
            
        bid_volume = sum(entry.size for entry in self.bids[:levels])
        ask_volume = sum(entry.size for entry in self.asks[:levels])
        
        return {
            'bid_volume': bid_volume,
            'ask_volume': ask_volume,
            'total_volume': bid_volume + ask_volume
        }
    
    def to_dict(self):
        """Convert orderbook to dictionary format"""
        return {
            'bids': [[str(entry.price), str(entry.size)] for entry in self.bids],
            'asks': [[str(entry.price), str(entry.size)] for entry in self.asks],
            'timestamp': self.timestamp,
            'symbol': self.symbol
        }


class ExchangeService(ABC):
    """Abstract base class for exchange services"""
    def __init__(self):
        self.trading_pairs = {}
        self.order_book_update_listeners = []
        self.ws = None
        self.ws_thread = None
        self.is_connected = False
        self.orderbooks = {}  # Symbol -> OrderBook mapping
        self.ws_subscriptions = set()  # Track active WebSocket subscriptions
        self.ws_url = ""  # WebSocket URL for the exchange
        self.reconnect_delay = 2  # Delay between reconnection attempts
        self.max_reconnect_attempts = 3  # Maximum number of reconnection attempts
        self._ws_lock = threading.Lock()  # Lock for WebSocket operations
        self._reconnect_count = 0  # Track reconnection attempts
        self.last_pong_time = time.time()  # Track last pong time
        self.heartbeat_interval = 30  # Heartbeat check interval in seconds
        self.heartbeat_thread = None
    
    @abstractmethod
    def connect(self, max_retries=3):
        """Connect to the exchange and initialize WebSocket connection"""
        for attempt in range(max_retries):
            try:
                self._init_websocket()
                return True
            except Exception as e:
                self.notify_error(f"Failed to connect: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2)  # Wait before retrying
                else:
                    return False
        return False

    def _init_websocket(self):
        """Initialize WebSocket connection with automatic reconnection"""
        with self._ws_lock:
            if self.ws:
                return
                
            # Start heartbeat monitoring thread
            def monitor_heartbeat():
                while self.is_connected:
                    if time.time() - self.last_pong_time > self.heartbeat_interval:
                        print(f"No heartbeat received for {self.heartbeat_interval} seconds, reconnecting...")
                        self._attempt_reconnect()
                    time.sleep(5)  # Check every 5 seconds
                    
            if self.heartbeat_thread and self.heartbeat_thread.is_alive():
                self.heartbeat_thread.join(timeout=1)
                
            self.heartbeat_thread = threading.Thread(target=monitor_heartbeat)
            self.heartbeat_thread.daemon = True
            self.heartbeat_thread.start()

            def on_message(ws, message):
                try:
                    self.last_pong_time = time.time()  # Update last pong time on any message
                    self._handle_ws_message(message)
                except Exception as e:
                    self.notify_error(f"Error handling message: {str(e)}")
                    
            def on_error(ws, error):
                self.notify_error(f"WebSocket error: {str(error)}")
                if not self.is_connected:
                    self._attempt_reconnect()
                
            def on_close(ws, close_status_code, close_msg):
                if self.is_connected:
                    self.is_connected = False
                    print(f"WebSocket connection closed: {close_msg}")
                    self._attempt_reconnect()
                
            def on_open(ws):
                self.is_connected = True
                self._reconnect_count = 0
                print("WebSocket connection established")
                # Resubscribe to previous subscriptions
                for symbol in self.ws_subscriptions:
                    self.subscribe_to_pair(symbol)
                    
            def on_ping(ws, message):
                ws.send('pong')
                self.last_pong_time = time.time()
                
            def on_pong(ws, message):
                self.last_pong_time = time.time()

            # Initialize WebSocket with all callback handlers and enable trace
            websocket.enableTrace(True)
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open,
                on_ping=on_ping,
                on_pong=on_pong
            )
            
            # Start WebSocket connection in a separate thread with ping interval
            self.ws_thread = threading.Thread(
                target=lambda: self.ws.run_forever(
                    ping_interval=30,
                    ping_timeout=10,
                    ping_payload='ping',
                    sslopt={"cert_reqs": ssl.CERT_NONE}
                )
            )
            self.ws_thread.daemon = True
            self.ws_thread.start()

    def _attempt_reconnect(self):
        """Attempt to reconnect to WebSocket with exponential backoff"""
        if self._reconnect_count >= self.max_reconnect_attempts:
            self.notify_error("Max reconnection attempts reached")
            return

        self._reconnect_count += 1
        backoff = self.reconnect_delay * (2 ** (self._reconnect_count - 1))
        print(f"Attempting to reconnect in {backoff} seconds...")
        time.sleep(backoff)

        try:
            # Close existing connection if any
            if self.ws:
                try:
                    self.ws.close()
                except:
                    pass
                self.ws = None

            # Clear existing subscriptions
            self.ws_subscriptions.clear()
            
            # Reinitialize WebSocket
            self._init_websocket()
            
            # Reset reconnect count on successful connection
            if self.is_connected:
                self._reconnect_count = 0
                print("Successfully reconnected")
                return True
        except Exception as e:
            self.notify_error(f"Reconnection failed: {str(e)}")
            
        return False

    def _handle_ws_message(self, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            # Process message based on type
            if 'type' in data:
                if data['type'] == 'orderbook':
                    self._handle_orderbook_update(data)
                elif data['type'] == 'trade':
                    self._handle_trade_update(data)
        except json.JSONDecodeError:
            self.notify_error("Failed to decode WebSocket message")
        except Exception as e:
            self.notify_error(f"Error processing message: {str(e)}")

        # WebSocket connection is already initialized in _init_websocket
        pass
    
    @abstractmethod
    def disconnect(self):
        """Disconnect from the exchange"""
        try:
            if self.ws:
                self.ws.close()
                self.ws = None
                
            if self.ws_thread and self.ws_thread.is_alive():
                self.ws_thread.join(timeout=1)
                self.ws_thread = None
                
            self.ws_subscriptions.clear()
            self.orderbooks.clear()
            self.is_connected = False
            return True
        except Exception as e:
            self.notify_error(f"Failed to disconnect: {str(e)}")
            return False
    
    @abstractmethod
    def get_available_pairs(self) -> List[TradingPair]:
        """Get available trading pairs"""
        pass
    
    @abstractmethod
    def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent trades for a trading pair"""
        pass

    @abstractmethod
    def subscribe_to_pair(self, symbol):
        """Subscribe to updates for a trading pair"""
        try:
            if not self.is_connected:
                if not self.connect():
                    return False
                    
            if symbol not in self.orderbooks:
                self.orderbooks[symbol] = OrderBook()
                self.orderbooks[symbol].symbol = symbol
                
            if symbol not in self.ws_subscriptions:
                if self._subscribe_orderbook(symbol):
                    self.ws_subscriptions.add(symbol)
                    return True
            return True
        except Exception as e:
            self.notify_error(f"Failed to subscribe to {symbol}: {str(e)}")
            return False
            
    def _subscribe_orderbook(self, symbol):
        """Send orderbook subscription message through WebSocket"""
        raise NotImplementedError("Subclass must implement _subscribe_orderbook")
        
    def _handle_ws_message(self, message):
        """Handle incoming WebSocket messages"""
        raise NotImplementedError("Subclass must implement _handle_ws_message")
    
    @abstractmethod
    def unsubscribe_from_pair(self, symbol):
        """Unsubscribe from updates for a trading pair"""
        pass
    
    @abstractmethod
    def get_orderbook(self, symbol) -> OrderBook:
        """Get the current order book for a symbol"""
        pass
    
    @abstractmethod
    def get_candles(self, symbol, timeframe, limit):
        """Get historical candles for a symbol"""
        pass
    
    def add_order_book_update_listener(self, listener):
        """Add a listener for order book updates"""
        if listener not in self.order_book_update_listeners:
            self.order_book_update_listeners.append(listener)
    
    def remove_order_book_update_listener(self, listener):
        """Remove a listener for order book updates"""
        if listener in self.order_book_update_listeners:
            self.order_book_update_listeners.remove(listener)
    
    def notify_order_book_update(self, symbol, order_book):
        """Notify all listeners of an order book update"""
        for listener in self.order_book_update_listeners:
            try:
                listener(symbol, order_book)
            except Exception as e:
                print(f"Error notifying listener: {e}")
    
    def notify_error(self, error_message):
        """Notify all listeners of an error"""
        print(f"Exchange error: {error_message}")


class SushiSwapExchangeService(ExchangeService):
    """SushiSwap exchange service implementation"""
    def __init__(self, ws_url: str = "wss://stream.sushi.com/ws"):
        super().__init__()
        self.base_url = "https://api.sushi.com/v1"
        self.ws_url = "wss://stream.sushi.com/ws" # Correct WebSocket URL
        self.is_initialized = False
        self.api_key = None  # Add API key if required
        self.api_secret = None  # Add API secret if required
        self.current_subscriptions = set()
        self.ws = None
        self.ws_thread = None
        self.is_connected = False
        self.ws_subscriptions = set()
        self.orderbooks = {}
        self.order_book_update_listeners = []
        self.order_update_handlers = []  # List to store order update handlers

    def on_order_update(self, handler: Callable):
        """Register a handler for order updates"""
        if handler not in self.order_update_handlers:
            self.order_update_handlers.append(handler)

    def _subscribe_orderbook(self, symbol):
        """Subscribe to orderbook updates for a symbol"""
        if not self.ws or not self.is_connected:
            return False
            
        try:
            subscribe_message = {
                "method": "SUBSCRIBE",
                "params": [f"{symbol.lower()}@depth20@100ms"], # Correct subscription parameters
                "id": int(time.time() * 1000)
            }
            self.ws.send(json.dumps(subscribe_message))
            return True
        except Exception as e:
            self.notify_error(f"Failed to subscribe to orderbook: {str(e)}")
            return False
            
    def _handle_ws_message(self, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            
            if 'stream' in data and 'data' in data:
                stream = data['stream']
                if '@depth' in stream:
                    self._handle_orderbook_update(data['data'])
                    
        except json.JSONDecodeError as e:
            self.notify_error(f"Failed to parse message: {str(e)}")
        except Exception as e:
            self.notify_error(f"Error handling message: {str(e)}")
            
    def _handle_orderbook_update(self, data):
        """Process orderbook update data"""
        try:
            symbol = data.get('s')  # Symbol
            if not symbol or symbol not in self.orderbooks:
                return
                
            orderbook = self.orderbooks[symbol]
            
            # Process bids and asks
            bids = [OrderBookEntry(Decimal(price), Decimal(qty), 'sushiswap') 
                   for price, qty in data.get('b', [])]
            asks = [OrderBookEntry(Decimal(price), Decimal(qty), 'sushiswap') 
                   for price, qty in data.get('a', [])]
                   
            # Update orderbook
            orderbook.update(
                bids=bids,
                asks=asks,
                timestamp=data.get('E'),  # Event time
                update_id=data.get('u')   # Update ID
            )
            
            # Notify listeners
            self.notify_order_book_update(symbol, orderbook)
            
        except Exception as e:
            self.notify_error(f"Error processing orderbook update: {str(e)}")
            
    def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent trades for a symbol from SushiSwap"""
        try:
            # Construct the API endpoint for recent trades
            endpoint = f"{self.base_url}/trades/{symbol}"
            params = {"limit": limit}
            
            # Make the API request
            response = requests.get(endpoint, params=params)
            response.raise_for_status()
            
            # Parse and format the trades data
            trades = response.json()
            formatted_trades = [{
                'id': trade.get('id'),
                'price': Decimal(str(trade.get('price', '0'))),
                'amount': Decimal(str(trade.get('amount', '0'))),
                'timestamp': trade.get('timestamp'),
                'side': trade.get('side', 'unknown'),
                'symbol': symbol
            } for trade in trades]
            
            return formatted_trades
            
        except requests.exceptions.RequestException as e:
            self.notify_error(f"Failed to fetch recent trades: {str(e)}")
            return []
        except Exception as e:
            self.notify_error(f"Error processing recent trades: {str(e)}")
            return []
            
    def get_status(self):
        """Get the current status of the SushiSwap service"""
        if not self.is_initialized:
            try:
                self.connect()
                return "connected"
            except Exception as e:
                return f"initialization_failed: {str(e)}"
        return "ready" if self.is_connected else "disconnected"

    def connect(self, max_retries: int = 3) -> bool:
        """Connect to SushiSwap with retry mechanism"""
        for attempt in range(max_retries):
            try:
                # Initialize connection to SushiSwap
                self._init_websocket()
                self.is_connected = True
                self.is_initialized = True
                print(f"Successfully connected to SushiSwap on attempt {attempt + 1}")
                return True
            except Exception as e:
                self.notify_error(f"Failed to connect to SushiSwap on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    print("Retrying connection...")
                    time.sleep(2)
                else:
                    print("Max retries reached, connection failed")
                    return False
        return False

    def disconnect(self):
        """Disconnect from SushiSwap"""
        try:
            if self.ws:
                self.ws.close()
                self.ws = None
            
            if self.ws_thread and self.ws_thread.is_alive():
                self.ws_thread.join(timeout=1)
                self.ws_thread = None
            
            self.current_subscriptions.clear()
            self.is_connected = False
            return True
        except Exception as e:
            self.notify_error(f"Failed to disconnect from SushiSwap: {e}")
            return False

    def get_available_pairs(self) -> List[TradingPair]:
        """Get available trading pairs from SushiSwap"""
        try:
            # Simulated trading pairs for testing
            pairs = [
                TradingPair("ETH/USDT"),
                TradingPair("BTC/USDT"),
                TradingPair("LINK/USDT")
            ]
            
            # Set some sample data for each pair
            for pair in pairs:
                pair.last_price = Decimal('1950.0') if 'ETH' in pair.symbol else \
                                Decimal('30000.0') if 'BTC' in pair.symbol else \
                                Decimal('15.0')
                pair.volume_24h = Decimal('1000000.0')
                pair.price_change_24h = Decimal('2.5')
            return pairs
        except Exception as e:
            self.notify_error(f"Failed to get trading pairs: {e}")
            return []

    def subscribe_to_pair(self, symbol):
        """Subscribe to updates for a trading pair"""
        try:
            if not self.is_connected:
                self.connect()
            
            if symbol in self.current_subscriptions:
                return True
            
            self.current_subscriptions.add(symbol)
            return True
        except Exception as e:
            self.notify_error(f"Failed to subscribe to {symbol}: {e}")
            return False

    def unsubscribe_from_pair(self, symbol):
        """Unsubscribe from updates for a trading pair"""
        try:
            if symbol in self.current_subscriptions:
                self.current_subscriptions.remove(symbol)
                
                if not self.current_subscriptions and self.ws:
                    self.disconnect()
                    
                return True
            return False
        except Exception as e:
            self.notify_error(f"Failed to unsubscribe from {symbol}: {e}")
            return False

    def get_orderbook(self, symbol) -> OrderBook:
        """Get the current order book for a symbol"""
        try:
            # Simulated order book data for testing
            order_book = OrderBook()
            
            base_price = 1950.0 if 'ETH' in symbol else \
                        30000.0 if 'BTC' in symbol else \
                        15.0
            
            # Create some sample bids and asks
            bids = [
                OrderBookEntry(base_price - (i * 0.1), 0.5 + (i * 0.2), 'SushiSwap')
                for i in range(5)
            ]
            
            asks = [
                OrderBookEntry(base_price + (i * 0.1), 0.3 + (i * 0.1), 'SushiSwap')
                for i in range(5)
            ]
            
            order_book.update(bids, asks, int(time.time() * 1000))
            return order_book
        except Exception as e:
            self.notify_error(f"Failed to get order book for {symbol}: {e}")
            return OrderBook()

    def get_candles(self, symbol, timeframe, limit):
        """Get historical candles for a symbol"""
        try:
            # Simulated candle data for testing
            current_time = int(time.time() * 1000)
            interval = 60000  # 1 minute in milliseconds
            
            base_price = 1950.0 if 'ETH' in symbol else \
                        30000.0 if 'BTC' in symbol else \
                        15.0
            
            candles = []
            for i in range(limit):
                timestamp = current_time - (i * interval)
                candle = {
                    'timestamp': timestamp,
                    'open': float(base_price + (i * 0.1)),
                    'high': float(base_price + (i * 0.15)),
                    'low': float(base_price + (i * 0.05)),
                    'close': float(base_price + (i * 0.12)),
                    'volume': float(1000 + (i * 10))
                }
                candles.append(candle)
            
            return candles[::-1]  # Reverse to get chronological order
        except Exception as e:
            self.notify_error(f"Failed to get candles for {symbol}: {e}")
            return []