import argparse
from contextlib import nullcontext, redirect_stdout
import json
import os
from pathlib import Path
import random
import sys
from threading import Thread
from time import monotonic, sleep

# Permite executar este arquivo de qualquer pasta e também dentro do ZIP.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from maspy import Admin
from Map_Env import Map, validate_settings
from Walker_Ag import Walker


def stop_walkers(walkers):
    Admin().start_event.set()  # Libera também os agentes que estiverem pausados.
    for walker in walkers:
        walker.stop_cycle()
    for walker in walkers:
        if walker.thread is not None:
            walker.thread.join(timeout=2)


def print_results(result):
    print("\nResultado da competição")
    for name, score in sorted(result["scores"].items(), key=lambda item: -item[1]):
        print(f"  {name}: {score} pontos, {result['steps'][name]} movimentos")
    for target in result["targets"]:
        print(f"  Alvo {target['position']} ({target['value']} pontos): {target['owner'] or 'disponível'}")
    if result["finished"]:
        label = "Vencedor" if len(result["winners"]) == 1 else "Empate"
        print(f"{label}: {', '.join(result['winners'])}")
    else:
        print(f"Partida interrompida: {result['stop_reason']}")


def main():
    parser = argparse.ArgumentParser(description="Walker competitivo com alvos de valores diferentes")
    parser.add_argument("--headless", action="store_true", help="Executa pelo terminal, sem abrir janela")
    parser.add_argument("--quiet", action="store_true", help="Mostra somente o resultado final")
    parser.add_argument("--width", type=int, default=10)
    parser.add_argument("--height", type=int, default=10)
    parser.add_argument("--walls", type=float, default=20, help="Porcentagem de paredes (0 a 60)")
    parser.add_argument("--agents", type=int, default=4)
    parser.add_argument("--episodes", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--delay", type=float, default=0.05)
    parser.add_argument("--timeout", type=float, default=120, help="Limite da partida, em segundos, após o treino")
    parser.add_argument("--max-moves", type=int, default=10000)
    parser.add_argument("--output", type=Path, help="Salva o resultado em JSON")
    args = parser.parse_args()
    settings = ((args.width, args.height), args.walls / 100, 2, args.agents, args.episodes)
    try:
        validate_settings(*settings)
        if not all(np.isfinite(value) for value in [args.delay, args.timeout]) or args.delay < 0 or args.timeout <= 0 or args.max_moves < 1:
            raise ValueError("Atraso deve ser positivo ou zero; limites de tempo e movimentos devem ser positivos.")
    except ValueError as error:
        parser.error(str(error))
    random.seed(args.seed)
    np.random.seed(args.seed)
    if not args.headless:
        from Pygame_Screens import MenuScreen
        menu = MenuScreen(settings)
        settings = menu.loop()
        if settings is None:
            return 0
        menu.show_message("Treinando os agentes. Aguarde...")
    started_training = monotonic()
    with open(os.devnull, "w") as silent_output:
        capture = redirect_stdout(silent_output) if args.quiet else nullcontext()
        with capture:
            map_size, walls, targets, agents, episodes = settings
            try:
                environment = Map(map_size, walls, targets)
            except (ValueError, RuntimeError) as error:
                parser.error(str(error))
            walkers = [Walker("walker", environment, episodes) for _ in range(agents)]
            training_seconds = monotonic() - started_training
            Admin().slow_cycle_by(args.delay)
            system = Thread(target=Admin().start_system, daemon=True)
            system.start()
            started = monotonic()
            stop_reason = "concluída"
            try:
                if args.headless:
                    while not environment.get_results()["finished"]:
                        if monotonic() - started >= args.timeout:
                            stop_reason = "limite de tempo"
                            break
                        if sum(environment.get_results()["steps"].values()) >= args.max_moves:
                            stop_reason = "limite de movimentos"
                            break
                        sleep(0.01)
                else:
                    from Pygame_Screens import MapVisualizer
                    stop_reason = MapVisualizer(environment).loop(args.timeout, args.max_moves)
            except KeyboardInterrupt:
                stop_reason = "interrompida pelo usuário"
            finally:
                stop_walkers(walkers)
                system.join(timeout=5)
    result = environment.get_results()
    result.update({"stop_reason": stop_reason, "training_seconds": round(training_seconds, 3),
                   "config": {"map_size": map_size, "walls_percent": walls * 100, "agents": agents,
                              "episodes": episodes, "seed": args.seed}})
    print_results(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result["finished"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
