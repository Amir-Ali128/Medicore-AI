#pragma once

#include <cstdint>

namespace medicore::vision {

struct ImageMetadata {
    int width{0};
    int height{0};
    int channels{0};
    double mean_intensity{0.0};
    double stddev_intensity{0.0};
    std::uint8_t min_intensity{0};
    std::uint8_t max_intensity{0};
};

}  // namespace medicore::vision
