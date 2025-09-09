## Copyright 2025 D.E.McFadden, III

## This file is part of Mork30.
## Mork30 is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License
## as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
## Mork30 is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty
## of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
## You should have received a copy of the GNU General Public License along with Mork30. If not, see <https://www.gnu.org/licenses/>.

import storagehandler
import requests, json
from datetime import date, timedelta, datetime
from bs4 import BeautifulSoup
import numpy as np

def get_daily_station_info(station_id):
    r = requests.get(f'https://cdec.water.ca.gov/dynamicapp/QueryDaily?s={station_id}')
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    t = soup.find('title')
    station_name = t.string[:t.string.find('(') - 1] #remove the parentheses and station id
    return station_name.title()

def confirm_ok(station_id, sensor_num=15, dur_code='D') -> bool:
    'Fetches JSON formatted data...just one...to validate the station_id, sensor_num, and dur_code'
    start = end = date.today()
    url = f'https://cdec.water.ca.gov/dynamicapp/req/JSONDataServlet?Stations={station_id}&SensorNums={sensor_num}&dur_code={dur_code}&Start={start.isoformat()}&End={end.isoformat()}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        jtext = response.json()
    except requests.exceptions.RequestException as e:
        print(f'Attempt to pull CDEC data failed: {e}')
        return
    return len(jtext) != 0

class CdecDailyResAdapter:
    "Very basic interface to CDEC's JSON data servlet, to retrieve daily reservoir contents time series"
    def __init__(self, debug=False):
        self.debug = debug

    def _fetch_data(self, station_id, start, nbr_years, sensor_num=15, dur_code='D') -> dict:
        'Fetches JSON formatted time series from CDEC'
        end = start + timedelta(366 * nbr_years + 62)
        self.url = f'https://cdec.water.ca.gov/dynamicapp/req/JSONDataServlet?Stations={station_id}&SensorNums={sensor_num}&dur_code={dur_code}&Start={start.isoformat()}&End={end.isoformat()}'
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            jtext = response.json()
        except requests.exceptions.RequestException as e:
            print(f'Attempt to pull CDEC data failed: {e}')
            return
        if len(jtext) == 0:
            raise ValueError(f'No CDEC data available from station_id {station_id}, sensor_num {sensor_num}, dur_code {dur_code}')
        ts = []
        previous_obs_value = -1
        if self.debug:
                with open('debug.json', 'w', encoding='utf-8') as debug_out:
                    json.dump(jtext, debug_out, ensure_ascii=False, indent=2)
        for row in jtext:
            obs_date = np.datetime64(datetime.strptime(row['date'], "%Y-%m-%d %H:%M").date())
            obs_value = float(row['value'])

            # Following section does rudimetary bad-data screening, needs work!
            if previous_obs_value < 0: previous_obs_value = obs_value
            if obs_value < 0: obs_value = previous_obs_value

            ts.append([obs_date, obs_value])
            previous_obs_value = obs_value
        return np.array(ts)

    def fill(self, handler:storagehandler.Handler, starting_date, nbr_years=1):
        'Load 1-day sampled storage at time 00:00 data from CDEC'

        dtst = self._fetch_data(handler.station_id, starting_date, nbr_years)
        storage = dtst[:,1]
        dt = dtst[:,0]
        flags = np.zeros(len(dt), dtype=np.int8)
        handler._storage = np.array([dt, storage, flags])