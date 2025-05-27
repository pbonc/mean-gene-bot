from flask import Blueprint, jsonify, current_app

battleship_api = Blueprint('battleship_api', __name__)

def get_battleship_game():
    # Import global bot instance (set this up in your main.py)
    bot = getattr(current_app, "bot_instance", None)
    if bot and hasattr(bot, "battleship_game") and bot.battleship_game:
        return bot.battleship_game
    return None

@battleship_api.route('/battleship/state')
def battleship_state():
    game = get_battleship_game()
    if not game:
        return jsonify({"error": "No game running"})
    return jsonify(game.get_state())