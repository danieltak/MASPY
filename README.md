# Projeto Inicial - Walker competitivo

Trabalho de Sistemas Multiagentes da UTFPR, de Antonio Galvão Martins Neto e
Daniel Watanabe. Adaptação do exemplo Navigation on 2D Grid do MASPY.

Os agentes disputam dois alvos, de **10 e 30 pontos**. Cada alvo pertence ao
primeiro agente que chegar. Os Walkers priorizam o maior valor disponível e
continuam até os dois alvos serem conquistados. Vence a maior pontuação.

## Executar

Use **Python 3.12 ou 3.13**. O framework MASPY está incluído em `maspy/`;
não é necessário instalar outra versão do MASPY pelo pip.

Na raiz do projeto:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python examples/2D-Navigation-Learn/Walker_Main.py
```

No Windows, os dois primeiros comandos são:

```bat
py -3.13 -m venv .venv
.venv\Scripts\activate
```

A janela permite alterar o mapa, a porcentagem de paredes, os agentes e os
episódios de treino. O treinamento acontece antes da partida e pode levar alguns
segundos. Para uma primeira demonstração rápida, use 100 episódios. Depois,
compare com 1000 episódios. O quadro público informa os alvos; as paredes são
descobertas na execução ou aprendidas indiretamente no modelo de treinamento.

A tela mostra os valores, os donos dos alvos, o placar, os movimentos e o vencedor.
As cores dos agentes se repetem a cada quatro; o número identifica cada Walker.
Agentes podem compartilhar uma célula. Os botões controlam a pausa e a velocidade.
Feche a janela para terminar o programa após visualizar o resultado.

## Executar pelo terminal

```bash
python examples/2D-Navigation-Learn/Walker_Main.py --headless --quiet --episodes 100 --seed 42 --output resultado.json
```

Parâmetros disponíveis em `--help`:

| Parâmetro | Padrão | Descrição |
| --- | --- | --- |
| `--width`, `--height` | 10 | Dimensões, entre 2 e 50 |
| `--walls` | 20 | Porcentagem de paredes, entre 0 e 60 |
| `--agents` | 4 | Quantidade de agentes, entre 2 e 20 |
| `--episodes` | 1000 | Episódios de treinamento por agente, de 1 a 10000 |
| `--seed` | 42 | Semente para o mapa e os sorteios do treinamento |
| `--delay` | 0.05 | Atraso do ciclo, em segundos |
| `--timeout` | 120 | Limite da partida após o treino, incluindo pausas |
| `--max-moves` | 10000 | Limite aproximado de movimentos do conjunto de agentes |
| `--output` | nenhum | Caminho do resultado JSON |
| `--headless` | desativado | Executa sem Pygame e sem abrir janela |
| `--quiet` | desativado | Oculta os logs do MASPY e mostra o resultado final |

O contador inclui tentativas bloqueadas por paredes e bordas. Os limites são
verificados periodicamente e podem ultrapassar alguns movimentos antes da parada.
Uma partida interrompida não declara vencedor e retorna código 1. Uma partida
concluída retorna 0; parâmetros inválidos retornam 2.

A semente não fixa a ordem de execução das threads. O vencedor e a quantidade de
movimentos podem mudar entre execuções com a mesma configuração.

## Código

- `examples/2D-Navigation-Learn/Map_Env.py`: grade, treino, percepções e conquista exclusiva.
- `examples/2D-Navigation-Learn/Walker_Ag.py`: agente BDI, prioridade por valor, Q-learning, A* e mensagens.
- `examples/2D-Navigation-Learn/Pygame_Screens.py`: configuração e visualização.
- `examples/2D-Navigation-Learn/Walker_Main.py`: entrada do programa e limites da execução.

O estado do treino é `(posição, destino)`. Chegar ao destino dá a recompensa do
alvo; colisões dão -10 e outros passos dão -1. O treino é individual e não disputa
pontos reais. Ao repetir uma posição três vezes na partida, o agente usa A* com as
paredes conhecidas até escolher outro destino. As mensagens compartilham caminhos,
paredes e conquistas; o ambiente decide a propriedade do alvo usando um lock.

## Créditos

Base: MASPY, de LaCA/UTFPR, e implementação inicial de Daniel na branch
`feature/projeto_inicial`. O framework mantém sua licença MIT em `LICENSE`.
