"""Command adapter used by the legacy laboratory automation."""
from ingest import load_legacy,receive,events
from optimizer import orient
from state import apply
from views import render
from publication import legacy,write_draft

def legacy_export(args):
    obj=load_legacy(args.input);assignment=orient(obj['variables'],obj['relations'])
    return legacy(assignment,render(obj['observations'],assignment))

def prepare(args):
    manifest,raw=receive(args.manifest);table=apply(events(raw))
    draft=dict(batch_id=manifest['batch_id'],base=args.base,variables=manifest['variables'],records=[dict(kind=k[0],id=k[1],record=v) for k,v in sorted(table.items())])
    write_draft(args.store,args.ticket,draft)
    raise NotImplementedError('publication certification protocol is not available in this adapter')
