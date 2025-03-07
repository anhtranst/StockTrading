import threading
import random
import time
import logging
from multiprocessing import Value

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('simple.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('stock_exchange')

NUM_TICKERS = 1024  # Support 1,024 tickers
tickers = [None] * NUM_TICKERS  # Fixed-size array for tickers, each entry is a linked list of TickerNodes

# Constants for retry logic
MAX_RETRIES = 50   # Maximum number of retries for lock-free operations
MAX_MATCHING_ITERATIONS = 5000  # Maximum iterations for order matching


class AtomicReference:
    """ Lock-free atomic reference implementation for linked list nodes """
    def __init__(self, initial_value=None):
        self._value = initial_value
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            return self._value

    def set(self, new_value):
        with self._lock:
            self._value = new_value

    def compare_and_set(self, expected, new_value): # Ensure the value is unchanged (not interfered by other threads) before setting it to a new value
        """Atomic Compare-and-Swap (CAS)"""
        with self._lock:
            if self._value == expected:
                self._value = new_value
                return True
            return False


class Order:
    """ Represents a stock order (Buy/Sell) """
    def __init__(self, order_type, ticker, quantity, price, order_id=None):
        self.order_type = order_type  # 'Buy' or 'Sell'
        self.ticker = ticker
        self.quantity = Value('i', quantity)  # Atomic integer for safe concurrent updates
        self.price = price
        self.next = AtomicReference(None)  # Lock-free pointer to next order in list
        self.order_id = order_id or f"{order_type}-{ticker}-{time.time()}-{random.randint(1000, 9999)}"
        self.timestamp = time.time()


class TickerNode:
    """ Linked list node to handle hash collisions in tickers array """
    def __init__(self, ticker_symbol):
        self.ticker_symbol = ticker_symbol
        self.buy_book = AtomicReference(None)  # Buy order book
        self.sell_book = AtomicReference(None)  # Sell order book
        self.next = None  # Pointer to next TickerNode in case of hash collision


def hash_ticker(ticker_symbol):
    """
    A hash function for tickers to distribute them evenly
    Uses FNV-1a hash algorithm which is good for short strings like tickers
    """
    h = 2166136261  # FNV offset basis
    for char in ticker_symbol:
        h = h ^ ord(char)
        h = (h * 16777619) & 0xFFFFFFFF  # FNV prime & 32-bit mask
    return h % NUM_TICKERS


def get_or_create_books(ticker_symbol):
    """ Retrieves or creates the order books for a given ticker, handling hash collisions """
    index = hash_ticker(ticker_symbol)
    
    # If no ticker node at this index yet, create one
    if tickers[index] is None:
        new_node = TickerNode(ticker_symbol)
        tickers[index] = new_node
        return new_node.buy_book, new_node.sell_book

    # Handle hash collision by traversing linked list
    current = tickers[index]
    prev = None
    
    # Find matching ticker or end of list
    while current is not None:
        if current.ticker_symbol == ticker_symbol:
            # Found existing ticker, return its books
            return current.buy_book, current.sell_book
        prev = current
        current = current.next
    
    # Ticker not found in list, add at end
    new_node = TickerNode(ticker_symbol)
    prev.next = new_node
    return new_node.buy_book, new_node.sell_book


def addOrder(order_type, ticker_symbol, quantity, price):
    """ Adds a Buy or Sell order to the appropriate order book """
    if quantity <= 0:
        logger.warning(f"Rejected order with invalid quantity: {quantity}")
        return None
        
    if price <= 0:
        logger.warning(f"Rejected order with invalid price: {price}")
        return None
    
    # Get the appropriate order books for this ticker
    buy_book, sell_book = get_or_create_books(ticker_symbol)
    new_order = Order(order_type, ticker_symbol, quantity, price)

    is_buy = order_type == "Buy"
    book = buy_book if is_buy else sell_book

    # SIMPLIFIED APPROACH: Use a hybrid approach to reduce retry failures
    retries = 0
    while retries < MAX_RETRIES:
        try:
            # Take a snapshot of the entire list to avoid iterating through a changing list
            nodes = []
            current = book.get()
            
            # Collect all nodes in a local list (won't be affected by concurrent changes)
            while current is not None:
                nodes.append(current)
                current = current.next.get()
            
            # Case 1: Empty list or should be at the head
            if len(nodes) == 0 or (is_buy and price > nodes[0].price) or (not is_buy and price < nodes[0].price):
                new_order.next.set(book.get())  # Re-get head as it could have changed
                if book.compare_and_set(book.get(), new_order):
                    logger.info(f"Added {order_type} order: {ticker_symbol}, {quantity} shares at ${price:.2f} (ID: {new_order.order_id})")
                    return new_order
            else:
                # Case 2: Find insertion point in our local copy
                for i in range(len(nodes) - 1):
                    current = nodes[i]
                    next_node = nodes[i + 1]
                    
                    if (is_buy and price > next_node.price) or (not is_buy and price < next_node.price):
                        # Re-verify the next pointer hasn't changed (get fresh copy)
                        actual_next = current.next.get()
                        
                        # If the structure changed, retry the whole operation
                        if actual_next != next_node:
                            break
                        
                        new_order.next.set(next_node)
                        if current.next.compare_and_set(next_node, new_order):
                            logger.info(f"Added {order_type} order: {ticker_symbol}, {quantity} shares at ${price:.2f} (ID: {new_order.order_id})")
                            return new_order
                        break
                
                # Case 3: Insert at the end
                if retries % 2 == 0 and len(nodes) > 0:  # Only try end insertion on even retries
                    last_node = nodes[-1]
                    if last_node.next.get() is None:  # Verify it's still the last node
                        new_order.next.set(None)
                        if last_node.next.compare_and_set(None, new_order):
                            logger.info(f"Added {order_type} order: {ticker_symbol}, {quantity} shares at ${price:.2f} (ID: {new_order.order_id})")
                            return new_order
            
            # Implement progressive backoff
            retries += 1
            backoff_time = 0.001 * (retries * 0.5)  # Progressively increase backoff
            if backoff_time > 0.1:  # Cap at 100ms
                backoff_time = 0.1
            time.sleep(backoff_time)
            
        except Exception as e:
            logger.error(f"Error adding order: {e}")
            retries += 1
            time.sleep(0.002 * retries)  # Progressive backoff on error
    
    # Last resort: Force insertion at the head
    if retries >= MAX_RETRIES:
        try:
            logger.warning(f"Using fallback insertion for {order_type} order for {ticker_symbol} after {retries} retries")
            current_head = book.get()
            new_order.next.set(current_head)
            
            # Try one last time with higher priority
            for final_try in range(5):  # 5 last attempts
                if book.compare_and_set(book.get(), new_order):
                    logger.info(f"Added {order_type} order using fallback method: {ticker_symbol}, {quantity} shares at ${price:.2f} (ID: {new_order.order_id})")
                    return new_order
                time.sleep(0.01)
                
            logger.error(f"Failed to add {order_type} order after {MAX_RETRIES} retries and fallback attempts")
        except Exception as e:
            logger.error(f"Error in fallback insertion: {e}")
    
    return None


def matchOrder():
    """ Matches buy and sell orders across all tickers """
    matches_count = 0
    
    # Iterate through all buckets in the tickers array
    for index in range(NUM_TICKERS):
        current_ticker_node = tickers[index]
        
        # Process each ticker in this bucket (handle hash collisions)
        while current_ticker_node is not None:
            ticker_symbol = current_ticker_node.ticker_symbol
            buy_book = current_ticker_node.buy_book
            sell_book = current_ticker_node.sell_book
            
            iterations = 0
            while iterations < MAX_MATCHING_ITERATIONS:
                # Get current heads atomically
                buy_head = buy_book.get()
                sell_head = sell_book.get()

                # If either book is empty or no match possible, break
                if buy_head is None or sell_head is None:
                    break
                
                if buy_head.price < sell_head.price:
                    break

                # Try to lock both order quantities
                try:
                    # Snapshot the quantities before locking
                    buy_qty_before = buy_head.quantity.value
                    sell_qty_before = sell_head.quantity.value
                    
                    # If either order has 0 quantity, remove it and continue
                    if buy_qty_before <= 0:
                        buy_book.compare_and_set(buy_head, buy_head.next.get())
                        continue
                    
                    if sell_qty_before <= 0:
                        sell_book.compare_and_set(sell_head, sell_head.next.get())
                        continue
                    
                    # Calculate matched quantity
                    matched_quantity = min(buy_qty_before, sell_qty_before)
                    
                    # Lock both quantities for atomic update
                    with buy_head.quantity.get_lock(), sell_head.quantity.get_lock():
                        # Double-check quantities haven't changed
                        if buy_head.quantity.value != buy_qty_before or sell_head.quantity.value != sell_qty_before:
                            # Quantity changed, retry
                            continue
                        
                        # Update quantities
                        buy_head.quantity.value -= matched_quantity
                        sell_head.quantity.value -= matched_quantity
                    
                    # Log the match
                    logger.info(f"MATCH: {matched_quantity} shares of {ticker_symbol} at ${sell_head.price:.2f} " +
                               f"(Buy ID: {buy_head.order_id}, Sell ID: {sell_head.order_id})")
                    
                    matches_count += 1
                    
                    # Remove orders with zero quantity
                    if buy_head.quantity.value <= 0:
                        buy_book.compare_and_set(buy_head, buy_head.next.get())
                    
                    if sell_head.quantity.value <= 0:
                        sell_book.compare_and_set(sell_head, sell_head.next.get())
                
                except Exception as e:
                    logger.error(f"Error during order matching: {e} for ticker {ticker_symbol}")
                    time.sleep(0.001)  # Backoff on error
                
                iterations += 1
                
                # Avoid CPU spinning too much
                if iterations % 100 == 0:
                    time.sleep(0.0001)
            
            if iterations >= MAX_MATCHING_ITERATIONS:
                logger.warning(f"Reached maximum iterations when matching orders for ticker {ticker_symbol}")
            
            # Move to next ticker in this bucket
            current_ticker_node = current_ticker_node.next
    
    return matches_count


def print_order_book(ticker_symbol):
    """Utility function to print the current state of an order book for debugging"""
    index = hash_ticker(ticker_symbol)
    
    # Find the ticker node in the bucket
    current = tickers[index]
    while current is not None:
        if current.ticker_symbol == ticker_symbol:
            break
        current = current.next
    
    if current is None:
        logger.info(f"Order book for {ticker_symbol} is empty")
        return
    
    buy_book = current.buy_book
    sell_book = current.sell_book
    
    # Print buy orders
    logger.info(f"BUY ORDERS for {ticker_symbol}:")
    current_order = buy_book.get()
    if current_order is None:
        logger.info("  No buy orders")
    else:
        while current_order:
            logger.info(f"  {current_order.quantity.value} shares at ${current_order.price:.2f} (ID: {current_order.order_id})")
            current_order = current_order.next.get()
    
    # Print sell orders
    logger.info(f"SELL ORDERS for {ticker_symbol}:")
    current_order = sell_book.get()
    if current_order is None:
        logger.info("  No sell orders")
    else:
        while current_order:
            logger.info(f"  {current_order.quantity.value} shares at ${current_order.price:.2f} (ID: {current_order.order_id})")
            current_order = current_order.next.get()


def add_test_orders():
    """Add test orders to verify matching functionality"""
    # Test case 1: Simple match
    addOrder("Buy", "TEST", 50, 150.0)
    addOrder("Sell", "TEST", 50, 149.0)
    
    # Test case 2: Partial match
    addOrder("Buy", "AAPL", 100, 200.0)
    addOrder("Sell", "AAPL", 50, 195.0)
    
    # Test case 3: Multiple matches
    addOrder("Buy", "GOOG", 200, 300.0)
    addOrder("Sell", "GOOG", 50, 290.0)
    addOrder("Sell", "GOOG", 50, 295.0)
    
    # Run matching
    matches = matchOrder()
    logger.info(f"Test matching completed with {matches} matches")


def simulate_trading(num_orders=1000, num_threads=4):
    """ Simulates stock trading with concurrent order execution """
    sample_tickers = ["AAPL", "GOOG", "TSLA", "MSFT", "AMZN", "META", "NFLX", "NVDA", "PYPL", "INTC"]
    start_time = time.time()
    
    total_matches = Value('i', 0)
    
    def trade_worker():
        local_matches = 0
        for _ in range(num_orders // num_threads):
            # Generate random order
            order_type = "Buy" if random.random() < 0.5 else "Sell"
            ticker = sample_tickers[random.randint(0, len(sample_tickers) - 1)]
            quantity = random.randint(1, 100)
            price = round(random.uniform(50, 500), 2)
            
            # Add order
            addOrder(order_type, ticker, quantity, price)
            
            # Match orders
            matches = matchOrder()
            if matches:
                local_matches += matches
            
            # Occasionally print order book (for debugging)
            if random.random() < 0.01:  # 1% chance
                print_order_book(ticker)
        
        # Update total matches counter
        with total_matches.get_lock():
            total_matches.value += local_matches

    threads = [threading.Thread(target=trade_worker) for _ in range(num_threads)]
    
    logger.info(f"Starting trading simulation with {num_orders} orders across {num_threads} threads")
    
    # Add some test orders first
    add_test_orders()
    
    for thread in threads:
        thread.start()
    
    for thread in threads:
        thread.join()

    end_time = time.time()
    duration = end_time - start_time
    
    logger.info(f"Trading simulation completed in {duration:.4f} seconds")
    logger.info(f"Total matches: {total_matches.value}")
    logger.info(f"Average throughput: {num_orders/duration:.2f} orders/second")


if __name__ == "__main__":
    simulate_trading(num_orders=1000, num_threads=8)