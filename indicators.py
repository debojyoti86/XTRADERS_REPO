from typing import List, Dict, Optional
from decimal import Decimal
import numpy as np
from dataclasses import dataclass
from datetime import datetime
from market_data import CandleData

@dataclass
class IndicatorConfig:
    enabled: bool
    type: str  # 'MA', 'RSI', 'MACD', etc.
    parameters: Dict[str, any]  # Indicator-specific parameters
    color: str  # Display color for the indicator

class TechnicalIndicators:
    def __init__(self):
        self.indicators: Dict[str, IndicatorConfig] = {}
    
    def add_indicator(self, name: str, config: IndicatorConfig) -> None:
        """Add a new indicator configuration"""
        self.indicators[name] = config
    
    def remove_indicator(self, name: str) -> None:
        """Remove an indicator configuration"""
        if name in self.indicators:
            del self.indicators[name]
    
    def calculate_ma(self, candles: List[CandleData], period: int) -> List[float]:
        """Calculate Moving Average"""
        if not candles or period <= 0:
            return []
            
        prices = [float(c.close_price) for c in candles]
        if len(prices) < period:
            return []
            
        ma = []
        for i in range(len(prices)):
            if i < period - 1:
                ma.append(None)
            else:
                window = prices[i-period+1:i+1]
                ma.append(sum(window) / period)
        return ma
    
    def calculate_rsi(self, candles: List[CandleData], period: int = 14) -> List[float]:
        """Calculate Relative Strength Index"""
        if not candles or period <= 0 or len(candles) < period + 1:
            return []
            
        prices = [float(c.close_price) for c in candles]
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        rsi = [None] * period
        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - (100 / (1 + rs)))
        
        for i in range(period + 1, len(prices)):
            avg_gain = (avg_gain * (period - 1) + gains[i-1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i-1]) / period
            
            if avg_loss == 0:
                rsi.append(100)
            else:
                rs = avg_gain / avg_loss
                rsi.append(100 - (100 / (1 + rs)))
        
        return rsi
    
    def calculate_macd(self, candles: List[CandleData], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Dict[str, List[float]]:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        if not candles:
            return {'macd': [], 'signal': [], 'histogram': []}
            
        prices = [float(c.close_price) for c in candles]
        
        # Calculate EMAs
        ema_fast = self._calculate_ema(prices, fast_period)
        ema_slow = self._calculate_ema(prices, slow_period)
        
        # Calculate MACD line
        macd_line = []
        for i in range(len(prices)):
            if i < slow_period - 1:
                macd_line.append(None)
            else:
                macd_line.append(ema_fast[i] - ema_slow[i])
        
        # Calculate signal line
        signal_line = self._calculate_ema([x for x in macd_line if x is not None], signal_period)
        signal_line = [None] * (len(macd_line) - len(signal_line)) + signal_line
        
        # Calculate histogram
        histogram = []
        for i in range(len(macd_line)):
            if macd_line[i] is None or signal_line[i] is None:
                histogram.append(None)
            else:
                histogram.append(macd_line[i] - signal_line[i])
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    def _calculate_ema(self, prices: List[float], period: int) -> List[float]:
        """Calculate Exponential Moving Average"""
        if not prices or period <= 0 or len(prices) < period:
            return []
            
        multiplier = 2 / (period + 1)
        ema = [sum(prices[:period]) / period]
        
        for price in prices[period:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
        
        return [None] * (period - 1) + ema
    
    def calculate_bollinger_bands(self, candles: List[CandleData], period: int = 20, num_std: float = 2.0) -> Dict[str, List[float]]:
        """Calculate Bollinger Bands"""
        if not candles or period <= 0 or len(candles) < period:
            return {'upper': [], 'middle': [], 'lower': []}
            
        prices = [float(c.close_price) for c in candles]
        middle_band = self.calculate_ma(candles, period)
        
        upper_band = []
        lower_band = []
        
        for i in range(len(prices)):
            if i < period - 1:
                upper_band.append(None)
                lower_band.append(None)
            else:
                window = prices[i-period+1:i+1]
                std = np.std(window)
                upper_band.append(middle_band[i] + num_std * std)
                lower_band.append(middle_band[i] - num_std * std)
        
        return {
            'upper': upper_band,
            'middle': middle_band,
            'lower': lower_band
        }