import sys
import os
sys.path.append(os.getcwd())

from src.features.feature_base import FeatureBase
from src import data
import pandas as pd

class AvgSpeedStreet(FeatureBase):
    """
    say for each street the avg quantities
    | KEY | avg_speed_street | avg_speed_sd_street | avg_speed_min_street | avg_speed_max_street | avg_n_vehicles_street
    """

    def __init__(self, mode):
        name = 'avg_speed_street'
        super(AvgSpeedStreet, self).__init__(
            name=name, mode=mode)

    def extract_feature(self):
        df = None

        if self.mode == 'local':
            tr = data.speeds_original('train')
            te = data.speed_test_masked()
            df = pd.concat([tr, te])
            del tr
            del te
        
        elif self.mode == 'full':
            tr = data.speeds(mode='full')
            te = data.speeds_original('test2')
            df = pd.concat([tr, te])
            del tr
            del te
        
        f = df[['KEY', 'SPEED_AVG', 'SPEED_SD', 'SPEED_MIN', 'SPEED_MAX', 'N_VEHICLES']].groupby(['KEY']).mean().reset_index()\
                .rename(columns={'SPEED_AVG': 'avg_speed_street',\
                                'SPEED_SD': 'avg_speed_sd_street', \
                                'SPEED_MIN': 'avg_speed_min_street', \
                                'SPEED_MAX': 'avg_speed_max_street', \
                                'N_VEHICLES': 'avg_n_vehicles_street'})
        return f

if __name__ == '__main__':
    from src.utils.menu import mode_selection
    mode = mode_selection()
    c = AvgSpeedStreet(mode)

    print('Creating {}'.format(c.name))
    c.save_feature()

    print(c.read_feature(one_hot=True))