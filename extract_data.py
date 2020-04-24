""" extract_data.py
    ---------------
    This script constructs the command line interface which is used to extract, clean and manage trade data for selected symbols, dates and
    times from the wrds database.

    Contact: nicolo.ceneda@student.unisg.ch
    Last update: 18 May 2020
"""


# ------------------------------------------------------------------------------------------------------------------------------------------
# 0. CODE SETUP
# ------------------------------------------------------------------------------------------------------------------------------------------


# Import the libraries

import os
import time
import argparse
import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import matplotlib.pyplot as plt


# Establish a connection to the wrds cloud

try:

    import wrds

except ImportError:

    raise ImportError('\nAn error occurred trying to import the wrds library locally: run the script on the wrds cloud.')

else:

    db = wrds.Connection()


# Import the functions from the functions script

from extract_data_functions import section, graph_output, graph_comparison, print_output


# Set the displayed size of pandas objects

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)


# Start timing the execution

start = time.time()


# ------------------------------------------------------------------------------------------------------------------------------------------
# 1. COMMAND LINE INTERFACE AND INPUT CHECK
# ------------------------------------------------------------------------------------------------------------------------------------------


# Define the commands available in the command line interface

min_start_date = '2003-09-10'
max_end_date = '2020-03-31'
min_start_time = '09:30:00'
max_end_time = '16:00:00'

parser = argparse.ArgumentParser(description='Command-line interface to extract trade data',
                                 formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=40))

parser.add_argument('-sl', '--symbol_list', metavar='', type=str, default=['AAPL'], nargs='+', help='List of symbols to extract.')
parser.add_argument('-sd', '--start_date', metavar='', type=str, default='{}'.format(min_start_date), help='Start date to extract the data.')
parser.add_argument('-ed', '--end_date', metavar='', type=str, default='{}'.format(max_end_date), help='End date to extract the data.')
parser.add_argument('-st', '--start_time', metavar='', type=str, default='{}'.format(min_start_time), help='Start time to extract the data.')
parser.add_argument('-et', '--end_time', metavar='', type=str, default='{}'.format(max_end_time), help='End time to extract the data.')
parser.add_argument('-bg', '--debug', action='store_true', help='Flag to debug the program.')
parser.add_argument('-po', '--print_output', action='store_true', help='Flag to print the output.')
parser.add_argument('-go', '--graph_output', action='store_true', help='Flag to graph the output.')

args = parser.parse_args()


# Define the debug settings

if args.debug:

    args.symbol_list = ['AAPL', 'AMZN', 'GOOG', 'TSLA']
    args.start_date = '2019-03-28'
    args.end_date = '2019-04-02'
    args.start_time = '09:38:00'
    args.end_time = '09:48:00'
    args.print_output = True
    args.graph_output = True

    section('You are debugging with: symbol_list: {} | start_date: {} | end_date: {} | start_time: {} | end_time: {}'.format(args.symbol_list,
            args.start_date, args.end_date, args.start_time, args.end_time))

else:

    section('You are querying with: symbol_list: {} | start_date: {} | end_date: {} | start_time: {} | end_time: {}'.format(args.symbol_list,
            args.start_date, args.end_date, args.start_time, args.end_time))


# Check the validity of the input symbols and create the list of symbols:

symbol_list = args.symbol_list

unwanted_symbols = ['GOOG', 'LBTYA', 'FOX']
wanted_symbols = ['GOOG', 'LBTY', 'FOXA']
wanted_symbols_suffix = {'GOOG': ('L', "='L'"), 'LBTY': ('K', "='K'"), 'FOXA': ('', "is null")}

suffix_query = {symbol: "is null" for symbol in symbol_list if symbol not in unwanted_symbols}

for pos, unwanted_symbol in enumerate(unwanted_symbols):

    if unwanted_symbol in symbol_list:

        wanted_symbol = wanted_symbols[pos]
        wanted_suffix = wanted_symbols_suffix[wanted_symbol][0]
        symbol_list[symbol_list.index(unwanted_symbol)] = wanted_symbol
        suffix_query[wanted_symbol] = wanted_symbols_suffix[wanted_symbol][1]
        print('\n*** WARNING: You attempted to query {}: {} has been selected instead as it is more liquid.'.format(unwanted_symbol,
              wanted_symbol + wanted_suffix))


# Check the validity of the input start and end dates and create the list of dates:

if args.start_date > args.end_date:

    print('\n*** ERROR: Invalid start and end dates: chose a start date before the end date.')
    exit()

elif args.start_date < min_start_date and args.end_date < max_end_date:

    print('\n*** ERROR: Invalid start date: choose a date after {}.'.format(min_start_date))
    exit()

elif args.start_date > min_start_date and args.end_date > max_end_date:

    print('\n*** ERROR: Invalid end date: choose a date before {}.'.format(max_end_date))
    exit()

elif args.start_date < min_start_date and args.end_date > max_end_date:

    print('\n*** ERROR: Invalid start and end dates: choose dates between {} and {}.'.format(min_start_date, max_end_date))
    exit()

nasdaq = mcal.get_calendar('NASDAQ')
nasdaq_cal = nasdaq.schedule(start_date=args.start_date, end_date=args.end_date)
date_index = nasdaq_cal.index
date_list = [str(d)[:10].replace('-', '') for d in date_index]


# Check the validity of the input times:

if args.start_time > args.end_time:

    print('\n*** ERROR: Invalid start and end times: chose a start time before the end time.')
    exit()

elif args.start_time < min_start_time and args.end_time < max_end_time:

    print('\n*** ERROR: Invalid start time: choose a time after {}.'.format(min_start_time))
    exit()

elif args.start_time > min_start_time and args.end_time > max_end_time:

    print('\n*** ERROR: Invalid end time: choose a time before {}.'.format(max_end_time))
    exit()

elif args.start_time < min_start_time and args.end_time > max_end_time:

    print('\n*** ERROR: Invalid start and end times: choose times between {} and {}.'.format(min_start_time, max_end_time))
    exit()


# ------------------------------------------------------------------------------------------------------------------------------------------
# 2. DATA EXTRACTION AND FIRST DATA CLEANING
# ------------------------------------------------------------------------------------------------------------------------------------------


# Create a function to run the SQL query and filter for unwanted 'tr_corr' and 'tr_scond'

def query_sql(date_, symbol_, start_time_, end_time_):

    max_attempts = 2

    parm = {'G': '%G%', 'L': '%L%', 'P': '%P%', 'T': '%T%', 'U': '%U%', 'X': '%X%', 'Z': '%Z%'}

    query = "SELECT date, time_m, sym_root, sym_suffix, tr_scond, size, price, tr_corr " \
            "FROM taqm_{}.ctm_{} " \
            "WHERE sym_root = '{}' " \
            "AND sym_suffix {} " \
            "AND time_m >= '{}' " \
            "AND time_m <= '{}' " \
            "AND tr_corr = '00'" \
            "AND tr_scond NOT LIKE %(G)s " \
            "AND tr_scond NOT LIKE %(L)s " \
            "AND tr_scond NOT LIKE %(P)s " \
            "AND tr_scond NOT LIKE %(T)s " \
            "AND tr_scond NOT LIKE %(U)s " \
            "AND tr_scond NOT LIKE %(X)s " \
            "AND tr_scond NOT LIKE %(Z)s ".format(date_[:4], date_, symbol_, suffix_query[symbol_], start_time_, end_time_)

    for attempt in range(max_attempts):

        try:

            queried_trades = db.raw_sql(query, params=parm)

        except Exception:

            if attempt < max_attempts - 1:

                print('\n*** WARNING: The query failed: trying again.')

            else:

                print('\n*** WARNING: The query failed and the max number of attempts has been reached.')

        else:

            return queried_trades, True

    return None, False


# Create a function to check the min and max number of observations for each symbol

def n_obs(queried_trades_, date_):

    global count_2, min_n_obs, min_n_obs_day, max_n_obs, max_n_obs_day
    count_2 += 1
    obs = queried_trades_.shape[0]

    if count_2 == 1:

        min_n_obs = obs
        n_obs_table.loc[count_1, 'min_n_obs'] = min_n_obs
        n_obs_table.loc[count_1, 'min_n_obs_day'] = pd.to_datetime(date_).strftime('%Y-%m-%d')

        max_n_obs = obs
        n_obs_table.loc[count_1, 'max_n_obs'] = max_n_obs
        n_obs_table.loc[count_1, 'max_n_obs_day'] = pd.to_datetime(date_).strftime('%Y-%m-%d')

    elif obs < min_n_obs:

        min_n_obs = obs
        n_obs_table.loc[count_1, 'min_n_obs'] = min_n_obs
        n_obs_table.loc[count_1, 'min_n_obs_day'] = pd.to_datetime(date_).strftime('%Y-%m-%d')

    elif obs > max_n_obs:

        max_n_obs = obs
        n_obs_table.loc[count_1, 'max_n_obs'] = max_n_obs
        n_obs_table.loc[count_1, 'max_n_obs_day'] = pd.to_datetime(date_).strftime('%Y-%m-%d')


# Run the SQL queries and compute the min and max number of observations for each queried symbol

warning_queried_trades = []
warning_query_sql = []
warning_ctm_date = []

n_obs_table = pd.DataFrame({'symbol': [], 'min_n_obs': [], 'min_n_obs_day': [], 'max_n_obs': [], 'max_n_obs_day': []})

output = pd.DataFrame([])

remove_dates = []

for count_1, symbol in enumerate(symbol_list):

    n_obs_table.loc[count_1, 'symbol'] = symbol
    min_n_obs = None
    min_n_obs_day = None
    max_n_obs = None
    max_n_obs_day = None
    count_2 = 0

    for date in date_list:

        print('Running a query with: symbol: {}, date: {}, start_time: {}; end_time: {}.'.format(symbol, pd.to_datetime(date).strftime('%Y-%m-%d'),
              args.start_time, args.end_time))

        all_tables = db.list_tables(library='taqm_{}'.format(date[:4]))

        if ('ctm_' + date) in all_tables:

            queried_trades, success_query_sql = query_sql(date, symbol, args.start_time, args.end_time)

            if success_query_sql:

                if queried_trades.shape[0] > 0:

                    print('Appending the queried trades to the output.')
                    output = output.append(queried_trades)
                    n_obs(queried_trades, date)

                else:

                    print('*** WARNING: Symbol {} did not trade on date {}: the date has been removed from date_list and all trades already '
                          'queried with this date have be cancelled; the warning has been recorded to "warning_queried_trades".'.format(symbol,
                           pd.to_datetime(date).strftime('%Y-%m-%d')))
                    remove_dates.append(date)
                    warning_queried_trades.append('{}+{}'.format(symbol, date))

            else:

                print('*** WARNING: The warning has been recorded to "warning_query_sql".')
                warning_query_sql.append('{}+{}'.format(symbol, date))

        else:

            print('*** WARNING: Could not find the table ctm_{} in the table list: the date has been removed from date_list; '
                  'the warning has been recorded to "warning_ctm_date".'.format(date))
            remove_dates.append(date)
            warning_ctm_date.append(date)

    date_list = [d for d in date_list if d not in list(set(remove_dates))]

    if len(date_list) == 0:

        print('\n*** ERROR: Could not find any table in the table list or at least one symbol did not trade for each date.')
        exit()

output = output[pd.to_datetime(output['date']).isin([pd.to_datetime(d) for d in date_list])]

print('\nThe updated parameters are: symbol_list: {}; date_list: {}'.format(args.symbol_list, date_list))


# Display the log of the warnings

section('Log of the raised warnings')

print('*** LOG: warning_queried_trades:\n', warning_queried_trades)

print('*** LOG: warning_ctm_date:\n', warning_ctm_date)

print('*** LOG: warning_query_sql:\n', warning_query_sql)


# Display the dataframe with the min and max number of observations for each symbol

section('Min and max number of observations for each queried symbol')

print(n_obs_table)


# Display the dataframe of the queried trades

section('Queried data')

print_output(output_=output, print_output_flag_=args.print_output, head_flag_=True)


# ------------------------------------------------------------------------------------------------------------------------------------------
# 3. DATA CLEANING
# ------------------------------------------------------------------------------------------------------------------------------------------


# Clean the data from unwanted 'tr_corr' and 'tr_scond'

""" During the querying step, the data was already filtered for 'tr_corr' and 'tr_scond':

    - Observations with 'tr_corr' == '00' were kept

    - Observations with 'tr_scond' in {'@', 'A', 'B', 'C', 'D', 'E', 'F', 'H', 'I', 'K', 'M', 
      'N', 'O', 'Q', 'R', 'S', 'V', 'W', 'Y', '1', '4', '5', '6', '7', '8', '9'} were kept.
    - Observations with 'tr_scond' in {'G', 'L', 'P', 'T', 'U', 'X', 'Z'} were discarded.
"""


# Clean the data from outliers

delta = 0.1

k_list = np.arange(41, 121, 20, dtype='int64')
y_list = np.arange(0.02, 0.08, 0.02)
k_grid, y_grid = np.meshgrid(k_list, y_list)
ky_array = np.array([k_grid.ravel(), y_grid.ravel()]).T

outlier_frame = pd.DataFrame(columns=['symbol', 'out_num', 'k', 'y'])
outlier_frame['symbol'] = pd.Series(symbol_list)

not_outlier_series = pd.Series([])

for pos, symbol in enumerate(symbol_list):

    count = 0

    for k, y in ky_array:

        count += 1
        outlier_num_sym = 0
        not_outlier_sym = pd.Series([])

        perc_b = int(k * delta)
        perc_t = int(k * (1 - delta) + 1)

        for date in date_list:

            price_sym_day = output.loc[(output['sym_root'] == symbol) & (pd.to_datetime(output['date']) == pd.to_datetime(date)), 'price']

            center_beg = int((k - 1) / 2)
            center_end = int(len(price_sym_day)) - center_beg

            window = np.sort(price_sym_day[:int(k)])
            mean_rolling = np.repeat(np.nan, len(price_sym_day))
            std_rolling = np.repeat(np.nan, len(price_sym_day))

            for i in range(center_beg, center_end):

                mean_rolling[i] = window[perc_b:perc_t].mean()
                std_rolling[i] = window[perc_b:perc_t].std()

                if i < center_end - 1:

                    idx_drop = np.searchsorted(window, price_sym_day[i - center_beg])
                    window[idx_drop] = price_sym_day[i + center_beg + 1]
                    window.sort()

            price_sym_day_mean = pd.Series(mean_rolling, index=price_sym_day.index)
            price_sym_day_std = pd.Series(std_rolling, index=price_sym_day.index)

            price_sym_day_mean.iloc[:center_beg] = price_sym_day_mean.iloc[center_beg]
            price_sym_day_mean.iloc[center_end:] = price_sym_day_mean.iloc[center_end - 1]
            price_sym_day_std.iloc[:center_beg] = price_sym_day_std.iloc[center_beg]
            price_sym_day_std.iloc[center_end:] = price_sym_day_std.iloc[center_end - 1]

            left_con = (price_sym_day - price_sym_day_mean).abs()
            right_con = (3 * price_sym_day_std) + y

            outlier_num_sym += (left_con > right_con).sum()
            not_outlier_sym = not_outlier_sym.append(left_con < right_con)

        if count == 1:

            outlier_frame.loc[pos, 'out_num'] = outlier_num_sym
            outlier_frame.loc[pos, 'k'] = k
            outlier_frame.loc[pos, 'y'] = y
            not_outlier_sym_f = not_outlier_sym

        elif outlier_num_sym > outlier_frame.loc[pos, 'out_num']:

            outlier_frame.loc[pos, 'out_num'] = outlier_num_sym
            outlier_frame.loc[pos, 'k'] = k
            outlier_frame.loc[pos, 'y'] = y
            not_outlier_sym_f = not_outlier_sym

    not_outlier_series = not_outlier_series.append(not_outlier_sym_f)

output_filtered = output[not_outlier_series]


# Display the table of optimal k, y

section('k, y to optimally filter each queried symbol')

print(outlier_frame)


# Display the cleaned dataframe of the queried trades

section('Cleaned data')

print_output(output_=output_filtered, print_output_flag_=args.print_output, head_flag_=True)


# ------------------------------------------------------------------------------------------------------------------------------------------
# 4. DATA MANAGEMENT
# ------------------------------------------------------------------------------------------------------------------------------------------


# Create a function to aggregate simultaneous observations

price_median = output_filtered.groupby(['sym_root', 'date', 'time_m']).median().reset_index().loc[:, ['sym_root', 'date', 'time_m', 'price']]
volume_sum = output_filtered.groupby(['sym_root', 'date', 'time_m']).sum().reset_index().loc[:, 'size']
output_aggregate = pd.concat([price_median, volume_sum], axis=1)


# Display the aggregated dataframe of the queried trades

section('Aggregated data')

print_output(output_=output_aggregate, print_output_flag_=args.print_output, head_flag_=True)


# Create a function to resample observations at lower frequency

freq_list = ['2S']

""" ALTERNATIVE IMPLEMENTATION
    --------------------------
    You can test different frequencies using: freq_list = ['500L', '1S', '2S', '5S'] 
"""

nan_frame = pd.DataFrame(columns=['symbol', 'freq', 'ratio'])
nan_frame['symbol'] = pd.Series(symbol_list)

for count, freq in enumerate(freq_list):

    output_resampled = pd.DataFrame(columns=output_aggregate.columns)

    for pos, symbol in enumerate(symbol_list):

        num_nan_sym = 0
        num_tot_sym = 0

        for date in date_list:

            df_sym_day = output_aggregate[(output_aggregate['sym_root'] == symbol) & (pd.to_datetime(output_aggregate['date']) == pd.to_datetime(date))]
            index_resample = pd.DatetimeIndex(df_sym_day['date'].apply(str) + ' ' + df_sym_day['time_m'].apply(str))
            df_sym_day = df_sym_day.set_index(index_resample)
            price_last = df_sym_day.resample(freq, label='right', closed='right').last().loc[:, ['sym_root', 'date', 'time_m', 'price']]
            volume_sum = df_sym_day.resample(freq, label='right', closed='right').sum().loc[:, 'size']
            df_sym_day_resampled = pd.concat([price_last, volume_sum], axis=1)

            start_datetime = pd.to_datetime(date).strftime('%Y-%m-%d') + ' ' + args.start_time
            end_datetime = pd.to_datetime(date).strftime('%Y-%m-%d') + ' ' + args.end_time
            index_extended = pd.date_range(start=start_datetime, end=end_datetime, freq=freq)
            df_extended_index = pd.DataFrame(index=index_extended)
            df_resampled = df_extended_index.join(df_sym_day_resampled)

            num_nan_sym += pd.isna(df_resampled['sym_root']).sum()
            num_tot_sym += len(df_resampled)

            # The position of this line is crucial
            df_resampled['price'] = df_resampled['price'].interpolate(method='linear')
            df_resampled['price'] = df_resampled['price'].fillna(method='bfill')
            df_resampled['sym_root'] = symbol
            df_resampled['date'] = df_resampled.index.date
            df_resampled['time_m'] = df_resampled.index.time

            output_resampled = output_resampled.append(df_resampled)

        ratio = num_nan_sym / num_tot_sym

        if count == 0:

            nan_frame.loc[pos, 'freq'] = freq
            nan_frame.loc[pos, 'ratio'] = ratio
            output_resampled_f = output_resampled

        elif ratio < nan_frame.loc[pos, 'ratio']:

            nan_frame.loc[pos, 'freq'] = freq
            nan_frame.loc[pos, 'ratio'] = ratio
            output_resampled_f = output_resampled


# Display the table of optimal resampling frequencies

section('Resampling frequencies')

print(nan_frame)


# Display the resampled dataframe of the queried trades

section('Resampled data')

print_output(output_=output_resampled_f, print_output_flag_=args.print_output, head_flag_=False)


# Display the final plots of the queried trades

if args.graph_output:

    graph_output(output_=output_resampled_f, symbol_list_=symbol_list, date_index_=date_index, usage_='Final')


# Display the comparative plot between the original and the final plots

if args.graph_output:

    graph_comparison(output, output_resampled_f, symbol_list[0], date_list[0], 'Original', 'Final')


# ------------------------------------------------------------------------------------------------------------------------------------------
# 5. EXPORT THE TIME SERIES OF PRICES
# ------------------------------------------------------------------------------------------------------------------------------------------


# Save the time series of prices

if args.debug:

    if not os.path.isdir('mode bg'):

        os.mkdir('mode bg')

    for symbol in symbol_list:

        if not os.path.isdir('mode bg/' + symbol):

            os.mkdir('mode bg/' + symbol)

        data = pd.DataFrame(output_resampled_f[output_resampled_f['sym_root'] == symbol][['date', 'time_m', 'price']])
        data.to_csv('mode bg/' + symbol + '/data.csv', index=False)

else:

    if not os.path.isdir('mode sl'):

        os.mkdir('mode sl')

    for symbol in symbol_list:

        if not os.path.isdir('mode sl/' + symbol):

            os.mkdir('mode sl/' + symbol)

        data = pd.DataFrame(output_resampled_f[output_resampled_f['sym_root'] == symbol][['date', 'time_m', 'price']])
        data.to_csv('mode sl/' + symbol + '/data.csv', index=False)


# ------------------------------------------------------------------------------------------------------------------------------------------
# PROGRAM SETUP
# ------------------------------------------------------------------------------------------------------------------------------------------


# Close the connection to the wrds cloud

db.close()


# Show the plots

plt.show()


# Time execution

end = time.time()

print('\nExecution time: ', end - start)


# ------------------------------------------------------------------------------------------------------------------------------------------
# TO DO LIST
# ------------------------------------------------------------------------------------------------------------------------------------------


# TODO: remove from the current directory the following files, which have been copied from the directory 'official paper code'
#       LSTM-HTQF.bat; LSTM-HTQF.py; makeData.bat; makeData.py; rawData (folder); readMe.txt.
