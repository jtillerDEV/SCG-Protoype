# test_connection.py
# Simple test script to verify API connection works
import os
from dotenv import load_dotenv
import alpaca_trade_api as tradeapi

def test_connection():
    load_dotenv()
    API_KEY = os.getenv("ALPACA_API_KEY")
    SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
    BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    
    if not all([API_KEY, SECRET_KEY, BASE_URL]):
        print("❌ Missing API credentials in .env file")
        return False
    
    try:
        print("🔄 Testing API connection...")
        api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL)
        
        # Test account access
        acct = api.get_account()
        print(f"✅ Account Status: {acct.status}")
        print(f"✅ Equity: ${acct.equity}")
        print(f"✅ Cash: ${acct.cash}")
        
        # Test market data access
        bars = api.get_bars("AAPL", "1Min", limit=5)
        print(f"✅ Market Data: Got {len(bars)} bars for AAPL")
        
        print("\n🎉 All tests passed! Your setup is ready.")
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

if __name__ == "__main__":
    test_connection()
