#ifndef DDI_SNAPSHOT_H
#define DDI_SNAPSHOT_H
#include <stddef.h>
#include <stdint.h>
#ifdef _WIN32
#define DDI_API __declspec(dllexport)
#else
#define DDI_API __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif

/* Public C ABI. All handles are opaque.
 * Valid handles must be freed exactly once, never concurrently with their use.
 * Distinct engines/transactions and reads of one snapshot may run concurrently.
 * A transaction itself is used by one thread at a time. */
typedef struct ddi_engine ddi_engine;
typedef struct ddi_tx ddi_tx;
typedef struct ddi_snapshot ddi_snapshot;
typedef struct ddi_diff ddi_diff;
enum { DDI_OK=0, DDI_INVALID=1, DDI_CONFLICT=2, DDI_CLOSED=3, DDI_FAILED=4 };
enum { DDI_MISSING=0, DDI_VALID=1, DDI_CONFLICTING=2, DDI_INVALID_ONLY=3 };
enum {
    DDI_MISSING_DRUG=0, DDI_CONFLICTING_DRUG=1, DDI_INVALID_DRUG=2,
    DDI_UNKNOWN_EVENT=3, DDI_CONFLICTING_EVENT=4, DDI_SELF=5,
    DDI_ALIAS_SELF=6, DDI_ACCEPTED=7
};
typedef struct {
    uint64_t d1;
    uint32_t type;
    uint32_t reserved;
    uint64_t d2;
    uint64_t support;
} ddi_edge;
typedef struct {
    uint64_t d1;
    uint32_t type;
    uint32_t reserved;
    uint64_t d2;
    uint64_t before;
    uint64_t after;
} ddi_change;

DDI_API int ddi_engine_new(ddi_engine **out);
/* Closes the engine; already acquired snapshots remain fully usable. */
DDI_API void ddi_engine_free(ddi_engine *engine);
DDI_API int ddi_begin(ddi_engine *engine, ddi_tx **out);
DDI_API void ddi_tx_free(ddi_tx *tx);

/* raw IDs, molecule keys, and evidence keys are positive uint64_t.
 * Types include zero and use uint32_t. Missing removes a binding/event entry.
 * A VALID binding requires a positive molecule; all other states require zero.
 * Only MISSING, VALID and CONFLICTING are valid event states.
 * Replacing an evidence key removes all of its old dependency/contribution.
 * Removing absent entries is a valid no-op. INVALID never mutates the tx. */
DDI_API int ddi_bind(ddi_tx *, uint64_t raw_id, uint32_t state, uint64_t molecule);
DDI_API int ddi_event(ddi_tx *, uint32_t type, uint32_t state);
DDI_API int ddi_put(ddi_tx *, uint64_t key, uint64_t raw_d1, uint32_t type, uint64_t raw_d2);
DDI_API int ddi_remove(ddi_tx *, uint64_t key);

/* Savepoint tokens never repeat within a tx. Rollback retains the chosen point
 * and deletes newer points. Release deletes the chosen point and newer points.
 * Rebase replays the surviving operation log on the latest committed state and
 * invalidates every old savepoint. Conflict leaves a transaction open.
 * Successful commit closes it, increments revision even for a no-op and writes
 * new_revision. Output parameters are unchanged for any non-OK return. */
DDI_API int ddi_savepoint(ddi_tx *, uint64_t *token);
DDI_API int ddi_rollback(ddi_tx *, uint64_t token);
DDI_API int ddi_release(ddi_tx *, uint64_t token);
DDI_API int ddi_rebase(ddi_tx *);
DDI_API int ddi_commit(ddi_tx *, uint64_t *new_revision);

DDI_API int ddi_current(ddi_engine *, ddi_snapshot **out);
DDI_API int ddi_preview(ddi_tx *, ddi_snapshot **out);
DDI_API void ddi_snapshot_free(ddi_snapshot *snapshot);
DDI_API uint64_t ddi_revision(const ddi_snapshot *snapshot);
/* Snapshot arrays are immutable, stable until this snapshot is freed and
 * sorted numerically by (d1,type,d2). reserved is always zero.
 * Empty views return NULL/0. All queries are independent of engine lifetime.
 * Counts use the eight reason indices above. A valid duplicate is ACCEPTED;
 * semantic edge.support counts distinct current evidence keys, both directions
 * stay distinct, and molecular alias regrouping is performed on the snapshot. */
DDI_API int ddi_edges(ddi_snapshot *, const ddi_edge **out, size_t *count);
DDI_API int ddi_counts(ddi_snapshot *, uint64_t out[8]);
DDI_API int ddi_support(ddi_snapshot *, uint64_t d1, uint32_t type, uint64_t d2, uint64_t *out);

/* Net support changes between arbitrary snapshots, including different engines
 * and previews. Borrowed delta arrays live until the independently owned diff
 * is freed, not until either source snapshot is freed. */
DDI_API int ddi_compare(ddi_snapshot *, ddi_snapshot *, ddi_diff **out);
DDI_API int ddi_changes(ddi_diff *, const ddi_change **out, size_t *count);
DDI_API void ddi_diff_free(ddi_diff *diff);
#ifdef __cplusplus
}
#endif
#endif
