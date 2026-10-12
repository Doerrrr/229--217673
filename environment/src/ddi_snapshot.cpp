// Deployed native draft: raw evidence is retained, but the version/curation
// integration is incomplete. Repair this file or add C++ helpers under src/.
#include "ddi_snapshot.h"
#include <map>
#include <memory>
#include <tuple>
#include <vector>
using U=uint64_t;
struct Raw {U a;uint32_t type;U b;};
struct Store {
    U revision=0;
    std::map<U,std::pair<uint32_t,U>> drugs;
    std::map<uint32_t,uint32_t> events;
    std::map<U,Raw> evidence;
    std::vector<ddi_edge> view;
};
struct ddi_engine {std::shared_ptr<Store> state=std::make_shared<Store>();};
struct ddi_tx {std::shared_ptr<Store> state;U point=0;bool open=true;};
struct ddi_snapshot {std::shared_ptr<Store> state;};
struct ddi_diff {std::vector<ddi_change> rows;};
extern "C" {
int ddi_engine_new(ddi_engine **out) {if(!out)return 1;*out=new ddi_engine;return 0;}
void ddi_engine_free(ddi_engine *e) {delete e;}
int ddi_begin(ddi_engine *e,ddi_tx **out) {if(!e||!out)return 1;*out=new ddi_tx{e->state};return 0;}
void ddi_tx_free(ddi_tx *tx) {delete tx;}
int ddi_bind(ddi_tx *tx,U id,uint32_t state,U mol) {if(!tx||!id)return 1;tx->state->drugs[id]={state,mol};return 0;}
int ddi_event(ddi_tx *tx,uint32_t type,uint32_t state) {if(!tx)return 1;tx->state->events[type]=state;return 0;}
int ddi_put(ddi_tx *tx,U key,U a,uint32_t type,U b) {if(!tx||!key)return 1;tx->state->evidence[key]={a,type,b};return 0;}
int ddi_remove(ddi_tx *tx,U key) {if(!tx)return 1;tx->state->evidence.erase(key);return 0;}
int ddi_savepoint(ddi_tx *tx,U *out) {if(!tx||!out)return 1;*out=++tx->point;return 0;}
int ddi_rollback(ddi_tx *tx,U) {return tx?0:1;}
int ddi_release(ddi_tx *tx,U) {return tx?0:1;}
int ddi_rebase(ddi_tx *tx) {return tx?0:1;}
int ddi_commit(ddi_tx *tx,U *out) {if(!tx||!out)return 1;*out=++tx->state->revision;tx->open=false;return 0;}
int ddi_current(ddi_engine *e,ddi_snapshot **out) {if(!e||!out)return 1;*out=new ddi_snapshot{e->state};return 0;}
int ddi_preview(ddi_tx *tx,ddi_snapshot **out) {if(!tx||!out)return 1;*out=new ddi_snapshot{tx->state};return 0;}
void ddi_snapshot_free(ddi_snapshot *s) {delete s;}
U ddi_revision(const ddi_snapshot *s) {return s?s->state->revision:0;}
int ddi_edges(ddi_snapshot *s,const ddi_edge **out,size_t *n) {
    if(!s||!out||!n)return 1;
    auto &v=s->state->view;v.clear();
    for(const auto &[key,r]:s->state->evidence) v.push_back({r.a,r.type,0,r.b,1});
    *out=v.empty()?nullptr:v.data();*n=v.size();return 0;
}
int ddi_counts(ddi_snapshot *s,U out[8]) {if(!s||!out)return 1;for(int i=0;i<8;++i)out[i]=0;out[7]=s->state->evidence.size();return 0;}
int ddi_support(ddi_snapshot *s,U,uint32_t,U,U *out) {if(!s||!out)return 1;*out=0;return 0;}
int ddi_compare(ddi_snapshot *a,ddi_snapshot *b,ddi_diff **out) {if(!a||!b||!out)return 1;*out=new ddi_diff;return 0;}
int ddi_changes(ddi_diff *d,const ddi_change **out,size_t *n) {if(!d||!out||!n)return 1;*out=nullptr;*n=0;return 0;}
void ddi_diff_free(ddi_diff *d) {delete d;}
}
