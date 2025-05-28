import json

with open("raffle_state.json", "r", encoding="utf-8") as f:
    state = json.load(f)

if isinstance(state["picks"], dict):
    # Convert from {"pick": "user", ...} to {"user": [pick, ...]}
    user_picks = {}
    for pick, user in state["picks"].items():
        user_picks.setdefault(user, []).append(pick)
    state["picks"] = user_picks

# Clean up nuclear
if "nuclear_key" in state:
    del state["nuclear_key"]
if "nuclear" not in state or not isinstance(state["nuclear"], dict):
    state["nuclear"] = {}

# Clean up chat_awarded (should be a list)
if "chat_awarded" in state and not isinstance(state["chat_awarded"], list):
    state["chat_awarded"] = list(state["chat_awarded"])

with open("raffle_state.json", "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("Conversion complete. New format:")
print(json.dumps(state, indent=2))