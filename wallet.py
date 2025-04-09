import uuid
import json
import decimal
from decimal import Decimal
from datetime import datetime
import os

class TransactionHistory:
    """Class to track transaction history for wallet transfers"""
    def __init__(self):
        self.transactions = []
        self.transaction_file = 'transaction_history.json'
        self._load_transactions()
    
    def _load_transactions(self):
        """Load transactions from file if it exists"""
        try:
            if os.path.exists(self.transaction_file):
                with open(self.transaction_file, 'r') as f:
                    self.transactions = json.load(f)
        except Exception as e:
            print(f"Error loading transactions: {e}")
    
    def _save_transactions(self):
        """Save transactions to file"""
        try:
            with open(self.transaction_file, 'w') as f:
                json.dump(self.transactions, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving transactions: {e}")
    
    def add_transaction(self, from_address, to_address, currency, amount):
        """Add a new transaction to the history"""
        transaction = {
            'id': str(uuid.uuid4()),
            'from_address': from_address,
            'to_address': to_address,
            'currency': currency,
            'amount': str(amount),  # Convert Decimal to string for JSON serialization
            'timestamp': datetime.now().isoformat()
        }
        self.transactions.append(transaction)
        self._save_transactions()
        return transaction
    
    def get_transactions(self, address=None, limit=10):
        """Get transactions, optionally filtered by address"""
        if address:
            filtered = [t for t in self.transactions 
                       if t['from_address'] == address or t['to_address'] == address]
            return filtered[-limit:] if limit else filtered
        return self.transactions[-limit:] if limit else self.transactions
    
    def load_transactions(self):
        try:
            self._load_transactions()
            return True
        except Exception as e:
            print(f"Error loading transactions: {e}")
            return False


class WalletModule:
    """Main wallet module that manages different wallet types"""
    def __init__(self):
        self.trading_balance = Decimal('0')
        self.profit_balance = Decimal('0')
        self.wallet_address = str(uuid.uuid4())
        self.crypto_balances = {}
        self.transaction_history = TransactionHistory()
        self._balance_update_callback = None
        self._initialized = False
        self._initialization_state = 'not_started'
        
        # Initialize with some demo funds
        self.trading_balance = Decimal('10000')  # Start with 10,000 USDT
        self.profit_balance = Decimal('1000')    # Start with 1,000 USDT

    def on_balance_update(self, callback):
        """Register a callback for balance updates"""
        self._balance_update_callback = callback

    def _notify_balance_update(self):
        """Notify registered callback about balance updates"""
        if self._balance_update_callback:
            self._balance_update_callback(self.trading_balance)

    def update_trading_balance(self, amount):
        """Update the trading balance by adding the specified amount"""
        if not self._initialized:
            raise RuntimeError("Wallet not initialized")
        self.trading_balance += amount
        self._notify_balance_update()
        return self.trading_balance

    def initialize(self, max_retries: int = 3) -> bool:
        """Initialize the wallet with proper state management"""
        try:
            self._initialization_state = 'starting'
            
            # Load transaction history
            if not self.transaction_history.load_transactions():
                raise RuntimeError("Failed to load transaction history")
            
            # Verify initial balances
            if self.trading_balance < 0 or self.profit_balance < 0:
                raise ValueError("Invalid initial balance")
            
            self._initialized = True
            self._initialization_state = 'completed'
            return True
            
        except Exception as e:
            self._initialization_state = 'failed'
            print(f"Wallet initialization failed: {str(e)}")
            return False

    @property
    def is_initialized(self) -> bool:
        """Check if wallet is properly initialized"""
        return self._initialized

    def verify_health(self) -> bool:
        """Verify wallet component health"""
        try:
            return (
                self._initialized and
                self.trading_balance >= 0 and
                self.profit_balance >= 0 and
                self.wallet_address is not None
            )
        except Exception:
            return False
    
    def get_trading_balance(self):
        """Get the current trading wallet balance"""
        if not self._initialized:
            raise RuntimeError("Wallet not initialized")
        return self.trading_balance
    
    def get_profit_balance(self):
        """Get the current profit wallet balance"""
        return self.profit_balance
    
    def update_trading_balance(self, amount):
        """Update the trading balance by adding the specified amount"""
        if not self._initialized:
            raise RuntimeError("Wallet not initialized")
        self.trading_balance += amount
        self._notify_balance_update()
        return self.trading_balance

    def initialize(self, max_retries: int = 3) -> bool:
        """Initialize the wallet with proper state management"""
        try:
            self._initialization_state = 'starting'
            
            # Load transaction history
            if not self.transaction_history.load_transactions():
                raise RuntimeError("Failed to load transaction history")
            
            # Verify initial balances
            if self.trading_balance < 0 or self.profit_balance < 0:
                raise ValueError("Invalid initial balance")
            
            self._initialized = True
            self._initialization_state = 'completed'
            return True
            
        except Exception as e:
            self._initialization_state = 'failed'
            print(f"Wallet initialization failed: {str(e)}")
            return False

    @property
    def is_initialized(self) -> bool:
        """Check if wallet is properly initialized"""
        return self._initialized

    def verify_health(self) -> bool:
        """Verify wallet component health"""
        try:
            return (
                self._initialized and
                self.trading_balance >= 0 and
                self.profit_balance >= 0 and
                self.wallet_address is not None
            )
        except Exception:
            return False
    
    def update_profit_balance(self, amount):
        """Update the profit balance by adding the specified amount"""
        self.profit_balance += amount
        return self.profit_balance
    
    def has_sufficient_trading_balance(self, amount):
        """Check if there's sufficient balance in the trading wallet"""
        return self.trading_balance >= amount
    
    def has_sufficient_profit_balance(self, amount):
        """Check if there's sufficient balance in the profit wallet"""
        return self.profit_balance >= amount
    
    def transfer(self, from_wallet, to_wallet, amount):
        """Transfer funds between wallets"""
        amount = Decimal(str(amount))  # Ensure amount is a Decimal
        
        if amount <= 0:
            return False
        
        if from_wallet == 'trading' and to_wallet == 'profit':
            if not self.has_sufficient_trading_balance(amount):
                return False
            
            self.trading_balance -= amount
            self.profit_balance += amount
            self.transaction_history.add_transaction(
                self.wallet_address, self.wallet_address, 'USDT', amount)
            return True
            
        elif from_wallet == 'profit' and to_wallet == 'trading':
            if not self.has_sufficient_profit_balance(amount):
                return False
                
            self.profit_balance -= amount
            self.trading_balance += amount
            self.transaction_history.add_transaction(
                self.wallet_address, self.wallet_address, 'USDT', amount)
            return True
            
        return False
    
    def deposit(self, to_wallet, amount, from_address='external'):
        """Deposit funds into a wallet from an external source"""
        amount = Decimal(str(amount))  # Ensure amount is a Decimal
        
        if amount <= 0:
            return False
        
        if to_wallet == 'trading':
            self.trading_balance += amount
        elif to_wallet == 'profit':
            self.profit_balance += amount
        else:
            return False
            
        self.transaction_history.add_transaction(
            from_address, self.wallet_address, 'USDT', amount)
        return True
    
    def withdraw(self, from_wallet, amount, to_address):
        """Withdraw funds from a wallet to an external address"""
        amount = Decimal(str(amount))  # Ensure amount is a Decimal
        
        if amount <= 0:
            return False
        
        if from_wallet == 'trading':
            if not self.has_sufficient_trading_balance(amount):
                return False
            self.trading_balance -= amount
        elif from_wallet == 'profit':
            if not self.has_sufficient_profit_balance(amount):
                return False
            self.profit_balance -= amount
        else:
            return False
            
        self.transaction_history.add_transaction(
            self.wallet_address, to_address, 'USDT', amount)
        return True
    
    def get_wallet_address(self):
        """Get the wallet address"""
        return self.wallet_address
    
    def get_transaction_history(self, limit=10):
        """Get transaction history for this wallet"""
        return self.transaction_history.get_transactions(self.wallet_address, limit)
    
    def get_crypto_balance(self, currency):
        """Get balance of a specific cryptocurrency"""
        return self.crypto_balances.get(currency, Decimal('0'))
    
    def update_crypto_balance(self, currency, amount):
        """Update balance of a specific cryptocurrency"""
        current = self.crypto_balances.get(currency, Decimal('0'))
        self.crypto_balances[currency] = current + Decimal(str(amount))
        return self.crypto_balances[currency]