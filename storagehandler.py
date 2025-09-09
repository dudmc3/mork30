## Copyright 2025 D.E.McFadden, III

## This file is part of Mork30.
## Mork30 is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License
## as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
## Mork30 is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty
## of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
## You should have received a copy of the GNU General Public License along with Mork30. If not, see <https://www.gnu.org/licenses/>.

import numpy as np
import matplotlib.pyplot as plt
from datetime import date

def showplots():
    'Display any created plot(s) interactively on screen'
    plt.show()

class Handler:

    # initialize
    def __init__(self, station_id, handle_init=True, volume_limit=0):
        self.volume_limit = volume_limit
        self.HANDLE_INIT = handle_init
        self.station_id = station_id

    def set_volume_limit(self, limit):
        # Usually set to volume at spillway; no collection above this
        self.volume_limit = limit

    def endyear(self):
        from datetime import date
        dt = self._storage[0][-1].astype(date)
        return dt.year

    def get_right_limit(self):
        from datetime import date
        #no! from dateutil.relativedelta import relativedelta
        dt = self._storage[0][-1].astype(date) #no! + relativedelta(months=1)
        return np.datetime64(dt.isoformat(), 'D')
        
    def extend_end(self):
        # Not for general use.
        # This extends the storage record out 31 days artificially.
        # It just takes the final value and duplicates it
        # This enables calculating a "draft version" of the analysis before you have T+30 days available
        dates = [self._storage[0][-1]+np.timedelta64(i,'D') for i in range(1,31)]
        storage = [self._storage[1][-1]] * 30
        flags = np.zeros(30, dtype=np.int8)
        self._storage = np.append(self._storage, [dates,storage,flags], axis=1)

    def set_beginnings(self, month=10, day=1):
        from datetime import date
        for i in range(len(self._storage[0])):
            dt = self._storage[0][i].astype(date)
            if dt.month == month and dt.day == day:
                # set the "beginning" flag
                self._storage[2][i] |= 4

    # This function supports identifying withdrawal of initial diversion to storage
    # Returns True if the reservoir passed through this elevation on zero or one prior days
    # since the beginning of the refill season
    def _hit_once(self, beginning, ind, st):
        ts = self._storage[1]
        if ind==0 or ind>len(ts): return False
        hitcount = 0
        for i in range(beginning, ind):
            if ts[i] <= st <= ts[i+1] or ts[i] >= st >= ts[i+1]: 
                hitcount += 1
                if hitcount > 1: return False
        return hitcount <= 1


    # Compute collection and withdrawal using the 30-day rule
    # Pass a numpy array with three columns:  obs_date, storage starting that date, and an integer
    # The integer has 4 bit flags, as documented in the book:
    #   bit 0:  strikeout, if set, skip processing this date
    #   bit 1:  (formerly italic) is not used anymore
    #   bit 2:  bold, if set, reset to start of collection period
    def compute_deltaS(self):

        storage = self._storage

        length = len(storage[0])
        collection_refill = np.zeros(length)
        withdrawal_after = np.zeros(length)
        regulation = np.zeros(length)
        collection_init = np.zeros(length)
        withdrawal_prereg = np.zeros(length)
        calcs = np.zeros(length)

        for ind in range(length-0-31):  # WAS:  -1
            storage_begin = storage[1][ind]  # for brevity and to avoid typographical errors in code
            storage_end = storage[1][ind+1]  # for brevity and to avoid typographical errors in code
            when = storage[0][ind]

            # disregard activity above the volume limit
            if self.volume_limit > 0:
                storage_begin = min(storage_begin, self.volume_limit)
                storage_end = min(storage_end, self.volume_limit)

            # calculate change in storage during today's date
            deltaStotal = storage_end - storage_begin

            # Look for the "strikeout" flag:  no storage or collection today
            if storage[2][ind] & 1:
                regulation[ind] = deltaStotal
                continue

            # Look for the "bold" flag:  reset the initial storage, start of collection season
            # The first data point evaluated also resets it
            if ind==0 or storage[2][ind] & 4:
                beginning = ind
                maxSeasonalStorage = storage[1][ind]
                priorMaxSeasonalStorage = maxSeasonalStorage
                lowestEver = maxSeasonalStorage

            # Handle increase in storage this day
            if deltaStotal > 0:
                lowestEver = min(lowestEver, storage_begin)

                # check for initial collection to storage
                if storage_end > maxSeasonalStorage and self.HANDLE_INIT:
                    # some of today's increase will be initial collection
                    assert storage_begin <= maxSeasonalStorage
                    priorMaxSeasonalStorage = maxSeasonalStorage
                    collection_init[ind] = storage_end - priorMaxSeasonalStorage
                    maxSeasonalStorage = storage_end
                    storage_end = priorMaxSeasonalStorage

                # Attention:  storage_end might have been adjsuted above!
                # And it might be equal to storage_begin in fact!
                # We are only examining the portion which was refill

                # Will we be releasing at least some of today's refill within a month?
                hit_storage = min(storage[1][ind+1 : ind+min(31, len(storage[1]))])
                if hit_storage < storage_end:
                    # yes, some or all of today's storage is regulation
                    regulation_start = max(hit_storage, storage_begin)
                    regulation[ind] = storage_end - regulation_start
                    assert regulation[ind] >= 0
                collection_refill[ind] = deltaStotal - regulation[ind] - collection_init[ind]
                assert collection_refill[ind] >= 0

            # Handle decrease in storage this day
            elif deltaStotal < 0:

                # divide into segments, analyze each one separately classify each
                if abs(deltaStotal) < 1.0:   # abs() added 06-Feb-2023
                    parts = 2
                else:
                    parts = 20
                deltaSpart = deltaStotal/parts
                for st in np.linspace(storage_begin, storage_end, parts+1)[1:]:
                    # (1) see if st has a hit_once.  If so, it's some kind of withdrawal 
                    # (2) else, apply the 30 day rule.  If so, it's all regulation
                    # (3) else, it's wd2 (post-regulation withdrawal)
                    if self._hit_once(beginning, ind, st) and self.HANDLE_INIT:
                        if regulation[ind] < 0:  # meaning, some regulation already happened today
                            withdrawal_after[ind] += deltaSpart
                        else:
                            withdrawal_prereg[ind] += deltaSpart
                    elif ind>0 and min(storage[1][ind-min(29, ind) : ind]) < st:
                        regulation[ind] += deltaSpart
                    else:
                        withdrawal_after[ind] += deltaSpart

                #print(deltaStotal, withdrawal_after[ind], withdrawal_prereg[ind], regulation[ind])
                assert abs(deltaStotal - (withdrawal_after[ind] + withdrawal_prereg[ind] + regulation[ind])) < .01

            # Check for no change in storage today
            else:
                pass # no change in storage today, just leave result arrays with zero

            #print(withdrawal_after[ind], collection_refill[ind], regulation[ind], storage[2][ind] & 2)

            # At least one of these must be zero every day
            assert withdrawal_after[ind] * collection_refill[ind] == 0

            # Check to see we properly accounted for this change in storage one way or another
            summation = withdrawal_after[ind] + collection_refill[ind] + regulation[ind] + withdrawal_prereg[ind] + collection_init[ind]
            if abs(summation-deltaStotal) >= .01:
                print(ind)
                print(withdrawal_after[ind], collection_refill[ind], regulation[ind], withdrawal_prereg[ind], collection_init[ind])
            assert abs(summation-deltaStotal) < .01

        self.cwr = np.row_stack((storage[0], collection_refill, withdrawal_after, regulation, collection_init, withdrawal_prereg, calcs))

    def summation(self):
        cwr = self.cwr
        return [cwr[1][i]+cwr[2][i]+cwr[3][i]+cwr[4][i]+cwr[5][i]   for i in range(len(cwr[1]))] 

    def store_daily_json(self, f):
        import json
        from datetime import date
        cwr_dict = [{
                'date': self.cwr[0][i].astype(date).strftime('%Y-%m-%d'),
                'coll': round(self.cwr[1][i]+self.cwr[4][i],2),
                'wd': round(-(self.cwr[2][i]+self.cwr[5][i]),2),
                'reg': round(self.cwr[3][i],2)
                } for i in range(len(self.cwr[1]))]
        json.dump(cwr_dict, f, ensure_ascii=False, indent=2)

class Plotter:
    'Plots the collection, withdrawal, and regulation time series'

    def __init__(self, handler, res_name, station_id, wateryear):
        self.handler = handler
        self.title, self.subtitle = f'{res_name} Storage Analysis', f"{station_id}, water year {wateryear}",
        plt.rcParams['font.family'] = 'sans-serif'
        # To customize the font add entries here; example is for Windows 10
        # plt.rcParams['font.sans-serif'] = ['Barlow Condensed', 'Gill Sans MT']
        self.fig, self.ax = plt.subplots(figsize=(9.0, 5.5))
        
    def make_plot(self):
        'Populate the axes with information'
        from matplotlib.dates import MonthLocator, DateFormatter, YearLocator, DayLocator
        import matplotlib.ticker as ticker
        self.fig.subplots_adjust(top=.93, right=.97)
        self.fig.text(1, 1, self.subtitle, fontsize=8, color='gray', horizontalalignment='right', verticalalignment='top')
        self.ax.set_title(self.title)

        # Draw gray line showing time series of storage
        self.plot_basic(marker='None', markersize=0)
        self.ax.set_xlim(right = self.handler.get_right_limit())
        self.plot_beginnings()

        # add time series of collection and withdrawal to the plot
        self.plot_ts()

        self.ax.set_xlabel('Start of months')
        self.ax.set_ylabel('Contents, acre-feet')
        self.ax.xaxis.set_major_locator(MonthLocator(bymonth=range(1,13,3)))
        self.ax.xaxis.set_minor_locator(MonthLocator())
        self.ax.xaxis.set_major_formatter(DateFormatter('%b\n%Y'))

        # Vertical month lines
        self.ax.grid(axis='x', which='both', alpha=.3, linestyle=':')

        # show spillway line, label it
        self.plot_limit_line()

    # Plots time series of storage given daily collection and withdrawal
    def plot_ts(self, annotate=False):
        initial = self.handler._storage[1][0]
        current_storage = initial

        for ind in range(len(self.handler.cwr[0])):
            midnight = self.handler.cwr[0][ind]
            collection_refill = self.handler.cwr[1][ind]
            withdrawal_after = self.handler.cwr[2][ind]
            regulation = self.handler.cwr[3][ind]
            collection_init = self.handler.cwr[4][ind]
            withdrawal_prereg = self.handler.cwr[5][ind]
            calc = self.handler.cwr[6][ind]

            ending_storage = current_storage + regulation + collection_refill + withdrawal_after + collection_init + withdrawal_prereg
            total = abs(regulation) + abs(withdrawal_after) + abs(withdrawal_prereg) + collection_refill + collection_init
            partday = lambda x: np.timedelta64(int(24*abs(x)), 'h')

            if ending_storage > current_storage:
                # Order is always:  collection_refill, regulation, collection_init

                x = midnight, midnight + partday(collection_refill/total)
                y = current_storage, current_storage + collection_refill
                if calc>0 and annotate:  self.ax.annotate(f'{calc:.0f}', (x[0],y[0]), fontsize=6)
                if collection_refill > 0:
                    self.ax.plot(x, y, color='darkgreen')

                x = x[1], x[1] + partday(regulation/total)
                y = y[1], y[1] + regulation
                # no plot, do nothing

                x = x[1], x[1] + partday(collection_init/total)
                y = y[1], y[1] + collection_init
                if collection_init > 0:
                    self.ax.plot(x, y, color='darkgreen')

            elif ending_storage < current_storage:
                order = (withdrawal_prereg, regulation, withdrawal_after)
                colors = ('darkgreen','none','darkgreen')


                x = midnight, midnight
                y = current_storage, current_storage
                if annotate:  self.ax.annotate(f'{calc:.0f}', (x[0],y[0]), fontsize=6)

                x = x[1], x[1] + partday(order[0]/total)
                y = y[1], y[1] + order[0]
                if order[0] != 0: self.ax.plot(x, y, color=colors[0])

                x = x[1], x[1] + partday(order[1]/total)
                y = y[1], y[1] + order[1]
                if order[1] != 0: self.ax.plot(x, y, color=colors[1])

                x = x[1], x[1] + partday(order[2]/total)
                y = y[1], y[1] + order[2]
                if order[2] != 0: self.ax.plot(x, y, color=colors[2])


            current_storage = ending_storage

    def plot_basic(self, marker='o', markersize=1):
        self.ax.plot(self.handler._storage[0], self.handler._storage[1], color='#909090', linewidth = .5, marker=marker, markersize=markersize)

    def plot_beginnings(self):
        if self.handler.HANDLE_INIT:
            for i in range(len(self.handler._storage[0])):
                if self.handler._storage[2][i] & 4:
                    self.ax.axvline(self.handler._storage[0][i], color='k')
        else:
            left,right = self.ax.get_xlim()
            top,bottom = self.ax.get_ylim()
            self.ax.annotate('init. coll. disregarded', (left,top), fontsize=6)
    
    def plot_limit_line(self):
        vl = self.handler.volume_limit
        if vl > 0:
            self.ax.axhline(vl, color='k', linewidth=.5, linestyle=':')
            left, right = self.ax.get_xlim()
            self.ax.annotate(f"{vl:,.0f}", (left, vl))


class Monthlies:
    "Utility for tabulating monthly diversion and withdrawal"

    def __init__(self, handler):
        # Returns an np array with month, collection, and withdrawal totals
        import calendar
        from datetime import date

        # only compute months for which our record is complete
        dt = [d.astype(date) for d in handler.cwr[0]]
        for start in range(len(dt)):
            if dt[start].day == 1: break
        ##print(f'Starting at {start}, {dt[start]}')
        for end in range(len(dt)-1, len(dt)-31, -1):
            daysin = calendar.monthrange(dt[end].year, dt[end].month)[1]
            if dt[end].day == daysin: break
        ##print(f'Ending at {end}, {dt[end]}')

        ym = []  # date of start of month
        cl = []  # monthly total collection (+)
        wd = []  # monthly total withdrawal (-)
        re = []  # monthly total net regulation (+ or -)
                 # regulation will be included as either direct diversion or available for free for rediversion later
        ind = start
        while ind <= end:
            assert dt[ind].day == 1
            y, m = dt[ind].year, dt[ind].month
            ym.append(np.datetime64(f'{y:04d}-{m:02d}-01'))
            daysin = calendar.monthrange(dt[ind].year, dt[ind].month)[1]
            total = lambda i: sum(handler.cwr[i][ind:ind+daysin])
            cl.append(total(1) + total(4))
            wd.append(total(2) + total(5))
            re.append(total(3))
            ind += daysin

        # DEBUG
        checksum1 = sum(handler.cwr[1][start:end+1]+handler.cwr[2][start:end+1]+handler.cwr[3][start:end+1]+handler.cwr[4][start:end+1]+handler.cwr[5][start:end+1])
        checksum2 = sum(cl+wd+re)
        assert abs(checksum1 - checksum2) < .1

        self.monthlies = np.array([ym,cl,wd,re])

    def plot_tabulate(self, ax):
        # Make room for and print the storage and collection time series
        # Uses Matplotlib.  Pass it an axes reference.
        bottom, top = ax.get_ylim()
        ax.set_ylim(bottom=bottom-(top-bottom)/8)
        left, right = ax.get_xlim()
        ax.set_xlim(left = left - np.timedelta64(31, 'D').astype(float))
        ax.annotate('Month:\nColl:\nWthdrl:\nReg:', (left,bottom), fontsize=8, ha='right', va='top', color='k')
        for ind in range(len(self.monthlies[0])):
            ym = self.monthlies[0][ind] + np.timedelta64(27, 'D')
            mon = self.monthlies[0][ind].astype(date).strftime('%b')
            col, wd, reg = self.monthlies[1][ind], self.monthlies[2][ind], self.monthlies[3][ind]
            col_wd_reg = f"{mon} \n{col:.0f} \n{-wd+.01:.0f} \n"
            if reg >= 0:
                col_wd_reg += f"{reg:.0f} "
            else:
                col_wd_reg += f"({-reg:.0f})"
            ax.annotate(col_wd_reg, (ym,bottom), fontsize=8, ha='right', va='top', color='k')

    def text_tabulate(self, f):
        # T account style listing
        #         123456781234567812345678
        header = 'Month      Debit  Credit\n'
        f.write('Collection to storage and withdrawal\n')
        f.write(header)
        for ind in range(len(self.monthlies[0])):
            mon = self.monthlies[0][ind].astype(date).strftime('%b')
            col, wd, reg = self.monthlies[1][ind], self.monthlies[2][ind], self.monthlies[3][ind]
            f.write(f'{mon}     {col:8.0f}{-wd:8.0f}\n')
        f.write('\n')
        f.write('Regulation, as direct diversion(+) and as use(–)\n')
        f.write(header)
        for ind in range(len(self.monthlies[0])):
            mon = self.monthlies[0][ind].astype(date).strftime('%b')
            col, wd, reg = self.monthlies[1][ind], self.monthlies[2][ind], self.monthlies[3][ind]
            if reg>0:
                dr, cr = reg,0
            else:
                dr, cr = 0, -reg
            f.write(f'{mon}     {dr:8.0f}{cr:8.0f}\n')

    def plot_bar(self, ax):
        # upward bars for collection, downward for withdrawal, plus additional for regulation
        for item in (self.monthlies[1], self.monthlies[2]):
            p = ax.bar(self.monthlies[0],item, width=np.timedelta64(30, 'D'), align='edge', color='tab:blue')
            #ax.bar_label(p, label_type='center', padding=12)
        ax.axhline(0, color='k')
        ax.spines.right.set_visible(False)
        ax.spines.top.set_visible(False)
        ax.spines.bottom.set_visible(False)
        ax.tick_params(axis='x', which='both', color='None')
