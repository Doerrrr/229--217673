"""Validated CLI schema adapted from the user-supplied DDI-032 answer."""
import json
import re
from fractions import Fraction
EXIT_FORMAT=4
RATION=re.compile(r"[+-]?[0-9]+(?:/[0-9]+)?\Z")
ID_CHARS=set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
LIMIT=Fraction(10)**12


class Bad(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message

def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise Bad(EXIT_FORMAT, "duplicate object key %r" % key)
        out[key] = value
    return out

def _reject_constant(text):
    raise Bad(EXIT_FORMAT, "%s is not a JSON number" % text)

def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)

def _need_object(value, where):
    if not isinstance(value, dict):
        raise Bad(EXIT_FORMAT, "%s must be an object" % where)
    return value

def _need_list(value, where):
    if not isinstance(value, list):
        raise Bad(EXIT_FORMAT, "%s must be a list" % where)
    return value

def _need_keys(obj, allowed, where):
    keys = set(obj)
    if keys != allowed:
        missing = sorted(allowed - keys)
        if missing:
            raise Bad(EXIT_FORMAT, "%s is missing %s" % (where, ",".join(missing)))
        raise Bad(EXIT_FORMAT, "%s has unknown field %s"
                  % (where, ",".join(sorted(keys - allowed))))

def _int_in(value, low, high, where):
    if not _is_int(value):
        raise Bad(EXIT_FORMAT, "%s must be an integer" % where)
    if not (low <= value <= high):
        raise Bad(EXIT_FORMAT, "%s is out of range" % where)
    return value

def _parse_rational(text, where):
    if not isinstance(text, str):
        raise Bad(EXIT_FORMAT, "%s must be a string" % where)
    if len(text) > 80:
        raise Bad(EXIT_FORMAT, "%s is longer than 80 characters" % where)
    if not RATION.match(text):
        raise Bad(EXIT_FORMAT, "%s is not a valid rational" % where)
    if "/" in text:
        head, _, tail = text.partition("/")
        value = Fraction(int(head), int(tail))
    else:
        value = Fraction(int(text))
    return value

def _monomial(raw, where, max_len):
    lst = _need_list(raw, where)
    if len(lst) > max_len:
        raise Bad(EXIT_FORMAT, "%s is longer than %d" % (where, max_len))
    previous = -1
    for item in lst:
        if not _is_int(item):
            raise Bad(EXIT_FORMAT, "%s has a non-integer index" % where)
        if item <= previous:
            raise Bad(EXIT_FORMAT, "%s is not strictly increasing" % where)
        previous = item
    return tuple(lst)

def parse_query(raw, index):
    where = "queries[%d]" % index
    obj = _need_object(raw, where)
    _need_keys(obj, {"id", "n", "basis", "terms"}, where)
    ident = obj["id"]
    if not isinstance(ident, str) or not (1 <= len(ident) <= 64):
        raise Bad(EXIT_FORMAT, where + ".id must be a 1-64 character string")
    for ch in ident:
        if ch not in ID_CHARS:
            raise Bad(EXIT_FORMAT, where + ".id has a character outside [A-Za-z0-9_-]")
    n = _int_in(obj["n"], 2, 32, where + ".n")

    basis_raw = _need_list(obj["basis"], where + ".basis")
    if not (1 <= len(basis_raw) <= 65):
        raise Bad(EXIT_FORMAT, where + ".basis must hold 1..65 monomials")
    basis = []
    seen = set()
    for item in basis_raw:
        mono = _monomial(item, where + ".basis[]", 2)
        for v in mono:
            if not (0 <= v < n):
                raise Bad(EXIT_FORMAT, where + ".basis[] has an index outside 0..n-1")
        if mono in seen:
            raise Bad(EXIT_FORMAT, where + ".basis repeats a monomial")
        seen.add(mono)
        basis.append(mono)
    if basis[0] != ():
        raise Bad(EXIT_FORMAT, where + ".basis must start with the empty monomial")
    for v in range(n):
        if (v,) not in seen:
            raise Bad(EXIT_FORMAT, where + ".basis must contain every single variable")

    terms_raw = _need_list(obj["terms"], where + ".terms")
    if not (1 <= len(terms_raw) <= 32768):
        raise Bad(EXIT_FORMAT, where + ".terms must hold 1..32768 entries")
    terms = []
    seen_terms = set()
    for item in terms_raw:
        term = _need_object(item, where + ".terms[]")
        _need_keys(term, {"vars", "coef"}, where + ".terms[]")
        mono = _monomial(term["vars"], where + ".terms[].vars", 4)
        for v in mono:
            if not (0 <= v < n):
                raise Bad(EXIT_FORMAT, where + ".terms[].vars has an index outside 0..n-1")
        if mono in seen_terms:
            raise Bad(EXIT_FORMAT, where + ".terms repeats a monomial")
        seen_terms.add(mono)
        coef = _parse_rational(term["coef"], where + ".terms[].coef")
        if coef == 0:
            raise Bad(EXIT_FORMAT, where + ".terms[].coef must not be zero")
        if abs(coef) > LIMIT:
            raise Bad(EXIT_FORMAT, where + ".terms[].coef is out of range")
        terms.append((mono, coef))
    return {"id": ident, "n": n, "basis": basis, "terms": terms}

def parse_document(text):
    try:
        doc = json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except Bad:
        raise
    except Exception as error:
        raise Bad(EXIT_FORMAT, "input is not valid JSON (%s)" % error.__class__.__name__)
    obj = _need_object(doc, "document")
    _need_keys(obj, {"version", "queries"}, "document")
    if not _is_int(obj["version"]) or obj["version"] != 1:
        raise Bad(EXIT_FORMAT, "version must be the integer 1")
    raw_queries = _need_list(obj["queries"], "queries")
    if not (1 <= len(raw_queries) <= 16):
        raise Bad(EXIT_FORMAT, "queries must hold 1..16 entries")
    queries = []
    seen = set()
    for index, raw in enumerate(raw_queries):
        query = parse_query(raw, index)
        if query["id"] in seen:
            raise Bad(EXIT_FORMAT, "duplicate query id %r" % query["id"])
        seen.add(query["id"])
        queries.append(query)
    return queries
