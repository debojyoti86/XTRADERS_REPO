import streamlit as st
import decimal
from decimal import Decimal
from datetime import datetime
from typing import Dict, Optional
import plotly.graph_objects as go
from trading_app import TradingApplication
from market_data import MarketDataService
from indicators import TechnicalIndicators, IndicatorConfig
from wallet_panel import WalletPanel
from auto_trader import AutoTrader
import os

# Load custom CSS files
for css_file in ['style.css', 'indicator_panel.css', 'exchange_login.css', 'trading_panel.css']:
    with open(os.path.join(os.path.dirname(__file__), css_file)) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

class TradingUI:
    def __init__(self):
        self.app = TradingApplication()
        self.market_data = MarketDataService()
        self.indicators = TechnicalIndicators()
        self.wallet_panel = WalletPanel(self.app.wallet)
        self.auto_trader = AutoTrader(self.app)
        self.initialize_session_state()
        self._ensure_market_data_connection()
        
    def initialize_session_state(self):
        """Initialize session state variables"""
        if 'initialized' not in st.session_state:
            st.session_state.initialized = False
            st.session_state.selected_symbol = None
            st.session_state.candle_data = {}
            st.session_state.market_data_connected = False
            st.session_state.selected_timeframe = '1m'
            st.session_state.active_indicators = {}
            st.session_state.auto_trading_enabled = False
            st.session_state.exchange_credentials = {
                'binance': {
                    'api_key': '',
                    'api_secret': '',
                    'connected': False
                },
                'kucoin': {
                    'api_key': '',
                    'api_secret': '',
                    'api_passphrase': '',
                    'connected': False
                },
                'bitbns': {
                    'api_key': '',
                    'api_secret': '',
                    'connected': False
                }
            }
            # Initialize default indicators
            st.session_state.active_indicators['MA_20'] = IndicatorConfig(
                enabled=True,
                type='MA',
                parameters={'period': 20},
                color='#2962FF'
            )
            st.session_state.active_indicators['RSI'] = IndicatorConfig(
                enabled=True,
                type='RSI',
                parameters={'period': 14},
                color='#FF6B6B'
            )
    
    def _ensure_market_data_connection(self):
        """Ensure market data service is connected"""
        if not st.session_state.market_data_connected:
            if self.market_data.connect():
                st.session_state.market_data_connected = True
                # Subscribe to default symbol
                self.market_data.subscribe_to_candles('BTC/USDT')
                st.session_state.selected_symbol = 'BTC/USDT'
            else:
                st.error('Failed to connect to market data service')
                return False
        return True
            
    def render_exchange_login(self):
        """Render the exchange login panel with dropdown selection"""
        st.markdown('<div class="exchange-login-panel">', unsafe_allow_html=True)
        st.subheader('Exchange Login')
        
        # Initialize selected exchange in session state if not present
        if 'selected_exchange' not in st.session_state:
            st.session_state.selected_exchange = None
        
        # Exchange selection dropdown
        available_exchanges = ['Binance', 'KuCoin', 'BitBNS']
        selected_exchange = st.selectbox(
            'Select Exchange',
            options=available_exchanges,
            index=None,
            placeholder="Select exchange...",
            key='exchange_selector'
        )
        
        # Update selected exchange in session state
        if selected_exchange != st.session_state.selected_exchange:
            st.session_state.selected_exchange = selected_exchange
        
        # Display login fields for the selected exchange
        if st.session_state.selected_exchange:
            exchange_key = st.session_state.selected_exchange.lower()
            
            # Binance Login
            if exchange_key == 'binance':
                binance_creds = st.session_state.exchange_credentials['binance']
                st.markdown(f'### {st.session_state.selected_exchange} Login')
                col1, col2 = st.columns(2)
                
                with col1:
                    new_api_key = st.text_input('API Key', value=binance_creds['api_key'], type='password', key='binance_api_key')
                    if new_api_key != binance_creds['api_key']:
                        binance_creds['api_key'] = new_api_key
                        binance_creds['connected'] = False
                        
                with col2:
                    new_api_secret = st.text_input('API Secret', value=binance_creds['api_secret'], type='password', key='binance_api_secret')
                    if new_api_secret != binance_creds['api_secret']:
                        binance_creds['api_secret'] = new_api_secret
                        binance_creds['connected'] = False
                
                if st.button('Connect to Binance'):
                    try:
                        from cex_exchanges import BinanceExchangeService
                        exchange = BinanceExchangeService()
                        exchange.set_credentials(binance_creds['api_key'], binance_creds['api_secret'])
                        if exchange.connect():
                            binance_creds['connected'] = True
                            st.success('Successfully connected to Binance')
                        else:
                            st.error('Failed to connect to Binance')
                    except Exception as e:
                        st.error(f'Error connecting to Binance: {str(e)}')
            
            # KuCoin Login
            elif exchange_key == 'kucoin':
                kucoin_creds = st.session_state.exchange_credentials['kucoin']
                st.markdown(f'### {st.session_state.selected_exchange} Login')
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    new_api_key = st.text_input('API Key', value=kucoin_creds['api_key'], type='password', key='kucoin_api_key')
                    if new_api_key != kucoin_creds['api_key']:
                        kucoin_creds['api_key'] = new_api_key
                        kucoin_creds['connected'] = False
                        
                with col2:
                    new_api_secret = st.text_input('API Secret', value=kucoin_creds['api_secret'], type='password', key='kucoin_api_secret')
                    if new_api_secret != kucoin_creds['api_secret']:
                        kucoin_creds['api_secret'] = new_api_secret
                        kucoin_creds['connected'] = False
                        
                with col3:
                    new_passphrase = st.text_input('API Passphrase', value=kucoin_creds['api_passphrase'], type='password', key='kucoin_api_passphrase')
                    if new_passphrase != kucoin_creds['api_passphrase']:
                        kucoin_creds['api_passphrase'] = new_passphrase
                        kucoin_creds['connected'] = False
                
                if st.button('Connect to KuCoin'):
                    try:
                        from cex_exchanges import KuCoinExchangeService
                        exchange = KuCoinExchangeService()
                        exchange.set_credentials(kucoin_creds['api_key'], kucoin_creds['api_secret'], kucoin_creds['api_passphrase'])
                        if exchange.connect():
                            kucoin_creds['connected'] = True
                            st.success('Successfully connected to KuCoin')
                        else:
                            st.error('Failed to connect to KuCoin')
                    except Exception as e:
                        st.error(f'Error connecting to KuCoin: {str(e)}')

            # BitBNS Login
            elif exchange_key == 'bitbns':
                bitbns_creds = st.session_state.exchange_credentials['bitbns']
                st.markdown(f'### {st.session_state.selected_exchange} Login')
                col1, col2 = st.columns(2)
                
                with col1:
                    new_api_key = st.text_input('API Key', value=bitbns_creds['api_key'], type='password', key='bitbns_api_key')
                    if new_api_key != bitbns_creds['api_key']:
                        bitbns_creds['api_key'] = new_api_key
                        bitbns_creds['connected'] = False
                        
                with col2:
                    new_api_secret = st.text_input('API Secret', value=bitbns_creds['api_secret'], type='password', key='bitbns_api_secret')
                    if new_api_secret != bitbns_creds['api_secret']:
                        bitbns_creds['api_secret'] = new_api_secret
                        bitbns_creds['connected'] = False
                
                if st.button('Connect to BitBNS'):
                    try:
                        from cex_exchanges import BitBNSExchangeService
                        exchange = BitBNSExchangeService()
                        exchange.set_credentials(bitbns_creds['api_key'], bitbns_creds['api_secret'])
                        if exchange.connect():
                            bitbns_creds['connected'] = True
                            st.success('Successfully connected to BitBNS')
                        else:
                            st.error('Failed to connect to BitBNS')
                    except Exception as e:
                        st.error(f'Error connecting to BitBNS: {str(e)}')
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def render(self):
        """Render the main trading interface"""
        st.markdown('<div class="main-container">', unsafe_allow_html=True)
        
        # Initialize application if not already done
        if not st.session_state.initialized:
            if self.app.initialize() and self.market_data.connect():
                st.session_state.initialized = True
            else:
                st.error('Failed to initialize trading application')
                return
        
        # Render exchange login panel
        self.render_exchange_login()
        
        # Ticker Panel
        self.render_ticker_panel()
        
        # Chart panel with minimal height
        st.markdown('<div style="height: calc(100vh - 400px);">', unsafe_allow_html=True)
        self.render_chart_panel()
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Compact trading components grid layout
        st.markdown(
            '<div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; margin: 0; height: calc(100vh - 200px);">', 
            unsafe_allow_html=True
        )
        
        # Render all trading components in a horizontal grid
        self.render_trading_panel()
        self.render_orderbook_panel()
        self.render_trades_panel()
        self.wallet_panel.render()
        
        # Minimal auto trading panel
        st.markdown('<div style="margin: 0; padding: 0;">', unsafe_allow_html=True)
        self.render_auto_trading_panel()
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def render_ticker_panel(self):
        """Render the ticker panel with key market information"""
        st.markdown('<div class="ticker-panel">', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        
        with col1:
            symbol = st.session_state.selected_symbol
            last_price = self.market_data.get_last_price(symbol)
            change_24h = self.market_data.get_24h_change(symbol)
            st.metric(
                symbol,
                f"${float(last_price):,.2f}",
                f"{float(change_24h):+.2f}%",
                delta_color="normal"
            )
        
        with col2:
            volume_24h = self.market_data.get_24h_volume(symbol)
            st.metric("24h Volume", f"${float(volume_24h):,.2f}")
        
        with col3:
            high_24h = self.market_data.get_24h_high(symbol)
            st.metric("24h High", f"${float(high_24h):,.2f}")
        
        with col4:
            low_24h = self.market_data.get_24h_low(symbol)
            st.metric("24h Low", f"${float(low_24h):,.2f}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def render_indicator_panel(self):
        """Render the horizontal indicator panel"""
        st.markdown('<div class="indicator-panel">', unsafe_allow_html=True)
        
        # Create columns for each indicator
        num_indicators = len(st.session_state.active_indicators)
        if num_indicators > 0:
            cols = st.columns(num_indicators)
            
            # Render each active indicator as a card in its own column
            for (name, indicator), col in zip(st.session_state.active_indicators.items(), cols):
                with col:
                    st.markdown(f'<div class="indicator-card">', unsafe_allow_html=True)
                    
                    # Indicator header with title and enable/disable toggle
                    st.markdown(
                        f'<div class="indicator-header">'
                        f'<span class="indicator-title">{name}</span>'
                        '</div>',
                        unsafe_allow_html=True
                    )
                    
                    enabled = st.checkbox('Enabled', value=indicator.enabled, key=f'{name}_enabled')
                    if enabled != indicator.enabled:
                        indicator.enabled = enabled
                    
                    # Indicator parameters
                    st.markdown('<div class="indicator-controls">', unsafe_allow_html=True)
                    if indicator.type == 'MA':
                        period = st.number_input(
                            'Period',
                            min_value=1,
                            value=indicator.parameters['period'],
                            key=f'{name}_period'
                        )
                        if period != indicator.parameters['period']:
                            indicator.parameters['period'] = period
                    elif indicator.type == 'RSI':
                        period = st.number_input(
                            'Period',
                            min_value=1,
                            value=indicator.parameters['period'],
                            key=f'{name}_period'
                        )
                        if period != indicator.parameters['period']:
                            indicator.parameters['period'] = period
                    
                    st.markdown('</div>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def render_chart_panel(self):
        """Render the advanced charting panel"""
        st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
        
        # Optimized chart controls layout
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            # Get available trading pairs from SushiSwap
            available_pairs = [pair.symbol for pair in self.app.exchange.get_available_pairs()]
            if not available_pairs:
                available_pairs = ['BTC/USDT']  # Fallback to default if no pairs available
                
            symbol = st.selectbox(
                'Trading Pair',
                available_pairs,
                key='chart_symbol'
            )
        
        with col2:
            timeframe = st.selectbox(
                'Timeframe',
                ['1m', '5m', '15m', '1h', '4h', '1d'],
                key='chart_timeframe'
            )
        
        with col3:
            st.markdown('<div class="chart-tools">', unsafe_allow_html=True)
            show_indicators = st.button('Indicators', key='show_indicators')
            st.markdown('</div>', unsafe_allow_html=True)
            
        # Show indicator panel when button is clicked
        if show_indicators:
            self.render_indicator_panel()
        
        # Update market data subscription if symbol changed
        if symbol != st.session_state.selected_symbol:
            st.session_state.selected_symbol = symbol
            self.market_data.subscribe_to_candles(symbol)
        
        # Get and display candlestick data
        candles = self.market_data.get_candle_history(symbol)
        if candles and len(candles) > 0:
            fig = go.Figure()
            
            # Candlestick chart
            fig.add_trace(go.Candlestick(
                x=[datetime.fromtimestamp(c.timestamp/1000) for c in candles],
                open=[float(c.open_price) for c in candles],
                high=[float(c.high_price) for c in candles],
                low=[float(c.low_price) for c in candles],
                close=[float(c.close_price) for c in candles],
                name='OHLC'
            ))
            
            # Add technical indicators
            for name, indicator in st.session_state.active_indicators.items():
                if not indicator.enabled:
                    continue
                    
                if indicator.type == 'MA':
                    ma_values = self.indicators.calculate_ma(candles, indicator.parameters['period'])
                    fig.add_trace(go.Scatter(
                        x=[datetime.fromtimestamp(c.timestamp/1000) for c in candles],
                        y=ma_values,
                        name=f"MA({indicator.parameters['period']})",
                        line=dict(color=indicator.color)
                    ))
                elif indicator.type == 'RSI':
                    rsi_values = self.indicators.calculate_rsi(candles, indicator.parameters['period'])
                    fig.add_trace(go.Scatter(
                        x=[datetime.fromtimestamp(c.timestamp/1000) for c in candles],
                        y=rsi_values,
                        name='RSI',
                        yaxis='y3',
                        line=dict(color=indicator.color)
                    ))
                elif indicator.type == 'MACD':
                    macd_data = self.indicators.calculate_macd(candles)
                    fig.add_trace(go.Scatter(
                        x=[datetime.fromtimestamp(c.timestamp/1000) for c in candles],
                        y=macd_data['macd'],
                        name='MACD',
                        yaxis='y4',
                        line=dict(color='#2962FF')
                    ))
                    fig.add_trace(go.Scatter(
                        x=[datetime.fromtimestamp(c.timestamp/1000) for c in candles],
                        y=macd_data['signal'],
                        name='Signal',
                        yaxis='y4',
                        line=dict(color='#FF6B6B')
                    ))
            
            # Volume bars
            fig.add_trace(go.Bar(
                x=[datetime.fromtimestamp(c.timestamp/1000) for c in candles],
                y=[float(c.volume) for c in candles],
                name='Volume',
                yaxis='y2',
                marker_color='rgba(128,128,128,0.5)'
            ))
            
            # Professional dark theme styling with subplots
            fig.update_layout(
                plot_bgcolor='#1A1F25',
                paper_bgcolor='#1A1F25',
                font=dict(color='#E0E0E0'),
                xaxis=dict(
                    gridcolor='#2D3748',
                    zerolinecolor='#2D3748',
                    rangeslider=dict(visible=False),
                    domain=[0, 1]
                ),
                yaxis=dict(
                    gridcolor='#2D3748',
                    zerolinecolor='#2D3748',
                    side='right',
                    domain=[0.3, 1]
                ),
                yaxis2=dict(
                    gridcolor='#2D3748',
                    zerolinecolor='#2D3748',
                    overlaying='y',
                    side='left',
                    showgrid=False
                ),
                yaxis3=dict(
                    gridcolor='#2D3748',
                    zerolinecolor='#2D3748',
                    domain=[0.1, 0.28],
                    title='RSI'
                ),
                yaxis4=dict(
                    gridcolor='#2D3748',
                    zerolinecolor='#2D3748',
                    domain=[0, 0.08],
                    title='MACD'
                ),
                height=800,
                margin=dict(l=50, r=50, t=30, b=30)
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info('Loading market data...')
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def render_orderbook_panel(self):
        """Render the order book panel"""
        st.markdown('<div class="order-book">', unsafe_allow_html=True)
        st.markdown('<div class="order-book-header">Order Book</div>', unsafe_allow_html=True)
        
        symbol = st.session_state.selected_symbol
        orderbook = self.market_data.get_orderbook(symbol)
        
        if orderbook:
            # Display asks (sell orders)
            st.markdown('<div class="asks">', unsafe_allow_html=True)
            for ask in reversed(orderbook.asks[:10]):
                st.markdown(
                    f'<div class="order-book-entry">'
                    f'<span class="ask-price">${float(ask.price):.2f}</span>'
                    f'<span class="size">{float(ask.size):.4f}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Spread indicator
            spread = orderbook.get_spread()
            st.markdown(
                f'<div class="spread-indicator">'
                f'<span>Spread: ${float(spread):.2f}</span>'
                f'</div>',
                unsafe_allow_html=True
            )
            
            # Display bids (buy orders)
            st.markdown('<div class="bids">', unsafe_allow_html=True)
            for bid in orderbook.bids[:10]:
                st.markdown(
                    f'<div class="order-book-entry">'
                    f'<span class="bid-price">${float(bid.price):.2f}</span>'
                    f'<span class="size">{float(bid.size):.4f}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info('Loading order book...')
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def render_auto_trading_panel(self):
        """Render the automated trading control panel"""
        with st.container():
            st.markdown('<div class="auto-trading-panel">', unsafe_allow_html=True)
            st.markdown('<div class="panel-header">Automated Trading</div>', unsafe_allow_html=True)
            
            # Auto-trading controls in a single container
            if not st.session_state.auto_trading_enabled:
                if st.button('Start Auto Trading', type='primary', use_container_width=True):
                    if self.auto_trader.start():
                        st.session_state.auto_trading_enabled = True
                        st.success('Automated trading started')
            else:
                if st.button('Stop Auto Trading', type='secondary', use_container_width=True):
                    self.auto_trader.stop()
                    st.session_state.auto_trading_enabled = False
                    st.info('Automated trading stopped')
            
            # Display trading status
            if st.session_state.auto_trading_enabled:
                status = self.auto_trader.get_trading_status()
                active_trades = self.auto_trader.get_active_trades()
                
                st.markdown('### Trading Status')
                st.markdown(f"Active Trades: {status['active_trades']}")
                st.markdown(f"Profit Target: {status['profit_target']}x")
                
                if active_trades:
                    st.markdown('### Active Trades')
                    for symbol, trade in active_trades.items():
                        st.markdown(
                            f"**{symbol}** - {trade['type'].upper()}\n"
                            f"Entry: ${float(trade['entry_price'] if trade['entry_price'] is not None else 0):.2f} | "
                            f"Quantity: {float(trade['quantity']):.4f}"
                        )
            
            st.markdown('</div>', unsafe_allow_html=True)
    
    def render_trades_panel(self):
        """Render the recent trades panel"""
        st.markdown('<div class="trades-panel">', unsafe_allow_html=True)
        st.markdown('<div class="trades-header">Recent Trades</div>', unsafe_allow_html=True)
        
        symbol = st.session_state.selected_symbol
        trades = self.market_data.get_recent_trades(symbol)
        
        if trades:
            for trade in trades[:20]:
                side_class = 'buy-trade' if trade['side'] == 'buy' else 'sell-trade'
                st.markdown(
                    f'<div class="trade-entry {side_class}">' 
                    f'<span class="trade-price">${float(trade["price"]):.2f}</span>' 
                    f'<span class="trade-size">{float(trade["size"]):.4f}</span>' 
                    f'<span class="trade-time">{datetime.fromtimestamp(trade["timestamp"]/1000).strftime("%H:%M:%S")}</span>' 
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info('Loading trades...')
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def render_trading_panel(self):
        """Render the trading panel with order form"""
        st.markdown('<div class="trading-panel">', unsafe_allow_html=True)
        
        # Trading form with compact layout
        with st.form('trading_form', clear_on_submit=True):
            # Create three columns for a more compact layout
            col1, col2, col3 = st.columns([1, 1, 1])
            
            # First column for side selection (Buy/Sell)
            with col1:
                side = st.selectbox(
                    'Side',
                    ['Buy', 'Sell'],
                    key='order_side',
                    label_visibility='collapsed'
                )
            
            # Second column for amount input
            with col2:
                quantity = st.number_input(
                    'Amount',
                    min_value=0.0,
                    step=0.0001,
                    format='%.4f',
                    key='order_quantity',
                    label_visibility='collapsed'
                )
            
            # Third column for order type and price
            with col3:
                order_type = st.selectbox(
                    'Type',
                    ['Market', 'Limit'],
                    key='order_type',
                    label_visibility='collapsed'
                )
                
                if order_type != 'Market':
                    price = st.number_input(
                        'Price',
                        min_value=0.0,
                        step=0.01,
                        format='%.2f',
                        key='order_price',
                        label_visibility='collapsed'
                    )
            
            # Order preview
            if quantity > 0 and (order_type == 'Market' or (order_type != 'Market' and price > 0)):
                total = quantity * (price if order_type != 'Market' else float(self.market_data.get_last_price(st.session_state.selected_symbol)))
                st.markdown(
                    f'<div class="order-preview">' 
                    f'<div>Total: ${total:.2f}</div>'
                    f'<div>Margin: ${total/leverage:.2f}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            
            # Submit button
            submit_button = st.form_submit_button(
                f'{side} {st.session_state.selected_symbol}',
                use_container_width=True,
                type='primary'
            )
            
            if submit_button:
                try:
                    order_params = {
                        'symbol': st.session_state.selected_symbol,
                        'side': side.lower(),
                        'type': order_type.lower(),
                        'quantity': Decimal(str(quantity)),
                        'leverage': leverage
                    }
                    if order_type != 'Market':
                        order_params['price'] = Decimal(str(price))
                    
                    order = self.app.place_order(**order_params)
                    if order:
                        st.success(f'{side} order placed successfully')
                    else:
                        st.error('Failed to place order')
                except Exception as e:
                    st.error(f'Failed to place order: {str(e)}')
        
        st.markdown('</div>', unsafe_allow_html=True)



def main():
    ui = TradingUI()
    ui.render()

if __name__ == '__main__':
    main()