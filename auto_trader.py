from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import time
from threading import Thread, Lock
from market_data import MarketDataService, CandleData
from trading_app import TradingApplication
from indicators import TechnicalIndicators

class AutoTrader:
    def __init__(self, app: TradingApplication):
        self.app = app
        self.market_data = MarketDataService()
        self.indicators = TechnicalIndicators()
        self.trading_lock = Lock()
        self.is_running = False
        self.active_trades: Dict[str, Dict] = {}
        self.profit_target = Decimal('2.0')  # 2x profit target
        self.cycle_duration = 5 * 60  # 5 minutes in seconds for faster adaptation
        self.min_price_difference = Decimal('0.002')  # Increased minimum price difference
        self.max_concurrent_trades = 3  # Reduced for better risk management
        self.stop_loss = Decimal('0.05')  # 5% stop loss
        self.trend_periods = {'short': 20, 'medium': 50, 'long': 200}  # MA periods for trend analysis
        
    def start(self):
        """Start the automated trading system"""
        if self.is_running:
            return False
            
        self.is_running = True
        Thread(target=self._trading_cycle_loop, daemon=True).start()
        Thread(target=self._monitor_positions, daemon=True).start()
        return True
    
    def stop(self):
        """Stop the automated trading system"""
        self.is_running = False
        self._close_all_positions()
    
    def _trading_cycle_loop(self):
        """Main trading cycle loop that runs every 15 minutes"""
        while self.is_running:
            cycle_start = datetime.now()
            
            try:
                with self.trading_lock:
                    self._execute_trading_cycle()
            except Exception as e:
                print(f"Error in trading cycle: {e}")
            
            # Wait for next cycle
            elapsed = (datetime.now() - cycle_start).total_seconds()
            if elapsed < self.cycle_duration:
                time.sleep(self.cycle_duration - elapsed)
    
    def _execute_trading_cycle(self):
        """Execute one complete trading cycle with enhanced strategy for 2x profit"""
        pairs = self.app.exchange.get_available_pairs()
        
        for pair in pairs:
            if len(self.active_trades) >= self.max_concurrent_trades:
                break
                
            candles = self.market_data.get_candle_history(pair.symbol)
            if not candles or len(candles) < 200:  # Ensure enough historical data
                continue
                
            # Calculate comprehensive technical indicators
            rsi = self.indicators.calculate_rsi(candles)
            macd = self.indicators.calculate_macd(candles)
            bb = self.indicators.calculate_bollinger_bands(candles)
            
            # Calculate multiple timeframe moving averages
            mas = {}
            for period_name, period in self.trend_periods.items():
                mas[period_name] = self.indicators.calculate_ma(candles, period)
            
            # Analyze market conditions
            trend = self._analyze_trend(mas)
            volatility = self._calculate_volatility(candles)
            momentum = self._analyze_momentum(rsi[-1], macd)
            
            # Execute trade if conditions are favorable
            if self._check_trading_conditions(trend, volatility, momentum, bb):
                position_size = self._calculate_position_size(volatility)
                self._execute_smart_trade(pair.symbol, position_size, trend)
    
    def _find_arbitrage_opportunities(self, pairs) -> List[Dict]:
        """Find arbitrage opportunities across different trading pairs"""
        opportunities = []
        
        for pair1 in pairs:
            for pair2 in pairs:
                if pair1 == pair2:
                    continue
                    
                price1 = self.market_data.get_last_price(pair1.symbol)
                price2 = self.market_data.get_last_price(pair2.symbol)
                
                if not (price1 and price2):
                    continue
                
                # Calculate price difference
                price_diff = abs(price1 - price2) / price1
                if price_diff > self.min_price_difference:
                    opportunities.append({
                        'pair1': pair1.symbol,
                        'pair2': pair2.symbol,
                        'price1': price1,
                        'price2': price2,
                        'difference': price_diff
                    })
        
        return sorted(opportunities, key=lambda x: x['difference'], reverse=True)
    
    def _analyze_trend(self, mas: Dict[str, List[float]]) -> str:
        """Analyze market trend using multiple timeframe moving averages"""
        if not all(mas.values()):
            return 'neutral'
            
        short_ma = mas['short'][-1]
        medium_ma = mas['medium'][-1]
        long_ma = mas['long'][-1]
        
        if short_ma > medium_ma > long_ma:
            return 'strong_uptrend'
        elif short_ma > medium_ma:
            return 'uptrend'
        elif short_ma < medium_ma < long_ma:
            return 'strong_downtrend'
        elif short_ma < medium_ma:
            return 'downtrend'
        return 'neutral'
    
    def _calculate_volatility(self, candles: List[CandleData]) -> Decimal:
        """Calculate market volatility using ATR-based method"""
        if len(candles) < 14:
            return Decimal('0')
            
        ranges = []
        for i in range(1, 14):
            high = Decimal(str(candles[-i].high_price))
            low = Decimal(str(candles[-i].low_price))
            ranges.append(high - low)
        
        return sum(ranges) / Decimal('14')
    
    def _analyze_momentum(self, rsi: float, macd: Dict) -> str:
        """Analyze market momentum using RSI and MACD"""
        if rsi is None or not macd['macd'] or not macd['signal']:
            return 'neutral'
            
        last_macd = macd['macd'][-1]
        last_signal = macd['signal'][-1]
        
        if rsi < 30 and last_macd > last_signal:
            return 'strong_buy'
        elif rsi < 40 and last_macd > last_signal:
            return 'buy'
        elif rsi > 70 and last_macd < last_signal:
            return 'strong_sell'
        elif rsi > 60 and last_macd < last_signal:
            return 'sell'
        return 'neutral'
    
    def _check_trading_conditions(self, trend: str, volatility: Decimal, momentum: str, bb: Dict[str, List[float]]) -> bool:
        """Check if market conditions are favorable for trading"""
        if not bb['upper'] or not bb['lower']:
            return False
            
        price = Decimal(str(bb['middle'][-1]))
        upper = Decimal(str(bb['upper'][-1]))
        lower = Decimal(str(bb['lower'][-1]))
        
        # Check for strong trend with momentum
        trend_momentum_aligned = (
            (trend in ['strong_uptrend', 'uptrend'] and momentum in ['strong_buy', 'buy']) or
            (trend in ['strong_downtrend', 'downtrend'] and momentum in ['strong_sell', 'sell'])
        )
        
        # Check if volatility is within acceptable range
        volatility_acceptable = volatility > Decimal('0.001') and volatility < Decimal('0.05')
        
        # Check if price is near Bollinger Band extremes
        price_at_extreme = price <= lower * Decimal('1.02') or price >= upper * Decimal('0.98')
        
        return trend_momentum_aligned and volatility_acceptable and price_at_extreme
    
    def _calculate_position_size(self, volatility: Decimal) -> Decimal:
        """Calculate optimal position size based on volatility and account balance"""
        balance = self.app.wallet.get_trading_balance()
        
        # Base position size on account balance
        base_size = balance * Decimal('0.2')  # Use 20% of balance as base size
        
        # Adjust size based on volatility
        if volatility > Decimal('0.03'):  # High volatility
            return base_size * Decimal('0.5')  # Reduce position size
        elif volatility < Decimal('0.01'):  # Low volatility
            return base_size * Decimal('1.5')  # Increase position size
        return base_size
    
    def _execute_smart_trade(self, symbol: str, position_size: Decimal, trend: str):
        """Execute a trade with smart entry and risk management"""
        if symbol in self.active_trades:
            return
            
        try:
            # Determine trade direction based on trend
            side = 'buy' if trend in ['strong_uptrend', 'uptrend'] else 'sell'
            
            # Place market order
            order = self.app.place_market_order(symbol, side, position_size)
            if order:
                stop_price = order.price * (Decimal('0.95') if side == 'buy' else Decimal('1.05'))
                
                self.active_trades[symbol] = {
                    'type': 'smart',
                    'side': side,
                    'entry_price': order.price,
                    'quantity': order.quantity,
                    'entry_time': datetime.now(),
                    'order_id': order.id,
                    'stop_price': stop_price,
                    'profit_target': order.price * (Decimal('2.0') if side == 'buy' else Decimal('0.5'))
                }
        except Exception as e:
            print(f"Error executing HFT trade: {e}")
    
    def _execute_arbitrage_trade(self, opportunity: Dict):
        """Execute an arbitrage trade between two pairs"""
        pair1, pair2 = opportunity['pair1'], opportunity['pair2']
        if pair1 in self.active_trades or pair2 in self.active_trades:
            return
            
        try:
            # Calculate position sizes
            balance = self.app.wallet.get_trading_balance()
            position_size = balance * Decimal('0.1')  # Use 10% of available balance
            
            # Execute trades
            buy_order = self.app.place_market_order(pair1, 'buy', position_size)
            sell_order = self.app.place_market_order(pair2, 'sell', position_size)
            
            if buy_order and sell_order:
                self.active_trades[pair1] = {
                    'type': 'arbitrage',
                    'pair2': pair2,
                    'entry_price': buy_order.price,
                    'quantity': buy_order.quantity,
                    'entry_time': datetime.now(),
                    'order_id': buy_order.id
                }
        except Exception as e:
            print(f"Error executing arbitrage trade: {e}")
    
    def _monitor_positions(self):
        """Monitor active positions with enhanced risk management"""
        while self.is_running:
            try:
                with self.trading_lock:
                    for symbol, trade in list(self.active_trades.items()):
                        current_price = self.market_data.get_last_price(symbol)
                        if not current_price:
                            continue
                            
                        entry_price = trade['entry_price']
                        side = trade['side']
                        
                        # Calculate profit/loss based on trade direction
                        if side == 'buy':
                            profit_ratio = (current_price - entry_price) / entry_price
                        else:
                            profit_ratio = (entry_price - current_price) / entry_price
                        
                        # Check stop loss and profit target
                        stop_hit = (
                            (side == 'buy' and current_price <= trade['stop_price']) or
                            (side == 'sell' and current_price >= trade['stop_price'])
                        )
                        
                        profit_target_hit = (
                            (side == 'buy' and current_price >= trade['profit_target']) or
                            (side == 'sell' and current_price <= trade['profit_target'])
                        )
                        
                        # Close position if conditions met
                        if stop_hit or profit_target_hit:
                            self._close_position(symbol, trade)
                            
            except Exception as e:
                print(f"Error monitoring positions: {e}")
            
            time.sleep(1)  # Check positions every second
    
    def _close_position(self, symbol: str, trade: Dict):
        """Close a single trading position"""
        try:
            # Close the main position
            self.app.place_market_order(symbol, 'sell', trade['quantity'])
            
            # If it's an arbitrage trade, close the paired position
            if trade['type'] == 'arbitrage' and trade['pair2'] in self.active_trades:
                pair2_trade = self.active_trades[trade['pair2']]
                self.app.place_market_order(trade['pair2'], 'buy', pair2_trade['quantity'])
                del self.active_trades[trade['pair2']]
            
            del self.active_trades[symbol]
        except Exception as e:
            print(f"Error closing position: {e}")
    
    def _close_all_positions(self):
        """Close all active trading positions"""
        with self.trading_lock:
            for symbol, trade in list(self.active_trades.items()):
                self._close_position(symbol, trade)
    
    def get_active_trades(self) -> Dict[str, Dict]:
        """Get current active trades"""
        return self.active_trades.copy()
    
    def get_trading_status(self) -> Dict:
        """Get current trading status"""
        return {
            'is_running': self.is_running,
            'active_trades': len(self.active_trades),
            'profit_target': float(self.profit_target),
            'cycle_duration': self.cycle_duration
        }