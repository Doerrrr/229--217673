#include "ddi_snapshot.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <tuple>
#include <utility>
#include <vector>

namespace {
using u64 = uint64_t;
using u32 = uint32_t;
using Edge = std::tuple<u64,u32,u64>;
struct KeyHash {
    size_t operator()(u64 key) const {
        key ^= key >> 30; key *= UINT64_C(0xbf58476d1ce4e5b9);
        key ^= key >> 27; key *= UINT64_C(0x94d049bb133111eb);
        return size_t(key ^ (key >> 31));
    }
    size_t operator()(const Edge &key) const {
        return (*this)(std::get<0>(key)) ^ ((*this)(std::get<1>(key)) << 1)
            ^ ((*this)(std::get<2>(key)) << 2);
    }
};
template<class K,class V> struct Table {
    using Part = std::map<K,V>;
    static constexpr size_t N = 256;
    std::array<std::shared_ptr<Part>,N> parts;
    Table() { for (auto &p:parts) p=std::make_shared<Part>(); }
    const V *get(const K &key) const {
        const auto &p=*parts[KeyHash{}(key)%N];
        auto it=p.find(key); return it==p.end()?nullptr:&it->second;
    }
    Part &edit(const K &key) {
        auto &p=parts[KeyHash{}(key)%N];
        if (!p.unique()) p=std::make_shared<Part>(*p);
        return *p;
    }
    void put(const K &key,const V &value) { edit(key)[key]=value; }
    void erase(const K &key) { edit(key).erase(key); }
    template<class Fn> void each(Fn fn) const {
        for (const auto &p:parts) for (const auto &[k,v]:*p) fn(k,v);
    }
};
struct Binding {u32 state; u64 molecule;};
struct Evidence {u64 d1; u32 type; u64 d2;};
struct Resolved {u32 reason; Edge edge;};
using Ids = std::shared_ptr<std::set<u64>>;
struct State {
    u64 revision=0;
    Table<u64,Binding> bindings;
    Table<u64,u32> events;
    Table<u64,Evidence> evidence;
    Table<u64,Ids> by_drug,by_type;
    Table<u64,Resolved> resolved;
    Table<Edge,u64> edges;
    std::array<u64,8> reasons{};
    mutable std::mutex cache_lock;
    mutable std::shared_ptr<const std::vector<ddi_edge>> cache;
    State() = default;
    State(const State &s):revision(s.revision),bindings(s.bindings),events(s.events),
        evidence(s.evidence),by_drug(s.by_drug),by_type(s.by_type),
        resolved(s.resolved),edges(s.edges),reasons(s.reasons) {}
    void invalidate() {cache.reset();}
    const std::vector<ddi_edge> &view() const {
        std::lock_guard<std::mutex> lock(cache_lock);
        if (!cache) {
            auto v=std::make_shared<std::vector<ddi_edge>>();
            edges.each([&](const Edge &k,u64 n){v->push_back({std::get<0>(k),std::get<1>(k),0,std::get<2>(k),n});});
            std::sort(v->begin(),v->end(),[](const ddi_edge &a,const ddi_edge &b){
                return std::tie(a.d1,a.type,a.d2)<std::tie(b.d1,b.type,b.d2);
            });
            cache=std::move(v);
        }
        return *cache;
    }
    void adjacency(Table<u64,Ids> &table,u64 id,u64 key,bool add) {
        const auto *old=table.get(id);
        Ids value=old?*old:std::make_shared<std::set<u64>>();
        /* value has our local owner and the old map owner at minimum. */
        if (old && value.use_count()>2) value=std::make_shared<std::set<u64>>(*value);
        else if (old) {
            /* Detach the map shard before deciding whether the set is shared
             * through an earlier state: the shard itself can share the only
             * pointer to this set. */
            table.edit(id);
            old=table.get(id);
            value=*old;
            if (value.use_count()>2) value=std::make_shared<std::set<u64>>(*value);
        }
        if (add) value->insert(key); else value->erase(key);
        if (value->empty()) table.erase(id); else table.put(id,value);
    }
    Resolved classify(const Evidence &e) const {
        const Binding *a=bindings.get(e.d1),*b=bindings.get(e.d2);
        if (!a || !b) return {DDI_MISSING_DRUG,{}};
        if (a->state==DDI_CONFLICTING || b->state==DDI_CONFLICTING) return {DDI_CONFLICTING_DRUG,{}};
        if (a->state==DDI_INVALID_ONLY || b->state==DDI_INVALID_ONLY) return {DDI_INVALID_DRUG,{}};
        const u32 *event=events.get(e.type);
        if (!event) return {DDI_UNKNOWN_EVENT,{}};
        if (*event==DDI_CONFLICTING) return {DDI_CONFLICTING_EVENT,{}};
        if (e.d1==e.d2) return {DDI_SELF,{}};
        if (a->molecule==b->molecule) return {DDI_ALIAS_SELF,{}};
        return {DDI_ACCEPTED,{a->molecule,e.type,b->molecule}};
    }
    void undo_resolution(u64 key) {
        const Resolved *r=resolved.get(key);
        if (!r) return;
        --reasons[r->reason];
        if (r->reason==DDI_ACCEPTED) {
            const auto edge=r->edge;
            const u64 n=*edges.get(edge);
            if (n==1) edges.erase(edge); else edges.put(edge,n-1);
        }
        resolved.erase(key);
    }
    void evaluate(u64 key) {
        undo_resolution(key);
        const Evidence *e=evidence.get(key);
        if (!e) return;
        const auto r=classify(*e);
        resolved.put(key,r); ++reasons[r.reason];
        if (r.reason==DDI_ACCEPTED) {
            const auto *old=edges.get(r.edge);
            const auto n=old?*old:0;
            edges.put(r.edge,n+1);
        }
    }
    void binding(u64 id,u32 state,u64 molecule) {
        if (state==DDI_MISSING) bindings.erase(id);
        else bindings.put(id,{state,molecule});
        const auto *affected=by_drug.get(id);
        if (affected) for (u64 key:**affected) evaluate(key);
        invalidate();
    }
    void event(u32 type,u32 state) {
        if (state==DDI_MISSING) events.erase(type); else events.put(type,state);
        const auto *affected=by_type.get(type);
        if (affected) for (u64 key:**affected) evaluate(key);
        invalidate();
    }
    void remove(u64 key) {
        const auto *existing=evidence.get(key);
        if (!existing) return;
        const Evidence e=*existing;
        undo_resolution(key);
        evidence.erase(key);
        adjacency(by_drug,e.d1,key,false);
        if (e.d2!=e.d1) adjacency(by_drug,e.d2,key,false);
        adjacency(by_type,e.type,key,false);
        invalidate();
    }
    void put(u64 key,u64 d1,u32 type,u64 d2) {
        remove(key);
        evidence.put(key,{d1,type,d2});
        adjacency(by_drug,d1,key,true);
        if (d2!=d1) adjacency(by_drug,d2,key,true);
        adjacency(by_type,type,key,true);
        evaluate(key); invalidate();
    }
};
struct Control {
    std::mutex lock;
    std::atomic<bool> closed{false};
    std::shared_ptr<State> current=std::make_shared<State>();
};
struct Op {u32 kind;u64 key;u64 a;u32 state;u64 b;};
void apply(State &state,const Op &op) {
    if (op.kind==0) state.binding(op.key,op.state,op.a);
    else if (op.kind==1) state.event(u32(op.key),op.state);
    else if (op.kind==2) state.put(op.key,op.a,op.state,op.b);
    else state.remove(op.key);
}
}
struct ddi_engine {std::shared_ptr<Control> control=std::make_shared<Control>();};
struct ddi_snapshot {std::shared_ptr<State> state;};
struct ddi_diff {std::vector<ddi_change> changes;};
struct ddi_tx {
    struct Point {u64 token;std::shared_ptr<State> state;size_t log_size;};
    std::shared_ptr<Control> control;
    std::shared_ptr<State> working;
    u64 base=0,next_token=1;
    bool open=true;
    std::vector<Op> log;
    std::vector<Point> points;
    void writable() {if (!working.unique()) working=std::make_shared<State>(*working);}
};
namespace {
int usable(ddi_tx *tx) {
    if (!tx) return DDI_INVALID;
    if (!tx->open || tx->control->closed.load()) return DDI_CLOSED;
    return DDI_OK;
}
int mutate(ddi_tx *tx,const Op &op) {
    const int rc=usable(tx); if (rc) return rc;
    try {tx->writable(); tx->log.push_back(op); apply(*tx->working,op); return DDI_OK;}
    catch (...) {tx->open=false;return DDI_FAILED;}
}
}
extern "C" {
int ddi_engine_new(ddi_engine **out) {
    if (!out) return DDI_INVALID;
    try {auto e=std::make_unique<ddi_engine>();*out=e.release();return DDI_OK;}
    catch (...) {return DDI_FAILED;}
}
void ddi_engine_free(ddi_engine *e) {
    if (e) {std::lock_guard<std::mutex> lock(e->control->lock);e->control->closed.store(true);}
    delete e;
}
int ddi_begin(ddi_engine *e,ddi_tx **out) {
    if (!e || !out) return DDI_INVALID;
    try {
        std::lock_guard<std::mutex> lock(e->control->lock);
        if (e->control->closed.load()) return DDI_CLOSED;
        auto tx=std::make_unique<ddi_tx>();tx->control=e->control;
        tx->base=e->control->current->revision;
        tx->working=std::make_shared<State>(*e->control->current);
        *out=tx.release();return DDI_OK;
    } catch (...) {return DDI_FAILED;}
}
void ddi_tx_free(ddi_tx *tx) {delete tx;}
int ddi_bind(ddi_tx *tx,u64 id,u32 state,u64 molecule) {
    if (!id || state>DDI_INVALID_ONLY || (state==DDI_VALID)!=(molecule!=0)) return DDI_INVALID;
    return mutate(tx,{0,id,molecule,state,0});
}
int ddi_event(ddi_tx *tx,u32 type,u32 state) {
    if (state>DDI_CONFLICTING) return DDI_INVALID;
    return mutate(tx,{1,type,0,state,0});
}
int ddi_put(ddi_tx *tx,u64 key,u64 a,u32 type,u64 b) {
    if (!key || !a || !b) return DDI_INVALID;
    return mutate(tx,{2,key,a,type,b});
}
int ddi_remove(ddi_tx *tx,u64 key) {
    if (!key) return DDI_INVALID;
    return mutate(tx,{3,key,0,0,0});
}
int ddi_savepoint(ddi_tx *tx,u64 *token) {
    if (!token) return DDI_INVALID;
    const int rc=usable(tx);if (rc) return rc;
    if (tx->next_token==std::numeric_limits<u64>::max()) return DDI_FAILED;
    try {
        const u64 next=tx->next_token;
        tx->points.push_back({next,tx->working,tx->log.size()});
        ++tx->next_token;*token=next;return DDI_OK;
    } catch (...) {return DDI_FAILED;}
}
int ddi_rollback(ddi_tx *tx,u64 token) {
    const int rc=usable(tx);if (rc) return rc;
    auto &points=tx->points;
    const auto p=std::find_if(points.begin(),points.end(),[&](const auto &v){return v.token==token;});
    if (p==points.end()) return DDI_INVALID;
    tx->working=p->state;tx->log.resize(p->log_size);points.erase(p+1,points.end());return DDI_OK;
}
int ddi_release(ddi_tx *tx,u64 token) {
    const int rc=usable(tx);if (rc) return rc;
    auto &points=tx->points;
    const auto p=std::find_if(points.begin(),points.end(),[&](const auto &v){return v.token==token;});
    if (p==points.end()) return DDI_INVALID;
    points.erase(p,points.end());return DDI_OK;
}
int ddi_rebase(ddi_tx *tx) {
    const int rc=usable(tx);if (rc) return rc;
    try {
        std::shared_ptr<State> fresh;
        {
            std::lock_guard<std::mutex> lock(tx->control->lock);
            if (tx->control->closed.load()) return DDI_CLOSED;
            fresh=std::make_shared<State>(*tx->control->current);
        }
        const u64 base=fresh->revision;
        for (const auto &op:tx->log) apply(*fresh,op);
        tx->working=std::move(fresh);tx->base=base;tx->points.clear();return DDI_OK;
    } catch (...) {tx->open=false;return DDI_FAILED;}
}
int ddi_commit(ddi_tx *tx,u64 *revision) {
    if (!revision) return DDI_INVALID;
    const int rc=usable(tx);if (rc) return rc;
    try {
        std::lock_guard<std::mutex> lock(tx->control->lock);
        if (tx->control->closed.load()) return DDI_CLOSED;
        if (tx->base!=tx->control->current->revision) return DDI_CONFLICT;
        if (tx->base==std::numeric_limits<u64>::max()) return DDI_FAILED;
        tx->writable();tx->working->revision=tx->base+1;
        tx->control->current=tx->working;tx->open=false;
        *revision=tx->working->revision;return DDI_OK;
    } catch (...) {tx->open=false;return DDI_FAILED;}
}
int ddi_current(ddi_engine *e,ddi_snapshot **out) {
    if (!e || !out) return DDI_INVALID;
    try {
        std::lock_guard<std::mutex> lock(e->control->lock);
        if (e->control->closed.load()) return DDI_CLOSED;
        auto snap=std::make_unique<ddi_snapshot>();snap->state=e->control->current;
        *out=snap.release();return DDI_OK;
    } catch (...) {return DDI_FAILED;}
}
int ddi_preview(ddi_tx *tx,ddi_snapshot **out) {
    if (!out) return DDI_INVALID;
    const int rc=usable(tx);if (rc) return rc;
    try {auto s=std::make_unique<ddi_snapshot>();s->state=tx->working;*out=s.release();return DDI_OK;}
    catch (...) {return DDI_FAILED;}
}
void ddi_snapshot_free(ddi_snapshot *s) {delete s;}
u64 ddi_revision(const ddi_snapshot *s) {return s?s->state->revision:0;}
int ddi_edges(ddi_snapshot *s,const ddi_edge **out,size_t *count) {
    if (!s || !out || !count) return DDI_INVALID;
    try {const auto &v=s->state->view();*out=v.empty()?nullptr:v.data();*count=v.size();return DDI_OK;}
    catch (...) {return DDI_FAILED;}
}
int ddi_counts(ddi_snapshot *s,u64 out[8]) {
    if (!s || !out) return DDI_INVALID;
    std::copy(s->state->reasons.begin(),s->state->reasons.end(),out);return DDI_OK;
}
int ddi_support(ddi_snapshot *s,u64 a,u32 type,u64 b,u64 *out) {
    if (!s || !out || !a || !b) return DDI_INVALID;
    const auto *count=s->state->edges.get({a,type,b});*out=count?*count:0;return DDI_OK;
}
int ddi_compare(ddi_snapshot *before,ddi_snapshot *after,ddi_diff **out) {
    if (!before || !after || !out) return DDI_INVALID;
    try {
        const auto &a=before->state->view(),&b=after->state->view();
        auto delta=std::make_unique<ddi_diff>();size_t i=0,j=0;
        const auto key=[](const ddi_edge &e){return std::tie(e.d1,e.type,e.d2);};
        const auto add=[&](const ddi_edge &e,u64 old,u64 now){
            delta->changes.push_back({e.d1,e.type,0,e.d2,old,now});
        };
        while (i<a.size() || j<b.size()) {
            if (j==b.size() || (i<a.size() && key(a[i])<key(b[j]))) {add(a[i],a[i].support,0);++i;}
            else if (i==a.size() || key(b[j])<key(a[i])) {add(b[j],0,b[j].support);++j;}
            else {if (a[i].support!=b[j].support) add(a[i],a[i].support,b[j].support);++i;++j;}
        }
        *out=delta.release();return DDI_OK;
    } catch (...) {return DDI_FAILED;}
}
int ddi_changes(ddi_diff *delta,const ddi_change **out,size_t *count) {
    if (!delta || !out || !count) return DDI_INVALID;
    *out=delta->changes.empty()?nullptr:delta->changes.data();*count=delta->changes.size();return DDI_OK;
}
void ddi_diff_free(ddi_diff *delta) {delete delta;}
}
