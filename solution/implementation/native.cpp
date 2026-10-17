// Input-driven tabu construction. Every emitted graph is rechecked in Python.
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <climits>
#include <iostream>
#include <numeric>
#include <random>
#include <vector>
using namespace std;
using Bits=__uint128_t;
int pc(Bits x){return __builtin_popcountll((uint64_t)x)+__builtin_popcountll((uint64_t)(x>>64));}
int first(Bits x){return (uint64_t)x?__builtin_ctzll((uint64_t)x):64+__builtin_ctzll((uint64_t)(x>>64));}
struct Cut {vector<int>a,b;int lo,hi,value=0;};
struct Edge {int u,v,fixed=-1;vector<int>cuts;};
struct Search {
 int n,kr,kb;double budget;vector<Edge>edges;int ei[80][80];
 vector<pair<int,int>> bounds;vector<Cut>cuts;vector<int>degree,tabu;
 array<Bits,80>red{},blue{};Bits full;long long mono[2]{},dw=1,cw=1;
 mt19937 rng{310031};chrono::steady_clock::time_point start;long long steps=0;
 array<Bits,80> bestred{};long long best_raw=LLONG_MAX;
 double elapsed(){return chrono::duration<double>(chrono::steady_clock::now()-start).count();}
 long long count(Bits mask,int need,int color){
  if(need==0)return 1;if(pc(mask)<need)return 0;if(need==1)return pc(mask);
  auto &adj=color?red:blue;long long total=0;
  while(pc(mask)>=need){int v=first(mask);mask&=mask-1;total+=count(mask&adj[v],need-1,color);}return total;
 }
 bool find(Bits mask,int need,int color,vector<int>&out){
  if(!need)return true;auto &adj=color?red:blue;
  while(pc(mask)>=need){int v=first(mask);mask&=mask-1;out.push_back(v);
   if(find(mask&adj[v],need-1,color,out))return true;out.pop_back();}return false;
 }
 long long around(int u,int v,int c){auto &a=c?red:blue;return count(a[u]&a[v],(c?kr:kb)-2,c);}
 int value(int e){return bool(red[edges[e].u]&(Bits(1)<<edges[e].v));}
 long long violation(int v,int d){return max(0,bounds[v].first-d)+max(0,d-bounds[v].second);}
 long long cv(int c,int x){return max(0,cuts[c].lo-x)+max(0,x-cuts[c].hi);}
 void setcolor(int e,int color){
  auto &a=edges[e];int u=a.u,v=a.v,old=value(e);if(old==color)return;
  int change=color?1:-1;degree[u]+=change;degree[v]+=change;
  if(color){red[u]|=Bits(1)<<v;red[v]|=Bits(1)<<u;blue[u]&=~(Bits(1)<<v);blue[v]&=~(Bits(1)<<u);}
  else{blue[u]|=Bits(1)<<v;blue[v]|=Bits(1)<<u;red[u]&=~(Bits(1)<<v);red[v]&=~(Bits(1)<<u);}
  for(int c:a.cuts)cuts[c].value+=change;
 }
 long long penalty(){long long x=mono[0]+mono[1];for(int i=0;i<n;i++)x+=dw*violation(i,degree[i]);for(int c=0;c<(int)cuts.size();c++)x+=cw*cv(c,cuts[c].value);return x;}
 void remember(){long long x=mono[0]+mono[1];for(int i=0;i<n;i++)x+=violation(i,degree[i]);for(int c=0;c<(int)cuts.size();c++)x+=cv(c,cuts[c].value);if(x<best_raw){best_raw=x;bestred=red;}}
 long long delta(int e){auto &a=edges[e];int old=value(e),d=old?-1:1;
  long long result=around(a.u,a.v,1-old)-around(a.u,a.v,old);
  for(int v:{a.u,a.v})result+=dw*(violation(v,degree[v]+d)-violation(v,degree[v]));
  for(int c:a.cuts)result+=cw*(cv(c,cuts[c].value+d)-cv(c,cuts[c].value));return result;
 }
 void apply(int e){auto&a=edges[e];int old=value(e);mono[old]-=around(a.u,a.v,old);mono[1-old]+=around(a.u,a.v,1-old);setcolor(e,1-old);}
 bool valid(){
  for(auto&e:edges)if(e.fixed>=0&&int(bool(red[e.u]&(Bits(1)<<e.v)))!=e.fixed)return false;
  for(int i=0;i<n;i++)if(violation(i,degree[i]))return false;
  for(int c=0;c<(int)cuts.size();c++)if(cv(c,cuts[c].value))return false;
  return count(full,kr,1)==0&&count(full,kb,0)==0;
 }
 void init(int prime,int complement){
  degree.assign(n,0);red.fill(0);blue.fill(0);for(int i=0;i<n;i++)blue[i]=full^(Bits(1)<<i);
  for(auto&c:cuts)c.value=0;
  vector<int>p(max(n,prime));iota(p.begin(),p.end(),0);shuffle(p.begin(),p.end(),rng);
  vector<int>res(max(1,prime),0);for(int i=1;i<prime;i++)res[i*i%prime]=1;
  for(int e=0;e<(int)edges.size();e++){
   auto&a=edges[e];int c=prime?res[(p[a.u]-p[a.v]+prime)%prime]^complement:int(rng()&1);
   if(a.fixed>=0)c=a.fixed;setcolor(e,c);
  }
  mono[0]=count(full,kb,0);mono[1]=count(full,kr,1);tabu.assign(edges.size(),0);
 }
 bool run(){
  start=chrono::steady_clock::now();full=(Bits(1)<<n)-1;
  vector<int>primes;for(int p=n;p<=max(n+8,101);p++)if(p%4==1){bool prime=true;for(int d=2;d*d<=p;d++)if(p%d==0)prime=false;if(prime)primes.push_back(p);}
  int restart=0;
  while(elapsed()<budget){
   int p=restart%4==3?0:primes[(restart/2)%primes.size()];init(p,restart%2);dw=cw=1;
   remember();if(valid())return true;
   long long current=penalty(),best=current;int stale=0;
   for(int step=1;step<=250000&&elapsed()<budget;step++,steps++){
    if(!current&&valid())return true;
    vector<int>pool;int choice=rng()%3;
    if((choice==0||cuts.empty())&&(mono[0]||mono[1])){
     int color=mono[1]?1:0;if(mono[0]&&mono[1])color=rng()%2;vector<int>clique;
     // Randomize vertex labels between restarts; exact find yields a violated constraint.
     if(find(full,color?kr:kb,color,clique))for(int i=0;i<(int)clique.size();i++)for(int j=0;j<i;j++)pool.push_back(ei[clique[i]][clique[j]]);
    }
    if(pool.empty()&&choice<=1){vector<int>bad;for(int i=0;i<n;i++)if(violation(i,degree[i]))bad.push_back(i);
     if(!bad.empty()){int u=bad[rng()%bad.size()];for(int v=0;v<n;v++)if(u!=v)pool.push_back(ei[u][v]);}}
    if(pool.empty()) {vector<int>bad;for(int c=0;c<(int)cuts.size();c++)if(cv(c,cuts[c].value))bad.push_back(c);
     if(!bad.empty()){auto&c=cuts[bad[rng()%bad.size()]];for(int u:c.a)for(int v:c.b)pool.push_back(ei[u][v]);}}
    if(pool.empty())for(int i=0;i<60;i++)pool.push_back(rng()%edges.size());
    if(pool.size()>100){shuffle(pool.begin(),pool.end(),rng);pool.resize(100);}
    long long bd=LLONG_MAX;int move=-1,ties=0;
    for(int e:pool){if(edges[e].fixed>=0)continue;long long d=delta(e);if(tabu[e]>step&&current+d>=best)continue;
     if(d<bd){bd=d;move=e;ties=1;}else if(d==bd&&rng()%++ties==0)move=e;}
    if(move<0){stale++;continue;}
    apply(move);current+=bd;remember();tabu[move]=step+3+rng()%max(4,n/4);
    if(current<best){best=current;stale=0;}else stale++;
    if(stale>10000)break;
    if(step%12000==0){dw=1+rng()%4;cw=1+rng()%4;current=penalty();best=current;stale=0;}
   }
   restart++;
  }
  red=bestred;return false;
 }
 void read(){
  cin>>n>>kr>>kb>>budget;int fixed;cin>>fixed;vector<array<int,3>>f(fixed);for(auto&a:f)cin>>a[0]>>a[1]>>a[2];
  for(int u=0;u<n;u++)for(int v=u+1;v<n;v++){ei[u][v]=ei[v][u]=edges.size();edges.push_back({u,v,-1,{}});}
  for(auto&a:f)edges[ei[a[0]][a[1]]].fixed=a[2];
  bounds.resize(n);for(auto&b:bounds)cin>>b.first>>b.second;
  int count;cin>>count;cuts.resize(count);
  for(int c=0;c<count;c++){auto&cut=cuts[c];int a,b;cin>>a>>b>>cut.lo>>cut.hi;cut.a.resize(a);cut.b.resize(b);
   for(auto&v:cut.a)cin>>v;for(auto&v:cut.b)cin>>v;for(int u:cut.a)for(int v:cut.b)edges[ei[u][v]].cuts.push_back(c);}
  degree.resize(n);
 }
};
// Bit-domain CSP for a labelled induced algebraic graph. Unfixed edges remain
// unknown constraints; no completed graph is stored in the program.
struct Embedding {
 Search &q;int p;bool wide=false;Bits full;array<Bits,104>adj{};vector<vector<pair<int,int>>>arcs;
 vector<int>cut_degree,answer;chrono::steady_clock::time_point begin;double budget;long long nodes=0;
 using State=array<Bits,104>;
 Embedding(Search&s):q(s),budget(s.budget){begin=chrono::steady_clock::now();}
 bool expired(){return chrono::duration<double>(chrono::steady_clock::now()-begin).count()>=budget;}
 Bits neighborhood(int a,int color){return color?adj[a]:(full^adj[a]^(Bits(1)<<a));}
 bool clique(Bits mask,int need,int color){if(!need)return true;while(pc(mask)>=need){int v=first(mask);mask&=mask-1;if(clique(mask&neighborhood(v,color),need-1,color))return true;}return false;}
 bool restrict_pair(State &d,int u,int v,int color,bool &changed){
  Bits keep=0,mask=d[u];while(mask){int a=first(mask);mask&=mask-1;if(neighborhood(a,color)&d[v])keep|=Bits(1)<<a;}
  if(!keep)return false;if(keep!=d[u]){d[u]=keep;changed=true;}return true;
 }
 bool propagate(State&d){
  bool changed=true;
  while(changed){
   changed=false;Bits taken=0;
   for(int u=0;u<p;u++){if(!d[u])return false;if(pc(d[u])==1){if(taken&d[u])return false;taken|=d[u];}}
   for(int u=0;u<p;u++)if(pc(d[u])>1){Bits keep=d[u]&~taken;if(!keep)return false;if(keep!=d[u]){d[u]=keep;changed=true;}}
   array<int,104>support{},only{};
   for(int u=0;u<p;u++){Bits mask=d[u];while(mask){int a=first(mask);mask&=mask-1;support[a]++;only[a]=u;}}
   for(int a=0;a<p;a++){if(!support[a])return false;if(support[a]==1&&d[only[a]]!=(Bits(1)<<a)){d[only[a]]=Bits(1)<<a;changed=true;}}
   for(int u=0;u<p;u++)if(pc(d[u])>=2&&pc(d[u])<=4){
    int count=0;for(int v=0;v<p;v++)count+=d[v]==d[u];int size=pc(d[u]);if(count>size)return false;
    if(count==size)for(int v=0;v<p;v++)if(d[v]!=d[u]&&(d[v]&d[u])){d[v]&=~d[u];if(!d[v])return false;changed=true;}
   }
   for(int u=0;u<p;u++)for(auto [v,c]:arcs[u])if(!restrict_pair(d,u,v,c,changed))return false;
   // Red degree in an induced graph = regular parent degree minus red links
   // to omitted vertices. Domain bounds provide safe cardinality propagation.
   if(p>q.n)for(int u=0;u<q.n;u++){
    int low=(p-1)/2-q.bounds[u].second,high=(p-1)/2-q.bounds[u].first;Bits keep=0,mask=d[u];
    while(mask){int a=first(mask);mask&=mask-1;int lo=0,hi=0;
     for(int v=q.n;v<p;v++){lo+=(d[v]&~adj[a])==0;hi+=bool(d[v]&adj[a]);}
     if(lo<=high&&hi>=low)keep|=Bits(1)<<a;
    }
    if(!keep)return false;if(keep!=d[u]){d[u]=keep;changed=true;}
   }
   if(!q.cuts.empty()){
    array<Bits,104>must{},possible{};
    for(int u=0;u<q.n;u++){must[u]=full;Bits mask=d[u];while(mask){int a=first(mask);mask&=mask-1;must[u]&=adj[a];possible[u]|=adj[a];}}
    for(auto&cut:q.cuts){int lo=0,hi=0;
     for(int u:cut.a)for(int v:cut.b){lo+=(d[v]&~must[u])==0;hi+=bool(d[v]&possible[u]);}
     if(lo>cut.hi||hi<cut.lo)return false;
     if(lo==cut.hi||hi==cut.lo)for(int u:cut.a)for(int v:cut.b){
      int forced=-1;if(lo==cut.hi&&(d[v]&~must[u]))forced=0;
      if(hi==cut.lo&&(d[v]&possible[u]))forced=1;
      if(forced>=0){if(!restrict_pair(d,u,v,forced,changed)||!restrict_pair(d,v,u,forced,changed))return false;}
     }
    }
   }
  }
  return true;
 }
 bool dfs(State d){
  nodes++;if(expired())return false;if(!propagate(d))return false;
  int chosen=-1,best_size=1000,best_degree=-1;
  for(int u=0;u<p;u++){int size=pc(d[u]),degree=arcs[u].size()+cut_degree[u];
   if(size>1&&(size<best_size||(size==best_size&&degree>best_degree))){chosen=u;best_size=size;best_degree=degree;}}
  if(chosen<0){answer.resize(q.n);for(int u=0;u<q.n;u++)answer[u]=first(d[u]);return true;}
  vector<pair<int,int>>values;Bits mask=d[chosen];
  while(mask){int a=first(mask);mask&=mask-1;int score=0;for(auto[v,c]:arcs[chosen])score+=pc(neighborhood(a,c)&d[v]);values.push_back({-score,a});}
  sort(values.begin(),values.end());
  for(auto[score,a]:values){if(!(d[chosen]&(Bits(1)<<a)))continue;State next=d;next[chosen]=Bits(1)<<a;if(dfs(next))return true;if(expired())return false;
   d[chosen]&=~(Bits(1)<<a);if(!d[chosen]||!propagate(d))return false;}return false;
 }
 bool run(){
  vector<int>candidates;for(int a=q.n;a<104;a++)candidates.push_back(a);
  if(wide)reverse(candidates.begin(),candidates.end());
  for(int candidate:candidates){p=candidate;if(expired())break;
   if(p%4!=1)continue;bool prime=true;for(int d=2;d*d<=p;d++)if(p%d==0)prime=false;if(!prime)continue;
   full=(Bits(1)<<p)-1;vector<int>res(p,0);for(int a=1;a<p;a++)res[a*a%p]=1;
   adj.fill(0);for(int u=0;u<p;u++)for(int v=0;v<p;v++)if(u!=v&&res[(u-v+p)%p])adj[u]|=Bits(1)<<v;
   if(clique(full,q.kr,1)||clique(full,q.kb,0))continue;
   bool possible=true;if(p==q.n)for(auto[lo,hi]:q.bounds)if(! (lo<=(p-1)/2&&(p-1)/2<=hi))possible=false;if(!possible)continue;
   arcs.assign(p,{});cut_degree.assign(p,0);
   auto add=[&](int u,int v,int c){arcs[u].push_back({v,c});arcs[v].push_back({u,c});};
   for(auto&e:q.edges)if(e.fixed>=0)add(e.u,e.v,e.fixed);
   if(p>q.n)for(int u=0;u<q.n;u++){
    int low=(p-1)/2-q.bounds[u].second,high=(p-1)/2-q.bounds[u].first;
    if(high==0)for(int v=q.n;v<p;v++)add(u,v,0);
    if(low==p-q.n)for(int v=q.n;v<p;v++)add(u,v,1);
   }
   for(auto&c:q.cuts){for(int u:c.a)cut_degree[u]++;for(int u:c.b)cut_degree[u]++;}
   State state{};for(int u=0;u<p;u++)state[u]=full;
   int root=0;for(int u=1;u<p;u++)if(arcs[u].size()>arcs[root].size())root=u;state[root]=1;
   if(!arcs[root].empty()){
    auto anchor=*max_element(arcs[root].begin(),arcs[root].end(),[&](auto a,auto b){return arcs[a.first].size()<arcs[b.first].size();});
    int a=1;if(anchor.second==0)while(res[a])a++;state[anchor.first]=Bits(1)<<a;
   }
   if(dfs(state))return true;
  }
  return false;
 }
};
int main(int argc,char**argv){Search s;s.read();if(!cin||s.n<5||s.n>80)return 2;
 if(argc>1&&(string(argv[1])=="embed"||string(argv[1])=="embed-wide")){
  Embedding e(s);e.wide=string(argv[1])=="embed-wide";bool okay=e.run();cerr<<"embedding_nodes="<<e.nodes<<" valid="<<okay<<'\n';if(!okay)return 1;
  int p=e.p;vector<int>res(p,0);for(int a=1;a<p;a++)res[a*a%p]=1;
  for(int u=0;u<s.n;u++){for(int v=0;v<s.n;v++)cout<<(u==v?'.':res[(e.answer[u]-e.answer[v]+p)%p]?'1':'0');cout<<'\n';}return 0;
 }
 bool okay=s.run();
 for(int u=0;u<s.n;u++){for(int v=0;v<s.n;v++)cout<<(u==v?'.':bool(s.red[u]&(Bits(1)<<v))?'1':'0');cout<<'\n';}
 cerr<<"best_penalty="<<s.best_raw<<" steps="<<s.steps<<" valid="<<okay<<'\n';return okay?0:1;}
