package com.routeresilience.gateway.jobs;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/** The sampling bound is the load-bearing claim ("ε with confidence 1−δ"), so pin its shape. */
class BoundsTest {

    @Test
    void tighterEpsilonCostsQuadraticallyMoreSamples() {
        int coarse = Bounds.sampleSize(80, 0.10, 0.1);
        int fine = Bounds.sampleSize(80, 0.05, 0.1);
        assertThat(fine).isGreaterThan(3 * coarse);          // k ∝ 1/ε²
    }

    @Test
    void achievedEpsilonInvertsSampleSize() {
        int k = Bounds.sampleSize(80, 0.05, 0.1);
        assertThat(Bounds.achievedEpsilon(80, k, 0.1)).isLessThanOrEqualTo(0.05 + 1e-9);
        assertThat(Bounds.achievedEpsilon(80, k, 0.1)).isGreaterThan(0.04);
    }

    @Test
    void moreSamplesNeverWorsensTheBound() {
        assertThat(Bounds.achievedEpsilon(80, 2000, 0.1))
                .isLessThan(Bounds.achievedEpsilon(80, 500, 0.1));
    }
}
