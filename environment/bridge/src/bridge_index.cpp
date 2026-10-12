// Deliberately incomplete native graph engine. Repair this source file.
// The public Python adapter provides valid '+', '-', '?' operations.
#include <iostream>
#include <string>

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    int vertices = 0, operations = 0;
    if (!(std::cin >> vertices >> operations) || vertices <= 0 || operations < 0)
        return 2;
    std::string line;
    std::getline(std::cin, line);
    int query_index = 0;
    for (int i = 0; i < operations; ++i) {
        if (!std::getline(std::cin, line)) return 2;
        if (!line.empty() && line[0] == '?') {
            std::cout << query_index++;
            for (int field = 0; field < 15; ++field) std::cout << " 0";
            std::cout << '\n';
        }
    }
}
