from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException, BinanceOrderException
import sys
from utils import find_min_delta
import logging
import time
from math import floor
from enum import Enum
import argparse
import os

logging.root.setLevel(logging.INFO)


def round_decimals_down(number: float, decimals: int = 2):
    """
    Returns a value rounded down to a specific number of decimal places.
    """
    factor = 10 ** decimals
    return floor(number * factor) / factor


class BaseClient():
    api_key: str
    api_secret: str
    client: Client
    order = None
    wait: int = 10
    quantity: float = 0
    quote_quantity: float = 0
    completed = False

    def __init__(self, symbol, wait=10):
        self.api_key = os.getenv("BINANCE_API_KEY")
        self.api_secret = os.getenv("BINANCE_API_SECRET")
        if not self.api_key or not self.api_secret:
            raise Exception(
                "BINANCE_API_KEY or BINANCE_API_SECRET cannot be read from the environment")
        self.client = Client(api_key=self.api_key, api_secret=self.api_secret)
        self.symbol = symbol
        self._init_symbol()
        self.wait = wait

    def _init_symbol(self):
        self.symbol_info = self.client.get_symbol_info(symbol=self.symbol)
        filtered_list = [f for f in self.symbol_info["filters"]
                         if f["filterType"] == "PRICE_FILTER"]
        if filtered_list and "tickSize" in filtered_list[0]:
            self.tick_size = float(filtered_list[0]["tickSize"])
        else:
            quote_precision = int(self.symbol_info["quotePrecision"])
            self.tick_size = float("0." + "0" * (quote_precision - 1) + "1")
        filtered_list = [f for f in self.symbol_info["filters"]
                         if f["filterType"] == "LOT_SIZE"]
        if filtered_list and "stepSize" in filtered_list[0]:
            self.step_size = float(filtered_list[0]["stepSize"])

    def fetch_order(self):
        if self.order:
            self.order = self.client.get_order(
                symbol=self.symbol, orderId=self.order["orderId"])
            if self.order["status"] == Client.ORDER_STATUS_FILLED:
                logging.info(f"Order completed. Order: {self.order}")
                if self.order["side"] == Client.SIDE_SELL:
                    self.quote_quantity = float(
                        self.order["cummulativeQuoteQty"])
                    self.quantity -= float(self.order["executedQty"])
                elif self.order["side"] == Client.SIDE_BUY:
                    self.quote_quantity -= float(
                        self.order["cummulativeQuoteQty"])
                    self.quantity += float(self.order["executedQty"])
            elif self.order["status"] == Client.ORDER_STATUS_EXPIRED:
                logging.info(f"Order expired. Order: {self.order}")
            elif self.order["status"] == Client.ORDER_STATUS_PARTIALLY_FILLED:
                logging.info(
                    f"Order partially filled. Waiting for fulfilment. Status: {self.order['executedQty']}/{self.order['origQty']}")

    def cancel_order(self):
        if self.order:
            self.client.cancel_order(
                symbol=self.symbol, orderId=self.order["orderId"])
            logging.info(f"Order {self.order['orderId']} canceled.")
        self.order = None

    def get_orderbook(self):
        return self.client.get_order_book(symbol=self.symbol, limit=5)

    def execute(self):
        pass

    def log_start(self):
        pass

    def start(self):
        self.log_start()
        try:
            while not self.completed:
                self.execute()
                time.sleep(self.wait)
        except (BinanceAPIException, BinanceRequestException, BinanceOrderException) as e:
            logging.exception(e)


class AutoSellClient(BaseClient):
    minask: float
    oco_sell: bool = False
    sell_stop_price: float
    sell_stop_limit: float
    sell_order_list: dict

    def __init__(self, symbol, quantity, minask, sell_stop_price=None, sell_stop_limit=None, wait=10):
        super().__init__(symbol, wait)
        self.quantity = quantity
        self.minask = minask
        self.quote_quantity = 0.0
        if sell_stop_price and sell_stop_limit:
            self.oco_sell = True
            self.sell_stop_price = sell_stop_price
            self.sell_stop_limit = sell_stop_limit

    def execute(self):
        self.fetch_order()
        if self.order:
            if self.order["status"] in [Client.ORDER_STATUS_FILLED, Client.ORDER_STATUS_EXPIRED]:
                self.completed = True
                return
            elif self.order["status"] == Client.ORDER_STATUS_PARTIALLY_FILLED:
                return
        self.orderbook_sell()

    def log_start(self):
        logging.info(
            f"Auto selling {self.symbol} with min ask: {self.minask}, quantity: {self.quantity} {self.symbol_info['baseAsset']}")
        if self.oco_sell:
            logging.info(
                f"stop price: {self.sell_stop_price}, stop_limit: {self.sell_stop_limit}")

    def orderbook_sell(self):
        asks = self.get_orderbook()["asks"]
        current_best_price = float(asks[0][0])
        if self.order:
            current_order_price = float(self.order["price"])
            if current_order_price == self.minask:
                logging.debug(
                    f"Ask price is the min ask price. No need for update. Ask price: {current_order_price}")
                return
            elif current_best_price == current_order_price:
                current_best_qty = float(asks[0][1])
                order_qty = round(
                    float(self.order["origQty"]) - float(self.order["executedQty"]), 8)
                second_best_price = float(asks[1][0])
                next_ask_diff = round(
                    second_best_price - current_best_price, 8)
                if current_best_qty != order_qty or next_ask_diff <= self.tick_size:
                    logging.debug(
                        f"Ask price is the best ask price. No need for update. Ask price: {current_order_price}")
                    return
            self.cancel_order()

        new_ask = current_best_price - self.tick_size
        new_ask = round(new_ask, 8)
        if new_ask < self.minask:
            new_ask = self.minask
        self._sell_order(new_ask)

    def _sell_order(self, price):
        if self.oco_sell:
            self.sell_order_list = self.client.order_oco_sell(
                symbol=self.symbol,
                quantity=self.quantity,
                price=str(price),
                stopPrice=str(self.sell_stop_price),
                stopLimitPrice=str(self.sell_stop_limit),
                stopLimitTimeInForce="GTC"
            )
            self.order = [
                o for o in self.sell_order_list["orderReports"]
                if o["type"] in ["LIMIT", "LIMIT_MAKER"]][0]
        else:
            self.order = self.client.order_limit_sell(
                symbol=self.symbol, quantity=self.quantity, price=str(price))
        logging.info(
            f"Placed a new order for {self.symbol}. quantity: {self.quantity}, Price: {price}")


class AutoBuyClient(BaseClient):
    client: Client
    minask: float
    quantity_to_buy: float = 0
    oco_buy: bool = False
    buy_stop_price: float
    buy_stop_limit: float
    buy_order_list: str

    def __init__(self, symbol, quantity, maxbid, buy_stop_price=None, buy_stop_limit=None, wait=10):
        super().__init__(symbol, wait)
        self.quantity_to_buy = quantity
        self.maxbid = maxbid
        if buy_stop_price and buy_stop_limit:
            self.oco_buy = True
            self.buy_stop_price = buy_stop_price
            self.buy_stop_limit = buy_stop_limit

    def execute(self):
        self.fetch_order()
        if self.order:
            if self.order["status"] in [Client.ORDER_STATUS_FILLED, Client.ORDER_STATUS_EXPIRED]:
                self.completed = True
                return
            elif self.order["status"] == Client.ORDER_STATUS_PARTIALLY_FILLED:
                return
        self.orderbook_buy()

    def log_start(self):
        logging.info(
            f"Auto buying with max bid: {self.maxbid}, quote quantity: {self.quantity_to_buy}")
        if self.oco_buy:
            logging.info(
                f"stop price: {self.buy_stop_price}, stop_limit: {self.buy_stop_limit}")

    def orderbook_buy(self):
        bids = self.get_orderbook()["bids"]
        current_best_price = float(bids[0][0])
        if self.order:
            current_order_price = float(self.order["price"])
            if current_order_price == self.maxbid:
                logging.debug(
                    f"Bid price is the max bid price. No need for update. Bid price: {current_order_price}")
                return
            elif current_best_price == current_order_price:
                current_best_qty = float(bids[0][1])
                order_qty = round(
                    float(self.order["origQty"]) - float(self.order["executedQty"]), 8)
                second_best_price = float(bids[1][0])
                next_bid_diff = round(
                    second_best_price - current_best_price, 8)
                if current_best_qty != order_qty or next_bid_diff <= self.tick_size:
                    logging.debug(
                        f"Ask price is the best ask price. No need for update. Ask price: {current_order_price}")
                    return
            self.cancel_order()

        new_bid = current_best_price + self.tick_size
        new_bid = round(new_bid, 8)
        if new_bid > self.maxbid:
            new_bid = self.maxbid

        self._buy_order(new_bid)

    def _buy_order(self, price):
        if self.quantity_to_buy > 0:
            quantity = self.quantity_to_buy
        elif self.quote_quantity:
            quantity = self.quote_quantity / price
            quantity -= quantity % self.step_size
        else:
            raise Exception(
                "Either quantity_to_buy or quote_quantity should be > 0")
        if self.oco_buy:
            self.sell_order_list = self.client.order_oco_sell(
                symbol=self.symbol,
                quantity=quantity,
                price=str(price),
                stopPrice=str(self.buy_stop_price),
                stopLimitPrice=str(self.buy_stop_limit),
                stopLimitTimeInForce="GTC"
            )
            self.order = [
                o for o in self.sell_order_list["orderReports"]
                if o["type"] in ["LIMIT", "LIMIT_MAKER"]][0]
        else:
            self.order = self.client.order_limit_buy(
                symbol=self.symbol, quantity=quantity, price=str(price))
        logging.info(
            f"Placed a new order for {self.symbol}. quantity: {quantity}, Price: {price}")


class AutoTradeClient(AutoBuyClient, AutoSellClient):
    side: str

    def __init__(self, symbol, side, quantity, minask, maxbid, sell_stop_price=None, sell_stop_limit=None, buy_stop_price=None, buy_stop_limit=None, wait=10):
        self.side = side.lower()
        if self.side not in ['buy', "sell"]:
            raise Exception("side should be one of [buy, sell]")
        # super(AutoSellClient, self).__init__(symbol, wait)
        BaseClient.__init__(self,  symbol, wait)
        if side == "buy":
            self.quantity_to_buy = quantity
        else:
            self.quantity = quantity
        self.minask = minask
        self.maxbid = maxbid
        self.buy_stop_price = buy_stop_price
        self.buy_stop_limit = buy_stop_limit
        self.sell_stop_price = sell_stop_price
        self.sell_stop_limit = sell_stop_limit

    def execute(self):
        self.fetch_order()
        if self.order:
            if self.order["status"] == Client.ORDER_STATUS_EXPIRED:
                self.completed = True
                return
            elif self.order["status"] == Client.ORDER_STATUS_PARTIALLY_FILLED:
                return
            elif self.order["status"] == Client.ORDER_STATUS_FILLED:
                self.order = None
                self.side = "buy" if self.side == "sell" else "sell"
        if self.side == "sell":
            self.orderbook_sell()
        else:
            self.orderbook_buy()

    def log_start(self):
        logging.info(
            f"Auto trading {self.symbol} with quantity: {max(self.quantity, self.quantity_to_buy)}, side: {self.side}, min ask: {self.minask}, maxbid: {self.maxbid}")
        if self.oco_buy:
            logging.info(
                f"buy stop price: {self.buy_stop_price}, buy stop limit: {self.buy_stop_limit}")
        if self.oco_sell:
            logging.info(
                f"sell stop price: {self.sell_stop_price}, sell stop limit: {self.sell_stop_limit}")


def configure_args(args):
    args.pop("func")
    if "wait" in args and not args["wait"]:
        args.pop("wait")
    if "sell_stop" in args:
        sell_stop = args.pop("sell_stop")
        if sell_stop:
            args["sell_stop_price"] = sell_stop[0]
            args["sell_stop_limit"] = sell_stop[1]
    if "buy_stop" in args:
        buy_stop = args.pop("buy_stop")
        if buy_stop:
            args["buy_stop_price"] = buy_stop[0]
            args["buy_stop_limit"] = buy_stop[1]
    return args


def sell(args):
    sell_client = AutoSellClient(**args)
    sell_client.start()


def buy(args):
    buy_client = AutoBuyClient(**args)
    buy_client.start()


def trade(args):
    trade_client = AutoTradeClient(**args)
    trade_client.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="follow_orderbook",
        description="A trade bot that follows the orderbook and places the best order according to given limits.")
    parser.add_argument("--wait", type=int, default=10,
                        help="number of seconds between checks. Default 10.")
    subparsers = parser.add_subparsers(help="operation types")

    sell_parser = subparsers.add_parser(
        "sell", help="place a sell order and exit once the order is executed or expired.")
    sell_parser.add_argument(
        "symbol", help="symbol to be traded (e.g. BTCUSDT)")
    sell_parser.add_argument("quantity", type=float,
                             help="quantity of the base asset to sell")
    sell_parser.add_argument("minask", type=float,
                             help="minimum ask price for sell operation")
    sell_parser.add_argument("--sell-stop", type=float, nargs=2,
                             metavar=("trigger",
                                      "limit"),
                             help="place an OCO sell order instead of limit order with the given stop and limit prices")
    sell_parser.set_defaults(func=sell)

    buy_parser = subparsers.add_parser(
        "buy", help="place a buy order and exit once the order is executed or expired.")
    buy_parser.add_argument(
        "symbol", help="symbol to be traded (e.g. BTCUSDT)")
    buy_parser.add_argument("quantity", type=float,
                            help="quantity of the base asset to buy")
    buy_parser.add_argument("maxbid", type=float,
                            help="minimum ask price for sell operation")
    buy_parser.add_argument("--buy-stop", type=float, nargs=2,
                            metavar=("trigger",
                                     "limit"),
                            help="place an OCO buy order instead of limit order with the given stop and limit prices")
    buy_parser.set_defaults(func=buy)

    trade_parser = subparsers.add_parser(
        "trade", help="place buy and sell orders in turn until one of the orders expires or the program exits.")
    trade_parser.add_argument(
        "symbol", help="symbol to be traded (e.g. BTCUSDT)")
    trade_parser.add_argument("side", choices=["buy", "sell"],
                              help="first operation of the trade")
    trade_parser.add_argument("quantity", type=float,
                              help="quantity of the base asset to buy")
    trade_parser.add_argument("maxbid", type=float,
                              help="maximum bid price for buy operation")
    trade_parser.add_argument("minask", type=float,
                              help="minimum ask price for sell operation")
    trade_parser.add_argument("--sell-stop", type=float, nargs=2,
                              metavar=("trigger",
                                       "limit"),
                              help="place OCO sell order instead of limit order with the given stop and limit prices")
    trade_parser.add_argument("--buy-stop", type=float, nargs=2,
                              metavar=("trigger",
                                       "limit"),
                              help="place OCO buy order instead of limit order with the given stop and limit prices")
    trade_parser.set_defaults(func=trade)

    args = parser.parse_args()
    print(args)
    args.func(configure_args(vars(args)))
