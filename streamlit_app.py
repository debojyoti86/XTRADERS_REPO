import streamlit as st
import pandas as pd
from typing import Dict, List
from market_data import MarketData
from trading_engine import TradingEngine
from wallet import Wallet
from models import Order, Trade

# Configure Streamlit page settings
st.set_page_config(
    page_title="XTraders Trading Application",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'market_data' not in st.session_state:
    st.session_state.market_data = MarketData()
if 'trading_engine' not in st.session_state:
    st.session_state.trading_engine = TradingEngine()
if 'wallet' not in st.session_state:
    st.session_state.wallet = Wallet()

def main():
    # Sidebar for configuration and controls
    with st.sidebar:
        st.title("Trading Controls")
        
        # Exchange selection
        exchange = st.selectbox(
            "Select Exchange",
            ["Binance", "KuCoin"]
        )
        
        # Trading pair selection
        trading_pair = st.selectbox(
            "Select Trading Pair",
            ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
        )
        
        # Order type and parameters
        order_type = st.selectbox(
            "Order Type",
            ["Market", "Limit"]
        )
        
        quantity = st.number_input(
            "Quantity",
            min_value=0.0,
            step=0.001
        )
        
        if order_type == "Limit":
            price = st.number_input(
                "Price",
                min_value=0.0,
                step=0.01
            )
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("Market Data")
        # Display real-time price chart
        try:
            market_data = st.session_state.market_data.get_market_data(exchange, trading_pair)
            st.line_chart(market_data)
        except Exception as e:
            st.error(f"Error loading market data: {str(e)}")
        
        # Order book visualization
        st.subheader("Order Book")
        try:
            order_book = st.session_state.market_data.get_order_book(exchange, trading_pair)
            col_bid, col_ask = st.columns(2)
            with col_bid:
                st.write("Bids")
                st.dataframe(order_book['bids'])
            with col_ask:
                st.write("Asks")
                st.dataframe(order_book['asks'])
        except Exception as e:
            st.error(f"Error loading order book: {str(e)}")
    
    with col2:
        st.header("Trading Activity")
        # Wallet balance
        st.subheader("Wallet Balance")
        try:
            balance = st.session_state.wallet.get_balance()
            st.write(balance)
        except Exception as e:
            st.error(f"Error loading wallet balance: {str(e)}")
        
        # Open orders
        st.subheader("Open Orders")
        try:
            open_orders = st.session_state.trading_engine.get_open_orders()
            st.table(open_orders)
        except Exception as e:
            st.error(f"Error loading open orders: {str(e)}")
        
        # Recent trades
        st.subheader("Recent Trades")
        try:
            recent_trades = st.session_state.trading_engine.get_recent_trades()
            st.table(recent_trades)
        except Exception as e:
            st.error(f"Error loading recent trades: {str(e)}")

        # Trading buttons
        col_buy, col_sell = st.columns(2)
        with col_buy:
            if st.button("Buy", type="primary"):
                try:
                    order = Order(
                        exchange=exchange,
                        symbol=trading_pair,
                        order_type=order_type,
                        side="buy",
                        quantity=quantity,
                        price=price if order_type == "Limit" else None
                    )
                    st.session_state.trading_engine.place_order(order)
                    st.success("Buy order placed successfully!")
                except Exception as e:
                    st.error(f"Error placing buy order: {str(e)}")
        
        with col_sell:
            if st.button("Sell", type="primary"):
                try:
                    order = Order(
                        exchange=exchange,
                        symbol=trading_pair,
                        order_type=order_type,
                        side="sell",
                        quantity=quantity,
                        price=price if order_type == "Limit" else None
                    )
                    st.session_state.trading_engine.place_order(order)
                    st.success("Sell order placed successfully!")
                except Exception as e:
                    st.error(f"Error placing sell order: {str(e)}")

if __name__ == "__main__":
    main()