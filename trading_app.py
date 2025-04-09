import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
import sys
import io

import time
from decimal import Decimal
from typing import Dict, Optional
from datetime import datetime
from wallet import WalletModule
from exchange import SushiSwapExchangeService
from trading_engine import TradingEngine, Order, Position
from market_data import MarketDataService

class TradingApplication:
    def __init__(self):
        # Initialize core components
        self.wallet = WalletModule()
        self.exchange = SushiSwapExchangeService()
        self.trading_engine = TradingEngine(self.wallet, self.exchange)
        self.market_data_service = MarketDataService()
        self.market_data: Dict[str, Decimal] = {}
        
        # Component state tracking
        self.component_states = {
            'wallet': {'initialized': False, 'error': None},
            'exchange': {'initialized': False, 'error': None},
            'trading_engine': {'initialized': False, 'error': None},
            'market_data': {'initialized': False, 'error': None}
        }
        
        # Event handlers and callbacks
        self._setup_event_handlers()
        
    def _setup_event_handlers(self):
        """Set up event handlers and callbacks for component integration"""
        try:
            # Market data price updates
            # Add price update handlers for all supported exchanges
            for exchange in ['binance', 'kucoin']:
                self.market_data_service.add_price_update_handler(exchange, self._handle_price_update)
            
            # Exchange order updates
            self.exchange.on_order_update(self._handle_order_update)
            
            # Trading engine position updates
            self.trading_engine.on_position_update(self._handle_position_update)
            
            # Wallet balance updates
            self.wallet.on_balance_update(self._handle_balance_update)
        except Exception as e:
            print(f"Error setting up event handlers: {str(e)}")
            raise
        
    def initialize(self, max_retries: int = 3) -> bool:
        """Initialize the trading application with enhanced error handling and state tracking"""
        # Initialize state tracking
        self.initialization_state = {
            'wallet': False,
            'exchange': False,
            'market_data': False,
            'trading_engine': False,
            'subscriptions': False
        }
        
        self.initialization_attempts = {
            'wallet': 0,
            'exchange': 0,
            'market_data': 0,
            'trading_engine': 0
        }

        # Initialize wallet first
        try:
            if not isinstance(self.wallet, WalletModule):
                raise TypeError("Invalid wallet component type")
            self.wallet.transaction_history.load_transactions()
            self.initialization_state['wallet'] = True
            print("✓ Wallet initialized successfully")
        except Exception as e:
            print(f"❌ Wallet initialization failed: {str(e)}")
            return False

        # Initialize components with enhanced retry logic and state management
        components_to_initialize = [
            ('exchange', self.exchange.connect, "Exchange"),
            ('market_data', self.market_data_service.connect, "Market data service"),
            ('trading_engine', self.trading_engine.initialize, "Trading engine")
        ]

        for attempt in range(max_retries):
            try:
                for component_key, init_func, component_name in components_to_initialize:
                    if not self.initialization_state[component_key]:
                        self.initialization_attempts[component_key] += 1
                        
                        # Add delay between retries
                        if self.initialization_attempts[component_key] > 1:
                            delay = min(2 ** (self.initialization_attempts[component_key] - 1), 10)
                            print(f"Retrying {component_name} initialization in {delay} seconds...")
                            time.sleep(delay)
                        
                        # Attempt initialization with timeout
                        if not init_func(max_retries=3):
                            raise Exception(f"{component_name} initialization timeout")
                        
                        self.initialization_state[component_key] = True
                        print(f"✓ {component_name} initialized successfully")
                        
                        # Special handling for market data service
                        if component_key == 'market_data':
                            if not self.market_data_service.initialized:
                                raise Exception("Market data service failed to initialize properly")

                # Initialize trading engine
                if not self.initialization_state['trading_engine']:
                    self.trading_engine.initialize()
                    self.initialization_state['trading_engine'] = True
                    print("✓ Trading engine initialized successfully")

                print("✓ Trading application initialized successfully")
                return True

            except Exception as e:
                print(f"❌ Initialization attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    delay = 2 * (attempt + 1)  # Progressive delay
                    print(f"Retrying initialization in {delay} seconds...")
                    time.sleep(delay)
                else:
                    print("❌ Max retries reached, initialization failed")
                    return False

        return False

    def _cleanup_connections(self):
        """Clean up connections in reverse order of initialization"""
        cleanup_errors = []

        try:
            self.market_data_service.disconnect()
        except Exception as e:
            cleanup_errors.append(f"Market data cleanup error: {str(e)}")

        try:
            self.exchange.disconnect()
        except Exception as e:
            cleanup_errors.append(f"Exchange cleanup error: {str(e)}")

        if cleanup_errors:
            print("Cleanup warnings:\n" + "\n".join(cleanup_errors))
    
    def place_market_order(self, symbol: str, side: str, quantity: Decimal) -> Optional[Order]:
        """Place a market order"""
        return self.trading_engine.place_order(
            symbol=symbol,
            side=side,
            order_type='market',
            quantity=quantity
        )
    
    def place_limit_order(self, symbol: str, side: str, quantity: Decimal, price: Decimal) -> Optional[Order]:
        """Place a limit order"""
        return self.trading_engine.place_order(
            symbol=symbol,
            side=side,
            order_type='limit',
            quantity=quantity,
            price=price
        )

    def place_conditional_order(self, symbol: str, side: str, quantity: Decimal, price: Decimal, order_type: str, trigger_price: Decimal) -> Optional[Order]:
        """Place a conditional order (stop_loss or take_profit)"""
        if order_type not in ['stop_loss', 'take_profit']:
            raise ValueError(f"Invalid conditional order type: {order_type}")
        
        return self.trading_engine.place_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price
        )
    
    def get_wallet_balances(self) -> Dict[str, Decimal]:
        """Get current wallet balances"""
        return {
            'trading': self.wallet.get_trading_balance(),
            'profit': self.wallet.get_profit_balance()
        }
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol"""
        return self.trading_engine.get_position(symbol)
    
    def get_order_history(self, symbol: Optional[str] = None):
        """Get order history"""
        return self.trading_engine.get_order_history(symbol)
    
    def transfer_between_wallets(self, from_wallet: str, to_wallet: str, amount: Decimal) -> bool:
        """Transfer funds between trading and profit wallets"""
        return self.wallet.transfer(from_wallet, to_wallet, amount)
    
    def update_market_data(self, symbol: str, price: Decimal):
        """Update market data and positions"""
        self.market_data[symbol] = price
        self.trading_engine.update_positions(self.market_data)
        
    def _handle_price_update(self, symbol: str, price: Decimal) -> None:
        """Handle market data price updates"""
        try:
            self.market_data[symbol] = price
            self.trading_engine.update_positions({symbol: price})
        except Exception as e:
            print(f"Error handling price update: {str(e)}")
    
    def _handle_order_update(self, order: Order) -> None:
        """Handle order status updates from exchange"""
        try:
            if order.status == 'filled':
                self.trading_engine._update_position(order)
                self.wallet.update_balance(order)
        except Exception as e:
            print(f"Error handling order update: {str(e)}")

    def _handle_position_update(self, position: Position) -> None:
        """Handle position updates from trading engine"""
        try:
            # Update wallet with realized PnL
            if position.realized_pnl != Decimal('0'):
                self.wallet.update_pnl(position.realized_pnl)
        except Exception as e:
            print(f"Error handling position update: {str(e)}")

    def _handle_balance_update(self, balance: Decimal) -> None:
        """Handle wallet balance updates"""
        try:
            # Update trading engine risk parameters
            self.trading_engine.risk_percentage = min(
                Decimal('0.02'),  # Max 2% risk
                Decimal('5000') / balance if balance > 0 else Decimal('0')
            )
        except Exception as e:
            print(f"Error handling balance update: {str(e)}")

    def get_market_price(self, symbol: str) -> Optional[Decimal]:
        """Get current market price for a symbol"""
        return self.market_data.get(symbol)
    
    def calculate_total_pnl(self) -> Dict[str, Decimal]:
        """Calculate total PnL across all positions"""
        positions = self.trading_engine.get_all_positions()
        total_unrealized = Decimal(sum(pos.unrealized_pnl for pos in positions))
        total_realized = Decimal(sum(pos.realized_pnl for pos in positions))
        
        return {
            'unrealized': total_unrealized,
            'realized': total_realized,
            'total': total_unrealized + total_realized
        }