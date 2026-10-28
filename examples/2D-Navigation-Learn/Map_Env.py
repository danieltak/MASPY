from collections import deque
from random import choice, sample
from threading import RLock
import random

from maspy import Environment, Percept, Any, action
from maspy.learning import listed


def validate_settings(map_size, walls, targets, agents, episodes):
    width, height = map_size
    if not (2 <= width <= 50 and 2 <= height <= 50):
        raise ValueError("Largura e altura devem ficar entre 2 e 50.")
    if not 0 <= walls <= 0.6:
        raise ValueError("Use de 0% a 60% de paredes.")
    if not 2 <= targets < width * height:
        raise ValueError("É preciso ter ao menos dois alvos e uma célula livre.")
    if not 2 <= agents <= 20:
        raise ValueError("Use pelo menos dois agentes, no máximo 20.")
    if not 1 <= episodes <= 10000:
        raise ValueError("Use entre 1 e 10000 episódios.")


def generate_map_with_walls(width, height, target_list, wall_prob=0.1, max_attempts=2000):
    target_set = set(target_list)
    for _ in range(max_attempts):
        walls = {
            (x, y) for x in range(width) for y in range(height)
            if random.random() < wall_prob and (x, y) not in target_set
        }
        # A busca sai de um único alvo. Começar pelos dois esconderia ilhas.
        pending = deque([target_list[0]])
        reachable = {target_list[0]}
        while pending:
            x, y = pending.popleft()
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                neighbor = x + dx, y + dy
                if not (0 <= neighbor[0] < width and 0 <= neighbor[1] < height):
                    continue
                if neighbor not in walls and neighbor not in reachable:
                    reachable.add(neighbor)
                    pending.append(neighbor)
        if len(reachable) == width * height - len(walls) and len(reachable) > len(target_set):
            return walls, sorted(reachable)
    raise RuntimeError("Não foi possível gerar um mapa conectado. Reduza a porcentagem de paredes.")


class Map(Environment):
    def __init__(self, map_size=(10, 10), walls_prob=0.2, targets=2):
        width, height = map_size
        if width < 1 or height < 1 or width * height <= targets:
            raise ValueError("O mapa precisa comportar os alvos e pelo menos uma posição inicial.")
        if not 0 <= walls_prob < 1:
            raise ValueError("A proporção de paredes deve estar entre 0 e 1, sem incluir 1.")
        if targets < 2:
            raise ValueError("A simulação precisa de pelo menos dois alvos.")
        super().__init__()
        self.map_size = map_size
        self.moves = {"up": (0, -1), "down": (0, 1), "right": (1, 0), "left": (-1, 0)}
        self.competition_lock = RLock()
        self.targets_to_find = targets
        self.claimed_targets = {}
        self.scores = {}
        self.steps = {}
        self.agent_positions = {}
        self.finished = False
        positions = [(x, y) for x in range(width) for y in range(height)]
        target_positions = sample(positions, targets)
        values = [10] + [30 + 20 * index for index in range(targets - 1)]
        self.target_values = dict(zip(target_positions, values))
        self.walls, self.open_positions = generate_map_with_walls(
            width, height, target_positions, walls_prob
        )
        for position in target_positions:
            self.create(Percept("target", position))
        for wall in self.walls:
            self.create(Percept("wall", wall))
        self.create(Percept("position", self.open_positions, listed))
        self.create(Percept("destination", target_positions, listed))
        self.possible_starts = "off-policy"

    def get_target_positions(self):
        return list(self.target_values)

    def on_connect(self, agent_name):
        with self.competition_lock:
            starts = [position for position in self.open_positions if position not in self.target_values]
            distances = {
                position: min(abs(position[0] - x) + abs(position[1] - y) for x, y in self.target_values)
                for position in starts
            }
            distant = [position for position in starts if distances[position] > self.map_size[0] / 2]
            if not distant:
                farthest = max(distances.values())
                distant = [position for position in starts if distances[position] == farthest]
            position = choice(distant)
            self.agent_positions[agent_name] = position
            self.scores[agent_name] = 0
            self.steps[agent_name] = 0
            self.create(Percept("agt_position", position, agent_name))
            self.create(Percept("available_targets", {}, agent_name))
            self.create(Percept("score", 0, agent_name))
            self.publish_status()

    def publish_status(self):
        available = {position: value for position, value in self.target_values.items()
                     if position not in self.claimed_targets}
        for name in self.scores:
            board = self.get(Percept("available_targets", Any, name), ck_group=True)
            board.change(values=(available.copy(),))
            score = self.get(Percept("score", Any, name), ck_group=True)
            score.change(values=(self.scores[name],))

    def _perception(self):
        with self.competition_lock:
            return super()._perception()

    def moviment(self, position, direction):
        dx, dy = self.moves[direction]
        x = max(0, min(position[0] + dx, self.map_size[0] - 1))
        y = max(0, min(position[1] + dy, self.map_size[1] - 1))
        return x, y

    def move_transition(self, position, destination, direction):
        next_position = self.moviment(position, direction)
        if self.has(Percept("wall", next_position)) or next_position == position:
            return position, -10, False
        if next_position == destination:
            return next_position, self.target_values[destination], True
        return next_position, -1, False

    @action(listed, ["up", "down", "left", "right"], move_transition)
    def move(self, agent_name, direction):
        if direction not in self.moves and direction != "stay":
            raise ValueError(f"Direção inválida: {direction}")
        # Movimento, pontuação e conquista acontecem juntos, inclusive com threads.
        with self.competition_lock:
            if self.finished:
                return
            position = self.agent_positions[agent_name]
            next_position = position if direction == "stay" else self.moviment(position, direction)
            self.steps[agent_name] += 1
            if next_position in self.walls:
                next_position = position
            self.agent_positions[agent_name] = next_position
            percept = self.get(Percept("agt_position", (Any, Any), agent_name), ck_group=True)
            percept.change(values=next_position)
            if next_position in self.target_values and next_position not in self.claimed_targets:
                value = self.target_values[next_position]
                self.claimed_targets[next_position] = agent_name
                self.scores[agent_name] += value
                self.create(Percept("arrived_target", next_position, agent_name))
                self.finished = len(self.claimed_targets) == len(self.target_values)
                self.publish_status()
                self.print(f"{agent_name} conquistou {next_position}: +{value} pontos")

    def get_results(self):
        with self.competition_lock:
            best_score = max(self.scores.values(), default=0)
            winners = [name for name, score in self.scores.items() if score == best_score]
            return {
                "finished": self.finished,
                "scores": self.scores.copy(),
                "steps": self.steps.copy(),
                "positions": self.agent_positions.copy(),
                "winners": winners if self.finished else [],
                "targets": [
                    {"position": position, "value": value, "owner": self.claimed_targets.get(position)}
                    for position, value in self.target_values.items()
                ],
            }
