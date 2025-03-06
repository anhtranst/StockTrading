import threading
import random
import time
import logging
import multiprocessing
from multiprocessing import Value

# Configure logging
logging.basicConfig(filename='trading_log.txt', level=logging.INFO, format='%(asctime)s - %(message)s')
order_book_logger = logging.getLogger("order_book")
order_book_logger.setLevel(logging.INFO)
file_handler = logging.FileHandler("order_book_log.txt", mode='w')  # Overwrite on each run
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
order_book_logger.addHandler(file_handler)

class Order:
    def __init__(self, order_type, ticker, quantity, price):
        self.order_type = order_type  # 'Buy' or 'Sell'
        self.ticker = ticker
        self.quantity = Value('i', quantity)  # Shared memory for atomic updates
        self.price = price
        self.next = None  # Pointer for linked list

class LockFreeOrderBook:
    def __init__(self):
        self.head = None  # Head of the linked list
    
    def add_order(self, new_order, is_buy):
        """
        Insert orders in sorted order: 
        - Buy orders: Descending (Higher price first)
        - Sell orders: Ascending (Lower price first)
        """
        while True:
            current = self.head
            prev = None
            
            while current and ((is_buy and current.price >= new_order.price) or (not is_buy and current.price <= new_order.price)):
                prev = current
                current = current.next
            
            new_order.next = current
            
            if prev is None:
                if self.head is current:
                    self.head = new_order
                    break
            else:
                if prev.next is current:
                    prev.next = new_order
                    break
        
        logging.info(f"[ADD ORDER] {new_order.order_type} {new_order.quantity.value} {new_order.ticker} at ${new_order.price}")
    
    def match_orders(self, other_book):
        """ Matches buy orders with sell orders """
        order_book_logger.info("\n[ORDER BOOK STATE BEFORE MATCH]")
        self.log_order_book("BUY BOOK")
        other_book.log_order_book("SELL BOOK")
        
        while self.head and other_book.head and self.head.price >= other_book.head.price:
            if self.head is None or other_book.head is None:
                break  # Prevent race condition
            
            matched_quantity = min(self.head.quantity.value, other_book.head.quantity.value)
            logging.info(f"[MATCH] {matched_quantity} shares of {self.head.ticker} matched at ${other_book.head.price}")
            
            if matched_quantity > 0:
                with self.head.quantity.get_lock():
                    self.head.quantity.value -= matched_quantity
                with other_book.head.quantity.get_lock():
                    other_book.head.quantity.value -= matched_quantity
            
            if self.head.quantity.value == 0:
                self.head = self.head.next if self.head else None
            if other_book.head.quantity.value == 0:
                other_book.head = other_book.head.next if other_book.head else None
        
        order_book_logger.info("\n[ORDER BOOK STATE AFTER MATCH]")
        self.log_order_book("BUY BOOK")
        other_book.log_order_book("SELL BOOK")
        file_handler.flush()
    
    def log_order_book(self, book_type):
        """Logs the state of the order book"""
        current = self.head
        orders = []
        while current:
            orders.append(f"{current.order_type} {current.quantity.value} {current.ticker} at ${current.price}")
            current = current.next
        
        if orders:
            order_book_logger.info(f"{book_type}:\n" + "\n".join(orders))
        else:
            order_book_logger.info(f"{book_type}: EMPTY")
        file_handler.flush()

class LockFreeStockExchange:
    def __init__(self):
        self.tickers = [None] * 1024  # Fixed size array
    
    def get_or_create_books(self, ticker):
        index = hash(ticker) % 1024
        if self.tickers[index] is None:
            self.tickers[index] = (LockFreeOrderBook(), LockFreeOrderBook())  # (Buy Book, Sell Book)
        return self.tickers[index]
    
    def add_test_orders(self):
        """ Adds test orders to ensure matching works """
        buy_book, sell_book = self.get_or_create_books("TEST")
        buy_book.add_order(Order("Buy", "TEST", 50, 150.0), is_buy=True)
        sell_book.add_order(Order("Sell", "TEST", 50, 149.0), is_buy=False)
        buy_book.match_orders(sell_book)
    
    def simulate_trading(self, num_orders=100, num_threads=4):
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
    exchange.add_test_orders()  # Ensure matching occurs
    exchange.simulate_trading(num_orders=1000, num_threads=8)  # Run multi-threaded test
