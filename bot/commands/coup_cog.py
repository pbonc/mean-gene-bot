"""Viewer-facing Coup / Commissioner commands."""

import json
from datetime import datetime

from twitchio.ext import commands

from bot.coup_service import get_coup_service, _iso, _key
from bot.overlay_server import broadcast_overlay_message


def identity(author):
    login = str(getattr(author, "name", ""))
    return {"id": str(getattr(author, "id", "") or "") or None, "login": login, "display": str(getattr(author, "display_name", login) or login)}


def is_admin(author):
    return bool(getattr(author, "is_mod", False)) or _key(getattr(author, "name", "")) == "iamdar"


class CoupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = get_coup_service()

    async def publish(self):
        await broadcast_overlay_message(self.service.snapshot())

    @commands.command(name="coup")
    async def coup(self, ctx, *args):
        actor = identity(ctx.author)
        if not args or args[0].casefold() == "status":
            await ctx.send(self.service.status_text()); return
        action = args[0].casefold()
        if action == "enter": ok, message = self.service.enter(actor)
        elif action == "rally": ok, message = self.service.rally(actor["login"])
        elif action == "withdraw": ok, message = self.service.withdraw(actor["login"])
        elif action in ("resist", "abdicate"): ok, message = self.service.decide(actor["login"], action)
        elif action == "throw":
            if len(args) != 2 or not args[1].startswith("@"): ok, message = False, "Use `!coup throw @username`. The @ is required."
            else: ok, message = self.service.throw(actor["login"], args[1])
        elif action.startswith("@"):
            ok, message = self.service.support(actor, action)
        else:
            ok, message = False, "Use `!coup @username` to support a candidate. The @ is required."
        await ctx.send(message)
        if ok: await self.publish()

    @commands.command(name="coupadmin")
    async def coupadmin(self, ctx, *raw_args):
        if not is_admin(ctx.author):
            await ctx.send("Only moderators or iAmDar may administer Coup."); return
        args = list(raw_args)
        if not args:
            await ctx.send("Coup admin: open/close | beginstream | state | adjust @user +/-N | remove/restore/rally/force200 @user | runoff @a @b | throw @from @to | undothrow @from | resolve @winner | setcommissioner @user | term status/pending/start/expire [ISO] | forceeligible | resetvote @user | headline text | clearheadlines | reset")
            return
        action = args.pop(0).casefold(); service = self.service
        try:
            if action == "open": ok, message = service.open_next()
            elif action == "beginstream": message = f"Coup stream session {service.begin_stream()} started."; ok = True
            elif action == "state": await ctx.send(json.dumps(service.snapshot(), ensure_ascii=False)[:480]); return
            else:
                with service.lock:
                    ok = True
                    if action == "close": service.state["phase"] = "closed"; message = "Coup entry and voting closed."
                    elif action in ("adjust", "force200"):
                        target = args[0]; candidate = service._candidate(target)
                        if not candidate: ok, message = False, "Candidate not found."
                        else:
                            candidate["direct_support"] = 200 if action == "force200" else max(0, candidate["direct_support"] + int(args[1]))
                            message = f"@{candidate['display']} now has {service.total(candidate)} support."
                            if action == "force200": service.state["phase"] = "decision"; service.state["lead_challenger"] = candidate["login"]
                    elif action in ("remove", "restore"):
                        candidate = service._candidate(args[0])
                        if not candidate: ok, message = False, "Candidate not found."
                        else: candidate["status"] = "disqualified" if action == "remove" else "active"; message = f"@{candidate['display']} is now {candidate['status']}."
                    elif action == "rally": ok, message = service.rally(args[0])
                    elif action in ("resist", "abdicate"): ok, message = service.decide(service.state["commissioner"]["login"], action)
                    elif action == "runoff":
                        finalists = [_key(args[0]), _key(args[1])]
                        if len(set(finalists)) != 2 or any(not service._candidate(user) for user in finalists): ok, message = False, "Two distinct existing candidates are required."
                        else:
                            service.state["finalists"] = finalists; service.state["phase"] = "runoff"
                            for candidate in service.state["candidates"].values(): candidate["status"] = "finalist" if candidate["login"] in finalists else ("eliminated" if candidate["status"] == "active" else candidate["status"])
                            message = "Runoff established: " + " vs. ".join("@" + service._candidate(user)["display"] for user in finalists)
                    elif action == "throw": ok, message = service.throw(args[0], args[1])
                    elif action in ("undothrow", "resetthrow"):
                        source = _key(args[0]); throw = next((item for item in service.state["throws"] if item["from"] == source), None)
                        if not throw: ok, message = False, "No throw found for that candidate."
                        else:
                            recipient = service._candidate(throw["to"])
                            if recipient: recipient["endorsement_support"] = max(0, recipient["endorsement_support"] - throw["amount"])
                            service.state["throws"].remove(throw); message = f"Throw from @{source} was removed."
                    elif action == "inspectthrows": await ctx.send(json.dumps(service.state["throws"], ensure_ascii=False)[:480]); return
                    elif action == "resolve":
                        winner = _key(args[0])
                        if not service._candidate(winner): ok, message = False, "Winner is not a candidate."
                        else: service._resolve(winner); message = f"Coup forcibly resolved for @{service._candidate(winner)['display']}."
                    elif action == "setcommissioner":
                        login = _key(args[0]); candidate = service._candidate(login)
                        service.state["commissioner"] = {"id": candidate.get("id") if candidate else None, "login": login, "display": (candidate or {}).get("display", args[0].lstrip("@"))}; message = f"Commissioner set to @{service.state['commissioner']['display']}."
                    elif action == "forceeligible": service.state["phase"] = "eligible"; service.state["term_pending_start"] = False; service.state["term_expires"] = _iso(service.clock()); message = "Coup eligibility forced."
                    elif action == "term":
                        mode = args[0].casefold()
                        if mode == "status": await ctx.send(f"Pending: {service.state['term_pending_start']} | Start: {service.state['term_start']} | Expires: {service.state['term_expires']}"); return
                        if mode == "pending": service.state["term_pending_start"] = True; service.state["term_start"] = None; service.state["term_expires"] = None; service.state["phase"] = "protected"; message = "Term will begin with the next stream."
                        elif mode in ("start", "expire"):
                            value = args[1]; datetime.fromisoformat(value.replace("Z", "+00:00"))
                            service.state["term_start" if mode == "start" else "term_expires"] = value; service.state["phase"] = "protected"; message = f"Term {mode} overridden to {value}."
                        else: ok, message = False, "Use term status, pending, start <ISO>, or expire <ISO>."
                    elif action == "resetvote":
                        login = _key(args[0]); vote = next((v for v in reversed(service.state["votes"]) if v["voter_login"] == login and not v.get("cooldown_waived")), None)
                        if vote: vote["cooldown_waived"] = True
                        message = "Vote cooldown reset." if vote else "No active vote cooldown found."
                    elif action == "headline": message = " ".join(args); service._event("admin", message, priority="high")
                    elif action == "clearheadlines":
                        for event in service.state["events"]: event["displayed"] = True
                        message = "Headline queue cleared."
                    elif action == "reset":
                        commissioner = service.state["commissioner"]; history = service.state["history"]; events = service.state["events"]
                        service.state = service._fresh(); service.state.update(commissioner=commissioner, history=history, events=events, phase="eligible"); message = "Current coup reset; Commissioner and history preserved."
                    else: ok, message = False, "Unknown coup admin action."
                    service._save()
        except (IndexError, ValueError): ok, message = False, "Invalid or incomplete coup admin arguments."
        await ctx.send(message)
        if ok: await self.publish()


def prepare(bot):
    if not bot.get_cog("CoupCog"):
        bot.add_cog(CoupCog(bot))
