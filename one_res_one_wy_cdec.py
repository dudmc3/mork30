## Copyright 2025 D.E.McFadden, III

## This file is part of Mork30.
## Mork30 is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License
## as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
## Mork30 is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty
## of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
## You should have received a copy of the GNU General Public License along with Mork30. If not, see <https://www.gnu.org/licenses/>.

# Storage collection to and withdrawal from other reservoirs
# specify the CDEC station ID and wateryear as command-line arguments
import sys, os
from pathlib import Path
import cdecpuller
from storagehandler import Handler, Plotter, Monthlies, showplots
from datetime import date


def one_res(station_id, wateryear, initialcoll=True, output_dir=None, nbr_years=1):
    "Produce 30-day storage analysis for one reservoir, one or more water years"

    # Ensure output directory is available
    if output_dir != None:
        if not os.path.isdir(output_dir): os.mkdir(output_dir)

    # Connect to a new Handler and set up its boundary conditions
    print(f'Setting up {station_id} for wateryear {wateryear}')
    handler = Handler(station_id, handle_init=initialcoll)
    res_name = cdecpuller.get_daily_station_info(station_id)

    # get data from CDEC
    # here is where you would replace cdecpuller with your own class which accesses your
    # company's water-resources time series data store
    print(f'Retrieving daily midnight readings from {res_name}')
    adapter = cdecpuller.CdecDailyResAdapter()
    adapter.fill(handler, date(wateryear-1, 9, 1), nbr_years=nbr_years)

    # Initialize look-back and look-ahead 30 days features
    handler.set_beginnings()

    # compute collection, withdrawal, and regulation
    print('Calculating 30-day rule storage')
    handler.compute_deltaS()

    # make a diagnostic plot
    print('Plotting')
    plotter = Plotter(handler, res_name, station_id, wateryear)
    plotter.make_plot()

    # Obtain monthly summations, add to plot
    monthly_summations = Monthlies(handler)
    monthly_summations.plot_tabulate(plotter.ax)

    # Provide monthly totals as text table and dailies as JSON
    if output_dir != None:
        dest = Path(output_dir)
        with open(dest / f'{station_id} monthly storage {wateryear}.txt', 'w') as f:
            f.write(f'{station_id} {res_name} storage analysis for water year {wateryear}\n\n')
            monthly_summations.text_tabulate(f)

        # Provide daily values to JSON text file
        with open(dest / f'{station_id} daily storage {wateryear}.json', 'w', encoding='utf-8') as f:
            handler.store_daily_json(f)
        
        # Save a copy of the plot
        plotter.fig.savefig(dest / f'{station_id} {wateryear}.svg')


# Main program
if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f'usage: {sys.argv[0]} station_id wateryear')
    else:
        station_id, wateryear = sys.argv[1].upper(), int(sys.argv[2])
        if not cdecpuller.confirm_ok(station_id):
            print(f'No CDEC daily reservoir storage station {station_id}')
        else:
            # Demonstration: one water year, don't save output, handle initial collection to storage
            one_res(station_id, wateryear)
            
            # Another example; two water years, save output in a sibling folder
            #one_res(station_id, wateryear, nbr_years=2, output_dir='../sa')
            
            showplots()