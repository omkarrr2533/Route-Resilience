package com.routeresilience.gateway.jobs;

/**
 * Parameters for an approximate-betweenness job. Everything is optional and clamped to a sane
 * range in the compact constructor, so a bare {@code POST} with no body runs sensible defaults.
 *
 * <ul>
 *   <li>{@code eps}/{@code delta} — the guarantee: max additive error ε at confidence 1−δ.</li>
 *   <li>{@code batchSamples} — sources per Monte Carlo batch (the progress granularity).</li>
 *   <li>{@code maxSamples} — a hard ceiling so a too-tight ε can't run forever.</li>
 * </ul>
 */
public record ApproxBetweennessRequest(
        String source, String weight,
        Double eps, Double delta,
        Integer batchSamples, Integer maxSamples) {

    public ApproxBetweennessRequest {
        if (source == null || source.isBlank()) source = "sample:koramangala";
        if (weight == null || weight.isBlank()) weight = "length";
        eps = clamp(eps == null ? 0.05 : eps, 0.005, 0.5);
        delta = clamp(delta == null ? 0.1 : delta, 0.001, 0.5);
        batchSamples = (int) clamp(batchSamples == null ? 150 : batchSamples, 10, 5_000);
        maxSamples = (int) clamp(maxSamples == null ? 20_000 : maxSamples, batchSamples, 200_000);
    }

    /** Idempotency key — the estimate is determined by the target, not the batch schedule. */
    public String key() {
        return "approx|" + source + "|" + weight + "|" + eps + "|" + delta;
    }

    private static double clamp(double v, double lo, double hi) {
        return Math.max(lo, Math.min(hi, v));
    }
}
