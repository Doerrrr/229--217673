#!/usr/bin/env python3
"""Behavioral, weighted verifier for the leakage-safe DDI release."""
import argparse
import csv
import itertools
import json
import random
import subprocess
import tempfile
import time
from pathlib import Path

from release_model import HEADERS, FOLDS, csv_bytes, digest, expected, assignment, curate, clusters
from screen_model import policy_input, resource_report, exhaustive_batch, optimize_batch

COMMAND = ["/usr/local/bin/ddi-release"]
DATA = Path("/data")
NAMES = tuple(HEADERS) + ("report.json",)
CACHE = {}
TEMPS = []
BASE_DRUGS = """ B ,OCC
A,CCO
X,CC
X,CN
I,not-a-smiles
A,not-a-smiles
L,
Z,CCN
Q,CCC
W,CO
"""
BASE_EVENTS = '00,first\n1,second\n01,other\n2,\nX,bad\n"03","multi\nline"\n\n'
BASE_INTERACTIONS = """d1,type,d2
A,0,Z
B,00,Z
Z,0,A
Z,0,Q
A,0,A
A,0,B
X,1,I
I,0,A
MISSING,1,X
A,99,Z
A,1,Z
A,X,Z
A,0
A,0,Q
W,03,Q
"""
FIXTURES = {
    "cardinality": (
        ["CCCCCO","CCCC(=O)O","CCCCCCC(=O)O","CCCCCCCOC","CCC","CCO","CCCCCOC","CCCCCCO","CCCCCCOC","CCCCCCCCCl"],
        [("D",0,"E"),("F",1,"I"),("G",1,"D"),("G",1,"I")],
        [("I",1875),("E",1875),("F",1667),None]),
    "score": (
        ["CC(C)N","CCCCCC(=O)O","CCCBr","CCCCCCCl","CCCO","C1CCCC1","CCCCCCCC","CCCCF","CCCCCCBr","CCCCCO"],
        [("A",0,"E"),("D",1,"J"),("E",1,"A"),("G",0,"J")],
        [("J",5385),("G",5385),None,("E",5385)]),
    "lex": (
        ["CCCCCCCC","CCCCCBr","CCCCCCCl","CCCCCCF","C","CCCCCCN","CCCCCCCF","CCC(=O)O","CCCCCC(=O)O","CCCC(=O)O"],
        [("A",0,"F"),("A",1,"F"),("C",0,"G"),("G",1,"A")],
        [("C",4444),("A",6154),("F",6154),("D",5294)]),
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def temp():
    item = tempfile.TemporaryDirectory(prefix="ddi-release-test-")
    TEMPS.append(item)
    return Path(item.name)


def inputs(root, drugs, events="0,zero\n1,one\n2,two\n", interactions="d1,type,d2\n"):
    for name, text in zip(("drug_list.csv","DDI_event.csv","newddi.csv"), (drugs,events,interactions)):
        (root/name).write_text(text, encoding="utf-8", newline="\n")
    write_policy(root)


def write_policy(root, stock=96, setup=0, overrides=(), **settings):
    config=dict(budget=1000000, assay_cost=0, max_pairs=48, cluster_cap=48, event_quotas=[])
    config.update(settings)
    policy=dict(version=1, defaults=dict(stock=stock,setup_cost=setup),
                drug_overrides=list(overrides), folds={fold:dict(config) for fold in FOLDS[1:]})
    (root/'screen_plan.json').write_text(json.dumps(policy),encoding='utf-8')
    return policy


def invoke(root, out, extra=(), timeout=180, omit=()):
    arguments = []
    for flag, path in (("--drugs", root/"drug_list.csv"), ("--events", root/"DDI_event.csv"),
                       ("--interactions", root/"newddi.csv"), ("--screen-plan", root/'screen_plan.json'), ("--out-dir", out)):
        if flag not in omit:
            arguments.extend((flag, str(path)))
    return subprocess.run(
        COMMAND + arguments + list(extra),
        capture_output=True, text=True, timeout=timeout, check=False)


def obtain(name):
    if name in CACHE:
        return CACHE[name]
    root = temp()
    if name == "full":
        root = DATA
    elif name == "base":
        inputs(root, BASE_DRUGS, BASE_EVENTS, BASE_INTERACTIONS)
    elif name in FIXTURES:
        smiles, triples, _ = FIXTURES[name]
        inputs(root, "".join(f"{chr(65+i)},{s}\n" for i,s in enumerate(smiles)),
               interactions=csv_bytes(["d1","type","d2"], triples).decode())
    elif name == "reverse":
        smiles, triples, _ = FIXTURES["cardinality"]
        triples = triples + [("F",2,"D"),("I",2,"D")]
        inputs(root, "".join(f"{chr(65+i)},{s}\n" for i,s in enumerate(smiles)),
               interactions=csv_bytes(["d1","type","d2"], triples).decode())
    elif name == "chemistry":
        inputs(root, "A,c1ccccc1\nB,Oc1ccccc1\nC,CC\nD,CCC\nE,N[C@@H](C)C(=O)O\nF,N[C@H](C)C(=O)O\nG,[Na+].CC(=O)[O-]\n")
    elif name == "chain":
        rows = dict()
        with (DATA/"drug_list.csv").open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.reader(handle):
                if row and row[0] in ("DB00666","DB06825","DB06788"):
                    rows[row[0]] = row[1]
        require(len(rows) == 3, "immutable chain fixture records unavailable")
        inputs(root, "".join(f"{key},{rows[key]}\n" for key in sorted(rows)))
    elif name == "empty":
        inputs(root, "", "", "d1,type,d2\n")
    else:
        raise AssertionError(name)
    out = temp()
    tables, report, targets, edges = expected(root)
    if name == "full":
        snapshot=json.loads(Path(__file__).with_name("full_snapshot.json").read_text(encoding="utf-8"))
        for key,value in snapshot.items():
            computed={k:v for k,v in report[key].items() if k != 'plan'} if key == 'release' else report[key]
            require(computed == value, f"independently computed full snapshot drift: {key}")
        require([(report['release']['plan'][f]['total_score'], report['release']['plan'][f]['total_cost'])
                 for f in FOLDS[1:]] == [(48920,94),(45297,95)], 'fixed resource optimum drift')
        require(report["input"]["interaction_rows"] == report["interactions"]["kept"]+sum(report["interactions"]["dropped"].values()), "raw count conservation")
        require(report["interactions"]["kept"] == sum(v["positives"] for v in report["release"]["folds"].values())+report["release"]["cross_fold_withheld"], "partition conservation")
    result = invoke(root, out)
    CACHE[name] = (root, out, tables, report, targets, edges, result)
    return CACHE[name]


def successful(case):
    require(case[-1].returncode == 0, f"command failed: {case[-1].stderr[:400]}")
    return case


def actual_table(case, name):
    successful(case)
    path = case[1]/name
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    require(rows and rows[0] == HEADERS[name], f"{name} header")
    require(all(len(row) == len(HEADERS[name]) for row in rows[1:]), f"{name} field count")
    return rows[1:]


def exact_table(case, name):
    actual = actual_table(case, name)
    want = [[str(value) for value in row] for row in case[2][name]]
    require(actual == want, f"{name} rows/order differ")
    require((case[1]/name).read_bytes() == csv_bytes(HEADERS[name], case[2][name]), f"{name} CSV serialization")


def section(case, key):
    successful(case)
    actual = json.loads((case[1]/"report.json").read_text(encoding="utf-8"))
    require(actual.get(key) == case[3][key], f"report.{key} differs")
    return actual


def check_assignment(name):
    case = obtain(name)
    pair_rows = case[2]["unobserved_pairs.csv"]
    # These small assignments were hand-enumerated, not copied from the Oracle.
    wanted = FIXTURES[name][2]
    selected = [(row[5], row[6]) if row[7] == "MATCHED" else None for row in pair_rows]
    require(selected == wanted, f"independent fixture {name} drift")
    exact_table(case, "unobserved_pairs.csv")
    check_resource_cases(name)


RESOURCE_CASES = {
    'shared': ('lex', dict(stock=1)),
    'quota_cluster': ('cardinality', dict(stock=2, cluster_cap=1,
        event_quotas=[dict(type=1,min=2,max=2)], max_pairs=3)),
    'budget': ('score', dict(stock=2,setup=3,budget=15,assay_cost=1)),
    'cost': ('score', dict(setup=0,max_pairs=2,budget=100, overrides=[
        dict(drug_id='E',stock=96,setup_cost=9)])),
    'alias': ('lex', dict(stock=96, overrides=[
        dict(drug_id='A',stock=1,setup_cost=3),dict(drug_id='ZZ',stock=1,setup_cost=3)])),
    'infeasible': ('lex', dict(stock=0,event_quotas=[dict(type=0,min=1,max=3)])),
    'zero_budget': ('lex', dict(setup=1,budget=0)),
    'zero_cost': ('lex', dict(stock=2,setup=0,budget=0)),
}


def resource_case(name):
    cache_key='resource_'+name
    if cache_key in CACHE:
        return CACHE[cache_key]
    fixture,settings=RESOURCE_CASES[name]
    smiles,triples,_=FIXTURES[fixture]
    text=''.join(f'{chr(65+i)},{s}\n' for i,s in enumerate(smiles))
    if name == 'alias':
        text += f'ZZ,{smiles[0]}\n'
    root,out=temp(),temp()
    inputs(root,text,interactions=csv_bytes(['d1','type','d2'],triples).decode())
    write_policy(root,**settings)
    tables,report,targets,options=expected(root)
    molecules,_,_,valid=curate(root,with_policy_ids=True)
    meta=clusters(molecules)
    resources,policies=policy_input(root/'screen_plan.json',molecules,valid)
    for fold in FOLDS[1:]:
        matches,status=exhaustive_batch(targets[fold],options[fold],meta,resources,policies[fold])
        rows=[r for r in tables['unobserved_pairs.csv'] if r[0] == fold]
        require([(r[5],r[6]) if r[7] == 'MATCHED' else None for r in rows] == matches,
                'small-instance MILP disagrees with exhaustive enumeration')
        require(report['release']['plan'][fold] == resource_report(targets[fold],matches,meta,resources,policies[fold],status),
                'small-instance resource ledger disagrees')
    # Explicit hand-calculated witnesses, independent of both solver outputs.
    witnesses={
        'shared': ('validation', [None,('A',6154),('D',6154),None], 12308, 0),
        'quota_cluster': ('test', [('I',1875),('E',1875),('F',1667),None],5417,0),
        'budget': ('validation', [('J',5385),('G',5385),None,('D',3889)],14659,15),
        'cost': ('validation', [('J',5385),('G',5385),None,None],10770,0),
        'alias': ('validation', [('C',4444),('F',5294),('D',6154),None],15892,3),
        'zero_cost': ('validation', [('D',5294),('A',6154),('F',6154),None],17602,0),
    }
    if name in witnesses:
        fold,wanted,score,cost=witnesses[name]
        rows=[r for r in tables['unobserved_pairs.csv'] if r[0]==fold]
        require([(r[5],r[6]) if r[7]=='MATCHED' else None for r in rows]==wanted, 'manual resource witness drift')
        require((report['release']['plan'][fold]['total_score'],report['release']['plan'][fold]['total_cost'])==(score,cost), 'manual resource totals drift')
    case=(root,out,tables,report,targets,options,invoke(root,out))
    CACHE[cache_key]=case
    return case


def check_resource_cases(group):
    names={'cardinality':('shared','quota_cluster','alias','infeasible'),
           'score':('budget','zero_budget','zero_cost'), 'lex':('cost',)}[group]
    for name in names:
        case=resource_case(name)
        exact_table(case,'unobserved_pairs.csv')
        section(case,'release')


def check_matching_full():
    case = obtain("full")
    exact_table(case, "unobserved_pairs.csv")
    actual=json.loads((case[1]/"report.json").read_text(encoding="utf-8"))
    require(actual["release"]["matching"] == case[3]["release"]["matching"], "matching report counts")
    require(actual['release']['plan'] == case[3]['release']['plan'], 'exact plan optimum/resource report')
    require(actual["files"]["unobserved_pairs.csv"] == case[3]["files"]["unobserved_pairs.csv"], "matching artifact checksum")


def check_chain():
    case = obtain("chain")
    rows = case[2]["molecules.csv"]
    require(len({row[3] for row in rows}) == 1, "expected transitive three-molecule component")
    exact_table(case, "molecules.csv")


def check_scaffold_chirality():
    case = obtain("chemistry")
    rows = {r[0]: r for r in case[2]["molecules.csv"]}
    require(rows["A"][3] == rows["B"][3], "same scaffold fixture")
    require(rows["C"][3] != rows["D"][3], "acyclic fallback fixture")
    require(rows["E"][1] != rows["F"][1] and rows["E"][3] != rows["F"][3], "chirality fixture")
    exact_table(case, "molecules.csv")


def check_full_chemistry():
    case = obtain("full")
    exact_table(case, "molecules.csv")
    actual=json.loads((case[1]/"report.json").read_text(encoding="utf-8"))
    require(actual["release"]["clusters"] == case[3]["release"]["clusters"], "cluster report count")
    for fold in FOLDS:
        require(actual["release"]["folds"][fold]["molecules"] == case[3]["release"]["folds"][fold]["molecules"], "fold molecule count")
    require(actual["files"]["molecules.csv"] == case[3]["files"]["molecules.csv"], "molecule manifest checksum")


def check_reverse_candidates():
    case = obtain("reverse")
    rows=actual_table(case,"unobserved_pairs.csv")
    require(len(rows) == len(case[2]["unobserved_pairs.csv"]), "reverse fixture target count")
    for row in rows:
        fold,index,a,typ,b,c,score,state=row
        i=int(index)-1
        require((a,int(typ),b) == case[4][fold][i], "reverse fixture target")
        if state == "MATCHED":
            require((c,int(score)) in case[5][fold][i], "unsafe reverse/other-type candidate")
        else:
            require(state == "UNMATCHED" and c == "" and score == "0", "reverse unmatched encoding")
    # Reverse known edges use event 2 while the target uses event 0.
    for row in actual_table(case,"unobserved_pairs.csv"):
        if row[2] == "D":
            require(row[5] not in ("F","I"), "reverse/other-type positive leakage")


def check_top8_scores():
    case = obtain("full")
    rows = actual_table(case, "unobserved_pairs.csv")
    targets, options = case[4], case[5]
    seen = {fold:set() for fold in FOLDS[1:]}
    indices = {fold:0 for fold in FOLDS[1:]}
    for row in rows:
        fold,index,a,typ,b,c,score,state = row
        require(fold in indices, "candidate fold")
        i = indices[fold]
        require(i < len(targets[fold]), "extra target")
        require((int(index),a,int(typ),b) == (i+1,*targets[fold][i]), "round-robin targets")
        if state == "MATCHED":
            require((c,int(score)) in options[fold][i], "candidate not in exact safe top-8")
            require(c not in seen[fold], "candidate capacity reused")
            seen[fold].add(c)
        else:
            require(state == "UNMATCHED" and c == "" and score == "0", "unmatched encoding")
        indices[fold] += 1
    require(all(indices[f] == len(targets[f]) for f in indices), "missing targets")
    # Ensure this is candidate production, not an all-unmatched placeholder.
    require(sum(len(v) for v in seen.values()) > 0, "candidate selection omitted")
    molecules,_,_,valid=curate(case[0],with_policy_ids=True)
    meta=clusters(molecules)
    resources,policies=policy_input(case[0]/'screen_plan.json',molecules,valid)
    actual=json.loads((case[1]/'report.json').read_text())
    for fold in FOLDS[1:]:
        matches=[(r[5],int(r[6])) if r[7] == 'MATCHED' else None for r in rows if r[0] == fold]
        ledger=resource_report(targets[fold],matches,meta,resources,policies[fold],actual['release']['plan'][fold]['status'])
        require(actual['release']['plan'][fold] == ledger, 'resource report differs from actual assays')
    check_exact_threshold()


def check_exact_threshold():
    wanted=('DB00014','DB00104','DB11660')
    raw={r[0]:r[1] for r in csv.reader((DATA/'drug_list.csv').open()) if r and r[0] in wanted}
    require(len(raw)==3,'immutable 0.15 fixture unavailable')
    root,out=temp(),temp()
    inputs(root,''.join(f'{d},{raw[d]}\n' for d in wanted),interactions='d1,type,d2\nDB00014,0,DB00104\n')
    tables,report,targets,options=expected(root)
    require(options['test']==[[('DB11660',1500)]], 'exact inclusive 0.15 fixture drift')
    case=(root,out,tables,report,targets,options,invoke(root,out))
    exact_table(case,'unobserved_pairs.csv')


def check_partition_full():
    case = obtain("full")
    exact_table(case, "positives.csv")
    actual=json.loads((case[1]/"report.json").read_text(encoding="utf-8"))
    require(actual["release"]["cross_fold_withheld"] == case[3]["release"]["cross_fold_withheld"], "withheld count")
    for fold in FOLDS:
        require(actual["release"]["folds"][fold]["positives"] == case[3]["release"]["folds"][fold]["positives"], "fold positive count")
    require(actual["files"]["positives.csv"] == case[3]["files"]["positives.csv"], "positive checksum")


def check_partition_tiny():
    case = obtain("base")
    exact_table(case, "positives.csv")
    empty = obtain("empty")
    for name in HEADERS:
        exact_table(empty,name)
    section(empty,"release")


def check_base():
    case = obtain("base")
    for key in ("input","drugs","events","interactions"):
        section(case,key)
    # Independent manual conservation and precedence counts.
    dropped = case[3]["interactions"]["dropped"]
    require(dropped == dict(malformed=2,missing_drug=1,conflicting_drug=1,invalid_drug=1,
                            unknown_type=1,conflicting_type=1,self_interaction=1,
                            alias_self_interaction=1,duplicate=1), "manual drop counts")
    require(case[3]["interactions"]["kept"] == 5, "manual kept count")
    actual=actual_table(case,"molecules.csv")
    require([r[:3] for r in actual] == [list(r[:3]) for r in case[2]["molecules.csv"]], "curated molecular identities")
    full=obtain("full")
    for key in ("input","drugs","events","interactions"):
        section(full,key)


def check_multiline():
    root,out = temp(),temp()
    inputs(root, '\ufeff\n\nA,CCO\nA,"bad\nSMILES"\nB,OCC\nC,CCC\nD,CCN\n',
           '\n0002,"multi\nline"\n2,"multi\nline"\n03,\n４,no\n1,extra,field\n',
           ' d1 , type , d2 \n A , 0002 , C \nB,2,C\nC,2,A\nA,４,D\n')
    tables, report, targets, options = expected(root)
    case=(root,out,tables,report,targets,options,invoke(root,out))
    require(report["drugs"]["invalid_rows"] == [dict(line=5,drug_id="A",reason="invalid_smiles")], "multiline physical line fixture")
    for key in ("input","drugs","events","interactions"):
        section(case,key)
    actual=actual_table(case,"molecules.csv")
    require([r[:3] for r in actual] == [list(r[:3]) for r in tables["molecules.csv"]], "multiline molecular identities")

    # All three inputs have a BOM, leading blank lines and standard CSV escaping.
    # One-field whitespace is ignored; multi-field empty records are rejected.
    root,out = temp(),temp()
    inputs(root, '\ufeff\n\n"A,one",CCO\n"B""two",CCC\n" ",CCN\n,\n,,\n',
           '\ufeff\n\n0,"dose ""high"", daily"\n00,"dose ""high"", daily"\n1,other\n,\n,,\n" "\n',
           '\ufeff\n\n d1 , type , d2 \n"A,one",00,"B""two"\n\n,\n,,\n" "\n')
    tables,report,targets,options = expected(root)
    case=(root,out,tables,report,targets,options,invoke(root,out))
    require(report["input"] == {"drug_rows":5,"event_rows":5,"interaction_rows":3}, "manual CSV record counts")
    require(report["drugs"]["invalid_rows"] == [
        dict(line=5,drug_id="",reason="malformed"),
        dict(line=6,drug_id="",reason="malformed"),
        dict(line=7,drug_id="",reason="malformed")], "manual empty drug rejections")
    require(report["events"]["invalid_rows"] == [
        dict(line=6,event_type="",reason="invalid_type"),
        dict(line=7,event_type="",reason="malformed")], "manual empty event rejections")
    require(report["interactions"]["kept"] == 1 and report["interactions"]["dropped"]["malformed"] == 2,
            "manual empty interaction rejections")
    for key in ("input","drugs","events","interactions"):
        section(case,key)
    # CCO and CCC hash to the test fold. This fixture has no matching choices;
    # checking all artifacts here only exercises CSV parsing/serialization.
    require([row[:3] for row in tables["molecules.csv"]] == [
        ("A,one","CCO","A,one"),("B\"two","CCC","B\"two")], "manual escaped identities")
    for name in HEADERS:
        exact_table(case,name)


def check_determinism():
    case=obtain("lex")
    exact_table(case,"molecules.csv")
    for name in HEADERS:
        actual_table(case,name)
    manifest=json.loads((case[1]/"report.json").read_text(encoding="utf-8"))["files"]
    for name in HEADERS:
        require(manifest[name]["sha256"] == digest((case[1]/name).read_bytes()), "artifact manifest not actual bytes")
    first={name:(case[1]/name).read_bytes() for name in NAMES}
    result=invoke(case[0],case[1])
    require(result.returncode == 0, "rerun failed")
    require(first == {name:(case[1]/name).read_bytes() for name in NAMES}, "rerun changed bytes")
    created_out = temp()/"missing-parent"/"release"
    require(not created_out.exists() and not created_out.parent.exists(), "output fixture already exists")
    result=invoke(case[0],created_out)
    require(result.returncode == 0 and created_out.is_dir(), "nested output directory not created")
    require(first == {name:(created_out/name).read_bytes() for name in NAMES}, "new directory changed output bytes")
    # Reverse input records and add a smaller alias. Molecular split must be stable.
    root,out = temp(),temp()
    drugs=list(csv.reader((case[0]/"drug_list.csv").open(encoding="utf-8")))
    drugs.reverse()
    drugs.append(["00",dict(drugs)["F"]])
    (root/"drug_list.csv").write_text(csv_bytes([],drugs).decode().lstrip("\n"),encoding="utf-8")
    for name in ("DDI_event.csv","newddi.csv"):
        with (case[0]/name).open(encoding="utf-8",newline="") as handle:
            rows=list(csv.reader(handle))
        rows=rows[:1]+list(reversed(rows[1:])) if name == "newddi.csv" else list(reversed(rows))
        stream="\n".join(",".join(row) for row in rows)+"\n"
        (root/name).write_text(stream,encoding="utf-8")
    (root/'screen_plan.json').write_bytes((case[0]/'screen_plan.json').read_bytes())
    exp=expected(root)
    second=(root,out,*exp,invoke(root,out))
    exact_table(second,"molecules.csv")
    before={r[1]:r[3:] for r in case[2]["molecules.csv"]}
    after={r[1]:r[3:] for r in exp[0]["molecules.csv"]}
    require(before == after, "alias changed chemical fold")


def check_fatal():
    cases=[("newddi.csv", b"wrong,type,d2\n"),("newddi.csv",b""),
           ("drug_list.csv",b'A,"unterminated\n'),("DDI_event.csv",b'0,"unterminated\n'),
           ("newddi.csv",b'd1,type,d2\nA,0,"unterminated\n'),
           ("drug_list.csv",b"\xff"),("DDI_event.csv",b"\xff"),("newddi.csv",b"\xff"),
           ("missing",None),("cli",None)]
    for index,(name,data) in enumerate(cases):
        root,out=temp(),temp()
        inputs(root,"A,CCO\nB,CCC\n",interactions="d1,type,d2\nA,0,B\n")
        sentinels={key: f"old-{index}-{key}\r\n\x00".encode() for key in NAMES}
        for key,value in sentinels.items():
            (out/key).write_bytes(value)
        if data is not None:
            (root/name).write_bytes(data)
        elif name == "missing":
            (root/"DDI_event.csv").unlink()
        result=invoke(root,out,extra=("--unknown-option",) if name == "cli" else ())
        require(result.returncode != 0 and bool(result.stderr.strip()), "fatal error not reported")
        require({key:(out/key).read_bytes() for key in NAMES} == sentinels,"fatal input clobbered output")
    flags=("--drugs","--events","--interactions","--screen-plan","--out-dir")
    for omitted in [(flag,) for flag in flags]+[flags]:
        root,out=temp(),temp()
        inputs(root,"A,CCO\nB,CCC\n",interactions="d1,type,d2\nA,0,B\n")
        sentinels={key: ("old-cli-"+",".join(omitted)+"-"+key+"\r\n\x00").encode() for key in NAMES}
        for key,value in sentinels.items():
            (out/key).write_bytes(value)
        result=invoke(root,out,omit=omitted)
        require(result.returncode != 0 and bool(result.stderr.strip()), f"missing CLI {omitted} not reported")
        require({key:(out/key).read_bytes() for key in NAMES} == sentinels,"missing CLI argument clobbered output")
    check_bad_plans()


def check_bad_plans():
    root,out=temp(),temp()
    inputs(root,'A,CCO\nB,OCC\nI,bad\nX,CC\nX,CN\n',events='0,zero\n1,one\n1,conflict\n')
    good=write_policy(root)
    variants=['{', '{"version":1,"version":1}', '[]', 'null']
    def altered(change):
        data=json.loads(json.dumps(good)); change(data); variants.append(json.dumps(data))
    for key,value in [('version',True),('version',2),('version',1.0),('unknown',0)]:
        altered(lambda d,k=key,v=value:d.update({k:v}))
    for key,value in [('stock',True),('stock',-1),('stock',97),('setup_cost',10001),('stock',2.0)]:
        altered(lambda d,k=key,v=value:d['defaults'].update({k:v}))
    for key,value in [('budget',-1),('budget',1000001),('assay_cost',10001),('max_pairs',49),('cluster_cap',49),('budget',False),('max_pairs',1.0),('extra',0)]:
        altered(lambda d,k=key,v=value:d['folds']['test'].update({k:v}))
    altered(lambda d:d['folds'].pop('test'))
    altered(lambda d:d['defaults'].pop('stock'))
    altered(lambda d:d.update(drug_overrides={}))
    for drug in ['missing','I','X',1]:
        altered(lambda d,x=drug:d.update(drug_overrides=[dict(drug_id=x,stock=1,setup_cost=0)]))
    altered(lambda d:d.update(drug_overrides=[dict(drug_id='A',stock=1,setup_cost=0),dict(drug_id='B',stock=2,setup_cost=0)]))
    altered(lambda d:d.update(drug_overrides=[dict(drug_id='A',stock=1,setup_cost=0,extra=1)]))
    for quota in [dict(type=99,min=0,max=1),dict(type=1,min=0,max=1),dict(type=True,min=0,max=1),dict(type=0,min=2,max=1),dict(type=0,min=-1,max=2),dict(type=0,min=0,max=49),dict(type=0,min=0,max=1.0)]:
        altered(lambda d,q=quota:d['folds']['test'].update(event_quotas=[q]))
    altered(lambda d:d['folds']['test'].update(event_quotas=[dict(type=0,min=0,max=1)]*2))
    variants += [json.dumps(good).replace('"stock": 96','"stock": 96, "stock": 96',1), json.dumps(good).replace('96','NaN',1)]
    for index,text in enumerate(variants+[None,'INVALID_UTF8']):
        sentinels={n:f'old-plan-{index}-{n}\x00'.encode() for n in NAMES}
        for name,value in sentinels.items(): (out/name).write_bytes(value)
        path=root/'screen_plan.json'
        if text is None: path.unlink()
        else: path.write_bytes(b'\xff' if text=='INVALID_UTF8' else text.encode())
        result=invoke(root,out)
        require(result.returncode != 0 and bool(result.stderr.strip()),f'bad plan {index} accepted')
        require(sentinels=={n:(out/n).read_bytes() for n in NAMES},'bad plan clobbered output')


CHECKS = [
    ("matching_cardinality",.10,lambda:check_assignment("cardinality")),
    ("matching_score",.10,lambda:check_assignment("score")),
    ("matching_cost_lex",.10,lambda:check_assignment("lex")),
    ("matching_full",.05,check_matching_full),
    ("chemistry_transitive",.08,check_chain),
    ("chemistry_scaffold_chirality",.05,check_scaffold_chirality),
    ("chemistry_full",.07,check_full_chemistry),
    ("candidate_reverse",.08,check_reverse_candidates),
    ("candidate_top8_score",.07,check_top8_scores),
    ("partition_full",.06,check_partition_full),
    ("partition_empty_tiny",.04,check_partition_tiny),
    ("curation_precedence",.07,check_base),
    ("curation_csv_numeric",.03,check_multiline),
    ("determinism_alias",.05,check_determinism),
    ("fatal_no_clobber",.05,check_fatal),
]


def selfcheck_model():
    """Validate the verifier's optimizer without any access to the Oracle."""
    rng=random.Random(821)
    for _ in range(120):
        options=[[(c,rng.randrange(1500,10001)) for c in "ABCD" if rng.random()<.5]
                 for _ in range(rng.randrange(1,5))]
        best=None
        for values in itertools.product(*[row+[None] for row in options]):
            keys=[v[0] for v in values if v]
            if len(keys)!=len(set(keys)):
                continue
            objective=(-len(keys),-sum(v[1] for v in values if v),tuple(v[0] if v else "\uffff" for v in values))
            if best is None or objective<best[0]:
                best=(objective,list(values))
        require(assignment(options)==best[1],"verifier assignment selfcheck failed")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--reward-file",required=True)
    parser.add_argument("--details-file",required=True)
    args=parser.parse_args()
    start=time.monotonic()
    selfcheck_model()
    outcomes=[]
    for name,weight,check in CHECKS:
        try:
            check()
            result={"name":name,"weight":weight,"passed":True}
        except Exception as exc:
            result={"name":name,"weight":weight,"passed":False,"error":str(exc)[:600]}
        outcomes.append(result)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    score=round(sum(item["weight"] for item in outcomes if item["passed"]),6)
    Path(args.reward_file).write_text(str(score),encoding="utf-8")
    Path(args.details_file).write_text(json.dumps({"reward":score,"elapsed_sec":round(time.monotonic()-start,3),"checks":outcomes},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"reward={score}",flush=True)


if __name__ == "__main__":
    main()
