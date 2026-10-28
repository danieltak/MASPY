import os
from time import monotonic

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

from maspy import Admin
from Map_Env import validate_settings

WINDOW_WIDTH, WINDOW_HEIGHT = 1200, 800
SIDEBAR_WIDTH = 330
BACKGROUND = (241, 243, 246)
INK = (34, 44, 62)
AGENT_COLORS = [(42, 103, 180), (139, 68, 173), (0, 134, 112), (205, 80, 67)]


def initialize_display(size, title):
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption(title)
    return pygame.display.set_mode(size)


def draw_text(screen, text, position, size=19, color=INK):
    font = pygame.font.SysFont("dejavusans", size)
    screen.blit(font.render(str(text), True, color), position)


class Button:
    def __init__(self, rect, text, callback):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.callback = callback

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self.callback()

    def draw(self, screen):
        hovered = self.rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(screen, (64, 95, 139) if hovered else (47, 70, 105), self.rect, border_radius=5)
        draw_text(screen, self.text, (self.rect.x + 12, self.rect.y + 8), 17, (255, 255, 255))


class TextInput:
    def __init__(self, rect, label, default):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.text = str(default)
        self.active = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.unicode in "0123456789.,":
                self.text += event.unicode

    def draw(self, screen):
        pygame.draw.rect(screen, (255, 255, 255), self.rect, border_radius=4)
        pygame.draw.rect(screen, (42, 103, 180) if self.active else (168, 177, 191), self.rect, 2, border_radius=4)
        draw_text(screen, self.label, (self.rect.x - 220, self.rect.y + 8), 18)
        draw_text(screen, self.text, (self.rect.x + 10, self.rect.y + 8), 18)


class MenuScreen:
    def __init__(self, settings=None):
        settings = settings or ((10, 10), 0.2, 2, 4, 1000)
        map_size, walls, _, agents, episodes = settings
        self.screen = initialize_display((620, 600), "Configurar competição")
        self.clock = pygame.time.Clock()
        self.inputs = [
            TextInput((310, 145, 180, 40), "Largura do mapa", map_size[0]),
            TextInput((310, 200, 180, 40), "Altura do mapa", map_size[1]),
            TextInput((310, 255, 180, 40), "Paredes (%)", walls * 100),
            TextInput((310, 310, 180, 40), "Agentes", agents),
            TextInput((310, 365, 180, 40), "Episódios de treino", episodes),
        ]
        self.start_button = Button((170, 465, 280, 42), "Iniciar competição", self.start)
        self.done = False
        self.settings = None
        self.error = ""

    def start(self):
        try:
            width, height = int(self.inputs[0].text), int(self.inputs[1].text)
            walls = float(self.inputs[2].text.replace(",", ".")) / 100
            agents, episodes = int(self.inputs[3].text), int(self.inputs[4].text)
            settings = ((width, height), walls, 2, agents, episodes)
            validate_settings(*settings)
            self.settings = settings
            self.done = True
        except ValueError as error:
            self.error = str(error) if "invalid literal" not in str(error) else "Preencha os campos com números válidos."

    def show_message(self, message):
        self.screen.fill(BACKGROUND)
        draw_text(self.screen, message, (45, 250), 20)
        pygame.display.flip()
        pygame.event.pump()

    def draw(self):
        self.screen.fill(BACKGROUND)
        draw_text(self.screen, "Walker competitivo", (65, 35), 28)
        draw_text(self.screen, "2 alvos: 10 e 30 pontos. Vence a maior pontuação.", (65, 85), 17)
        for field in self.inputs:
            field.draw(self.screen)
        self.start_button.draw(self.screen)
        if self.error:
            # As mensagens cabem em duas linhas, inclusive as do parser numérico.
            words, line, lines = self.error.split(), "", []
            for word in words:
                if len(line + word) > 53:
                    lines.append(line)
                    line = ""
                line += word + " "
            lines.append(line)
            for index, text in enumerate(lines[:2]):
                draw_text(self.screen, text, (35, 535 + index * 23), 16, (175, 40, 40))
        pygame.display.flip()

    def loop(self):
        while not self.done:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return None
                self.start_button.handle_event(event)
                for field in self.inputs:
                    field.handle_event(event)
            self.draw()
            self.clock.tick(30)
        return self.settings


class MapVisualizer:
    def __init__(self, env):
        self.env = env
        self.screen = initialize_display((WINDOW_WIDTH, WINDOW_HEIGHT), "Competição pelos alvos")
        self.clock = pygame.time.Clock()
        self.cell_size = min((WINDOW_WIDTH - SIDEBAR_WIDTH - 40) // env.map_size[0],
                             (WINDOW_HEIGHT - 40) // env.map_size[1])
        sidebar_x = WINDOW_WIDTH - SIDEBAR_WIDTH + 20
        self.buttons = [
            Button((sidebar_x, 70, 285, 40), "Pausar / continuar", Admin().pause_system),
            Button((sidebar_x, 120, 137, 40), "Mais lento", Admin().slower_cycle),
            Button((sidebar_x + 147, 120, 138, 40), "Mais rápido", Admin().faster_cycle),
        ]
        self.stop_reason = "concluída"

    def draw(self):
        result = self.env.get_results()
        self.screen.fill(BACKGROUND)
        cell = self.cell_size
        for x in range(self.env.map_size[0]):
            for y in range(self.env.map_size[1]):
                rect = pygame.Rect(20 + x * cell, 20 + y * cell, cell, cell)
                pygame.draw.rect(self.screen, (48, 57, 70) if (x, y) in self.env.walls else (255, 255, 255), rect)
                pygame.draw.rect(self.screen, (212, 218, 226), rect, 1)
        for target in result["targets"]:
            x, y = target["position"]
            rect = pygame.Rect(23 + x * cell, 23 + y * cell, cell - 6, cell - 6)
            color = (183, 193, 195) if target["owner"] else (244, 195, 91)
            pygame.draw.rect(self.screen, color, rect, border_radius=3)
            draw_text(self.screen, target["value"], (rect.x + 3, rect.y + 1), min(19, max(10, cell // 3)))
        for index, (name, position) in enumerate(result["positions"].items()):
            x, y = position
            center = 20 + x * cell + cell // 2, 20 + y * cell + cell // 2
            # Pequeno deslocamento mantém agentes na mesma célula distinguíveis.
            offset = (index % 3 - 1) * max(2, cell // 8)
            center = center[0] + offset, center[1] + cell // 6
            pygame.draw.circle(self.screen, AGENT_COLORS[index % len(AGENT_COLORS)], center, max(4, cell // 6))
            draw_text(self.screen, name.split("_")[-1], (center[0] - 4, center[1] - 8), min(15, max(10, cell // 4)), (255, 255, 255))
        x = WINDOW_WIDTH - SIDEBAR_WIDTH
        pygame.draw.rect(self.screen, (227, 232, 239), (x, 0, SIDEBAR_WIDTH, WINDOW_HEIGHT))
        draw_text(self.screen, "Competição", (x + 20, 22), 25)
        for button in self.buttons:
            button.draw(self.screen)
        draw_text(self.screen, "Alvos", (x + 20, 190), 21)
        for index, target in enumerate(result["targets"]):
            y = 225 + index * 45
            draw_text(self.screen, f"{target['value']} pontos em {target['position']}", (x + 20, y), 17)
            draw_text(self.screen, target["owner"] or "Disponível", (x + 20, y + 22), 15)
        draw_text(self.screen, "Placar / movimentos", (x + 20, 335), 20)
        for index, (name, score) in enumerate(sorted(result["scores"].items(), key=lambda item: -item[1])):
            draw_text(self.screen, f"{name}: {score} pts / {result['steps'][name]}", (x + 20, 370 + index * 18), 15)
        if result["finished"]:
            draw_text(self.screen, "Partida encerrada", (x + 20, 745), 18)
            draw_text(self.screen, "Vencedor: " + ", ".join(result["winners"]), (x + 20, 771), 16)
        elif self.stop_reason != "concluída":
            draw_text(self.screen, self.stop_reason, (x + 20, 745), 17)
        pygame.display.flip()

    def loop(self, timeout=120, max_moves=10000):
        started = monotonic()
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return "concluída" if self.env.finished else "janela fechada"
                for button in self.buttons:
                    button.handle_event(event)
            result = self.env.get_results()
            if not result["finished"] and self.stop_reason == "concluída":
                if monotonic() - started >= timeout:
                    self.stop_reason = "Limite de tempo atingido"
                elif sum(result["steps"].values()) >= max_moves:
                    self.stop_reason = "Limite de movimentos atingido"
                if self.stop_reason != "concluída":
                    Admin().start_event.set()
                    for agent in self.env._agents.values():
                        agent.stop_cycle()
            self.draw()
            self.clock.tick(30)
