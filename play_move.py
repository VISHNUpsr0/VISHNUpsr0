"""
Chess-vs-bot game engine, driven by GitHub Issue comments.

Triggered by the chess-bot.yml workflow on every new comment on the
"Chess vs Bot" issue. Reads the current position from state.fen,
applies the commenter's move, lets Stockfish reply, re-renders
board.svg, and posts a comment with the result.

Human always plays White. Comment `new game` (or `reset`) at any
time to start over.
"""

import json
import os
import urllib.request

import chess
import chess.engine
import chess.svg

STATE_FILE = "chess-bot/state.fen"
BOARD_FILE = "chess-bot/board.svg"

COMMENT_BODY = os.environ["COMMENT_BODY"]
ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]
TOKEN = os.environ["GH_TOKEN"]
REPO = os.environ["REPO"]

STARTING_FEN = chess.STARTING_FEN


def post_comment(body: str) -> None:
    url = f"https://api.github.com/repos/{REPO}/issues/{ISSUE_NUMBER}/comments"
    data = json.dumps({"body": body}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    urllib.request.urlopen(req)


def load_board() -> chess.Board:
    if os.path.exists(STATE_FILE):
        fen = open(STATE_FILE).read().strip()
        if fen:
            return chess.Board(fen)
    return chess.Board()


def save_state(board: chess.Board, lastmove: "chess.Move | None" = None) -> None:
    with open(STATE_FILE, "w") as f:
        f.write(board.fen())
    svg = chess.svg.board(board=board, lastmove=lastmove, size=400)
    with open(BOARD_FILE, "w") as f:
        f.write(svg)


def parse_move(board: chess.Board, text: str):
    token = text.strip().split()[0].strip(".,!") if text.strip() else ""
    try:
        return board.parse_uci(token)
    except Exception:
        pass
    try:
        return board.parse_san(token)
    except Exception:
        return None


def result_message(board: chess.Board) -> "str | None":
    # Human is always White. Whoever's turn it is when the game ends
    # is the side that has no legal moves.
    if board.is_checkmate():
        return "Checkmate! " + ("You win! 🎉" if board.turn == chess.BLACK else "Bot wins! 🤖")
    if board.is_stalemate():
        return "🤝 Stalemate — it's a draw."
    if board.is_insufficient_material():
        return "🤝 Draw — insufficient material to continue."
    if board.can_claim_fifty_moves():
        return "🤝 Draw claimed (fifty-move rule)."
    if board.can_claim_threefold_repetition():
        return "🤝 Draw claimed (threefold repetition)."
    return None


def find_engine_path() -> str:
    for candidate in ("stockfish", "/usr/games/stockfish", "/usr/bin/stockfish"):
        try:
            chess.engine.SimpleEngine.popen_uci(candidate).quit()
            return candidate
        except Exception:
            continue
    raise RuntimeError("Stockfish binary not found on PATH")


def main() -> None:
    lowered = COMMENT_BODY.strip().lower()

    if "new game" in lowered or lowered == "reset":
        board = chess.Board()
        save_state(board)
        post_comment(
            "♟️ New game started! You're **White** — comment your move "
            "(e.g. `e4` or `e2e4`)."
        )
        return

    board = load_board()

    if board.is_game_over():
        post_comment("This game is already over — comment `new game` to start a fresh one.")
        return

    move = parse_move(board, COMMENT_BODY)
    if move is None or move not in board.legal_moves:
        post_comment(
            f"❓ I couldn't read that as a legal move: `{COMMENT_BODY.strip()}`.\n"
            "Use UCI (`e2e4`) or SAN (`e4`, `Nf3`, `O-O`)."
        )
        return

    board.push(move)
    over = result_message(board)
    if over:
        save_state(board, lastmove=move)
        post_comment(f"You played `{move.uci()}`.\n\n{over}\n\nComment `new game` to play again.")
        return

    engine_path = find_engine_path()
    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        result = engine.play(board, chess.engine.Limit(time=1.0))
    bot_move = result.move
    board.push(bot_move)

    over = result_message(board)
    save_state(board, lastmove=bot_move)

    msg = f"You played `{move.uci()}`. Bot replies with `{bot_move.uci()}`."
    msg += f"\n\n{over}\n\nComment `new game` to play again." if over else "\n\nYour move!"
    post_comment(msg)


if __name__ == "__main__":
    main()
