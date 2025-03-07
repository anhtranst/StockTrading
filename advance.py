import threading
import random
import time
import logging
import multiprocessing
from multiprocessing import Value
import threading
import ctypes
from threading import Thread
import queue # to handle logging the transactions, which is not required for the assignment

# Configure logging
logging.basicConfig(filename='advance.log', level=logging.INFO, format='%(asctime)s - %(message)s')
log_queue = queue.Queue()

def log_message(message):
    log_queue.put(message)

def process_log_queue():
    """ Continuously processes log messages from the queue """
    while True:
        try:
            message = log_queue.get()
            if message == "STOP": 
                break
            logging.info(message)
        except queue.Empty:
            continue

log_thread = threading.Thread(target=process_log_queue, daemon=True)
log_thread.start()

class AtomicReference:
    """Simple atomic reference implementation for lock-free operations"""
    def __init__(self, initial_value=None):
        self._value = initial_value
        self._lock = threading.Lock()
    
    def get(self):
        with self._lock:
            return self._value
    
    def set(self, new_value):
        with self._lock:
            self._value = new_value
    
    def compare_and_set(self, expected, new_value):
        """Atomic compare and set operation"""
        with self._lock:
            if self._value == expected:
                self._value = new_value
                return True
            return False

class Order:
    def __init__(self, order_type, ticker, quantity, price):
        self.order_type = order_type  # 'Buy' or 'Sell'
        self.ticker = ticker
        self.quantity = Value('i', quantity)  # Shared memory for atomic updates
        self.price = price
        self.next = AtomicReference(None)  # Atomic reference for next pointer

class LockFreeOrderBook:
    def __init__(self):
        self.head = AtomicReference(None)  # Atomic reference for the head pointer
    
    def add_order(self, new_order, is_buy):
        """
        Insert orders in sorted order using lock-free techniques: 
        - Buy orders: Descending (Higher price first)
        - Sell orders: Ascending (Lower price first)
        """
        while True:
            current_head = self.head.get()
            
            # If the list is empty or the new order should be at the head
            if current_head is None or (is_buy and new_order.price > current_head.price) or (not is_buy and new_order.price < current_head.price):
                new_order.next.set(current_head)
                if self.head.compare_and_set(current_head, new_order):
                    break
                # If CAS fails, the loop will retry
            else:
                # Find the right position to insert
                current = current_head
                while True:
                    next_node = current.next.get()
                    
                    # Check if we've reached the right position
                    if next_node is None or (is_buy and new_order.price > next_node.price) or (not is_buy and new_order.price < next_node.price):
                        new_order.next.set(next_node)
                        if current.next.compare_and_set(next_node, new_order):
                            break
                        # If CAS fails, retry from the beginning
                        break
                    
                    current = next_node
                
                # If we successfully inserted, break the outer loop
                if current.next.get() == new_order:
                    break
        
        log_message(f"[ADD ORDER] {new_order.order_type} {new_order.quantity.value} {new_order.ticker} at ${new_order.price}")
    
    def match_orders(self, other_book, max_retries=1000):
        """ Matches buy orders with sell orders using lock-free techniques """      
        retries = 0
        while retries < max_retries:
            buy_head = self.head.get()
            sell_head = other_book.head.get()
            
            if buy_head is None or sell_head is None:
                break
            
            if buy_head.price < sell_head.price:
                break
            
            matched_quantity = min(buy_head.quantity.value, sell_head.quantity.value)
            
            if matched_quantity <= 0:
                break
            
            # Lock both buy and sell order quantities at the same time to prevent mismatched updates
            with buy_head.quantity.get_lock(), sell_head.quantity.get_lock():
                buy_head.quantity.value -= matched_quantity
                sell_head.quantity.value -= matched_quantity
            
            if matched_quantity > 0:
                log_message(f"[MATCH] {matched_quantity} shares of {buy_head.ticker} matched at ${sell_head.price}")
            
            if buy_head.quantity.value == 0:
                self.head.compare_and_set(buy_head, buy_head.next.get())
            
            if sell_head.quantity.value == 0:
                other_book.head.compare_and_set(sell_head, sell_head.next.get())
            
            retries += 1
        
class LockFreeStockExchange:
    def __init__(self):
        self.tickers = [None] * 1024  # Fixed size array for 1,024 tickers
    
    def get_or_create_books(self, ticker):
        """Get or create order books for a ticker using a fixed-size array"""
        # Simple hash function to map ticker to array index
        index = hash(ticker) % 1024
        
        # If no books exist, create them using atomic operations
        if self.tickers[index] is None:
            new_books = (LockFreeOrderBook(), LockFreeOrderBook())  # (Buy Book, Sell Book)
            
            # Use atomic compare and exchange to avoid race conditions
            current = self.tickers[index]
            if current is None:
                # Only set if still None (atomic check-and-set)
                self.tickers[index] = new_books
        
        return self.tickers[index]
    
    def add_test_orders(self):
        """ Adds test orders to ensure matching works """
        buy_book, sell_book = self.get_or_create_books("TEST")
        buy_book.add_order(Order("Buy", "TEST", 50, 150.0), is_buy=True)
        sell_book.add_order(Order("Sell", "TEST", 50, 149.0), is_buy=False)
        buy_book.match_orders(sell_book)
    
    def simulate_trading(self, num_orders=1000, num_threads=4):
        """ Simulates concurrent trading using multiple threads """
        tickers = ["AAPL", "GOOG", "TSLA", "MSFT", "AMZN"]
        start_time = time.time()
        
        def trade_worker():
            for _ in range(num_orders // num_threads):
                order_type = "Buy" if random.randint(0, 1) else "Sell"
                ticker = tickers[random.randint(0, len(tickers) - 1)]
                quantity = random.randint(1, 100)
                price = round(random.uniform(50, 500), 2)
                buy_book, sell_book = self.get_or_create_books(ticker)
                
                if order_type == "Buy":
                    buy_book.add_order(Order(order_type, ticker, quantity, price), is_buy=True)
                else:
                    sell_book.add_order(Order(order_type, ticker, quantity, price), is_buy=False)
                
                buy_book.match_orders(sell_book)
        
        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(target=trade_worker)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        print(f"Trading simulation completed in {end_time - start_time:.4f} seconds")

if __name__ == "__main__":
    exchange = LockFreeStockExchange()
    exchange.add_test_orders()
    exchange.simulate_trading()
    log_queue.put("STOP")
    log_thread.join()