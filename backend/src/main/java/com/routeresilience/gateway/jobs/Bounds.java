package com.routeresilience.gateway.jobs;

/**
 * The error bound that turns sampling into a guarantee. Mirrors the Python
 * {@code approx_betweenness} math so the gateway can size a job and report its current ε
 * without a round-trip to the compute service.
 *
 * <p>Source sampling estimates each edge's normalized betweenness as a mean of i.i.d. [0,1]
 * variables, so Hoeffding bounds one edge and a union bound over the {@code m} edges makes it
 * hold for all of them: {@code k ≥ ln(2m/δ) / (2ε²)} sources guarantee a max error ≤ ε with
 * probability ≥ 1−δ. Invert it and you get the ε already certified after {@code k} sources —
 * which is exactly the number that ticks down on the progress bar.
 */
public final class Bounds {

    private Bounds() {}

    /** Sources needed for an ε-additive estimate of every edge at confidence 1−δ. */
    public static int sampleSize(int m, double eps, double delta) {
        return (int) Math.ceil(Math.log(2.0 * m / delta) / (2.0 * eps * eps));
    }

    /** The ε the bound certifies once {@code samples} sources are in. */
    public static double achievedEpsilon(int m, long samples, double delta) {
        if (samples <= 0) {
            return 1.0;   // nothing sampled yet — betweenness is in [0,1], so ε ≤ 1 trivially
        }
        return Math.sqrt(Math.log(2.0 * m / delta) / (2.0 * samples));
    }
}
