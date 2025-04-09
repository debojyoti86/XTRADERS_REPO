import decimal
from decimal import Decimal
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import time

@dataclass
class Position:
    symbol: str
    size: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    timestamp: datetime

@dataclass
class Order:
    id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    order_type: str  # 'market' or 'limit'
    quantity: Decimal
    price: Optional[Decimal]
    status: str  # 'pending', 'filled', 'cancelled'
    timestamp: datetime

class TradingEngine:
    def __init__(self, wallet, exchange):
        self.wallet = wallet
        self.exchange = exchange
        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
        self.risk_percentage = Decimal('0.02')  # 2% risk per trade
        self._position_update_callbacks = []
        
    def calculate_position_size(self, entry_price: Decimal, stop_loss: Decimal) -> Decimal:
        """Calculate position size based on risk management rules"""
        risk_amount = self.wallet.get_trading_balance() * self.risk_percentage
        price_risk = abs(entry_price - stop_loss)
        if price_risk == 0:
            return Decimal('0')
        return risk_amount / price_risk
    
    def place_order(self, symbol: str, side: str, order_type: str,
                    quantity: Decimal, price: Optional[Decimal] = None,
                    trigger_price: Optional[Decimal] = None) -> Optional[Order]:
        """Place a new order"""
        try:
            # Validate wallet balance
            required_balance = quantity * (price or Decimal('0'))
            if not self.wallet.has_sufficient_trading_balance(required_balance):
                print(f"Insufficient balance for order: {required_balance}")
                return None
                
            # Create and submit order
            order = Order(
                id=str(len(self.orders) + 1),
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                status='pending',
                timestamp=datetime.now()
            )
            
            # Here we would integrate with the exchange service
            # For now, we'll simulate order execution
            order.status = 'filled'
            self._update_position(order)
            
            self.orders.append(order)
            return order
            
        except Exception as e:
            print(f"Error placing order: {e}")
            return None
    
    def _update_position(self, order: Order) -> None:
        """Update position after order execution"""
        if order.status != 'filled':
            return
            
        position = self.positions.get(order.symbol)
        order_size = order.quantity if order.side == 'buy' else -order.quantity
        order_price = order.price or Decimal('0')
        
        if not position:
            position = Position(
                symbol=order.symbol,
                size=order_size,
                entry_price=order_price,
                current_price=order_price,
                unrealized_pnl=Decimal('0'),
                realized_pnl=Decimal('0'),
                timestamp=datetime.now()
            )
            self.positions[order.symbol] = position
            self._notify_position_update(position)
        else:
            # Update existing position
            new_size = position.size + order_size
            if new_size == 0:
                # Position closed
                realized_pnl = (order_price - position.entry_price) * position.size
                position.realized_pnl += realized_pnl
                self._notify_position_update(position)
                self.positions.pop(order.symbol)
            else:
                # Position modified
                position.size = new_size
                position.entry_price = order_price
                position.current_price = order_price
                position.timestamp = datetime.now()
                self._notify_position_update(position)
    
    def update_positions(self, market_prices: Dict[str, Decimal]) -> None:
        """Update positions with current market prices"""
        for symbol, position in self.positions.items():
            if symbol in market_prices:
                current_price = market_prices[symbol]
                position.current_price = current_price
                position.unrealized_pnl = (current_price - position.entry_price) * position.size
                self._notify_position_update(position)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol"""
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        """Get all current positions"""
        return list(self.positions.values())
    
    def get_order_history(self, symbol: Optional[str] = None) -> List[Order]:
        """Get order history, optionally filtered by symbol"""
        if symbol:
            return [order for order in self.orders if order.symbol == symbol]
        return self.orders
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order"""
        for order in self.orders:
            if order.id == order_id and order.status == 'pending':
                order.status = 'cancelled'
                return True
        return False

    def on_position_update(self, callback) -> None:
        """Register a callback for position updates"""
        if callback not in self._position_update_callbacks:
            self._position_update_callbacks.append(callback)

    def _notify_position_update(self, position: Position) -> None:
        """Notify all registered callbacks about position updates"""
        for callback in self._position_update_callbacks:
            try:
                callback(position)
            except Exception as e:
                print(f"Error in position update callback: {str(e)}")

    def initialize(self, max_retries: int = 3) -> bool:
        """Initialize the trading engine with proper state management and component synchronization"""
        try:
            # Validate core components
            if not self.wallet or not self.exchange:
                raise ValueError("Trading engine requires valid wallet and exchange components")

            # Reset internal state
            self.positions.clear()
            self.orders.clear()
            self._position_update_callbacks.clear()
            self._initialized = False
            self._initialization_state = 'starting'

            for attempt in range(max_retries):
                try:
                    # Initialize components with proper sequence and state tracking
                    components = [
                        ('wallet', self.wallet, 'is_initialized'),
                        ('exchange', self.exchange, 'is_connected'),
                        ('market_data', getattr(self.exchange, 'market_data', None), 'initialized')
                    ]

                    # Verify each component with enhanced timeout and state management
                    timeout = 30  # 30 seconds timeout
                    for name, component, check_attr in components:
                        if not component:
                            continue

                        self._initialization_state = f'initializing_{name}'
                        print(f"Initializing {name}...")

                        start_time = time.time()
                        while not getattr(component, check_attr, False):
                            if time.time() - start_time > timeout:
                                self._initialization_state = 'timeout'
                                raise TimeoutError(f"{name.capitalize()} initialization timeout")
                            time.sleep(1)
                            print(f"Waiting for {name} initialization...")

                        # Verify component health after initialization
                        if hasattr(component, 'verify_health') and not component.verify_health():
                            self._initialization_state = 'health_check_failed'
                            raise RuntimeError(f"{name.capitalize()} health check failed")

                    # Initialize position tracking and verify market data connection
                    self._initialization_state = 'syncing_positions'
                    self._sync_positions()

                    # Verify market data stream is active
                    if hasattr(self.exchange, 'market_data'):
                        self._initialization_state = 'verifying_market_data'
                        if not self.exchange.market_data.verify_stream_active():
                            raise RuntimeError("Market data stream verification failed")

                    self._initialization_state = 'completed'
                    self._initialized = True
                    print("✓ Trading engine initialized successfully")
                    return True

                except (TimeoutError, RuntimeError) as e:
                    if attempt < max_retries - 1:
                        print(f"Initialization attempt {attempt + 1} failed: {str(e)}. Retrying...")
                        time.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        print(f"❌ Initialization failed after {max_retries} attempts: {str(e)}")
                        return False

            return False

        except Exception as e:
            self._initialization_state = 'failed'
            print(f"❌ Critical error during initialization: {str(e)}")
            return False

    def _sync_positions(self):
        """Synchronize positions with exchange"""
        try:
            exchange_positions = self.exchange.get_positions()
            for pos in exchange_positions:
                self.positions[pos.symbol] = pos
            print(f"Synchronized {len(exchange_positions)} positions from exchange")
        except Exception as e:
            print(f"Warning: Failed to sync positions: {str(e)}")