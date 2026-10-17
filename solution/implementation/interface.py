import json, re
SLOT_RE=re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
MIN_N,MAX_N=5,80
QUERY_KEYS=("id","n","red_forbid","blue_forbid","fixed","degrees","cuts")
CUT_KEYS=("left","right","min","max")
class InputError(Exception):
    pass

def _pairs_hook(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise InputError("duplicate JSON key: %r" % (key,))
        seen[key] = value
    return seen

def _reject_constant(name):
    raise InputError("non-finite numeric constant in JSON: %s" % (name,))

def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)

def validate_document(doc):
    if not isinstance(doc, dict):
        raise InputError("top level must be a JSON object")
    if set(doc.keys()) != {"version", "queries"}:
        raise InputError("top level must have exactly version and queries")
    version = doc["version"]
    if not _is_int(version) or version != 1:
        raise InputError("version must be the integer 1")
    queries = doc["queries"]
    if not isinstance(queries, list):
        raise InputError("queries must be a list")
    if not (1 <= len(queries) <= 32):
        raise InputError("queries must contain 1..32 entries")

    parsed = []
    seen_ids = set()
    for qindex, query in enumerate(queries):
        where = "queries[%d]" % qindex
        if not isinstance(query, dict):
            raise InputError("%s must be an object" % where)
        if set(query.keys()) != set(QUERY_KEYS):
            raise InputError("%s must have exactly %s"
                             % (where, ",".join(QUERY_KEYS)))
        qid = query["id"]
        if not isinstance(qid, str) or SLOT_RE.match(qid) is None:
            raise InputError("%s.id is not a valid identifier" % where)
        if qid in seen_ids:
            raise InputError("duplicate query id: %r" % (qid,))
        seen_ids.add(qid)

        n = query["n"]
        if not _is_int(n) or not (MIN_N <= n <= MAX_N):
            raise InputError(where + ".n must be an integer in 5..80")
        kr = query["red_forbid"]
        kb = query["blue_forbid"]
        for name, value in (("red_forbid", kr), ("blue_forbid", kb)):
            if not _is_int(value) or not (3 <= value <= 8):
                raise InputError("%s.%s must be an integer in 3..8" % (where, name))
            if value > n:
                raise InputError("%s.%s cannot exceed n" % (where, name))

        raw_fixed = query["fixed"]
        if not isinstance(raw_fixed, list):
            raise InputError(where + ".fixed must be a list")
        if len(raw_fixed) > n * (n - 1) // 2:
            raise InputError(where + ".fixed has too many entries")
        fixed = []
        seen_edges = set()
        for findex, item in enumerate(raw_fixed):
            loc = "%s.fixed[%d]" % (where, findex)
            if not isinstance(item, list) or len(item) != 3:
                raise InputError(loc + " must be a triple")
            u, v, c = item
            if not (_is_int(u) and _is_int(v) and _is_int(c)):
                raise InputError(loc + " must contain integers")
            if not (0 <= u < v < n):
                raise InputError(loc + ": require 0 <= u < v < n")
            if c not in (0, 1):
                raise InputError(loc + ": colour must be 0 or 1")
            if (u, v) in seen_edges:
                raise InputError(loc + ": duplicate edge")
            seen_edges.add((u, v))
            fixed.append((u, v, c))

        raw_degrees = query["degrees"]
        if not isinstance(raw_degrees, list) or len(raw_degrees) != n:
            raise InputError(where + ".degrees must have n entries")
        degrees = []
        for vindex, pair in enumerate(raw_degrees):
            if not isinstance(pair, list) or len(pair) != 2:
                raise InputError("%s.degrees[%d] must be a pair" % (where, vindex))
            lo, hi = pair
            if not (_is_int(lo) and _is_int(hi)):
                raise InputError("%s.degrees[%d] must be integers" % (where, vindex))
            if not (0 <= lo <= hi <= n - 1):
                raise InputError("%s.degrees[%d]: require 0 <= low <= high <= n-1"
                                 % (where, vindex))
            degrees.append((lo, hi))

        raw_cuts = query["cuts"]
        if not isinstance(raw_cuts, list):
            raise InputError(where + ".cuts must be a list")
        if len(raw_cuts) > 16:
            raise InputError(where + ".cuts must contain at most 16 entries")
        cuts = []
        for cindex, item in enumerate(raw_cuts):
            loc = "%s.cuts[%d]" % (where, cindex)
            if not isinstance(item, dict):
                raise InputError(loc + " must be an object")
            if set(item.keys()) != set(CUT_KEYS):
                raise InputError(loc + " must have exactly left,right,min,max")
            sides = []
            for key in ("left", "right"):
                raw = item[key]
                if not isinstance(raw, list) or len(raw) == 0:
                    raise InputError(loc + "." + key + " must be a non-empty list")
                seen_local = set()
                for value in raw:
                    if not _is_int(value) or not (0 <= value < n):
                        raise InputError(loc + "." + key + ": index out of range")
                    if value in seen_local:
                        raise InputError(loc + "." + key + ": duplicate vertex")
                    seen_local.add(value)
                sides.append(seen_local)
            left, right = sides
            if left & right:
                raise InputError(loc + ": left and right must be disjoint")
            lo = item["min"]
            hi = item["max"]
            if not (_is_int(lo) and _is_int(hi)):
                raise InputError(loc + ": min/max must be integers")
            cap = len(left) * len(right)
            if not (0 <= lo <= hi <= cap):
                raise InputError(loc + ": require 0 <= min <= max <= |left|*|right|")
            lm = 0
            for v in left:
                lm |= 1 << v
            rm = 0
            for v in right:
                rm |= 1 << v
            cuts.append((lm, rm, lo, hi))

        parsed.append((qid, n, kr, kb, fixed, degrees, cuts))
    return parsed

def load_document(path):
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise InputError("cannot read input: %s" % (exc,))
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError("input is not valid UTF-8: %s" % (exc,))
    try:
        doc = json.loads(text, object_pairs_hook=_pairs_hook,
                         parse_constant=_reject_constant)
    except InputError:
        raise
    except Exception as exc:
        raise InputError("invalid JSON: %s" % (exc,))
    return validate_document(doc)
