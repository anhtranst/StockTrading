# Real-Time Stock Trading Engine

## Overview
This project implements a real-time stock trading engine that efficiently matches buy and sell orders while ensuring thread safety. It is designed to handle concurrent order processing using lock-free data structures while maintaining high performance.

## Problem Statement
The goal of this assignment is to develop a stock trading engine that:
- Matches buy and sell orders based on price-time priority.
- Ensures thread safety using lock-free data structures.
- Does **not** use dictionaries or maps for storage.
- Processes buy and sell orders in a multi-threaded environment.

## Solution Approach
To achieve an efficient real-time stock matching system, the following design was used:

1. **Order Matching Algorithm**  
   - Orders are sorted by price (highest buy price first, lowest sell price first).  
   - If prices match, transactions are executed based on time priority (earlier orders are fulfilled first).  
   - Partially matched orders remain in the queue until fully executed.

2. **Thread Safety & Concurrency**  
   - Lock-free data structures ensure concurrent access without blocking threads.  
   - Atomic operations handle race conditions while maintaining order integrity.  

3. **Data Structure Choice (No Dictionaries/Maps)**  
   - Buy and sell orders are stored in **linked lists** instead of hash maps.  
   - Orders are processed using a **priority queue** approach without using direct key-value lookups.

4. **Order Execution Process**  
   - When a new order is placed, it is compared against the existing order book.  
   - If a match is found, a trade is executed, and both orders are updated accordingly.  
   - If no match exists, the order is added to the appropriate queue (buy or sell).  

## Code Structure
The code is organized into the following key components:

- **`Order` (Class):** Represents a stock order with attributes:
  - `type` (BUY/SELL)
  - `price`
  - `quantity`
  - `timestamp`

- **`OrderBook` (Class):**  
  - Maintains separate lists for buy and sell orders.  
  - Matches buy and sell orders based on price-time priority.  
  - Ensures atomic updates for thread safety.

- **`TradingEngine` (Class):**  
  - Processes incoming orders in a concurrent environment.  
  - Uses multiple threads to handle order matching efficiently.  
  - Ensures lock-free operations while maintaining data integrity.

- **`main.py` (Script):**  
  - Entry point that initializes the trading engine.  
  - Simulates placing buy and sell orders for testing.  

## Installation & Running the Code
### Prerequisites
- Python 3.8 or later

### Steps to Run
1. Clone the repository:
   ```bash
   git clone https://github.com/anhtranst/StockTrading.git
   cd StockTrading
