import json
import time
import hmac
import hashlib
import requests
import websocket
import threading
from decimal import Decimal
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from exchange import ExchangeService, TradingPair, OrderBook as ExchangeOrderBook
from models import OrderBook, OrderBookEntry

@dataclass
class ExchangeInfo:
    name: str
    type: str  # 'CEX' or 'DEX'
    base_url: str
    ws_url: str
    api_key: Optional[str] = None
    api_secret: Optional[str] = None

class ExchangeIntegrator:
    def __init__(self):
        self.exchanges: Dict[str, ExchangeService] = {}
        self.trading_pairs: Dict[str, Dict[str, TradingPair]] = {}
        self.orderbooks: Dict[str, Dict[str, OrderBook]] = {}
        self.is_connected = False
        self.price_update_handlers = []
        self.orderbook_update_handlers = []
        self.exchange_threads: Dict[str, threading.Thread] = {}
        self.exchange_locks: Dict[str, threading.Lock] = {}
        self.connection_status: Dict[str, bool] = {}
        self.ws_base_url = 'wss://api.xtraders.io'  # Use production WebSocket server

    def add_exchange(self, exchange_info: ExchangeInfo) -> bool:
        """Add a new exchange to the integrator"""
        try:
            if exchange_info.type == 'DEX':
                from exchange import SushiSwapExchangeService
                exchange = SushiSwapExchangeService()
                # Configure DEX WebSocket endpoint with proper error handling
                try:
                    exchange.ws_url = exchange_info.ws_url or "wss://api.sushi.com/ws"
                    exchange.base_url = exchange_info.base_url or "https://api.sushi.com"
                    # Initialize WebSocket connection with retry mechanism
                    if not exchange.connect(max_retries=3):
                        raise Exception("Failed to establish WebSocket connection")
                except Exception as ws_error:
                    print(f"WebSocket initialization error: {str(ws_error)}")
                    return False
            else:  # CEX
                from cex_exchanges import BinanceExchangeService, KuCoinExchangeService
                if exchange_info.name.lower() == 'binance':
                    exchange = BinanceExchangeService()
                    if exchange_info.api_key and exchange_info.api_secret:
                        exchange.set_credentials(exchange_info.api_key, exchange_info.api_secret)
                elif exchange_info.name.lower() == 'kucoin':
                    exchange = KuCoinExchangeService()
                    if all([exchange_info.api_key, exchange_info.api_secret, exchange_info.api_passphrase]):
                        exchange.set_credentials(exchange_info.api_key, exchange_info.api_secret, exchange_info.api_passphrase)
                else:
                    raise NotImplementedError(f"Exchange {exchange_info.name} not implemented yet")

            self.exchanges[exchange_info.name] = exchange
            self.trading_pairs[exchange_info.name] = {}
            self.orderbooks[exchange_info.name] = {}
            return True
        except Exception as e:
            print(f"Error adding exchange {exchange_info.name}: {e}")
            return False

    def _connect_exchange(self, exchange_name: str, exchange: ExchangeService, max_retries: int) -> bool:
        """Connect to a single exchange and set up its data streams"""
        try:
            with self.exchange_locks[exchange_name]:
                if not exchange.connect(max_retries):
                    print(f"Failed to connect to {exchange_name}")
                    return False

                # Get and store available trading pairs
                pairs = exchange.get_available_pairs()
                self.trading_pairs[exchange_name] = {pair.symbol: pair for pair in pairs}

                # Subscribe to market data for all pairs
                for pair in pairs:
                    if not exchange.subscribe_to_pair(pair.symbol):
                        print(f"Failed to subscribe to {pair.symbol} on {exchange_name}")
                        return False

                self.connection_status[exchange_name] = True
                return True

        except Exception as e:
            print(f"Error connecting to {exchange_name}: {e}")
            self.connection_status[exchange_name] = False
            return False

    def connect(self, max_retries: int = 3) -> bool:
        """Connect to all configured exchanges concurrently"""
        threads = []

        # Initialize locks and connection status for each exchange
        for exchange_name in self.exchanges.keys():
            self.exchange_locks[exchange_name] = threading.Lock()
            self.connection_status[exchange_name] = False

        # Start connection threads for each exchange
        for exchange_name, exchange in self.exchanges.items():
            thread = threading.Thread(
                target=self._connect_exchange,
                args=(exchange_name, exchange, max_retries)
            )
            threads.append(thread)
            self.exchange_threads[exchange_name] = thread
            thread.start()

        # Wait for all connections to complete
        for thread in threads:
            thread.join()

        # Check if all exchanges connected successfully
        self.is_connected = all(self.connection_status.values())
        return self.is_connected

    def disconnect(self) -> bool:
        """Disconnect from all exchanges"""
        success = True
        for exchange_name, exchange in self.exchanges.items():
            try:
                if not exchange.disconnect():
                    print(f"Failed to disconnect from {exchange_name}")
                    success = False
            except Exception as e:
                print(f"Error disconnecting from {exchange_name}: {e}")
                success = False

        self.is_connected = False
        return success

    def get_aggregated_orderbook(self, symbol: str) -> Optional[OrderBook]:
        """Get aggregated order book across all exchanges"""
        aggregated_book = OrderBook(max_depth=20)  # Initialize with keyword argument
        aggregated_bids = []
        aggregated_asks = []

        for exchange_name, exchange in self.exchanges.items():
            try:
                book = exchange.get_orderbook(symbol)
                if book:
                    aggregated_bids.extend(book.bids)
                    aggregated_asks.extend(book.asks)
            except Exception as e:
                print(f"Error getting orderbook from {exchange_name}: {e}")

        if aggregated_bids or aggregated_asks:
            # Sort and update aggregated order book
            timestamp = int(time.time() * 1000)
            aggregated_book.update(
                bids=sorted(aggregated_bids, key=lambda x: x.price, reverse=True),
                asks=sorted(aggregated_asks, key=lambda x: x.price),
                timestamp=timestamp,
                update_id=None
            )
            return aggregated_book
        return None

    def get_best_price(self, symbol: str, side: str) -> Optional[Decimal]:
        """Get best price across all exchanges for a given symbol and side"""
        best_price = None
        for exchange in self.exchanges.values():
            try:
                book = exchange.get_orderbook(symbol)
                if not book:
                    continue

                if side.lower() == 'buy':
                    ask = book.get_best_ask()
                    if ask and (best_price is None or ask.price < best_price):
                        best_price = ask.price
                else:  # sell
                    bid = book.get_best_bid()
                    if bid and (best_price is None or bid.price > best_price):
                        best_price = bid.price

            except Exception as e:
                print(f"Error getting best price: {e}")

        return best_price

    def add_price_update_handler(self, handler):
        """Add handler for price updates"""
        if handler not in self.price_update_handlers:
            self.price_update_handlers.append(handler)

    def add_orderbook_update_handler(self, handler):
        """Add handler for order book updates"""
        if handler not in self.orderbook_update_handlers:
            self.orderbook_update_handlers.append(handler)

    def get_supported_exchanges(self) -> List[str]:
        """Get list of supported exchanges"""
        return list(self.exchanges.keys())

    def get_trading_pairs(self, exchange_name: Optional[str] = None) -> Dict[str, TradingPair]:
        """Get trading pairs for specific exchange or all exchanges"""
        if exchange_name:
            return self.trading_pairs.get(exchange_name, {})
        
        # Combine trading pairs from all exchanges
        all_pairs = {}
        for exchange_pairs in self.trading_pairs.values():
            all_pairs.update(exchange_pairs)
        return all_pairs
