from trading_app import TradingApplication
import sys

def main():
    try:
        # Create and initialize trading application
        app = TradingApplication()
        
        # Initialize with retry mechanism
        if not app.initialize(max_retries=3):
            print("Failed to initialize trading application after maximum retries")
            sys.exit(1)
            
        print("Trading application is running. Press Ctrl+C to exit.")
        
        # Keep the application running
        try:
            while True:
                pass
        except KeyboardInterrupt:
            print("\nShutting down trading application...")
            app._cleanup_connections()
            print("Trading application shutdown complete.")
            
    except Exception as e:
        print(f"Error running trading application: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()