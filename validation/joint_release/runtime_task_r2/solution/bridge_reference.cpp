// Author-only feasibility implementation, not a candidate answer or released task.
// SPDX-License-Identifier: CC-BY-SA-4.0
// Incremental bridge-forest idea adapted from the cp-algorithms contributors:
// https://cp-algorithms.com/graph/bridge-searching-online.html
// This implementation adds complete rollback, component metadata and a temporal
// interval traversal. Its correctness is checked against independent deletion BFS.
#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

class ReversibleBridges {
    struct Undo { int *address; int previous; };
    std::vector<int> block_parent, component_parent, forest_parent;
    std::vector<int> component_size, component_min, block_size, block_min;
    std::vector<std::uint64_t> marks;
    std::vector<Undo> journal;
    std::uint64_t traversal = 0;
    int bridge_count = 0, component_count;

    void assign(int &slot, int value) {
        if (slot == value) return;
        journal.push_back({&slot, slot});
        slot = value;
    }
    int block(int v) {
        if (v < 0) return -1;
        int root = v;
        while (block_parent[root] != root) root = block_parent[root];
        while (v != root) {
            int next = block_parent[v];
            assign(block_parent[v], root);
            v = next;
        }
        return root;
    }
    int component(int v) {
        v = block(v);
        int root = v;
        while (component_parent[root] != root)
            root = block(component_parent[root]);
        while (v != root) {
            int next = block(component_parent[v]);
            assign(component_parent[v], root);
            v = next;
        }
        return root;
    }
    void reroot(int v) {
        v = block(v);
        const int root = v, previous_root = component(v);
        const int size = component_size[previous_root];
        const int minimum = component_min[previous_root];
        int child = -1;
        while (v >= 0) {
            int next = block(forest_parent[v]);
            assign(forest_parent[v], child);
            assign(component_parent[v], root);
            child = v;
            v = next;
        }
        assign(component_size[root], size);
        assign(component_min[root], minimum);
    }
    void close_cycle(int a, int b) {
        ++traversal;
        std::vector<int> left, right;
        int common = -1;
        while (common < 0) {
            if (a >= 0) {
                a = block(a);
                left.push_back(a);
                if (marks[a] == traversal) { common = a; break; }
                marks[a] = traversal;
                a = forest_parent[a];
            }
            if (b >= 0) {
                b = block(b);
                right.push_back(b);
                if (marks[b] == traversal) { common = b; break; }
                marks[b] = traversal;
                b = forest_parent[b];
            }
        }
        // Traversal marks are scratch, not graph state. Their monotonically
        // increasing generation never repeats across rollback branches.
        for (const auto *path : {&left, &right}) {
            for (int v : *path) {
                if (v == common) break;
                assign(block_size[common], block_size[common] + block_size[v]);
                assign(block_min[common], std::min(block_min[common], block_min[v]));
                assign(block_parent[v], common);
                assign(bridge_count, bridge_count - 1);
            }
        }
    }
public:
    explicit ReversibleBridges(int n)
        : block_parent(n), component_parent(n), forest_parent(n, -1),
          component_size(n, 1), component_min(n), block_size(n, 1),
          block_min(n), marks(n, 0), component_count(n) {
        for (int i = 0; i < n; ++i)
            block_parent[i] = component_parent[i] = component_min[i] = block_min[i] = i;
    }
    std::size_t mark() const { return journal.size(); }
    void restore(std::size_t position) {
        while (journal.size() > position) {
            auto item = journal.back();
            journal.pop_back();
            *item.address = item.previous;
        }
    }
    void add(int a, int b) {
        a = block(a); b = block(b);
        if (a == b) return;
        int ca = component(a), cb = component(b);
        if (ca == cb) { close_cycle(a, b); return; }
        if (component_size[ca] > component_size[cb]) {
            std::swap(a, b); std::swap(ca, cb);
        }
        reroot(a);
        assign(forest_parent[a], b);
        assign(component_parent[a], b);
        assign(component_size[cb], component_size[cb] + component_size[a]);
        assign(component_min[cb], std::min(component_min[cb], component_min[a]));
        assign(bridge_count, bridge_count + 1);
        assign(component_count, component_count - 1);
    }
    std::array<int, 15> inspect(int a, int b, int edge_a, int edge_b) {
        const int ba = block(a), bb = block(b), ca = component(a), cb = component(b);
        const int active = edge_a >= 0;
        const int critical = active && block(edge_a) != block(edge_b);
        return {component_count, bridge_count, component_count + bridge_count,
                component_min[ca], component_size[ca], block_min[ba], block_size[ba],
                component_min[cb], component_size[cb], block_min[bb], block_size[bb],
                ca == cb, ba == bb, active, critical};
    }
};

struct Interval { int begin, end, a, b; };
struct Query { int a, b, edge_a, edge_b; };
struct Active { int begin, a, b; };

class Timeline {
    std::vector<std::vector<std::pair<int, int>>> tree;
    const std::vector<Query> &queries;
    ReversibleBridges graph;
    std::vector<std::array<int, 15>> results;
    void insert(int node, int lo, int hi, const Interval &span) {
        if (span.begin >= hi || span.end <= lo) return;
        if (span.begin <= lo && hi <= span.end) {
            tree[node].push_back({span.a, span.b});
            return;
        }
        int mid = lo + (hi - lo) / 2;
        insert(node * 2, lo, mid, span);
        insert(node * 2 + 1, mid, hi, span);
    }
    void visit(int node, int lo, int hi) {
        const auto position = graph.mark();
        for (const auto &[a, b] : tree[node]) graph.add(a, b);
        if (hi - lo == 1) {
            const auto &q = queries[lo];
            results[lo] = graph.inspect(q.a, q.b, q.edge_a, q.edge_b);
        } else {
            int mid = lo + (hi - lo) / 2;
            visit(node * 2, lo, mid);
            visit(node * 2 + 1, mid, hi);
        }
        graph.restore(position);
    }
public:
    Timeline(int n, const std::vector<Query> &q, const std::vector<Interval> &spans)
        : tree(4 * q.size() + 4), queries(q), graph(n), results(q.size()) {
        if (q.empty()) return;
        for (const auto &span : spans)
            if (span.begin < span.end) insert(1, 0, static_cast<int>(q.size()), span);
        visit(1, 0, static_cast<int>(q.size()));
    }
    const auto &output() const { return results; }
};

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    int n, operations;
    if (!(std::cin >> n >> operations) || n <= 0 || operations < 0) return 2;
    std::unordered_map<std::uint64_t, Active> active;
    std::vector<Interval> spans;
    std::vector<Query> queries;
    for (int i = 0; i < operations; ++i) {
        char kind; std::uint64_t key; int a, b;
        if (!(std::cin >> kind)) return 2;
        if (kind == '+' || kind == '-') {
            if (!(std::cin >> key) || key == 0) return 2;
            auto old = active.find(key);
            if (old != active.end()) {
                spans.push_back({old->second.begin, static_cast<int>(queries.size()), old->second.a, old->second.b});
                active.erase(old);
            }
            if (kind == '+') {
                if (!(std::cin >> a >> b) || a < 0 || b < 0 || a >= n || b >= n) return 2;
                active.emplace(key, Active{static_cast<int>(queries.size()), a, b});
            }
        } else if (kind == '?') {
            if (!(std::cin >> a >> b >> key) || a < 0 || b < 0 || a >= n || b >= n) return 2;
            auto edge = active.find(key);
            queries.push_back({a, b, edge == active.end() ? -1 : edge->second.a,
                              edge == active.end() ? -1 : edge->second.b});
        } else return 2;
    }
    for (const auto &[key, item] : active)
        spans.push_back({item.begin, static_cast<int>(queries.size()), item.a, item.b});
    Timeline answer(n, queries, spans);
    int ordinal = 0;
    for (const auto &row : answer.output()) {
        std::cout << ordinal++;
        for (int v : row) std::cout << ' ' << v;
        std::cout << '\n';
    }
}
