from maspy import *
from maspy.learning import *
from maspy.learning.core import HashableWrapper
from collections import deque
from random import choice
from threading import Lock
import heapq

class EpisodeEnvModel(EnvModel):
    def progress_bar(self, iterable, prefix="Episode", length=50):
        yield from super().progress_bar(iterable, "Episode", length)

class Walker(Agent):
    simulation_walkers = {}
    simulation_stats_lock = Lock()

    @classmethod
    def reset_simulation_stats(cls):
        with cls.simulation_stats_lock:
            cls.simulation_walkers = {}

    def __init__(self, name, map: Environment, episodes: int):
        super().__init__(name, max_intentions=1)
        self.map = map
        self.targets_to_find = map.targets_to_find
        self.last_reported_target_count = -1
        self.simulation_steps = 0
        self.search_completed = False
        self.filter_perceptions(add, focus, self.my_name)
        #self.show_slct = True
        #self.show_cycle = True
        model = EpisodeEnvModel(map, self, True)
        self.add_policy(model)
        state = model.env.get(Percept("agt_position", (Any, Any), self.my_name), ck_group=True)
        assert isinstance(state, Percept)
        initial_training_state = HashableWrapper((state.values, frozenset()))
        model.initial_states = {
            "position": [state.values],
            "found_targets": [frozenset()],
        }
        model.initial_state_distrib = [initial_training_state]
        model.curr_state = initial_training_state
        #print(f"Agent {self.my_name} starts at {state.values}")
        model.learn(qlearning, num_episodes=episodes)
        self.reset_knowledge()
        with self.simulation_stats_lock:
            self.simulation_walkers[self.my_name] = self
    
    def reset_knowledge(self):
        self.rm(Belief("Path_Graph", Any))
        self.add(Belief("Path_Graph", dict()))
        self.rm(Belief("Wall_Set", Any))
        self.add(Belief("Wall_Set", []))
        self.add(Belief("use_learn"))
        self.add(Goal("move"))

    def found_target_values(self):
        claimed = self.get(Belief("claimed_targets", Any, "Map"))
        return set(claimed.values) if claimed else set()

    def completed_target_search(self):
        found_count = len(self.found_target_values())
        if found_count != self.last_reported_target_count:
            status = "search complete" if found_count >= self.targets_to_find else "continuing search"
            self.print(f"Claimed {found_count}/{self.targets_to_find} targets; {status}")
            self.last_reported_target_count = found_count

        if found_count < self.targets_to_find:
            return False

        if not self.search_completed:
            self.search_completed = True
            self.print(
                f"Completed the simulation in {self.simulation_steps} steps"
            )
            self.stop_cycle()
            self.print_simulation_summary_if_complete()
        return True

    def print_simulation_summary_if_complete(self):
        with self.simulation_stats_lock:
            walkers = list(self.simulation_walkers.values())
            if not walkers or not all(walker.search_completed for walker in walkers):
                return

            print("\nSimulation step summary:")
            for walker in sorted(walkers, key=lambda item: item.my_name):
                print(f"  {walker.my_name}: {self.map.scores[walker.my_name]} points, {walker.simulation_steps} steps")
            for target, owner in self.map.claimed_targets.items():
                print(f"  Target {target} ({self.map.target_values[target]} points): {owner}")
            best_score = max(self.map.scores.values())
            winners = [name for name, score in self.map.scores.items() if score == best_score]
            print(f"Winner: {', '.join(winners)}")

    def move_and_count(self, direction):
        self.simulation_steps += 1
        self.move(direction)
    
    def update_map(self, position, direction):
        map_graph = self.get(Belief("Path_Graph", Any))
        wall_list = self.get(Belief("Wall_Set", Any))
        new_pos = self.get(Belief("agt_position", (Any,Any), "Map"))
        assert (map_graph and wall_list and new_pos), f"{map_graph} | {wall_list} | {new_pos}"
        if new_pos.values not in map_graph.values:
            old_graph = map_graph.values
            old_graph.setdefault(position, set()).add(new_pos.values)
            old_graph.setdefault(new_pos.values, set()).add(position)
            map_graph.change(values=old_graph)
        if new_pos.values == position and direction != "stay":
            match direction:
                case "up": wall_pos = (position[0],position[1]-1)
                case "down": wall_pos = (position[0],position[1]+1)
                case "left": wall_pos = (position[0]-1,position[1])
                case "right": wall_pos = (position[0]+1,position[1])
            walls = wall_list.values
            if wall_pos not in walls:
                walls.append(wall_pos)
                self.print(f"Driver {self.my_name} found a wall at {wall_pos} added to {walls}")
    
    @pl(gain, Goal("move"), Belief("agt_position", (Any,Any), "Map"))
    def make_move(self, src, position):
        found_targets = self.found_target_values()
        if self.has(Belief("use_learn")):
            direction, _ = self.get_best_action(
                "Map", (position, frozenset(found_targets))
            )
            self.print(f"From {position} Moving on a Learned Direction ({direction})")
        else:
            direction = choice(["up", "down", "left", "right"])
            self.print(f"From {position} Moving Randomly ({direction}) without a learned policy")
        self.move_and_count(direction) # Move Action

        self.perceive("Map") # Manual Perception of Map
        self.update_map(position, direction) # Update of Map/Wall Beliefs
            
        if not self.completed_target_search():
            return False # Retries current event 