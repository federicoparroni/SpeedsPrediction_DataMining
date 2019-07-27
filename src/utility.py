import os
import numpy as np
import pandas as pd
import datetime
from tqdm.auto import tqdm

def check_folder(path):
    split_folder = os.path.split(path)
    if '.' in split_folder[1]:
        # path is a file
        path = split_folder[0]
    if not os.path.exists(path):
        print(f'{path} folder created')
        os.makedirs(path, exist_ok=True)

def df_to_datetime(df, columns):
    for c in columns:
        df[c] = pd.to_datetime(df[c])
    return df

def discretize_timestamp(df, col_name, step=15*60, ceil=True, rename_col=None, ceil_if_rem0=False):
    """
    Discretize a datetime column of a dataframe.
    df (dataframe):     dataframe
    col_name (str):     name of the datetime column
    step (int):         interval of discretization
    ceil (bool):       whether to approximate to the lower or upper value
    rename_col (str):   name of the new column, None to replace the old one
    """
    unix_timestamps = df[col_name].astype('int64') // 10**9 #s
    remainders = unix_timestamps % step

    mask_rem_non0 = remainders > 0
    if ceil:
        if ceil_if_rem0:
            unix_timestamps = unix_timestamps - remainders + step
        else:
            unix_timestamps[mask_rem_non0] = unix_timestamps[mask_rem_non0] - remainders + step
    else:
        if ceil_if_rem0:
            unix_timestamps = unix_timestamps - remainders
        else:
            unix_timestamps[mask_rem_non0] = unix_timestamps[mask_rem_non0] - remainders
    
    if isinstance(rename_col, str):
        df[rename_col] = pd.to_datetime(unix_timestamps, unit='s')
    else:
        df[col_name] = pd.to_datetime(unix_timestamps, unit='s')
    return df



def reduce_mem_usage(df):
    """
    call on a dataframe to reduce its memory consumption
    :param df:
    :return:
    """
    start_mem = df.memory_usage().sum() / 1024 ** 2

    for col in df.columns:
        col_type = df[col].dtype

        if col_type != object and col_type != "datetime64[ns]":
            c_min = df[col].min()
            c_max = df[col].max()
            if str(col_type)[:3] == 'int':
                if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                    df[col] = df[col].astype(np.int16)
                elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
                elif c_min > np.iinfo(np.int64).min and c_max < np.iinfo(np.int64).max:
                    df[col] = df[col].astype(np.int64)
            else:
                if c_min > np.finfo(np.float16).min and c_max < np.finfo(np.float16).max:
                    df[col] = df[col].astype(np.float16)
                elif c_min > np.finfo(np.float32).min and c_max < np.finfo(np.float32).max:
                    df[col] = df[col].astype(np.float32)
                else:
                    df[col] = df[col].astype(np.float64)
        elif col_type == object:
            df[col] = df[col].astype('category')

    end_mem = df.memory_usage().sum() / 1024 ** 2
    print('Decreased by {:.1f}%'.format(100 * (start_mem - end_mem) / start_mem))

    return df


def expand_timestamps(df, col_ts_start='START_DATETIME_UTC', col_ts_end='END_DATETIME_UTC', ceil_if_rem0=False):
    """ Expand the timestamp of a dataframe, in order to have all the intermediate timestamps
        between col_ts_start and col_ts_end.
    """
    tqdm.pandas()
    # cast the columns containing string to datetime
    df[col_ts_start] = pd.to_datetime(df[col_ts_start])
    df[col_ts_end] = pd.to_datetime(df[col_ts_end])
    df = df.sort_values(col_ts_start).reset_index()

    # discretize the timestamps
    df = discretize_timestamp(df, col_name=col_ts_start, ceil=True, ceil_if_rem0=ceil_if_rem0)
    df = discretize_timestamp(df, col_name=col_ts_end, ceil=True, ceil_if_rem0=ceil_if_rem0)

    # cast the datatimes to unix timestamps (s)
    df[col_ts_start] = df[col_ts_start].astype('int') // 10**9   #s
    df[col_ts_end] = df[col_ts_end].astype('int') // 10**9  #s

    # compute the difference of the 2 timestamps in time steps of 15 minutes
    df['step_duration'] = (df[col_ts_end] - df[col_ts_start]) // (15*60) +1

    # build the time range from start to end at steps of 900 seconds (15 minutes)
    df['DATETIME_UTC'] = df.progress_apply(lambda x:
                                    np.arange(x[col_ts_start], x[col_ts_end] + 900, 900), axis=1)

    # expand the list of timestamps in the time_range
    df = pd.DataFrame({
        col: np.repeat(df[col].values, df['step_duration'])
        for col in df.columns.drop('DATETIME_UTC')}
    ).assign(**{'DATETIME_UTC': np.concatenate(df['DATETIME_UTC'].values)})

    return df

def merge_speed_events(speed_df, events_df):
    """ Join the speed dataframe with the events (drops speed rows with only NaN avg speed, if all speeds are NaNs, it
    means that the rows is one of those to predict). """
    # discriminate speeds to predict in which the SPEED_AVGs are already NaN
    speed_df['to_predict'] = (speed_df['SPEED_AVG'].isnull() *1)
    speed_df.loc[speed_df['to_predict'] != 1, 'to_predict'] = np.nan

    joined = speed_df.merge(events_df.drop('KEY_2',axis=1).reset_index(), how='outer', on=['KEY','DATETIME_UTC'])
    out_event_range_mask = ~((joined.KM_START <= joined.KM) & (joined.KM_END >= joined.KM))
    #joined.loc[out_event_range_mask, events_df.columns.drop(['KEY','KEY_2','DATETIME_UTC']).tolist()+['index']] = np.nan
    joined.loc[out_event_range_mask, ['index', 'SPEED_AVG', 'to_predict']] = np.nan
    #joined.dropna(subset=joined.columns.drop(['KEY','DATETIME_UTC']), how='all', inplace=True)
    joined.dropna(subset=['index','SPEED_AVG','to_predict'], how='all', inplace=True)

    speed_df.drop('to_predict', axis=1, inplace=True)
    return joined.drop('to_predict', axis=1).rename(columns={'index':'event_index'})


def time_windows_event(dataset_df, speeds_df, steps_behind=10, steps_after=3, step=15*60):
    """ Filter the dataset to get a window containing n time steps before the beginning
        of the event and m time steps after the end for each involved sensor

        dataset_df (df): dataset dataframe
        steps_behind (int): n (not including the event start)
        steps_after (int): m (not including the event start)
        step (int): step size in seconds
    """
    tqdm.pandas()
    # get the first time step of each event for each sensor
    start_events = dataset_df[dataset_df.event_index.notnull()]
    start_events = start_events[['KEY_2','event_index','DATETIME_UTC']].groupby(['KEY_2','event_index'], as_index=False).min()
    start_events['sample_id'] = start_events.index
    print('Total events found:', start_events.shape[0])

    start_delta = datetime.timedelta(seconds=step*steps_behind)
    end_delta = datetime.timedelta(seconds=step*steps_after)

    # construct the time window for each event beginning
    start_events['window'] = start_events.progress_apply(lambda x:
                                    list(pd.date_range(start=x.DATETIME_UTC - start_delta,
                                                       end=x.DATETIME_UTC + end_delta,
                                                       freq=f'{step}s')), axis=1)
    start_events = start_events.drop('DATETIME_UTC', axis=1)

    # build the filter
    filter_df = pd.DataFrame({ col: np.repeat(start_events[col].values, start_events['window'].str.len())
        for col in start_events.columns.drop('window')
    }).assign(**{'DATETIME_UTC': np.concatenate(start_events['window'].values)})
    print('Filter size:', filter_df.shape[0])

    # join to filter the desired rows, removing duplicated road-timestamps from the dataset (they will be duplicated again
    # after the merge, since a different time window is created for each event)
    return filter_df.merge(speeds_df, how='left', on=['KEY_2','DATETIME_UTC']) \
            .sort_values(['sample_id','DATETIME_UTC'])
