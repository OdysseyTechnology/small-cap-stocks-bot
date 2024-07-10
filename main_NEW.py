import math
import multiprocessing
import traceback

from multiprocessing import Pool
import os
import sys

import requests
from googleapiclient.discovery import build

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.errors import HttpError

from config import config
import time

import pandas as pd
import pandas_ta as ta

import asyncio
import websockets

dataframe = pd.DataFrame()

dataframe.ta.indicators()

SPREADSHEET_ID = config.GOOGLE_SPREADSHEET_ID
RANGE_NAME = config.GOOGLE_RANGE_NAME
API_KEY = config.GOOGLE_API_KEY

TRADIER_SANDBOX_ACCOUNT_ID = config.TRADIER_SANDBOX_ACCOUNT_ID
TRADIER_SANDBOX_ACCESS_TOKEN = config.TRADIER_SANDBOX_ACCESS_TOKEN

# POLYGON_API_KEY = config.POLYGONIO_API_KEY

'''
Using only 1 and 5 minute candles 
'''


class stratMainWIthMP:
    '''
    anything we need to do once... put here
    '''

    def __init__(self):

        print('inside constructor')

    def authenticate_google_sheets(self, api_key):
        return build('sheets', 'v4', developerKey=api_key).spreadsheets()

    def get_google_sheet(self):
        sheets = self.authenticate_google_sheets(API_KEY)
        result = sheets.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME,
                                     valueRenderOption='UNFORMATTED_VALUE').execute()
        values = result.get('values', [])

        self.validate_google_sheet_data(values)

        return values

    def authenticate_write_to_google_sheet(self):
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

        creds = None

        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(creds.to_json())

        return creds

    def write_to_google_sheet(self, column, price, row_type):
        creds = self.authenticate_write_to_google_sheet()

        try:
            service = build("sheets", "v4", credentials=creds)
            sheet = service.spreadsheets()

            if row_type == 'entry':
                sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=f'Sheet1!{column}7',
                                      valueInputOption="USER_ENTERED",
                                      body={'values': [[price]]}).execute()  # as of now, row 7 is for entries
            elif row_type == 'exit':
                sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=f'Sheet1!{column}8',
                                      valueInputOption="USER_ENTERED",
                                      body={'values': [[price]]}).execute()  # as of now, row 8 is for exits
        except HttpError as e:
            print(e)

    def validate_google_sheet_data(self, values):

        # validate that inputted tickers are valid for the exchange
        for index in range(1, len(values[0])):  # begin iterations from 1st index
            ticker = values[0][index]

            # https://documentation.tradier.com/brokerage-api/reference/exchanges
            response = requests.get('https://sandbox.tradier.com/v1/markets/lookup',
                                    params={'q': f'{ticker}', 'exchanges': 'Q,N', 'types': 'stock'},
                                    headers={'Authorization': 'Bearer wQ4YYAiuU0n8ryvrZGzWucnTS9Tt',
                                             'Accept': 'application/json'}
                                    )

            json_response = response.json()

            if json_response == {'securities': None}:  # if ticker is not valid, kill script (at this time)
                # maybe just remove the entire row with invalid input?
                print(f'no securities found for {ticker}')
                # sys.exit(0) #TODO comment out when building code.

    def get_available_balance(self):
        response = requests.get(f'https://sandbox.tradier.com/v1/accounts/{TRADIER_SANDBOX_ACCOUNT_ID}/balances',
                                params={},
                                headers={'Authorization': 'Bearer wQ4YYAiuU0n8ryvrZGzWucnTS9Tt',
                                         'Accept': 'application/json'}
                                )
        json_response = response.json()
        return json_response['balances']['total_cash']

    def get_intervals_without_set_time(self, symbol, interval):
        response = requests.get('https://sandbox.tradier.com/v1/markets/timesales',
                                params={'symbol': f'{symbol}', 'interval': f'{interval}'},
                                headers={'Authorization': 'Bearer wQ4YYAiuU0n8ryvrZGzWucnTS9Tt',
                                         'Accept': 'application/json'}
                                )
        json_response = response.json()
        return json_response

    def place_limit_sell_order(self, symbol, price, quantity):
        print('inside place_limit_sell_order function')
        response = requests.post(f'https://sandbox.tradier.com/v1/accounts/{TRADIER_SANDBOX_ACCOUNT_ID}/orders',
                                 data={'class': 'equity', 'symbol': f'{symbol}', 'side': 'sell',
                                       'quantity': f'{quantity}', 'type': 'limit',
                                       'duration': 'day', 'price': f'{price}', 'tag': 'my-tag-example-5'},
                                 headers={'Authorization': 'Bearer wQ4YYAiuU0n8ryvrZGzWucnTS9Tt',
                                          'Accept': 'application/json'}
                                 )
        json_response = response.json()
        return json_response

    def place_limit_buy_order(self, symbol, side, price, quantity):
        response = requests.post(f'https://sandbox.tradier.com/v1/accounts/{TRADIER_SANDBOX_ACCOUNT_ID}/orders',
                                 data={'class': 'equity', 'symbol': f'{symbol}', 'side': f'{side}',
                                       'quantity': f'{quantity}', 'type': 'limit',
                                       'duration': 'day', 'price': f'{price}', 'tag': 'my-tag-example'},
                                 headers={'Authorization': 'Bearer wQ4YYAiuU0n8ryvrZGzWucnTS9Tt',
                                          'Accept': 'application/json'}
                                 )
        json_response = response.json()
        return json_response

    def get_positions(self):  # just a function to test this endpoint... commenting out
        response = requests.get(f'https://sandbox.tradier.com/v1/accounts/{TRADIER_SANDBOX_ACCOUNT_ID}/positions',
                                params={},
                                headers={'Authorization': 'Bearer wQ4YYAiuU0n8ryvrZGzWucnTS9Tt',
                                         'Accept': 'application/json'}
                                )
        json_response = response.json()
        return json_response

    def is_position_open_for_current_ticker(self, ticker, open_positions):
        # NOTE: "ticker" is coming in as a list, not str
        # TODO: should we just bypass this function if we have no open positions? Instead of catching the error...

        try:
            for position in list(open_positions.values())[0]:
                print(f'checking for {ticker[0]} inside position {position}')

                if ticker[0] in position['symbol']:
                    print(f'FOUND {ticker} in position {position}')
                    return True
            return False
        except AttributeError as e:
            print('\nCaught AttributeError inside is_position_open_for_current_ticker():', e,
                  '--- Do we have no positions open?')
        except Exception as e:
            print('\nCaught generic Exception inside is_position_open_for_current_ticker():', e)

    def get_orders(self):  # get open orders
        response = requests.get(f'https://sandbox.tradier.com/v1/accounts/{TRADIER_SANDBOX_ACCOUNT_ID}/orders',
                                params={},
                                headers={'Authorization': 'Bearer wQ4YYAiuU0n8ryvrZGzWucnTS9Tt',
                                         'Accept': 'application/json'}
                                )
        json_response = response.json()
        return json_response

    def get_stock_quote(self, symbol):  # testing this endpoint...
        response = requests.get('https://sandbox.tradier.com/v1/markets/quotes',
                                # params={'symbols': 'AAPL,VXX190517P00016000', 'greeks': 'false'},
                                params={'symbols': f'{symbol}', 'greeks': 'false'},
                                headers={'Authorization': 'Bearer wQ4YYAiuU0n8ryvrZGzWucnTS9Tt',
                                         'Accept': 'application/json'}
                                )
        json_response = response.json()
        print('status code is', response.status_code)
        return json_response

    def buy_stock(self, google_sheet, stock_ticker):

        print(f'\n**BUY LOGIC for {stock_ticker}**\n')

        '''
            Thread specific setup
        '''

        stock_index: int = 0  # default to 0

        tickers = google_sheet[0][1:]
        entries = google_sheet[6][1:]
        dollar_amount = google_sheet[1][1:]
        break_levels = google_sheet[5][1:]  # "break_level" in the Sheet
        amount = google_sheet[1][1:]
        min_targets = google_sheet[2][1:]
        # max_targets = sheet[3][1:]
        prices = google_sheet[4][1:]

        for index in range(len(tickers)):
            if tickers[index] == stock_ticker:
                stock_index = index
                break

        # -----------------------------END THREAD SETUP--------------------------------------------------------------

        one_min_intervals_dict = {}  # preferably use dict over list?

        '''
            BUY LOGIC
            - When the bot sees GREEN CANDLE (close > open) for a ticker close above break level for that ticker 
        '''
        if entries[stock_index] == '.':
            print(
                f'\n**MONITORING INSIDE BUY** getting one minute intervals for ticker {tickers[stock_index]} in the sheet')
            one_min_interval = self.get_intervals_without_set_time(tickers[stock_index], '1min')

            one_min_intervals_dict[
                f'{tickers[stock_index]}'] = one_min_interval

            # after getting current one min candle... now validate close > open (green candle validation)
            intervals = one_min_intervals_dict[tickers[stock_index]]['series']['data']
            last_open_value = intervals[len(intervals) - 1]['open']
            last_close_value = intervals[len(intervals) - 1]['close']

            '''
                BUY LOGIC 1
                - When the bot sees GREEN CANDLE (close > open) for a ticker close above break level for that ticker
            '''
            # last_close_value = 2000  # FOR TESTING ONLY
            if last_close_value > last_open_value:  # https://discord.com/channels/@me/1216220927356833812/1217840275192545281
                print(f'Last 1m candle for {tickers[stock_index]} was Green. It closed higher than it opened.'
                      f' {last_close_value} > {last_open_value}. Now let us see if it closed above the break level')

                if last_close_value > break_levels[stock_index]:
                    print(f'Last 1m candle for {tickers[stock_index]}'
                          f' has closed above the break level of {break_levels[stock_index]}.'
                          f' {last_close_value} > {break_levels[stock_index]}. Time to enter the position.')

                    # Buy dollar amount/share price shares. (Using limit buy @ ask)
                    last_ticker_price = intervals[len(intervals) - 1]['price']

                    quantity_of_shares_to_buy = math.floor(dollar_amount[stock_index] / last_ticker_price)

                    ask = self.get_stock_quote(tickers[stock_index])['quotes']['quote']['ask']

                    self.place_limit_buy_order(tickers[stock_index], 'buy',
                                               ask,
                                               quantity_of_shares_to_buy)  # TODO: validate this will get fulfilled when trading live

                    column = ''
                    if stock_index == 0:
                        column = 'B'
                    elif stock_index == 1:
                        column = 'C'
                    elif stock_index == 2:
                        column = 'D'
                    elif stock_index == 3:
                        column = 'E'
                    elif stock_index == 4:
                        column = 'F'

                    print(f'Adding entry price ${ask} to cell {column}7 for {stock_ticker}.')

                    self.write_to_google_sheet(column, ask, 'entry')
                    google_sheet = self.get_google_sheet()
            else:
                print(f'Last 1m candle for {tickers[stock_index]} was Red. It closed lower than equal to it opened.'
                      f' {last_close_value} < {last_open_value}. Doing nothing & proceeding.')

        '''
            BUY LOGIC 2
                - When ticker price is 2atrs above break level, enter the position

            One Minute Average True Range (ATR)
        '''
        # TODO - When ticker price is 2atrs above break level
        entries = google_sheet[6][1:]

        if entries[stock_index] == '.':
            print(f'Checking when ticker price is 2atrs above break level for {tickers[stock_index]}...\n')
            intervals = one_min_intervals_dict[tickers[stock_index]]['series']['data']
            last_close_value = intervals[len(intervals) - 1]['close']

            one_minute_interval_dataframes_dict = {}

            one_minute_interval_dataframes_dict[f'{tickers[stock_index]}'] = \
                (pd.DataFrame.from_dict(one_min_intervals_dict[f'{tickers[stock_index]}']['series']['data']))

            one_minute_interval_dataframes_dict[tickers[stock_index]]['atr14'] = ta.atr(
                one_minute_interval_dataframes_dict[tickers[stock_index]]['high'],
                one_minute_interval_dataframes_dict[tickers[stock_index]]['low'],
                one_minute_interval_dataframes_dict[tickers[stock_index]]['close'], length=14)

            values_of_atr_dataframe = one_minute_interval_dataframes_dict[tickers[stock_index]]['atr14']
            atr_list = values_of_atr_dataframe.values.tolist()

            if last_close_value >= ((atr_list[len(atr_list) - 1]) * 2) + break_levels[
                stock_index]:  # TODO validate this is "2atrs" as specified by Noah
                print(f'last atr greater than or equal to 2 atrs. {last_close_value} is >='
                      f' to {(((atr_list[len(atr_list) - 1]) * 2) + break_levels[stock_index])} Time to enter position')

                # Buy dollar amount/share price shares. (Using limit buy @ ask)
                last_ticker_price = intervals[len(intervals) - 1]['price']

                quantity_of_shares_to_buy = math.floor(dollar_amount[stock_index] / last_ticker_price)

                ask = self.get_stock_quote(tickers[stock_index])['quotes']['quote']['ask']

                self.place_limit_buy_order(tickers[stock_index], 'buy',
                                           ask, quantity_of_shares_to_buy)
                # TODO: validate this will get fulfilled when trading live

                column = ''
                if stock_index == 0:
                    column = 'B'
                elif stock_index == 1:
                    column = 'C'
                elif stock_index == 2:
                    column = 'D'
                elif stock_index == 3:
                    column = 'E'
                elif stock_index == 4:
                    column = 'F'

                self.write_to_google_sheet(column, ask, 'entry')

    '''
    SELL LOGIC 1
        - For every valid stock in the Google Sheets, Sell 25% of stock position if we hit the min_target,
            Using limit sell @ bid
        - check this very frequently (at LEAST once a minute)

    '''

    def sell_logic_one(self, account_open_positions, stock_ticker, stock_index,
                       min_targets, last_close_value, prices, bid):

        print(f'Checking to see if we currently qualify for Sell Logic 1 for stock {stock_ticker}.')

        # last_close_value = 2000 # TESTING ONLY
        if last_close_value >= min_targets[stock_index]:
            # positions = self.get_positions().get('positions')  # API CALL
            ticker_position = account_open_positions['position'][stock_index]
            ticker_cost_basis = ticker_position['cost_basis']
            position_to_sell = ticker_cost_basis / 4

            quantity_of_shares_to_sell = math.floor(position_to_sell / prices[stock_index])

            print(f'Last closing value of {last_close_value} is now greater than the min_target value'
                  f' of {min_targets[stock_index]}.\nTime to sell {stock_ticker} position of'
                  f' ${ticker_cost_basis} by 25% for ${position_to_sell}')

            self.place_limit_sell_order(tickers[stock_index], bid,
                                        quantity_of_shares_to_sell)  # position_to_sell right?? #5.090770833333334 fails due to many decimal points

            print(
                f'Attempted limit sell order of ${position_to_sell} placed for a total of {stock_ticker}.'
                f'\n. {quantity_of_shares_to_sell} shares were sold for the bid price of ${bid}')
            # TODO validate it was successful and redo if not ^

    '''
    SELL LOGIC 2
        - Sell 50% of position when candle close below 10ema/1min 
        - check this very frequently (at LEAST once a minute)
    '''

    def sell_logic_two(self, account_open_positions, stock_ticker, stock_index,
                       one_minute_interval_dataframes_dict, last_close_value, bid):
        print(f'\nChecking to see if we currently qualify for Sell Logic 2 for stock {stock_ticker}')

        values_of_ema_dataframe = one_minute_interval_dataframes_dict[stock_ticker]['ema10'].values
        ema_list = values_of_ema_dataframe.tolist()

        # last_close_value = 10  # FOR TESTING ONLY TO ENTER THE BELOW CONDITION
        if last_close_value < ema_list[len(ema_list) - 1]:
            print('Last closing value is less than the latest 10ema on the 1 minute candle.'
                  f' {last_close_value} < {ema_list[len(ema_list) - 1]}'
                  f'\nTime to sell 50% of current position for {stock_ticker}')

            # last_close_value = intervals[len(intervals) - 1]['close']   # DURING TESTING... THIS IS TO RESET

            ticker_position = account_open_positions['position'][stock_index]
            ticker_cost_basis = ticker_position['cost_basis']
            position_to_sell = ticker_cost_basis / 2

            quantity_of_shares_to_sell = math.floor(position_to_sell / bid)

            self.place_limit_sell_order(tickers[stock_index], bid, quantity_of_shares_to_sell)
            # TODO: validate this will get fulfilled when trading live
        # ----------------------------------------END SELL LOGIC 2--------------------------------------------------

    def sell_logic_three(self, account_open_positions, stock_ticker, stock_index,
                         five_minute_interval_dataframes_dict, last_close_value, bid):
        print('Checking to see if we currently qualify for Sell Logic 3')

        values_of_ema_dataframe = five_minute_interval_dataframes_dict[stock_ticker]['ema10'].values
        ema_list = values_of_ema_dataframe.tolist()

        # last_close_value = 10  # FOR TESTING ONLY TO ENTER THE BELOW CONDITION
        if last_close_value < ema_list[len(ema_list) - 1]:
            print('Last closing value is less than the latest 10ema on the 5 minute candle.'
                  f' {last_close_value} < {ema_list[len(ema_list) - 1]}'
                  f'\nTime to close the remaining position for {stock_ticker}')

            # last_close_value = intervals[len(intervals) - 1]['close']   # DURING TESTING... THIS IS TO RESET

            ticker_position = account_open_positions['position'][stock_index]
            ticker_cost_basis = ticker_position['cost_basis']
            position_to_sell = ticker_cost_basis

            quantity_of_shares_to_sell = math.floor(position_to_sell / bid)

            self.place_limit_sell_order(tickers[stock_index], bid, quantity_of_shares_to_sell)
            # TODO: validate this will get fulfilled when trading live

            # ----------------------------------------END SELL LOGIC 3--------------------------------------------------

            # We only want to write the price one time, when we FINALLY exit our position, correct?
            column = ''
            if stock_index == 0:
                column = 'B'
            elif stock_index == 1:
                column = 'C'
            elif stock_index == 2:
                column = 'D'
            elif stock_index == 3:
                column = 'E'
            elif stock_index == 4:
                column = 'F'

            self.write_to_google_sheet(column, bid, 'exit')

    '''
        Creating/adding to Dataframes for the given ticker
    '''

    def create_dataframe(self, stock_ticker, interval_time, x_min_intervals_dict):
        print(f'\n**DATAFRAME CREATION - Creating {interval_time} minute Dataframe for {stock_ticker}.**')

        interval_dataframe_dict = {}

        interval_dataframe_dict[f'{stock_ticker}'] = (pd.DataFrame.
        from_dict(
            x_min_intervals_dict[f'{stock_ticker}']['series']['data']))

        print(f'\n**DATAFRAME ADDITION - Adding ema10 indicator to Dataframe for {stock_ticker}.**')

        for index_1 in range(len(interval_dataframe_dict)):
            interval_dataframe_dict[stock_ticker]['ema10'] = ta.ema(
                interval_dataframe_dict[stock_ticker]['close'], length=10)

            print(f'ema10 indicator values added to {interval_time} minute Dataframe for {stock_ticker}')

        return interval_dataframe_dict

    def sell_stock(self, google_sheet, stock_ticker):

        print(f'\n**SELL LOGIC for {stock_ticker}**\n')

        '''
            Thread specific setup
        '''

        stock_index: int = 0  # default to 0

        tickers = google_sheet[0][1:]
        entries = google_sheet[6][1:]
        amount = google_sheet[1][1:]
        min_targets = google_sheet[2][1:]
        # max_targets = sheet[3][1:]
        prices = google_sheet[4][1:]

        for index in range(len(tickers)):
            if tickers[index] == stock_ticker:
                stock_index = index

        # -----------------------------END THREAD SETUP--------------------------------------------------------------

        is_first_time_running_code = True

        while True:

            if not is_first_time_running_code:
                # https://stackoverflow.com/questions/17220128/display-a-countdown-for-the-python-sleep-function#:~:text=41-,you%20could%20always%20do,-%23do%20some%20stuff
                print(f'Sleeping thread for 15 seconds for {stock_ticker}')
                # time.sleep(15)  # sleep for 15 seconds before proceeding
                for i in range(15, 0, -1):
                    # sys.stdout.write(f'{stock_ticker}:' + str(i) + ' ')
                    sys.stdout.write(str(i) + f' seconds left until {stock_ticker} proceeds. ')
                    sys.stdout.flush()
                    time.sleep(1)

            is_first_time_running_code = False

            # available_balance = self.get_available_balance()  # API CALL
            # print('\nChecking available balance, it is: $', available_balance)

            one_min_intervals_dict = {}
            account_open_positions = self.get_positions().get('positions')

            if account_open_positions == 'null':
                print('No open positions found for any ticker.'
                      ' Skipping all Sell Logic entirely and returning to the beginning')
                continue

            # Validate we do not attempt any sell logic on a ticker that currently has NO position open
            if self.is_position_open_for_current_ticker([stock_ticker], account_open_positions) is False:
                print(f'\nHave not entered into a position for {stock_ticker}. Skipping sell logic entirely')
                continue  # returns to beginning of the while loop
                # sys.exit(0) # TODO kill thread or loop/wait for an event like the "continue"?

            print(f'Found open position for {stock_ticker}.'
                  f' Proceeding with Sell Logic.')
            print(f'Now getting one minute intervals from the sheet for {stock_ticker}')

            one_min_interval = self.get_intervals_without_set_time(stock_ticker, '1min')  # API CALL

            one_min_intervals_dict[
                f'{stock_ticker}'] = one_min_interval  # add to dict with key/value pair like "AAPL: 130"

            intervals = one_min_intervals_dict[stock_ticker]['series']['data']
            last_close_value = intervals[len(intervals) - 1]['close']

            bid = self.get_stock_quote(stock_ticker)['quotes']['quote']['bid']  # API CALL

            # check and see if we qualify for sell logic 1
            self.sell_logic_one(account_open_positions, stock_ticker, stock_index,
                                min_targets, last_close_value, prices, bid)

            # create dataframe for one minute and add EMA indicator to the dataframe
            one_minute_interval_dataframes_dict = self.create_dataframe(stock_ticker, '1', one_min_intervals_dict)

            # check and see if we qualify for sell logic 2
            self.sell_logic_two(account_open_positions, stock_ticker, stock_index,
                                one_minute_interval_dataframes_dict, last_close_value, bid)

            '''
            SELL LOGIC 3
                - Sell remaining 25% of position when candle closes below 10ema/5min
                - check for this every 5 minutes

            '''
            # TODO where to put inside? 5 minute section or not??

            print(f'Getting five minute intervals from the sheet')
            five_min_interval = self.get_intervals_without_set_time(stock_ticker, '5min')

            five_min_intervals_dict = {}
            five_min_intervals_dict[
                f'{stock_ticker}'] = five_min_interval  # add to dict with key/value pair like "AAPL: 130"

            print(f'\n**DATAFRAME CREATION - Creating 5 minute Dataframe for {stock_ticker}.**')

            five_minute_interval_dataframes_dict = {}

            five_minute_interval_dataframes_dict[f'{stock_ticker}'] = (pd.DataFrame.from_dict(
                five_min_intervals_dict[f'{stock_ticker}']['series']['data']))

            print(f'\n**DATAFRAME ADDITION - Adding ema10 indicator to 5 minute Dataframe for {stock_ticker}.**')

            for index_1 in range(len(one_minute_interval_dataframes_dict)):
                five_minute_interval_dataframes_dict[stock_ticker]['ema10'] = ta.ema(
                    five_minute_interval_dataframes_dict[stock_ticker]['close'], length=10)

                print(f'ema10 indicator values added to 5 minute Dataframe for {stock_ticker}')

            self.sell_logic_three(account_open_positions, stock_ticker, stock_index,
                                  five_minute_interval_dataframes_dict, last_close_value, bid)

            '''
            SCRIPT EXIT LOGIC
                - only after ALL stock positions have been closed, do we exit
                - check very frequently for this
            '''

            print(f'Reached end of sell_stock() for {stock_ticker}')

            # TODO above ^

    def main(self, sheet_data_ticker):
        pid = os.getpid()

        print(f'inside main() for {sheet_data_ticker}. Process is {multiprocessing.current_process()}.')
        print(f'{sheet_data_ticker} pid = {pid}')

        while True:
            print(f'Checking Launch status in the Sheet for {sheet_data_ticker}')

            time.sleep(5)  # needed so we dont exceed google api rate limit

            sheet = self.get_google_sheet()  # calling get_google_sheet() again here until i figure out how to pass it in properly for Pool()

            tickers = sheet[0][1:]
            launches = sheet[10][1:]

            for index in range(len(tickers)):
                if sheet_data_ticker == tickers[index]:
                    if launches[index] == 'y' or launches[index] == 'Y':
                        print(f'Launch is set to y or Y for {tickers[index]}, proceeding with bot.')

                        self.buy_stock(sheet, sheet_data_ticker)  # buy the stocks and enter our positions
                        self.sell_stock(sheet, sheet_data_ticker)


if __name__ == '__main__':
    strat_main_with_mp = stratMainWIthMP()

    sheet = strat_main_with_mp.get_google_sheet()

    tickers = sheet[0][1:]

    entries = sheet[6][1:]
    amount = sheet[1][1:]
    min_targets = sheet[2][1:]
    # max_targets = sheet[3][1:]
    prices = sheet[4][1:]

    # sheet_data_dict = {'tickers': tickers, 'entries': entries, 'amount': amount,
    #                    'min_targets': min_targets, 'prices': prices}

    print(tickers)

    with Pool(5) as p:
        p.map(strat_main_with_mp.main, tickers)  # TODO how to correctly pass in sheet_data_dict ?

    print("SCRIPT COMPLETED")
