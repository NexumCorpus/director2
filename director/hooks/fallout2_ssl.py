"""Fallout 2 SSL compiler — dialogue/quest JSON -> sfall-ready sources.

Closes the loop the fallout2 hook left open ("compile it to your mod format
in a later task"): trusted, deterministic translation of VALIDATED dialogue
JSON into

* a ``.ssl`` script (classic Fallout 2 scripting language, sfall-extended)
  using ``gsay_*`` / ``giq_option`` dialog calls, and
* the matching ``.msg`` file holding every line of text.

State model: every declared variable compiles to an sfall global
(``get_sfall_global_int`` / ``set_sfall_global``), so no vault13.gam edits or
GVAR registration are needed. Remap specific variables to engine stats by
hand if desired (e.g. player_karma -> get_critter_stat).

What is exact: the .msg format, message-id wiring, node/option topology,
condition/effect translation. What is project-specific and marked TODO in
the output: header include paths and script registration (scripts.lst /
scripts.h), which depend on the mod's build tree.

Compilation refuses invalid trees (:class:`CompileError`), so the graph
invariants the validators enforce are preconditions here — generated scripts
cannot contain dangling jumps or undeclared state.
"""

from __future__ import annotations

import re
from pathlib import Path

from .fallout2 import (_COND_RE, _EFFECT_RE, validate_dialogue,
                       validate_quest)


class CompileError(ValueError):
    """Input JSON failed validation or cannot be carried to SSL."""


# `Node_<id>` is reserved for JSON nodes; terminals use `Term_` so a node
# literally named "end"/"combat" can never collide with them.
_TERMINAL_PROC = {"end": "Term_End", "exit": "Term_End",
                  "combat": "Term_Combat", "barter": "Term_Barter"}
_TERMINAL_BODY = {
    "Term_End": ("procedure Term_End begin\n"
                 "   /* no reply issued -> conversation ends */\n"
                 "end"),
    "Term_Combat": ("procedure Term_Combat begin\n"
                    "   attack(dude_obj);\n"
                    "end"),
    "Term_Barter": ("procedure Term_Barter begin\n"
                    "   gdialog_mod_barter(0);\n"
                    "end"),
}


def _ident(s: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_]", "_", str(s))
    if not out or out[0].isdigit():
        out = "n_" + out
    return out


def _script_name(tree: dict, explicit: str | None) -> str:
    """<=8 lowercase chars (classic script-name budget). Default: 'wr' +
    first word of the NPC name."""
    if explicit:
        name = re.sub(r"[^a-z0-9]", "", str(explicit).lower())[:8]
    else:
        npc = str(tree.get("npc", "")).strip()
        first = npc.split()[0] if npc else "npc"
        name = ("wr" + re.sub(r"[^a-z0-9]", "", first.lower()))[:8]
    if not name or name[0].isdigit():
        name = ("s" + name)[:8]
    return name or "wrnpc"


def _msg_escape(text: str) -> str:
    # braces are structural in .msg files; newlines break the line format
    return (str(text).replace("{", "(").replace("}", ")")
            .replace("\r", " ").replace("\n", " ").strip())


def _operand(tok: str) -> str:
    if re.fullmatch(r"-?\d+", tok):
        return tok
    return f'get_sfall_global_int("{tok}")'


def _compile_cond(cond: str) -> str:
    m = _COND_RE.match(str(cond))
    if not m:                                   # validation should prevent this
        raise CompileError(f"unparseable condition '{cond}'")
    var, op, val = m.group(1), m.group(2), m.group(3)
    return f'(get_sfall_global_int("{var}") {op} {_operand(val)})'


def _compile_effect(eff: str) -> str:
    m = _EFFECT_RE.match(str(eff))
    if not m:
        raise CompileError(f"unparseable effect '{eff}'")
    var, op, val = m.group(1), m.group(2), m.group(3)
    if op == "=":
        return f'set_sfall_global("{var}", {_operand(val)});'
    sign = "+" if op == "+=" else "-"
    return (f'set_sfall_global("{var}", get_sfall_global_int("{var}") '
            f'{sign} {_operand(val)});')


def compile_dialogue(tree: dict, script_name: str | None = None,
                     base_msg_id: int = 100) -> dict:
    """Compile validated dialogue JSON to ``{"script_name", "ssl", "msg",
    "globals", "stats"}``. Raises :class:`CompileError` on invalid input."""
    problems = validate_dialogue(tree)
    if problems:
        extra = f" (+{len(problems) - 5} more)" if len(problems) > 5 else ""
        raise CompileError("dialogue JSON failed validation: "
                           + "; ".join(problems[:5]) + extra)

    name = _script_name(tree, script_name)
    nodes: dict = tree["nodes"]
    entry = tree.get("entry", "start")
    variables = tree.get("variables") or {}

    # ---- message table: deterministic ids in JSON order ----------------- #
    msg: list[tuple[int, str]] = []
    node_msg: dict[str, int] = {}
    resp_msg: dict[tuple[str, int], int] = {}
    next_id = int(base_msg_id)
    for nid, node in nodes.items():
        node_msg[nid] = next_id
        msg.append((next_id, _msg_escape(node["text"])))
        next_id += 1
        for i, r in enumerate(node.get("responses") or []):
            resp_msg[(nid, i)] = next_id
            msg.append((next_id, _msg_escape(r.get("text", ""))))
            next_id += 1

    # ---- response targets: direct jump, or effect-dispatch proc --------- #
    used_terminals: set[str] = set()
    resp_target: dict[tuple[str, int], str] = {}
    dispatch_procs: list[str] = []
    n_dispatch = 0
    for nid, node in nodes.items():
        for i, r in enumerate(node.get("responses") or []):
            goto = str(r.get("goto", ""))
            if goto in nodes:
                target = f"Node_{_ident(goto)}"
            else:
                target = _TERMINAL_PROC[goto]
                used_terminals.add(goto)
            effects = [str(e) for e in (r.get("effects") or [])]
            if effects:
                n_dispatch += 1
                pname = f"Resp_{n_dispatch:03d}"
                body = "\n".join("   " + _compile_effect(e) for e in effects)
                dispatch_procs.append(f"procedure {pname} begin\n{body}\n"
                                      f"   call {target};\nend")
                resp_target[(nid, i)] = pname
            else:
                resp_target[(nid, i)] = target

    # ---- node procedures ------------------------------------------------ #
    def node_proc(nid: str, node: dict) -> str:
        inner = [f"   gsay_reply(NAME, {node_msg[nid]});"]
        for i, r in enumerate(node.get("responses") or []):
            opt = (f"giq_option(4, NAME, {resp_msg[(nid, i)]}, "
                   f"{resp_target[(nid, i)]}, 50);")
            rconds = [str(c) for c in (r.get("conditions") or [])]
            if rconds:
                joined = " and ".join(_compile_cond(c) for c in rconds)
                inner.append(f"   if ({joined}) then")
                inner.append(f"      {opt}")
            else:
                inner.append(f"   {opt}")
        pname = f"Node_{_ident(nid)}"
        conds = [str(c) for c in (node.get("conditions") or [])]
        if conds:
            used_terminals.add("end")
            joined = " and ".join(_compile_cond(c) for c in conds)
            gated = "\n".join("   " + line for line in inner)
            return (f"procedure {pname} begin\n"
                    f"   /* entry gate from node 'conditions' */\n"
                    f"   if ({joined}) then begin\n"
                    f"{gated}\n"
                    f"   end\n"
                    f"   else begin\n"
                    f"      call Term_End;\n"
                    f"   end\n"
                    f"end")
        return f"procedure {pname} begin\n" + "\n".join(inner) + "\nend"

    node_procs = [node_proc(nid, node) for nid, node in nodes.items()]
    terminal_procs = [_TERMINAL_BODY[p] for p in
                      sorted({_TERMINAL_PROC[t] for t in used_terminals})]

    # ---- assembly -------------------------------------------------------- #
    decl_names = (["start", "talk_p_proc"]
                  + [f"Node_{_ident(nid)}" for nid in nodes]
                  + [f"Resp_{i + 1:03d}" for i in range(n_dispatch)]
                  + sorted({_TERMINAL_PROC[t] for t in used_terminals}))
    header = (
        f"/* {name}.ssl — generated by Director 2.0 fallout2_wr hook.\n"
        f"   NPC: {tree.get('npc', '?')}\n"
        f"   Source: validated dialogue JSON (reachability, gotos and\n"
        f"   variables all checked before compilation). Regenerate rather\n"
        f"   than hand-editing topology; text lives in {name}.msg.\n"
        f"   State -> sfall globals: "
        f"{', '.join(sorted(variables)) or '(none)'}\n"
        f"*/\n\n"
        f"/* TODO(project): point these at your mod's header tree and\n"
        f"   register {name} in scripts.lst / scripts.h. */\n"
        f"#include \"..\\headers\\define.h\"\n"
        f"#define NAME SCRIPT_{name.upper()}\n"
        f"#include \"..\\headers\\command.h\"\n")
    decls = "\n".join(f"procedure {d};" for d in decl_names)
    start_proc = "procedure start begin\nend"
    talk = (f"procedure talk_p_proc begin\n"
            f"   start_gdialog(NAME, self_obj, 4, -1, -1);\n"
            f"   gsay_start;\n"
            f"   call Node_{_ident(entry)};\n"
            f"   gsay_end;\n"
            f"   end_dialogue;\n"
            f"end")
    ssl = "\n\n".join([header, decls, start_proc, talk]
                      + node_procs + dispatch_procs + terminal_procs) + "\n"
    msg_text = (f"# {name}.msg — generated; ids referenced by {name}.ssl\n"
                + "\n".join(f"{{{mid}}}{{}}{{{text}}}" for mid, text in msg)
                + "\n")
    total_responses = sum(len(n.get("responses") or [])
                          for n in nodes.values())
    return {"script_name": name, "ssl": ssl, "msg": msg_text,
            "globals": sorted(variables),
            "stats": {"nodes": len(nodes), "responses": total_responses,
                      "dispatch_procs": n_dispatch,
                      "messages": len(msg)}}


def compile_quest_header(quest: dict) -> str:
    """Validated quest JSON -> a documentation header (.h): sfall global key
    defines plus the stage graph as a comment block."""
    problems = validate_quest(quest)
    if problems:
        raise CompileError("quest JSON failed validation: "
                           + "; ".join(problems[:5]))
    qid = _ident(quest.get("id", "quest"))
    lines = [f"/* {qid} — quest scaffold header "
             f"(generated by Director 2.0 fallout2_wr hook).",
             f"   Name: {quest.get('name', '?')}",
             "   sfall global keys used by the quest state machine: */"]
    for v in sorted(quest.get("variables") or {}):
        lines.append(f'#define GLOB_{_ident(v).upper()}   "{v}"')
    lines.append("")
    lines.append("/* stage graph (topology enforced by trusted validators):")
    for sid, stage in (quest.get("stages") or {}).items():
        lines.append(f"   {sid}: "
                     f"{str(stage.get('description', '')).strip()}")
        for t in stage.get("transitions") or []:
            when = " and ".join(str(c) for c in (t.get("when") or []))
            lines.append(f"     -> {t.get('to')} when {when or 'always'}")
    lines.append("*/")
    return "\n".join(lines) + "\n"


def compile_to_files(tree: dict, out_dir, script_name: str | None = None
                     ) -> list[Path]:
    """Compile a dialogue tree and write ``<name>.ssl`` + ``<name>.msg``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    res = compile_dialogue(tree, script_name=script_name)
    ssl_p = out / f"{res['script_name']}.ssl"
    msg_p = out / f"{res['script_name']}.msg"
    ssl_p.write_text(res["ssl"], encoding="utf-8")
    msg_p.write_text(res["msg"], encoding="utf-8")
    return [ssl_p, msg_p]
