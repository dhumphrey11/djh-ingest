#!/usr/bin/env python3
"""
Initialize Firestore with symbol configuration data for the ingestion pipeline
"""

import asyncio
import logging
from google.cloud import firestore
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample data
UNIVERSE_SYMBOLS = [
    # Tech stocks
    {"ticker": "AAPL", "active": True, "sector": "Technology", "name": "Apple Inc."},
    {"ticker": "MSFT", "active": True, "sector": "Technology", "name": "Microsoft Corporation"},
    {"ticker": "GOOGL", "active": True, "sector": "Technology", "name": "Alphabet Inc."},
    {"ticker": "AMZN", "active": True, "sector": "Technology", "name": "Amazon.com Inc."},
    {"ticker": "NVDA", "active": True, "sector": "Technology", "name": "NVIDIA Corporation"},
    {"ticker": "META", "active": True, "sector": "Technology", "name": "Meta Platforms Inc."},
    {"ticker": "TSLA", "active": True, "sector": "Technology", "name": "Tesla Inc."},
    
    # Financial stocks
    {"ticker": "JPM", "active": True, "sector": "Financial", "name": "JPMorgan Chase & Co."},
    {"ticker": "BAC", "active": True, "sector": "Financial", "name": "Bank of America Corp."},
    {"ticker": "WFC", "active": True, "sector": "Financial", "name": "Wells Fargo & Company"},
    
    # Healthcare
    {"ticker": "JNJ", "active": True, "sector": "Healthcare", "name": "Johnson & Johnson"},
    {"ticker": "PFE", "active": True, "sector": "Healthcare", "name": "Pfizer Inc."},
    
    # Consumer
    {"ticker": "KO", "active": True, "sector": "Consumer", "name": "The Coca-Cola Company"},
    {"ticker": "PG", "active": True, "sector": "Consumer", "name": "Procter & Gamble Co."},
    
    # Energy
    {"ticker": "XOM", "active": True, "sector": "Energy", "name": "Exxon Mobil Corporation"},
]

INDICES = [
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "type": "ETF"},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "type": "ETF"}, 
    {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "type": "ETF"},
    {"symbol": "DIA", "name": "SPDR Dow Jones Industrial Average ETF Trust", "type": "ETF"},
    {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF", "type": "ETF"},
]

ACTIVE_POSITIONS = [
    # Sample portfolio positions
    {"ticker": "AAPL", "quantity": 100, "avg_cost": 175.50, "sector": "Technology"},
    {"ticker": "MSFT", "quantity": 50, "avg_cost": 380.25, "sector": "Technology"},
    {"ticker": "GOOGL", "quantity": 25, "avg_cost": 140.80, "sector": "Technology"},
    {"ticker": "TSLA", "quantity": 30, "avg_cost": 250.75, "sector": "Technology"},
    {"ticker": "JPM", "quantity": 40, "avg_cost": 145.20, "sector": "Financial"},
    {"ticker": "SPY", "quantity": 200, "avg_cost": 445.60, "sector": "Index"},
]

async def init_firestore():
    """Initialize Firestore with symbol configuration data"""
    
    # Initialize Firestore client
    client = firestore.AsyncClient()
    
    try:
        # 1. Set up universe symbols and indices
        logger.info("Setting up universe symbols and indices...")
        universe_doc_ref = client.document("react_universeSymbols/config")
        
        universe_data = {
            "symbols": UNIVERSE_SYMBOLS,
            "indices": INDICES,
            "last_updated": datetime.utcnow(),
            "total_symbols": len(UNIVERSE_SYMBOLS),
            "total_indices": len(INDICES)
        }
        
        await universe_doc_ref.set(universe_data)
        logger.info(f"✓ Created universe config with {len(UNIVERSE_SYMBOLS)} symbols and {len(INDICES)} indices")
        
        # 2. Set up active positions
        logger.info("Setting up active portfolio positions...")
        active_doc_ref = client.document("react_activeSymbols/positions")
        
        active_data = {
            "positions": ACTIVE_POSITIONS,
            "last_updated": datetime.utcnow(),
            "total_positions": len(ACTIVE_POSITIONS),
            "total_value": sum(pos["quantity"] * pos["avg_cost"] for pos in ACTIVE_POSITIONS)
        }
        
        await active_doc_ref.set(active_data)
        logger.info(f"✓ Created active positions with {len(ACTIVE_POSITIONS)} positions")
        
        # 3. Verify the data was created correctly
        logger.info("Verifying created documents...")
        
        # Check universe symbols
        universe_doc = await universe_doc_ref.get()
        if universe_doc.exists:
            data = universe_doc.to_dict()
            if data:
                logger.info(f"✓ Universe symbols verified: {len(data.get('symbols', []))} symbols")
        
        # Check active positions  
        active_doc = await active_doc_ref.get()
        if active_doc.exists:
            data = active_doc.to_dict()
            if data:
                logger.info(f"✓ Active positions verified: {len(data.get('positions', []))} positions")
        
        logger.info("🎉 Firestore initialization completed successfully!")
        
    except Exception as e:
        logger.error(f"Failed to initialize Firestore: {e}")
        raise
    
    finally:
        # Close the client
        client.close()

def main():
    """Main function to run the initialization"""
    print("🚀 Initializing Firestore with symbol configuration...")
    asyncio.run(init_firestore())

if __name__ == "__main__":
    main()