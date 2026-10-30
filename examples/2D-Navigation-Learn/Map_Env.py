from maspy import *
from maspy.learning import *
from collections import deque
from random import choice, sample
from threading import Lock
import random

def generate_map_with_walls(
    width: int,
    height: int,
    target_list: list[tuple[int, int]],
    wall_prob: float = 0.1,
    max_attempts: int = 2000,
):
    def neighbors(x, y):
        for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
            nx, ny = x+dx, y+dy
            if 0 <= nx < width and 0 <= ny < height:
                yield nx, ny

    target_set = set(target_list)

    for _ in range(max_attempts):
        walls = {(x, y) for x in range(width) for y in range(height)
                 if random.random() < wall_prob and (x, y) not in target_set}

        queue = deque(target_list)
        reachable = set(target_list)
        while queue:
            cx, cy = queue.popleft()
            for nx, ny in neighbors(cx, cy):
                if (nx, ny) not in walls and (nx, ny) not in reachable:
                    reachable.add((nx, ny))
                    queue.append((nx, ny))

        total_open = width * height - len(walls)
        if len(reachable) == total_open:
            available = sorted(reachable)
            return walls, available

    raise RuntimeError("Failed to generate a valid map.")

class Map(Environment):
    def __init__(self, map_size=(10, 10), walls_prob=0.1, targets=2):
        super().__init__()
        minimum_targets = 2
        self.targets_to_find = targets
        self.target_values = {}
        self.claimed_targets = {}
        self.scores = {}
        self.competition_lock = Lock()
        self.moves = {
            "up": (0, -1),"down": (0, 1), 
            "right": (1, 0), "left": (-1, 0),
        }
        self.map_size = map_size

        map_positions = [
            (x, y)
            for x in range(self.map_size[0])
            for y in range(self.map_size[1])
        ]
        if not minimum_targets <= targets <= len(map_positions):
            raise ValueError(
                f"targets must be between {minimum_targets} and "
                f"{len(map_positions)}, got {targets}"
            )

        targets_list = sample(map_positions, targets)
        for n, target in enumerate(targets_list):
            self.target_values[target] = 10 + 20 * n
            self.print(f"Target{n+1} is at {target}: {self.target_values[target]} points")
            self.create(Percept("target", target))
        
        positions = generate_map_with_walls(map_size[0], map_size[1], targets_list, walls_prob, 2000)

        for wall in positions[0]:
            self.create(Percept("wall", wall))
        self.create(Percept("position", positions[1], listed))
        self.possible_starts = "off-policy"

    def get_target_positions(self) -> list[tuple[int, int]]:
        targets = self.get(Percept("target", (Any, Any)), all=True)
        if not isinstance(targets, list):
            return []
        return [target.values for target in targets]
    
    def reset_positions(self, og_pos):
        found_pos = self.get(Percept("arrived_target", (Any, Any)), all=True)
        assert isinstance(found_pos, list)
        self.delete(found_pos)
        new_pos_prcpts = self.get(Percept("agt_position", (Any, Any)), all=True)
        assert isinstance(new_pos_prcpts, list)
        for pos_prcpt in new_pos_prcpts:
            pos_prcpt.change(values=og_pos[pos_prcpt.group])

    def on_connect(self, agt):
        target_positions = self.get_target_positions()
        open_positions = [
            (x, y)
            for x in range(self.map_size[0])
            for y in range(self.map_size[1])
            if not self.has(Percept("wall", (x, y)))
            and (x, y) not in target_positions
        ]
        if not open_positions:
            raise RuntimeError("No open position is available for an agent.")

        def distance_to_closest_target(position):
            return min(
                abs(position[0] - target[0]) + abs(position[1] - target[1])
                for target in target_positions
            )

        distant_positions = [
            position
            for position in open_positions
            if distance_to_closest_target(position) > self.map_size[0] / 2
        ]
        if not distant_positions:
            greatest_distance = max(map(distance_to_closest_target, open_positions))
            distant_positions = [
                position
                for position in open_positions
                if distance_to_closest_target(position) == greatest_distance
            ]

        start_pos = choice(distant_positions)
        self.create(Percept("agt_position", start_pos, agt))
        self.scores[agt] = 0
        self.create(Percept("claimed_targets", [], agt))
        #print(f"MAP> Agent {agt} starts at {start_pos}")
    
    def moviment(self, position, direction):
        dx, dy = self.moves[direction]
        new_x = max(0, min(position[0] + dx, self.map_size[0] - 1))
        new_y = max(0, min(position[1] + dy, self.map_size[1] - 1)) 
        return new_x, new_y
    
    def move_transition(self, position, found_targets, direction):
        reward = -1
        terminated = False

        found_targets = frozenset(found_targets)
        new_position = self.moviment(position, direction)
        new_found_targets = found_targets

        if (
            new_position in self.get_target_positions()
            and self.target_values[new_position] not in found_targets
        ):
            new_found_targets = found_targets | {self.target_values[new_position]}
            reward = self.target_values[new_position]
            terminated = len(new_found_targets) == self.targets_to_find
        elif self.target_values.get(new_position) in found_targets:
            reward = -5
        elif self.has(Percept("wall", new_position)) or position == new_position:
            reward = -10
        return new_position, new_found_targets, reward, terminated
    
    @action(listed, ["up", "down", "left", "right"], move_transition)
    def move(self, agt, direction):
        position = self.get(Percept("agt_position", (Any, Any), agt), ck_group=True)
        assert isinstance(position, Percept)
        
        wall_flag = False
        pos = position.values
        if direction == "stay":
            new_pos = pos
        else:
            new_pos = self.moviment(pos, direction)
            if self.has(Percept("wall", new_pos)):
                wall_flag = True
                new_pos = pos
            else:
                position.change(values=new_pos)
        
        n_pos = self.get(Percept("agt_position", (Any, Any), agt), ck_group=True).values
        if n_pos in self.get_target_positions():
            with self.competition_lock:
                if n_pos not in self.claimed_targets:
                    self.claimed_targets[n_pos] = agt
                    self.scores[agt] += self.target_values[n_pos]
                    self.create(Percept("arrived_target", n_pos, agt))
                    claimed_values = [self.target_values[target] for target in self.claimed_targets]
                    for agent_name in self.scores:
                        claimed = self.get(Percept("claimed_targets", Any, agent_name), ck_group=True)
                        claimed.change(values=(claimed_values,))
                    self.print(f"{agt} claimed target worth {self.target_values[n_pos]} points")
        elif wall_flag:
            self.print(f"{agt} in {pos} moves {direction} but hits a wall")
        else:
            self.print(f"{agt} in {pos} moves {direction} to {n_pos}")
