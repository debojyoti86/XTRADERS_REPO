from decimal import Decimal
from typing import List, Dict, Optional, Any
import time

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
    def __init__(self, *, max_depth: int = 20):
        self.bids: List[OrderBookEntry] = []  # List of OrderBookEntry objects (buy orders)
        self.asks: List[OrderBookEntry] = []  # List of OrderBookEntry objects (sell orders)
        self.timestamp: int = 0
        self.last_update_id: int = 0
        self.max_depth: int = max_depth
        self.symbol: Optional[str] = None
        self.update_id: int = 0  # Track the update sequence number

    def update(self, bids: List[OrderBookEntry], asks: List[OrderBookEntry], timestamp: Optional[int] = None, update_id: Optional[int] = None) -> None:
        """Update the order book with new bids and asks"""
        if update_id and update_id <= self.last_update_id:
            return  # Skip outdated updates

        # Process bids and asks
        processed_bids = [bid for bid in bids if bid.size > 0]
        processed_asks = [ask for ask in asks if ask.size > 0]

        # Sort bids in descending order (highest price first)
        self.bids = sorted(processed_bids, key=lambda x: x.price, reverse=True)[:self.max_depth]
        # Sort asks in ascending order (lowest price first)
        self.asks = sorted(processed_asks, key=lambda x: x.price)[:self.max_depth]
        
        self.timestamp = timestamp or int(time.time() * 1000)
        if update_id:
            self.last_update_id = update_id

    def get_best_bid(self) -> Optional[OrderBookEntry]:
        """Get the highest bid"""
        return self.bids[0] if self.bids else None

    def get_best_ask(self) -> Optional[OrderBookEntry]:
        """Get the lowest ask"""
        return self.asks[0] if self.asks else None

    def get_volume(self, levels: Optional[int] = None) -> Dict[str, Decimal]:
        """Calculate total volume (sum of bid and ask quantities)"""
        if levels is None:
            levels = self.max_depth
            
        bid_volume = Decimal(str(sum(entry.size for entry in self.bids[:levels])))
        ask_volume = Decimal(str(sum(entry.size for entry in self.asks[:levels])))
        return {
            'bid_volume': bid_volume,
            'ask_volume': ask_volume,
            'total_volume': bid_volume + ask_volume
        }

    def get_spread(self) -> Decimal:
        """Calculate the bid-ask spread"""
        if not self.bids or not self.asks:
            return Decimal('0')
            
        best_bid = self.bids[0].price if self.bids else Decimal('0')
        best_ask = self.asks[0].price if self.asks else Decimal('0')
        
        if best_bid == Decimal('0') or best_ask == Decimal('0'):
            return Decimal('0')
            
        return best_ask - best_bid

    def get_mid_price(self) -> Decimal:
        """Get the mid price between best bid and best ask"""
        if not self.bids or not self.asks:
            return Decimal('0')
        
        best_bid = self.bids[0].price if self.bids else Decimal('0')
        best_ask = self.asks[0].price if self.asks else Decimal('0')
        
        if best_bid == Decimal('0') or best_ask == Decimal('0'):
            return Decimal('0')
            
        return (best_bid + best_ask) / Decimal('2')

    def to_dict(self) -> Dict[str, Any]:
        """Convert orderbook to dictionary format"""
        return {
            'bids': [[str(entry.price), str(entry.size)] for entry in self.bids],
            'asks': [[str(entry.price), str(entry.size)] for entry in self.asks],
            'timestamp': self.timestamp,
            'symbol': self.symbol
        }