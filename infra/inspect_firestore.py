#!/usr/bin/env python3

"""
Script to inspect existing Firestore collections and document structure
"""

import asyncio
import logging
from google.cloud import firestore
from typing import Dict, List, Any

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def inspect_firestore():
    """Inspect existing Firestore collections and documents"""
    print("🔍 Inspecting existing Firestore collections...")
    
    # Initialize Firestore client
    db = firestore.Client()
    
    try:
        # List all collections
        collections = db.collections()
        collection_names = []
        
        print("\n📁 Available Collections:")
        for collection in collections:
            collection_names.append(collection.id)
            print(f"  - {collection.id}")
        
        # Check specific collections we're interested in
        collections_to_check = [
            'react_universeSymbols',
            'react_activeSymbols', 
            'symbols',
            'universe_symbols',
            'active_symbols',
            'indices',
            'config'
        ]
        
        for collection_name in collections_to_check:
            print(f"\n📋 Checking collection: {collection_name}")
            collection_ref = db.collection(collection_name)
            docs = collection_ref.stream()
            
            doc_count = 0
            for doc in docs:
                doc_count += 1
                doc_data = doc.to_dict()
                print(f"  📄 Document ID: {doc.id}")
                
                # Print document structure without full content
                if doc_data:
                    print(f"    📊 Fields: {list(doc_data.keys())}")
                    
                    # Show some sample data for key fields
                    for key, value in doc_data.items():
                        if isinstance(value, list) and len(value) > 0:
                            print(f"      {key}: List with {len(value)} items")
                            if len(value) <= 3:
                                print(f"        Sample: {value}")
                            else:
                                print(f"        Sample: {value[:3]}...")
                        elif isinstance(value, dict):
                            print(f"      {key}: Dict with keys: {list(value.keys())[:5]}")
                        else:
                            print(f"      {key}: {type(value).__name__} - {str(value)[:100]}...")
                else:
                    print(f"    ⚠️  Empty document")
            
            if doc_count == 0:
                print(f"    ❌ Collection '{collection_name}' not found or empty")
            else:
                print(f"    ✓ Found {doc_count} documents")
        
        print("\n🎉 Firestore inspection completed!")
        
    except Exception as e:
        logger.error(f"Error inspecting Firestore: {e}")
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_firestore())