# Real-Time Stock Trading Engine

> **Note**: This README explains the implementation in `simple.py` which satisfies the original requirements. There is another implementation, `advance.py`, which is explained in `README_ADVANCE.md`.

## Overview
This project implements a high-performance, lock-free stock trading engine that efficiently matches buy and sell orders in a multi-threaded environment. The system is designed to handle concurrent order processing while ensuring thread safety without traditional locks.

## Features
- Support for 1,024 different stock tickers with hash collision handling
- Lock-free concurrent order processing
- O(n) time complexity for order matching
- Sorted order books (highest buy price first, lowest sell price first)
- Detailed logging and performance metrics
- Robust error handling and recovery mechanisms

## Problem Statement
The goal was to develop a stock trading engine that:
- Adds buy and sell orders with specified ticker, quantity, and price
- Matches orders when a buy price is greater than or equal to a sell price
- Handles race conditions using lock-free data structures
- Avoids using dictionaries, maps or equivalent data structures
- Achieves O(n) time complexity for order matching

## Solution Architecture

### Data Structures
1. **Fixed-Size Array for Tickers**
   - A simple array of size 1,024 holds all ticker data
   - Each slot can contain multiple ticker nodes (for handling hash collisions)
   - FNV-1a hash function maps ticker symbols to array indices

2. **Linked List for Hash Collision Resolution**
   - Each array slot contains a linked list of TickerNode objects
   - Each TickerNode represents a unique ticker and contains buy/sell order books
   - This allows multiple tickers to share the same hash bucket

3. **Lock-Free Linked Lists for Order Books**
   - Buy orders are stored in descending price order
   - Sell orders are stored in ascending price order
   - Pointers between nodes use atomic references

4. **Atomic References**
   - Custom implementation that provides thread-safe pointer manipulation
   - Supports Compare-And-Swap (CAS) operations for lock-free updates

### Key Components

#### Order
Each order contains:
- Order type (Buy or Sell)
- Ticker symbol
- Quantity (atomic value)
- Price
- Unique order ID
- Timestamp

#### TickerNode
Represents a single ticker symbol with its associated order books:
- Ticker symbol
- Buy order book (as AtomicReference)
- Sell order book (as AtomicReference)
- Next pointer (for hash collision resolution)

#### AtomicReference
Provides thread-safe operations:
- `get()` - Retrieve the current value
- `set()` - Set a new value
- `compare_and_set()` - Atomic compare and swap operation

#### Order Insertion (addOrder)
The system uses a lock-free algorithm to insert orders in sorted position:
1. Takes a snapshot of the current book to avoid traversal issues
2. Attempts insertion at the head if appropriate
3. Otherwise, finds the correct position based on price
4. Uses progressive backoff for retries
5. Includes a fallback mechanism to prevent order loss

#### Order Matching (matchOrder)
Matching follows these steps:
1. Iterates through all buckets in the tickers array
2. For each bucket, traverses the linked list of ticker nodes (handling hash collisions)
3. For each ticker, checks if the highest buy price meets or exceeds the lowest sell price
4. If a match is possible, atomically updates quantities
5. Removes completed orders (quantity = 0)
6. Continues until no more matches are possible

## Implementation Details

### Hash Collision Handling
The implementation uses a chained hash table approach to handle collisions:
1. Each array slot contains a linked list of ticker nodes
2. When a hash collision occurs, new tickers are appended to this list
3. Lookup involves finding the right bucket, then traversing the list to find the specific ticker
4. This approach maintains O(1) average-case access time while handling any number of collisions

### Thread Safety Mechanisms
1. **Atomic Operations**
   - All critical updates use atomic operations
   - No global locks to prevent deadlocks

2. **Optimistic Concurrency Control**
   - Assumes operations will succeed but verifies afterward
   - Retries with backoff if verification fails

3. **Snapshot-Based Processing**
   - Creates local snapshots before operating on dynamic structures
   - Prevents issues with concurrent modifications during traversal

4. **Progressive Backoff**
   - Increases wait time with each retry attempt
   - Reduces contention in high-load scenarios

### Performance Considerations
1. **FNV-1a Hash Function**
   - Efficiently distributes tickers across the array
   - Minimizes collision probability

2. **Sorted Order Books**
   - Enables O(1) access to best prices
   - Facilitates efficient matching

3. **Retry Limits**
   - Prevents excessive CPU consumption
   - Balances persistence with system load

## How to Run the Code

### Prerequisites
- Python 3.6 or later

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/anhtranst/StockTrading.git
   cd StockTrading
   ```

2. No additional dependencies are required as the code uses only Python standard libraries.

### Running the Simulation
Execute the main Python file:
```bash
python simple.py
```

This will start a simulation that:
1. Creates a stock exchange
2. Adds test orders to ensure matching works
3. Simulates multi-threaded trading with random orders
4. Logs results to both console and log files

### Configuration Options
You can modify these parameters in the main script:
- `num_orders`: Total number of orders to simulate
- `num_threads`: Number of concurrent trading threads
- Sample tickers and price ranges

### Log Files
The system generates a log file:
- `simple.log`: Trading activity, order matches, and performance metrics

## Code Structure

### Main Functions
1. `addOrder(order_type, ticker_symbol, quantity, price)`
   - Adds a new order to the appropriate order book
   - Returns the created order object or None if insertion failed

2. `matchOrder()`
   - Matches buy and sell orders across all tickers
   - Returns the number of matches made
   - Handles hash collisions by traversing ticker node lists

3. `simulate_trading(num_orders, num_threads)`
   - Creates multiple threads that add random orders
   - Measures and reports performance metrics

### Utility Functions
1. `hash_ticker(ticker_symbol)`
   - Maps ticker symbols to array indices
   - Uses FNV-1a hash algorithm for even distribution

2. `get_or_create_books(ticker_symbol)`
   - Finds or creates order books for a specific ticker
   - Handles hash collisions appropriately

3. `print_order_book(ticker_symbol)`
   - Outputs the current state of an order book
   - Useful for debugging and verification

4. `add_test_orders()`
   - Adds predetermined orders to verify matching functionality
   - Ensures basic functionality works before starting simulation

## Performance Metrics
The simulation reports:
- Total execution time
- Number of orders processed
- Orders per second throughput
- Total matches made

## Limitations and Future Improvements
1. **Python's GIL Constraint**
   - Python's Global Interpreter Lock limits true parallelism
   - A C/C++ implementation would offer better performance

2. **Potential Enhancements**
   - Implement partial order matching
   - Add support for order cancellation
   - Include market orders and limit orders
   - Add more sophisticated price-time priority

3. **Scaling Considerations**
   - Current implementation handles 1,024 tickers efficiently
   - For more tickers, a distributed approach would be needed

4. **Hash Collision Optimization**
   - Current implementation uses simple linked lists for collision resolution
   - For extremely high collision rates, more sophisticated structures could be used

## Conclusion
This lock-free stock trading engine demonstrates how to build high-performance concurrent systems without traditional locks. The implementation satisfies all requirements while maintaining O(n) time complexity for order matching, ensuring thread safety in a multi-threaded environment, and properly handling hash collisions for ticker symbols.