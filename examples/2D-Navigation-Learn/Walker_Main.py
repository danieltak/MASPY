import sys
from pathlib import Path

# Inclui o MASPY local ao executar este arquivo diretamente.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from maspy import *

from Map_Env import Map
from Walker_Ag import Walker
from Pygame_Screens import MapVisualizer, MenuScreen
from threading import Thread

if __name__ == '__main__':
    Admin(listener_log=True)
    Channel().show_exec = True
    menu = MenuScreen()
    settings = menu.loop()
    if settings:
        map_size, walls_perc, num_targets, num_walkers, episodes = settings
        map = Map(map_size, walls_perc, num_targets)
        walkers = []
        Walker.reset_simulation_stats()
        for _ in range(num_walkers):
            wlk = Walker("wk", map, episodes)
            walkers.append(wlk)
        Admin().slow_cycle_by(0.2)
        Thread(target=Admin().start_system, daemon=True).start()
        #Thread(target=start_interface, daemon=True).start()
        vis = MapVisualizer(map)
        vis.loop()
