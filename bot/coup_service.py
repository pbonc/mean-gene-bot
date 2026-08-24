"""Persistent state machine for the stream's Commissioner coup contest."""

from __future__ import annotations

import json
import os
import random
import threading
from calendar import monthrange
from copy import deepcopy
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, "data", "coup_state.json")
BUILD_MILESTONES = (50, 100, 150, 175, 200)
RUNOFF_MILESTONES = (225, 250, 275, 290, 300)
VOTE_COOLDOWN_HOURS = 12


def _now():
    return datetime.now(timezone.utc)


def _iso(value=None):
    return (value or _now()).isoformat()


def _key(value):
    return str(value or "").lstrip("@").strip().casefold()


def _add_months(value, months=3):
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


class CoupService:
    def __init__(self, path=DEFAULT_PATH, clock=_now, rng=None, graft_chance=0.20, vote_cooldown_hours=VOTE_COOLDOWN_HOURS):
        self.path = path
        self.clock = clock
        self.rng = rng or random.Random()
        self.graft_chance = max(0.0, min(1.0, float(graft_chance)))
        self.vote_cooldown_hours = max(0.0, float(vote_cooldown_hours))
        self.lock = threading.RLock()
        self.state = self._load()
        self._clear_startup_rallies()

    def _clear_startup_rallies(self):
        """A bot process restart always requires candidates to rally again."""
        changed = False
        for candidate in self.state.get("candidates", {}).values():
            if candidate.get("rally_session_id") is not None or candidate.get("rally_until") is not None:
                candidate["rally_session_id"] = None
                candidate["rally_until"] = None
                changed = True
        if changed:
            self._save()

    def _fresh(self):
        return {
            "version": 1, "commissioner": {"id": None, "login": "tankahdelphia", "display": "Tankahdelphia"},
            "phase": "building", "coup_id": 1, "session_id": 0, "session_started_at": None,
            "candidates": {}, "votes": [], "lead_challenger": None, "decision": None,
            "finalists": [], "throws": [], "events": [], "history": [],
            "resolved_at": None, "term_pending_start": False, "term_start": None, "term_expires": None,
            "milestones": {},
        }

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as stream:
                return json.load(stream)
        state = self._fresh()
        self.state = state
        self._save()
        return state

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temp = self.path + ".tmp"
        with open(temp, "w", encoding="utf-8") as stream:
            json.dump(self.state, stream, indent=2, ensure_ascii=False)
        os.replace(temp, self.path)

    def _event(self, event_type, text, users=(), priority="normal"):
        event = {"id": len(self.state["events"]) + 1, "coup_id": self.state["coup_id"], "type": event_type,
                 "headline": text, "users": list(users), "timestamp": _iso(self.clock()), "priority": priority,
                 "displayed": False, "display_count": 0}
        self.state["events"].append(event)
        return event

    def _candidate(self, login):
        return self.state["candidates"].get(_key(login))

    def _active_candidates(self):
        return [c for c in self.state["candidates"].values() if c["status"] == "active"]

    def _rallied(self, candidate):
        return (
            candidate.get("rally_session_id") == self.state["session_id"]
            and bool(candidate.get("rally_until"))
            and datetime.fromisoformat(candidate["rally_until"]) > self.clock()
        )

    def enter(self, identity):
        with self.lock:
            if self.state["phase"] != "building": return False, "Candidate entry is not open right now."
            login = _key(identity["login"])
            existing = self._candidate(login)
            if existing and existing["status"] != "withdrawn": return False, f"@{identity['display']} is already entered."
            self.state["candidates"][login] = {"id": identity.get("id"), "login": login, "display": identity["display"],
                "direct_support": existing.get("direct_support", 0) if existing else 0, "endorsement_support": 0,
                "status": "active", "role": "incumbent" if login == self.state["commissioner"]["login"] else "challenger",
                "entered_at": _iso(self.clock()), "rally_until": None, "rally_session_id": None}
            self._event("candidate_entered", f"COUP WATCH: @{identity['display']} has entered the race.", [login])
            self._save(); return True, f"@{identity['display']} has entered the coup. Use `!coup rally` to receive support."

    def rally(self, login):
        with self.lock:
            if self.state["phase"] not in ("building", "runoff"): return False, "Rallies are frozen in the current coup phase."
            candidate = self._candidate(login)
            required_status = "finalist" if self.state["phase"] == "runoff" else "active"
            if not candidate or candidate["status"] != required_status: return False, "Only an eligible coup participant may rally."
            candidate["rally_until"] = _iso(self.clock() + timedelta(days=7))
            candidate["rally_session_id"] = self.state["session_id"]
            self._event("rally", f"ON THE TRAIL: @{candidate['display']} rallies supporters.", [candidate["login"]])
            self._save(); return True, f"@{candidate['display']} rallies! You can now show your support with `!coup @{candidate['display']}`."

    def support(self, voter, target_login):
        with self.lock:
            if self.state["phase"] not in ("building", "runoff"): return False, "Coup support is frozen right now."
            voter_login = _key(voter["login"]); target_login = _key(target_login)
            if voter_login == "iamdar": return False, "@iAmDar cannot cast coup support."
            voter_key = str(voter.get("id")) if voter.get("id") else voter_login
            cooldown = timedelta(hours=self.vote_cooldown_hours)
            recent_vote = next((v for v in reversed(self.state["votes"]) if v["voter_key"] == voter_key and not v.get("cooldown_waived") and self.clock() - datetime.fromisoformat(v["timestamp"]) < cooldown), None)
            if recent_vote:
                remaining = cooldown - (self.clock() - datetime.fromisoformat(recent_vote["timestamp"]))
                hours, remainder = divmod(max(0, int(remaining.total_seconds())), 3600)
                minutes = remainder // 60
                return False, f"Your coup support is on cooldown for another {hours}h {minutes}m."
            candidate = self._candidate(target_login)
            if not candidate: return False, "That user is not an eligible coup candidate."
            if self.state["phase"] == "building" and candidate["status"] != "active": return False, "That candidate cannot receive support."
            if self.state["phase"] == "runoff" and target_login not in self.state["finalists"]: return False, "Only runoff participants may receive support."
            if not self._rallied(candidate): return False, f"@{candidate['display']} needs to rally this stream before receiving support."
            commissioner_graft = (
                self.state["phase"] == "building"
                and voter_login == self.state["commissioner"]["login"]
                and self.rng.random() < self.graft_chance
            )
            points = 2 if commissioner_graft else 1
            candidate["direct_support"] += points
            self.state["votes"].append({"voter_key": voter_key,
                "voter_login": voter_login, "candidate": target_login, "points": points,
                "commissioner_graft": commissioner_graft, "session_id": self.state["session_id"], "timestamp": _iso(self.clock())})
            total = self.total(candidate); self._milestone(candidate, total)
            if self.state["phase"] == "building" and total >= 200:
                if target_login == self.state["commissioner"]["login"]:
                    self._event("incumbent_wins", f"BREAKING: Commissioner @{candidate['display']} reaches 200 and defeats the coup without a runoff!", [target_login], "breaking")
                    self._resolve(target_login)
                else:
                    self.state["lead_challenger"] = target_login
                    self._event("challenge", f"BREAKING: @{candidate['display']} has reached 200 and forced a coup runoff!", [target_login], "breaking")
                    self._establish_runoff()
            elif self.state["phase"] == "runoff" and total >= 300: self._resolve(target_login)
            if commissioner_graft:
                message = f"COMMISSIONER GRAFT! @{voter['display']}'s vote for @{candidate['display']} mysteriously counts twice. The auditors have been reassigned. {total} coup support."
            else:
                message = f"@{voter['display']} supports @{candidate['display']}! {total} coup support."
            self._save(); return True, message

    @staticmethod
    def total(candidate): return int(candidate.get("direct_support", 0)) + int(candidate.get("endorsement_support", 0))

    def _milestone(self, candidate, total):
        thresholds = RUNOFF_MILESTONES if self.state["phase"] == "runoff" else BUILD_MILESTONES
        key = candidate["login"]
        seen = self.state["milestones"].setdefault(key, [])
        for threshold in thresholds:
            if total >= threshold and threshold not in seen:
                seen.append(threshold)
                if threshold not in (200, 300): self._event("milestone", f"COUP {'ALERT' if threshold >= 250 else 'WATCH'}: @{candidate['display']} has crossed {threshold} support.", [key])

    def decide(self, commissioner_login, decision):
        with self.lock:
            return False, "Commissioner decisions are no longer used. The Commissioner must enter and race to 200."

    def _establish_runoff(self):
        active = sorted(self._active_candidates(), key=lambda c: (-self.total(c), c["entered_at"]))
        finalists = [c["login"] for c in active[:2]]
        if len(finalists) == 1:
            self.state["finalists"] = finalists
            self._resolve(finalists[0])
            return
        self.state["decision"] = "top_two"
        self.state["finalists"] = finalists
        for candidate in self.state["candidates"].values():
            candidate["status"] = "finalist" if candidate["login"] in finalists else ("eliminated" if candidate["status"] == "active" else candidate["status"])
        self.state["phase"] = "runoff"
        names = ["@" + self._candidate(k)["display"] for k in finalists]
        self._event("runoff", f"COUP RUNOFF: {' vs '.join(names)} • First to 300", finalists, "high")

    def withdraw(self, login):
        with self.lock:
            if self.state["phase"] != "building": return False, "Withdrawal is only available during coup building."
            c = self._candidate(login)
            if not c or c["status"] != "active": return False, "You are not an active challenger."
            c["status"] = "withdrawn"; self._save(); return True, f"@{c['display']} has withdrawn from the coup."

    def throw(self, login, target):
        with self.lock:
            c = self._candidate(login); target_c = self._candidate(target)
            if self.state["phase"] != "runoff": return False, "Support may only be thrown during a runoff."
            if not c or c["status"] != "eliminated": return False, "Only an eliminated candidate may throw support."
            if any(t["from"] == c["login"] for t in self.state["throws"]): return False, "You have already thrown support in this coup."
            if not target_c or target_c["login"] not in self.state["finalists"]: return False, "Support must be thrown to a runoff participant."
            amount = self.total(c) // 10; target_c["endorsement_support"] += amount
            self.state["throws"].append({"from": c["login"], "to": target_c["login"], "amount": amount, "timestamp": _iso(self.clock())})
            self._event("endorsement", f"ENDORSEMENT: @{c['display']} throws support behind @{target_c['display']} • +{amount}", [c["login"], target_c["login"]], "high")
            if self.total(target_c) >= 300: self._resolve(target_c["login"])
            self._save(); return True, f"@{c['display']} throws support behind @{target_c['display']}! +{amount} coup support."

    def _resolve(self, winner_login):
        old = deepcopy(self.state["commissioner"]); winner = deepcopy(self._candidate(winner_login))
        retained = winner_login == old["login"]
        self.state["commissioner"] = {k: winner.get(k) for k in ("id", "login", "display")}
        record = {"coup_id": self.state["coup_id"], "starting_commissioner": old, "decision": self.state["decision"],
            "lead_challenger": self.state["lead_challenger"], "finalists": self.state["finalists"], "candidates": deepcopy(self.state["candidates"]),
            "throws": deepcopy(self.state["throws"]), "winner": winner_login, "result": "failed" if retained else "succeeded", "resolved_at": _iso(self.clock())}
        self.state["history"].append(record); self.state["phase"] = "protected"; self.state["resolved_at"] = record["resolved_at"]
        self.state["term_pending_start"] = True; self.state["term_start"] = None; self.state["term_expires"] = None
        self._event("resolved", f"BREAKING: THE COUP {'FAILS' if retained else 'SUCCEEDS'} • @{winner['display']} {'retains office' if retained else 'is the new Commissioner'}!", [winner_login], "breaking")

    def begin_stream(self):
        with self.lock:
            self.state["session_id"] += 1; self.state["session_started_at"] = _iso(self.clock())
            if self.state["term_pending_start"]:
                start = self.clock(); self.state["term_pending_start"] = False; self.state["term_start"] = _iso(start); self.state["term_expires"] = _iso(_add_months(start))
                self._event("term_started", f"OFFICIAL: Commissioner @{self.state['commissioner']['display']}'s three-month protected term has begun.", [self.state["commissioner"]["login"]], "high")
                if self.state["history"]: self.state["history"][-1].update(term_start=self.state["term_start"], term_expires=self.state["term_expires"])
            self._refresh_term(); self._save(); return self.state["session_id"]

    def _refresh_term(self):
        if self.state["phase"] == "protected" and self.state.get("term_expires") and self.clock() >= datetime.fromisoformat(self.state["term_expires"]):
            self.state["phase"] = "eligible"
            self._event("term_expired", f"COUP WATCH: Commissioner @{self.state['commissioner']['display']}'s protected term has ended. A new coup may now be established.", priority="high")

    def open_next(self):
        with self.lock:
            self._refresh_term()
            if self.state["phase"] not in ("eligible", "closed"): return False, "A new coup is not eligible to open."
            self.state.update(phase="building", coup_id=self.state["coup_id"] + 1, candidates={}, votes=[], lead_challenger=None, decision=None, finalists=[], throws=[], milestones={})
            self._save(); return True, "A new coup is now open for challengers."

    def adjust(self, login, amount):
        with self.lock:
            c = self._candidate(login)
            if not c: return False, "Candidate not found."
            c["direct_support"] = max(0, c["direct_support"] + int(amount)); self._save(); return True, f"@{c['display']} now has {self.total(c)} support."

    def snapshot(self):
        with self.lock:
            self._refresh_term(); self._save()
            candidates = sorted((dict(c, support=self.total(c), rally_active=self._rallied(c)) for c in self.state["candidates"].values()), key=lambda c: -c["support"])
            phase = self.state["phase"]; commissioner = self.state["commissioner"]
            if phase == "building": ticker = "COUP WATCH: " + " • ".join(f"@{c['display']} {c['support']}" for c in candidates[:3]) + " • First to 200"
            elif phase == "decision": ticker = f"COUP CRISIS: @{self._candidate(self.state['lead_challenger'])['display']} has challenged Commissioner @{commissioner['display']}"
            elif phase == "runoff": ticker = "COUP: " + " vs ".join(f"@{self._candidate(k)['display']} {self.total(self._candidate(k))}" for k in self.state["finalists"]) + " • First to 300"
            elif phase == "protected":
                expiry = datetime.fromisoformat(self.state["term_expires"]) if self.state.get("term_expires") else None
                ticker = f"COMMISSIONER: @{commissioner['display']} • Protected" + (f" through {expiry.strftime('%B')} {expiry.day}" if expiry else "; term begins next stream")
            else: ticker = f"COMMISSIONER: @{commissioner['display']} • A new coup may now be established"
            return {"type": "coup_state", "currentCommissioner": commissioner, "phase": phase, "coupActive": phase in ("building", "decision", "runoff"), "coupEligible": phase == "eligible",
                "candidates": candidates, "leader": candidates[0] if candidates else None, "challenger": self.state["lead_challenger"], "commissionerDecision": self.state["decision"],
                "runoffParticipants": self.state["finalists"], "throws": deepcopy(self.state["throws"]), "initialTarget": 200, "runoffTarget": 300,
                "currentTarget": 300 if phase == "runoff" else 200, "termPendingStart": self.state["term_pending_start"], "termStart": self.state["term_start"],
                "termExpires": self.state["term_expires"], "tickerText": ticker, "latestHeadline": self.state["events"][-1] if self.state["events"] else None,
                "headlineQueue": [e for e in self.state["events"] if not e["displayed"]][-10:], "recentEvents": self.state["events"][-20:], "history": self.state["history"][-10:]}

    def status_text(self):
        s = self.snapshot(); commissioner = s["currentCommissioner"]["display"]
        if s["phase"] == "decision": return f"THE COMMISSIONER HAS BEEN CHALLENGED: @{self._candidate(s['challenger'])['display']} reached 200. Awaiting Commissioner @{commissioner}: `!coup resist` or `!coup abdicate`."
        return s["tickerText"]


_service = None
def get_coup_service():
    global _service
    if _service is None: _service = CoupService()
    return _service
