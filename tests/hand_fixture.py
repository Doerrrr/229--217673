"""One hand-resolved duplicate/prefix example, not a general solver."""
from copy import deepcopy
import sys
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]/'cohort_unordered'
if str(BASE) not in sys.path:sys.path.insert(0,str(BASE))
from fixtures import Record,Batch,Case

def fixture():
    r0=Record('chr7',31,'A',('G',),('GT','AD','PL'),(('S',('0|1',[10,20],[101,102,103])),))
    r1=Record('chr7',31,'A',('G',),('GT','AD','PL'),(('S',('1|1',[12,22],[111,112,113])),))
    r2=Record('chr7',31,'AC',('TC',),('GT','AD','PL'),(('S',('0|1',[30,40],[201,202,203])),))
    case=Case('duplicate_prefix',(Batch('first',('S',),(r0,r1)),Batch('second',('S',),(r2,))),('S',))
    release=[{'chrom':'chr7','position':31,'reference':'AC','alternate':['GC','TC'],
      'contributors':[{'source':'first','ordinal':0},{'source':'first','ordinal':1},{'source':'second','ordinal':0}],
      'samples':[{'name':'S','winner':{'source':'first','ordinal':0,'format':['GT','AD','PL'],
        'values':{'GT':'0|1','AD':[10,20,None],'PL':[101,102,103,None,None,None]}},
        'others':[{'source':'first','ordinal':1,'format':['GT','AD','PL'],
          'values':{'GT':'1|1','AD':[12,22,None],'PL':[111,112,113,None,None,None]}},
          {'source':'second','ordinal':0,'format':['GT','AD','PL'],
          'values':{'GT':'0|2','AD':[30,None,40],'PL':[201,None,None,202,None,203]}}]}]}]
    original=[
      {'source':'first','ordinal':0,'chrom':'chr7','position':31,'reference':'A','alternate':['G'],
       'format':['GT','AD','PL'],'samples':[{'name':'S','values':{'GT':'0|1','AD':[10,20],'PL':[101,102,103]}}]},
      {'source':'first','ordinal':1,'chrom':'chr7','position':31,'reference':'A','alternate':['G'],
       'format':['GT','AD','PL'],'samples':[{'name':'S','values':{'GT':'1|1','AD':[12,22],'PL':[111,112,113]}}]},
      {'source':'second','ordinal':0,'chrom':'chr7','position':31,'reference':'AC','alternate':['TC'],
       'format':['GT','AD','PL'],'samples':[{'name':'S','values':{'GT':'0|1','AD':[30,40],'PL':[201,202,203]}}]},
    ]
    return case,deepcopy(release),deepcopy(original)
