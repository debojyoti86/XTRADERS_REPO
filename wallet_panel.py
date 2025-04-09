import streamlit as st
from decimal import Decimal
from typing import Dict, List
from datetime import datetime
from wallet import WalletModule

class WalletPanel:
    def __init__(self, wallet: WalletModule):
        self.wallet = wallet
        
    def render(self):
        """Render the wallet panel"""
        st.markdown('<div class="wallet-panel">', unsafe_allow_html=True)
        st.markdown('<div class="wallet-header">Wallet</div>', unsafe_allow_html=True)
        
        # Display wallet balances
        self.render_balances()
        
        # Display transaction history
        self.render_transaction_history()
        
        # Transfer funds form
        self.render_transfer_form()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def render_balances(self):
        """Display wallet balances section"""
        st.markdown('<div class="balances-section">', unsafe_allow_html=True)
        
        # Get balances
        trading_balance = self.wallet.get_trading_balance()
        profit_balance = self.wallet.get_profit_balance()
        total_balance = trading_balance + profit_balance
        
        # Display balances in columns
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Trading Balance",
                f"${float(trading_balance):,.2f}",
                delta=None,
                delta_color="normal"
            )
        
        with col2:
            st.metric(
                "Profit Balance",
                f"${float(profit_balance):,.2f}",
                delta=None,
                delta_color="normal"
            )
        
        with col3:
            st.metric(
                "Total Balance",
                f"${float(total_balance):,.2f}",
                delta=None,
                delta_color="normal"
            )
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def render_transaction_history(self):
        """Display transaction history section"""
        st.markdown('<div class="transaction-history">', unsafe_allow_html=True)
        st.markdown('<div class="section-header">Transaction History</div>', unsafe_allow_html=True)
        
        transactions = self.wallet.get_transaction_history()
        if transactions:
            for tx in transactions[:10]:  # Show last 10 transactions
                tx_type_class = 'credit' if tx['type'] == 'credit' else 'debit'
                amount = float(tx['amount'])
                st.markdown(
                    f'<div class="transaction-entry {tx_type_class}">' 
                    f'<span class="tx-type">{tx["type"].title()}</span>' 
                    f'<span class="tx-amount">${amount:,.2f}</span>' 
                    f'<span class="tx-time">{datetime.fromtimestamp(tx["timestamp"]).strftime("%Y-%m-%d %H:%M")}</span>' 
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info('No transactions found')
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    def render_transfer_form(self):
        """Display transfer funds form"""
        st.markdown('<div class="transfer-form">', unsafe_allow_html=True)
        st.markdown('<div class="section-header">Transfer Funds</div>', unsafe_allow_html=True)
        
        with st.form('transfer_form'):
            col1, col2 = st.columns(2)
            
            with col1:
                from_wallet = st.selectbox(
                    'From',
                    ['Trading', 'Profit'],
                    key='transfer_from'
                )
            
            with col2:
                to_wallet = st.selectbox(
                    'To',
                    ['Profit', 'Trading'],
                    key='transfer_to'
                )
            
            amount = st.number_input(
                'Amount',
                min_value=0.0,
                step=0.01,
                format='%.2f',
                key='transfer_amount'
            )
            
            if st.form_submit_button('Transfer', use_container_width=True):
                if from_wallet == to_wallet:
                    st.error('Cannot transfer to the same wallet')
                elif amount <= 0:
                    st.error('Amount must be greater than 0')
                else:
                    try:
                        if self.wallet.transfer(
                            from_wallet.lower(),
                            to_wallet.lower(),
                            Decimal(str(amount))
                        ):
                            st.success('Transfer successful')
                            st.experimental_rerun()
                        else:
                            st.error('Transfer failed')
                    except Exception as e:
                        st.error(f'Transfer failed: {str(e)}')
        
        st.markdown('</div>', unsafe_allow_html=True)