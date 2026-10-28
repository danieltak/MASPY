from collections import Counter
import heapq

from maspy import Agent, Belief, Goal, Any, add, gain, focus, pl, atomic, broadcast, tell
from maspy.learning import EnvModel, qlearning


def choose_target(position, available):
    if not available:
        return None
    # O valor vem primeiro. Distância e coordenadas só desempatarão valores iguais.
    return min(available, key=lambda target: (
        -available[target],
        abs(position[0] - target[0]) + abs(position[1] - target[1]),
        target,
    ))


def astar_explore(start, goal, known, walls, map_size):
    width, height = map_size
    walls = set(walls)
    pending = [(0, start)]
    previous = {start: None}
    costs = {start: 0}
    while pending:
        _, current = heapq.heappop(pending)
        if current == goal:
            path = []
            while current is not None:
                path.append(current)
                current = previous[current]
            return path[::-1]
        x, y = current
        for neighbor in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
            if not (0 <= neighbor[0] < width and 0 <= neighbor[1] < height):
                continue
            if neighbor in walls:
                continue
            step_cost = 1 if neighbor in known.get(current, set()) else 1.25
            cost = costs[current] + step_cost
            if neighbor not in costs or cost < costs[neighbor]:
                costs[neighbor] = cost
                previous[neighbor] = current
                distance = abs(goal[0] - neighbor[0]) + abs(goal[1] - neighbor[1])
                heapq.heappush(pending, (cost + distance, neighbor))
    return None


def astar_direction(agent, position, target):
    graph = agent.get(Belief("Path_Graph", Any)).values
    walls = agent.get(Belief("Wall_Set", Any)).values
    path = astar_explore(position, target, graph, walls, agent.map_size)
    if not path or len(path) < 2:
        return "stay"
    dx, dy = path[1][0] - position[0], path[1][1] - position[1]
    return {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}[(dx, dy)]


class Walker(Agent):
    def __init__(self, name, map, episodes=1000):
        if episodes < 1:
            raise ValueError("O treinamento precisa de pelo menos um episódio.")
        super().__init__(name, max_intentions=1)
        self.map_size = map.map_size
        self.destination = None
        self.visits = Counter()
        self.using_path = False
        self.simulation_steps = 0
        self.search_completed = False
        self.filter_perceptions(add, focus, self.my_name)
        model = EnvModel(map, self)
        self.add_policy(model)
        # Cada episódio aprende a alcançar um destino, sem alterar a competição.
        model.learn(qlearning, num_episodes=episodes, max_steps=map.map_size[0] * map.map_size[1] * 4)
        self.add(Belief("Path_Graph", {}))
        self.add(Belief("Wall_Set", []))
        self.add(Goal("move"))

    def update_map(self, old_position, new_position, direction):
        graph_belief = self.get(Belief("Path_Graph", Any))
        walls_belief = self.get(Belief("Wall_Set", Any))
        graph = graph_belief.values
        if new_position != old_position:
            if new_position not in graph.get(old_position, set()):
                graph.setdefault(old_position, set()).add(new_position)
                graph.setdefault(new_position, set()).add(old_position)
                graph_belief.change(values=graph)
                self.send(broadcast, tell, Belief("Sent_Graph", graph))
        elif direction != "stay":
            dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[direction]
            wall = old_position[0] + dx, old_position[1] + dy
            width, height = self.map_size
            walls = walls_belief.values
            if 0 <= wall[0] < width and 0 <= wall[1] < height and wall not in walls:
                walls.append(wall)
                walls_belief.change(values=walls)
                self.send(broadcast, tell, Belief("Sent_Walls", walls))

    @pl(gain, Goal("move"), Belief("agt_position", (Any, Any), "Map"))
    def make_move(self, source, position):
        self.perceive("Map")
        position = self.get(Belief("agt_position", (Any, Any), "Map")).values
        available = self.get(Belief("available_targets", Any, "Map")).values
        target = choose_target(position, available)
        if target is None:
            self.search_completed = True
            self.stop_cycle()
            return
        if target != self.destination:
            self.destination = target
            self.visits.clear()
            self.using_path = False
            self.print(f"Buscando {target}, que vale {available[target]} pontos")
        self.visits[position] += 1
        if self.visits[position] >= 3:
            self.using_path = True
        if self.using_path:
            direction = astar_direction(self, position, target)
        else:
            direction, _ = self.get_best_action("Map", (position, target))
        old_score = self.get(Belief("score", Any, "Map")).values
        self.move(direction)
        self.simulation_steps += 1
        self.perceive("Map")
        new_position = self.get(Belief("agt_position", (Any, Any), "Map")).values
        self.update_map(position, new_position, direction)
        new_score = self.get(Belief("score", Any, "Map")).values
        if new_score > old_score:
            self.send(broadcast, tell, Belief("Target_Claimed", (new_position, self.my_name)))
        return False

    @pl(gain, Belief("Sent_Graph", Any), plan_type=atomic)
    def update_graph(self, source, received_graph):
        belief = self.get(Belief("Path_Graph", Any))
        graph = belief.values
        for position, neighbors in received_graph.items():
            graph.setdefault(position, set()).update(neighbors)
        belief.change(values=graph)

    @pl(gain, Belief("Sent_Walls", Any), plan_type=atomic)
    def update_walls(self, source, received_walls):
        belief = self.get(Belief("Wall_Set", Any))
        walls = sorted(set(belief.values) | set(received_walls))
        belief.change(values=walls)

    @pl(gain, Belief("Target_Claimed", (Any, Any)), plan_type=atomic)
    def target_claimed(self, source, claim):
        position, owner = claim
        if position == self.destination:
            self.destination = None
