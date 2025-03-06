import threading
import random
import time
import logging

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
        self.quantity = quantity
        self.price = price
        self.next = None  # Pointer for linked list

class OrderBook:
    def __init__(self):
        self.head = None  # Head of the linked list
    
    def add_order(self, new_order, is_buy):
        """
        Insert orders in sorted order: 
        - Buy orders: Descending (Higher price first)
        - Sell orders: Ascending (Lower price first)
        """
        if self.head is None or (is_buy and self.head.price < new_order.price) or (not is_buy and self.head.price > new_order.price):
            new_order.next = self.head
            self.head = new_order
            logging.info(f"[ADD ORDER] {new_order.order_type} {new_order.quantity} {new_order.ticker} at ${new_order.price}")
            return
        
        current = self.head
        while current.next and ((is_buy and current.next.price >= new_order.price) or (not is_buy and current.next.price <= new_order.price)):
            current = current.next
        
        new_order.next = current.next
        current.next = new_order
        logging.info(f"[ADD ORDER] {new_order.order_type} {new_order.quantity} {new_order.ticker} at ${new_order.price}")
    
    def match_orders(self, other_book):
        """ Matches buy orders with sell orders """
        order_book_logger.info("\n[ORDER BOOK STATE BEFORE MATCH]")
        self.log_order_book("BUY BOOK")
        other_book.log_order_book("SELL BOOK")
        
        matched = False  # Track if any orders are matched
        while self.head and other_book.head and self.head.price >= other_book.head.price:
            matched_quantity = min(self.head.quantity, other_book.head.quantity)
            logging.info(f"[MATCH] {matched_quantity} shares of {self.head.ticker} matched at ${other_book.head.price}")
            
            self.head.quantity -= matched_quantity
            other_book.head.quantity -= matched_quantity
            matched = True
            
            if self.head.quantity == 0:
                self.head = self.head.next
            if other_book.head.quantity == 0:
                other_book.head = other_book.head.next
        
        order_book_logger.info("\n[ORDER BOOK STATE AFTER MATCH]")
        self.log_order_book("BUY BOOK")
        other_book.log_order_book("SELL BOOK")
        file_handler.flush()
        
        if not matched:
            order_book_logger.info("No matches found during this cycle.")
    
    def log_order_book(self, book_type):
        """Logs the state of the order book"""
        current = self.head
        orders = []
        while current:
            orders.append(f"{current.order_type} {current.quantity} {current.ticker} at ${current.price}")
            current = current.next
        
        if orders:
            order_book_logger.info(f"{book_type}:\n" + "\n".join(orders))
        else:
            order_book_logger.info(f"{book_type}: EMPTY")
        file_handler.flush()

class StockExchange:
    def __init__(self):
        self.tickers = [None] * 1024  # Fixed size array
        self.lock = threading.Lock()
    
    def get_or_create_books(self, ticker):
        index = hash(ticker) % 1024
        if self.tickers[index] is None:
            self.tickers[index] = (OrderBook(), OrderBook())  # (Buy Book, Sell Book)
        return self.tickers[index]
    
    def add_test_orders(self):
        """ Adds test orders to ensure matching works """
        buy_book, sell_book = self.get_or_create_books("TEST")
        buy_book.add_order(Order("Buy", "TEST", 50, 150.0), is_buy=True)
        sell_book.add_order(Order("Sell", "TEST", 50, 149.0), is_buy=False)
        buy_book.match_orders(sell_book)
    
    def simulate_trading(self, num_orders=100):
        tickers = ["AAPL", "GOOG", "TSLA", "MSFT", "AMZN"]
        
        for _ in range(num_orders):
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

if __name__ == "__main__":
    exchange = StockExchange()
    exchange.add_test_orders()  # Ensure matching occurs
    exchange.simulate_trading(num_orders=100)  # Run a limited number of orders