# binance-trade-bot
*Disclaimer*: These scripts have not been tested properly. Use with caution. I may not be held responsible for any financial lost as a concequence of using these scripts.

Simple Python scripts for auto-trading.

## Installation
Requires Python >= 3.7

```sh
pip install -r requirements.txt
```

## Configuration

Binance API Key and API Secret are required to trade on Binance. Make sure the API Key has the necessary permissions to trade. Set your API Key and Secret to the environment.

```sh
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
```

## follow_orderbook

follow_orderbook script performs sell or buy operation based on a limit and the status of the orderbook. Main purpose of this script is to stay on top of the orderbook. It keeps checking the orderbook and updates your order if it finds a better price on the orderbook. You can give a single sell or a single buy command as well as a trade command which keeps selling and buying based on the min ask and max bid prices you define.

For a sell operation, it always gives the best ask price on the orderbook which is higher than or equal to the min ask price you define. If the best ask on the orderbook goes below the min ask price you define it keeps the order with the min ask price.

For a buy operation, it always gives the best bid price on the orderbook which is lower than or equal to the max bid price you define. If the best bid on the orderbook goes above the max bid price you define it keeps the order with the max bid price.

A trade operation is nothing but switching between a sell and a buy operation based on the min ask and the max bid prices you define. It does not switch to the next operation without fully completing the current one.

Each order is given as a limit order or an OCO (one cancels the other) order. An OCO order is a limit order and a stop-limit order given together. Whichever executed first, it cancels the other. If the price reaches the limit price first the limit order will be executed and stop-limit order will be cancelled. Or vice versa if the price reaches the stop price first.

### Usage

**Main:**

```sh
usage: follow_orderbook [-h] [--wait WAIT] {sell,buy,trade} ...

A trade bot that follows the orderbook and places the best order according to given limits.

positional arguments:
  {sell,buy,trade}  operation types
    sell            place a sell order and exit once the order is executed or expired.
    buy             place a buy order and exit once the order is executed or expired.
    trade           place buy and sell orders in turn until one of the orders expires or the program exits.

optional arguments:
  -h, --help        show this help message and exit
  --wait WAIT       number of seconds between checks. Default 10.
```

**Sell:**

```sh
usage: follow_orderbook sell [-h] [--sell-stop trigger limit] symbol quantity minask

positional arguments:
  symbol                symbol to be traded (e.g. BTCUSDT)
  quantity              quantity of the base asset to sell
  minask                minimum ask price for sell operation

optional arguments:
  -h, --help            show this help message and exit
  --sell-stop trigger limit
                        place an OCO sell order instead of limit order with the given stop and limit prices
```

**Buy:**

```sh
usage: follow_orderbook buy [-h] [--buy-stop trigger limit] symbol quantity maxbid

positional arguments:
  symbol                symbol to be traded (e.g. BTCUSDT)
  quantity              quantity of the base asset to buy
  maxbid                minimum ask price for sell operation

optional arguments:
  -h, --help            show this help message and exit
  --buy-stop trigger limit
                        place an OCO buy order instead of limit order with the given stop and limit prices
```

**Trade:**

```sh
usage: follow_orderbook trade [-h] [--sell-stop trigger limit] [--buy-stop trigger limit] symbol {buy,sell} quantity maxbid minask

positional arguments:
  symbol                symbol to be traded (e.g. BTCUSDT)
  {buy,sell}            first operation of the trade
  quantity              quantity of the base asset to buy
  maxbid                maximum bid price for buy operation
  minask                minimum ask price for sell operation

optional arguments:
  -h, --help            show this help message and exit
  --sell-stop trigger limit
                        place OCO sell order instead of limit order with the given stop and limit prices
  --buy-stop trigger limit
                        place OCO buy order instead of limit order with the given stop and limit prices
```